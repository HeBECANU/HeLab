"""Layout audit (Side, 2026-11-04; see README.md beside this file). Not a test of the suite: copy it into tests/ to run."""
from __future__ import annotations

import json
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
        if type(w).__name__ in ("ElidedLabel",) or isinstance(w.parentWidget(), (QAbstractSpinBox, QComboBox)):
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
    (OUT / "findings.json").write_text(json.dumps(FINDINGS, indent=1))


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
