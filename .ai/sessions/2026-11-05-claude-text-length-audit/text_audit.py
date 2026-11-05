"""Text-length audit (LR-3's app half, Mendy, 2026-11-05; see README.md beside this file).

Extends Side's layout audit (.ai/sessions/2026-11-04-claude-ui-audit/layout_audit.py) to the whole app at
several window sizes and panel widths, with long folder names and long values where text comes from data.
Not a test of the suite: copy it into tests/ to run (README).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QModelIndex, QPoint, QRect, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QTextDocument
from PyQt6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox, QApplication,
                             QCheckBox, QComboBox, QDialog, QHeaderView, QLabel, QLineEdit, QMessageBox, QRadioButton, QTabBar,
                             QToolTip, QTreeView, QWidget)

import tests.test_accessible_names as an

OUT = Path(__file__).resolve().parent.parent / ".ai" / "temp" / "text-audit"
OUT.mkdir(parents=True, exist_ok=True)
FINDINGS: list[dict[str, Any]] = []

# Long names where text comes from data: a lab folder three levels deep, each name as long as the lab's.
LONG_PARTS = ("Helium BEC lab data archive copied from the lab PC on the shared drive",
              "2026-11-05 halo correlations after the evaporation ramp change (Tony's long-run test)",
              "run_0042_mF=+1_after_evaporation_ramp_v3_with_a_much_longer_condition_name_than_usual")
TOOLTIP_WIDE = 800  # px: a plain-text tooltip line wider than this is reported (Qt doesn't wrap plain text).
TOOLTIP_TALL = 30  # lines
WRAPPED_TALL = 4  # lines: a word-wrapped label taller than this is reported


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


@pytest.fixture(scope="module", autouse=True)
def dump() -> Any:
    yield
    (OUT / "findings.json").write_text(json.dumps(FINDINGS, indent=1))
    lines = [f"{f['case']} | {f['kind']} | {f['widget']} | "
             + ", ".join(f"{k}={v}" for k, v in f.items() if k not in ("case", "kind", "widget")) for f in FINDINGS]
    (OUT / "findings.txt").write_text("\n".join(lines) + "\n")


def long_run(root: Path, shots: int = 3) -> Path:
    """A synthetic TXY folder under three long names, settled (as ``an.run_folder``)."""
    run = root.joinpath(*LONG_PARTS)
    run.mkdir(parents=True)
    old = time.time() - 60
    for shot in range(1, shots + 1):
        path = run / f"d_txy_forc{shot}.txt"
        path.write_text("".join(f"{0.1 + i * 1e-3:.6f},{(i % 7) * 1e-3:.6f},{(i % 5) * 1e-3:.6f}\n"
                                for i in range(300)))
        os.utime(path, (old, old))
    return run


def full_text(w: QWidget) -> str:
    if isinstance(w, (QLabel, QAbstractButton)):
        return w.text()
    if isinstance(w, QComboBox):
        return w.currentText()
    return ""


def shown_text(w: QWidget) -> str:
    """What an eliding widget draws (``text()`` gives its full text)."""
    if type(w).__name__ == "ElidedLabel":
        return QLabel.text(w)  # type: ignore[arg-type]
    return full_text(w)


def name_of(w: QWidget) -> str:
    return f"{type(w).__name__}[{w.objectName() or w.accessibleName() or ''}] {full_text(w)[:60]!r}"


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


def plain(text: str) -> str:
    if Qt.mightBeRichText(text):
        doc = QTextDocument()
        doc.setHtml(text)
        return doc.toPlainText()
    return text


def add(case: str, kind: str, widget: QWidget | None, **detail: Any) -> None:
    FINDINGS.append({"case": case, "kind": kind, "widget": name_of(widget) if widget is not None else "", **detail})


def audit_tooltip(case: str, w: QWidget, tip: str, seen: set[str]) -> None:
    if not tip or tip in seen:
        return
    seen.add(tip)
    metrics = QFontMetrics(QToolTip.font())
    rich = Qt.mightBeRichText(tip)
    lines = plain(tip).split("\n")
    if len(lines) > TOOLTIP_TALL:
        add(case, "tooltip tall", w, lines=len(lines), first=lines[0][:80])
    if not rich:  # (Qt wraps a rich-text tooltip to the screen; a plain one is as wide as its longest line.)
        widest = max(lines, key=metrics.horizontalAdvance)
        if metrics.horizontalAdvance(widest) > TOOLTIP_WIDE:
            add(case, "tooltip wide", w, px=metrics.horizontalAdvance(widest), chars=len(widest), line=widest[:100])


def audit_view(case: str, view: QAbstractItemView) -> None:
    """Item views: cells whose text is cut, and whether the cell's tooltip has the whole of it."""
    model = view.model()
    if model is None:
        return
    cut, untipped, example = 0, 0, ""

    def walk(parent: QModelIndex, depth: int) -> None:
        nonlocal cut, untipped, example
        try:
            columns = model.columnCount(parent)
        except TypeError:  # (A list model's is private: one column.)
            columns = 1
        header = view.header() if isinstance(view, QTreeView) else None
        for row in range(min(model.rowCount(parent), 60)):
            for column in range(columns):
                index = model.index(row, column, parent)
                if header is not None and header.isSectionHidden(column):
                    continue
                rect = view.visualRect(index)
                text = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
                if not text or not rect.isValid() or rect.width() <= 0:
                    continue
                need = view.fontMetrics().horizontalAdvance(text.split("\n")[0]) + 8
                icon = model.data(index, Qt.ItemDataRole.DecorationRole)
                if icon is not None:
                    need += view.iconSize().width() if view.iconSize().isValid() else 16
                if rect.width() < need:
                    cut += 1
                    tip = str(model.data(index, Qt.ItemDataRole.ToolTipRole) or "")
                    if text not in plain(tip):
                        untipped += 1
                    example = example or f"{text[:60]!r} {rect.width()}<{need}"
            if depth < 4 and hasattr(view, "isExpanded"):
                child = model.index(row, 0, parent)
                if view.isExpanded(child):  # type: ignore[attr-defined]
                    walk(child, depth + 1)

    walk(QModelIndex(), 0)
    if cut:
        add(case, "cells cut", view, cells=cut, without_full_tooltip=untipped, example=example)


def audit(top: QWidget, case: str) -> None:
    QApplication.processEvents()
    top.grab().save(str(OUT / f"{case.replace(' ', '_').replace('›', '-').replace('/', '-')}.png"))
    top_rect = top.rect()
    widgets = [w for w in top.findChildren(QWidget) if w.isVisibleTo(top) and w.width() > 0 and w.height() > 0]
    seen_tips: set[str] = set()
    audit_tooltip(case, top, top.toolTip(), seen_tips)
    for w in widgets:
        audit_tooltip(case, w, w.toolTip(), seen_tips)
        if isinstance(w, QAbstractItemView) and not isinstance(w, QHeaderView) \
                and not isinstance(w.parentWidget(), QComboBox):
            audit_view(case, w)
        if isinstance(w, QTabBar):
            for i in range(w.count()):
                audit_tooltip(case, w, w.tabToolTip(i), seen_tips)
        if isinstance(w.parentWidget(), (QAbstractSpinBox, QComboBox)):
            continue
        kind = type(w).__name__
        # Eliding widgets: the text they show is cut on purpose; report when the tooltip lacks the rest.
        if kind in ("ElidedLabel", "ElidedButton"):
            full, shown = full_text(w), shown_text(w)
            if kind == "ElidedButton":
                need = w.fontMetrics().horizontalAdvance(full) + 16
                elided = w.width() < need
            else:
                elided = bool(full) and shown != full
            if elided:
                add(case, "elided", w, shows=shown[:80], chars_shown=len(shown.rstrip("…")), chars=len(full),
                    full_in_tooltip=plain(full) in plain(getattr(w, "hover_tip", w.toolTip)()) if full else True)
            continue
        hint = w.sizeHint()
        if isinstance(w, (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit)) and hint.isValid():
            if w.height() < hint.height() - 1:
                add(case, "squeezed", w, h=w.height(), hint=hint.height())
        if isinstance(w, (QAbstractButton,)) and not isinstance(w, (QCheckBox, QRadioButton)) and w.text():
            if hint.isValid() and w.width() < hint.width() - 4 and w.isVisible():
                add(case, "button text cut", w, w=w.width(), need=hint.width())
        if isinstance(w, (QCheckBox, QRadioButton)) and w.text() and w.width() < hint.width() - 2:
            add(case, "check text cut", w, w=w.width(), need=hint.width())
        if isinstance(w, QComboBox) and w.currentText():
            need = w.fontMetrics().horizontalAdvance(w.currentText()) + 34  # (Fusion's frame and arrow.)
            if w.width() < need:
                add(case, "combo text cut", w, w=w.width(), need=need)
        if isinstance(w, QLabel) and w.text() and w.pixmap().isNull():
            if not w.wordWrap():
                need = w.fontMetrics().horizontalAdvance(plain(w.text()).split("\n")[0])
                if need > 0 and w.width() < need - 2:
                    add(case, "label cut", w, w=w.width(), need=need, text=plain(w.text())[:100])
                if w.height() < w.fontMetrics().height() - 2:
                    add(case, "label squeezed", w, h=w.height(), need=w.fontMetrics().height())
            else:
                # The text's own height at its width (a label may be taller: its row's stretch).
                lines = round(min(w.height(), w.heightForWidth(w.width())) / max(1, w.fontMetrics().lineSpacing()))
                if lines > WRAPPED_TALL:
                    add(case, "wraps tall", w, lines=lines, w=w.width(), text=plain(w.text())[:100])
        if not in_scroll(w) and w.window() is top.window():
            r = visible_rect(w, top)
            if r.right() > top_rect.right() + 1 or r.bottom() > top_rect.bottom() + 1:
                add(case, "outside window", w, rect=[r.x(), r.y(), r.width(), r.height()],
                    top=[top_rect.width(), top_rect.height()])
    # Names running into their values (Side's check): a label's text ends under 5 px from the next widget.
    texts = [w for w in widgets if isinstance(w, (QLabel, QCheckBox)) and text_width(w) > 0
             and type(w).__name__ != "ElidedLabel"]
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
                add(case, "touching", a, next=name_of(b), gap=gap)


def sized(qtbot: QtBot, top: QWidget, case: str, size: tuple[int, int]) -> None:
    """Resize ``top`` and audit it, noting when its contents keep it larger than asked."""
    top.resize(*size)
    qtbot.wait(150)
    if top.width() > size[0] + 2 or top.height() > size[1] + 2:
        add(case, "window larger than asked", top, asked=list(size), got=[top.width(), top.height()],
            minimum=[top.minimumSizeHint().width(), top.minimumSizeHint().height()])
    audit(top, case)


SETTINGS_SIZES = ((880, 620), (800, 500), (700, 450))


def test_settings(qtbot: QtBot) -> None:
    from helab.utils.folder_cache import get_folder_cache
    from helab.utils.io_service import get_io_service
    from helab.utils.settings_store import app_settings
    from helab.views.SettingsDialog import SettingsDialog
    service = get_io_service()
    dialog = SettingsDialog(settings=app_settings(), cache=get_folder_cache(service))
    qtbot.addWidget(dialog)
    dialog.show()
    an.settled(qtbot, service)
    for size in SETTINGS_SIZES:
        for index in range(dialog.tabs.count()):
            dialog.tabs.setCurrentIndex(index)
            sized(qtbot, dialog, f"Settings {size[0]}x{size[1]} › {dialog.tabs.tabText(index)}", size)
    dialog.reject()


WINDOW_SIZES = ((1440, 860), (1100, 700), (900, 600))
LEFT_WIDTHS = (250, 420, 700)


@pytest.mark.no_auto_data_root
def test_main_window(qtbot: QtBot, tmp_path: Path) -> None:
    """The main window with a long-named folder loaded, at each size and left-panel width; then with a
    Live phrase in the status bar (a session set by hand, no checks run) and Folder details' Live row."""
    from helab.views.explorer_live import LiveSession
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    run = long_run(tmp_path)
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.resize(*WINDOW_SIZES[0])
    window.show()
    try:
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer), timeout=10_000)
        sized(qtbot, window, "main empty 1440x860", WINDOW_SIZES[0])
        empty_minimum = window.minimumSizeHint().width()
        window.add_new_folder_explorer_tab(target_path=str(run))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        qtbot.waitUntil(lambda: explorer.displayed_dataset is not None
                        and explorer.displayed_dataset.path == str(run), timeout=30_000)
        qtbot.wait(300)
        add("main loaded", "window minimum width", window, empty=empty_minimum, loaded=window.minimumSizeHint().width(),
            middle=window.splitter.widget(1).minimumSizeHint().width())
        for size in WINDOW_SIZES:
            for left in LEFT_WIDTHS:
                if left > size[0] - 400:
                    continue
                window.resize(*size)
                qtbot.wait(100)
                sizes = window.splitter.sizes()
                window.splitter.setSizes([left, sum(sizes) - left - sizes[2], sizes[2]])
                case = f"main loaded {size[0]}x{size[1]} left {left}"
                sized(qtbot, window, case, size)
                got = window.splitter.sizes()
                if abs(got[0] - left) > 2:
                    add(case, "panel width not taken", window.splitter, asked=left, got=got,
                        minimum=[window.splitter.widget(i).minimumSizeHint().width() for i in range(3)])
        dataset = explorer.displayed_dataset
        assert dataset is not None
        explorer.live = LiveSession(str(run), time.time() - 3600, set(dataset.data), dataset, new=1234,
                                    checks=99, checked_at=time.time())
        try:
            for size in WINDOW_SIZES:
                window.resize(*size)
                window.splitter.setSizes([420, size[0] - 420 - window.splitter.sizes()[2], window.splitter.sizes()[2]])
                window.update_status_bar_left()
                explorer._update_folder_summary()
                sized(qtbot, window, f"main Live {size[0]}x{size[1]}", size)
                add(f"main Live {size[0]}x{size[1]}", "status bar text", window.status_bar_message_left,
                    full=window.status_bar_message_left.text(),
                    shows=QLabel.text(window.status_bar_message_left))
        finally:
            explorer.live = None
    finally:
        an.quit_window(qtbot, window)


DIALOG_SIZES: tuple[tuple[int, int] | None, ...] = (None, (640, 420))


@pytest.mark.parametrize("case", list(an.DIALOGS))
def test_dialog(case: str, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each dialog of the accessible-names walk, given a long folder path where it names one."""
    make, _ = an.DIALOGS[case]
    service, cache = an.frozen(monkeypatch)
    folder = tmp_path.joinpath(*LONG_PARTS)
    folder.mkdir(parents=True)
    try:
        window = make(cache, folder)
        qtbot.addWidget(window)
        window.show()
        qtbot.wait(150)
        if hasattr(window, "refresh"):
            window.refresh()
        audit(window, f"dialog {case} {window.width()}x{window.height()} (as opened)")
        if window.width() > 1400 or window.height() > 900:
            add(f"dialog {case}", "opens large", window, size=[window.width(), window.height()])
        sized(qtbot, window, f"dialog {case} 640x420", (640, 420))
        if isinstance(window, QDialog):
            window.reject()
        window.close()
    finally:
        service.shutdown()


def ask_old_traces(cache: Any, parent: QWidget, folder: Path) -> None:
    from helab.views.HelabMainWindow import HelabMainWindow
    HelabMainWindow._ask_delete_old_traces(parent, 3, 4_000, str(folder / "io-traces"))  # type: ignore[arg-type]


ASKS: dict[str, Callable[[Any, QWidget, Path], None]] = {
    "old I/O traces": ask_old_traces,
    **{case: (lambda make: lambda cache, parent, folder: make(cache, parent))(make)
       for case, make in an.ASKS.items() if case != "old I/O traces"}}


@pytest.mark.parametrize("case", list(ASKS))
def test_message_box(case: str, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[str] = []

    def opened(box: QMessageBox) -> int:
        box.show()
        QApplication.processEvents()
        audit(box, f"box {case} {box.width()}x{box.height()}")
        seen.append(case)
        box.close()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", opened)
    service, cache = an.frozen(monkeypatch)
    parent = QWidget()
    qtbot.addWidget(parent)
    try:
        ASKS[case](cache, parent, tmp_path.joinpath(*LONG_PARTS))
    finally:
        service.shutdown()
    assert seen
