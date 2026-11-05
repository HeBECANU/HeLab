"""What HeLab keeps for after a crash (LR-15, Tony 2026-11-05): a hard crash leaves every thread's
Python stack in ``logs/crash-<pid>.txt`` (an I/O helper's ``helper-crash-<pid>.txt``), removed at a
clean exit while empty; the console's output in ``console-<pid>.txt``; Qt's messages in the log; the
last run's crash named at start; a memory line each minute while Live is on. The startup tidy counts
these files with the logs and removes empty ones. Crashes and the console run in child processes
(``faulthandler`` and the console belong to pytest here), each with its own temporary folder."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, cast

import pytest
from pytestqt.qtbot import QtBot

import test_accessible_names as an  # (Also imports QtWebEngine before the app starts.)
from helab.utils import app_log, console_tee, crash_file

ROOT = Path(__file__).resolve().parents[1]

CHILD = """
import os, sys, threading
sys.path.insert(0, sys.argv[1])
folder, name, how = sys.argv[2], sys.argv[3], sys.argv[4]
for kind in ("CACHES", "TEMPS"):
    os.environ[f"HELAB_DIR_{kind}_OVERRIDE"] = folder
os.environ["HELAB_APP_DIR_OVERRIDE"] = folder
if name == "HELPER":  # As an I/O helper starts: standard library only, the folder from the app.
    os.environ["HELAB_HELPER_CRASH_DIR"] = os.path.join(folder, "logs")
    from helab.utils import crash_file
    path = crash_file.start_for_helper()
    assert not [m for m in sys.modules if m.startswith("PyQt6")]
else:
    from helab.utils import app_log
    path = app_log.start_crash_file(folder, getattr(app_log, name))
print(path, flush=True)
if how == "crash":
    import faulthandler
    ready = threading.Event()
    def waiting():
        ready.set()
        threading.Event().wait()
    threading.Thread(target=waiting, name="helper-like", daemon=True).start()
    ready.wait()
    faulthandler._sigsegv()
"""


def child(folder: Path, name: str, how: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    result = subprocess.run([sys.executable, "-c", CHILD, str(ROOT), str(folder), name, how],
                            capture_output=True, text=True, timeout=60)
    return result, Path(result.stdout.strip().splitlines()[0])


@pytest.mark.parametrize("name,file", [("CRASH_NAME", "crash-{pid}.txt"), ("HELPER_CRASH_NAME", "helper-crash-{pid}.txt"),
                                       ("HELPER", "helper-crash-{pid}.txt")])
def test_a_hard_crash_leaves_every_threads_stack_in_the_crash_file(tmp_path: Path, name: str, file: str) -> None:
    result, path = child(tmp_path, name, "crash")
    assert result.returncode != 0
    assert path.parent == tmp_path / "logs" and path.name.endswith(".txt")
    assert path.name == file.format(pid=path.name.split("-")[-1].removesuffix(".txt"))
    text = path.read_text()
    assert "Fatal Python error: Segmentation fault" in text or "Windows fatal exception: access violation" in text, text
    assert "Current thread 0x" in text and "Thread 0x" in text and "waiting" in text, text  # (Every thread.)


def test_a_clean_exit_removes_the_empty_crash_file(tmp_path: Path) -> None:
    result, path = child(tmp_path, "CRASH_NAME", "exit")
    assert result.returncode == 0, result.stderr
    assert path.name.startswith("crash-") and not path.exists()


def test_no_crash_file_where_it_cant_be_written(tmp_path: Path, caplog: pytest.LogCaptureFixture,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "logs").write_text("a file, not a folder")
    assert app_log.start_crash_file(str(tmp_path)) is None  # (Fails before faulthandler is touched.)
    assert "No crash file" in caplog.text
    monkeypatch.delenv(crash_file.HELPER_DIR_ENV, raising=False)
    assert crash_file.start_for_helper() is None  # (No folder named: none.)
    monkeypatch.setenv(crash_file.HELPER_DIR_ENV, str(tmp_path / "logs"))
    assert crash_file.start_for_helper() is None


def put(folder: Path, name: str, age: float, size: int) -> None:
    path = folder / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))


def test_the_tidy_counts_crash_files_with_the_logs_and_removes_empty_ones(tmp_path: Path) -> None:
    put(tmp_path, "helab-101.log", 5 * 3600, 10)
    put(tmp_path, "crash-101.txt", 5 * 3600, 30)  # A crash's stack: kept while the count allows.
    put(tmp_path, "helper-crash-102.txt", 4 * 3600, 0)  # A killed helper's: nothing in it.
    put(tmp_path, "crash-103.txt", 3 * 3600, 0)
    put(tmp_path, "helper-crash-104.txt", 10, 0)  # Just made (a helper starting): never deleted.
    put(tmp_path, "helab-105.log", 2 * 3600, 10)
    files = {file.path.rsplit(os.sep, 1)[-1]: file.pid for file in app_log.scan_logs(str(tmp_path))}
    assert files == {"helab-101.log": 101, "crash-101.txt": 101, "helper-crash-102.txt": 102,
                     "crash-103.txt": 103, "helper-crash-104.txt": 104, "helab-105.log": 105}
    assert app_log.tidy_logs(str(tmp_path), keep=10) == 50
    assert {path.name for path in (tmp_path / "logs").iterdir()} == {
        "helab-101.log", "crash-101.txt", "helper-crash-104.txt", "helab-105.log"}
    assert app_log.tidy_logs(str(tmp_path), keep=2) == 10  # The oldest by mtime go, crash files with them.
    assert {path.name for path in (tmp_path / "logs").iterdir()} == {"helper-crash-104.txt", "helab-105.log"}


def test_helab_and_its_helpers_start_their_crash_files() -> None:
    """``main`` once it logs to its file; each I/O helper as it starts."""
    main = (ROOT / "helab" / "main.py").read_text()
    assert main.index("app_log.start_crash_file(app_folder())") > main.index("app_log.start_log_file(app_folder())")
    helper = (ROOT / "helab" / "io_helper.py").read_text()
    assert helper.index("crash_file.start_for_helper()") < helper.index("json.loads(sys.stdin.readline())")
    service = (ROOT / "helab" / "utils" / "io_service.py").read_text()
    assert "env[crash_file.HELPER_DIR_ENV] = app_log.log_folder(app_folder())" in service


# The console file (``console_tee``): fd 1 and 2, C-level writes and child processes' too.

TEE_CHILD = """
import atexit, os, sys
sys.path.insert(0, sys.argv[1])
os.environ.pop("HELAB_NO_CONSOLE_FILE", None)
from helab.utils import console_tee
tee = console_tee.start(sys.argv[2])
atexit.register(tee.stop)  # (As main does.)
print("python-stdout", flush=True)
os.write(2, b"fd-stderr\\n")  # (As C code writes.)
os.system("echo from-a-child-process")  # (It inherits fd 1.)
print(tee.path, flush=True)
"""


def test_the_console_is_kept_in_the_logs_folder_and_still_reaches_the_terminal(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    result = subprocess.run([sys.executable, "-c", TEE_CHILD, str(ROOT), str(logs)], capture_output=True, text=True,
                            timeout=60, env={k: v for k, v in os.environ.items() if k != "HELAB_NO_CONSOLE_FILE"})
    assert result.returncode == 0, result.stderr
    assert "python-stdout" in result.stdout and "from-a-child-process" in result.stdout  # The terminal, as before.
    assert "fd-stderr" in result.stderr
    path = Path(result.stdout.strip().splitlines()[-1])
    assert path.parent == logs and path.name.startswith("console-") and path.name.endswith(".txt")
    kept = path.read_text()
    # (A child process on Windows inherits the OS's standard handles, which dup2 on the C runtime's
    # descriptors may leave: there only HeLab's own writes are checked.)
    for text in ("python-stdout", "fd-stderr", *(() if sys.platform == "win32" else ("from-a-child-process",))):
        assert text in kept, kept


def test_the_console_file_is_off_under_the_test_suite(tmp_path: Path) -> None:
    assert os.environ.get(console_tee.OFF_ENV)  # (conftest)
    assert console_tee.start(str(tmp_path)) is None and not list(tmp_path.glob("console-*"))


def test_the_console_file_rotates_once_at_its_cap_and_is_tidied_with_the_logs(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    path = tmp_path / "logs" / "console-404.txt"
    tee = console_tee.ConsoleTee(str(path), cap=10)
    tee.write(b"12345678")
    tee.write(b"abcdef")  # Past the cap: the first file becomes .1.
    tee.write(b"ghij")
    tee.write(b"klmnop")  # And again: the newest output is always kept.
    tee.stop()
    assert tee.rotations == 2 and path.read_bytes() == b"klmnop"
    assert Path(f"{path}.1").read_bytes() == b"abcdefghij"
    assert console_tee.CAP == 20 * 1000 * 1000
    found = {Path(file.path).name: file.pid for file in app_log.scan_logs(str(tmp_path))}
    assert found == {"console-404.txt": 404, "console-404.txt.1": 404}


# Qt's messages in the log.

def test_qts_warnings_go_to_the_log_with_their_category_once_a_minute(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(app_log, "_qt_seen", {})
    with caplog.at_level(logging.DEBUG, logger="qt"):
        app_log.qt_message("QtWarningMsg", "qt.qpa.fonts", "Populating font family aliases took 120 ms")
        app_log.qt_message("QtWarningMsg", "qt.qpa.fonts", "Populating font family aliases took 120 ms")
        app_log.qt_message("QtCriticalMsg", "default", "QPainter::begin: Paint device returned engine == 0")
        app_log.qt_message("QtDebugMsg", "qt.core", "a debug line")
    lines = [(record.levelno, record.getMessage()) for record in caplog.records if record.name == "qt"]
    assert lines == [(logging.WARNING, "[qt.qpa.fonts] Populating font family aliases took 120 ms"),
                     (logging.ERROR, "[default] QPainter::begin: Paint device returned engine == 0")]
    assert "a debug line" in capsys.readouterr().err  # (Below a warning: the console only, as Qt prints it.)
    monkeypatch.setattr(app_log, "REPEAT_SECONDS", 0.0)
    with caplog.at_level(logging.WARNING, logger="qt"):
        app_log.qt_message("QtWarningMsg", "qt.qpa.fonts", "Populating font family aliases took 120 ms")
    assert caplog.records[-1].getMessage().endswith("(and 1 more like it since)")


def test_qts_message_handler_is_installed(caplog: pytest.LogCaptureFixture) -> None:
    from PyQt6.QtCore import qInstallMessageHandler, qWarning
    previous = app_log.install_qt_messages()
    try:
        with caplog.at_level(logging.WARNING, logger="qt"):
            qWarning("LR-15 check: a warning from Qt's side")
    finally:
        qInstallMessageHandler(previous)
    assert any("LR-15 check: a warning from Qt's side" in record.getMessage() for record in caplog.records)


# The last run's crash, named at start.

def test_the_last_runs_crash_file_is_named_at_start(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    put(tmp_path, "helab-101.log", 5 * 3600, 10)  # The run before the last.
    put(tmp_path, "crash-101.txt", 5 * 3600, 40)  # (Its crash: named when it was the last run.)
    put(tmp_path, "helper-crash-150.txt", 5.5 * 3600, 40)  # A helper of that run (before its log ended).
    put(tmp_path, "helab-202.log", 3600, 10)  # The last run.
    put(tmp_path, "crash-202.txt", 3600, 40)
    put(tmp_path, "helper-crash-303.txt", 2 * 3600, 40)  # A helper's crash while it ran.
    put(tmp_path, "helper-crash-304.txt", 2 * 3600, 0)  # (Empty: nothing.)
    with caplog.at_level(logging.WARNING):
        assert app_log.note_previous_crash(str(tmp_path)) == ["crash-202.txt", "helper-crash-303.txt"]
    assert f"The previous run crashed: see {tmp_path / 'logs' / 'crash-202.txt'}" in caplog.text
    (tmp_path / "logs" / "crash-202.txt").write_text("")
    os.utime(tmp_path / "logs" / "crash-202.txt", (time.time() - 3600, time.time() - 3600))
    assert app_log.previous_crashes(str(tmp_path)) == ["helper-crash-303.txt"]
    assert app_log.previous_crashes(str(tmp_path / "none")) == []


# The memory line while Live is on.

def test_the_memory_line_says_what_grows(qtbot: QtBot, tmp_path: Path) -> None:
    from types import SimpleNamespace
    import numpy as np
    from helab.analysis.results import RamResults
    results = RamResults()
    array = np.zeros(1000)
    for job in ("a", "b"):
        results.add(cast(Any, SimpleNamespace(job_id=job, data={"x": array, "y": array[:10], "z": np.ones(5)})))
    assert results.usage() == (2, 8000 + 2 * 40)  # (A buffer and its views count once.)
    line = app_log.memory_line(2 << 30, 1 << 30, 1 << 29, 8 << 30, results.usage(), 3, [("run_1", 1234, 57)])
    assert line.startswith("Memory while Live: RSS 2.0 GiB · RAM budget 1.5 GiB of 8.0 GiB "
                           "(datasets 1.0 GiB, plots 512 MiB) · results 2 (7.9 KiB)")
    assert line.endswith(" · open plots 3 · Live run_1: 1,234 shots, revision 57")


@pytest.mark.no_auto_data_root  # RAM only: no save left for the quit to wait for.
def test_the_main_window_logs_memory_each_minute_only_while_live_is_on(
        qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from helab.views.explorer_live import LiveSession
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.HelabMainWindow import HelabMainWindow
    run = an.run_folder(tmp_path)
    window = HelabMainWindow()
    qtbot.addWidget(window)
    window.show()
    try:
        assert window.memory_log_timer.interval() == 60_000 and window.memory_log_timer.isActive()
        qtbot.waitUntil(lambda: isinstance(window.tab_widget.currentWidget(), FolderExplorer), timeout=10_000)
        window.add_new_folder_explorer_tab(target_path=str(run))
        explorer = window.tab_widget.currentWidget()
        assert isinstance(explorer, FolderExplorer)
        qtbot.waitUntil(lambda: explorer.displayed_dataset is not None
                        and explorer.displayed_dataset.path == str(run), timeout=30_000)
        assert window.log_memory() == ""  # Live off: nothing.
        dataset = explorer.displayed_dataset
        assert dataset is not None
        explorer.live = LiveSession(str(run), time.time(), set(dataset.data), dataset)
        try:
            with caplog.at_level(logging.INFO):
                line = window.log_memory()
            assert line.startswith("Memory while Live: RSS ") and " · open plots 0 · Live run: 3 shots, revision " in line
            assert line in caplog.text
        finally:
            explorer.live = None
    finally:
        an.quit_window(qtbot, window)


def test_main_starts_them_all_in_order() -> None:
    main = (ROOT / "helab" / "main.py").read_text()
    order = ["app_log.start_log_file(app_folder())", "app_log.start_crash_file(app_folder())",
             "console_tee.start(app_log.log_folder(app_folder()))", "atexit.register(console.stop)",
             "app_log.install_qt_messages()", "logging.captureWarnings(True)", "app_log.note_previous_crash(app_folder())"]
    assert [main.index(part) for part in order] == sorted(main.index(part) for part in order)
