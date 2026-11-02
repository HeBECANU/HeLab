"""The GUI watchdog (``helab/utils/gui_watchdog.py``): its thread ends with its window, also when the window
was deleted without its full close (A47.3: a quit left waiting for saves, as quit tests leave it)."""
from __future__ import annotations

import faulthandler
import logging
import os
import threading
import time
from typing import Callable

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from helab.utils.gui_watchdog import GUIWatchdog

NAME = "HeLab-GUI-watchdog"


def started_by(make: Callable[[], object]) -> tuple[object, threading.Thread]:
    """What ``make`` returns, and the watchdog thread it started."""
    before = {thread for thread in threading.enumerate() if thread.name == NAME}
    made = make()
    [thread] = [thread for thread in threading.enumerate() if thread.name == NAME and thread not in before]
    return made, thread


def delete_now(obj: QObject) -> None:
    obj.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_its_thread_ends_when_its_parent_is_deleted_unstopped(qtbot: QtBot) -> None:
    """Deleted without ``stop()`` (the window's close returned early), the thread used to run on, logging
    "GUI stalled" every 30 s for the rest of the process; it stops within a check now."""
    parent = QObject()
    watchdog, thread = started_by(lambda: GUIWatchdog(parent))
    assert isinstance(watchdog, GUIWatchdog) and thread.is_alive()
    delete_now(parent)
    thread.join(timeout=3)
    assert not thread.is_alive() and watchdog.stopped.is_set()


def test_stop_ends_it_too(qtbot: QtBot) -> None:
    parent = QObject()
    watchdog, thread = started_by(lambda: GUIWatchdog(parent))
    assert isinstance(watchdog, GUIWatchdog)
    watchdog.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()
    delete_now(parent)


@pytest.mark.no_auto_data_root
def test_a_window_whose_quit_waits_for_saves_takes_its_watchdog_with_it(qtbot: QtBot,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """A47.3: closing while saves run leaves the quit window to decide (``closeEvent`` returns early, the watchdog
    still running); a test ending there deletes the window at teardown. Its watchdog ends with it."""
    from helab.views.HelabMainWindow import HelabMainWindow
    window, thread = started_by(HelabMainWindow)
    assert isinstance(window, HelabMainWindow)
    monkeypatch.setattr(window, "_wait_for_saves", lambda: True)  # (A save running: the quit window opens.)
    window.show()
    window.close()
    assert window.isVisible() and thread.is_alive()  # The close waits.
    delete_now(window)
    thread.join(timeout=3)
    assert not thread.is_alive()


def test_a_stall_line_names_its_window_and_the_tests(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                    caplog: pytest.LogCaptureFixture) -> None:
    """A~3 of Quick Fixes 9: Windows CI logs "GUI stalled" from a window an earlier test left alive, its stacks
    lost (xdist keeps no worker stderr). The line names the watchdog's window, the test that made it and the
    test running now, so the next sighting names the leak."""
    from helab.utils import gui_watchdog
    # (No stack dump here: only watchdogs call it, and a skipped dump harms none.)
    monkeypatch.setattr(faulthandler, "dump_traceback", lambda **kwargs: None)
    parent = QObject()
    parent.setObjectName("plots_window")
    watchdog, thread = started_by(lambda: GUIWatchdog(parent))
    assert isinstance(watchdog, GUIWatchdog)
    test = os.environ["PYTEST_CURRENT_TEST"]
    try:
        with caplog.at_level(logging.ERROR):
            watchdog.last_beat -= 10  # Its heartbeat stopped (no event loop runs here: nothing beats).
            deadline = time.monotonic() + 5
            while "GUI stalled" not in caplog.text and time.monotonic() < deadline:
                time.sleep(0.05)
        [line] = [record.getMessage() for record in caplog.records if "GUI stalled" in record.getMessage()]
        assert f"(QObject 'plots_window'; made in {test}; now in {test})" in line, line
    finally:
        watchdog.stop()
        thread.join(timeout=3)
        delete_now(parent)
    unnamed = QObject()
    assert gui_watchdog.describe(unnamed) == "QObject" and gui_watchdog.describe(None) == "no window"
    delete_now(unnamed)
