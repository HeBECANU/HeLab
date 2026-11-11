"""A disk cache of decoded .rgadata files, so reloading a folder is fast.

Entries are keyed by the file's absolute path and validated against its size
and modification time, so a changed file is decoded again. Files modified
within ``SETTLE_SECONDS`` may still be being written by RGASoft; they are
always decoded and never cached. A file the parser rejects is remembered
too, and its error is raised again until the file changes. The cache is one SQLite file holding the
configuration JSON and the raw numbers (never a pickle); deleting it is safe.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from .rga_visualiser import RGAData, Scan, parse_rgadata


DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / "rga_visualiser_cache" / "scans.sqlite"
)
# Bump when parse_rgadata's output changes, so old entries are decoded again.
PARSER_VERSION = 1
SETTLE_SECONDS = 10.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    parser_version INTEGER NOT NULL,
    metadata TEXT NOT NULL,
    masses BLOB NOT NULL,
    config_indices BLOB NOT NULL,
    elapsed BLOB NOT NULL,
    point_counts BLOB NOT NULL,
    scan_values BLOB NOT NULL
)
"""
# Files the parser rejected (e.g. an aborted scan with no complete spectrum),
# so they are not read again until they change.
_FAILURES_SCHEMA = """
CREATE TABLE IF NOT EXISTS failures (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    parser_version INTEGER NOT NULL,
    message TEXT NOT NULL
)
"""


def _pack(code: str, values: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(values)}{code}", *values)


def _unpack(code: str, blob: bytes) -> tuple[float, ...]:
    return struct.unpack(f"<{len(blob) // struct.calcsize(code)}{code}", blob)


def _encode(data: RGAData) -> tuple[str, bytes, bytes, bytes, bytes, bytes]:
    # RGASoft stores currents as float32, so storing them as float32 is exact.
    flat = [value for scan in data.scans for value in scan.values]
    return (
        json.dumps(data.metadata, separators=(",", ":")),
        _pack("d", data.masses),
        _pack("q", [scan.config_index for scan in data.scans]),
        _pack("d", [scan.elapsed_seconds for scan in data.scans]),
        _pack("q", [len(scan.values) for scan in data.scans]),
        _pack("f", flat),
    )


def _decode(
    metadata: str,
    masses: bytes,
    config_indices: bytes,
    elapsed: bytes,
    point_counts: bytes,
    scan_values: bytes,
) -> RGAData:
    values = _unpack("f", scan_values)
    scans: list[Scan] = []
    cursor = 0
    for config_index, elapsed_seconds, count in zip(
        _unpack("q", config_indices),
        _unpack("d", elapsed),
        _unpack("q", point_counts),
    ):
        scans.append(
            Scan(
                int(config_index),
                float(elapsed_seconds),
                tuple(values[cursor : cursor + int(count)]),
            )
        )
        cursor += int(count)
    if cursor != len(values):
        raise ValueError("cached scan values do not match their point counts")
    loaded = json.loads(metadata)
    if not isinstance(loaded, dict):
        raise ValueError("cached metadata is not an object")
    return RGAData(
        metadata=loaded,
        masses=tuple(float(mass) for mass in _unpack("d", masses)),
        scans=tuple(scans),
    )


class ScanCache:
    """Decode .rgadata files through a SQLite cache.

    Any problem with the cache itself (a damaged or locked file, a read-only
    folder) turns the cache off for the rest of this session's use and files
    are simply decoded; the cache never makes a load fail.
    """

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path
        self.hits = 0
        self.problem: str | None = None
        self._connection: sqlite3.Connection | None = None
        self._opened = False

    def __enter__(self) -> ScanCache:
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _db(self) -> sqlite3.Connection | None:
        if not self._opened:
            self._opened = True
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(self.path, timeout=5)
                connection.execute(_SCHEMA)
                connection.execute(_FAILURES_SCHEMA)
                connection.commit()
                self._connection = connection
            except (OSError, sqlite3.Error) as exc:
                self.problem = f"cache unavailable: {exc}"
        return self._connection

    def _disable(self, exc: Exception) -> None:
        self.problem = f"cache disabled: {exc}"
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
        self._connection = None

    def load(self, path: Path) -> RGAData:
        """Return the decoded file, from the cache when it is unchanged."""

        stat = path.stat()
        settled = time.time() - stat.st_mtime >= SETTLE_SECONDS
        # absolute(), not resolve(): resolving stats every folder on the share.
        key = str(path.absolute())
        db = self._db() if settled else None
        if db is not None:
            try:
                row = db.execute(
                    "SELECT metadata, masses, config_indices, elapsed, "
                    "point_counts, scan_values FROM files WHERE path = ? "
                    "AND size = ? AND mtime_ns = ? AND parser_version = ?",
                    (key, stat.st_size, stat.st_mtime_ns, PARSER_VERSION),
                ).fetchone()
            except sqlite3.Error as exc:
                self._disable(exc)
                row = None
            failure = None
            if row is None and self._connection is not None:
                try:
                    failure = self._connection.execute(
                        "SELECT message FROM failures WHERE path = ? AND size = ? "
                        "AND mtime_ns = ? AND parser_version = ?",
                        (key, stat.st_size, stat.st_mtime_ns, PARSER_VERSION),
                    ).fetchone()
                except sqlite3.Error as exc:
                    self._disable(exc)
            if failure is not None:
                self.hits += 1
                raise ValueError(str(failure[0]))
            if row is not None:
                try:
                    data = _decode(*row)
                except (ValueError, OverflowError) as exc:
                    data = None
                    self.problem = f"cache entry ignored: {exc}"
                if data is not None:
                    self.hits += 1
                    return data

        try:
            data = parse_rgadata(path)
        except (ValueError, struct.error) as exc:
            db = self._connection if settled else None
            if db is not None:
                try:
                    db.execute(
                        "INSERT OR REPLACE INTO failures VALUES (?, ?, ?, ?, ?)",
                        (key, stat.st_size, stat.st_mtime_ns, PARSER_VERSION, str(exc)),
                    )
                    db.execute("DELETE FROM files WHERE path = ?", (key,))
                except sqlite3.Error as cache_exc:
                    self._disable(cache_exc)
            raise
        db = self._connection if settled else None
        if db is not None:
            try:
                db.execute("DELETE FROM failures WHERE path = ?", (key,))
                db.execute(
                    "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, stat.st_size, stat.st_mtime_ns, PARSER_VERSION, *_encode(data)),
                )
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self._disable(exc)
        return data

    def close(self) -> None:
        """Commit new entries and close the database."""

        if self._connection is None:
            return
        try:
            self._connection.commit()
            self._connection.close()
        except sqlite3.Error as exc:
            self.problem = f"cache not saved: {exc}"
        self._connection = None

