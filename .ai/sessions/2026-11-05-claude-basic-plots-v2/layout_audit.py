"""Layout audit (Side, 2026-11-04, ``sessions/2026-11-04-claude-ui-audit/``), extended on the Basic plots v2 floor
(LR-3, 2026-11-05) with ``test_plot_settings``: plot settings and plot docks with a long folder name at several
panel widths and window sizes, and a check for plain-text tooltips with over-long lines. Not a test of the suite:
copy it into tests/ to run, on a real display (``HELAB_SHOW_GUI=1``; see README.md beside the original).
``-k plot_settings`` runs the new case alone; its findings go to ``findings-plot-settings.json``."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QAbstractSpinBox, QApplication, QCheckBox,
                             QComboBox, QDialog, QLabel, QLineEdit, QWidget)

import tests.test_accessible_names as an

OUT = Path(__file__).resolve().parent.parent / ".ai" / "temp" / "ui-audit"
TOOLTIP_LINE = 100  # A plain-text tooltip line longer than this runs across the screen (Qt wraps rich text only).
OUT.mkdir(parents=True, exist_ok=True)
FINDINGS: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def helab_look() -> Any:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_style, old_font = app.style().name(), app.font()  # type: ignore[union-attr]
    app.setStyle("Fusion")
    app.setFont(QFont("SF Mono", 12))
    yield
    app.setStyle(old_style)
    app.setFont(old_font)


def name_of(w: QWidget) -> str:
    text = ""
    if isinstance(w, (QLabel, QAbstractButton)):
        text = w.text()
    return f"{type(w).__name__}[{w.objectName() or w.accessibleName() or ''}] {text[:50]!r}"


def in_scroll(w: QWidget) -> bool:
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QAbstractScrollArea) and p.viewport() is not None and p.viewport().isAncestorOf(w):
            return True
        p = p.parentWidget()
    return False


def visible_rect(w: QWidget, top: QWidget) -> QRect:
    return QRect(w.mapTo(top, QPoint(0, 0)), w.size())


def text_width(w: QWidget) -> int:
    if isinstance(w, QLabel):
        return w.fontMetrics().horizontalAdvance(w.text()) if w.text() and not w.wordWrap() else -1
    if isinstance(w, QCheckBox):
        return w.sizeHint().width()
    return -1


def audit(top: QWidget, case: str) -> None:
    QApplication.processEvents()
    top.grab().save(str(OUT / f"{case.replace(' ', '_').replace('›', '-').replace('/', '-')}.png"))
    top_rect = top.rect()
    widgets = [w for w in top.findChildren(QWidget) if w.isVisibleTo(top) and w.width() > 0 and w.height() > 0]
    for w in widgets:
        # (An ElidedLabel, or a subclass such as plot settings' TipLabel, elides by design: never "cut".)
        if (any(cls.__name__ == "ElidedLabel" for cls in type(w).__mro__)
                or isinstance(w.parentWidget(), (QAbstractSpinBox, QComboBox))):
            continue
        hint, minimum = w.sizeHint(), w.minimumSizeHint()
        if isinstance(w, (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit)) and hint.isValid():
            if w.height() < hint.height() - 1:
                FINDINGS.append({"case": case, "kind": "squeezed", "widget": name_of(w),
                                 "h": w.height(), "hint": hint.height()})
        if isinstance(w, QLabel) and w.text() and not w.wordWrap() and w.pixmap().isNull():
            need = w.fontMetrics().horizontalAdvance(w.text().split("\n")[0]) if "<" not in w.text() else -1
            if need > 0 and w.width() < need - 2:
                FINDINGS.append({"case": case, "kind": "label cut", "widget": name_of(w), "w": w.width(), "need": need})
            if w.height() < w.fontMetrics().height() - 2:
                FINDINGS.append({"case": case, "kind": "label squeezed", "widget": name_of(w), "h": w.height(),
                                 "need": w.fontMetrics().height()})
        tip = w.toolTip()
        if tip and not tip.lstrip().startswith("<") and max(len(line) for line in tip.splitlines() or [""]) > TOOLTIP_LINE:
            FINDINGS.append({"case": case, "kind": "tooltip too wide", "widget": name_of(w),
                             "longest": max(len(line) for line in tip.splitlines())})
        if not in_scroll(w) and w.window() is top.window():
            r = visible_rect(w, top)
            if r.right() > top_rect.right() + 1 or r.bottom() > top_rect.bottom() + 1:
                FINDINGS.append({"case": case, "kind": "outside window", "widget": name_of(w),
                                 "rect": [r.x(), r.y(), r.width(), r.height()], "top": [top_rect.width(), top_rect.height()]})
    # Names running into their values: text end of one label within 4 px of the next widget on its row.
    texts = [w for w in widgets if isinstance(w, (QLabel, QCheckBox)) and text_width(w) > 0]
    for a in texts:
        ra = visible_rect(a, top)
        if isinstance(a, QLabel) and a.alignment() & Qt.AlignmentFlag.AlignRight:
            continue
        end = ra.x() + text_width(a)
        for b in widgets:
            if b is a or b.parentWidget() is not a.parentWidget() or a.isAncestorOf(b) or b.isAncestorOf(a):
                continue
            rb = visible_rect(b, top)
            overlap = min(ra.bottom(), rb.bottom()) - max(ra.top(), rb.top())
            if overlap < min(ra.height(), rb.height()) * 0.6:
                continue
            gap = rb.x() - end
            if isinstance(b, QLabel) and b.text() and (b.alignment() & Qt.AlignmentFlag.AlignRight):
                gap = rb.right() - b.fontMetrics().horizontalAdvance(b.text()) - end
            if -2 <= gap < 5 and rb.x() >= ra.x() + 4:
                FINDINGS.append({"case": case, "kind": "touching", "widget": name_of(a), "next": name_of(b), "gap": gap})


@pytest.fixture(scope="module", autouse=True)
def dump() -> Any:
    yield
    name = "findings-plot-settings.json" if os.environ.get("AUDIT_PLOT_SETTINGS_ONLY") else "findings.json"
    (OUT / name).write_text(json.dumps(FINDINGS, indent=1))


def test_settings(qtbot: QtBot) -> None:
    from helab.utils.io_service import get_io_service
    from helab.utils.folder_cache import get_folder_cache
    from helab.utils.settings_store import app_settings
    from helab.views.SettingsDialog import SettingsDialog
    service = get_io_service()
    dialog = SettingsDialog(settings=app_settings(), cache=get_folder_cache(service))
    qtbot.addWidget(dialog)
    for size in ((880, 620), (800, 500)):
        dialog.resize(*size)
        dialog.show()
        an.settled(qtbot, service)
        for index in range(dialog.tabs.count()):
            dialog.tabs.setCurrentIndex(index)
            qtbot.wait(50)
            audit(dialog, f"Settings {size[0]}x{size[1]} › {dialog.tabs.tabText(index)}")
    dialog.reject()


def test_main_window(qtbot: QtBot, tmp_path: Path) -> None:
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    run = an.run_folder(tmp_path)
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.resize(1440, 860)
    window.show()
    try:
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer), timeout=10_000)
        audit(window, "main empty")
        window.add_new_folder_explorer_tab(target_path=str(run))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        qtbot.waitUntil(lambda: explorer.displayed_dataset is not None, timeout=30_000)
        qtbot.wait(200)
        audit(window, "main loaded")
        for name in ("Counts per shot", "T, X, Y histograms"):
            an.script_button(window, name).click()
        scripts = window.panel_right_bottom_script_selector
        qtbot.waitUntil(lambda: len(scripts.instances()) == 2 and all(i.shown is not None for i in scripts.instances()),
                        timeout=30_000)
        qtbot.wait(300)
        audit(window, "main plots")
        window.resize(1100, 700)
        qtbot.wait(300)
        audit(window, "main plots small")
    finally:
        an.quit_window(qtbot, window)


@pytest.mark.parametrize("case", list(an.DIALOGS))
def test_dialog(case: str, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    make, _ = an.DIALOGS[case]
    service, cache = an.frozen(monkeypatch)
    try:
        window = make(cache, tmp_path)
        qtbot.addWidget(window)
        window.show()
        qtbot.wait(100)
        audit(window, f"dialog {case}")
        if isinstance(window, QDialog):
            window.reject()
        window.close()
    finally:
        service.shutdown()


# LR-3: plot settings with long folder names (Basic plots v2 floor)

LONG_PARENT = "2026-11-05_overnight_transfer_scan_series_with_a_long_name"
LONG_RUN = "run_0042_bragg_pulse_scan_detuning_minus_two_MHz_long_descriptive_folder_name"
PLOTS = (("v2", "Counts per shot"), ("v2", "T, X, Y histograms"), ("v2", "XY histogram"), ("v2", "Transfer fractions"),
         ("v1", "Counts per shot"))
WINDOWS = ((1100, 700), (1440, 860), (1920, 1080))
PANELS = (250, 320, 480)


def long_run_folder(root: Path, shots: int = 3) -> Path:
    """A synthetic TXY folder with a long path, settled (modified a minute ago)."""
    run = root / LONG_PARENT / LONG_RUN
    run.mkdir(parents=True)
    old = time.time() - 60
    for shot in range(1, shots + 1):
        path = run / f"d_txy_forc{shot}.txt"
        path.write_text("".join(f"{2.1 + (i % 50) * 1e-3:.6f},{(i % 7) * 1e-3:.6f},{(i % 5) * 1e-3:.6f}\n"
                                for i in range(600)))
        os.utime(path, (old, old))
    return run


def plot_button(window: Any, version: str, name: str) -> Any:
    from PyQt6.QtWidgets import QPushButton
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


def test_plot_settings(qtbot: QtBot, tmp_path: Path) -> None:
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    run = long_run_folder(tmp_path)
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.resize(*WINDOWS[1])
    window.show()
    scripts = window.panel_right_bottom_script_selector
    try:
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer), timeout=10_000)
        window.add_new_folder_explorer_tab(target_path=str(run))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        qtbot.waitUntil(lambda: explorer.displayed_dataset is not None, timeout=30_000)
        for opened, (version, name) in enumerate(PLOTS, start=1):
            plot_button(window, version, name).click()
            qtbot.waitUntil(lambda: len(scripts.instances()) == opened
                            and all(i.shown is not None for i in scripts.instances()), timeout=30_000)
        settings = window.plots.panel_right_top_plot_settings
        for size in WINDOWS:
            window.resize(*size)
            qtbot.wait(200)
            for panel in PANELS:
                left, middle, right = window.splitter.sizes()
                window.splitter.setSizes([left, max(100, middle + right - panel), panel])
                qtbot.wait(150)
                for instance in scripts.instances():
                    dock = instance.dock_widget
                    assert dock is not None
                    settings.show_plot(dock, raise_dock=True)
                    qtbot.wait(80)
                    info = getattr(instance, "plot_info", None)
                    states = (False, True) if info is not None else (None,)
                    for state in states:
                        if info is not None:
                            info.set_open(bool(state))
                            qtbot.wait(50)
                        how = "" if state is None else (" info open" if state else " info closed")
                        audit(window, f"plot settings {size[0]}x{size[1]} panel {panel} {instance.name} "
                                      f"{instance.metadata.identity().analysis_id}{how}")
    finally:
        an.quit_window(qtbot, window)
