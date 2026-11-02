"""Live scripts in the Scripts panel (helab/views/plots/script_tree.py) and their open plots
(``AnalysisInstance.adopt_script``, ``keep_script``): Reload, remembered folders, auto-reload, load
errors, and plots rerunning on the new code with their settings, or keeping the old code. Scripts
are written into ``tmp_path``; no real data (datasets are made in memory).

The manager's reload alone: tests/test_scripts_reload.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, List, Optional

import pytest
from PyQt6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from helab.analysis.dataset_view import view_of
from helab.scripts.base import DatasetAnalysis
from helab.utils.folder_cache import FolderCache
from helab.utils.settings_defaults import SCRIPT_AUTO_RELOAD_SETTING, SCRIPT_FOLDERS_SETTING, read_setting
from helab.utils.settings_store import app_settings
from helab.views.plots.instance import AnalysisInstance
from helab.views.plots.script_tree import TreePanelWidget, read_script_folders
from test_presets_plots import (Window, Windows, cache, dataset, folder, fresh_presets, new_window,  # noqa: F401
                                      no_disk_cache, runner, set_values, windows)
from test_scripts_reload import restored_imports  # noqa: F401

HEADER = '''
from typing import Any, List, Optional
from PyQt6.QtWidgets import QLabel, QWidget
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
'''

# A script with three settings; its result names its helper's TAG, so a test sees which code ran.
SCRIPT = HEADER + '''
import {helper}

class Live(DatasetAnalysis):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata("{name}", "test", "Lab", __file__, "lab.live", "{version}")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def parameters(self, action_name: str) -> List[ParameterSpec]:
        return [{specs}]

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        {wait}return ({helper}.TAG, dict(context.parameters))

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return QLabel(str(result.data), parent)
'''
SPECS = ('ParameterSpec("bins", "Bins", "int", 10, (1, 100)), ParameterSpec("scale", "Scale", "float", 1.0), '
         'ParameterSpec("mode", "Mode", "choice", "a", choices=("a", "b"))')
# The edited script: Scale removed, Mode now a number, Extra new.
EDITED = ('ParameterSpec("bins", "Bins", "int", 10, (1, 100)), ParameterSpec("mode", "Mode", "int", 0, (0, 9)), '
          'ParameterSpec("extra", "Extra", "bool", True)')


def write_script(folder_: Path, helper: str, tag: str, *, specs: str = SPECS, name: str = "Live",
                 version: str = "1", wait: str = "") -> None:
    (folder_ / f"{helper}.py").write_text(f"import threading\nTAG = {tag!r}\nGATE = threading.Event()\n")
    (folder_ / "live.py").write_text(SCRIPT.format(helper=helper, specs=specs, name=name, version=version,
                                                   wait=wait))


def open_plot(qtbot: QtBot, window: Window, cache: FolderCache) -> AnalysisInstance:
    """A plot of the folder's ``Live`` script on three shots, once it has drawn."""
    scripts = window.scripts
    window.view = view_of(dataset("run", range(1, 4)), cache.root_of(folder("run")))
    (metadata,) = scripts.script_manager.get_scripts_in_group("Lab")
    script_class = scripts.script_manager.get_script(metadata.script_id)
    assert script_class is not None
    script = script_class()
    assert isinstance(script, DatasetAnalysis)
    instance = scripts.run_analysis(metadata, script, "Plot")
    assert instance is not None
    qtbot.waitUntil(lambda: instance.shown is not None, timeout=10_000)
    return instance


def shown_tag(instance: AnalysisInstance) -> Any:
    assert instance.shown is not None
    return instance.shown.data[0]


def test_reload_reruns_an_open_plot_on_the_new_code_keeping_its_settings(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path) -> None:
    window = new_window(qtbot, cache, windows)
    write_script(tmp_path, "lab_live_a", "old")
    window.scripts.add_folder(str(tmp_path))
    instance = open_plot(qtbot, window, cache)
    assert shown_tag(instance) == "old"
    set_values(instance, {"bins": 5, "scale": 2.5, "mode": "b"})
    dock, number, old_script = instance.dock_widget, instance.instance_id, instance.script
    write_script(tmp_path, "lab_live_a", "new", specs=EDITED, name="Live, edited")
    window.scripts.reload_scripts()
    qtbot.waitUntil(lambda: instance.shown is not None and shown_tag(instance) == "new", timeout=10_000)
    assert instance.script is not old_script and instance.name == "Live, edited"
    assert instance.dock_widget is dock and instance.instance_id == number
    assert dock is not None and dock.windowTitle() == f"Live, edited ({number})"
    # Bins kept; Mode retyped and Extra new: at their defaults; Scale gone.
    assert instance.values() == {"bins": 5, "mode": 0, "extra": True}
    assert instance.shown is not None and instance.shown.data[1] == {"bins": 5, "mode": 0, "extra": True}
    assert instance.presets is not None
    note = instance.presets.note.text()
    assert note.startswith("Reloaded · ⚠ 3 settings at the script's defaults: Mode")
    assert "scale: not a setting of this script now" in instance.presets.note.toolTip()
    assert "another copy" not in instance.presets.note.toolTip()
    assert any(text.startswith("Reloaded 1 script folder · 1 plot rerun") for text in window.notices)


def test_a_script_that_fails_to_reload_leaves_its_plot_on_the_old_code(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path) -> None:
    window = new_window(qtbot, cache, windows)
    write_script(tmp_path, "lab_live_b", "old")
    window.scripts.add_folder(str(tmp_path))
    instance = open_plot(qtbot, window, cache)
    old_script, shown = instance.script, instance.shown
    (tmp_path / "live.py").write_text("def broken(:\n")
    window.scripts.reload_scripts()
    assert instance.script is old_script and instance.shown is shown  # Its last result stays.
    assert instance._script_note.startswith("⚠ Script didn't reload (SyntaxError: ")
    assert "still running the code loaded at" in instance.status_label.text()
    dock = instance.dock_widget
    assert dock is not None and str(dock.property("plotError")).startswith("⚠ Script didn't reload")
    (line,) = window.scripts.error_items()
    assert line.text(0).startswith("live.py: SyntaxError: ") and "Traceback" in line.toolTip(0)
    # Rerun runs the code it has.
    instance.run()
    qtbot.waitUntil(lambda: instance.shown is not shown and instance.shown is not None, timeout=10_000)
    assert shown_tag(instance) == "old"
    # Fixed: the next reload gives it the new code, and the error goes.
    write_script(tmp_path, "lab_live_b", "fixed")
    window.scripts.reload_scripts()
    qtbot.waitUntil(lambda: shown_tag(instance) == "fixed", timeout=10_000)
    assert instance._script_note == "" and window.scripts.error_items() == []


def test_a_vanished_class_or_a_removed_folder_keeps_the_old_code(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path) -> None:
    window = new_window(qtbot, cache, windows)
    write_script(tmp_path, "lab_live_c", "old")
    window.scripts.add_folder(str(tmp_path))
    instance = open_plot(qtbot, window, cache)
    (tmp_path / "live.py").write_text((tmp_path / "live.py").read_text().replace('"lab.live"', '"lab.other"'))
    window.scripts.reload_scripts()
    assert "(its class is gone from its folder)" in instance._script_note
    window.scripts.remove_folder(str(tmp_path))
    assert "(its folder was removed from the Scripts list)" in instance._script_note
    assert window.scripts.script_manager.folders() == [] and read_script_folders() == []
    assert "Lab" not in window.scripts.groups


def test_a_reload_waits_for_a_run_of_its_scripts_on_the_worker_thread(
        qtbot: QtBot, cache: FolderCache, windows: Windows, tmp_path: Path) -> None:
    """CoCo: a reload never runs while a compute of that script is on the worker thread; this one
    ignores cancellation, so the reload waits until its compute returns."""
    window = new_window(qtbot, cache, windows)
    write_script(tmp_path, "lab_live_d", "old", wait="lab_live_d.GATE.wait(30)\n        ")
    window.scripts.add_folder(str(tmp_path))
    gate = sys.modules["lab_live_d"].GATE
    gate.set()
    instance = open_plot(qtbot, window, cache)
    gate.clear()
    instance.run()
    qtbot.waitUntil(lambda: bool(instance.runner.in_flight()), timeout=10_000)
    old_class = type(instance.script)
    write_script(tmp_path, "lab_live_d", "new")
    window.scripts.reload_scripts()
    assert window.scripts.reload_button.text() == "Reload (waiting)"
    assert window.scripts.script_manager.get_script(f"{tmp_path / 'live.py'}::Live") is old_class  # Not yet.
    gate.set()  # Its compute returns (as cancelled): the reload goes on.
    qtbot.waitUntil(lambda: instance.shown is not None and shown_tag(instance) == "new", timeout=10_000)
    assert window.scripts.reload_button.text() == "Reload"


def test_folders_are_remembered_restored_and_removed(qtbot: QtBot, tmp_path: Path) -> None:
    first, missing = tmp_path / "first", tmp_path / "missing"
    first.mkdir()
    write_script(first, "lab_live_e", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    assert not scripts.reload_button.isEnabled()
    scripts.add_folder(str(first))
    scripts.add_folder(str(missing))
    assert json.loads(read_setting(app_settings(), SCRIPT_FOLDERS_SETTING, typed=True)) == [str(first), str(missing)]
    assert scripts.reload_button.isEnabled()
    # At the next start: both listed, the missing one with its line.
    again = TreePanelWidget()
    qtbot.addWidget(again)
    assert again.script_manager.folders() == [str(first), str(missing)] and "Lab" in again.groups
    assert [item.text(0) for item in again.error_items()] == ["missing: folder not found"]
    again._fill_folders_menu()
    titles = [action.text() for action in again.folders_menu.actions()]
    assert str(first) in titles and str(missing) in titles and "Reload when a script is saved" in titles
    again.remove_folder(str(missing))
    assert read_script_folders() == [str(first)] and again.error_items() == []
    # An unreadable setting: none restored.
    app_settings().setValue(SCRIPT_FOLDERS_SETTING, "not json")
    assert read_script_folders() == []


def test_auto_reload_watches_only_the_script_folders_while_on(qtbot: QtBot, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    write_script(tmp_path, "lab_live_f", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(tmp_path))
    assert scripts.watched() == [] and scripts._watcher is None  # Off by default: no watcher at all.
    scripts.auto_reload_action.setChecked(True)
    assert read_setting(app_settings(), SCRIPT_AUTO_RELOAD_SETTING, typed=True) is True
    assert scripts.watched() == sorted([str(tmp_path), str(tmp_path / "lab_live_f.py"), str(tmp_path / "live.py")])
    reloaded: List[Optional[List[str]]] = []
    monkeypatch.setattr(scripts, "reload_scripts", lambda folders=None: reloaded.append(folders))
    scripts._check_changes()
    assert reloaded == []  # Nothing changed.
    (tmp_path / "notes.txt").write_text("not a script")
    scripts._check_changes()
    assert reloaded == []
    (tmp_path / "lab_live_f.py").write_text("TAG = 'two, longer'\n")
    scripts._check_changes()
    assert reloaded == [[str(tmp_path)]]
    # A file event starts the settle wait, after which it compares.
    scripts._changed(str(tmp_path / "live.py"))
    assert scripts._settle.isActive()
    # Restored at the next start; off again drops the watcher.
    again = TreePanelWidget()
    qtbot.addWidget(again)
    assert again.auto_reload_action.isChecked() and again.watched()
    again.set_auto_reload(False)
    assert again._watcher is None and again.watched() == []
    assert read_setting(app_settings(), SCRIPT_AUTO_RELOAD_SETTING, typed=True) is False


def test_a_load_error_shows_its_traceback_in_a_details_window(qtbot: QtBot, tmp_path: Path) -> None:
    (tmp_path / "raises.py").write_text("raise ValueError('lab script failed')\n")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(tmp_path))
    (line,) = scripts.error_items()
    assert line.text(0) == "raises.py: lab script failed"
    parent = line.parent()
    assert parent is not None and parent.text(0) == "⚠ 1 script file didn't load"
    # Whatever group is shown.
    scripts.group_selector.setCurrentText("DLD Front Panel Port")
    assert [item.text(0) for item in scripts.error_items()] == ["raises.py: lab script failed"]
    (error,) = scripts.script_manager.errors()
    box = scripts.show_error_details(error)
    assert isinstance(box, QMessageBox) and not box.isModal() and box.objectName() == "script_error_details"
    assert "ValueError: lab script failed" in box.detailedText()
    box.close()
    scripts._show_error_details(scripts.error_items()[0], 0)  # (A double-click; the tree was made again.)
    assert scripts._details is not None
    scripts._details.close()


def test_loading_a_loaded_folder_again_is_a_reload(qtbot: QtBot, tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    write_script(tmp_path, "lab_live_g", "one")
    scripts = TreePanelWidget()
    qtbot.addWidget(scripts)
    scripts.add_folder(str(tmp_path))
    called: List[Any] = []
    monkeypatch.setattr(scripts, "reload_scripts", lambda folders=None: called.append(folders))
    scripts.add_folder(str(tmp_path) + "/.")
    assert called == [[str(tmp_path)]]

