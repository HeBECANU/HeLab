"""A folder chosen with Qt's own dialog, never the OS's (Q~4, Tony 2026-11-10; GT-9 of the GUI-thread audit).

The native file dialog runs the OS's in HeLab's GUI thread, and its sidebar can freeze on a share that went away
(Windows' "Working on it…", a dead SMB mount in macOS's). Qt's own dialog lists folders on a thread of its own
(``QFileSystemModel``) and starts in a local folder (the home folder), so HeLab stays responsive while a share is
slow. Used for Load Scripts… and Settings' folder choices; the converter's profile import and export keep the
native dialog (local files).
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import QFileDialog, QWidget

OPTIONS = QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog


def start_folder() -> str:
    """Where the dialog opens: the home folder (local; a share's folder could be slow to list)."""
    return os.path.expanduser("~")


def choose_folder(parent: QWidget | None, title: str) -> str:
    """A folder the user chose with Qt's dialog, or "" if cancelled."""
    return QFileDialog.getExistingDirectory(parent, title, start_folder(), OPTIONS)


__all__ = ["OPTIONS", "choose_folder", "start_folder"]
