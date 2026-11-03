"""Q49.3 (b): a user script folder is test-imported in a separate process (``helab.scripts.probe``) before
HeLab imports it on the GUI thread (``script_tree.FolderProbes``); a folder whose test import hangs or crashes
is skipped with the reason. Scripts are written into ``tmp_path``; no real data.

The probe really runs here (a subprocess per folder); the other live-scripts tests turn it off
(tests/test_live_scripts.py, ``no_probe``).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from pytestqt.qtbot import QtBot

from helab.scripts import probe
from helab.utils.folder_cache import FolderCache
from helab.utils.settings_defaults import SCRIPT_FOLDERS_SETTING
from helab.utils.settings_store import app_settings
from helab.views.plots import script_tree
from helab.views.plots.script_tree import PROBED_NOTE, TreePanelWidget, read_script_folders
from test_live_scripts import no_marker, open_plot, shown_tag, write_script  # noqa: F401
from test_presets_plots import (Window, Windows, cache, fresh_presets, new_window, no_disk_cache,  # noqa: F401
                                runner, windows)
from test_scripts_reload import restored_imports  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
# A script that records, at import, which process imported it and whether HeLab's GUI was imported there.
RECORDS = '''
import json, os, sys
with open(os.path.join(os.path.dirname(__file__), "imported.jsonl"), "a") as handle:
    handle.write(json.dumps({"pid": os.getpid(), "gui": "helab.views.HelabMainWindow" in sys.modules}) + "\\n")
'''


@pytest.fixture(autouse=True)
def short_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2 s limit (from the probe's ``ready``: its own start doesn't count), so a hang is found quickly."""
    monkeypatch.setattr(script_tree, "PROBING", True)
    monkeypatch.setattr(script_tree, "PROBE_SECONDS", 2.0)


def answers(response: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in response.read_text(encoding="utf-8").splitlines()]


def run_probe(argv: List[str], response: Path) -> List[Dict[str, Any]]:
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(ROOT), os.environ.get("PYTHONPATH"))))}
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=environment)
    assert done.returncode == 0, done.stderr
    return answers(response)


def test_the_probe_answers_ready_then_done_and_a_file_that_raises_isnt_its_failure(tmp_path: Path) -> None:
    """The probe imports the folder as the manager does: a file that raises (or exits) is that file's error,
    for HeLab's real import to list, so the probe still finishes; a script making a Qt widget at import
    works (an offscreen QApplication); a missing folder is done, not loaded."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    write_script(folder, "lab_probe_a", "one")
    (folder / "raises.py").write_text("raise ValueError('at import')\n")
    (folder / "exits.py").write_text("import sys\nsys.exit(4)\n")
    (folder / "widget.py").write_text("from PyQt6.QtWidgets import QLabel\nLABEL = QLabel('made at import')\n")
    response = tmp_path / "response.jsonl"
    program, arguments = probe.command(str(folder), str(response))
    assert arguments[:3] == ["-P", "-m", "helab.scripts.probe"]  # (A source run; the frozen app's is below.)
    ready, done = run_probe([program, *arguments], response)
    assert ready["kind"] == probe.READY and ready["application"] == probe.OFFSCREEN
    assert done["kind"] == probe.DONE and done["loaded"] is True
    missing = tmp_path / "missing.jsonl"
    assert run_probe([sys.executable, "-P", "-m", "helab.scripts.probe", str(tmp_path / "gone"), str(missing)],
                     missing)[1] == {"kind": probe.DONE, "loaded": False, "seconds": pytest.approx(0, abs=5)}


def test_the_frozen_apps_dispatch_runs_the_probe_before_any_gui_import(tmp_path: Path) -> None:
    """``helab/main.py`` dispatches ``--helab-script-probe`` (the frozen app's command) before importing
    HeLab's GUI: the probed script finds no main window module imported."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "records.py").write_text(RECORDS)
    response = tmp_path / "response.jsonl"
    events = run_probe([sys.executable, "-P", str(ROOT / "helab" / "main.py"), probe.FROZEN_ARGUMENT, str(folder),
                        str(response)], response)
    assert [event["kind"] for event in events] == [probe.READY, probe.DONE]
    [record] = [json.loads(line) for line in (folder / "imported.jsonl").read_text().splitlines()]
    assert record["gui"] is False and record["pid"] == events[0]["pid"]


def hangs(folder: Path, how: str = "import time\ntime.sleep(120)\n") -> None:
    folder.mkdir()
    (folder / "hangs.py").write_text(how)


def test_a_remembered_folder_whose_import_hangs_is_skipped_at_start(qtbot: QtBot, tmp_path: Path) -> None:
    """At start each remembered folder is tested first; one that hangs isn't imported (never in this
    process), waits for Reload with the reason in the start note, whose tooltip says how it was checked; the
    good one loads; ``foldersRestored`` once both answered, the hung probe killed and its exit confirmed."""
    good, stuck = tmp_path / "good", tmp_path / "stuck"
    good.mkdir()
    write_script(good, "lab_probe_b", "one")
    hangs(stuck, "import json, os, time\nopen(os.path.join(os.path.dirname(__file__), 'pid'), 'w').write("
                 "str(os.getpid()))\ntime.sleep(120)\n")
    app_settings().setValue(SCRIPT_FOLDERS_SETTING, json.dumps([str(good), str(stuck)]))
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with qtbot.waitSignal(scripts.foldersRestored, timeout=60_000):
        pass
    assert "Lab" in scripts.groups and scripts.script_manager.folders() == [str(good)]
    assert scripts._skipped == {str(stuck): "its import didn't finish within 2 s"}
    assert "not loaded at start (its import didn't finish within 2 s)" in scripts.start_note.text()
    assert PROBED_NOTE in scripts.start_note.toolTip()
    assert not scripts._probes.busy() and scripts.reload_button.text() == "Reload"
    pid = int((stuck / "pid").read_text())
    assert pid != os.getpid()
    if sys.platform != "win32":  # (Windows' os.kill would terminate, not ask.)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)  # (Killed, and its exit seen.)
    assert read_script_folders() == [str(good), str(stuck)]  # (Still remembered: Reload tries it again.)


def test_load_scripts_of_a_folder_that_crashes_at_import_lists_it_with_the_reason(
        qtbot: QtBot, tmp_path: Path) -> None:
    """Load Scripts… tests a new folder too: one whose import ends the process (``os._exit``) isn't
    imported; its row says why, its tooltip how it was checked."""
    folder = tmp_path / "crashes"
    hangs(folder, "import os\nos._exit(3)\n")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(folder))
    assert scripts.reload_button.text() == "Reload (checking)"
    assert "separate process" in scripts.reload_button.toolTip()
    qtbot.waitUntil(lambda: bool(scripts.error_items()), timeout=60_000)
    [line] = scripts.error_items()
    assert line.text(0) == "crashes: didn't load: its import stopped HeLab's test import (exit code 3)"
    assert PROBED_NOTE in line.toolTip(0) and "so it wasn't imported" in line.toolTip(0)
    assert read_script_folders() == [str(folder)] and scripts.reload_button.text() == "Reload"


def test_a_reload_that_would_hang_keeps_the_plots_code_until_it_is_fixed(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path) -> None:
    """A script edited to wait for input at import (the probe's stdin stays open, so ``input()`` waits as in
    a terminal-launched HeLab) doesn't reload: its plot keeps the code it has and says why. A reload asked
    while the test runs follows it in a round of its own; once fixed, the plot takes the new code."""
    window = new_window(qtbot, cache, windows)
    scripts = window.scripts
    write_script(tmp_path, "lab_probe_c", "old")
    scripts.add_folder(str(tmp_path))
    qtbot.waitUntil(lambda: "Lab" in scripts.groups, timeout=60_000)
    instance = open_plot(qtbot, window, cache)
    assert shown_tag(instance) == "old"
    (tmp_path / "waits.py").write_text("ANSWER = input('Which detector? ')\n")
    scripts.reload_scripts()
    assert scripts._probing and scripts.reload_button.text() == "Reload (checking)"
    scripts.reload_scripts()  # (Waits for the running round: never a second probe beside it.)
    assert scripts._pending == {str(tmp_path)} and len(scripts._probes._running) == 1
    qtbot.waitUntil(lambda: "didn't finish within 2 s" in instance._script_note, timeout=60_000)
    assert shown_tag(instance) == "old"
    qtbot.waitUntil(lambda: not scripts._probing and not scripts._pending, timeout=60_000)  # (The second round.)
    [line] = scripts.error_items()
    assert line.text(0).endswith(": didn't load: its import didn't finish within 2 s")
    (tmp_path / "waits.py").unlink()
    write_script(tmp_path, "lab_probe_c", "fixed")
    scripts.reload_scripts()
    qtbot.waitUntil(lambda: instance.shown is not None and shown_tag(instance) == "fixed", timeout=60_000)
    assert instance._script_note == "" and scripts.error_items() == []


def test_a_probe_that_cant_start_imports_the_folder_anyway(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Q49.3 P4: no probe (its program missing) must not stop every folder from loading: imported, logged."""
    monkeypatch.setattr(probe, "command", lambda folder, response: (str(tmp_path / "no-such-program"), []))
    write_script(tmp_path, "lab_probe_d", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with caplog.at_level(logging.WARNING):
        scripts.add_folder(str(tmp_path))
        qtbot.waitUntil(lambda: "Lab" in scripts.groups, timeout=60_000)
    assert any("test import couldn't start" in record.getMessage() for record in caplog.records)
    assert scripts.error_items() == []
