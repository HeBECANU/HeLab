"""Live scripts' reload (``ScriptsManager``, Qt-free): the user's folders are recorded and loaded
again with their helper modules, what failed is kept with its traceback, and HeLab's and the
interpreter's modules are never unloaded. Scripts are written into ``tmp_path``.

The Scripts panel and open plots: tests/test_live_scripts.py.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Iterator

import pytest

from helab.scripts.scripts_manager import ScriptsManager
from test_scripts_folder import analysis, write

# A script whose compute returns its helper's VALUE (the helper's name is given, unique per test:
# Python's module names are one namespace).
USES_HELPER = '''
import {helper}

class Uses({base}):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata("Uses", "test", "Lab", __file__, "lab.uses", "1")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        return {helper}.VALUE

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return QLabel(str(result.data), parent)
'''


@pytest.fixture(autouse=True)
def restored_imports() -> Iterator[None]:
    """sys.path and sys.modules as they were: a test's helper modules and folders don't outlive it."""
    path, modules = list(sys.path), set(sys.modules)
    yield
    sys.path[:] = path
    for name in set(sys.modules) - modules:
        del sys.modules[name]


def uses(folder: Path, helper: str, base: str = "DatasetAnalysis") -> Path:
    return write(folder, "uses.py", USES_HELPER.format(helper=helper, base=base))


def value_of(manager: ScriptsManager, folder: Path) -> object:
    script_class = manager.get_script(f"{folder / 'uses.py'}::Uses")
    assert script_class is not None
    return script_class().compute("Plot", None)  # type: ignore[attr-defined]


def test_a_helper_beside_a_script_is_imported_and_reloaded(tmp_path: Path) -> None:
    (tmp_path / "lab_helper_a.py").write_text("VALUE = 1\n")
    uses(tmp_path, "lab_helper_a")
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    # The helper (no script in it) isn't a failure, as a stray file without scripts is.
    write(tmp_path, "stray.py", "VALUE = 0\n", header="")
    manager.load_directory(str(tmp_path))
    assert [Path(error.path).name for error in manager.errors()] == ["stray.py"]
    assert value_of(manager, tmp_path) == 1
    assert manager.helper_modules(str(tmp_path)) == {"lab_helper_a": str(tmp_path / "lab_helper_a.py")}
    assert str(tmp_path) in sys.path
    # Same size, most likely within the same second: Python's .pyc check would keep the old code.
    (tmp_path / "lab_helper_a.py").write_text("VALUE = 2\n")
    assert manager.reload() == [str(tmp_path)]
    assert value_of(manager, tmp_path) == 2  # The helper imported fresh, from its source.
    assert not (tmp_path / "__pycache__").exists()  # Nothing written into the user's folder.


def test_a_helper_package_and_its_submodules_reload(tmp_path: Path) -> None:
    package = tmp_path / "lab_pkg_b"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "inner.py").write_text("VALUE = 'one'\n")
    write(tmp_path, "uses.py", USES_HELPER.format(helper="lab_pkg_b.inner", base="DatasetAnalysis"))
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    assert value_of(manager, tmp_path) == "one"
    assert set(manager.helper_modules(str(tmp_path))) == {"lab_pkg_b", "lab_pkg_b.inner"}
    (package / "inner.py").write_text("VALUE = 'two'\n")
    manager.reload()
    assert value_of(manager, tmp_path) == "two"
    # Its files count for auto-reload too.
    assert str(package / "inner.py") in manager.watched_files(str(tmp_path))


def test_a_helper_imported_later_in_compute_is_found_and_reloaded(tmp_path: Path) -> None:
    (tmp_path / "lab_helper_c.py").write_text("VALUE = 3\n")
    write(tmp_path, "uses.py", USES_HELPER.replace("import {helper}\n", "").replace(
        "return {helper}.VALUE", "import {helper}\n        return {helper}.VALUE").format(
        helper="lab_helper_c", base="DatasetAnalysis"))
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    assert manager.helper_modules(str(tmp_path)) == {}
    assert value_of(manager, tmp_path) == 3  # Imported now, from the folder on sys.path.
    assert "lab_helper_c" in manager.helper_modules(str(tmp_path))
    (tmp_path / "lab_helper_c.py").write_text("VALUE = 4\n")
    manager.reload()
    assert "lab_helper_c" not in sys.modules
    assert value_of(manager, tmp_path) == 4


def test_helpers_change_the_scripts_hash(tmp_path: Path) -> None:
    """D1: a folder whose scripts import helpers records each script's hash with the helpers'."""
    helper = tmp_path / "lab_helper_d.py"
    helper.write_text("VALUE = 1\n")
    script = uses(tmp_path, "lab_helper_d")
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    (metadata,) = manager.get_scripts_in_group("Lab")
    plain = hashlib.sha256(script.read_bytes()).hexdigest()
    folded = hashlib.sha256("\n".join(
        [plain, f"lab_helper_d.py:{hashlib.sha256(helper.read_bytes()).hexdigest()}"]).encode()).hexdigest()
    assert metadata.file_hash == folded != plain
    helper.write_text("VALUE = 2\n")
    manager.reload()
    (metadata,) = manager.get_scripts_in_group("Lab")
    assert metadata.file_hash not in (folded, plain)


def test_heLabs_and_the_interpreters_modules_are_never_unloaded(tmp_path: Path) -> None:
    """A script folder holding HeLab's own files or a copy of the standard library's: a reload never
    unloads those modules (they live under HeLab's package and the interpreter's folders)."""
    import json
    import helab.scripts.base as base
    manager = ScriptsManager()
    for module in (base, json):
        assert module.__file__ is not None
        folder = str(Path(module.__file__).parent)
        assert module.__name__ not in manager.helper_modules(folder)
    write(tmp_path, "counts.py", analysis())
    manager.load_directory(str(tmp_path))
    manager.reload()
    assert sys.modules["helab.scripts.base"] is base and sys.modules["json"] is json


def test_errors_are_kept_with_their_traceback_and_cleared_on_a_good_reload(tmp_path: Path) -> None:
    write(tmp_path, "good.py", analysis("Good", "Good"))
    write(tmp_path, "syntax.py", "def broken(:\n", header="")
    write(tmp_path, "raises.py", "raise ValueError('lab script failed')\n", header="")
    write(tmp_path, "exits.py", "import sys\nsys.exit(3)\n", header="")
    write(tmp_path, "empty.py", "VALUE = 1\n", header="")
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    errors = {Path(error.path).name: error for error in manager.errors()}
    assert sorted(errors) == ["empty.py", "exits.py", "raises.py", "syntax.py"]
    assert errors["syntax.py"].line().startswith("syntax.py: SyntaxError: ") and "line 1" in errors["syntax.py"].message
    assert errors["raises.py"].message == "lab script failed"
    assert "Traceback" in errors["raises.py"].details and "ValueError: lab script failed" in errors["raises.py"].details
    assert errors["exits.py"].message == "SystemExit(3)"
    assert errors["empty.py"].message == "No HelabAnalysisScript subclass found"
    for name in ("syntax.py", "raises.py", "exits.py", "empty.py"):
        (tmp_path / name).unlink()
    manager.reload()
    assert manager.errors() == []
    assert [metadata.name for metadata in manager.get_scripts_in_group("Lab")] == ["Good"]


def test_a_missing_folder_is_kept_with_an_error_and_loads_once_back(tmp_path: Path) -> None:
    folder = tmp_path / "away"
    manager = ScriptsManager()
    assert manager.add_folder(str(folder)) is False
    assert manager.folders() == [str(folder)]
    (error,) = manager.errors()
    assert error.path == str(folder) and error.message == "folder not found"
    folder.mkdir()
    write(folder, "counts.py", analysis())
    assert manager.reload() == [str(folder)]
    assert manager.errors() == [] and manager.get_groups() == ["Lab"]
    # Gone again: its scripts go with it, and it stays listed.
    for file in folder.iterdir():
        file.unlink()
    folder.rmdir()
    assert manager.reload() == [] and manager.get_groups() == [] and manager.folders() == [str(folder)]


def test_removing_a_folder_forgets_its_scripts_helpers_and_path(tmp_path: Path) -> None:
    (tmp_path / "lab_helper_e.py").write_text("VALUE = 1\n")
    uses(tmp_path, "lab_helper_e")
    write(tmp_path, "broken.py", "raise ValueError('x')\n", header="")
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    assert manager.folder_of(f"{tmp_path / 'uses.py'}::Uses") == str(tmp_path)
    manager.remove_folder(str(tmp_path))
    assert manager.folders() == [] and manager.get_groups() == [] and manager.errors() == []
    assert "lab_helper_e" not in sys.modules and str(tmp_path) not in sys.path
    assert manager.folder_of(f"{tmp_path / 'uses.py'}::Uses") == ""


def test_reloading_one_folder_leaves_the_others(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "lab_helper_f.py").write_text("VALUE = 'first'\n")
    (second / "lab_helper_g.py").write_text("VALUE = 'second'\n")
    uses(first, "lab_helper_f")
    uses(second, "lab_helper_g")
    manager = ScriptsManager()
    manager.load_directory(str(first))
    manager.load_directory(str(second))
    second_class = manager.get_script(f"{second / 'uses.py'}::Uses")
    second_helper = sys.modules["lab_helper_g"]
    manager.reload([str(first)])
    assert manager.get_script(f"{second / 'uses.py'}::Uses") is second_class
    assert sys.modules["lab_helper_g"] is second_helper
    assert manager.folders() == [str(first), str(second)]


def test_watched_files_and_their_stamps(tmp_path: Path) -> None:
    script = write(tmp_path, "counts.py", analysis())
    (tmp_path / "notes.txt").write_text("not watched")
    manager = ScriptsManager()
    manager.load_directory(str(tmp_path))
    assert manager.watched_files(str(tmp_path)) == [str(script)]
    before = manager.stamp(manager.watched_files(str(tmp_path)))
    assert [entry[0] for entry in before] == [str(script)]
    script.write_text(script.read_text() + "\n# edited\n")
    assert manager.stamp(manager.watched_files(str(tmp_path))) != before
    assert manager.stamp([str(tmp_path / "missing.py")]) == ()
    assert manager.watched_files(str(tmp_path / "missing")) == []
