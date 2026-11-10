"""The console's output kept in the logs folder (LR-15, Tony 2026-11-05): ``console-<pid>.txt``.

Run from source, HeLab sometimes prints errors to its terminal that its log never sees: a traceback
printed by a library, a C++ warning, NumPy's. ``ConsoleTee`` catches them at the file-descriptor
level, so C-level writes are caught too: file descriptors 1 and 2 are each pointed at a pipe, and a
daemon thread per pipe writes every chunk to the file, then hands it to its terminal's own writer thread
(``_Terminal``), so a terminal that stops taking output (a PowerShell window paused by a selection) never
stops the pump: a full pipe would block every writer, ``faulthandler`` too, which writes holding the GIL and
so froze the whole process (the TDC PC, 2026-11-09). What a stuck terminal can't take is dropped there,
never from the file. On Windows, Python's own ``sys.stdout``/``sys.stderr`` on a console write to the
console's handle, not through the descriptor, so they are pointed at the new descriptors too (with the
logging handlers that write to them), or the file would never see them. At ``CAP`` bytes
the file is renamed ``console-<pid>.txt.1`` (replacing the one before) and a new one started, so the
latest output is always kept and a run keeps at most twice ``CAP`` (the console shows the log at
DEBUG). Tidied with the logs; removed at a clean exit while empty.

Not for the crash file (``crash_file``): ``faulthandler`` writes there directly, as this thread dies
with the process. The I/O helpers' stderr is their request's own file (``IOService``), not this.
Off where ``OFF_ENV`` is set (the test suite's conftest sets it, so test runs print as they did).
"""
from __future__ import annotations

import codecs
import io
import logging
import os
import queue
import sys
import threading
from typing import Any, Callable, TextIO, cast

CONSOLE_NAME = "console-{pid}.txt"
CAP = 20 * 1000 * 1000  # bytes, before the file is rotated once
OFF_ENV = "HELAB_NO_CONSOLE_FILE"
TERMINAL_CHUNKS = 256  # held for a slow terminal before its output is dropped (each up to 64 KiB)
# (Windows: a console's raw stream, which writes UTF-8 bytes as text; absent elsewhere.)
_WINDOWS_CONSOLE_IO = cast(Callable[..., Any] | None, getattr(io, "_WindowsConsoleIO", None))


def writes_past_its_descriptor(stream: TextIO) -> bool:
    """Whether ``stream`` writes to a Windows console's handle rather than through its descriptor (so
    ``dup2`` doesn't redirect it). Tests patch it."""
    raw = getattr(getattr(stream, "buffer", None), "raw", None)
    return _WINDOWS_CONSOLE_IO is not None and isinstance(raw, cast(type, _WINDOWS_CONSOLE_IO))


def _console(fd: int) -> Any:
    """A Windows console's raw stream on ``fd`` (UTF-8 written as text, as Python writes to a console); None
    elsewhere, or for a pipe or a file (written as bytes)."""
    if _WINDOWS_CONSOLE_IO is None:
        return None
    try:
        return _WINDOWS_CONSOLE_IO(fd, "w", closefd=False)
    except (OSError, ValueError):
        return None


class _Terminal:
    """Writes chunks to the original terminal on its own thread; ``put`` never waits. ``console``: the
    terminal's console stream (tests give a stand-in), by default ``_console(fd)``."""

    def __init__(self, fd: int, console: Any = None) -> None:
        self.fd = fd
        self.dropped = 0  # bytes the terminal didn't take in time
        self.chunks: queue.Queue[bytes | None] = queue.Queue(TERMINAL_CHUNKS)
        self.console: Any = console if console is not None else _console(fd)
        self.thread = threading.Thread(target=self._run, name=f"console-tee-terminal-{fd}", daemon=True)
        self.thread.start()

    def put(self, chunk: bytes) -> None:
        try:
            self.chunks.put_nowait(chunk)
        except queue.Full:
            self.dropped += len(chunk)

    def _run(self) -> None:
        # A console takes whole UTF-8 characters only, and the pump's reads end anywhere: a character split
        # across two reads waits here for its rest (an invalid byte becomes U+FFFD; one left at the end too).
        decoder = codecs.getincrementaldecoder("utf-8")("replace") if self.console is not None else None
        while True:
            chunk = self.chunks.get()
            data = chunk if chunk is not None else b""
            if decoder is not None:
                data = decoder.decode(data, final=chunk is None).encode("utf-8")
            try:
                self._write(data)
            except (OSError, ValueError):
                return  # (The terminal went: the file still gets it.)
            if chunk is None:
                return

    def _write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = self.console.write(view) if self.console is not None else os.write(self.fd, view)
            view = view[written or len(view):]  # (Nothing taken: dropped, rather than tried for ever.)

    def close(self, timeout: float) -> None:
        """Let it write what it holds, for up to ``timeout`` seconds."""
        try:
            self.chunks.put(None, timeout=timeout)
        except queue.Full:
            return
        self.thread.join(timeout=timeout)


class ConsoleTee:
    """File descriptors 1 and 2 copied to ``path`` as well as to where they went (``start``, ``stop``)."""

    def __init__(self, path: str, cap: int = CAP) -> None:
        self.path, self.cap = path, cap
        self.written = 0
        self.rotations = 0
        self._file = open(path, "ab", buffering=0)
        self._lock = threading.Lock()
        self._ends: list[tuple[int, int | None, threading.Thread, _Terminal | None]] = []  # (fd, its original, ...)
        self._rebound: list[tuple[str, TextIO, TextIO]] = []  # (sys's name, the stream it had, the new one)

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
            terminal = _Terminal(original) if original is not None else None
            pump = threading.Thread(target=self._pump, args=(read, terminal), name=f"console-tee-{fd}", daemon=True)
            pump.start()
            self._ends.append((fd, original, pump, terminal))
        self._rebind()

    def _rebind(self) -> None:
        """Point a ``sys.stdout``/``sys.stderr`` that writes past its descriptor (a Windows console) at the
        descriptor, and the logging handlers writing to it at the new stream."""
        for name, fd in (("stdout", 1), ("stderr", 2)):
            old = cast(TextIO | None, getattr(sys, name))
            if old is None or not writes_past_its_descriptor(old):
                continue
            new = cast(TextIO, io.TextIOWrapper(io.FileIO(fd, "w", closefd=False), encoding="utf-8",
                                                errors="backslashreplace", line_buffering=True, write_through=True))
            setattr(sys, name, new)
            _swap_handler_streams(old, new)
            self._rebound.append((name, old, new))

    def _pump(self, read: int, terminal: _Terminal | None) -> None:
        """Copy the pipe to the file and the terminal until it closes. Never stops early, never waits on the
        terminal: a writer to a full pipe would wait for ever."""
        while True:
            try:
                chunk = os.read(read, 65536)
            except OSError:
                break
            if not chunk:
                break
            self.write(chunk)
            if terminal is not None:
                terminal.put(chunk)
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
        for name, old, new in reversed(self._rebound):
            setattr(sys, name, old)
            _swap_handler_streams(new, old)
        self._rebound = []
        for fd, original, _, _ in self._ends:
            if original is not None:
                os.dup2(original, fd)  # (Closes the pipe's write end: the pump reads the rest, then stops.)
            else:
                null = os.open(os.devnull, os.O_WRONLY)
                os.dup2(null, fd)
                os.close(null)
        for _, original, pump, terminal in self._ends:
            pump.join(timeout=2.0)
            if terminal is not None:
                terminal.close(timeout=2.0)  # (It still writes the rest to the terminal: closed after.)
                if terminal.thread.is_alive():
                    continue  # (Stuck on a terminal that takes nothing: its descriptor left open for it.)
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


def _swap_handler_streams(old: TextIO, new: TextIO) -> None:
    """Logging handlers writing to ``old`` write to ``new`` (``coloredlogs``' console handler holds the
    ``sys.stderr`` it was installed with)."""
    loggers = [logging.getLogger(), *(logger for logger in logging.Logger.manager.loggerDict.values()
                                      if isinstance(logger, logging.Logger))]
    for logger in loggers:
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream is old:
                handler.setStream(new)


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
