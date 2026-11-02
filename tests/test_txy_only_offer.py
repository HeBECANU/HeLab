"""Caching v2 stage 4, S4~1 (Tony, 2026-11-02): setting a folder, or Settings' policy, to TXY only removes
nothing by itself; HeLab offers to remove its cached copy of the raw pulses, with their size, saying the d files
aren't touched, and removes only on a yes (Settings' only for the folders that follow it). Temp stores only."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.io_ops.admin import cache_admin

from test_cache_tab import admin_request, finish, frozen_cache, inventory, make_tab
from test_raw_fill import done, fill, write_raw
from helab.io_ops import stores
from helab.utils.cache_store import CacheStore
from test_txy_loading import v4_options


def opened(options: dict[str, Any], *sources: Path) -> CacheStore:
    return stores._cache_store(options["directory"], [str(source) for source in sources])


def raw_folders(tmp_path: Path) -> tuple[dict[str, Any], Path, Path]:
    options = v4_options(tmp_path)
    folders = []
    for name in ("a", "b"):
        folder = tmp_path / "data" / name
        folder.mkdir(parents=True)
        for shot in (1, 2):
            write_raw(folder, shot)
        assert done(fill(folder, options))["saved"] == 2
        folders.append(folder)
    return options, folders[0], folders[1]


def test_txy_only_for_a_folder_reports_its_raw_pulses_and_removes_nothing(tmp_path: Path) -> None:
    options, a, b = raw_folders(tmp_path)
    sent: list[dict[str, Any]] = []
    cache_admin(options, "folder_choice", sent.append, path=str(a), policy="txy", set_at=5.0)  # type: ignore[arg-type]
    [result] = [event for event in sent if event["kind"] == "admin_result"]
    assert result["folder_raw"]["shots"] == 2 and result["folder_raw"]["bytes"] > 0
    assert result["folder_raw"]["only_copy"] == 0
    with opened(options, a) as store:
        assert len(store.raw_rows(str(a)).value or {}) == 2  # (Nothing removed by the choice itself.)
    sent.clear()
    cache_admin(options, "folder_choice", sent.append, path=str(a), policy="raw", set_at=6.0)  # type: ignore[arg-type]
    assert "folder_raw" not in next(event for event in sent if event["kind"] == "admin_result")


def test_settings_txy_only_removes_only_the_raw_pulses_of_folders_that_follow_it(tmp_path: Path) -> None:
    options, a, b = raw_folders(tmp_path)
    cache_admin(options, "folder_choice", lambda event: None, path=str(b), policy="raw+used", set_at=5.0)
    sent: list[dict[str, Any]] = []
    cache_admin(options, "clear_raw", sent.append, following=True)  # type: ignore[arg-type]
    assert any(event["kind"] == "removed" and event["kinds"] == ["raw"] for event in sent)
    with opened(options, a, b) as store:
        assert store.raw_rows(str(a)).value == {} and len(store.raw_rows(str(b)).value or {}) == 2
        assert store.folder_raw(str(b))["shots"] == 2 and store.folder_raw(str(a))["shots"] == 0


def test_the_tab_that_chose_txy_only_asks_and_removes_only_on_a_yes(qtbot: QtBot,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from helab.views.FolderExplorer import FolderExplorer, remove_raw_text
    service, cache = frozen_cache(monkeypatch)
    try:
        offered: list[tuple[str, str, int, int]] = []
        cache.rawRemovalOffered.connect(lambda *args: offered.append(args))
        job = cache.set_folder_choice("/data/run", policy="txy", owner="tab-1")
        request = admin_request(service, "folder_choice")
        assert request.owner == job
        finish(service, request, {"kind": "admin_result", "action": "folder_choice", "next_deadline": None,
                                  "choices": {"policy": "txy"}, "folder_raw": {"shots": 2, "bytes": 3_000_000,
                                                                               "only_copy": 1}})
        assert offered == [("tab-1", "/data/run", 3_000_000, 1)]
        answers: list[bool] = [False, True]
        asked: list[tuple[str, int, int]] = []

        def ask(path: str, size: int, only: int) -> bool:
            asked.append((path, size, only))
            return answers.pop(0)
        explorer = SimpleNamespace(model=SimpleNamespace(owner="tab-1", cache=cache), closed=False, ask_remove_raw=ask)
        FolderExplorer._offer_raw_removal(explorer, "tab-2", "/data/run", 3_000_000, 1)  # type: ignore[arg-type]
        assert not asked  # (Another tab's choice: not this one's to ask.)
        FolderExplorer._offer_raw_removal(explorer, "tab-1", "/data/run", 3_000_000, 1)  # type: ignore[arg-type]
        assert not [r for r in service.pending if r.payload.get("action") == "clear_raw"]  # (Kept.)
        FolderExplorer._offer_raw_removal(explorer, "tab-1", "/data/run", 3_000_000, 1)  # type: ignore[arg-type]
        assert admin_request(service, "clear_raw").payload["params"]["paths"] == ["/data/run"]
        text = remove_raw_text("/data/run", 3_000_000, 1)
        assert "Also remove HeLab's cached copy of this folder's raw pulses (3.0 MB)? Your d files aren't touched." \
            in text and "1 of them are the only copy" in text
    finally:
        service.shutdown()


def test_settings_txy_only_asks_before_removing_the_raw_pulses(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                              tmp_path: Path) -> None:
    from helab.utils import folder_cache
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, asked = make_tab(qtbot, cache, tmp_path)
        raw = {"count": 40, "bytes": 30 * 10**6, "folders": 2, "only_copy": 0, "only_copy_bytes": 0, "last_used": None}
        tab.inventory = inventory(raw=raw, txy={"layers": 0, "folders": 0, "shots": 0, "bytes": 0, "only_copy": 0,
                                                "only_copy_folders": 0, "only_copy_bytes": 0, "tags": {},
                                                "last_used": None}, legacy=None, older_stores=[])
        def decline(title: str, text: str, verb: str) -> bool:
            asked.append((title, text, verb))
            return False
        tab.confirm = decline
        tab.policy_combo.setCurrentIndex(tab.policy_combo.findData("txy"))
        tab.save(tab.settings)
        assert asked and "up to 30.0 MB" in asked[-1][1] and "Your d files aren't touched" in asked[-1][1]
        assert not [r for r in service.pending if r.payload.get("action") == "clear_raw"]  # (Declined.)
        folder_cache.set_cache_policy("raw+used")
        tab.confirm = lambda title, text, verb: True
        tab.save(tab.settings)
        assert admin_request(service, "clear_raw").payload["params"] == {"following": True}
        count = len(asked)
        tab._job = ""
        tab.save(tab.settings)  # (Already TXY only: nothing asked again.)
        assert len(asked) == count
    finally:
        folder_cache.set_cache_policy("raw+used")
        service.shutdown()
