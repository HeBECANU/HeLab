"""A local folder or file shown in the system's file manager (or its default app), never waited for.

``QDesktopServices.openUrl`` runs the shell's open (``ShellExecuteW`` on Windows, ``NSWorkspace`` on macOS)
synchronously on HeLab's GUI thread, and that can stall on a share that went away (GT-9). A detached process
does the same instead: ``open`` on macOS, ``explorer`` on Windows, ``xdg-open`` elsewhere. Web addresses still
go through ``openUrl`` (a browser, not a folder).
"""
from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtCore import QProcess


def open_command(path: str) -> tuple[str, list[str]]:
    """The program and arguments that open ``path`` (a folder in the file manager, a file in its app)."""
    if sys.platform == "darwin":
        return "open", [path]
    if sys.platform == "win32":
        return "explorer", [os.path.normpath(path)]
    return "xdg-open", [path]


def launch(program: str, arguments: list[str]) -> bool:
    """Start ``program`` detached (never waited for); whether it started. Tests replace it."""
    return bool(QProcess.startDetached(program, arguments)[0])


def show(path: str) -> bool:
    """Open ``path`` in the file manager (a file: in its default app), without waiting; whether it started. An
    empty path opens nothing (``normpath("")`` is HeLab's working folder; ``openUrl`` of it did nothing: GT-28)."""
    if not path.strip():
        return False
    program, arguments = open_command(path)
    started = launch(program, arguments)
    if not started:
        logging.warning("Couldn't open %s: %s didn't start", path, program)
    return started


__all__ = ["launch", "open_command", "show"]
