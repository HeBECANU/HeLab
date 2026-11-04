"""The Activity window (Q62.1): opening it, its groups, columns and details, refreshing (nothing while
hidden, bounded while shown), memory-only rendering, and its remembered size."""
from __future__ import annotations

import builtins
import logging
import os
from pathlib import Path
import time
from typing import Any, Iterator

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt

from helab.utils import activity
from helab.utils.activity import Finished
from helab.utils.folder_cache import FolderCache, get_folder_cache
from helab.utils.io_service import IORequest, IOService
from helab.utils.settings_defaults import ACTIVITY_SIZE_SETTING, read_setting
from helab.utils.settings_store import app_settings
from helab.views.ActivityWindow import ActivitySources, ActivityWindow, parse_size
from helab.views.HelabMainWindow import ACTIVITY_HINT, HelabMainWindow


@pytest.fixture(autouse=True)
def fresh_activity() -> Iterator[None]:
    """``HISTORY`` and ``LOG_LINES_HANDLER`` are module-global: reset around each test, and the handler
    taken off the root logger, so neither leaks into another test."""
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    yield
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    activity.remove_log_lines()


def quiet_service(monkeypatch: pytest.MonkeyPatch) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_run", lambda request: None)
    return service


def make_window(qtbot: QtBot, service: IOService, cache: FolderCache | None = None) -> ActivityWindow:
    window = ActivityWindow(ActivitySources(service, cache or get_folder_cache(service), mover=lambda: None))
    qtbot.addWidget(window)
    return window


def texts(window: ActivityWindow) -> list[list[str]]:
    """The Now list as [group heading, then each row's first and State columns]."""
    rows = []
    for index in range(window.now.topLevelItemCount()):
        group = window.now.topLevelItem(index)
        assert group is not None
        rows.append([group.text(0)] + [f"{child.text(0)} | {child.text(3)}" for child in
                                       (group.child(n) for n in range(group.childCount())) if child is not None])
    return rows


def test_it_lists_tasks_by_group_with_their_columns_and_details(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(2)
    service.submit("a", 0, "/data/run_1", "details")
    service.submit("b", 0, "/data/run_2", "raw_fill")
    service.submit("c", 0, "/data/run_3", "scan")
    window = make_window(qtbot, service)
    window.show()
    assert texts(window) == [["Loads and scans (2)", "Folder details | running", "Check folder status | queued (1st)"],
                             ["Cache upkeep (1)", "Cache raw pulses | running"]]
    group = window.now.topLevelItem(0)
    assert group is not None and group.isFirstColumnSpanned() and group.isExpanded()
    row = group.child(0)
    assert row is not None and row.text(2) == "run_1" and row.toolTip(2) == "/data/run_1"
    assert [window.now.headerItem().text(n) for n in range(7)] == [  # type: ignore[union-attr]
        "Task", "Tab", "Folder", "State", "Progress", "Elapsed", "Left"]
    window.now.setCurrentItem(row)
    assert "Folder: /data/run_1" in window.details.toPlainText()
    assert "Lane: background" in window.details.toPlainText()
    assert window.buttons["log"].isEnabled() and not window.buttons["retry"].isEnabled()
    assert window.buttons["cancel"].toolTip().startswith("Not for this task")  # (No tab or plot owns it.)
    assert window.summary.text().startswith(service.activity_counts())
    service.shutdown()


def test_rows_update_in_place_and_keep_the_selection(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.submit("a", 0, "/data/run_1", "details")
    service.submit("c", 0, "/data/run_3", "scan")
    window = make_window(qtbot, service)
    window.show()
    group = window.now.topLevelItem(0)
    assert group is not None
    queued = group.child(1)
    assert queued is not None
    window.now.setCurrentItem(queued)
    service.submit("d", 0, "/data/run_4", "scan")
    window.refresh()
    group = window.now.topLevelItem(0)
    assert group is not None and group.child(1) is queued and window.now.currentItem() is queued
    assert group.childCount() == 3 and group.text(0) == "Loads and scans (3)"
    service.cancel("c")
    window.refresh()
    assert window.now.currentItem() is not queued and group.childCount() == 2
    service.shutdown()


def test_the_history_tab_lists_finished_tasks_newest_first(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    window = make_window(qtbot, service)
    window.show()
    now = time.time()
    activity.record(Finished("t1", "loads", "Load data", "/data/run_1", now - 9, "ok", started=now - 14))
    activity.record(Finished("t2", "loads", "Load data", "/data/run_2", now, "failed", "broken"))
    window.refresh()
    first, second = window.history.topLevelItem(0), window.history.topLevelItem(1)
    assert first is not None and second is not None
    assert (first.text(3), first.text(4)) == ("run_2", "✕ failed: broken")
    assert (second.text(3), second.text(4), second.text(5)) == ("run_1", "done", "0:05")
    logging.warning("Load data failed: /data/run_2 — broken")
    activity.install_log_lines()
    logging.warning("Load data failed: /data/run_2 — broken again")
    window.tabs.setCurrentWidget(window.history)
    window.history.setCurrentItem(first)
    details = window.details.toPlainText()
    assert "Outcome: ✕ failed: broken" in details
    assert "Log:" in details and "WARNING Load data failed: /data/run_2 — broken again" in details
    service.shutdown()


def test_closed_it_does_nothing(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    window = make_window(qtbot, service)
    assert not window.watching and not window._tick.isActive() and window.refreshes == 0
    service.submit("a", 0, "/data/run_1", "details")
    service.activityChanged.emit()
    activity.record(Finished("t1", "loads", "Load data", "/data/run_1", 1.0e9, "ok"))
    qtbot.wait(300)
    assert window.refreshes == 0 and activity.HISTORY.listeners == []
    window.show()
    assert window.watching and window._tick.isActive() and window.refreshes == 1
    assert window.request_refresh in activity.HISTORY.listeners
    window.hide()
    assert not window.watching and not window._tick.isActive() and not window._refresh_timer.isActive()
    assert activity.HISTORY.listeners == []
    count = window.refreshes
    service.activityChanged.emit()
    qtbot.wait(300)
    assert window.refreshes == count
    service.shutdown()


def test_refreshes_are_bounded(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    window = make_window(qtbot, service)
    window.show()
    window._tick.stop()  # (Only the signals count here.)
    count = window.refreshes
    for _ in range(100):
        service.activityChanged.emit()
        service.resultReady.emit(IORequest("x", 0, "/x", "scan", {}, 60.0), {"kind": "started"})
    qtbot.waitUntil(lambda: window.refreshes == count + 1, timeout=2_000)
    qtbot.wait(ActivityWindow.REFRESH_MS * 2)
    assert window.refreshes == count + 1
    service.shutdown()


def test_rendering_reads_memory_only(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A refresh submits no I/O and never touches a source folder."""
    source = tmp_path / "source"
    (source / "run_1").mkdir(parents=True)
    from types import SimpleNamespace
    from test_activity import fake_explorer
    from helab.utils.folder_cache import Dataset
    from helab.views.explorer_convert import FolderConversion
    from helab.views.explorer_live import AutoConvert, LiveSession
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    service.submit("a", 0, str(source / "run_1"), "load")
    service.submit("b", 0, str(source / "run_2"), "scan")
    # (AW-11: a tab's rows too, and the history's.)
    live = str(source / "live")
    session = LiveSession(live, time.time(), set(), Dataset(live, "sig", {}, {"fingerprint": []}, 0), unsettled=1)
    session.convert = AutoConvert(time.time(), error="the conversion failed")
    conversion = FolderConversion(str(source / "raw"), "cache", time.time(), request=True, todo=3, done=1)
    box = SimpleNamespace(windowTitle=lambda: "Convert on a share?", text=lambda: f"{source} is on a share.")
    explorer = fake_explorer("tab", [session], {conversion.path: conversion}, convert_box=box)
    activity.install_log_lines()
    logging.warning("Load data failed: %s — broken", source / "run_3")
    activity.record(Finished("io:x", "loads", "Load data", str(source / "run_3"), time.time(), "failed", "broken",
                             started=time.time() - 3))
    window = ActivityWindow(ActivitySources(service, cache, lambda: [("tab", explorer)], mover=lambda: None))
    qtbot.addWidget(window)
    touched: list[str] = []
    top = os.path.normcase(str(source))

    def guard(real: Any) -> Any:
        def call(path: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                name = os.path.normcase(os.fspath(path))
            except TypeError:
                name = ""
            if name.startswith(top):
                touched.append(f"{getattr(real, '__name__', real)} {name}")
            return real(path, *args, **kwargs)
        return call
    for module, name in ((os, "stat"), (os, "lstat"), (os, "scandir"), (os, "listdir"), (builtins, "open")):
        monkeypatch.setattr(module, name, guard(getattr(module, name)))

    def refused(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("I/O submitted while rendering")
    monkeypatch.setattr(service, "submit", refused)
    monkeypatch.setattr(cache, "submit", refused)
    window.show()
    window.refresh()
    titles = {row.title for row in window.snapshot.tasks}
    assert {"Live", "Auto-convert", "Convert raw files to TXY", "Question: Convert on a share?"} <= titles
    for index in range(window.now.topLevelItemCount()):
        group = window.now.topLevelItem(index)
        assert group is not None and group.child(0) is not None
        window.now.setCurrentItem(group.child(0))
    window.tabs.setCurrentWidget(window.history)
    window.history.setCurrentItem(window.history.topLevelItem(0))
    assert "Log:" in window.details.toPlainText()
    window.refresh()
    assert touched == []
    monkeypatch.undo()
    service.shutdown()


def test_its_size_is_remembered(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    window = make_window(qtbot, service)
    assert (window.width(), window.height()) == (1080, 440)
    window.show()
    window.resize(1300, 600)  # (Wider than its buttons need on every OS: Windows' fonts need about 1,070 px.)
    window.hide()
    assert read_setting(app_settings(), ACTIVITY_SIZE_SETTING) == "1300,600"
    again = make_window(qtbot, service)
    assert (again.width(), again.height()) == (1300, 600)
    service.shutdown()


def test_parse_size() -> None:
    assert parse_size("900,500") == (900, 500)
    assert parse_size("10,10") == (400, 200)
    assert parse_size("junk") == parse_size(None) == parse_size("-1,5") == (1080, 440)


def test_window_activity_and_the_status_bars_click_open_it(qtbot: QtBot) -> None:
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.show()
    try:
        assert activity.LOG_LINES_HANDLER in logging.getLogger().handlers
        activity_window = window.activity_window
        assert not activity_window.isVisible()
        window.action_activity.trigger()
        assert activity_window.isVisible() and activity_window.watching
        assert window.action_activity.objectName() == "window_activity"
        activity_window.hide()
        qtbot.mouseClick(window.status_bar_message_left, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
        assert activity_window.isVisible()
        window.update_status_bar_left()
        assert window.status_bar_message_left.toolTip().endswith(f"\n\n{ACTIVITY_HINT}") or \
            window.status_bar_message_left.toolTip() == ACTIVITY_HINT
    finally:
        window.close()
    assert activity.LOG_LINES_HANDLER not in logging.getLogger().handlers
    assert not window.activity_window.isVisible()


# AW-1: rows that change group or parent while the old one leaves

def sources_with(service: IOService, cache: FolderCache, tabs: list[tuple[str, Any]]) -> ActivitySources:
    return ActivitySources(service, cache, lambda: tabs, mover=lambda: None)


def shown_rows(window: ActivityWindow) -> list[tuple[str, ...]]:
    """Every row as (group heading, its row's title, and its children's titles)."""
    rows = []
    for index in range(window.now.topLevelItemCount()):
        group = window.now.topLevelItem(index)
        assert group is not None
        for n in range(group.childCount()):
            child = group.child(n)
            assert child is not None
            rows.append((group.text(0), child.text(0),
                         *[grand.text(0) for grand in (child.child(m) for m in range(child.childCount()))
                           if grand is not None]))
    return rows


def still_works(window: ActivityWindow) -> None:
    assert not window.now.signalsBlocked()
    group = window.now.topLevelItem(0)
    assert group is not None and group.child(0) is not None
    window.now.setCurrentItem(group.child(0))
    assert window.details.toPlainText()  # (Selection reaches the details pane: signals flow.)


def test_a_load_that_becomes_a_cache_write_moves_to_saves(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    window = make_window(qtbot, service, cache)
    window.show()
    assert cache.submit("tab", 0, "/data/run_1", "load", {})
    window.refresh()
    assert [row[:2] for row in shown_rows(window)] == [("Loads and scans (1)", "Load data")]
    service.active[0].completed = True  # (It delivered its data and goes on writing the disk cache.)
    window.refresh()
    window.refresh()
    assert [row[:2] for row in shown_rows(window)] == [("Saves (1)", "Save data cache")]
    still_works(window)
    service.shutdown()


def test_a_conversion_that_finishes_while_its_pass_is_listed(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_activity import fake_explorer
    from helab.views.explorer_convert import FolderConversion
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    conversion = FolderConversion(FolderCache.key("/raw"), "cache", time.time(), request=True)
    explorer = fake_explorer("tab", conversions={conversion.path: conversion})
    window = ActivityWindow(sources_with(service, cache, [("raw", explorer)]))
    qtbot.addWidget(window)
    window.show()
    assert cache.submit("tab:convert", 0, "/raw", "convert", {})
    window.refresh()
    assert shown_rows(window) == [("Conversions (2)", "Convert raw files to TXY", "Convert raw files to TXY")]
    conversion.request, conversion.finished = False, True  # (Its row leaves; its pass is still exiting.)
    window.refresh()
    window.refresh()
    assert shown_rows(window) == [("Conversions (1)", "Convert raw files to TXY")]
    still_works(window)
    service.shutdown()


def test_a_live_session_that_ends_before_its_save(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_activity import fake_explorer
    from helab.utils.folder_cache import Dataset
    from helab.views.explorer_live import LiveSession
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    path = FolderCache.key("/live")
    session = LiveSession(path, time.time(), set(), Dataset(path, "sig", {}, {"fingerprint": []}, 0), on=False)
    sessions = [session]
    explorer = fake_explorer("tab", sessions)
    explorer.live_control.sessions = lambda: list(sessions)
    window = ActivityWindow(sources_with(service, cache, [("live", explorer)]))
    qtbot.addWidget(window)
    window.show()
    assert cache.save("tab:live-save", path, {"save_memory": True})
    window.refresh()
    assert shown_rows(window) == [("Live (2)", "Live", "Load data")]
    sessions.clear()  # (Live's session ends; its save still runs.)
    window.refresh()
    window.refresh()
    assert shown_rows(window) == [("Saves (1)", "Load data")]
    still_works(window)
    service.shutdown()


def test_a_saved_size_larger_than_the_screen_is_fitted_to_it(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """AW-9: a size saved on a larger monitor opens no larger than this screen."""
    service = quiet_service(monkeypatch)
    app_settings().setValue(ACTIVITY_SIZE_SETTING, "20000,15000")
    window = make_window(qtbot, service)
    assert (window.width(), window.height()) == (20000, 15000)
    window.show()
    screen = window.screen()
    assert screen is not None
    room = screen.availableGeometry()
    # (Never below the window's own least size: its button row needs about 1,070 px with Windows' fonts, more
    # than the offscreen screen's 800.)
    least = window.minimumSizeHint()
    assert window.width() <= max(room.width(), least.width(), 400)
    assert window.height() <= max(room.height(), least.height(), 200)
    assert window.width() < 20000 and window.height() < 15000
    service.shutdown()


def test_history_rows_are_added_on_top_and_keep_their_selection(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """AW-10: entries have unique keys though their ids repeat (Live sessions of one folder); a new entry
    goes on top without rebuilding the others, so the chosen row stays chosen; the oldest drops off."""
    service = quiet_service(monkeypatch)
    window = make_window(qtbot, service)
    window.show()
    now = time.time()
    activity.record(Finished("live:tab:live:/live", "live", "Live", "/live", now - 9, "failed", "first"))
    activity.record(Finished("live:tab:live:/live", "live", "Live", "/live", now - 5, "ok"))
    window.refresh()
    window.tabs.setCurrentWidget(window.history)
    older = window.history.topLevelItem(1)
    assert older is not None
    window.history.setCurrentItem(older)
    chosen = window.selected_entry()
    assert chosen is not None and chosen.message == "first"
    keys = [entry.key for entry in activity.HISTORY.entries()]
    assert len(set(keys)) == 2
    activity.record(Finished("live:tab:live:/live", "live", "Live", "/live", now, "failed", "third"))
    window.refresh()
    assert window.history.topLevelItemCount() == 3 and window.history.topLevelItem(2) is older
    assert window.history.currentItem() is older and window.selected_entry() == chosen
    for n in range(activity.HISTORY_SIZE):
        activity.record(Finished(f"t{n}", "loads", "Load data", f"/data/{n}", now, "ok"))
    window.refresh()
    assert window.history.topLevelItemCount() == activity.HISTORY_SIZE
    first = window.history.topLevelItem(0)
    assert first is not None and first.text(3) == str(activity.HISTORY_SIZE - 1)
    service.shutdown()
