"""How a helper is started and read (``IOService._run``, ``_file_lines``): what happens on the
daemon thread before and after the helper process runs."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from helab.utils.io_service import IORequest, IOService


@pytest.mark.parametrize("another", [False, True], ids=["alone", "another thread starts a process meanwhile"])
def test_writing_held_data_out_counts_as_progress(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                  another: bool) -> None:
    """A Live save writes the data held in RAM to the helper's folder before the helper starts; a
    dump slower than the no-progress time must not retire the save before its helper runs.

    Only this request's start is counted: ``subprocess.Popen`` is patched for the whole process, and a
    process another thread starts meanwhile (an earlier test's helper, still starting) goes to the real
    one. Counting it too was Windows CI's "assert (2 == 1)": two starts about 1 ms apart (known-issues)."""
    service = IOService()
    service.timer.stop()
    request = IORequest("tab", 0, "/data", "load", {"save_memory": True}, service.NO_PROGRESS_TIMEOUT,
                        arrays={1: np.zeros(3), 2: np.zeros(3)})
    request.last_activity = time.monotonic()
    ours, real_popen = threading.current_thread(), subprocess.Popen
    others: list[int] = []

    def other_start() -> None:
        with subprocess.Popen([sys.executable, "-c", "pass"]) as process:
            others.append(process.wait())

    def slow_save(*args: Any, **kwargs: Any) -> None:
        request.last_activity -= service.NO_PROGRESS_TIMEOUT  # As if each array took that long.
        if another and not others:
            thread = threading.Thread(target=other_start)
            thread.start()
            thread.join()

    idle_at_start: list[float] = []

    def popen(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread() is not ours:
            return real_popen(*args, **kwargs)  # (Not this request's: ``_run`` runs on the test's thread here.)
        idle_at_start.append(time.monotonic() - request.last_activity)
        raise OSError("not started in this test")

    monkeypatch.setattr(np, "save", slow_save)
    monkeypatch.setattr("helab.utils.io_service.subprocess.Popen", popen)
    service._run(request)
    assert len(idle_at_start) == 1 and idle_at_start[0] < request.timeout
    assert others == ([0] if another else [])
    service.shutdown()


def test_the_frozen_reader_reads_lines_written_just_before_the_helper_exited(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The packaged app reads the helper's response file: a ``done`` written between the reader's
    last read and its check that the helper exited must still be read."""
    response = tmp_path / "response.jsonl"
    response.write_text('{"kind": "status"}\n', encoding="utf-8")

    class Exiting:
        def poll(self) -> int:
            with response.open("a", encoding="utf-8") as stream:
                stream.write('{"kind": "done"}\n')
            return 0

    request = IORequest("tab", 0, "/data", "list", {}, 60.0)
    monkeypatch.setattr(request, "process", Exiting())
    assert list(IOService._file_lines(request, str(response))) == ['{"kind": "status"}\n', '{"kind": "done"}\n']


@pytest.mark.parametrize("exited", [False, True], ids=["dies", "died before its request was written"])
def test_a_helper_that_dies_leaves_what_it_said_in_the_log(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, exited: bool) -> None:
    """Whether it exits before or after its request is written to it (then the write finds its
    pipe closed: "Broken pipe" on macOS CI), it exited unexpectedly, and what it said is logged."""
    service = IOService()
    service.timer.stop()
    started = subprocess.Popen

    def dying(command: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        process = started([sys.executable, "-c", "import sys; sys.stderr.write('ImportError: no blosc\\n'); "
                           "sys.exit(1)"], **kwargs)
        if exited:
            process.wait()
        return process

    monkeypatch.setattr("helab.utils.io_service.subprocess.Popen", dying)
    request = IORequest("tab", 0, "/data", "list", {}, 60.0)
    with caplog.at_level(logging.WARNING):
        service._run(request)
    events = []
    while not service.messages.empty():
        events.append(service.messages.get_nowait()[1])
    assert {"kind": "error", "message": "I/O helper exited unexpectedly"} in events
    assert "ImportError: no blosc" in caplog.text
    service.shutdown()


def test_shutdown_stops_its_helpers_itself_not_only_from_the_reapers(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The area review's second unverified note (io.md): the reaper threads that kill cancelled helpers are
    daemon threads, which may not run before the interpreter exits after quitting, so a helper (a finishing
    save's cache write) could outlive HeLab. ``shutdown`` signals each one itself (``kill`` never waits)."""
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_run", lambda request: None)
    monkeypatch.setattr(service, "_reap", lambda request: None)  # (The reapers never got to run.)
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], text=True)
    try:
        service.submit("tab", 0, "/saving", "load", {"save": True})
        request = service.active[0]
        request.process = helper
        request.completed = True  # Delivered its data; writing the disk cache.
        service.shutdown()
        assert helper.wait(timeout=10) != 0
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait()


@pytest.mark.parametrize("another", [False, True], ids=["alone", "another service's helper starts meanwhile"])
def test_a_helper_still_starting_when_helab_quits_is_stopped(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                             another: bool) -> None:
    """A40.1 (IO Fixes' A~1): HeLab quits while ``_run`` is inside ``Popen`` (no ``process`` yet, so ``shutdown``
    can't kill it). ``shutdown`` cancels every active request first, and ``_run`` kills a cancelled request's
    process as soon as ``Popen`` returns: the helper doesn't outlive HeLab. (A ``self.closed`` check there, as
    proposed, would add nothing: no request is closed without being cancelled.)

    The fake takes this request's start only, known by its stderr file in the request's own folder: another
    IOService's helper starting meanwhile (a ``HeLab-*`` thread too) gets the real ``Popen``. Taking any
    ``HeLab-*`` thread's made that one ``started[0]``, never killed here (caching-v2 CI 41451159277)."""
    service = IOService()
    service.timer.stop()
    real_popen = subprocess.Popen
    in_popen, quitting = threading.Event(), threading.Event()
    started: list[subprocess.Popen[str]] = []
    others: list[subprocess.Popen[str]] = []
    ours: list[IORequest] = []

    def popen(*args: Any, **kwargs: Any) -> Any:
        errors = getattr(kwargs.get("stderr"), "name", "")
        if not ours or not ours[0].output or os.path.dirname(str(errors)) != ours[0].output:
            return real_popen(*args, **kwargs)  # (Not this request's start: another's, or another thread's.)
        in_popen.set()
        assert quitting.wait(10)
        process = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
        started.append(process)
        return process
    monkeypatch.setattr("helab.utils.io_service.subprocess.Popen", popen)
    if another:
        def other_helper() -> None:  # (As another IOService's _run starts its helper.)
            others.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True))
        threading.Thread(target=other_helper, name="HeLab-list").start()
    service.before_start = ours.append  # (This request, known before its _run thread starts.)
    service.submit("tab", 0, "/somewhere", "list")
    service._dispatch()
    assert in_popen.wait(10)
    service.shutdown()  # HeLab quits now.
    quitting.set()
    qtbot.waitUntil(lambda: bool(started) and len(others) == int(another), timeout=10_000)
    try:
        assert len(started) == 1 and started[0].wait(timeout=10) != 0
        assert all(process.poll() is None for process in others)  # (Not this service's: not stopped by it.)
    finally:
        for process in (*started, *others):
            if process.poll() is None:
                process.kill()
                process.wait()
