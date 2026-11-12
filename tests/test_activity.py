"""The Activity window's model (Q62.1–Q62.5): states, groups, the history and each source's tasks, from
fakes and an IOService that starts no helper (``_run`` replaced)."""
from __future__ import annotations

import logging
import threading
import time
from types import SimpleNamespace
from typing import Any, Iterator, List, Optional, Sequence, cast

import numpy as np
import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtWidgets import QLabel, QWidget

from helab.analysis.dataset_view import build_view
from helab.analysis.runner import AnalysisRunner
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.runner_core import RunInfo
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.utils import activity
from helab.utils.activity import Finished, Progress
from helab.utils.folder_cache import Dataset, FolderCache, QuitSave, get_folder_cache
from helab.utils.io_service import IORequest, IOService
from helab.utils.load_clock import LoadClock
from helab.views.ActivityWindow import (PAUSED_BY_YOU, PAUSED_FOREGROUND, PAUSED_MISMATCH, ActivitySources,
                                        conversion_id, live_id)
from helab.views.explorer_convert import FolderConversion
from helab.views.explorer_live import AutoConvert, LiveSession


@pytest.fixture(autouse=True)
def fresh_activity() -> Iterator[None]:
    """``HISTORY`` and ``LOG_LINES_HANDLER`` are module-global: each test starts and ends with them empty,
    and the handler off the root logger."""
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    yield
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    activity.remove_log_lines()


def quiet_service(monkeypatch: pytest.MonkeyPatch, foreground: set[str] | None = None) -> IOService:
    """An IOService whose requests start without a helper (``_run`` does nothing) and whose timer is off."""
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_run", lambda request: None)
    service.is_foreground = lambda request: request.owner in (foreground or set())
    return service


def exit_helper(service: IOService, request: IORequest) -> None:
    request.exited.set()
    service.messages.put((request, {"kind": "exit"}))
    service._tick()


def fake_explorer(owner: str = "tab", sessions: Sequence[LiveSession] = (), conversions: dict[str, Any] | None = None,
                  live_box: Any = None, convert_box: Any = None) -> Any:
    """What ``ActivitySources`` reads of a ``FolderExplorer``."""
    by_path = {session.path: session for session in sessions}
    live_control = SimpleNamespace(
        sessions=lambda: list(sessions), box=live_box, session=by_path.get,
        live_line=lambda session: ("Live · watching", "Checks every 3 s", False),
        convert_line=lambda session: ("converted 2", ["Converts with each check"], False), stall_seconds=lambda: 60.0)
    converter = SimpleNamespace(owner=f"{owner}:convert", conversions=conversions or {}, box=convert_box,
                                row=lambda path: ("Converting…", "Converting the raw files"))
    return SimpleNamespace(model=SimpleNamespace(owner=owner), bg_owner=f"{owner}:bg", live_owner=f"{owner}:live",
                           live_save_owner=f"{owner}:live-save", live_control=live_control, converter=converter)


def sources(service: IOService, cache: FolderCache | None = None, tabs: Sequence[tuple[str, Any]] = (),
            **kwargs: Any) -> ActivitySources:
    return ActivitySources(service, cache or get_folder_cache(service), lambda: cast(Any, tabs),
                           mover=kwargs.pop("mover", lambda: None), **kwargs)


def task(snapshot: activity.Snapshot, prefix: str) -> activity.Task:
    return next(task for task in snapshot.tasks if task.id.startswith(prefix))


# Pure rules

def test_every_io_operation_has_a_group() -> None:
    for operation in IOService.LABELS:
        assert activity.group_of(operation, {}) != "other", operation
    assert activity.group_of("load", {"live": True}) == "live"
    assert activity.group_of("load", {"save": True}) == "saves"
    assert activity.group_of("load", {}, finishing=True) == "saves"
    assert activity.group_of("cache_admin", {}, admin="sweep") == "upkeep"
    assert activity.group_of("cache_admin", {}, admin="folder_prefs") == "saves"
    assert activity.group_of("something_new", {}) == "other"


def test_the_history_keeps_failures_and_leaves_out_frequent_successes() -> None:
    assert not activity.kept_in_history("load", {"live": True}, "ok")
    assert activity.kept_in_history("load", {"live": True}, "failed")
    for operation in ("list", "details", "cached", "icons", "subtree_save", "volumes_verify", "convert"):
        assert not activity.kept_in_history(operation, {}, "ok")
        assert activity.kept_in_history(operation, {}, "cancelled")
        assert activity.kept_in_history(operation, {}, "failed")
    assert activity.kept_in_history("load", {}, "ok") and activity.kept_in_history("scan", {}, "ok")


def test_the_history_holds_the_last_200_newest_first() -> None:
    history = activity.History()
    for n in range(250):
        history.add(Finished(f"t{n}", "loads", "Load data", f"/data/{n}", float(n),
                             "failed" if n % 2 else "ok", "broken" if n % 2 else ""))
    entries = history.entries()
    assert len(entries) == activity.HISTORY_SIZE == 200
    assert [entry.id for entry in entries[:3]] == ["t249", "t248", "t247"] and entries[-1].id == "t50"
    assert entries[0].failed and not entries[1].failed
    assert activity.outcome_text(entries[0]) == "✕ failed: broken" and activity.outcome_text(entries[1]) == "done"


def test_the_history_is_added_to_on_the_gui_thread_only() -> None:
    called: list[int] = []
    activity.HISTORY.listeners.append(lambda: called.append(1))
    errors: list[BaseException] = []

    def off_thread() -> None:
        try:
            activity.record(Finished("x", "analysis", "Plot", "", 0.0, "ok"))
        except AssertionError as error:
            errors.append(error)
    thread = threading.Thread(target=off_thread)
    thread.start()
    thread.join()
    assert errors and not called and len(activity.HISTORY) == 0
    activity.record(Finished("x", "analysis", "Plot", "", 0.0, "ok"))
    assert called == [1] and len(activity.HISTORY) == 1


def test_a_failing_listener_never_reaches_the_reporter(caplog: pytest.LogCaptureFixture) -> None:
    """AW-6: a view's error is logged; the owner's report returns, and later listeners still hear."""
    heard: list[int] = []

    def broken() -> None:
        raise RuntimeError("wrapped C/C++ object has been deleted")
    activity.HISTORY.listeners += [broken, lambda: heard.append(1)]
    activity.record(Finished("x", "loads", "Load data", "/data", 0.0, "ok"))
    assert heard == [1] and len(activity.HISTORY) == 1
    assert "Activity history listener" in caplog.text


def test_progress_and_ordinals() -> None:
    assert Progress(123, 579).text() == "123 of 579 files · 21%"
    assert Progress(0, 0).text() == "no files" and Progress().text() == "" and Progress().fraction is None
    assert Progress(1, 4, 50, 100).fraction == 0.5
    assert [activity.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


def test_log_lines_name_a_folder_within_its_time() -> None:
    handler = activity.install_log_lines()
    assert handler in logging.getLogger().handlers
    activity.install_log_lines()
    assert logging.getLogger().handlers.count(handler) == 1
    logging.warning("Load data failed: /data/run_1 — broken")
    logging.warning("Load data failed: /data/run_2 — broken")
    logging.info("Load data: /data/run_1 (info is not kept)")
    lines = handler.about("/data/run_1", time.time() - 5, time.time())
    assert len(lines) == 1 and "WARNING Load data failed: /data/run_1 — broken" in lines[0]
    assert handler.about("/data/run_1", until=time.time() - 3600) == [] and handler.about("") == []
    logging.warning("Load data failed: /data/run_10 — broken")  # (AW-12: another folder.)
    logging.warning("Shot file unreadable: /data/run_1/d_txy_forc3.txt")
    assert [line.split("WARNING ")[1] for line in handler.about("/data/run_1")] == [
        "Load data failed: /data/run_1 — broken", "Shot file unreadable: /data/run_1/d_txy_forc3.txt"]
    activity.remove_log_lines()
    assert handler not in logging.getLogger().handlers


# IOService's requests

def test_requests_show_running_stalled_paused_queued_and_stopping(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.submit("a", 0, "/a", "details")
    service.submit("b", 0, "/b", "scan")
    service.submit("c", 0, "/c", "scan")
    running = service.active[0]
    built = sources(service).snapshot()
    rows = {row.folder: row for row in built.tasks}
    assert (rows["/a"].state, rows["/a"].state_text, rows["/a"].group) == ("running", "running", "loads")
    assert (rows["/b"].state, rows["/b"].state_text) == ("queued", "queued (1st)")
    assert rows["/c"].state_text == "queued (2nd)"
    assert "Lane: background" in rows["/a"].details and "Helper process: starting" in rows["/a"].details
    running.last_activity = time.monotonic() - 12
    running.last_event = "heartbeat"
    row = task(sources(service).snapshot(), "io:a:")
    assert row.state == "stalled" and row.state_text.startswith("no progress for 0:1")
    assert any("(heartbeat)" in line for line in row.details)
    running.paused = True
    assert task(sources(service).snapshot(), "io:a:").state_text == f"paused: {PAUSED_FOREGROUND}"
    service.mismatch_hold = True
    assert task(sources(service).snapshot(), "io:a:").state_text == f"paused: {PAUSED_MISMATCH}"
    assert task(sources(service).snapshot(), "io:b:").state_text == f"held: {PAUSED_MISMATCH}"
    service.mismatch_hold = False
    service.cancel("a")
    row = task(sources(service).snapshot(), "io:a:")
    assert row.state == "stopping" and row.state_text.startswith("stopping (0:0") and "cancel" not in row.actions
    exit_helper(service, running)
    assert not any(row.id.startswith("io:a:") for row in sources(service).snapshot().tasks)
    service.shutdown()


def test_a_retry_held_behind_its_stopping_attempt_is_one_row(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.submit("tab", 0, "/data", "load")
    old = service.active[0]
    old.current_file = "/data/d_txy_forc3.txt"
    old.last_activity = time.monotonic() - 100
    service._tick()  # Timed out: retired, its retry queued behind it.
    assert old in service.retired and len(service.pending) == 1
    rows = [row for row in sources(service).snapshot().tasks if row.folder == "/data"]
    assert len(rows) == 1 and rows[0].state == "stopping"
    assert "Attempt 2 of 3 starts when it exits" in rows[0].details
    service.shutdown()


def test_counts_are_the_status_bars(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(3)
    for name in "abcde":
        service.submit(name, 0, f"/{name}", "scan")
    service.active[1].paused = True
    service.cancel("c")
    counts = sources(service).snapshot().counts
    assert counts.text == service.activity_counts()
    assert (counts.running, counts.paused, counts.queued, counts.stopping) == (1, 1, 2, 1)
    assert counts.text == "1 running · 1 paused · 2 queued · 1 stopping (0 s)"
    service.shutdown()


def test_cache_admin_is_named_by_its_action_and_waiting_saves_are_listed(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    owner = cache.cache_admin("sweep")
    assert owner
    row = task(sources(service, cache).snapshot(), f"io:{owner}:")
    assert (row.title, row.group) == ("Clean up disk cache: sweep", "upkeep")
    monkeypatch.setattr(cache, "quit_entries", lambda: [QuitSave("new shots", "/live", "waiting", None),
                                                       QuitSave("cache save", "/other", "writing", None)])
    saves = [row for row in sources(service, cache).snapshot().tasks if row.id.startswith("save:")]
    assert [(row.folder, row.state, row.group) for row in saves] == [("/live", "queued", "saves")]
    assert saves[0].state_text == "waits for the folder's previous save or load"
    service.shutdown()


def test_a_load_shows_its_tab_progress_clock_and_file(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch, {"tab"})
    cache = get_folder_cache(service)
    explorer = fake_explorer("tab")
    other = fake_explorer("tab2")
    assert cache.submit("tab", 0, "/data", "load", {})
    assert cache.submit("tab2", 1, "/data", "load", {})  # Joins the same job.
    request = service.active[0]
    job = cache.job_of(request.owner)
    assert job is not None
    job.progress = {"total_files": 4, "checked_files": 1, "read_bytes": 25, "total_read_bytes": 100}
    job.current_file = "d_txy_forc2.txt"
    job.clock = LoadClock()
    job.clock.run(time.monotonic() - 3)
    built = sources(service, cache, [("run_7", explorer), ("other", other)]).snapshot()
    row = task(built, f"io:{request.owner}:")
    assert (row.title, row.tab, row.group) == ("Load data", "run_7, other", "loads")
    assert row.progress == Progress(1, 4, 25, 100)
    assert row.progress is not None and row.progress.text() == "1 of 4 files · 25%"
    assert row.elapsed is not None and 2.5 < row.elapsed < 10
    assert "File: d_txy_forc2.txt" in row.details and "Shared by: run_7, other" in row.details
    assert {"cancel", "show", "log"} <= row.actions
    service.shutdown()


def test_a_live_session_lists_its_check_and_auto_convert_under_it(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch, {"tab:live"})
    cache = get_folder_cache(service)
    data = Dataset("/live", "sig", {1: np.zeros((2, 3))}, {"fingerprint": [[1, 10, 100]]}, 0)
    session = LiveSession("/live", time.time() - 30, {1}, data, request="check", checks=4, new=2)
    session.convert = AutoConvert(time.time() - 20, request=True, todo=3, done=1)
    explorer = fake_explorer("tab", [session])
    assert cache.submit("tab:live", 0, "/live", "load", {"live": True})
    request = service.active[0]
    built = sources(service, cache, [("live tab", explorer)]).snapshot()
    parent = task(built, "live:")
    assert parent.id == live_id(explorer, "/live")
    # (LR-7: a check says nothing new on the session's row, and gets a row of its own only after 2 s.)
    assert (parent.state, parent.state_text, parent.tab) == ("waiting", "watching · 2 new shots", "live tab")
    assert "Checking now" in parent.details
    assert {"stop_live", "show"} <= parent.actions and "retry" not in parent.actions
    assert not [row for row in built.tasks if row.id.startswith(f"io:{request.owner}:")]
    request.started -= activity.LIVE_CHILD_SECONDS
    built = sources(service, cache, [("live tab", explorer)]).snapshot()
    check = task(built, f"io:{request.owner}:")
    assert (check.title, check.group, check.parent) == ("Live check", "live", parent.id)
    assert "cancel" not in check.actions and "stop_live" in check.actions
    convert = task(built, "autoconvert:")
    assert (convert.parent, convert.state, convert.state_text) == (parent.id, "running", "converting 1 of 3")
    assert "cancel" in convert.actions
    session.request, session.unsettled, session.convert.request = "", 2, False
    session.convert.waiting = {"d4.txt": ("still being written", "")}
    built = sources(service, cache, [("live tab", explorer)]).snapshot()
    assert task(built, "live:").state_text == "waiting for 2 files to settle"
    assert task(built, "autoconvert:").state == "settling"
    session.error = "the folder can't be read — Retry"
    session.convert.error = "the conversion failed"
    built = sources(service, cache, [("live tab", explorer)]).snapshot()
    assert task(built, "live:").state == "failed" and "retry" in task(built, "live:").actions
    assert task(built, "autoconvert:").state_text == "stopped: the conversion failed"
    service.shutdown()


def test_gui_conversions_and_the_converters_questions(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    running = FolderConversion("/raw", "cache", time.time() - 5, request=True, todo=4, done=2)
    settling = FolderConversion("/raw2", "cache", time.time(), passes=1, waiting=3)
    stopped = FolderConversion("/raw3", "temp", time.time(), error="cancelled")
    finished = FolderConversion("/raw4", "temp", time.time(), finished=True)
    box = SimpleNamespace(windowTitle=lambda: "Convert on a share?", text=lambda: "raw is on a share.\nConvert?")
    explorer = fake_explorer("tab", conversions={"/raw": running, "/raw2": settling, "/raw3": stopped,
                                                 "/raw4": finished}, convert_box=box)
    built = sources(service, cache, [("raw tab", explorer)]).snapshot()
    rows = {row.folder: row for row in built.tasks if row.id.startswith("conversion:")}
    assert set(rows) == {"/raw", "/raw2", "/raw3"}
    assert rows["/raw"].id == conversion_id(explorer, "/raw")
    assert (rows["/raw"].state, rows["/raw"].progress) == ("running", Progress(2, 4, noun="shot"))
    assert "cancel" in rows["/raw"].actions
    assert rows["/raw2"].state_text == "waiting for 3 files to settle"
    assert rows["/raw3"].state == "failed" and "retry" in rows["/raw3"].actions
    question = task(built, "question:")
    assert (question.title, question.state_text, question.group) == (
        "Question: Convert on a share?", "waiting for your answer", "convert")
    assert "answer" in question.actions and "raw is on a share." in question.details
    service.shutdown()


# The analysis runner, scripts and the cache move

class Blocking(DatasetAnalysis):
    """Computes once released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()

    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata("Blocking", "test", "Tests", __file__, "tests.blocking", "3")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        self.entered.set()
        self.release.wait(10)
        return 1

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return QLabel(str(result.data), parent)


def test_runner_jobs_are_queued_running_and_stopping(qtbot: QtBot) -> None:
    runner = AnalysisRunner()
    first, second = Blocking(), Blocking()
    data = {1: np.zeros((2, 3))}
    data[1].setflags(write=False)
    view = build_view(Dataset("/data/run", "sig", data, {"fingerprint": [[1, 101, 1001]], "loaded_at": 1.0e9}, 0))
    try:
        one = runner.submit(first, first.get_metadata(), "Plot", view, owner="p1")
        two = runner.submit(second, second.get_metadata(), "Plot", view, owner="p2")
        assert first.entered.wait(10)
        jobs = runner.jobs()
        assert [(job.job_id, job.state, job.owner) for job in jobs] == [(one.job_id, "running", "p1"),
                                                                        (two.job_id, "queued", "p2")]
        assert jobs[0].started_at is not None and jobs[1].started_at is None
        runner.cancel(one.job_id)
        assert runner.jobs()[0].state == "stopping"
        rows = activity.analysis_tasks(runner.jobs(), time.monotonic(), tab=lambda owner: {"p1": "Counts (1)"}.get(owner, ""))
        assert [(row.state, row.state_text, row.tab) for row in rows] == [
            ("stopping", "stopping", "Counts (1)"), ("queued", "queued (1st)", "")]
        assert "cancel" not in rows[0].actions and "cancel" in rows[1].actions and "show" in rows[0].actions
    finally:
        first.release.set()
        second.release.set()
        runner.stop()
    assert runner.jobs() == ()


def test_analysis_rows_from_plain_run_records() -> None:
    now = time.monotonic()
    jobs = [RunInfo("a1", "p1", "tests.blocking v3", "Plot", True, "running", now - 4, time.time() - 4, now - 2,
                    time.time() - 2)]
    row = activity.analysis_tasks(jobs, now, tab=lambda owner: "Plot one")[0]
    assert (row.title, row.state, row.state_text, row.group) == ("tests.blocking v3: Plot", "running", "computing",
                                                                  "analysis")
    assert row.elapsed is not None and 1.5 < row.elapsed < 3 and "following Live" in row.details[0]
    assert row.route == activity.Route("analysis", "p1", job="a1")


def test_script_probes_and_a_waiting_reload(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    panel = SimpleNamespace(probe_activity=lambda: [("/scripts/a", "importing", time.monotonic() - 2),
                                                    ("/scripts/b", "queued", None)],
                            reload_waiting=lambda: (["/scripts/a"], 2), probe_limits=lambda: (60.0, 10.0))
    built = sources(service, scripts=lambda: panel).snapshot()
    rows = [row for row in built.tasks if row.group == "scripts"]
    assert [(row.folder, row.state, row.state_text) for row in rows] == [
        ("/scripts/a", "running", "test-importing"), ("/scripts/b", "queued", "queued"),
        ("/scripts/a", "waiting", "waits for 2 runs to end")]
    assert rows[0].details[1] == "Its own time limits end it (60 s to start, 10 s to import)"  # (AW-8.)
    service.shutdown()


def test_the_cache_move_and_its_steps(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    mover = SimpleNamespace(owner="cache-move-1", running=True, moving=True, switched_folder=False, busy=True,
                            method="copy", source="/old", target="/new")
    service.submit("cache-move-1", 1, "/old", "cache_move", {"move": {"action": "move"}})
    built = sources(service, cache, mover=lambda: mover).snapshot()
    move = task(built, "move")
    assert (move.state_text, move.group) == ("moving to /new", "upkeep") and "cancel" in move.actions
    step = task(built, "io:cache-move-1:")
    assert (step.parent, step.title) == ("move", "Move disk cache") and "cancel" in step.actions
    service.shutdown()


def test_the_snapshot_is_ordered_by_group(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(4)
    service.submit("x", 0, "/x", "raw_fill")
    service.submit("y", 0, "/y", "scan")
    service.submit("z", 0, "/z", "convert")
    groups = [row.group for row in sources(service).snapshot().tasks]
    assert groups == ["loads", "convert", "upkeep"]
    service.shutdown()


def paused_text(service: IOService, request: IORequest, cache: Optional[FolderCache] = None) -> str:
    return sources(service, cache).why_paused(request)


def test_the_user_hold_is_named(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.submit("a", 0, "/a", "scan")
    service.set_user_hold(True)
    assert paused_text(service, service.active[0]) == PAUSED_BY_YOU
    assert sources(service).snapshot().user_paused
    service.shutdown()


def test_a_live_sessions_quick_work_has_no_rows_and_its_state_changes_with_new_shots() -> None:
    """LR-7 (Tony (a), 2026-11-05): at a 0.5 s check interval the rows stay put. A Live session's own
    helper work gets a row only after ``LIVE_CHILD_SECONDS`` or while paused, stalled or failed; other rows
    and a stopped session's work are left as they are. The session's state names new shots, by clock time."""
    from helab.utils.activity import LIVE_CHILD_SECONDS, Route, Task, quiet_live
    from helab.views.ActivityWindow import watching_text

    def row(name: str, state: str = "running", elapsed: float | None = 0.3, parent: str = "live:a") -> Task:
        return Task(name, "live", name, "/live", "tab", state, state, elapsed=elapsed,  # type: ignore[arg-type]
                    route=Route("io", name), parent=parent)

    rows = [row("quick"), row("queued", "queued", None), row("slow", elapsed=LIVE_CHILD_SECONDS),
            row("paused", "paused"), row("stalled", "stalled"), row("failed", "failed"),
            row("other session", parent="live:b"), row("top", parent="")]
    assert [task.id for task in quiet_live(rows, {"live:a"})] == ["slow", "paused", "stalled", "failed",
                                                                  "other session", "top"]
    data = Dataset("/live", "sig", {}, {"fingerprint": []}, 0)
    session = LiveSession("/live", time.time(), set(), data)
    assert watching_text(session) == "watching · no new shots yet"
    session.new, session.new_at = 1, time.mktime((2026, 11, 5, 14, 2, 31, 0, 0, -1))
    assert watching_text(session) == "watching · 1 new shot · last 14:02:31"


def test_an_auto_convert_pass_with_nothing_to_convert_leaves_its_row_as_it_was(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """LR-7: auto-convert runs a pass with each check; one with no shots to convert says nothing new."""
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    data = Dataset("/live", "sig", {}, {"fingerprint": []}, 0)
    session = LiveSession("/live", time.time(), set(), data)
    session.convert = AutoConvert(time.time(), request=True, converted=5)
    explorer = fake_explorer("tab", [session])
    convert = task(sources(service, cache, [("live tab", explorer)]).snapshot(), "autoconvert:")
    assert (convert.state, convert.state_text, convert.progress) == ("waiting", "converted 5 · converts with each check",
                                                                     None)
    session.convert.todo = 2
    convert = task(sources(service, cache, [("live tab", explorer)]).snapshot(), "autoconvert:")
    assert (convert.state, convert.state_text) == ("running", "converting 0 of 2")
    service.shutdown()


def test_an_auto_convert_rows_waiting_note_says_when_it_was_once_no_conversion_followed(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """The lab's "waiting for a very old d raw to settle": the row's waiting note is the last conversion's. Once
    no conversion has followed it for longer than Live's backstop allows, it says when it was so."""
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    data = Dataset("/live", "sig", {}, {"fingerprint": []}, 0)
    session = LiveSession("/live", time.time(), set(), data)
    session.convert = AutoConvert(time.time(), waiting={"d2392.txt": ("settling", "")}, summary_at=time.time() - 5)
    explorer = fake_explorer("tab", [session])
    convert = task(sources(service, cache, [("live tab", explorer)]).snapshot(), "autoconvert:")
    assert (convert.state, convert.state_text) == ("settling", "waiting for 1 raw file to settle")
    session.convert.summary_at = at = time.mktime((2026, 11, 11, 16, 38, 50, 0, 0, -1))
    convert = task(sources(service, cache, [("live tab", explorer)]).snapshot(), "autoconvert:")
    assert (convert.state, convert.state_text) == ("settling", "waiting for 1 raw file to settle (as of 16:38:50)")
    assert time.time() - at > 60
    service.shutdown()


def test_the_status_bars_live_phrase_changes_only_when_shots_come_in() -> None:
    """LR-9 (Tony 2026-11-05): steady while Live only checks; it says so while it reads, converts or saves."""
    from helab.views.explorer_live import live_brief
    data = Dataset("/live", "sig", {}, {"fingerprint": []}, 0)
    session = LiveSession("/live", time.time(), set(), data, new=12)
    assert live_brief(session, "run_1") == "Live checking run_1 · 12 new shots"
    session.request = "check"  # (A check that finds nothing says the same.)
    assert live_brief(session, "run_1") == "Live checking run_1 · 12 new shots"
    session.convert = AutoConvert(time.time(), request=True)  # (A pass with nothing to convert too.)
    assert live_brief(session, "run_1") == "Live + auto-convert checking run_1 · 12 new shots"
    session.convert.todo, session.convert.done = 3, 1
    assert live_brief(session, "run_1") == "Live auto-converting run_1 · 1 of 3"
    session.reading = True
    assert live_brief(session, "run_1") == "Live updating run_1 · reading new shots"
    session.reading, session.request, session.convert = False, "save", None
    assert live_brief(session, "run_1") == "Live saving run_1 · 12 new shots"


def test_the_status_bars_live_phrase_names_the_latest_shot_and_its_age() -> None:
    """LR-11 (Tony 2026-11-05): "· latest shot 1235 · 12 s ago" from the data in memory, the one part
    that ticks; a TXY file's time says so; none before the first shot, no age without a time."""
    from helab.views.explorer_live import latest_shot, live_brief
    taken = 1_700_000_000.0
    data = Dataset("/live", "sig", {1234: np.zeros((1, 3)), 1235: np.zeros((1, 3))},
                   {"fingerprint": [[1234, 10, 5], [1235, 10, 6]],
                    "raw_times": [[1234, int((taken - 30) * 1e9)], [1235, int(taken * 1e9)]]}, 0)
    session = LiveSession("/live", taken, set(data.data), data, new=12)
    steady = "Live checking run_1 · 12 new shots · latest shot 1235"
    assert live_brief(session, "run_1", taken + 12) == f"{steady} · 12 s ago"
    assert live_brief(session, "run_1", taken + 75) == f"{steady} · 1 min 15 s ago"
    session.request, session.reading = "check", True
    assert live_brief(session, "run_1", taken + 13) == "Live updating run_1 · reading new shots · latest shot 1235 · 13 s ago"
    # A new shot (new data) is found again; one without a raw file has its TXY file's time.
    session.dataset = Dataset("/live", "sig", {**data.data, 1236: np.zeros((1, 3))},
                              {**data.metadata, "fingerprint": [*data.metadata["fingerprint"],
                                                                [1236, 10, int((taken + 20) * 1e9)]]}, 0)
    session.shots, session.reading = set(session.dataset.data), False
    assert latest_shot(session) == (1236, taken + 20, True)
    assert live_brief(session, "run_1", taken + 25).endswith(" · latest shot 1236 · 5 s ago, TXY file time")
    session.dataset = Dataset("/live", "sig", {1237: np.zeros((1, 3))}, {"fingerprint": []}, 0)
    session.shots = {1237}
    assert live_brief(session, "run_1", taken) == "Live checking run_1 · 12 new shots · latest shot 1237"
    session.dataset, session.shots = Dataset("/live", "sig", {}, {"fingerprint": []}, 0), set()
    assert live_brief(session, "run_1", taken) == "Live checking run_1 · 12 new shots"
