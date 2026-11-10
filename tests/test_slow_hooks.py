"""GT-17 (guard 4): a user script's hook that runs on the GUI thread (``render``, ``update``, ``draw``, the
``_hook`` ones: ``describe_*``, ``estimated_bytes``, ``parameter_warnings``…) is timed, and one over
``SLOW_HOOK_SECONDS`` is logged with the plot, the script's class and the hook: the window waited for it."""
from __future__ import annotations

import logging
import time
import types
from typing import Any, cast

import pytest

from helab.views.plots import instance as instance_module
from helab.views.plots.instance import AnalysisInstance


class Slow:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def describe_result(self, action: str, result: object) -> str:
        time.sleep(self.seconds)
        return "described"

    def render(self, result: object) -> object:
        time.sleep(self.seconds)
        return "drawn"

    def update(self, drawn: object, result: object) -> bool:
        time.sleep(self.seconds)
        return True


def plot(script: Slow) -> Any:
    return types.SimpleNamespace(script=script, action="Plot", name="Counts per shot (1)", backend=lambda: "",
                                 shown=object(), released=None, _content=types.SimpleNamespace(),
                                 _drawn_with="")


def test_a_slow_hook_is_logged_with_its_plot_script_and_hook(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(instance_module, "SLOW_HOOK_SECONDS", 0.01)
    monkeypatch.setattr("helab.views.plots.instance.sip.isdeleted", lambda widget: False)
    shown, result = plot(Slow(0.05)), cast(Any, object())
    with caplog.at_level(logging.WARNING):
        assert AnalysisInstance._hook(shown, "describe_result", "", result) == "described"
        assert cast(Any, AnalysisInstance._draw(shown, result)) == "drawn"
        assert AnalysisInstance._updated(shown, result) is shown._content
    lines = [record.getMessage() for record in caplog.records]
    assert [line.split(" took ")[0] for line in lines] == [
        "Counts per shot (1): Slow.describe_result", "Counts per shot (1): Slow.render",
        "Counts per shot (1): Slow.update"], lines
    assert all("on the GUI thread" in line for line in lines)


def test_a_quick_hook_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    assert instance_module.SLOW_HOOK_SECONDS == 0.5
    with caplog.at_level(logging.WARNING):
        assert AnalysisInstance._hook(plot(Slow(0.0)), "describe_result", "", object()) == "described"
    assert not caplog.records
