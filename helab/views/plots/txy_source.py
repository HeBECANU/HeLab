"""A plot's TXY choice (Q6.6, Q18.2, Q53.2): which TXY its data is made of, in its settings page.

A TXY priority list (``txy_sources``): External (the MATLAB converter's ``d_txy_forc``), the conversion
profile, and any profile's HeLab TXY by its tag, in order; each shot takes the first entry with a usable TXY.
"As the folder's tab" follows the folder's tab (its own list, else Settings › TXY converter's). A plot on
another choice than the tab's loads its own dataset of the folder (RAM only) through ``FolderCache`` and loads
it again when Live finds new shots. The row is one button naming the list in short, which opens the list
editor (``helab/views/txy_list.py``); a line under it names the profile HeLab converts with and, from the
folder's date, the plate profile the swap dates suggest (Q6.10: shown, never applied), and "Keep" (Keep this
plot's TXY choice, on by default; Q14.2 = Q23.4): on, the choice is saved with the plot's presets,
arrangements and the plots reopened at start; off, it isn't (for tweaking and exploring).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from helab.analysis.dataset_view import DatasetView
from helab.convert.profile import BUILTIN_PROFILES, UNCALIBRATED, DetectorProfile, file_tag, suggested_plates
from helab.utils.accessible import identify
from helab.utils.txy_sources import Entries
from helab.views.ElidedLabel import ElidedLabel
from helab.views.txy_list import AskList, ask_txy_list, known_names, list_summary


def known_profiles() -> dict[str, DetectorProfile]:
    """The built-in and user profiles by name (a user profile folder that can't be read gives none)."""
    from helab.convert.user_profiles import ProfileLibrary
    from helab.utils.constants import profiles_folder
    try:
        user = ProfileLibrary(profiles_folder()).profiles()
    except OSError:
        user = {}
    return {**dict(BUILTIN_PROFILES), **user}


def profile_by_tag(tag: str) -> Optional[DetectorProfile]:
    """The known profile whose TXY carry ``tag`` (``profile.file_tag``), or None."""
    return next((profile for profile in known_profiles().values() if file_tag(profile) == tag), None)


def folder_day(view: DatasetView) -> str:
    """The folder's date (``YYYY-MM-DD``, local): its first shot's, "" when no shot has a time."""
    times = view.shot_times()
    return datetime.fromtimestamp(min(times.values())).strftime("%Y-%m-%d") if times else ""


def plate_note(view: DatasetView, profile_name: str) -> str:
    """``plates-2022 suggested for this folder's date (2023-02-04)`` when the swap dates suggest
    another profile than the one HeLab converts with; "" otherwise."""
    day = folder_day(view)
    suggested = suggested_plates(day) if day else None
    if suggested is None or suggested == profile_name:
        return ""
    return f"{suggested}{' (uncalibrated)' if suggested in UNCALIBRATED else ''} suggested for this folder's date ({day})"


class ElidedButton(QPushButton):
    """A push button whose text is cut with "…" to its width (the full text in ``full`` and the tooltip), so it
    shrinks with the settings panel and is never narrower than what it shows (Q33.2, R2-2)."""

    PADDING = 24  # (The style's margins around a push button's text.)

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.full = text

    def set_full_text(self, text: str) -> None:
        self.full = text
        self._elide()

    def resizeEvent(self, a0: QResizeEvent | None) -> None:
        super().resizeEvent(a0)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight,
                                              max(0, self.width() - self.PADDING))
        if shown != self.text():
            self.setText(shown)


class TxySourceRow(QWidget):
    """``TXY: [the plot's list ▸]`` and one line under it: the profile HeLab converts with, and a plate
    suggestion when there is one, with the Keep box at its end. The button opens the TXY list editor
    (``helab/views/txy_list.py``, Q53.2) with "As the folder's tab" at the top; ``changed`` is called with the
    list chosen (None: as the tab); ``kept`` with Keep's state. ``context`` gives the conversion profile's
    tag and the tab's list in short, for the button and the editor."""

    def __init__(self, entries: Optional[Sequence[str]], changed: Callable[[Optional[Entries]], None],
                 context: Callable[[], tuple[str, str]] = lambda: ("", ""), parent: Optional[QWidget] = None,
                 keep: bool = True, kept: Optional[Callable[[bool], None]] = None) -> None:
        super().__init__(parent)
        self._changed = changed
        self._context = context
        self.entries: Optional[Entries] = tuple(entries) if entries is not None else None
        self.ask_list: AskList = ask_txy_list  # (A test answers in its place.)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("TXY:"))
        self.button = identify(ElidedButton(""), "txy_source", "TXY priority",
                               "Which TXY this plot's data is made of, in order: each shot from the first entry with "
                               "a usable TXY (External: the MATLAB converter's d_txy_forc; HeLab's "
                               "d_txy_helab_<tag>). As the folder's tab: what its tab and Live read.")
        self.button.setToolTip(self.button.accessibleDescription())
        self.button.setMinimumWidth(40)  # (It shrinks with the panel, not set its width: Q33.2.)
        self.button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.button.clicked.connect(self.edit)
        row.addWidget(self.button, 1)
        layout.addLayout(row)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        self.note = identify(ElidedLabel(), "txy_note")  # (One line that never widens the panel: Q33.2.)
        line.addWidget(self.note, 1)
        # "Keep" for short (the row shrinks with the panel); its name and tooltip say it in full.
        self.keep_box = identify(QCheckBox("Keep"), "txy_keep", "Keep this plot's TXY choice",
                                 "Keep this plot's TXY choice: save it with its presets, arrangements and the "
                                 "plots reopened at start. Off (for tweaking and exploring): they start as the "
                                 "folder's tab.")
        self.keep_box.setToolTip(self.keep_box.accessibleDescription())
        self.keep_box.setChecked(keep)
        self.keep_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if kept is not None:
            self.keep_box.toggled.connect(kept)
        line.addWidget(self.keep_box)
        layout.addLayout(line)
        self.set_entries(self.entries)

    def set_entries(self, entries: Optional[Sequence[str]]) -> None:
        """Show the plot's list (None: as the tab)."""
        self.entries = tuple(entries) if entries is not None else None
        tag, tab = self._context()
        text = (f"As the folder's tab ({tab})" if self.entries is None and tab
                else list_summary(self.entries, tag, "As the folder's tab"))
        self.button.set_full_text(text)
        self.button.setToolTip(f"{text}\n\n{self.button.accessibleDescription()}")

    def edit(self) -> None:
        """The list editor; a change is the plot's (``changed``)."""
        tag, tab = self._context()
        accepted, entries = self.ask_list(self, "TXY for this plot", "This plot's data, in this order (each shot "
                                          "from the first entry with a usable TXY):", self.entries, tag,
                                          known_names(), "As the folder's tab", tab)
        if accepted and (entries is None or entries) and entries != self.entries:
            self.set_entries(entries)
            self._changed(self.entries)

    def show_profile(self, view: DatasetView, profile_name: str) -> None:
        """One line: the profile, the data's TXY and a plate suggestion (detail in the tooltip)."""
        suggestion = plate_note(view, profile_name)
        self.note.setText(f"HeLab converts with {profile_name}" + (f" · {suggestion}" if suggestion else ""))
        self.note.setToolTip(f"{view.txy_text()}\nHeLab's TXY are read by their profile's tag (the profiles in "
                             f"the list; Conversion profile: the one HeLab converts with, {profile_name}; "
                             "Settings → TXY converter)."
                             + (f"\nThe plate swap dates suggest {suggestion}; it is not applied: choose it in "
                                "Settings → TXY converter to convert with it." if suggestion else ""))
