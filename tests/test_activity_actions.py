"""The Activity window's actions (Q62.3) through their owners, the Retry guard, the user's Pause background
I/O, and the session history's reports (Q62.4): fakes and an IOService that starts no helper."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, List, Optional, Sequence, cast

import numpy as np
import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtWidgets import QLabel, QWidget

from helab.analysis.dataset_view import build_view
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.runner import AnalysisRunner
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.utils import activity
from helab.utils.activity import Finished, Route
from helab.utils.folder_cache import Dataset, FolderCache, get_folder_cache
from helab.utils.io_service import BACKGROUND, FOREGROUND, USER_HOLD_NOTE, IORequest, IOService
from helab.views.ActivityWindow import STATE_COLUMN, ActivityActions, ActivitySources, ActivityWindow
from helab.views.explorer_convert import FolderConversion
from helab.views.explorer_live import AutoConvert, LiveSession
from helab.views.FolderExplorer import FolderExplorer
from test_live import age_folder, open_loaded, write_shot  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_activity() -> Iterator[None]:
    """``HISTORY`` and ``LOG_LINES_HANDLER`` are module-global: reset around each test, the handler taken
    off the root logger."""
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    yield
    activity.HISTORY.clear()
    activity.LOG_LINES_HANDLER.clear()
    activity.remove_log_lines()


def quiet_service(monkeypatch: pytest.MonkeyPatch, foreground: set[str] | None = None) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_run", lambda request: None)
    service.is_foreground = lambda request: request.owner in (foreground or set())
    return service


def exit_helper(service: IOService, request: IORequest) -> None:
    request.exited.set()
    service.messages.put((request, {"kind": "exit"}))
    service._tick()


class Calls:
    """Records calls by name."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, name: str) -> Any:
        def record(*args: Any) -> Any:
            self.calls.append((name, args))
        return record

    def last(self) -> Any:
        return self.calls[-1] if self.calls else None

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def fake_explorer(calls: Calls, owner: str = "tab", selected: str = "", live: Optional[LiveSession] = None,
                  conversions: dict[str, Any] | None = None) -> Any:
    sessions = [live] if live is not None else []
    live_control = SimpleNamespace(
        live=live, sessions=lambda: sessions, box=None, watching=lambda path: live is not None and live.path == path,
        session=lambda path: live if live is not None and live.path == path else None,
        set_auto_convert=calls("set_auto_convert"),
        live_line=lambda session: ("Live", "", False), convert_line=lambda session: ("", [], False))
    converter = SimpleNamespace(owner=f"{owner}:convert", conversions=conversions or {}, box=None,
                                row=lambda path: ("", ""), clicked=calls("converter.clicked"))
    return SimpleNamespace(model=SimpleNamespace(owner=owner), bg_owner=f"{owner}:bg", live_owner=f"{owner}:live",
                           live_save_owner=f"{owner}:live-save", live_control=live_control, converter=converter,
                           selected_path_globally=selected, cancel_loading=calls("cancel_loading"),
                           retry=calls("retry"), refresh_folder=calls("refresh_folder"),
                           resume_live=calls("resume_live"), stop_live=calls("stop_live"))


def actions_for(service: IOService, cache: FolderCache, tabs: Sequence[tuple[str, Any]] = (), **kwargs: Any) -> ActivityActions:
    sources = ActivitySources(service, cache, lambda: cast(Any, tabs), runners=kwargs.pop("runners", lambda: ()),
                              plots=kwargs.pop("plots", lambda: {}), mover=kwargs.pop("mover", lambda: None))
    sources._index_owners()
    return ActivityActions(sources, **kwargs)


def row(actions: ActivityActions, prefix: str) -> activity.Task:
    return next(task for task in actions.sources.snapshot().tasks if task.id.startswith(prefix))


# Cancel

def test_cancelling_a_tabs_load_goes_through_the_tab_and_shows_stopping_until_its_exit(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch, {"tab"})
    cache = get_folder_cache(service)
    calls = Calls()
    explorer = fake_explorer(calls, selected="/data")
    actions = actions_for(service, cache, [("data", explorer)])
    assert cache.submit("tab", 0, "/data", "load", {})
    request = service.active[0]
    task = row(actions, f"io:{request.owner}:")
    assert "cancel" in task.actions and task.tab == "data"
    assert actions.cancel(task)
    assert calls.names() == ["cancel_loading"]  # (The fake does nothing, so FolderCache's own cancel follows.)
    assert request in service.retired
    stopping = row(actions, f"io:{request.owner}:")
    assert stopping.state == "stopping" and "cancel" not in stopping.actions
    exit_helper(service, request)
    assert not any(task.id.startswith(f"io:{request.owner}:") for task in actions.sources.snapshot().tasks)
    service.shutdown()


def test_cancel_reaches_each_owner(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(4)
    cache = get_folder_cache(service)
    calls = Calls()
    data = Dataset("/live", "sig", {}, {"fingerprint": []}, 0)
    session = LiveSession("/live", time.time(), set(), data)
    explorer = fake_explorer(calls, live=session)
    asked: list[tuple[str, Optional[str], Optional[str]]] = []
    real_cancel = cache.cancel

    def cancel(owner: str, operation: str | None = None, path: str | None = None) -> None:
        asked.append((owner, operation, path))
        real_cancel(owner, operation, path)
    monkeypatch.setattr(cache, "cancel", cancel)
    runner = SimpleNamespace(jobs=lambda: (), cancel=calls("runner.cancel"))
    mover = SimpleNamespace(owner="cache-move-1", busy=True, running=True, moving=True, switched_folder=False,
                            method="copy", source="/old", target="/new", cancel=calls("mover.cancel"))
    actions = actions_for(service, cache, [("live", explorer)], runners=lambda: [runner], mover=lambda: mover)
    assert cache.submit("tab:bg", 0, "/bg", "load", {})
    assert actions.cancel(row(actions, f"io:{service.active[-1].owner}:"))
    assert asked[-1] == ("tab:bg", "load", FolderCache.key("/bg"))
    assert actions.cancel(activity.Task("c", "convert", "Convert", "/raw", "", "running", "",
                                        route=Route("conversion", "tab:convert", "convert", "/raw")))
    assert asked[-1] == ("tab:convert", "convert", "/raw")
    assert actions.cancel(activity.Task("a", "live", "Auto-convert", "/live", "", "running", "",
                                        route=Route("autoconvert", "tab:live", path="/live")))
    assert calls.last() == ("set_auto_convert", (False,))
    assert actions.cancel(activity.Task("j", "analysis", "Plot", "", "", "running", "",
                                        route=Route("analysis", "p1", job="a7")))
    assert calls.last() == ("runner.cancel", ("a7",))
    assert actions.cancel(activity.Task("m", "upkeep", "Move", "", "", "running", "", route=Route("move", "x")))
    assert calls.last() == ("mover.cancel", ())
    service.submit("raw_fill:/folder", 0, "/folder", "raw_fill", {"cache": {}})
    cache._raw_fills.add("raw_fill:/folder")
    fill = service.active[-1]
    assert actions.cancel(row(actions, "io:raw_fill:/folder:"))
    assert fill in service.retired
    service.shutdown()


def test_cancel_all_queued_leaves_saves(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    calls = Calls()
    explorer = fake_explorer(calls)
    actions = actions_for(service, cache, [("tab", explorer)])
    service.submit("blocker", 0, "/first", "details")  # (Takes the one background slot.)
    assert cache.submit("tab", 0, "/a", "scan", {})
    assert cache.submit("tab", 0, "/b", "scan", {})
    assert cache.save("tab:live-save", "/live", {"save_memory": True})
    queued = [task for task in actions.sources.snapshot().tasks if task.state == "queued"]
    assert sorted(task.group for task in queued) == ["loads", "loads", "saves"]
    assert actions.cancel_queued(actions.sources.snapshot()) == 2
    left = [task for task in actions.sources.snapshot().tasks if task.state == "queued"]
    assert [task.group for task in left] == ["saves"]
    service.shutdown()


# Retry, Stop Live, Show

def test_retry_waits_until_the_attempt_it_replaces_has_exited(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    calls = Calls()
    explorer = fake_explorer(calls, selected="/data")
    actions = actions_for(service, cache, [("data", explorer)])
    failed = Finished("io:x", "loads", "Browse folder", "/data/sub", time.time(), "failed", "timed out",
                      owners=("tab",), route=Route("io", "x", "list", "/data/sub"))
    service.submit("x", 0, "/data/sub", "list")
    old = service.active[0]
    service.cancel("x")
    assert old in service.retired and service.unexited("list", "/data/sub")
    assert actions.retry_refusal(failed.route, failed.outcome, failed.owners).startswith("The previous attempt")
    assert not actions.retry(failed.route, failed.folder, failed.owners) and calls.calls == []
    exit_helper(service, old)
    assert not service.unexited("list", "/data/sub")
    assert actions.retry_refusal(failed.route, failed.outcome, failed.owners) == ""
    assert actions.retry(failed.route, failed.folder, failed.owners)
    assert calls.calls == [("refresh_folder", ("/data/sub",))]
    load = Finished("io:y", "loads", "Load data", "/data", time.time(), "failed", owners=("tab",),
                    route=Route("io", "y", "load", "/data"))
    assert actions.retry(load.route, load.folder, load.owners) and calls.last() == ("retry", ())
    other = Finished("io:z", "loads", "Load data", "/other", time.time(), "failed", owners=("tab",),
                     route=Route("io", "z", "load", "/other"))
    assert actions.retry_refusal(other.route, other.outcome, other.owners).startswith("Select the folder")
    assert actions.retry_refusal(load.route, "ok", load.owners) == "Only a failed or cancelled task"
    service.shutdown()


def test_retry_and_stop_live_reach_live_conversions_plots_and_probes(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    calls = Calls()
    session = LiveSession("/live", time.time(), set(), Dataset("/live", "sig", {}, {"fingerprint": []}, 0))
    stopped = FolderConversion("/raw", "cache", time.time(), error="cancelled")
    explorer = fake_explorer(calls, live=session, conversions={"/raw": stopped})
    ran: list[str] = []
    reloaded: list[list[str]] = []
    def run_plot(plot: str) -> bool:
        ran.append(plot)
        return True
    actions = actions_for(service, cache, [("live", explorer)], plots=lambda: {"p1": "Counts (1)"},
                          run_plot=run_plot, reload_scripts=reloaded.append)
    live = Route("live", "tab:live", path="/live")
    assert actions.retry_refusal(live) == "Live isn't stopped by an error"
    session.error = "Folder not found — Retry"
    assert actions.retry(live, "/live") and calls.last() == ("resume_live", ())
    assert actions.stop_live(live) and calls.last() == ("stop_live", ())
    assert not actions.stop_live(Route("live", "tab:live", path="/elsewhere"))
    assert actions.retry(Route("conversion", "tab:convert", "convert", "/raw"), "/raw")
    assert calls.last() == ("converter.clicked", ("/raw",))
    assert actions.retry(Route("analysis", "p1", job="a1"), "") and ran == ["p1"]
    assert actions.retry_refusal(Route("analysis", "p9", job="a1")) == "Its plot is closed"
    assert actions.retry(Route("probe", path="/scripts"), "/scripts") and reloaded == [["/scripts"]]
    service.shutdown()


def test_show_in_tab_and_its_plot(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    shown: list[tuple[Any, str]] = []
    plots: list[str] = []
    explorer = fake_explorer(Calls())
    def show_plot(plot: str) -> bool:
        plots.append(plot)
        return True
    actions = actions_for(service, cache, [("data", explorer)], plots=lambda: {"p1": "Counts (1)"},
                          show_tab=lambda e, p: shown.append((e, p)), show_plot=show_plot)
    entry = Finished("io:q", "loads", "Load data", "/data", time.time(), "failed", owners=("tab",),
                     route=Route("io", "q", "load", "/data"))
    assert actions.show_target(entry.route, entry.owners) and actions.show(entry.route, entry.folder, entry.owners)
    assert shown == [(explorer, "/data")]
    assert actions.show(Route("analysis", "p1", job="a1"), "") and plots == ["p1"]
    assert not actions.show_target(Route("io", "nobody", "load", "/x"))
    service.shutdown()


# The user's hold (Pause background I/O)

def test_the_user_hold_pauses_background_work_but_not_saves_live_or_the_local_lane(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(6)
    service.submit("bg", 0, "/bg", "scan")
    service.submit("save", 0, "/save", "load", {"save": True})
    service.submit("live", 0, "/live", "load", {"live": True})
    service.submit("local", 0, "/cache", "cached")
    lanes = {request.owner: request.lane for request in service.active}
    assert lanes == {"bg": BACKGROUND, "save": BACKGROUND, "live": BACKGROUND, "local": "local"}
    service.set_user_hold(True)
    assert {request.owner for request in service.active if request.pause_requested} == {"bg"}
    assert [service.user_held(request) for request in service.active] == [True, False, False, False]
    service.messages.put((service.active[0], {"kind": "paused"}))
    service._tick()
    assert service.activity_counts() == f"3 running · 1 paused · {USER_HOLD_NOTE}"
    assert "Paused by you (Activity: Resume background I/O):\nCheck folder status: /bg" in service.queue_tooltip()
    service.submit("bg2", 0, "/bg2", "details")
    service.submit("save2", 0, "/save2", "load", {"save": True})
    service.submit("local2", 0, "/cache2", "cached")
    assert [request.owner for request in service.pending] == ["bg2"]  # (A save and a cached read start.)
    service.set_user_hold(False)
    assert not any(request.pause_requested for request in service.active)
    assert not service.pending
    service.shutdown()


def test_the_user_hold_never_pauses_the_current_tab(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch, {"tab"})
    service.submit("tab", 0, "/fg", "load")
    service.submit("tab", 0, "/fg", "list")
    service.set_user_hold(True)
    assert {request.lane for request in service.active} == {FOREGROUND}
    # (The selected load may pause while the tab lists a folder, as always: never for the user's hold.)
    assert not any(service.user_held(request) for request in service.active)
    assert not any(request.pause_requested for request in service.active if request.operation == "list")
    service.submit("tab", 1, "/fg2", "list")  # (Waits for the listing slot, never for the hold.)
    assert not any(service.user_held(request) for request in service.pending)
    service.shutdown()


def test_quitting_lifts_the_user_hold(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    service.set_user_hold(True)
    cache.cancel_for_quit()
    assert not service.user_hold
    cache.quitting = False
    service.shutdown()


def test_the_window_pauses_and_resumes(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    window = ActivityWindow(ActivitySources(service, get_folder_cache(service), mover=lambda: None))
    qtbot.addWidget(window)
    window.show()
    window.pause_button.click()
    assert service.user_hold and window.pause_button.isChecked() and window.pause_button.text() == "Resume background I/O"
    window.pause_button.click()
    assert not service.user_hold and window.pause_button.text() == "Pause background I/O"
    service.shutdown()


# The history's reports

def test_iosevice_reports_each_requests_end_once(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(4)
    service.submit("a", 0, "/a", "scan")
    service.submit("b", 0, "/b", "scan")
    service.submit("c", 0, "/c", "load")
    service.submit("d", 0, "/d", "details")  # (A details scan's success: not kept, AW-2.)
    a, b, c, d = service.active
    service.messages.put((a, {"kind": "done"}))
    service.messages.put((b, {"kind": "error", "message": "Permission denied — Retry"}))
    service.messages.put((d, {"kind": "done"}))
    service._tick()
    service.cancel("c")
    service.cancel("c")
    entries = activity.HISTORY.entries()
    assert [(entry.folder, entry.outcome, entry.message) for entry in entries] == [
        ("/c", "cancelled", ""), ("/b", "failed", "Permission denied"), ("/a", "ok", "")]
    assert entries[1].title == "Check folder status" and entries[1].route == Route("io", "b", "scan", "/b")
    service.shutdown()


def test_a_retried_timeout_isnt_an_end_but_the_last_one_is(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.submit("tab", 0, "/data", "load")
    first = service.active[0]
    first.current_file = "/data/d_txy_forc1.txt"
    first.last_activity = time.monotonic() - 100
    service._tick()
    assert len(activity.HISTORY) == 0  # (Attempt 2 waits behind it.)
    exit_helper(service, first)
    service._dispatch()
    for attempt in (2, 3):
        request = service.active[0]
        request.current_file = "/data/d_txy_forc1.txt"
        request.file_attempts = {"/data/d_txy_forc1.txt": attempt}
        request.attempt = attempt
        request.last_activity = time.monotonic() - 100
        service._tick()
        exit_helper(service, request)
        service._dispatch()
    entries = activity.HISTORY.entries()
    assert [(entry.outcome, entry.attempts) for entry in entries] == [("failed", 3)]
    assert entries[0].message.startswith("File timed out after 3 attempts")
    service.shutdown()


def test_a_live_check_is_kept_only_when_it_fails(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch)
    service.configure_concurrency(2)
    service.submit("tab:live", 0, "/live", "load", {"live": True})
    service.submit("tab:live", 1, "/live", "load", {"live": True})
    ok, broken = service.active
    service.messages.put((ok, {"kind": "done"}))
    service.messages.put((broken, {"kind": "error", "message": "Folder not found"}))
    service._tick()
    assert [(entry.title, entry.outcome, entry.group) for entry in activity.HISTORY.entries()] == [
        ("Live check", "failed", "live")]
    service.shutdown()


class Blocking(DatasetAnalysis):
    def __init__(self, fail: bool = False) -> None:
        self.release = threading.Event()
        self.fail = fail

    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata("Blocking", "test", "Tests", __file__, "tests.blocking", "3")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        self.release.wait(10)
        if self.fail:
            raise RuntimeError("broken")
        return 1

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return QLabel(str(result.data), parent)


def test_the_runner_reports_on_the_gui_thread_and_leaves_out_lives_successes(qtbot: QtBot) -> None:
    runner = AnalysisRunner()
    data = {1: np.zeros((2, 3))}
    data[1].setflags(write=False)
    view = build_view(Dataset("/data/run", "sig", data, {"fingerprint": [[1, 101, 1001]], "loaded_at": 1.0e9}, 0))
    ok, broken, live = Blocking(), Blocking(fail=True), Blocking()
    for script in (ok, broken, live):
        script.release.set()
    try:
        runner.submit(ok, ok.get_metadata(), "Plot", view, owner="p1")
        runner.submit(broken, broken.get_metadata(), "Plot", view, owner="p2")
        runner.submit(live, live.get_metadata(), "Plot", view, owner="p3", live=True)
        qtbot.waitUntil(lambda: len(activity.HISTORY) == 2 and runner.jobs() == (), timeout=10_000)
        qtbot.wait(100)
    finally:
        runner.stop()
    entries = activity.HISTORY.entries()
    assert [(entry.owners, entry.outcome, entry.message) for entry in entries] == [
        (("p2",), "failed", "broken"), (("p1",), "ok", "")]
    assert entries[0].title == "tests.blocking v3: Plot" and entries[0].route.kind == "analysis"


def test_live_off_and_a_gui_conversions_end_are_reported(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                        tmp_path: Path) -> None:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    monkeypatch.setattr("helab.models.SnapshotFileSystemModel.get_io_service", lambda: service)
    run = tmp_path / "run"
    run.mkdir()
    for shot in (1, 2):
        write_shot(run, shot)
    age_folder(run, 120)
    explorer: FolderExplorer = open_loaded(qtbot, service, run, tmp_path)
    path = str(run)
    assert explorer.start_live()
    explorer.stop_live(save=False)
    live = activity.HISTORY.entries()[0]
    assert (live.title, live.folder, live.outcome, live.route) == ("Live", path, "ok",
                                                                   Route("live", explorer.live_owner, path=path))
    converter = explorer.converter
    converter.conversions[path] = FolderConversion(path, "cache", time.time() - 3, request=True)
    converter.event(IORequest(converter.owner, 0, path, "convert", {}, 60.0), {"kind": "error", "message": "broken"})
    entry = activity.HISTORY.entries()[0]
    assert (entry.title, entry.outcome, entry.message, entry.route.kind) == (
        "Convert raw files to TXY", "failed", "broken", "conversion")
    # AW-5: failures that start no helper are reported too.
    cache = explorer.model.cache
    monkeypatch.setattr(cache, "convert", lambda *args, **kwargs: False)
    assert not converter.start(path, "cache")
    entry = activity.HISTORY.entries()[0]
    assert (entry.outcome, entry.message) == ("failed", "the conversion couldn't be queued")
    assert explorer.start_live()
    session = explorer.live_control.live
    assert session is not None
    session.convert = AutoConvert(time.time())
    explorer.live_control._convert_tick(session)
    entry = activity.HISTORY.entries()[0]
    assert (entry.title, entry.outcome, entry.message, entry.route.kind) == (
        "Auto-convert", "failed", "the conversion couldn't be queued", "autoconvert")
    session.convert.error, session.convert.request = "", True
    explorer.live_control._convert_event(session, {"kind": "offline"})
    entry = activity.HISTORY.entries()[0]
    assert (entry.title, entry.message) == ("Auto-convert", "not while working offline")
    explorer.stop_live(save=False)
    explorer.close_cleanup()
    service.shutdown()


def test_probes_and_the_cache_move_report_their_ends(qtbot: QtBot) -> None:
    from PyQt6.QtCore import QObject
    from helab.views.plots.script_tree import FolderProbes, ProbeFailure, _Probe
    holder = QObject()
    probes = FolderProbes(holder)
    item = _Probe("/scripts/a", started=time.monotonic() - 2)
    item.output = ""
    probes._ended(item, ProbeFailure("its import didn't finish within 10 s"))
    entry = activity.HISTORY.entries()[0]
    assert (entry.title, entry.folder, entry.outcome, entry.message) == (
        "Test-import scripts", "/scripts/a", "failed", "its import didn't finish within 10 s")
    assert entry.started is not None and 1 < time.time() - entry.started < 10
    from helab.views.CacheMover import CacheMover
    mover = SimpleNamespace(lock=None, running=True, moving=True, _cancelled=True, move_id="m1", source="/old",
                            target="/new", method="copy", _abort_reason="", owner="cache-move-1",
                            finished=SimpleNamespace(emit=lambda moved: None))
    CacheMover._end(cast(Any, mover), False)
    entry = activity.HISTORY.entries()[0]
    assert (entry.title, entry.outcome, entry.folder) == ("Move disk cache", "cancelled", "/old")


def test_the_windows_buttons_call_the_owners(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    service = quiet_service(monkeypatch, {"tab"})
    cache = get_folder_cache(service)
    calls = Calls()
    explorer = fake_explorer(calls, selected="/data")
    actions = actions_for(service, cache, [("data", explorer)])
    window = ActivityWindow(actions.sources, actions)
    qtbot.addWidget(window)
    assert cache.submit("tab", 0, "/data", "load", {})
    window.show()
    group = window.now.topLevelItem(0)
    assert group is not None and group.child(0) is not None
    window.now.setCurrentItem(group.child(0))
    assert window.buttons["cancel"].isEnabled() and window.buttons["show"].isEnabled()
    assert not window.buttons["stop_live"].isEnabled() and window.buttons["stop_live"].toolTip() == "Only Live"
    window.buttons["cancel"].click()
    assert calls.names() == ["cancel_loading"]
    window.refresh()
    group = window.now.topLevelItem(0)
    child = group.child(0) if group is not None else None
    assert child is not None and child.text(STATE_COLUMN).startswith("stopping")
    assert not window.buttons["cancel"].isEnabled()
    activity.record(Finished("io:q", "loads", "Load data", "/data", time.time(), "failed", "broken", owners=("tab",),
                             route=Route("io", "q", "load", "/data")))
    window.refresh()
    window.tabs.setCurrentWidget(window.history)
    window.history.setCurrentItem(window.history.topLevelItem(0))
    # (Its previous attempt hasn't exited yet: Retry waits.)
    assert not window.buttons["retry"].isEnabled()
    assert window.buttons["retry"].toolTip().startswith("The previous attempt is still stopping")
    exit_helper(service, service.retired[0])
    window.refresh()
    assert window.buttons["retry"].isEnabled()
    window.buttons["retry"].click()
    assert calls.names()[-1] == "retry"
    service.shutdown()


def test_auto_converts_passes_add_no_successes_to_the_history(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """AW-2: Live's auto-convert runs a pass with each check; only a failed one is kept."""
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    for _ in range(20):
        assert cache.submit("tab:live", 0, "/live", "convert", {})
        request = service.active[-1]
        service.messages.put((request, {"kind": "done"}))
        service._tick()
        exit_helper(service, request)
    assert activity.HISTORY.entries() == []
    assert cache.submit("tab:live", 0, "/live", "convert", {})
    request = service.active[-1]
    service.messages.put((request, {"kind": "error", "message": "Permission denied"}))
    service._tick()
    assert [(entry.title, entry.outcome) for entry in activity.HISTORY.entries()] == [
        ("Convert raw files to TXY", "failed")]
    service.shutdown()


def test_cancel_all_queued_never_stops_a_running_task(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """AW-3: a tab's queued selected load is left to the tab's own Cancel (which would also stop the tab's
    running background loads); the running background load goes on, the queued scan is cancelled."""
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    calls = Calls()
    explorer = fake_explorer(calls, selected="/a")
    actions = actions_for(service, cache, [("tab", explorer)])
    assert cache.submit("tab:bg", 0, "/bg", "load", {})
    running = service.active[0]
    assert cache.submit("tab", 0, "/a", "load", {})  # (Queued: the one background slot is taken.)
    assert cache.submit("tab", 0, "/b", "scan", {})
    assert [request.operation for request in service.pending] == ["load", "scan"]
    assert actions.cancel_queued(actions.sources.snapshot()) == 1
    assert "cancel_loading" not in calls.names()
    assert running in service.active and not running.cancelled.is_set()
    assert [(request.operation, request.path) for request in service.pending] == [("load", FolderCache.key("/a"))]
    # (One row's Cancel on it is the tab's Cancel, as the toolbar's.)
    selected = next(task for task in actions.sources.snapshot().tasks if task.folder == FolderCache.key("/a"))
    assert actions.cancel(selected) and calls.names() == ["cancel_loading"]
    service.shutdown()


def test_a_gui_conversions_failed_or_cancelled_pass_is_one_history_entry(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AW-15: a pass of Folder details' conversion that fails, or is cancelled, is the conversion's own entry
    only (its route, its Retry), not IOService's as well; a failed Live auto-convert pass still has one."""
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    monkeypatch.setattr(service, "_run", lambda request: None)
    monkeypatch.setattr("helab.models.SnapshotFileSystemModel.get_io_service", lambda: service)
    run = tmp_path / "run"
    run.mkdir()
    for shot in (1, 2):
        write_shot(run, shot)
    age_folder(run, 120)
    explorer: FolderExplorer = open_loaded(qtbot, service, run, tmp_path)
    path = str(run)
    activity.HISTORY.clear()

    def started(operation: str) -> IORequest:
        request = next(r for r in service.pending if r.operation == operation and r.path == path)
        service._start(request, BACKGROUND)
        return request

    def entries() -> list[tuple[str, str, str]]:
        return [(entry.title, entry.outcome, entry.route.kind) for entry in activity.HISTORY.entries()
                if entry.folder == path]
    converter = explorer.converter
    assert converter.start(path, "cache")
    request = started("convert")
    service.messages.put((request, {"kind": "error", "message": "Permission denied"}))
    service._tick()
    assert entries() == [("Convert raw files to TXY", "failed", "conversion")]
    activity.HISTORY.clear()
    converter.conversions.pop(path)
    assert converter.start(path, "cache")
    request = started("convert")
    converter.close()  # (As closing the tab does: the pass is cancelled.)
    assert entries() == [("Convert raw files to TXY", "cancelled", "conversion")]
    activity.HISTORY.clear()
    exit_helper(service, request)
    # Live's auto-convert reports no pass of its own: IOService's entry is its failure's.
    assert explorer.model.cache.convert(explorer.live_owner, path)
    request = started("convert")
    service.messages.put((request, {"kind": "error", "message": "Permission denied"}))
    service._tick()
    assert entries() == [("Convert raw files to TXY", "failed", "io")]
    assert not explorer.model.cache._self_reported  # (Every mark is taken as its request ends.)
    explorer.close_cleanup()
    service.shutdown()


def test_a_live_pass_left_running_by_a_cancelled_gui_conversion_keeps_its_failure(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """AW-16: the GUI conversion and Live's auto-convert share one pass of a folder; the GUI side is cancelled,
    Live's goes on, so the pass is no longer the conversion's to report: its failure is IOService's entry."""
    service = quiet_service(monkeypatch)
    cache = get_folder_cache(service)
    cache.self_reporting.add("tab:convert")
    assert cache.submit("tab:convert", 0, "/raw", "convert", {})
    assert cache.submit("tab:live", 0, "/raw", "convert", {})  # (Joins the same pass.)
    request = service.active[0]
    assert len(service.active) == 1
    cache.cancel("tab:convert", "convert", FolderCache.key("/raw"))
    assert request in service.active  # (Live still wants it.)
    service.messages.put((request, {"kind": "error", "message": "Permission denied"}))
    service._tick()
    assert [(entry.title, entry.outcome, entry.route.kind) for entry in activity.HISTORY.entries()] == [
        ("Convert raw files to TXY", "failed", "io")]
    assert not cache._self_reported
    service.shutdown()
