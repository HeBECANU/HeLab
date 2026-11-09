"""The GUI watchdog (``helab/utils/gui_watchdog.py``): its thread ends with its window, also when the window
was deleted without its full close (A47.3: a quit left waiting for saves, as quit tests leave it)."""
from __future__ import annotations

import faulthandler
import logging
import os
import threading
import time
from typing import Any, Callable

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
            watchdog.beats = 1  # (Past its first beat: no event loop runs here, so nothing beats.)
            watchdog.last_beat -= 10  # Its heartbeat stopped.
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


def wait_for(caplog: pytest.LogCaptureFixture, text: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while text not in caplog.text and time.monotonic() < deadline:
        time.sleep(0.05)
    return text in caplog.text


def test_building_the_window_before_the_first_beat_is_no_stall(qtbot: QtBot,
                                                               caplog: pytest.LogCaptureFixture) -> None:
    """The TDC PC, 2026-11-06: a stall dumped at every start, from inside the window's constructor, before
    the event loop ran to beat. Before the first beat only ``STARTUP_STALL_SECONDS`` is a stall."""
    from helab.utils import gui_watchdog
    assert gui_watchdog.STARTUP_STALL_SECONDS >= 30 * gui_watchdog.STALL_SECONDS
    parent = QObject()
    watchdog, thread = started_by(lambda: GUIWatchdog(parent))
    assert isinstance(watchdog, GUIWatchdog)
    try:
        with caplog.at_level(logging.INFO):
            watchdog.last_beat -= 10  # Built for 10 s, not yet beaten.
            assert not wait_for(caplog, "GUI stalled", 1.5)
            watchdog.last_beat = time.monotonic() - 10
            watchdog._beat()  # The first beat: the start's time, not a delay.
            assert "GUI event loop's first beat 10." in caplog.text and "heartbeat delayed" not in caplog.text
            assert watchdog.max_delay == 0.0
    finally:
        watchdog.stop()
        thread.join(timeout=3)
        delete_now(parent)


def test_a_stalls_thread_stacks_go_to_the_log_never_the_console(qtbot: QtBot, caplog: pytest.LogCaptureFixture,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """The TDC PC, 2026-11-09: the stacks went to stderr, the console tee's pipe; its pump stuck, the pipe full,
    ``faulthandler`` waited holding the GIL and the whole app froze. They go through a regular file into the
    log now."""
    dump = faulthandler.dump_traceback
    targets: list[int] = []

    def dump_and_note(file: Any, all_threads: bool = True) -> None:
        targets.append(file.fileno())
        dump(file=file, all_threads=all_threads)

    monkeypatch.setattr(faulthandler, "dump_traceback", dump_and_note)
    parent = QObject()
    watchdog, thread = started_by(lambda: GUIWatchdog(parent))
    assert isinstance(watchdog, GUIWatchdog)
    try:
        with caplog.at_level(logging.ERROR):
            watchdog.beats = 1
            watchdog.last_beat -= 10
            assert wait_for(caplog, "GUI stall's thread stacks:", 5)
        [stacks] = [record.getMessage() for record in caplog.records if "thread stacks:" in record.getMessage()]
        assert "most recent call first" in stacks and "_watch" in stacks, stacks
        assert targets and not set(targets) & {0, 1, 2}  # (A regular file: never the console's descriptors.)
    finally:
        watchdog.stop()
        thread.join(timeout=3)
        delete_now(parent)
