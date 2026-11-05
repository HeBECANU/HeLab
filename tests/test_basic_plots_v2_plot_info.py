"""LR-4's "Plot info" section and LR-3's long texts in a plot's settings: the section is closed by default (one
line, the input, all of it in a wrapped tooltip) and, open, lists the input in full, the dock's source lines, the
data's TXY and the record, wrapped to the panel; with a long folder name at the panel's narrowest, every label
on the page wraps, elides or fits, and no tooltip there is a long plain line."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

from helab.views.ElidedLabel import ElidedLabel
from helab.views.HelabMainWindow import HelabMainWindow
from helab.views.plots.instance import AnalysisInstance
from helab.views.plots.plot_info import PlotInfo, TipLabel, rich, wrapped_tip
from tests.test_basic_plots_v2_buttons import plot_button
from tests.test_debug_runner_menu import load, window  # noqa: F401  (``window`` is a fixture)

pytestmark = pytest.mark.no_auto_data_root  # RAM only, as tests/test_debug_runner_menu.py.

LONG = "run_0042_bragg_pulse_scan_detuning_minus_two_MHz_long_descriptive_folder_name"
TOOLTIP_LINE = 100


def long_run(root: Path) -> Path:
    run = root / "2026-11-05_overnight_transfer_scan_series" / LONG
    run.mkdir(parents=True)
    old = time.time() - 60
    for shot in range(1, 4):
        path = run / f"d_txy_forc{shot}.txt"
        path.write_text("".join(f"{2.1 + (i % 50) * 1e-3:.6f},{(i % 7) * 1e-3:.6f},{(i % 5) * 1e-3:.6f}\n"
                                for i in range(300)))
        os.utime(path, (old, old))
    return run


def opened(window: HelabMainWindow, qtbot: QtBot, tmp_path: Path, version: str = "v2") -> AnalysisInstance:
    scripts = window.panel_right_bottom_script_selector
    load(window, qtbot, long_run(tmp_path))
    plot_button(window, version, "Counts per shot").click()
    qtbot.waitUntil(lambda: len(scripts.instances()) == 1 and scripts.instances()[0].shown is not None,
                    timeout=30_000)
    return scripts.instances()[0]


def test_wrapped_tips_and_tip_labels(qtbot: QtBot) -> None:
    assert wrapped_tip("") == "" and wrapped_tip("a < b\nc") == "<qt>a &lt; b<br>c</qt>" and rich(wrapped_tip("x"))
    assert not rich("plain text") and rich("<b>bold</b>")
    label = TipLabel()
    qtbot.addWidget(label)
    label.setText("A long line")
    assert label.text() == "A long line" and label.toolTip() == "<qt>A long line</qt>"
    label.setToolTip("Its own tip\nsecond")
    assert label.toolTip() == "<qt>Its own tip<br>second</qt>"
    label.setToolTip("<b>rich</b>")
    assert label.toolTip() == "<b>rich</b>"


def test_plot_info_holds_the_plots_input_and_record(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                                    tmp_path: Path) -> None:
    instance = opened(window, qtbot, tmp_path)
    info = instance.plot_info
    assert isinstance(info, PlotInfo) and not info.is_open() and not instance.info_open  # Closed (Q~7).
    assert info.summary is instance.input_label and instance.input_label.text().startswith(f"Input: {LONG} · rev 1")
    assert instance.path in instance.input_label.toolTip() and rich(instance.input_label.toolTip())
    assert info.toggle.accessibleName() == "Plot info" and info.toggle.objectName() == "plot_info"
    lines = info.lines()
    assert lines[0] == f"{instance.input_label.text()} · {instance.path}"
    assert any(line.startswith(("Data source: ", "Showing previously loaded data: ")) for line in lines)
    assert any(line.startswith("TXY: ") for line in lines) and any(line.startswith("Covers: ") for line in lines)
    assert info.text.isHidden()
    info.set_open(True)
    assert info.is_open() and instance.info_open and not info.text.isHidden()
    assert info.text.wordWrap() and instance.path in info.text.text()
    info.toggle.click()
    assert not info.is_open() and info.text.isHidden()


def test_v1_plots_get_the_section_too(window: HelabMainWindow, qtbot: QtBot, tmp_path: Path) -> None:  # noqa: F811
    instance = opened(window, qtbot, tmp_path, "v1")
    assert instance.metadata.identity().analysis_id == "helab.counts_per_shot"
    assert isinstance(instance.plot_info, PlotInfo) and instance.plot_info.lines()


def page_widgets(instance: AnalysisInstance) -> list[QWidget]:
    """The plot's settings page, its parameter tree left out (its rows' own tooltips: the parameters' tips)."""
    page = instance.param_tab
    assert page is not None
    from helab.analysis.parameter_tree import SettingsTree
    trees = page.findChildren(SettingsTree)
    return [widget for widget in page.findChildren(QWidget) if widget.isVisibleTo(page)
            and not any(tree is widget or tree.isAncestorOf(widget) for tree in trees)]


def test_a_long_folder_name_fits_the_narrowest_panel(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                                     tmp_path: Path) -> None:
    """LR-3's check, offscreen: at the panel's least width (250 px), each label on the page wraps, elides or fits,
    with Plot info closed and open, and no tooltip there is a plain line over 100 characters."""
    instance = opened(window, qtbot, tmp_path)
    left, middle, right = window.splitter.sizes()
    window.splitter.setSizes([left, middle + right - 250, 250])
    names = {widget.objectName() for widget in page_widgets(instance)}
    assert {"plot_input", "plot_info", "txy_source", "txy_note", "plot_status"} <= names  # The page's lines.
    for state in (False, True):
        instance.plot_info.set_open(state)
        qtbot.wait(50)
        for widget in page_widgets(instance):
            if isinstance(widget, QLabel) and widget.text() and not isinstance(widget, ElidedLabel):
                fits = widget.fontMetrics().horizontalAdvance(widget.text().split("\n")[0]) <= widget.width() + 2
                assert widget.wordWrap() or fits, f"{widget.objectName() or widget.text()!r} is cut"
            tip = widget.toolTip()
            if tip and not rich(tip):
                longest = max(len(line) for line in tip.splitlines())
                assert longest <= TOOLTIP_LINE, f"{widget.objectName()}: a {longest}-character tooltip line"
