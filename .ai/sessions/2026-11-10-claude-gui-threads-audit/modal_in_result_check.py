"""GT audit: does a modal loop opened from an ``IOService.resultReady`` slot stop every helper's events?

Run as ``QT_QPA_PLATFORM=offscreen python .ai/sessions/2026-11-10-claude-gui-threads-audit/modal_in_result_check.py``
(it sets HeLab's folder overrides to a scratch folder before importing ``helab``). A real ``IOService`` gets
events in its ``messages`` queue as a helper's reader thread puts them (two fake requests, no helper started).
The first event's slot opens a nested ``QEventLoop`` for 1 s, as ``box.exec()`` does; a thread keeps putting
heartbeats for the other request meanwhile. It prints how many of those were delivered while the loop ran,
and with the same loop opened from a ``QTimer.singleShot(0)`` instead (the fix), for comparison.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

scratch = tempfile.mkdtemp(prefix="gt-modal-")
for name in ("HELAB_DIR_TEMPS_OVERRIDE", "HELAB_DIR_CACHES_OVERRIDE", "HELAB_APP_DIR_OVERRIDE"):
    os.environ[name] = os.path.join(scratch, name.lower())
os.environ["HELAB_TEST_SETTINGS_FILE"] = os.path.join(scratch, "settings.ini")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from helab.utils.io_service import IORequest, IOService  # noqa: E402


def run(app: QApplication, deferred: bool) -> str:
    service = IOService()
    asker = IORequest("dialog-owner", 0, "/nowhere/a", "list", {}, 60.0)
    other = IORequest("live-owner", 0, "/nowhere/b", "live", {}, 60.0)
    during: list[float] = []
    state = {"in_loop": False, "opened": False}

    def nested() -> None:
        loop = QEventLoop()
        QTimer.singleShot(1000, loop.quit)
        state["in_loop"] = True
        loop.exec()  # (As ``box.exec()`` in a result handler does.)
        state["in_loop"] = False

    def slot(request: IORequest, event: dict) -> None:
        if request is asker and not state["opened"]:
            state["opened"] = True
            if deferred:
                QTimer.singleShot(0, nested)
            else:
                nested()
        elif request is other and state["in_loop"]:
            during.append(time.monotonic())

    service.resultReady.connect(slot)
    stop = threading.Event()

    def reader() -> None:  # (A helper's reader thread: one heartbeat every 20 ms.)
        while not stop.is_set():
            service._put(other, {"kind": "heartbeat"})
            time.sleep(0.02)

    service._put(asker, {"kind": "entries", "entries": []})
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    done = QEventLoop()
    QTimer.singleShot(1600, done.quit)
    done.exec()
    stop.set()
    thread.join()
    service.timer.stop()
    return (f"modal {'from QTimer.singleShot(0)' if deferred else 'inside the resultReady slot'}: "
            f"{len(during)} heartbeats of another request delivered during its 1 s")


def main() -> int:
    app = QApplication(sys.argv)
    print(run(app, deferred=False))
    print(run(app, deferred=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
