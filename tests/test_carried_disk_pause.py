"""A test that leaves the app-wide FolderCache paused at 80% doesn't pause the next one
(``conftest.no_carried_disk_pause``): the next test's main window showed "Disk cache below 80% — automatic
loading resumed" in front of its status bar (Windows CI 42001112700)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TWO_TESTS = '''
from helab.utils.folder_cache import get_folder_cache
from helab.utils.io_service import get_io_service


def test_leaves_the_cache_paused(qapp, monkeypatch):
    cache = get_folder_cache(get_io_service())
    monkeypatch.setattr("helab.utils.folder_cache._disk_budget", 1000)  # (Put back at teardown.)
    cache.disk_usage = 900
    cache.update_auto_load_pause()
    assert cache.auto_load_paused and cache._full_warned


def test_after_it(qapp):
    cache = get_folder_cache(get_io_service())
    assert not cache.auto_load_paused and cache.disk_usage is None and not cache._full_warned
    changes = []
    cache.autoLoadPauseChanged.connect(changes.append)
    cache.update_auto_load_pause()  # (A main window's settings do this: it said "resumed".)
    assert changes == []
'''


def test_a_pause_left_by_one_test_doesnt_reach_the_next(tmp_path: Path) -> None:
    """In order, in a run of its own with this conftest as its plugin (as ``test_left_widgets.py``)."""
    test = tmp_path / "test_two.py"  # (Outside tests/, so conftest comes only by -p.)
    test.write_text(TWO_TESTS, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "tests")])}
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "conftest", "-p", "no:cacheprovider",
                           "-p", "no:xdist", "-p", "no:rerunfailures", "-q", "-rA", str(test)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    out = done.stdout + done.stderr
    assert "PASSED test_two.py::test_leaves_the_cache_paused" in out, out
    assert "PASSED test_two.py::test_after_it" in out, out
    assert "2 passed" in out, out
