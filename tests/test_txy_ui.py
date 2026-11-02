"""Caching v2 stage 2, step 5 (the UI, store-v4 only): Settings › Cache's TXY data row (its Clear, and Clear all
taking TXY data too), the global cache policy (saved, sent with store-v4 requests, raw pulses skipped under
``txy``), lowering the budget asked from the helper's plan (S2-1), and Make room naming TXY layers. The switch
stays off: none of this shows with store-v3."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.utils import cache_store, folder_cache
from helab.utils.settings_defaults import CACHE_POLICY_SETTING, read_setting
from helab.views.CacheDialogs import room_items, room_text

from test_cache_tab import GB, admin_request, finish, frozen_cache, inventory, make_tab

MB = 10**6
TXY = {"layers": 3, "folders": 2, "shots": 120, "bytes": 40 * MB, "only_copy": 3, "only_copy_folders": 1,
       "only_copy_bytes": 5 * MB, "tags": {"MATLAB": 2, "m19v1": 1}, "last_used": None}


def v4_inventory(**changes: Any) -> dict[str, Any]:
    return inventory(**{"raw": {"count": 40, "bytes": 30 * MB, "folders": 2, "only_copy": 0, "only_copy_bytes": 0,
                                "last_used": None}, "txy": TXY, "legacy": None, "older_stores": [], **changes})


def test_the_tab_shows_txy_data_and_the_policy_only_with_store_v4(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, asked = make_tab(qtbot, cache, tmp_path)
        tab.inventory = inventory()
        tab._update()
        assert not tab.txy_button.isVisibleTo(tab) and not tab.policy_combo.isVisibleTo(tab)
        tab.inventory = v4_inventory()
        tab._update()
        assert tab.txy_button.isVisibleTo(tab) and tab.policy_combo.isVisibleTo(tab)
        assert "120 shots in 2 folders" in tab.txy_label.text() and "MATLAB, m19v1" in tab.txy_label.text()
        assert "3 only copies" in tab.txy_label.text()
        tab.clear_txy()
        assert "the only copy" in asked[-1][1] and admin_request(service, "clear_txy")
        tab._job = ""
        tab.clear(list(cache_store.KINDS))  # (Clear all.)
        assert "TXY data for 2 folders" in asked[-1][1]
        assert admin_request(service, "clear").payload["params"]["kinds"][-2:] == ["raw", "txy"]
        assert [tab.policy_combo.itemText(i) for i in range(3)] == [
            "Raw + what you load (default)", "Raw only, convert on load", "TXY only (no raw)"]
    finally:
        service.shutdown()


def test_the_clear_questions_name_only_copies_by_folder(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:
    """C2S2-1, C2S2-3: Clear all names the TXY data and raw pulses that are the only copy (remove_txy(None) and
    remove_raw(None) take them), and TXY data's Clear counts folders, not layers, with a singular that reads."""
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, asked = make_tab(qtbot, cache, tmp_path)
        raw = {"count": 40, "bytes": 30 * MB, "folders": 2, "only_copy": 4, "only_copy_bytes": MB, "last_used": None}
        tab.inventory = inventory(raw=raw, txy=TXY, legacy=None, older_stores=[])
        tab._update()
        tab.clear(list(cache_store.KINDS))
        assert "only copy (TXY data of 1 folder and raw pulses of 4 shots)" in asked[-1][1]
        assert "can't be read again" in asked[-1][1]
        tab._job = ""
        tab.inventory = v4_inventory()
        tab._update()
        tab.clear(list(cache_store.KINDS))
        assert "only copy (TXY data of 1 folder)" in asked[-1][1]
        tab._job = ""
        tab.inventory = v4_inventory(txy={**TXY, "only_copy": 0, "only_copy_folders": 0})
        tab.clear(list(cache_store.KINDS))
        assert "only copy" not in asked[-1][1]
        tab._job = ""
        tab.inventory = v4_inventory(txy={**TXY, "folders": 1, "only_copy": 3, "only_copy_folders": 1})
        tab.clear_txy()
        assert "the cached TXY data of 1 folder (" in asked[-1][1]
        assert "only copy (TXY data of 1 folder)" in asked[-1][1] and "3 folder" not in asked[-1][1]
    finally:
        service.shutdown()


def test_the_purge_question_counts_txy_and_raw_folders_in_store_v4(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    """C2S2-2: in store-v4 a purge of cached data takes TXY layers and seen raw layers not used since the cutoff
    (only copies stay), so its question and estimate count them, from the same comparisons as the purge."""
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, asked = make_tab(qtbot, cache, tmp_path)
        old = time.time() - 400 * 86400
        ages = {"datasets": [], "txy": [[old, 40 * MB, "root://u/a"], [old, MB, "root://u/a"],
                                        [time.time(), MB, "root://u/b"]],
                "raw": [[old, 30 * MB, "root://u/a"], [old, MB, "root://u/c"]]}
        tab.inventory = v4_inventory()
        tab.inventory["ages"] = {**tab.inventory["ages"], **ages}
        tab.dataset_days.setValue(30)
        tab._update()
        assert "(2 folders)" in tab.dataset_estimate.text() and tab.purge_datasets_button.isEnabled()
        tab.purge_datasets()
        text = asked[-1][1]
        assert "TXY data for 1 folder, raw pulses for 2 folders" in text and "cached data for 0" not in text
        assert "Only copies stay" in text
        estimate = cache_store.purge_estimate(tab.inventory, time.time() - 30 * 86400, datasets=True)
        assert estimate == {"datasets": 0, "bytes": 72 * MB, "txy_folders": 1, "txy_bytes": 41 * MB,
                            "raw_folders": 2, "raw_bytes": 31 * MB}
        assert admin_request(service, "purge").payload["params"]["what"] == "datasets"
    finally:
        service.shutdown()


def test_the_policy_is_saved_and_sent_with_store_v4_requests(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, _ = make_tab(qtbot, cache, tmp_path)
        tab.policy_combo.setCurrentIndex(tab.policy_combo.findData("txy"))
        tab.save(tab.settings)
        assert read_setting(tab.settings, CACHE_POLICY_SETTING, typed=True) == "txy"
        assert folder_cache.cache_policy() == "txy"
        assert "policy" not in folder_cache.store_options()  # (store-v3: none.)
        monkeypatch.setattr(folder_cache, "store_root", lambda folder: str(tmp_path / "caches" / "store-v4"))
        assert folder_cache.store_options()["policy"] == "txy"
    finally:
        folder_cache.set_cache_policy("raw+used")
        service.shutdown()


def test_policy_txy_keeps_no_raw_pulses(tmp_path: Path) -> None:
    from test_raw_fill import done, fill, source as _source, write_raw  # noqa: F401
    folder = tmp_path / "data" / "run"
    folder.mkdir(parents=True)
    for shot in (1, 2):
        write_raw(folder, shot)
    options = {"directory": str(tmp_path / "caches" / "store-v4"), "budget": 8 << 30, "budget_set_at": 1.0}
    assert done(fill(folder, {**options, "policy": "txy"}))["reason"] == "policy"
    assert done(fill(folder, options))["saved"] == 2


def test_lowering_the_budget_asks_from_the_helpers_plan_and_removes_exactly_it(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """S2-1's step 5: in store-v4 the question names what the plan removes (TXY data, raw pulses, only copies)
    and the trim sends those items, so nothing else goes; declining lowers nothing."""
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, asked = make_tab(qtbot, cache, tmp_path)
        applied: list[bool] = []
        tab.budgetApplied.connect(applied.append)
        finish(service, admin_request(service, "inventory"), {"kind": "inventory", "inventory": v4_inventory()})
        tab.disk_budget.setValue(1.0)
        assert tab.apply_budget() is None and not asked
        planning = admin_request(service, "trim")
        assert planning.payload["params"]["plan_only"] is True
        room = {"paths": [], "bytes": 0, "oldest_last_used": None, "newest_last_used": None, "possible": True,
                "raw_paths": ["/data/b"], "only_copy_paths": [], "raw_bytes": 30 * MB,
                "txy_layers": [["/data/a", "helab:h"]], "txy_seen": [], "txy_only": [["/data/z", "matlab"]],
                "txy_bytes": 40 * MB}
        items = room_items(room)
        finish(service, planning, {"kind": "admin_result", "action": "trim", "room": room, "items": items})
        assert "only copy: its TXY files are gone from z" in asked[-1][1] and "Lowering the budget" in asked[-1][1]
        trim = admin_request(service, "trim")
        assert trim is not planning and trim.payload["params"]["plan"] == items
        finish(service, trim, {"kind": "admin_result", "action": "trim", "datasets": 0, "bytes": 70 * MB})
        assert applied == [True]
        tab.confirm = lambda title, text, verb: False
        finish(service, admin_request(service, "inventory"), {"kind": "inventory", "inventory": v4_inventory()})
        tab.disk_budget.setValue(0.5)
        assert tab.apply_budget() is None
        finish(service, admin_request(service, "trim"), {"kind": "admin_result", "action": "trim", "room": room,
                                                        "items": items})
        assert applied == [True, False] and "Budget not lowered" in tab.message
        assert not any(r.payload.get("params", {}).get("plan") for r in service.pending)
    finally:
        service.shutdown()


def test_make_room_names_txy_layers_and_its_items_are_the_stores() -> None:
    room = {"paths": ["/data/x"], "bytes": 10 * MB, "newest_last_used": None, "possible": True,
            "raw_paths": ["/data/w"], "only_copy_paths": [], "raw_bytes": MB,
            "txy_layers": [["/data/r", "helab:h"]], "txy_seen": [["/data/y", "matlab"]],
            "txy_only": [["/data/z", "matlab"]], "txy_bytes": 3 * MB}
    text = room_text(room)
    assert "HeLab makes again from their cached raw pulses" in text and "read again from their TXY files" in text
    assert "TXY data that is the only copy: its TXY files are gone from z" in text
    assert room_items(room) == list(cache_store.room_items(
        ["/data/x"], ["/data/w"], [], [("/data/r", "helab:h")], [("/data/y", "matlab")], [("/data/z", "matlab")]))
    assert room_items(room)[1] == cache_store.txy_item("txy:", "/data/r", "helab:h")


# The folder's own choices (step 5c)

def test_a_folders_own_choices_are_kept_and_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache = frozen_cache(monkeypatch)
    try:
        assert cache.set_folder_choice("/data/run", source="helab-only", tag="m19v1")
        request = admin_request(service, "folder_choice")
        assert request.payload["params"]["source"] == "helab-only" and request.payload["params"]["tag"] == "m19v1"
        assert cache.folder_choices["/data/run"]["source"] == "helab-only"  # (Kept now: the next load follows it.)
        cache.set_folder_choice("/data/run", policy="txy")
        assert cache.folder_choices["/data/run"]["policy"] == "txy" and cache.folder_choices["/data/run"]["tag"] == "m19v1"
    finally:
        service.shutdown()


def test_the_explorers_dialogs_set_exactly_what_was_picked(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from helab.utils import txy_sources
    from helab.views.CacheTab import POLICY_LABELS
    from helab.views.FolderExplorer import FOLDER_CHOICE_GLOBAL, FolderExplorer
    service, cache = frozen_cache(monkeypatch)
    try:
        answers: list[str] = []

        def ask(parent: Any, title: str, label: str, items: list[str], index: int, editable: bool) -> tuple[str, bool]:
            return answers.pop(0), True
        explorer = SimpleNamespace(model=SimpleNamespace(cache=cache), ask_item=ask)
        answers[:] = [txy_sources.LABELS["helab-only"], "m19v1"]
        FolderExplorer.choose_folder_txy(explorer, "/data/run")  # type: ignore[arg-type]
        assert admin_request(service, "folder_choice").payload["params"] | {"set_at": 0} == {
            "path": "/data/run", "source": "helab-only", "tag": "m19v1", "set_at": 0}
        answers[:] = [FOLDER_CHOICE_GLOBAL]
        FolderExplorer.choose_folder_txy(explorer, "/data/run")  # type: ignore[arg-type]
        assert admin_request(service, "folder_choice").payload["params"]["source"] == ""
        answers[:] = [dict(POLICY_LABELS)["raw"]]
        FolderExplorer.choose_folder_policy(explorer, "/data/run")  # type: ignore[arg-type]
        assert admin_request(service, "folder_choice").payload["params"]["policy"] == "raw"
    finally:
        service.shutdown()


def test_folder_details_names_a_folders_own_choices() -> None:
    from helab.views.FolderDetailsPanel import FolderDetailsPanel
    row = ("120 MATLAB", "MATLAB's TXY")
    assert FolderDetailsPanel._with_choices(row, {}) == row
    text, tip = FolderDetailsPanel._with_choices(row, {"source": "helab-only", "tag": "m19v1", "policy": "txy"})
    assert "this folder: " in text and "(m19v1)" in text and "cache: TXY only (no raw)" in text
    assert "right-click › TXY for this folder…" in tip
