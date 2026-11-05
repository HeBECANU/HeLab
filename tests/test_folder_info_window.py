"""The Folder info window (``helab/views/FolderInfoWindow.py``; Q64.1–Q64.10) from fake reads: it shows the model, its
buttons call the tab's existing actions, it reads on open, on Refresh, after an action (at the folder's next change)
and, while Live watches the folder, after each Live save, with one read in flight; a retargeted window drops the old
answer; a failed read says so; long lists open beside it, widening it; it is never taller than its screen and keeps
its size; opening and rendering touch no source folder; its per-folder Clears ask first, clear that folder only and
say whether they worked. And the ways in: right-click › Folder info…, Folder details' link, File › Folder info…
(⌘I)."""
from __future__ import annotations

import os
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from helab.utils.folder_cache import FolderCache
from helab.utils.io_service import IORequest, IOService
from helab.utils.settings_defaults import FOLDER_INFO_SIZE_SETTING
from helab.utils.settings_store import app_settings
from helab.views.ElidedLabel import ElidedLabel
from helab.views.FolderInfoWindow import FolderInfoSources, FolderInfoWindow

NOW = time.time()  # (Realistic times: Windows' local time refuses some small ones.)


class FakeExplorer:
    """A tab: its existing actions recorded, Live watching ``live_path`` when set."""

    def __init__(self) -> None:
        self.closed = False
        self.calls: list[tuple[Any, ...]] = []
        self.live_path = ""
        self.model = SimpleNamespace(refresh_pending=lambda path: False)
        self.converter = SimpleNamespace(convert_unavailable=lambda path: "",
                                         ask_convert=lambda path: self.calls.append(("convert", path)))
        explorer = self
        self.live_control = SimpleNamespace(
            sessions=lambda: [], set_write_beside=lambda path, on: explorer.calls.append(("write_beside", path, on)))

    @property
    def live(self) -> Any:
        return SimpleNamespace(path=self.live_path) if self.live_path else None

    def place_root_state(self, path: str) -> tuple[bool, str]:
        return True, "Place one here"

    def place_root(self, path: str) -> None:
        self.calls.append(("place_root", path))

    def clear_data_cache(self, path: str) -> None:
        self.calls.append(("clear_data", path))

    def set_folder_flag(self, path: str, key: str, on: bool) -> None:
        self.calls.append(("flag", path, key, on))

    def choose_folder_txy(self, path: str) -> None:
        self.calls.append(("txy", path))

    def choose_folder_policy(self, path: str) -> None:
        self.calls.append(("policy", path))

    def show_folder_constants(self, path: str) -> None:
        self.calls.append(("constants", path))

    def refresh_folder(self, path: str) -> None:
        self.calls.append(("refresh", path))


@pytest.fixture
def setup(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    cache = FolderCache(service)
    explorer = FakeExplorer()
    explorer.live_control.live = None
    settings_opened: list[tuple[str, str]] = []

    def tabs() -> list[tuple[str, Any]]:
        explorer.live_control.live = explorer.live
        return [("Tab 1", explorer)]
    fake: Any = explorer
    sources = FolderInfoSources(cache, tabs, lambda: fake, lambda path: ("Correlations (1)",),
                                lambda: {"tests.corr": "Correlations"}, lambda tab, root: settings_opened.append((tab, root)))
    window = FolderInfoWindow(sources)
    qtbot.addWidget(window)
    path = str(tmp_path / "data" / "x")  # (Never made: nothing may read it.)
    cache.data_roots[str(tmp_path / "data")] = ("uuid-1", "data")
    yield SimpleNamespace(service=service, cache=cache, explorer=explorer, window=window, path=path,
                          settings=settings_opened)
    window.close()
    service.shutdown()


def reads(service: IOService) -> list[IORequest]:
    return [request for request in service.pending if request.operation == "cache_admin"
            and request.payload["action"] == "folder_info"]


def answer(path: str, **changes: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "folder_info", "path": path, "key": "root://uuid-1/x", "root_state": "rooted", "layout": 4,
        "read_at": time.time(), "store": "", "parts": {name: {"status": "found", "error": ""} for name in (
            "raw", "layers", "views", "seed", "results", "prefs", "convert_prefs", "choices", "constants", "history",
            "summary", "listing", "converted")},
        "raw": {"shots": 3, "bytes": 3000, "first": 1, "last": 3, "saved_first": NOW - 600, "saved_last": NOW - 60,
                "last_used": NOW - 60, "seen_at": NOW - 60, "only_copy": 0, "only_copy_bytes": 0, "gone_first": None,
                "gone_last": None},
        "layers": [], "layers_more": 0, "views": [], "views_more": 0, "seed_bytes": 0,
        "results": {"count": 0, "bytes": 0, "rows": [], "more": 0}, "prefs": None, "convert_prefs": None,
        "choices": None, "constants": None, "history": None, "summary": None, "listing_at": None, "converted": []}
    event.update(changes)
    return event


def finish(service: IOService, request: IORequest, *events: dict[str, Any], error: str = "") -> None:
    for event in events:
        service.resultReady.emit(request, event)
    service.resultReady.emit(request, {"kind": "error", "message": error} if error else {"kind": "done"})
    service.pending.remove(request)


def labels(window: QWidget) -> list[str]:
    return [label.text() for label in window.findChildren(ElidedLabel) if not label.isHidden()]


def button(window: QWidget, ident: str) -> Any:
    found = window.findChild(QWidget, ident)
    assert found is not None, ident
    return found


def test_it_opens_reads_once_and_shows_the_answer(setup: Any, qtbot: QtBot) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    assert s.window.windowTitle() == f"Folder info — {s.path}" and s.window.isVisible()
    [request] = reads(s.service)
    assert request.payload["params"]["path"] == s.path and request.priority
    assert any(text.endswith("reading…") for text in labels(s.window)), labels(s.window)
    finish(s.service, request, answer(s.path))
    shown = labels(s.window)
    assert any(text.startswith("Raw pulses: 3 shots (d1–d3)") for text in shown)
    assert any(text.startswith("As of ") and "reading" not in text for text in shown), shown
    assert "Plots: Correlations (1)" in shown


def test_one_read_in_flight_and_a_retarget_drops_the_old_answer(setup: Any) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    button(s.window, "folder_info_refresh").click()
    button(s.window, "folder_info_refresh").click()
    [first] = reads(s.service)
    other = s.path + "-other"
    s.window.show_folder(other, s.explorer)  # (Retargeted while the first read runs.)
    assert len(reads(s.service)) == 1
    finish(s.service, first, answer(s.path, raw={**answer(s.path)["raw"], "shots": 99}))
    [second] = reads(s.service)
    assert second.payload["params"]["path"] == other and not any("99 shots" in text for text in labels(s.window))
    finish(s.service, second, answer(other))
    assert any(text.startswith("Raw pulses: 3 shots") for text in labels(s.window)) and not reads(s.service)


def test_a_failed_read_says_so_and_never_nothing_saved(setup: Any) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    [request] = reads(s.service)
    finish(s.service, request, error="Disk cache could not be read: locked")
    shown = labels(s.window)
    assert any(text == "Couldn't read the disk cache: Disk cache could not be read: locked" for text in shown)
    assert "Not read: see above" in shown and not any("Nothing cached" in text for text in shown)


def test_each_button_calls_the_tabs_existing_action(setup: Any) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    for ident in ("store_clear_data", "flags_flag_no_cache", "flags_flag_write_beside", "choices_txy_choose",
                  "choices_policy_choose", "constants_constants_edit", "scan_scan_refresh", "converted_convert"):
        button(s.window, f"folder_info_{ident}").click()
    path = s.path
    assert s.explorer.calls == [("clear_data", path), ("flag", path, "no_cache", True), ("write_beside", path, True),
                                ("txy", path), ("policy", path), ("constants", path), ("refresh", path),
                                ("convert", path)]
    button(s.window, "folder_info_store_settings_cache").click()
    button(s.window, "folder_info_results_settings_roots").click()
    assert s.settings == [("Cache", ""), ("Data roots", "uuid-1")]  # (Data roots with the folder's root selected.)
    # The window changes nothing itself: a toggle shows the folder's flag as memory has it.
    assert not button(s.window, "folder_info_flags_flag_no_cache").isChecked()


def test_it_reads_after_an_action_at_the_folders_next_change_only(setup: Any, qtbot: QtBot) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.cache.folderPrefsChanged.emit(s.path)  # (Not after an action here: no read.)
    qtbot.wait(400)
    assert not reads(s.service)
    button(s.window, "folder_info_flags_flag_no_cache").click()
    s.cache.folderPrefsChanged.emit(s.path + "-elsewhere")
    s.cache.folderPrefsChanged.emit(s.path)
    qtbot.waitUntil(lambda: len(reads(s.service)) == 1)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.cache.folderPrefsChanged.emit(s.path)  # (Disarmed by the read it caused.)
    qtbot.wait(400)
    assert not reads(s.service)


def test_while_live_watches_it_reads_after_each_save_and_follows_checks(setup: Any, qtbot: QtBot) -> None:
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.cache.saveEnded.emit(s.path, "rejected")  # (A save that saved nothing: no read.)
    s.cache.saveEnded.emit(s.path + "-other", "saved")  # (Another folder's: no read.)
    assert not reads(s.service)
    s.explorer.live_path = s.path
    s.window.live_changed()  # (Live on: the header and This session say so.)
    qtbot.waitUntil(lambda: any("Live: on in Tab 1" in text for text in labels(s.window)))
    s.explorer.calls.clear()
    s.cache.datasetChanged.emit(s.path)  # (A Live check that brought shots: memory only.)
    qtbot.wait(600)
    assert not reads(s.service) and any("Live: refreshes by itself" in text for text in labels(s.window))
    s.cache.saveEnded.emit(s.path, "saved")
    s.cache.saveEnded.emit(s.path, "superseded")  # (A second while the first reads: queued, once.)
    assert len(reads(s.service)) == 1
    finish(s.service, reads(s.service)[0], answer(s.path))
    assert len(reads(s.service)) == 1


def results(count: int) -> dict[str, Any]:
    rows = [{"result_id": f"r{index}", "analysis_id": "tests.corr", "version": "1", "file_name": "c.py",
             "action": "Plot", "settings": f"bins={index}", "settings_full": f"bins={index}", "bytes": 10,
             "computed_at": NOW - 600, "saved_at": NOW - 600, "last_used": NOW - 60, "damaged": False}
            for index in range(count)]
    return {"count": count, "bytes": 10 * count, "rows": rows, "more": 0}


def test_long_lists_open_to_the_side_and_it_is_never_taller_than_its_screen(setup: Any, qtbot: QtBot) -> None:
    s = setup
    screen = QApplication.primaryScreen()
    assert screen is not None
    room = screen.availableGeometry()
    app_settings().setValue(FOLDER_INFO_SIZE_SETTING, f"{room.width() * 3},{room.height() * 3}")
    window = FolderInfoWindow(s.window.sources)
    qtbot.addWidget(window)
    window.show_folder(s.path, s.explorer)
    assert window.height() <= room.height() and window.width() <= room.width()
    window.resize(max(420, room.width() // 3), min(400, room.height()))
    finish(s.service, reads(s.service)[0], answer(s.path, results=results(40)))
    more = button(window, "folder_info_results_more")
    assert more.text() == "All 40 saved results ›"
    before = window.width()
    more.click()
    qtbot.waitUntil(lambda: window.pane.isVisible())
    assert window.width() > before and window.tree.topLevelItemCount() == 40
    assert window.height() <= room.height()
    button(window, "folder_info_detail_close").click()
    assert not window.pane.isVisible() and abs(window.width() - before) <= 2
    window.close()
    saved = str(app_settings().value(FOLDER_INFO_SIZE_SETTING))
    assert saved == f"{window.width()},{window.height()}"


def test_opening_and_rendering_touch_no_source_folder(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    s = setup
    data = os.path.normcase(os.path.dirname(s.path))
    touched: list[str] = []
    for name in ("stat", "lstat", "scandir", "listdir", "open"):
        original = getattr(os, name)

        def traced(*args: Any, _original: Any = original, _name: str = name, **kwargs: Any) -> Any:
            if args and isinstance(args[0], (str, os.PathLike)) and os.path.normcase(os.fspath(args[0])).startswith(data):
                touched.append(f"{_name} {args[0]}")
            return _original(*args, **kwargs)
        monkeypatch.setattr(os, name, traced)
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path, results=results(10)))
    s.window.open_detail("results")
    s.window.rebuild()
    assert touched == [] and {request.operation for request in s.service.pending} <= {"cache_admin"}


def test_ram_only_offers_place_root_through_the_tab(setup: Any) -> None:
    s = setup
    s.cache.data_roots.clear()
    s.cache.unrooted[s.path] = "no .helab-root found here or above"
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path, root_state="no_root", key="", parts={
        name: {"status": "skipped", "error": ""} for name in answer(s.path)["parts"]}))
    assert "RAM only: no .helab-root here or above" in labels(s.window)
    button(s.window, "folder_info_place_root").click()
    assert s.explorer.calls == [("place_root", s.path)]
    assert not button(s.window, "folder_info_flags_flag_no_cache").isEnabled()


# The ways in (Q64.1, Q64.2)

def test_folder_details_link_ends_the_disk_cache_row(qtbot: QtBot) -> None:
    from helab.views.FolderDetailsPanel import FOLDER_INFO_LINK, FolderDetailsPanel
    panel = FolderDetailsPanel()
    qtbot.addWidget(panel)
    panel.show()
    link = panel.findChild(QLabel, "details_folder_info")
    assert link is not None and link.text() == FOLDER_INFO_LINK and link.isHidden()
    panel.set_row("cache", "⚓ data · /data")
    assert not link.isHidden()
    with qtbot.waitSignal(panel.folderInfoRequested):
        qtbot.mouseClick(link, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    panel.set_row("cache", "")
    assert link.isHidden()


def test_the_file_menu_and_the_right_click_open_it(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from PyQt6.QtGui import QKeySequence
    from PyQt6.QtWidgets import QMenu
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.show()
    try:
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        action = window.action_folder_info
        assert action.shortcut() == QKeySequence("Ctrl+I")
        menu = next(item.menu() for item in window.menu_bar.actions() if item.text() == "File")
        assert isinstance(menu, QMenu) and action in menu.actions()
        menu.aboutToShow.emit()
        assert action.isEnabled()
        opened: list[tuple[str, Any]] = []
        monkeypatch.setattr(window, "show_folder_info", lambda path, tab=None: opened.append((path, tab)))
        action.trigger()
        assert opened == [(explorer.selected_path_globally or explorer.model_root_path, explorer)]
        monkeypatch.setattr(window, "_place_root_target", lambda: None)
        window.update_folder_info_action()
        assert not action.isEnabled()
    finally:
        window.close()


def test_settings_data_roots_selects_the_folders_root(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path: Path) -> None:
    """Data roots selects the root Folder info names (a mounted location first), now or once its list is read."""
    from helab.views.DataRootsTab import DataRootsTab
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    cache = FolderCache(service)
    monkeypatch.setattr(cache, "cache_admin", lambda action, **params: "job-1")
    monkeypatch.setattr("helab.utils.folder_cache.store_options", lambda: {"directory": str(tmp_path)})
    try:
        page = DataRootsTab(cache)
        qtbot.addWidget(page)
        assert not page.select_root("uuid-b")  # (Not read yet: selected when it is.)
        row = {"kind": "vol", "label": "b", "first_seen": 1.0e9, "last_seen": 1.6e9, "decision": "confirmed"}
        rows = [{**row, "location": "vol://a/x", "uuid": "uuid-a", "label": "a", "path": "/a"},
                {**row, "location": "vol://b/old", "uuid": "uuid-b", "path": ""},
                {**row, "location": "vol://b/now", "uuid": "uuid-b", "path": "/b"}]
        cache.cacheAdminResult.emit("inventory", {"kind": "inventory", "inventory": {"roots": rows}})
        assert (page.selected() or {}).get("location") == "vol://b/now"
        assert page.select_root("uuid-a") and (page.selected() or {}).get("location") == "vol://a/x"
        assert not page.select_root("uuid-none") and (page.selected() or {}).get("location") == "vol://a/x"
    finally:
        service.shutdown()


def clears(service: IOService) -> list[IORequest]:
    return [request for request in service.pending if request.operation == "cache_admin"
            and request.payload["action"] in ("clear_raw", "clear_results", "clear_converted_txy")]


def test_each_clear_asks_first_then_clears_this_folder_and_says_so(setup: Any) -> None:
    """Q~6, Q64.6 b (Tony, 2026-11-05): Clear raw pulses…, Clear this folder's saved results… and Clear this folder's
    converted TXY…, each asked first from the current read; a no removes nothing; a yes clears this folder only, and the
    header says it worked (or why not), the folder read again."""
    s = setup
    asked: list[Any] = []
    answers = [False, True, True, True]

    def ask(question: Any) -> bool:
        asked.append(question)
        return answers.pop(0)
    s.window.ask_clear = ask
    s.window.show_folder(s.path, s.explorer)
    converted = [{"base": "cache", "folder": "/c/x", "status": "found", "error": "", "last_used": NOW,
                  "tags": [{"tag": "m19v1", "profile": "matlab-2019", "version": 1, "output": "cache", "shots": 2,
                            "bytes": 2000, "newest": NOW, "only_copy": 0, "only_copy_bytes": 0}]}]
    finish(s.service, reads(s.service)[0], answer(s.path, results={"count": 2, "bytes": 500, "rows": [], "more": 0},
                                                  converted=converted))
    button(s.window, "folder_info_store_clear_raw").click()  # (Answered no.)
    assert asked[0].title == "Clear raw pulses of this folder" and not clears(s.service)
    button(s.window, "folder_info_store_clear_raw").click()
    [raw] = clears(s.service)
    assert (raw.payload["action"], raw.payload["params"]["paths"]) == ("clear_raw", [s.path]) and raw.priority
    assert not button(s.window, "folder_info_store_clear_raw").isEnabled()  # (While it runs.)
    finish(s.service, raw, {"kind": "removed", "kinds": ["raw"], "paths": [s.path], "raw": 3, "bytes": 3000})
    assert any(text.startswith("Removed this folder's cached raw pulses · ") for text in labels(s.window))
    [again] = reads(s.service)  # (What is left, read again.)
    finish(s.service, again, answer(s.path, raw={**answer(s.path)["raw"], "shots": 0, "bytes": 0},
                                    results={"count": 2, "bytes": 500, "rows": [], "more": 0}))
    assert not button(s.window, "folder_info_store_clear_raw").isEnabled()
    button(s.window, "folder_info_results_clear_results").click()
    [results] = clears(s.service)
    assert (results.payload["action"], results.payload["params"]["paths"]) == ("clear_results", [s.path])
    finish(s.service, results, error="This disk cache was written by a newer HeLab and is read-only")
    assert ("Couldn't remove this folder's saved results: This disk cache was written by a newer HeLab and is "
            "read-only") in labels(s.window)
    finish(s.service, reads(s.service)[0], answer(s.path, converted=converted))
    button(s.window, "folder_info_converted_clear_converted").click()
    [txy] = clears(s.service)
    assert (txy.payload["action"], txy.payload["params"]["path"]) == ("clear_converted_txy", s.path)
    assert [question.accept for question in asked] == ["Remove cached raw pulses", "Remove cached raw pulses",
                                                       "Remove saved results", "Remove converted TXY"]
    s.window.show_folder(s.path + "-other", s.explorer)  # (Retargeted: that Clear's end says nothing here.)
    finish(s.service, txy)
    assert not any(text.startswith(("Removed", "Couldn't remove")) for text in labels(s.window))


def test_it_reads_after_lives_save_on_stop(setup: Any, qtbot: QtBot) -> None:
    """FI-1: ``stop_live`` turns Live off before its last save, so the read follows the save of the window's folder,
    not Live being on."""
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.explorer.live_path = s.path
    s.window.live_changed()
    s.explorer.live_path = ""  # (Live off, as ``stop_live`` sets it before its save.)
    s.window.live_changed()
    assert not reads(s.service)
    s.cache.saveEnded.emit(s.path, "saved")  # (The stop's save.)
    assert len(reads(s.service)) == 1


def test_minimised_it_keeps_following_and_reads_once_restored(setup: Any, qtbot: QtBot) -> None:
    """FI-5: a minimised window stays hooked up; a save meanwhile is read once it is restored (one read)."""
    from PyQt6.QtGui import QHideEvent, QShowEvent
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.window.setWindowState(Qt.WindowState.WindowMinimized)
    s.window.hideEvent(QHideEvent())  # (What minimising sends; the offscreen platform sends none.)
    s.cache.saveEnded.emit(s.path, "saved")
    s.cache.saveEnded.emit(s.path, "saved")
    assert not reads(s.service) and s.window._connected
    s.window.setWindowState(Qt.WindowState.WindowNoState)
    s.window.showEvent(QShowEvent())
    assert len(reads(s.service)) == 1
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.window.hideEvent(QHideEvent())  # (Closed, not minimised: unhooked, nothing waits.)
    assert not s.window._connected and not s.window._missed


def test_every_show_and_retarget_fits_its_screen(setup: Any, qtbot: QtBot) -> None:
    """FI-8: not only the first show: reopened after a larger size (another monitor), it fits the screen again."""
    s = setup
    screen = QApplication.primaryScreen()
    assert screen is not None
    room = screen.availableGeometry()
    s.window.show_folder(s.path, s.explorer)
    s.window.hide()
    s.window.resize(room.width() * 2, room.height() * 2)
    s.window.show_folder(s.path + "-other", s.explorer)
    assert s.window.width() <= room.width() and s.window.height() <= room.height()


def test_the_detail_pane_never_moves_the_window_down(setup: Any, qtbot: QtBot) -> None:
    """FI-3: open and close the pane a few times; the window's frame stays where it was. (The offscreen platform has
    no frames, so the title bar's creep itself shows only on a screen: M~1.)"""
    s = setup
    s.window.show_folder(s.path, s.explorer)
    s.window.resize(480, 400)
    finish(s.service, reads(s.service)[0], answer(s.path, results=results(40)))
    top = s.window.frameGeometry().topLeft()
    for _ in range(3):
        button(s.window, "folder_info_results_more").click()
        qtbot.waitUntil(lambda: s.window.pane.isVisible())
        button(s.window, "folder_info_detail_close").click()
    assert s.window.frameGeometry().y() == top.y()


class FakeScreen:
    """A screen of ``height`` px available (``fit_screen`` reads only that)."""

    def __init__(self, height: int) -> None:
        self.height = height

    def availableGeometry(self) -> Any:
        from PyQt6.QtCore import QRect
        return QRect(0, 0, 1600, self.height)


def test_once_shown_it_fits_its_own_screen_not_the_main_windows(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """FI-9: the main window on the laptop (700 px), Folder info moved to a taller monitor (1400 px) and made 1200 px
    tall: a reopen or a restore keeps its height there. Its first show fits the main window's screen."""
    s = setup
    laptop, monitor = FakeScreen(700), FakeScreen(1400)
    parent = SimpleNamespace(screen=lambda: laptop)
    monkeypatch.setattr(s.window, "parentWidget", lambda: parent)
    monkeypatch.setattr(s.window, "screen", lambda: laptop)
    s.window.resize(600, 1000)
    s.window.show_folder(s.path, s.explorer)  # (First show: over the main window, on the laptop.)
    assert s.window.height() <= 700
    monkeypatch.setattr(s.window, "screen", lambda: monitor)  # (Moved to the monitor.)
    s.window.resize(600, 1200)
    s.window.hide()
    s.window.show_folder(s.path, s.explorer)
    assert s.window.height() == 1200


def test_a_spontaneous_hide_that_isnt_a_minimise_is_a_close(setup: Any) -> None:
    """FI-10: a title-bar close the platform reports as spontaneous unhooks the window and saves its size; only a
    minimise keeps it hooked up."""
    from PyQt6.QtGui import QHideEvent

    class Spontaneous(QHideEvent):
        def spontaneous(self) -> bool:
            return True
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.window.resize(640, 500)
    app_settings().setValue(FOLDER_INFO_SIZE_SETTING, "1,1")
    s.window.hideEvent(Spontaneous())
    assert not s.window._connected and not s.window._away
    assert str(app_settings().value(FOLDER_INFO_SIZE_SETTING)) == f"{s.window.width()},{s.window.height()}"


def test_a_minimise_reported_after_its_hide_still_keeps_it_hooked_up(setup: Any) -> None:
    """FI-10's other order: a platform that sends the spontaneous hide before the state says minimised; the state
    change hooks it up again, as minimised, and the restore reads what fell due."""
    from PyQt6.QtGui import QHideEvent, QShowEvent

    class Spontaneous(QHideEvent):
        def spontaneous(self) -> bool:
            return True
    s = setup
    s.window.show_folder(s.path, s.explorer)
    finish(s.service, reads(s.service)[0], answer(s.path))
    s.window.hideEvent(Spontaneous())  # (Not minimised yet: a close, so far.)
    s.window.setWindowState(Qt.WindowState.WindowMinimized)
    assert s.window._connected and s.window._away
    s.cache.saveEnded.emit(s.path, "saved")
    assert not reads(s.service)
    s.window.setWindowState(Qt.WindowState.WindowNoState)
    s.window.showEvent(QShowEvent())
    assert len(reads(s.service)) == 1
