"""A user's script is in ``sys.modules`` only while its file runs (``scripts_manager._importing``): a
``@dataclass`` in a file with ``from __future__ import annotations`` loads, and afterwards nothing is
left under its name (``helab.scripts.dynamic.<file name>``) or what was there is back, whether the
file loaded or failed, across a reload, and with two folders holding files of the same name."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from helab.scripts import scripts_manager
from helab.scripts.scripts_manager import ScriptLoadError, ScriptsManager

# The file the manual's warning was about: a dataclass with plain-name fields, under the __future__
# import that makes every annotation a string the dataclass resolves through sys.modules.
SCRIPT = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PyQt6.QtWidgets import QLabel, QWidget

from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.scripts.base import DatasetAnalysis, ScriptMetadata


@dataclass(frozen=True)
class Found:
    count: int
    label: str = {label!r}


class Counts(DatasetAnalysis):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata({name!r}, "test", "Lab", __file__, "lab.counts", "1")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        return Found(context.view.event_count)

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return QLabel(str(result.data), parent)
'''
NAME = "helab.scripts.dynamic.counts.py"


def _write(folder: Path, name: str = "Counts", label: str = "first") -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / "counts.py"
    path.write_text(SCRIPT.format(name=name, label=label), encoding="utf-8")
    return path


def _found(manager: ScriptsManager, path: Path) -> object:
    script = manager.get_script(f"{path}::Counts")
    assert script is not None
    module = sys.modules.get(script.__module__)
    assert module is None
    found_class = getattr(script, "compute").__globals__["Found"]  # the file's own globals
    return found_class(3)


def test_a_dataclass_under_future_annotations_loads_and_leaves_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "scripts")
    manager = ScriptsManager()
    manager.load_directory(str(path.parent))
    assert manager.errors() == []
    assert repr(_found(manager, path)) == "Found(count=3, label='first')"
    assert NAME not in sys.modules and not scripts_manager._IMPORTING


def test_a_failed_load_restores_what_held_the_name(tmp_path: Path) -> None:
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "counts.py").write_text("from dataclasses import dataclass\nraise RuntimeError('broken')\n")
    earlier = ModuleType(NAME)
    sys.modules[NAME] = earlier
    try:
        manager = ScriptsManager()
        manager.load_directory(str(folder))
        (error,) = manager.errors()
        assert "broken" in error.message
        assert sys.modules.get(NAME) is earlier
    finally:
        sys.modules.pop(NAME, None)
    assert not scripts_manager._IMPORTING


def test_a_reload_runs_the_new_file_and_leaves_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "scripts", label="first")
    manager = ScriptsManager()
    manager.load_directory(str(path.parent))
    _write(tmp_path / "scripts", label="second")
    assert manager.reload() == [scripts_manager._normal(str(path.parent))]
    assert manager.errors() == []
    assert repr(_found(manager, path)) == "Found(count=3, label='second')"
    assert NAME not in sys.modules


def test_two_folders_with_the_same_file_name_keep_their_own_code(tmp_path: Path) -> None:
    first = _write(tmp_path / "one", name="One", label="one")
    second = _write(tmp_path / "two", name="Two", label="two")
    manager = ScriptsManager()
    manager.load_directory(str(first.parent))
    manager.load_directory(str(second.parent))
    assert manager.errors() == []
    assert repr(_found(manager, first)) == "Found(count=3, label='one')"
    assert repr(_found(manager, second)) == "Found(count=3, label='two')"
    assert NAME not in sys.modules


def test_an_overlapping_load_of_one_name_is_refused_not_waited_for() -> None:
    module = ModuleType(NAME)
    with scripts_manager._importing(NAME, module):
        assert sys.modules[NAME] is module
        with pytest.raises(ScriptLoadError, match="already being loaded"):
            with scripts_manager._importing(NAME, ModuleType(NAME)):
                pass
        assert sys.modules[NAME] is module
    assert NAME not in sys.modules and not scripts_manager._IMPORTING
