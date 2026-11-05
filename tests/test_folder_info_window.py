"""The Folder info window (``helab/views/FolderInfoWindow.py``; Q64.1–Q64.10) from fake reads: it shows the model, its
buttons call the tab's existing actions, it reads on open, on Refresh, after an action (at the folder's next change)
and, while Live watches the folder, after each Live save, with one read in flight; a retargeted window drops the old
answer; a failed read says so; long lists open beside it, widening it; it is never taller than its screen and keeps
its size; opening and rendering touch no source folder. And the ways in: right-click › Folder info…, Folder details'
link, File › Folder info… (⌘I)."""
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
    s.cache.saveEnded.emit(s.path, "saved")  # (Live off: a save alone doesn't read.)
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
