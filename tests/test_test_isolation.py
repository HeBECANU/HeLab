"""Tests run apart from the developer's data and from each other (tests/conftest.py): they test
this checkout's helab, new tabs start in an empty temp folder, never the default data path
(``/Volumes/dld_output`` when it is mounted), and each test's disk cache is a store of its own."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

import helab
from conftest import START_FOLDER, live_reason, this_tests
from helab.utils import constants
from helab.utils.cache_store import CacheStore, store_root
from helab.utils.folder_cache import store_options
from helab.views.FolderExplorer import FolderExplorer
from helab.views.HelabMainWindow import HelabMainWindow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = {"DEFAULT_DATA_PATH", "DEV_POTENTIAL_DATA_PATHS"}
# The modules that may read the default data paths: conftest patches FolderTabWidget's names, and
# io_ops.infra reads them only to refuse them under pytest.
READERS = {"helab/utils/constants.py", "helab/views/FolderTabWidget.py", "helab/io_ops/infra.py"}


def test_helab_is_this_checkouts() -> None:
    """pytest.ini's ``pythonpath`` puts this checkout first, so pytest never tests another
    checkout's helab: a floor's venv copied from Ground has Ground's editable install."""
    assert Path(helab.__file__).resolve() == ROOT / "helab" / "__init__.py"


def test_pytest_imports_the_checkout_it_runs_in_before_any_other(tmp_path: Path) -> None:
    other = tmp_path / "other-checkout" / "helab"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text("", encoding="utf-8")
    test = tmp_path / "test_which.py"  # (Outside tests/: no conftest, so it imports quickly.)
    test.write_text("import helab\n\ndef test_which():\n    print('helab at', helab.__file__)\n",
                    encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(other.parent)}
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist",
                           "-s", "-q", "--rootdir", str(ROOT), "-c", str(ROOT / "pytest.ini"), str(test)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"helab at {ROOT / 'helab' / '__init__.py'}" in done.stdout, done.stdout


def test_only_patched_modules_read_the_default_data_paths() -> None:
    """A new reader of the default data paths would slip past conftest's patch."""
    readers = set()
    for file in (ROOT / "helab").rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                  for alias in node.names}
        if names & DEFAULT_PATHS:
            readers.add(file.relative_to(ROOT).as_posix())
    assert readers == READERS


def test_a_main_windows_tabs_start_in_the_test_folder(qtbot: QtBot) -> None:
    window = HelabMainWindow()
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.tab_widget.count() == 1)  # (Its first tab comes from a timer.)
    window.add_new_folder_explorer_tab()
    explorers = [window.tab_widget.widget(index) for index in range(window.tab_widget.count())]
    assert len(explorers) == 2
    data = [os.path.normcase(path) for path in constants.DEV_POTENTIAL_DATA_PATHS if path]
    for explorer in explorers:
        assert isinstance(explorer, FolderExplorer)
        for path in (explorer.target_path, explorer.view_path, explorer.selected_path_globally):
            assert os.path.normcase(path) == os.path.normcase(os.path.abspath(START_FOLDER))
            assert os.path.normcase(path) not in data
    window.close()


def test_each_test_has_a_store_of_its_own(private_store: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Made for this test: nothing an earlier test of this worker saved (a pending save, a budget,
    roots) is there. conftest seeds only this test's data root."""
    assert constants.cache_dir() == private_store == os.environ["HELAB_DIR_CACHES_OVERRIDE"]
    assert Path(private_store).is_relative_to(tmp_path_factory.getbasetemp())
    assert store_options()["directory"] == store_root(private_store)
    with CacheStore(store_root(private_store), root_mode=True) as store:
        assert len(store.root_locations()) == 1
        assert store.inventory()["pending"] == []


def test_a_process_wide_fake_acts_on_this_tests_threads_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A46.1: ``this_tests`` gives a fake to the test's own thread and to threads started after it is put in
    place (an IOService's helpers), and the real function to threads alive before (an earlier test's helper
    reader or log tidy calling ``os.stat`` meanwhile): Windows CI's flakes counted or refused those."""
    go, answers = threading.Event(), dict[str, int | str]()

    def call(name: str) -> None:
        try:
            answers[name] = os.stat(tmp_path).st_mode
        except AssertionError as exc:
            answers[name] = str(exc)

    def earlier_thread() -> None:
        assert go.wait(10)
        call("earlier")
    earlier = threading.Thread(target=earlier_thread)
    earlier.start()  # (Alive before the patch: another test's.)

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("refused")
    monkeypatch.setattr(os, "stat", this_tests(refused, os.stat))
    go.set()
    earlier.join(10)
    later = threading.Thread(target=call, args=("later",))
    later.start()
    later.join(10)
    call("ours")
    assert isinstance(answers["earlier"], int) and answers["later"] == answers["ours"] == "refused", answers


def test_a_failure_or_rerun_is_said_as_it_happens() -> None:
    """A CI job cancelled at its time limit never reaches pytest's summary, which lost every traceback and rerun
    reason of Ubuntu CI 41468043383's attempt 1: conftest writes each failure's and rerun's reason live."""
    text = "def test_x():\n>       assert 1 == 2\nE       assert 1 == 2\n\ntests/test_x.py:3: AssertionError"

    def report(outcome: str, when: str = "call") -> pytest.TestReport:
        return pytest.TestReport("tests/test_x.py::test_x", ("tests/test_x.py", 2, "test_x"), {},
                                 outcome, text, when)  # type: ignore[arg-type]  # ("rerun" is rerunfailures')
    assert live_reason(report("rerun")) == ("RERUN REASON tests/test_x.py::test_x (call):\n"
                                            "E       assert 1 == 2\ntests/test_x.py:3: AssertionError")
    assert (live_reason(report("failed", "teardown")) or "").startswith("FAILED REASON tests/test_x.py::test_x (teardown):")
    assert live_reason(report("passed")) is None and live_reason(report("skipped")) is None
    # xdist's report of a worker that died (here: killed at CI's --timeout after a hang) has the phase "???".
    assert (live_reason(report("failed", "???")) or "").startswith(
        "FAILED REASON tests/test_x.py::test_x (worker crashed or was killed):")
