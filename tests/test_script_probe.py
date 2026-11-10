"""Q49.3 (b): a user script folder is test-imported in a separate process (``helab.scripts.probe``) before
HeLab imports it on the GUI thread (``script_tree.FolderProbes``); a folder whose test import hangs or crashes
is skipped with the reason. Scripts are written into ``tmp_path``; no real data.

The probe really runs here (a subprocess per folder); the other live-scripts tests turn it off
(tests/test_live_scripts.py, ``no_probe``).
"""
from __future__ import annotations

import hashlib
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


# The time limit while a test expects a probe to pass, crash or exit: far above any import's time under CI
# load, so those tests wait for the probe's own answer, never the timer (Ground CI 41640562938: a 2 s limit
# expired while the no-plugin probe was still importing PyQt6.QtWidgets, before its crash).
LONG = 60.0
# The limit only a round expected to hang gets (``short``), so a hang is found quickly. Set after anything that
# must pass in the same test has answered, so no passing import ever races it.
SHORT = 2.0


@pytest.fixture(autouse=True)
def long_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script_tree, "PROBING", True)
    monkeypatch.setattr(script_tree, "PROBE_SECONDS", LONG)


def short(monkeypatch: pytest.MonkeyPatch, on: bool = True) -> None:
    """The short limit for a round expected to hang (``on`` False: back to the long one). ``FolderProbes``
    reads the limit at each poll, so it applies to a probe already running."""
    monkeypatch.setattr(script_tree, "PROBE_SECONDS", SHORT if on else LONG)


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
    ready, done, after = run_probe([program, *arguments], response)
    assert ready["kind"] == probe.READY and ready["application"] == probe.OFFSCREEN
    assert done["kind"] == probe.DONE and done["loaded"] is True
    missing = tmp_path / "missing.jsonl"
    assert run_probe([sys.executable, "-P", "-m", "helab.scripts.probe", str(tmp_path / "gone"), str(missing)],
                     missing)[1:] == [{"kind": probe.DONE, "loaded": False, "seconds": pytest.approx(0, abs=5)},
                                      {"kind": probe.READS, "reads": None}]  # (Nothing read: GT-6.)
    # What HeLab's own import would read again (GT-6): names, and each file's size, time and hash, no bytes; said
    # after ``done``, so never within the import's time limit (GT-27).
    assert after["kind"] == probe.READS and "reads" not in done
    reads = after["reads"]
    assert reads["names"] == sorted(path.name for path in folder.glob("*.py")) and "raises.py" in reads["names"]
    script = folder / "live.py"
    entry = reads["files"][os.path.normcase(str(script.resolve()))]
    assert entry == [script.stat().st_size, script.stat().st_mtime_ns, hashlib.sha256(script.read_bytes()).hexdigest()]
    assert all(len(entry) == 3 for entry in reads["files"].values())


def test_the_frozen_apps_dispatch_runs_the_probe_before_any_gui_import(tmp_path: Path) -> None:
    """``helab/main.py`` dispatches ``--helab-script-probe`` (the frozen app's command) before importing
    HeLab's GUI: the probed script finds no main window module imported."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "records.py").write_text(RECORDS)
    response = tmp_path / "response.jsonl"
    events = run_probe([sys.executable, "-P", str(ROOT / "helab" / "main.py"), probe.FROZEN_ARGUMENT, str(folder),
                        str(response)], response)
    assert [event["kind"] for event in events] == [probe.READY, probe.DONE, probe.READS]
    [record] = [json.loads(line) for line in (folder / "imported.jsonl").read_text().splitlines()]
    assert record["gui"] is False and record["pid"] == events[0]["pid"]


def hangs(folder: Path, how: str = "import time\ntime.sleep(120)\n") -> None:
    folder.mkdir()
    (folder / "hangs.py").write_text(how)


def test_a_remembered_folder_whose_import_hangs_is_skipped_at_start(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """At start each remembered folder is tested first; one that hangs isn't imported (never in this
    process), waits for Reload with the reason in the start note, whose tooltip says how it was checked; the
    good one loads; ``foldersRestored`` once both answered, the hung probe killed and its exit confirmed.
    (The short limit is set once the good folder's probe has ended: only the hung one meets it.)"""
    good, stuck = tmp_path / "good", tmp_path / "stuck"
    good.mkdir()
    write_script(good, "lab_probe_b", "one")
    hangs(stuck, "import json, os, time\nopen(os.path.join(os.path.dirname(__file__), 'pid'), 'w').write("
                 "str(os.getpid()))\ntime.sleep(120)\n")
    app_settings().setValue(SCRIPT_FOLDERS_SETTING, json.dumps([str(good), str(stuck)]))
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with qtbot.waitSignal(scripts.foldersRestored, timeout=120_000):
        qtbot.waitUntil(lambda: [item.folder for item in scripts._probes._running.values()] == [str(stuck)]
                        and (stuck / "pid").is_file(), timeout=60_000)
        short(monkeypatch)
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
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    short(monkeypatch)
    scripts.reload_scripts()
    assert scripts._probing and scripts.reload_button.text() == "Reload (checking)"
    scripts.reload_scripts()  # (Waits for the running round: never a second probe beside it.)
    assert scripts._pending == {str(tmp_path)} and len(scripts._probes._running) == 1
    qtbot.waitUntil(lambda: "didn't finish within 2 s" in instance._script_note, timeout=60_000)
    assert shown_tag(instance) == "old"
    qtbot.waitUntil(lambda: not scripts._probing and not scripts._pending, timeout=60_000)  # (The second round.)
    [line] = scripts.error_items()
    assert line.text(0).endswith(": didn't load: its import didn't finish within 2 s")
    short(monkeypatch, False)
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


def test_the_packaged_app_is_checked_to_probe_under_an_offscreen_application() -> None:
    """ci-build.yml runs the frozen app's probe on each OS after the build (the offscreen platform plugin
    collected, the dispatch before any GUI import), as the source tests can't."""
    text = (ROOT / ".github" / "workflows" / "ci-build.yml").read_text(encoding="utf-8")
    step = text[text.index("- name: Check the script folder probe in the packaged app"):]
    step = step[:step.index("\n      - name: ", 1)]
    assert '"--helab-script-probe"' in step and 'events[0]["application"] == "offscreen"' in step
    assert '== ["ready", "done", "reads"]' in step  # (The reads follow ``done``: GT-27.)
    assert 'seen == {"frozen": True, "gui": False}' in step and "if:" not in step.split("run:")[0]


# Run in the probe only (its QApplication's name), never in the test's process: an endless task on Qt's global
# thread pool, which ~QCoreApplication would wait for (review FU-1).
POOL_TASK = '''
import time
from PyQt6.QtCore import QCoreApplication, QRunnable, QThreadPool

class Forever(QRunnable):
    def run(self) -> None:
        time.sleep(120)

if QCoreApplication.applicationName() == "HeLab script probe":
    TASK = Forever()
    TASK.setAutoDelete(False)
    QThreadPool.globalInstance().start(TASK)
'''


def python_command(code: str) -> Any:
    """A ``probe.command`` replacement: this interpreter running ``code`` with the folder and response as
    ``sys.argv[1:3]``."""
    return lambda folder, response: (sys.executable, ["-c", code, folder, response])


def test_a_script_leaving_a_thread_pool_task_running_doesnt_hold_its_probe(
        qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """FU-1: a script that starts an endless task on Qt's global thread pool at import: the probe answers
    ``done`` and exits at once (its QApplication is never torn down, which would wait for the task), so the
    folder loads within the limit and no probe had to be ended."""
    write_script(tmp_path, "lab_probe_e", "one")
    (tmp_path / "pool.py").write_text(POOL_TASK)
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with caplog.at_level(logging.INFO):
        scripts.add_folder(str(tmp_path))
        qtbot.waitUntil(lambda: "Lab" in scripts.groups, timeout=30_000)
    assert not scripts._probes.busy() and scripts.reload_button.text() == "Reload"
    assert not any("didn't exit" in record.getMessage() for record in caplog.records)


def test_a_probe_that_answers_done_but_doesnt_exit_is_ended_and_its_folder_loads(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """FU-1: whatever holds a probe open after ``done``, it is killed ``PROBE_EXIT_SECONDS`` later and its
    folder still passes (it finished), so no round waits on it."""
    monkeypatch.setattr(script_tree, "PROBE_EXIT_SECONDS", 1.0)
    monkeypatch.setattr(probe, "command", python_command(
        "import json, sys, time\n"
        "with open(sys.argv[2], 'a') as handle:\n"
        "    handle.write(json.dumps({'kind': 'ready', 'application': 'offscreen'}) + '\\n')\n"
        "    handle.write(json.dumps({'kind': 'done', 'loaded': True, 'seconds': 0}) + '\\n')\n"
        "time.sleep(120)\n"))
    write_script(tmp_path, "lab_probe_f", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with caplog.at_level(logging.WARNING):
        scripts.add_folder(str(tmp_path))
        qtbot.waitUntil(lambda: "Lab" in scripts.groups, timeout=30_000)
    assert scripts.error_items() == [] and not scripts._probes.busy()
    assert any("finished but its process didn't exit within 1 s" in record.getMessage() for record in caplog.records)


def test_without_the_offscreen_plugin_the_probe_runs_without_an_application(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """P3's fallback: no offscreen platform plugin, no QApplication (a missing plugin would abort the probe),
    said in ``ready`` and the log; a script making a widget at import then ends the probe and is skipped."""
    monkeypatch.setattr(probe, "_plugin_folders", lambda: [])
    assert probe._application() == (None, f"{probe.NO_APPLICATION} (no offscreen platform plugin)")
    monkeypatch.setattr(probe, "command", python_command(
        "import sys\nimport helab.scripts.probe as p\np._plugin_folders = lambda: []\nsys.exit(p.main(sys.argv[1:3]))\n"))
    folder = tmp_path / "widget"
    hangs(folder, "from PyQt6.QtWidgets import QLabel\nLABEL = QLabel('made at import')\n")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    with caplog.at_level(logging.INFO):
        scripts.add_folder(str(folder))
        qtbot.waitUntil(lambda: bool(scripts.error_items()), timeout=60_000)
    [line] = scripts.error_items()
    assert line.text(0).startswith("widget: didn't load: its import ")
    assert "crashed" in line.text(0) or "exit code" in line.text(0)
    assert any("QApplication: none (no offscreen platform plugin)" in record.getMessage() for record in caplog.records)


def test_a_probe_not_ready_within_the_start_limit_is_ended(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``PROBE_START_SECONDS``: a probe that never begins the folder's import (here it only sleeps) is killed
    and the folder skipped with its own reason."""
    monkeypatch.setattr(script_tree, "PROBE_START_SECONDS", 1.0)
    monkeypatch.setattr(probe, "command", python_command("import time\ntime.sleep(120)\n"))
    write_script(tmp_path, "lab_probe_g", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(tmp_path))
    qtbot.waitUntil(lambda: bool(scripts.error_items()), timeout=30_000)
    [line] = scripts.error_items()
    assert line.text(0).endswith(": didn't load: HeLab's test import didn't start within 1 s")
    assert "Lab" not in scripts.groups and not scripts._probes.busy()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_a_script_killing_its_process_by_a_signal_is_a_crash(qtbot: QtBot, tmp_path: Path) -> None:
    folder = tmp_path / "signal"
    hangs(folder, "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(folder))
    qtbot.waitUntil(lambda: bool(scripts.error_items()), timeout=60_000)
    [line] = scripts.error_items()
    assert line.text(0) == "signal: didn't load: its import crashed HeLab's test import"


def test_stop_kills_the_probes_and_answers_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    """At quit (``aboutToQuit``): running probes are killed, queued ones dropped, and no round answers."""
    from PyQt6.QtCore import QObject, QProcess
    owner = QObject()
    probes = script_tree.FolderProbes(owner)
    folders = []
    for name in ("one", "two", "three"):
        hangs(tmp_path / name, "import time\ntime.sleep(120)\n")
        folders.append(str(tmp_path / name))
    answered: List[Any] = []
    probes.probe(folders, answered.append)
    assert len(probes._running) == script_tree.PROBES_AT_ONCE and len(probes._queue) == 1
    qtbot.waitUntil(lambda: all(item.ready is not None for item in probes._running.values()), timeout=60_000)
    ended: List[Any] = []
    for item in probes._running.values():
        assert item.process is not None
        item.process.finished.connect(lambda _code, status: ended.append(status))
    probes.stop()
    qtbot.waitUntil(lambda: not probes.busy(), timeout=30_000)
    assert answered == [] and not probes._queue and not probes._rounds
    assert ended == [QProcess.ExitStatus.CrashExit] * script_tree.PROBES_AT_ONCE  # (Killed, their exits seen.)


def test_auto_reload_tests_the_folder_before_reloading_it(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reload when a script is saved goes through the probe too: a save that makes the import hang leaves
    the plot on its code and lists the folder; the next save that fixes it reloads."""
    window = new_window(qtbot, cache, windows)
    scripts = window.scripts
    write_script(tmp_path, "lab_probe_h", "old")
    scripts.add_folder(str(tmp_path))
    qtbot.waitUntil(lambda: "Lab" in scripts.groups, timeout=60_000)
    scripts.set_auto_reload(True)
    instance = open_plot(qtbot, window, cache)
    (tmp_path / "lab_probe_h.py").write_text("import time\ntime.sleep(120)\nTAG = 'hung'\n")
    short(monkeypatch)
    scripts._check_changes()  # (What the settle timer runs after a save.)
    assert scripts._probing and scripts.reload_button.text() == "Reload (checking)"
    qtbot.waitUntil(lambda: "didn't finish within 2 s" in instance._script_note, timeout=60_000)
    qtbot.waitUntil(lambda: not scripts._probing, timeout=30_000)
    [line] = scripts.error_items()
    assert line.text(0).endswith(": didn't load: its import didn't finish within 2 s")
    short(monkeypatch, False)
    write_script(tmp_path, "lab_probe_h", "fixed")
    scripts._check_changes()
    qtbot.waitUntil(lambda: instance.shown is not None and shown_tag(instance) == "fixed", timeout=60_000)
    assert scripts.error_items() == []
