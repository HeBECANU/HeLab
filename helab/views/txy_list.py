"""The TXY priority list control (Q53.2): one editor for Settings › TXY converter, right-click › TXY for this
folder… and each plot's TXY row.

A list of every entry a choice can name: "Conversion profile (m19v1)" (``Conversion``, the profile HeLab
converts with), "External (MATLAB converter)" (MATLAB's ``d_txy_forc``, Q53.1) and every built-in and user
profile by its tag. The ticked ones, in their order, are the list (drag to reorder, or Move up / Move down);
each shot takes the first entry with a usable TXY. A "follow" box at the top ("As Settings", "As the folder's
tab") makes the place follow the level above instead. A one-line summary says the list in short
("m23v1 › m19v1 › External"); OK needs a list of one entry or more, or the follow box.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from helab.utils import txy_sources
from helab.utils.accessible import identify, identify_buttons
from helab.utils.txy_sources import CONVERSION, EXTERNAL, Entries

_TOKEN = Qt.ItemDataRole.UserRole


def known_names() -> dict[str, str]:
    """Every known profile's tag → name: the built-ins, then the user's (a profile folder that can't be read
    gives none of theirs)."""
    from helab.convert.profile import BUILTIN_PROFILES, file_tag
    from helab.convert.user_profiles import ProfileLibrary
    from helab.utils.constants import profiles_folder
    try:
        user = ProfileLibrary(profiles_folder()).profiles()
    except OSError:
        user = {}
    names: dict[str, str] = {}
    for name, profile in (*BUILTIN_PROFILES.items(), *sorted(user.items())):
        names.setdefault(file_tag(profile), name)
    return names


def entry_text(token: str, conversion_tag: str, names: Mapping[str, str]) -> str:
    """An entry as the list names it."""
    if token == CONVERSION:
        return f"Conversion profile ({conversion_tag})" if conversion_tag else "Conversion profile"
    if token == EXTERNAL:
        return txy_sources.EXTERNAL_LABEL
    name = names.get(token)
    return f"{name} ({token})" if name else f"{token} (no profile known by this tag)"


def list_summary(entries: Optional[Sequence[str]], conversion_tag: str, follows: str = "") -> str:
    """A choice in short: the list, or what it follows ("As Settings (Conversion (m19v1) › External)")."""
    if entries is None:
        return follows
    return txy_sources.summary(entries, conversion_tag) if entries else "Nothing ticked"


class TxyListEditor(QWidget):
    """The list with its follow box, order buttons and summary. ``entries``: the list as saved (None:
    following, when ``follow`` names what); ``names``: every known profile's tag → name, in the order they
    are offered; ``follows``: what the follow box follows, in short, for the summary."""

    changed = pyqtSignal()

    def __init__(self, entries: Optional[Sequence[str]], conversion_tag: str, names: Mapping[str, str],
                 follow: str = "", follows: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.conversion_tag = conversion_tag
        self.names = dict(names)
        self.follows = follows
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.follow_box: Optional[QCheckBox] = None
        if follow:
            self.follow_box = identify(QCheckBox(follow), "txy_list_follow", follow,
                                       f"{follow}: this place reads what the level above reads ({follows}).")
            self.follow_box.setToolTip(self.follow_box.accessibleDescription())
            self.follow_box.setChecked(entries is None)
            self.follow_box.toggled.connect(self._follow_changed)
            layout.addWidget(self.follow_box)
        self.list = identify(QListWidget(), "txy_list", "TXY priority",
                             "Ticked entries, in order: each shot takes the first with a usable TXY. Drag to "
                             "reorder.")
        self.list.setToolTip(self.list.accessibleDescription())
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.up_button = identify(QPushButton("Move up"), "txy_list_up", "Move up",
                                  "Move the selected entry before the one above it")
        self.down_button = identify(QPushButton("Move down"), "txy_list_down", "Move down",
                                    "Move the selected entry after the one below it")
        self.up_button.clicked.connect(lambda: self.move_entry(-1))
        self.down_button.clicked.connect(lambda: self.move_entry(1))
        buttons.addWidget(self.up_button)
        buttons.addWidget(self.down_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.summary = identify(QLabel(""), "txy_list_summary")
        layout.addWidget(self.summary)
        self._fill(entries)
        self.list.itemChanged.connect(lambda _: self._changed())
        model = self.list.model()
        if model is not None:  # (A drag that reorders.)
            model.rowsMoved.connect(lambda *_: self._changed())
        self._follow_changed()

    def _fill(self, entries: Optional[Sequence[str]]) -> None:
        ticked = list(entries or ())
        offered = [CONVERSION, EXTERNAL, *self.names]
        self.list.blockSignals(True)
        for token in [*ticked, *(token for token in offered if token not in ticked)]:
            item = QListWidgetItem(entry_text(token, self.conversion_tag, self.names))
            item.setData(_TOKEN, token)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
            item.setCheckState(Qt.CheckState.Checked if token in ticked else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def following(self) -> bool:
        return self.follow_box is not None and self.follow_box.isChecked()

    def ticked(self) -> Entries:
        """The ticked entries, in their order."""
        items = (self.list.item(row) for row in range(self.list.count()))
        return tuple(str(item.data(_TOKEN)) for item in items
                     if item is not None and item.checkState() == Qt.CheckState.Checked)

    def entries(self) -> Optional[Entries]:
        """The list chosen; None while following."""
        return None if self.following() else self.ticked()

    def valid(self) -> bool:
        return self.following() or bool(self.ticked())

    def set_ticked(self, tokens: Sequence[str]) -> None:
        """Tick exactly ``tokens``, in that order (the rest after them, unticked)."""
        self.list.clear()
        self._fill(tokens)
        self._changed()

    def move_entry(self, step: int) -> None:
        row = self.list.currentRow()
        to = row + step
        if row < 0 or not 0 <= to < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(to, item)
        self.list.setCurrentRow(to)
        self._changed()

    def _follow_changed(self) -> None:
        following = self.following()
        for widget in (self.list, self.up_button, self.down_button):
            widget.setEnabled(not following)
        self._changed()

    def _changed(self) -> None:
        self.summary.setText(list_summary(self.entries(), self.conversion_tag, self.follows))
        self.changed.emit()


class TxyListDialog(QDialog):
    """The editor in a small dialog with OK (only while ``valid``) and Cancel."""

    def __init__(self, title: str, text: str, entries: Optional[Sequence[str]], conversion_tag: str,
                 names: Mapping[str, str], follow: str = "", follows: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        if text:
            label = QLabel(text)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.editor = TxyListEditor(entries, conversion_tag, names, follow, follows, self)
        layout.addWidget(self.editor, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        identify_buttons(self.buttons, "txy_list")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.editor.changed.connect(self._valid_changed)
        self._valid_changed()

    def _valid_changed(self) -> None:
        button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if button is not None:
            button.setEnabled(self.editor.valid())


# (accepted, the list: None to follow.) Callers keep it as an attribute, so a test answers in its place.
AskList = Callable[..., "tuple[bool, Optional[Entries]]"]


def ask_txy_list(parent: Optional[QWidget], title: str, text: str, entries: Optional[Sequence[str]],
                 conversion_tag: str, names: Mapping[str, str], follow: str = "",
                 follows: str = "") -> tuple[bool, Optional[Entries]]:
    """Ask for a list in the dialog (modal, as the item pickers it replaces were)."""
    dialog = TxyListDialog(title, text, entries, conversion_tag, names, follow, follows, parent)
    try:
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return accepted, dialog.editor.entries() if accepted else None
    finally:
        dialog.deleteLater()


__all__ = ["AskList", "TxyListDialog", "TxyListEditor", "ask_txy_list", "entry_text", "known_names", "list_summary"]
