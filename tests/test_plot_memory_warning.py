"""A plot's memory warning on its settings page (Basic plots v2's 2D histograms first, Tony 2026-11-10): one line
shown as the settings change while their estimate (``DatasetAnalysis.estimated_bytes``) reaches
``budget_core.ESTIMATE_WARN_SHARE`` of the RAM budget, with Undo and Cancel; hidden under it, with the budget
unknown and for a script with no estimate. The plot runs either way; one log warning per change of settings."""
from __future__ import annotations

import logging
from typing import Any, Iterator, Mapping

import pytest
from pytestqt.qtbot import QtBot

from test_plot_ram_budget import Copy, Window, cache, dataset, open_plot, runner, window  # noqa: F401 (fixtures)
from helab.analysis.budget_core import ESTIMATE_WARN_SHARE
from helab.analysis.parameter_tree import parameter_of
from helab.analysis.results import AnalysisContext
from helab.utils.folder_cache import FolderCache
from helab.views.plots.instance import AnalysisInstance
from helab.views.plots.memory_row import MemoryRow

GIB = 1 << 30
BUDGET = 10 * GIB


class Heavy(Copy):
    """``Copy`` whose runs would take Scale GiB; it keeps each run's budget."""

    def __init__(self) -> None:
        super().__init__()
        self.budgets: list[int] = []

    def estimated_bytes(self, action_name: str, values: Mapping[str, Any]) -> int:
        return int(values["scale"]) * GIB

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        self.budgets.append(context.ram_budget)
        return super().compute(action_name, context)


class Failing(Copy):
    def estimated_bytes(self, action_name: str, values: Mapping[str, Any]) -> int:
        raise RuntimeError("no estimate")


@pytest.fixture
def budgeted(cache: FolderCache) -> Iterator[FolderCache]:
    cache.max_data_bytes = BUDGET
    yield cache


def row_of(instance: AnalysisInstance) -> MemoryRow:
    assert instance.memory_row is not None
    return instance.memory_row


def set_scale(instance: AnalysisInstance, value: int) -> None:
    assert instance.parameter_root is not None
    parameter_of(instance.parameter_root, instance.script.parameters("Plot")[0]).setValue(value)


def shown(instance: AnalysisInstance) -> bool:
    return not row_of(instance).isHidden()


def test_the_row_shows_over_the_share_and_hides_under(window: Window, qtbot: QtBot, budgeted: FolderCache) -> None:
    script = Heavy()
    instance = open_plot(window, qtbot, dataset("heavy", range(1, 3)), script)
    assert not shown(instance) and script.budgets == [BUDGET]  # (Its run got the budget.)
    assert ESTIMATE_WARN_SHARE == 0.5
    set_scale(instance, 6)  # 6 GiB of 10: over half.
    qtbot.waitUntil(lambda: shown(instance))
    assert row_of(instance).label.text() == "⚠ Estimated memory 6.0 GiB: 60 % of the RAM budget (10.0 GiB)"
    set_scale(instance, 5)  # Exactly half: it reaches it.
    qtbot.waitUntil(lambda: "50 %" in row_of(instance).label.text())
    set_scale(instance, 4)
    qtbot.waitUntil(lambda: not shown(instance))


def test_the_row_follows_the_budget_and_hides_with_it_unknown(window: Window, qtbot: QtBot,
                                                              budgeted: FolderCache) -> None:
    instance = open_plot(window, qtbot, dataset("heavy", range(1, 3)), Heavy())
    set_scale(instance, 6)
    qtbot.waitUntil(lambda: shown(instance))
    budgeted.set_ram_budget(20 * GIB)  # 6 of 20 GiB: under.
    window.budget.check()  # (As the main window does after a new budget: the plots' share of it.)
    qtbot.waitUntil(lambda: not shown(instance))
    budgeted.set_ram_budget(BUDGET)
    window.budget.check()
    qtbot.waitUntil(lambda: shown(instance))
    budgeted.max_data_bytes = 0  # Unknown: never shown.
    set_scale(instance, 9)
    qtbot.wait(50)
    assert not shown(instance)


def test_no_estimate_or_one_that_raises_shows_nothing(window: Window, qtbot: QtBot, budgeted: FolderCache,
                                                       caplog: pytest.LogCaptureFixture) -> None:
    plain = open_plot(window, qtbot, dataset("plain", range(1, 3)), Copy())
    with caplog.at_level(logging.ERROR):
        failing = open_plot(window, qtbot, dataset("failing", range(1, 3)), Failing())
    for instance in (plain, failing):
        set_scale(instance, 10)
    qtbot.wait(50)
    assert not shown(plain) and not shown(failing)
    assert "estimated_bytes of Copy failed" in caplog.text


def test_undo_puts_back_the_settings_last_under_it(window: Window, qtbot: QtBot, budgeted: FolderCache) -> None:
    instance = open_plot(window, qtbot, dataset("heavy", range(1, 3)), Heavy())
    set_scale(instance, 2)
    qtbot.wait(20)
    set_scale(instance, 7)
    qtbot.waitUntil(lambda: shown(instance))
    row = row_of(instance)
    assert row.undo.isEnabled() and row.undo.toolTip() == "Put back: Scale 2 (now 7)"
    row.undo.click()
    assert instance.values()["scale"] == 2
    qtbot.waitUntil(lambda: not shown(instance))


def test_cancel_is_on_only_while_a_run_is_in_flight_and_cancels_it(window: Window, qtbot: QtBot,
                                                                   budgeted: FolderCache) -> None:
    script = Heavy()
    instance = open_plot(window, qtbot, dataset("heavy", range(1, 3)), script)
    set_scale(instance, 8)
    qtbot.waitUntil(lambda: shown(instance))
    row = row_of(instance)
    assert not row.cancel.isEnabled()
    script.go.clear()  # The next run waits.
    try:
        instance.run()
        assert instance.job_id and row.cancel.isEnabled()
        row.cancel.click()
    finally:
        script.go.set()
    qtbot.waitUntil(lambda: not instance.job_id, timeout=10_000)
    assert not row.cancel.isEnabled() and instance.status_label.text() == "Cancelled"


def test_one_log_warning_per_change_of_settings(window: Window, qtbot: QtBot, budgeted: FolderCache,
                                                caplog: pytest.LogCaptureFixture) -> None:
    instance = open_plot(window, qtbot, dataset("heavy", range(1, 3)), Heavy())

    def warnings() -> list[str]:
        return [record.getMessage() for record in caplog.records
                if record.levelno == logging.WARNING and "Estimated memory" in record.getMessage()]
    with caplog.at_level(logging.WARNING):
        set_scale(instance, 6)
        qtbot.waitUntil(lambda: len(warnings()) == 1)
        instance.run()  # (A run, a Live rerun, a budget check: the same settings, not logged again.)
        qtbot.waitUntil(lambda: not instance.job_id, timeout=10_000)
        instance._memory_check()
        assert len(warnings()) == 1
        set_scale(instance, 7)
        qtbot.waitUntil(lambda: len(warnings()) == 2)
    assert "7.0 GiB" in warnings()[1] and "it still runs" in warnings()[1]
