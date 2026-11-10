"""A process's crash file (LR-15, Tony 2026-11-05): every thread's Python stack when it crashes hard.

A segfault in Qt or NumPy, or an abort, ends Python before any excepthook or log line: ``faulthandler``,
pointed at a file opened at start and kept open, still writes the stacks (directly, not through the
console's tee, whose thread dies with the process). A clean exit removes the file while empty.

Standard library only: the I/O helpers start one too (``helab/io_helper.py``, before importing Qt or
the app's settings), in the folder the app names in ``HELPER_DIR_ENV``.
"""
from __future__ import annotations

import atexit
import faulthandler
import os
from typing import IO

CRASH_NAME = "crash-{pid}.txt"
HELPER_CRASH_NAME = "helper-crash-{pid}.txt"
# The folder the app's I/O helpers write their crash files in (the app's logs folder), set by ``IOService``.
HELPER_DIR_ENV = "HELAB_HELPER_CRASH_DIR"

_crash: tuple[IO[str], str] | None = None
# The file ``exit_after``'s timer writes to: kept open to the process's end once armed.
_armed: IO[str] | None = None


def start(folder: str, name: str = CRASH_NAME) -> str:
    """Write every thread's Python stack to ``<folder>/<name>`` (``{pid}`` this process's) if the process
    crashes hard; the file is opened now and kept open. Its path. Raises ``OSError`` if it can't be
    written. A clean exit removes it while empty (``end``)."""
    global _crash
    path = os.path.join(folder, name.format(pid=os.getpid()))
    os.makedirs(folder, exist_ok=True)
    file = open(path, "w", encoding="utf-8")
    end()  # (A second start replaces the first.)
    faulthandler.enable(file=file, all_threads=True)
    _crash = (file, path)
    atexit.register(end)
    return path


def exit_after(seconds: float) -> bool:
    """Quit's last resort (``helab.views.quit_watch``): if this process still runs ``seconds`` from now,
    every thread's stack goes to the crash file and the process ends, with exit code 1. The timer is
    ``faulthandler``'s own C thread, which outlives Python's teardown, where a daemon thread (the quit watch)
    no longer runs (GT-2). False without a crash file. The file then stays open to the process's end, and
    stays even while empty (the startup tidy removes empty ones)."""
    global _armed
    if _crash is None:
        return False
    _armed = _crash[0]
    faulthandler.dump_traceback_later(seconds, exit=True, file=_armed)
    return True


def end() -> None:
    """At a clean exit: stop writing crash stacks to the file, and remove it if nothing was written."""
    global _crash
    if _crash is None:
        return
    file, path = _crash
    _crash = None
    faulthandler.disable()
    if file is _armed:
        return  # (Its last resort may still write during teardown.)
    try:
        file.close()
        if os.path.getsize(path) == 0:
            os.remove(path)
    except OSError:  # (Gone, or held elsewhere on Windows: the tidy at the next start takes it.)
        pass


def start_for_helper() -> str | None:
    """An I/O helper's crash file in the folder the app named (``HELPER_DIR_ENV``); None without one or
    if it can't be written (a helper says nothing: its stderr is its request's)."""
    folder = os.environ.get(HELPER_DIR_ENV)
    if not folder:
        return None
    try:
        return start(folder, HELPER_CRASH_NAME)
    except OSError:
        return None
