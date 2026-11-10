"""Event-loop heartbeat and independent diagnostics for sustained stalls."""
from __future__ import annotations

import faulthandler
import logging
import os
import tempfile
import threading
import time

from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer

from helab.utils import app_log


def describe(owner: QObject | None) -> str:
    """A watchdog's window as its stall line names it: its class, and its object name when it has one."""
    if owner is None:
        return "no window"
    name = owner.objectName()
    return f"{type(owner).__name__} {name!r}" if name else type(owner).__name__


STALL_SECONDS = 2.0  # Without a beat, once the event loop has beaten once.
# Before the first beat: the window is still being built and the event loop not yet running, which takes over
# 2 s on a slow PC (the lab's TDC PC: about 15 s), so only a far longer wait is a stall.
STARTUP_STALL_SECONDS = 60.0
LOG_SECONDS = 1.0  # At most this long for each of its log lines (``app_log.log_within``).


def thread_stacks() -> str:
    """Every thread's Python stack, as ``faulthandler`` writes it. It writes holding the GIL, so it writes to
    a regular file, which never blocks: into a pipe the console tee no longer drains (its console blocked),
    the write would never return and the whole process would freeze with it (the TDC PC, 2026-11-09)."""
    with tempfile.TemporaryFile() as file:
        faulthandler.dump_traceback(file=file, all_threads=True)
        file.seek(0)
        return file.read().decode("utf-8", "replace")


class GUIWatchdog(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.last_beat = time.monotonic()
        self.max_delay = 0.0
        self.beats = 0  # (Set on the GUI thread, read on the watching one.)
        self.stopped = threading.Event()
        # For the stall line (A~3 of Quick Fixes 9: Windows CI's stalls came from a window an earlier test left
        # alive): its window, kept current on the GUI thread so the watching thread never calls Qt, and, under
        # pytest, the test that made it.
        self.owner = describe(parent)
        self.made_in = os.environ.get("PYTEST_CURRENT_TEST", "")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._beat)
        self.timer.start(100)
        threading.Thread(target=self._watch, daemon=True, name="HeLab-GUI-watchdog").start()

    def _beat(self) -> None:
        now = time.monotonic()
        delay = now - self.last_beat
        if self.beats == 0:
            logging.info("GUI event loop's first beat %.3fs after its watchdog started", delay)
        else:
            self.max_delay = max(self.max_delay, delay)
            if delay > 0.5:
                logging.warning("GUI heartbeat delayed %.3fs", delay)
        self.last_beat = now
        self.beats += 1
        self.owner = describe(self.parent())

    def _watch(self) -> None:
        last_dump = 0.0
        while not self.stopped.wait(0.5):
            if sip.isdeleted(self):
                # Deleted with its window, unstopped (a close left waiting for saves, then the window deleted:
                # quit tests, A47.3): its heartbeat is gone too, so it would only log stalls from now on.
                self.stopped.set()
                return
            now = time.monotonic()
            limit = STALL_SECONDS if self.beats else STARTUP_STALL_SECONDS
            if now - self.last_beat > limit and now - last_dump > 30.0:
                # (Never held by a console that takes nothing: this thread watches on, GT-3.)
                app_log.log_within(LOG_SECONDS, logging.ERROR, "GUI stalled for %.2fs (%s); capturing thread stacks",
                                   now - self.last_beat, self.where())
                try:
                    stacks = thread_stacks().rstrip()
                except (OSError, RuntimeError, ValueError) as exc:
                    app_log.log_within(LOG_SECONDS, logging.ERROR, "Could not dump GUI stall traceback: %r", exc)
                else:
                    app_log.log_within(LOG_SECONDS, logging.ERROR, "GUI stall's thread stacks:\n%s", stacks)
                last_dump = now

    def where(self) -> str:
        """Whose heartbeat stopped: its window, and under pytest the test that made it and the one running now
        (``PYTEST_CURRENT_TEST``, read as the stall is said)."""
        parts = [self.owner]
        if self.made_in:
            parts.append(f"made in {self.made_in}")
        running = os.environ.get("PYTEST_CURRENT_TEST", "")
        if running or self.made_in:
            parts.append(f"now in {running or 'no test'}")
        return "; ".join(parts)

    def stop(self) -> None:
        self.timer.stop()
        self.stopped.set()
