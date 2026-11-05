"""The console's output kept in the logs folder (LR-15, Tony 2026-11-05): ``console-<pid>.txt``.

Run from source, HeLab sometimes prints errors to its terminal that its log never sees: a traceback
printed by a library, a C++ warning, NumPy's. ``ConsoleTee`` catches them at the file-descriptor
level, so C-level writes are caught too: file descriptors 1 and 2 are each pointed at a pipe, and a
daemon thread per pipe writes every chunk to the original terminal and to the file. At ``CAP`` bytes
the file is renamed ``console-<pid>.txt.1`` (replacing the one before) and a new one started, so the
latest output is always kept and a run keeps at most twice ``CAP`` (the console shows the log at
DEBUG). Tidied with the logs; removed at a clean exit while empty.

Not for the crash file (``crash_file``): ``faulthandler`` writes there directly, as this thread dies
with the process. The I/O helpers' stderr is their request's own file (``IOService``), not this.
Off where ``OFF_ENV`` is set (the test suite's conftest sets it, so test runs print as they did).
"""
from __future__ import annotations

import os
import sys
import threading

CONSOLE_NAME = "console-{pid}.txt"
CAP = 20 * 1000 * 1000  # bytes, before the file is rotated once
OFF_ENV = "HELAB_NO_CONSOLE_FILE"


class ConsoleTee:
    """File descriptors 1 and 2 copied to ``path`` as well as to where they went (``start``, ``stop``)."""

    def __init__(self, path: str, cap: int = CAP) -> None:
        self.path, self.cap = path, cap
        self.written = 0
        self.rotations = 0
        self._file = open(path, "ab", buffering=0)
        self._lock = threading.Lock()
        self._ends: list[tuple[int, int | None, threading.Thread]] = []  # (fd, its original, the pump)

    def start(self) -> None:
        for fd in (1, 2):
            try:
                original: int | None = os.dup(fd)
            except OSError:  # (No console: a windowed app. The file alone.)
                original = None
            read, write = os.pipe()
            for stream in (sys.stdout, sys.stderr):
                if stream is not None:
                    stream.flush()
            os.dup2(write, fd)
            os.close(write)
            pump = threading.Thread(target=self._pump, args=(read, original), name=f"console-tee-{fd}", daemon=True)
            pump.start()
            self._ends.append((fd, original, pump))

    def _pump(self, read: int, original: int | None) -> None:
        """Copy the pipe to the terminal and the file until it closes. Never stops early: a writer to a
        full pipe would wait for ever."""
        while True:
            try:
                chunk = os.read(read, 65536)
            except OSError:
                break
            if not chunk:
                break
            if original is not None:
                try:
                    view = memoryview(chunk)
                    while view:
                        view = view[os.write(original, view):]
                except OSError:
                    original = None  # (The terminal went: the file still gets it.)
            self.write(chunk)
        os.close(read)

    def write(self, chunk: bytes) -> None:
        """Add ``chunk`` to the file; past ``cap`` bytes, the file is rotated first (``.1``)."""
        with self._lock:
            try:
                if self.written and self.written + len(chunk) > self.cap:
                    self._file.close()
                    os.replace(self.path, self.path + ".1")
                    self._file = open(self.path, "ab", buffering=0)
                    self.written = 0
                    self.rotations += 1
                self._file.write(chunk)
                self.written += len(chunk)
            except (OSError, ValueError):  # (A full disk, or closed at exit: the terminal still has it.)
                pass

    def stop(self) -> None:
        """Point the descriptors back, let the pumps finish what's in the pipes, close the file; removed if
        empty."""
        for stream in (sys.stdout, sys.stderr):
            if stream is not None:
                try:
                    stream.flush()
                except (OSError, ValueError):
                    pass
        for fd, original, _ in self._ends:
            if original is not None:
                os.dup2(original, fd)  # (Closes the pipe's write end: the pump reads the rest, then stops.)
            else:
                null = os.open(os.devnull, os.O_WRONLY)
                os.dup2(null, fd)
                os.close(null)
        for _, original, pump in self._ends:
            pump.join(timeout=2.0)  # (It still writes the rest to the terminal: closed after.)
            if original is not None:
                os.close(original)
        self._ends = []
        with self._lock:
            self._file.close()
        try:
            if os.path.getsize(self.path) == 0:
                os.remove(self.path)
        except OSError:
            pass


def start(folder: str) -> ConsoleTee | None:
    """Keep the console in ``<folder>/console-<pid>.txt`` (``folder`` the logs folder) until ``stop``;
    None where ``OFF_ENV`` is set or the file can't be written."""
    if os.environ.get(OFF_ENV):
        return None
    try:
        os.makedirs(folder, exist_ok=True)
        tee = ConsoleTee(os.path.join(folder, CONSOLE_NAME.format(pid=os.getpid())))
        tee.start()
    except OSError:
        return None
    return tee
