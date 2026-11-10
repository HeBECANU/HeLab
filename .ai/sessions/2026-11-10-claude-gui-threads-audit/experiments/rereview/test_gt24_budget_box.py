"""Re-review, GT-24: Settings › Cache's "Lower the disk cache budget?" opens inside a helper's delivery.

Run from the checkout's root: ``PYTHONPATH=tests python -m pytest -p conftest <this file> -q``. It reuses
``tests/test_cache_tab.py``'s helpers, keeps CacheTab's real ``_confirm`` (the box), and delivers the budget job's
answer the way IOService's ``_tick`` does (inside ``gui_delivery.delivering("io")``; the tests' ``finish`` emits
``resultReady`` directly, outside any delivery, so guard 2 never sees this path). Guard 2 records the box.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from test_cache_tab import GB, admin_request, finish, frozen_cache, inventory, make_tab


def test_the_budget_question_opens_inside_the_delivery(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                       tmp_path: Path, no_modal_in_delivery: list[str]) -> None:
    from helab.utils import gui_delivery
    service, cache = frozen_cache(monkeypatch)
    try:
        tab, _ = make_tab(qtbot, cache, tmp_path)
        tab.confirm = tab._confirm  # (The real box, as in the app.)
        finish(service, admin_request(service, "inventory"), {"kind": "inventory", "inventory": inventory()})
        tab.disk_budget.setValue(4.0)
        assert tab.apply_budget() is None
        request = admin_request(service, "budget")
        with gui_delivery.delivering("io"), qtbot.captureExceptions() as caught:
            finish(service, request, {"kind": "admin_result", "action": "budget", "budget": 4 * GB,
                                      "recorded": False, "usage": 5 * GB, "next_deadline": None})
        assert caught and "GT-1" in str(caught[0][1])  # (Raised by guard 2 in the box's exec, inside the slot.)
        assert no_modal_in_delivery and "QMessageBox.exec while delivering 'io'" in no_modal_in_delivery[0]
        assert "_ask_trim" in no_modal_in_delivery[0]
        no_modal_in_delivery.clear()  # (Seen: the test itself passes.)
    finally:
        service.shutdown()
