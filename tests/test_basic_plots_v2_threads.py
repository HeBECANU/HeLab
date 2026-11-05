"""Basic plots v2's hooks run where the script contract says: each plot opened from the Scripts panel computes on
the analysis worker thread and draws (``render``, ``draw``) and updates in place (``update``) on the GUI thread."""
from __future__ import annotations

import inspect
import threading
from pathlib import Path
from typing import Any, Callable

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from pytestqt.qtbot import QtBot

from helab.scripts import standard_v2
from helab.scripts.base import DatasetAnalysis
from helab.views.HelabMainWindow import HelabMainWindow
from test_basic_plots_v2_buttons import plot_button
from test_debug_runner_menu import load, run_folder, window  # noqa: F401  (``window`` is a fixture)

pytestmark = pytest.mark.no_auto_data_root  # RAM only, as tests/test_debug_runner_menu.py.

HOOKS = ("compute", "render", "draw", "update")


def v2_classes() -> list[type[DatasetAnalysis]]:
    return [cls for module in standard_v2.MODULES for cls in vars(module).values()
            if inspect.isclass(cls) and issubclass(cls, DatasetAnalysis) and cls.__module__ == module.__name__
            and not inspect.isabstract(cls)]


def recording(calls: list[tuple[str, str, bool]], name: str, hook: str, original: Callable[..., Any]
              ) -> Callable[..., Any]:
    def wrapped(self: DatasetAnalysis, *args: Any, **kwargs: Any) -> Any:
        calls.append((name, hook, threading.current_thread() is threading.main_thread()))
        return original(self, *args, **kwargs)
    return wrapped


def test_compute_on_the_worker_drawing_and_updates_on_the_gui_thread(
        window: HelabMainWindow, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    calls: list[tuple[str, str, bool]] = []
    names = []
    for cls in v2_classes():
        name = cls().get_metadata().name
        names.append(name)
        for hook in HOOKS:
            monkeypatch.setattr(cls, hook, recording(calls, name, hook, getattr(cls, hook)))
    assert len(names) == 7
    scripts = window.panel_right_bottom_script_selector
    load(window, qtbot, run_folder(tmp_path))
    for name in names:
        plot_button(window, "v2", name).click()
        qtbot.waitUntil(lambda: len(scripts.instances()) == 1 and scripts.instances()[0].shown is not None,
                        timeout=30_000)
        instance = scripts.instances()[0]
        first = instance.shown
        instance.rerun_button.click()  # The same settings again: drawn in place where the library can.
        qtbot.waitUntil(lambda: instance.shown is not None and instance.shown is not first, timeout=30_000)
        instance.close()
        qtbot.waitUntil(lambda: not scripts.instances(), timeout=10_000)
        ran = [(hook, on_gui) for script, hook, on_gui in calls if script == name]
        assert ("compute", False) in ran and ("update", True) in ran, (name, ran)  # Run twice, updated in place.
        assert any(hook in ("render", "draw") for hook, _ in ran), (name, ran)
        assert all(on_gui == (hook != "compute") for hook, on_gui in ran), (name, ran)
