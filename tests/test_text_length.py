"""Text that comes from data fits its window (LR-3; the audit in
.ai/sessions/2026-11-05-claude-text-length-audit/): long folder names and long tooltips."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QFontMetrics, QHelpEvent
from PyQt6.QtWidgets import QAbstractButton, QApplication, QLabel, QPushButton, QTabBar, QToolTip, QWidget

import test_accessible_names as an
from helab.views import tooltips
from helab.views.ElidedLabel import ElidedLabel
from helab.views.explorer_text import BREAK, breakable, middle

# A folder three levels deep under names as long as the lab's.
LONG_PARTS = ("Helium BEC lab data archive copied from the lab PC on the shared drive",
              "2026-11-05 halo correlations after the evaporation ramp change (Tony's long-run test)",
              "run_0042_mF=+1_after_evaporation_ramp_v3_with_a_much_longer_condition_name_than_usual")


def long_run(root: Path, shots: int = 3) -> Path:
    """A settled synthetic TXY folder under ``LONG_PARTS``."""
    run = root.joinpath(*LONG_PARTS)
    run.mkdir(parents=True)
    old = time.time() - 60
    for shot in range(1, shots + 1):
        path = run / f"d_txy_forc{shot}.txt"
        path.write_text("".join(f"{0.1 + i * 1e-3:.6f},{(i % 7) * 1e-3:.6f},{(i % 5) * 1e-3:.6f}\n" for i in range(300)))
        os.utime(path, (old, old))
    return run


def test_long_words_get_break_opportunities_and_names_shorten_in_the_middle() -> None:
    name = LONG_PARTS[2]
    assert breakable("Loaded run — run a script") == "Loaded run — run a script"
    broken = breakable(f"Loaded {name} — run a script")
    assert broken.replace(BREAK, "") == f"Loaded {name} — run a script" and BREAK in broken
    assert breakable("a/b\nshort") == "a/b\nshort"
    assert middle("run_1") == "run_1"
    short = middle(name)
    assert len(short) == 40 and short.startswith("run_0042_mF=+1_after") and short.endswith("than_usual")
    assert "…" in short


def test_a_long_plain_tooltip_wraps_at_words_and_breaks_a_long_path(qtbot: QtBot) -> None:
    metrics = QFontMetrics(QToolTip.font())
    text = ("While Live watches a folder, its next check starts this long after the previous one ended, so checks "
            "never overlap and a slow share isn't asked twice at once.\nKept: " + "/".join(LONG_PARTS))
    assert tooltips.needs_wrap(text, metrics)
    wrapped = tooltips.wrap_tip(text, metrics)
    lines = wrapped.split("\n")
    assert len(lines) > 3 and all(metrics.horizontalAdvance(line) <= tooltips.WIDTH for line in lines)
    assert "".join(wrapped.split()) == "".join(text.split())  # Nothing lost: only line breaks added.
    assert lines[0].startswith("While Live watches") and not lines[1].startswith(" ")
    assert not tooltips.needs_wrap("Short", metrics) and tooltips.wrap_tip("Short", metrics) == "Short"
    assert not tooltips.needs_wrap("<b>rich</b> " + "x " * 400, metrics)  # (Qt wraps rich text.)


def test_the_apps_filter_shows_a_long_plain_tooltip_wrapped(qtbot: QtBot) -> None:
    """T4 (Tony 2026-11-05): the widget keeps its tooltip; the one shown is wrapped at ~600 px."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    wrap = tooltips.TooltipWrap()
    app.installEventFilter(wrap)
    try:
        button = QPushButton("Change…")
        qtbot.addWidget(button)
        long_tip = "Move the disk cache to another folder. " * 12
        button.setToolTip(long_tip)
        button.show()
        event = QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2), button.mapToGlobal(QPoint(2, 2)))
        assert wrap.eventFilter(button, event)
        metrics = QFontMetrics(QToolTip.font())
        assert button.toolTip() == long_tip
        assert QToolTip.text() == tooltips.wrap_tip(long_tip, metrics) and "\n" in QToolTip.text()
        button.setToolTip("Short")
        assert not wrap.eventFilter(button, event)  # (Qt shows it as it is.)
        # T3: an elided label's tip with its full text, shown by the filter (no event() override there).
        label = ElidedLabel("3 TXY found · 3 loaded · 1,234 new shots")
        qtbot.addWidget(label)
        label.setToolTip("Counts of this folder")
        label.show()
        label.resize(label.natural_width() // 3, label.sizeHint().height())
        qtbot.waitUntil(label.elided, timeout=5_000)
        assert wrap.eventFilter(label, QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2), label.mapToGlobal(QPoint(2, 2))))
        assert QToolTip.text() == label.hover_tip() == "3 TXY found · 3 loaded · 1,234 new shots\n\nCounts of this folder"
        label.resize(label.natural_width() + 40, label.sizeHint().height())
        qtbot.waitUntil(lambda: not label.elided(), timeout=5_000)
        assert not wrap.eventFilter(label, QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2), label.mapToGlobal(QPoint(2, 2))))
        tabs = QTabBar()
        qtbot.addWidget(tabs)
        tabs.addTab("General")
        tabs.setTabToolTip(0, long_tip)
        tabs.show()
        assert tooltips.tooltip_at(tabs, QHelpEvent(QEvent.Type.ToolTip, tabs.tabRect(0).center(), QPoint())) == long_tip
    finally:
        app.removeEventFilter(wrap)
        QToolTip.hideText()


def test_an_elided_label_shows_its_full_text_in_its_tooltip(qtbot: QtBot) -> None:
    """(b), T3: Folder details' rows and the summary's lines lost the text they cut."""
    label = ElidedLabel("3 TXY found · 3 loaded · 1,234 new shots")
    qtbot.addWidget(label)
    label.show()
    label.resize(label.natural_width() + 40, label.sizeHint().height())  # (Widths from the font: any OS.)
    qtbot.waitUntil(lambda: not label.elided(), timeout=5_000)
    assert label.hover_tip() == ""
    label.setToolTip("Counts of this folder")
    label.resize(label.natural_width() // 3, label.sizeHint().height())
    qtbot.waitUntil(label.elided, timeout=5_000)
    assert label.toolTip() == "Counts of this folder"
    assert label.hover_tip() == "3 TXY found · 3 loaded · 1,234 new shots\n\nCounts of this folder"
    label.setToolTip("Folder: 3 TXY found · 3 loaded · 1,234 new shots")  # (Already in it: as it is.)
    assert label.hover_tip() == label.toolTip()
    label.setToolTip("<b>Counts</b>")
    assert label.hover_tip() == "3 TXY found · 3 loaded · 1,234 new shots<br><br><b>Counts</b>"
    label.setToolTip("")
    assert label.hover_tip() == "3 TXY found · 3 loaded · 1,234 new shots"


@pytest.mark.no_auto_data_root  # RAM only: no save left for the quit to wait for.
def test_a_long_folder_name_doesnt_widen_the_main_window_or_hide_the_live_phrases_end(
        qtbot: QtBot, tmp_path: Path) -> None:
    """(a), T1: the centre hint's long name held the plots area 648 px wide and the window ≥ 1105 px;
    T2: the status bar's Live phrase lost its counts and age off the end."""
    from helab.views.explorer_live import LiveSession
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    run = long_run(tmp_path)
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.resize(1100, 700)
    window.show()
    try:
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer), timeout=10_000)
        empty = window.minimumSizeHint().width()
        window.add_new_folder_explorer_tab(target_path=str(run))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        qtbot.waitUntil(lambda: explorer.displayed_dataset is not None
                        and explorer.displayed_dataset.path == str(run), timeout=30_000)
        qtbot.waitUntil(lambda: LONG_PARTS[2] in window.plots.central_placeholder.text(), timeout=10_000)
        assert window.minimumSizeHint().width() <= empty + 100, (empty, window.minimumSizeHint().width())
        plots_area = window.splitter.widget(1)
        assert plots_area is not None and plots_area.minimumSizeHint().width() < 400
        assert window.plots.central_placeholder.text().startswith(f"Loaded {LONG_PARTS[2]}")
        # T7 (Tony 2026-11-05): Arm auto-convert on a line of its own at a tight panel, its text whole;
        # at a normal width, the summary's fixed three lines.
        button, line = explorer.auto_convert_button, explorer._summary_line
        assert button.isVisible() and button.parent() is explorer.live_row
        assert explorer.summary_widget.height() == 3 * line
        # Tight: the line holds the button but not it beside "Live…" (widths from the fonts, any OS).
        need = button.width() + 4 + explorer.folder_freshness_label.fontMetrics().horizontalAdvance("Live…")
        offset = window.splitter.sizes()[0] - explorer.live_row.width()
        window._set_split((button.width() + need) // 2 + offset, 300, window.splitter.width())
        qtbot.waitUntil(lambda: explorer.convert_row.isVisible(), timeout=5_000)
        assert button.parent() is explorer.convert_row and button.isVisible()
        assert explorer.summary_widget.height() == 4 * line and explorer.convert_row.width() >= button.width()
        window._set_split(450, 300, window.splitter.width())
        qtbot.waitUntil(lambda: explorer.convert_row.isHidden(), timeout=5_000)
        assert button.parent() is explorer.live_row and button.isVisible()
        assert explorer.summary_widget.height() == 3 * line
        dataset = explorer.displayed_dataset
        assert dataset is not None
        explorer.live = LiveSession(str(run), time.time() - 3600, set(dataset.data), dataset, new=1234)
        try:
            window.update_status_bar_left()
            label = window.status_bar_message_left
            # A window as wide as the phrase needs with the name shortened (fonts differ by OS).
            room = label.fontMetrics().horizontalAdvance(explorer.activity_brief) + 40
            if label.width() < room:
                window.resize(window.width() + room - label.width(), window.height())
                qtbot.waitUntil(lambda: label.width() >= room, timeout=5_000)
                window.update_status_bar_left()
            # (After any notice the window shows first, e.g. the disk cache's "below 80 %".)
            assert f"Live checking {middle(LONG_PARTS[2])} · 1,234 new shots · latest shot 3" in label.text()
            assert "latest shot 3 · 1 min" in QLabel.text(label), QLabel.text(label)  # (Shown: the age too.)
            assert str(run) in label.toolTip()
        finally:
            explorer.live = None
    finally:
        an.quit_window(qtbot, window)


@pytest.mark.parametrize("case", ["copy root", "large folder"])
def test_a_long_path_doesnt_open_a_dialog_wider_than_900_px(
        case: str, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(c), T5 and T6: It's a copy… opened 2868 px wide, Load a large folder? 1119 px."""
    make, _ = an.DIALOGS[case]
    service, cache = an.frozen(monkeypatch)
    folder = tmp_path.joinpath(*LONG_PARTS)
    folder.mkdir(parents=True)
    try:
        window = make(cache, folder)
        qtbot.addWidget(window)
        window.show()
        qtbot.wait(50)
        assert window.width() <= 900, window.width()
        shown = " ".join([*(w.text() for w in window.findChildren(QLabel)),
                          *(w.text() for w in window.findChildren(QAbstractButton))])
        tips = " ".join(w.toolTip() for w in window.findChildren(QWidget))
        assert LONG_PARTS[2] in shown.replace(BREAK, "") or LONG_PARTS[2] in tips
        window.close()
    finally:
        service.shutdown()


def test_a_wrap_row_takes_its_groups_rows_only_when_it_doesnt_fit(qtbot: QtBot) -> None:
    from helab.views.wrap_row import WrapRow
    buttons = [QPushButton(text) for text in ("Refresh", "Forget location…", "Delete .helab-root…", "Review…")]
    row = WrapRow(buttons, (buttons[:2], buttons[2:]))
    qtbot.addWidget(row)
    row.resize(row.sizeHint().width() + 20, 40)
    row.show()
    qtbot.wait(20)
    assert row.wrapped is False and len(row.rows) == 1
    narrow = max(buttons[0].sizeHint().width() + buttons[1].sizeHint().width(),
                 buttons[2].sizeHint().width() + buttons[3].sizeHint().width()) + 20
    assert row.minimumSizeHint().width() < row.sizeHint().width()  # (A window can narrow to two rows.)
    row.resize(narrow, 80)
    qtbot.wait(20)
    assert row.wrapped is True and len(row.rows) == 2
    assert all(button.width() >= button.sizeHint().width() for button in buttons)
    row.resize(row.sizeHint().width() + 20, 40)
    qtbot.wait(20)
    assert row.wrapped is False


def test_the_data_roots_buttons_keep_their_text_at_settings_least_size(qtbot: QtBot) -> None:
    """T8 (Tony 2026-11-05): "Clear cached analysis…" was cut at 800×500. At a tight width the buttons
    take two rows; at a normal width, one."""
    from helab.utils.folder_cache import get_folder_cache
    from helab.utils.io_service import get_io_service
    from helab.utils.settings_store import app_settings
    from helab.views.DataRootsTab import DataRootsTab
    from helab.views.SettingsDialog import SettingsDialog
    service = get_io_service()
    dialog = SettingsDialog(settings=app_settings(), cache=get_folder_cache(service))
    qtbot.addWidget(dialog)
    dialog.resize(800, 500)
    dialog.show()
    try:
        tab = dialog.findChild(DataRootsTab)
        assert tab is not None
        dialog.tabs.setCurrentIndex(dialog.tabs.indexOf(tab))
        qtbot.wait(50)
        buttons = [tab.refresh_button, tab.forget_button, tab.delete_button, tab.clear_button,
                   tab.clear_results_button, tab.review_button]
        rows = tab.button_rows
        assert rows.wrapped is (not rows.fits(rows.width()))
        assert all(button.width() >= button.sizeHint().width() for button in buttons), [
            (button.text(), button.width(), button.sizeHint().width()) for button in buttons]
        dialog.resize(rows.sizeHint().width() + 120, 620)  # A normal width: one row.
        qtbot.wait(50)
        assert rows.wrapped is False and all(button.width() >= button.sizeHint().width() for button in buttons)
        dialog.resize(800, 500)
        qtbot.wait(50)
        assert all(button.width() >= button.sizeHint().width() for button in buttons)
    finally:
        dialog.reject()


def plain_tips(window: QWidget) -> list[tuple[str, str]]:
    """Each plain-text tooltip in ``window`` (its widgets' and its tab bars' tabs'), with whose."""
    found = [(window.objectName(), window.toolTip())]
    for widget in window.findChildren(QWidget):
        found.append((f"{type(widget).__name__}[{widget.objectName()}]", widget.toolTip()))
        if isinstance(widget, QTabBar):
            found += [(f"tab {widget.tabText(i)}", widget.tabToolTip(i)) for i in range(widget.count())]
    return [(who, tip) for who, tip in found if tip and not tooltips.rich_text(tip)]


def too_wide(window: QWidget) -> list[str]:
    """(d): the tooltips of ``window`` with a line over 800 px as the app's filter shows them."""
    metrics = QFontMetrics(QToolTip.font())
    wide = []
    for who, tip in plain_tips(window):
        shown = tooltips.wrap_tip(tip, metrics) if tooltips.needs_wrap(tip, metrics) else tip
        widest = max(metrics.horizontalAdvance(line) for line in shown.split("\n"))
        if widest > 800:
            wide.append(f"{who}: {widest} px")
    return wide


def test_no_tooltip_in_settings_shows_a_line_over_800_px(qtbot: QtBot) -> None:
    """(d), T4: 58 plain tooltips had lines over 800 px (up to 3444 px) before the app's filter wrapped them."""
    from helab.utils.folder_cache import get_folder_cache
    from helab.utils.io_service import get_io_service
    from helab.utils.settings_store import app_settings
    from helab.views.SettingsDialog import SettingsDialog
    service = get_io_service()
    dialog = SettingsDialog(settings=app_settings(), cache=get_folder_cache(service))
    qtbot.addWidget(dialog)
    dialog.show()
    try:
        an.settled(qtbot, service)
        metrics = QFontMetrics(QToolTip.font())
        assert any(tooltips.needs_wrap(tip, metrics) for _, tip in plain_tips(dialog))  # (There are long ones.)
        assert not too_wide(dialog)
    finally:
        dialog.reject()


@pytest.mark.parametrize("case", list(an.DIALOGS))
def test_no_tooltip_in_a_dialog_shows_a_line_over_800_px(
        case: str, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(d), with a long folder path where a dialog names one."""
    make, _ = an.DIALOGS[case]
    service, cache = an.frozen(monkeypatch)
    folder = tmp_path.joinpath(*LONG_PARTS)
    folder.mkdir(parents=True)
    try:
        window = make(cache, folder)
        qtbot.addWidget(window)
        window.show()
        qtbot.wait(20)
        assert not too_wide(window)
        window.close()
    finally:
        service.shutdown()


def test_main_installs_the_tooltip_filter() -> None:
    """``helab/main.py`` installs it once the app has its font (the tooltips' metrics)."""
    source = (Path(__file__).resolve().parents[1] / "helab" / "main.py").read_text()
    assert source.index("tooltips.install(app)") > source.index("app.setFont(helab_mono_font)")


def test_rich_text_is_qts_guess() -> None:
    assert tooltips.rich_text("<b>x</b>") and not tooltips.rich_text("a < b")
    assert Qt.TextFormat.PlainText  # (The module needs Qt's names loaded.)
