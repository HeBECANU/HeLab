"""Q~4 (Tony, 2026-11-10; GT-9): Load Scripts… and Settings' folder choices (temp folder, cache folder) use Qt's
own folder dialog from the home folder, never the OS's, whose sidebar can freeze HeLab on a dead share. The
converter's profile import and export keep the native one."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtWidgets import QFileDialog

from helab.views import folder_dialog

ROOT = Path(__file__).resolve().parents[1]


def test_the_folder_is_chosen_with_qts_dialog_from_home(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[Any, ...]] = []

    def get(*args: Any) -> str:
        asked.append(args)
        return "/chosen"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(get))
    assert folder_dialog.choose_folder(None, "Choose the temp folder") == "/chosen"
    [(parent, title, start, options)] = asked
    assert parent is None and title == "Choose the temp folder" and start == os.path.expanduser("~")
    assert options & QFileDialog.Option.DontUseNativeDialog and options & QFileDialog.Option.ShowDirsOnly


@pytest.mark.parametrize("module,function", [
    ("helab/views/SettingsDialog.py", "browse_dir_temps"),
    ("helab/views/SettingsDialog.py", "change_cache_folder"),
    ("helab/views/plots/script_tree.py", "_on_load_directory"),
])
def test_load_scripts_and_settings_folders_use_it(module: str, function: str) -> None:
    tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
    [body] = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function]
    calls = {ast.unparse(node.func) for node in ast.walk(body) if isinstance(node, ast.Call)}
    assert "choose_folder" in calls and not any(call.startswith("QFileDialog.") for call in calls)


def test_the_converters_profile_import_and_export_stay_native() -> None:
    text = (ROOT / "helab/views/ConverterTab.py").read_text(encoding="utf-8")
    assert "QFileDialog.getOpenFileName" in text and "QFileDialog.getSaveFileName" in text
    assert "DontUseNativeDialog" not in text
