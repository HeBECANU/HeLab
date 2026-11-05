"""LR-4's "Plot info" section and LR-3's long texts in a plot's settings: the section is closed by default (one
line, the input, elided, the folder's path in its tooltip) and, open, lists the dock's source line, the run's
detail and settings, the data's TXY and the record, wrapped to the panel; with a long folder name at the
panel's narrowest, every label on the page wraps, elides or fits. (Tooltips are plain text: the app wraps them,
``helab/views/tooltips.py``.)"""
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
from helab.views.explorer_text import breakable
from helab.views.plots.plot_info import PlotInfo
from test_basic_plots_v2_buttons import plot_button
from test_debug_runner_menu import load, run_folder, window  # noqa: F401  (``window`` is a fixture)

pytestmark = pytest.mark.no_auto_data_root  # RAM only, as tests/test_debug_runner_menu.py.

LONG = "run_0042_bragg_pulse_scan_detuning_minus_two_MHz_long_descriptive_folder_name"


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


def test_plot_info_holds_the_plots_input_and_record(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                                    tmp_path: Path) -> None:
    instance = opened(window, qtbot, tmp_path)
    info = instance.plot_info
    assert isinstance(info, PlotInfo) and not info.is_open() and not instance.info_open  # Closed (Q~7).
    assert info.summary is instance.input_label and instance.input_label.text().startswith(f"Input: {LONG} · rev 1")
    assert instance.path in instance.input_label.toolTip()  # (Plain: the app wraps it.)
    assert info.toggle.accessibleName() == "Plot info" and info.toggle.objectName() == "plot_info"
    lines = info.lines()
    assert lines[0].startswith(("Data source: ", "Showing previously loaded data: "))  # The dock's line.
    assert any(line.startswith(f"Input: {instance.path} · revision 1") for line in lines)  # The folder in full.
    assert any(line.startswith("TXY: ") for line in lines) and any(line.startswith("Covers: ") for line in lines)
    # LR-4: the dock keeps one line (folder, revision, Live); the run's detail and settings are here.
    dock = instance.dock_widget
    assert dock is not None
    detail = dock.property("plotSourceDetail")
    assert isinstance(detail, str) and "helab.v2.counts_per_shot v1" in detail and detail in lines
    line = dock.findChild(QLabel, "plot_data_source")
    assert line is not None and "helab.v2.counts_per_shot" not in line.text() and "\n" not in line.text()
    assert "Covers: " in line.toolTip()  # The record.
    assert info.body.isHidden()
    info.set_open(True)
    assert info.is_open() and instance.info_open and not info.body.isHidden()
    assert info.body.maximumHeight() <= info.text.fontMetrics().lineSpacing() * 12  # Scrolls beyond.
    assert info.text.wordWrap() and instance.path in info.text.text().replace("\u200b", "")
    assert breakable(LONG) in info.text.text()  # A long name has break opportunities (explorer_text).
    info.toggle.click()
    assert not info.is_open() and info.body.isHidden()


def test_v1_plots_get_the_section_too(window: HelabMainWindow, qtbot: QtBot, tmp_path: Path) -> None:  # noqa: F811
    instance = opened(window, qtbot, tmp_path, "v1")
    assert instance.metadata.identity().analysis_id == "helab.counts_per_shot"
    assert isinstance(instance.plot_info, PlotInfo) and instance.plot_info.lines()


def page_widgets(instance: AnalysisInstance) -> list[QWidget]:
    """The plot's settings page, its parameter tree (its rows' tooltips are the parameters' tips) and its Presets
    row left out: at 250 px "Preset:" is cut with Windows' fonts, known since the 2026-11-04 layout audit and not
    one of the lines LR-3 is about (the handoff's A~3)."""
    page = instance.param_tab
    assert page is not None
    from helab.analysis.parameter_tree import SettingsTree
    from helab.views.plots.presets import PresetBar
    left_out: list[QWidget] = [*page.findChildren(SettingsTree), *page.findChildren(PresetBar)]
    return [widget for widget in page.findChildren(QWidget) if widget.isVisibleTo(page)
            and not any(other is widget or other.isAncestorOf(widget) for other in left_out)]


def test_a_long_folder_name_fits_the_narrowest_panel(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                                     tmp_path: Path) -> None:
    """LR-3's check, offscreen: at the panel's least width (250 px), each label on the page wraps, elides or fits,
    with Plot info closed and open."""
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


def test_plot_info_follows_the_docks_relabel(window: HelabMainWindow, qtbot: QtBot,  # noqa: F811
                                             tmp_path: Path) -> None:
    """When the tab moves on to other data, the main window relabels the dock ("Showing previously loaded data");
    Plot info's first line, the dock's line, follows at once, not at the plot's next run."""
    instance = opened(window, qtbot, tmp_path)
    dock = instance.dock_widget
    assert dock is not None
    line = dock.findChild(QLabel, "plot_data_source")
    assert line is not None and line.text().startswith("Data source: ") and instance.plot_info.lines()[0] == line.text()
    (tmp_path / "other").mkdir()
    load(window, qtbot, run_folder(tmp_path / "other"))  # Another tab shows another folder.
    qtbot.waitUntil(lambda: line.text().startswith("Showing previously loaded data: "), timeout=10_000)
    assert instance.plot_info.lines()[0] == line.text()
