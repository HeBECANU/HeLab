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
TXY = {"layers": 3, "folders": 2, "shots": 120, "bytes": 40 * MB, "only_copy": 1, "only_copy_bytes": 5 * MB,
       "tags": {"MATLAB": 2, "m19v1": 1}, "last_used": None}


def v4_inventory(**changes: Any) -> dict[str, Any]:
    return inventory(raw={"count": 40, "bytes": 30 * MB, "folders": 2, "only_copy": 0, "only_copy_bytes": 0,
                          "last_used": None}, txy=TXY, legacy=None, older_stores=[], **changes)


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
        assert "1 only copies" in tab.txy_label.text()
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
