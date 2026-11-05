"""LR-2: while a plot of a script is open, its Plot button reads "New" (Q65.2) and its tooltip says how many are
open ("Open another Counts per shot plot (1 open)"); it still opens another plot, and reads "Plot" again once
none is open. Its accessible name stays, and v1's and v2's scripts are counted apart."""
from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot

from helab.views.HelabMainWindow import HelabMainWindow
from helab.views.plots import script_tree
from test_debug_runner_menu import load, run_folder, window  # noqa: F401  (``window`` is a fixture)

# RAM only (no data root): nothing is left for a quit to wait for (as tests/test_debug_runner_menu.py).
pytestmark = pytest.mark.no_auto_data_root


def plot_button(window: HelabMainWindow, version: str, name: str) -> QPushButton:
    tree = window.panel_right_bottom_script_selector.tree_widget
    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is None or top.text(0) != version:
            continue
        for row in range(top.childCount()):
            item = top.child(row)
            if item is not None and item.text(0) == name:
                button = tree.itemWidget(item, 1)
                assert isinstance(button, QPushButton)
                return button
    raise AssertionError(f"No {name} in {version}")


def test_the_plot_button_reads_new_while_a_plot_of_it_is_open(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                                              tmp_path: Path) -> None:
    assert script_tree.NEW_PLOT_TEXT == "New"
    scripts = window.panel_right_bottom_script_selector
    load(window, qtbot, run_folder(tmp_path))
    v2, v1 = plot_button(window, "v2", "Counts per shot"), plot_button(window, "v1", "Counts per shot")
    assert v2.text() == v1.text() == "Plot" and v2.accessibleName() == "Plot Counts per shot"
    v2.click()
    qtbot.waitUntil(lambda: len(scripts.instances()) == 1, timeout=30_000)
    v2 = plot_button(window, "v2", "Counts per shot")
    assert v2.text() == "New" and v2.toolTip() == "Open another Counts per shot plot (1 open)"
    assert v2.accessibleName() == "Plot Counts per shot" and v2.accessibleDescription() == v2.toolTip()
    assert plot_button(window, "v1", "Counts per shot").text() == "Plot"  # Another script: counted apart.
    assert plot_button(window, "v2", "T, X, Y histograms").text() == "Plot"
    v2.click()  # It still opens another plot.
    qtbot.waitUntil(lambda: len(scripts.instances()) == 2, timeout=30_000)
    assert plot_button(window, "v2", "Counts per shot").toolTip() == "Open another Counts per shot plot (2 open)"
    # The tree listed again (another group and back) keeps the names.
    scripts.group_selector.setCurrentText("DLD Front Panel Port")
    scripts.group_selector.setCurrentText("Basic Plots")
    assert plot_button(window, "v2", "Counts per shot").text() == "New"
    for instance in list(scripts.instances()):
        instance.close()
    qtbot.waitUntil(lambda: not scripts.instances(), timeout=10_000)
    button = plot_button(window, "v2", "Counts per shot")
    assert button.text() == "Plot" and "on this tab's loaded data" in button.toolTip()
