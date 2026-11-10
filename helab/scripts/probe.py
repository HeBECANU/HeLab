"""The try-import of a user script folder (Q49.3 (b)): run in a process of its own before HeLab imports
the folder on the GUI thread, so a folder whose import hangs or crashes is skipped instead of freezing or
killing HeLab.

    python -P -m helab.scripts.probe FOLDER RESPONSE_FILE      # a source run
    HeLab --helab-script-probe FOLDER RESPONSE_FILE            # the frozen app (helab/main.py's dispatch)

It imports the folder as the GUI does (``ScriptsManager().add_folder``: the same ``sys.path``, helper
modules, source-only loader and per-file errors), with an offscreen ``QApplication`` first so a script that
makes a Qt object at import behaves as in the app; without the ``offscreen`` platform plugin, none (said in
the ``ready`` line). The answer goes to ``RESPONSE_FILE`` as JSON lines, never stdout (a windowed frozen app
may have no standard streams): ``{"kind": "ready", "application": …}`` once it is about to import the
folder (the time limit counts from here, so the probe's own start doesn't), then ``{"kind": "done",
"loaded": …, "seconds": …, "reads": …}``: ``reads`` is what HeLab's own import would read of the folder again
(``scripts_manager.FolderReads``: its ``.py`` names, each file's size, time and SHA-256, never its bytes; null
when it couldn't be listed or holds too many files), so the GUI thread doesn't (GT-6). Then it ends at once (``os._exit``), so a script's atexit hook or thread
can't hold it open. A file that raises at import isn't a failure here: the manager keeps its error, and
HeLab's real import lists it. The GUI side: ``helab/views/plots/script_tree.py`` (``FolderProbes``).

Qt-free at import (``PURE`` in ``tests/test_headless_imports.py``): Qt is imported only in ``main``.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from typing import Any, List, Optional, TextIO

READY = "ready"
DONE = "done"
# The frozen app's argument (helab/main.py dispatches it before any GUI import).
FROZEN_ARGUMENT = "--helab-script-probe"
# The probe's QApplication's program name (never an empty argv: QtWebEngine needs one).
PROGRAM_NAME = "HeLab script probe"
# What the ``ready`` line says ran.
OFFSCREEN = "offscreen"
NO_APPLICATION = "none"
# The probe's QApplication, never deleted (see ``main``).
_KEPT: List[Optional[object]] = []


def command(folder: str, response: str) -> tuple[str, List[str]]:
    """The program and arguments that probe ``folder``, answering in ``response``: this executable with the
    frozen dispatch's argument, or this interpreter running this module (``-P``: no current folder on
    ``sys.path``, so a module there can't shadow HeLab's)."""
    if getattr(sys, "frozen", False):
        return sys.executable, [FROZEN_ARGUMENT, folder, response]
    return sys.executable, ["-P", "-m", "helab.scripts.probe", folder, response]


def _plugin_folders() -> List[str]:
    from PyQt6.QtCore import QCoreApplication, QLibraryInfo
    folders = [QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath), *QCoreApplication.libraryPaths()]
    folders += [entry for entry in os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep) if entry]
    return folders


def _application() -> tuple[Optional[object], str]:
    """An offscreen ``QApplication`` when its platform plugin is there (a missing one would abort the
    process, so it is looked for first), else none; what ran."""
    try:
        from PyQt6.QtWidgets import QApplication
        if not any(glob.glob(os.path.join(folder, "platforms", "*qoffscreen*")) for folder in _plugin_folders()):
            return None, f"{NO_APPLICATION} (no offscreen platform plugin)"
        os.environ["QT_QPA_PLATFORM"] = OFFSCREEN
        return QApplication.instance() or QApplication([PROGRAM_NAME]), OFFSCREEN
    except Exception as error:  # (Qt unusable here: the import is still worth testing.)
        return None, f"{NO_APPLICATION} ({type(error).__name__}: {error})"


def _say(handle: TextIO, **event: Any) -> None:
    handle.write(json.dumps(event) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def main(argv: List[str]) -> int:
    """Probe ``argv`` = [FOLDER, RESPONSE_FILE]. It never returns after answering (``os._exit(0)``); 2 for
    wrong arguments."""
    if len(argv) != 2:
        sys.stderr.write("usage: python -m helab.scripts.probe FOLDER RESPONSE_FILE\n")
        return 2
    folder, response = argv
    with open(response, "a", encoding="utf-8") as handle:
        application, ran = _application()
        from helab.scripts.scripts_manager import ScriptsManager
        _say(handle, kind=READY, application=ran, pid=os.getpid())
        started = time.monotonic()
        manager = ScriptsManager()
        loaded = manager.add_folder(folder)
        seconds = round(time.monotonic() - started, 3)
        reads = manager.folder_reads(folder) if loaded else None
        _say(handle, kind=DONE, loaded=loaded, seconds=seconds, reads=reads.to_json() if reads is not None else None)
    # Never torn down: ~QCoreApplication waits for the global QThreadPool, so a script that started an endless
    # task at import would hold the probe open after ``done`` (review FU-1). Kept referenced until ``os._exit``,
    # which ends the process at once.
    _KEPT.append(application)
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
