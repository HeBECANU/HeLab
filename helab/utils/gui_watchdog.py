"""Event-loop heartbeat and independent diagnostics for sustained stalls."""
from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import time

from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer


def describe(owner: QObject | None) -> str:
    """A watchdog's window as its stall line names it: its class, and its object name when it has one."""
    if owner is None:
        return "no window"
    name = owner.objectName()
    return f"{type(owner).__name__} {name!r}" if name else type(owner).__name__


class GUIWatchdog(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.last_beat = time.monotonic()
        self.max_delay = 0.0
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
        self.max_delay = max(self.max_delay, delay)
        if delay > 0.5:
            logging.warning("GUI heartbeat delayed %.3fs", delay)
        self.last_beat = now
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
            if now - self.last_beat > 2.0 and now - last_dump > 30.0:
                logging.error("GUI stalled for %.2fs (%s); capturing thread stacks", now - self.last_beat, self.where())
                try:
                    if sys.__stderr__ is not None:
                        faulthandler.dump_traceback(file=sys.__stderr__, all_threads=True)
                except (OSError, RuntimeError, ValueError):
                    logging.exception("Could not dump GUI stall traceback")
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
