"""Live with auto-convert must never stop picking up shots (2026-11-11: twice in a day, Live went quiet after a
conversion while the GUI thread was slow): a check's answer and its helper's ``done`` can reach the GUI in
different ``IOService._tick`` drains (each drains 8 ms of events at most), and the next check, started between
them, must be a check of its own, not a request joined to the one that has already answered.

Helpers run in-process, as in ``test_live`` and ``test_live_convert``.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.io_ops import convert
from helab.io_ops.fingerprints import DEFAULT_CHECK_LEVEL
from helab.io_ops.live import live_check
from helab.utils.folder_cache import FolderCache
from helab.utils.io_service import IORequest, IOService
from helab.views import explorer_live
from helab.views.FolderExplorer import FolderExplorer
from test_convert_helab import raw_bytes
from test_live import deliver, job_of, producer, service  # noqa: F401
from test_live_convert import check, cycle, of, one_worker, run_convert, watching_raw_folder, write_raw  # noqa: F401


def control_timer_active(explorer: FolderExplorer) -> bool:
    """Whether Live's next check is timed."""
    return explorer.live_control._live_timer.isActive()


def run_check(cache: FolderCache, path: str, tmp_path: Path) -> tuple[IORequest, list[dict[str, Any]]]:
    """``test_live_convert.check``'s first half: the queued Live check, run in-process; its events, not delivered.
    It doesn't convert on read (store-v4's Live does; store-v3's, or a check that listed the folder before the raw
    file settled, doesn't): a new shot reaches the data only through the conversion, as at the lab."""
    request = producer(cache, path, "load")
    payload = request.payload
    assert payload.get("live")
    txy = {**payload["txy"], "on_read": False}
    output = tmp_path / f"artifacts-{time.monotonic_ns()}"
    output.mkdir()
    sent: list[Any] = []
    live_check(path, str(output), sent.append, memory=payload.get("memory"), known=payload.get("known"),
               since=payload.get("live_since"), identity=str(payload.get("identity") or ""),
               seen=payload.get("seen"), check_level=str(payload.get("check_level") or DEFAULT_CHECK_LEVEL),
               listed_mtime=payload.get("listed_mtime"), seen_names=payload.get("seen_names"),
               identity_root=payload.get("identity_root"), recent=payload.get("recent"),
               txy=txy, memory_origins=payload.get("memory_origins"),
               helab_since=payload.get("helab_since"))
    sent.append({"kind": "done"})
    cache.service.pending.remove(request)
    return request, sent


@pytest.mark.parametrize("converted", ["during the check", "after its answer"])
def test_a_check_started_between_an_answer_and_its_done_is_its_own(
        qtbot: QtBot, service: IOService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, converted: str) -> None:
    """The lab's stall: a conversion writes shot 1 while a Live check runs (``check_soon``), or just after it
    answered; that check answers ``live_unchanged`` (it listed the folder before the TXY was renamed in), and its
    ``done`` comes a drain later. The check Live starts at once must reach a helper, and read shot 1."""
    monkeypatch.setattr(convert, "DAMAGED_SECONDS", 1e9)
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache = explorer.model.cache
    session = explorer.live
    assert session is not None
    cycle(qtbot, explorer, path, tmp_path)  # (Records.)
    write_raw(Path(path), 1, raw_bytes(10_000))
    cycle(qtbot, explorer, path, tmp_path)  # (Seen once.)
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs and session.request == "check")
    cache.live_interval = 30.0  # Long: only the converted shot asks for a check soon.

    # The check runs before the conversion renames shot 1's TXY in: it finds nothing new.
    request, sent = run_check(cache, path, tmp_path)
    assert [event["kind"] for event in sent] == ["live_unchanged", "done"]
    answer, done = sent
    if converted == "during the check":
        assert [event["shot"] for event in of(run_convert(cache, path), "shot_converted")] == [1]
        assert session.check_soon
        deliver(cache, request, [answer])
    else:
        deliver(cache, request, [answer])
        assert session.request == ""
        assert [event["shot"] for event in of(run_convert(cache, path), "shot_converted")] == [1]
    # The GUI's event loop runs between the two drains: Live's next tick (0 ms) comes first.
    qtbot.wait(30)
    deliver(cache, request, [done])

    # Live's next check reaches a helper of its own, and finds shot 1's new TXY (read once settled, a check later).
    qtbot.waitUntil(lambda: job_of(cache, path) is not None, timeout=2_000)
    assert session.request == "check"
    answer = of(check(cache, path, tmp_path), "live_unchanged")[0]
    assert [os.path.basename(name) for name in answer["live_seen_names"]] == ["d_txy_helab_m19v1_1.txt"]
    assert session.request == "" and session.seen_names == answer["live_seen_names"]
    assert control_timer_active(explorer)
    explorer.stop_live(save=False)
    explorer.close_cleanup()


def test_a_late_event_of_an_answered_check_never_stops_the_next(
        qtbot: QtBot, service: IOService, tmp_path: Path) -> None:
    """A check's helper failing after its answer (its ``done`` lost: "I/O helper exited unexpectedly") is the old
    check's: the next check, already running, goes on."""
    explorer, path = watching_raw_folder(qtbot, tmp_path, auto_convert=False)
    cache = explorer.model.cache
    session = explorer.live
    assert session is not None
    cache.live_interval = 0.0
    qtbot.waitUntil(lambda: job_of(cache, path) is not None)
    request, sent = run_check(cache, path, tmp_path)
    deliver(cache, request, sent[:-1])
    qtbot.waitUntil(lambda: job_of(cache, path) is not None and job_of(cache, path) is not cache._producers.get(
        request.owner), timeout=2_000)
    assert session.request == "check"
    deliver(cache, request, [{"kind": "error", "message": "I/O helper exited unexpectedly"}])
    assert session.request == "check" and not session.error
    explorer.stop_live(save=False)
    explorer.close_cleanup()


def test_the_backstop_starts_a_check_live_lost(qtbot: QtBot, service: IOService, tmp_path: Path,
                                               caplog: pytest.LogCaptureFixture) -> None:
    """Belt and braces: while Live is on, a check that is thought in flight with no job behind it, or no check
    timed at all, for ``LIVE_STALL_SECONDS``, is logged with Live's state and replaced by a new check."""
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache = explorer.model.cache
    control = explorer.live_control
    session = explorer.live
    assert session is not None
    cache.live_interval = 30.0
    qtbot.waitUntil(lambda: job_of(cache, path) is not None)
    check(cache, path, tmp_path)
    assert session.request == "" and control._live_timer.isActive()

    # Lost: Live thinks a check runs, but none does (and no timer will start one).
    control._live_timer.stop()
    session.request = "check"
    control._live_watch()
    assert job_of(cache, path) is None  # (Not yet: a few intervals first.)
    session.check_started_at -= control.stall_seconds() + 1
    with caplog.at_level(logging.WARNING):
        control._live_watch()
    qtbot.waitUntil(lambda: job_of(cache, path) is not None, timeout=2_000)
    assert session.request == "check"
    assert any("Live: no check started for" in record.getMessage() and "request='check'" in record.getMessage()
               for record in caplog.records), caplog.text

    # A check that runs (its job is there) is the helper's to time out: never replaced beside itself.
    caplog.clear()
    session.check_started_at -= control.stall_seconds() + 1
    job = job_of(cache, path)
    control._live_watch()
    assert job_of(cache, path) is job and not caplog.records

    # A conversion thought in flight with no job behind it ends, and the next tick converts again.
    check(cache, path, tmp_path)
    convert_state = session.convert
    assert convert_state is not None
    cache.cancel(explorer.live_owner, "convert", path)
    convert_state.request, convert_state.error = True, ""
    convert_state.requested_at -= control.stall_seconds() + 1
    with caplog.at_level(logging.WARNING):
        control._live_watch()
    assert not convert_state.request and "Live auto-convert: no conversion of" in caplog.text

    # No check in flight and none timed: one starts.
    assert session.request == "" and job_of(cache, path) is None
    control._live_timer.stop()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        control._live_watch()
    qtbot.waitUntil(lambda: job_of(cache, path) is not None, timeout=2_000)
    assert "request='', reading=False, check_soon=False, timer=False" in caplog.text
    explorer.stop_live(save=False)
    assert not control._watch_timer.isActive()
    explorer.close_cleanup()


def test_a_raw_file_live_cant_read_ends_unconvertible_and_a_new_session_tries_it_again(
        qtbot: QtBot, service: IOService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A raw file locked for good (a writer's or an antivirus's lock) stops being waited on: unconvertible
    (``read_failed``) once unchanged and unreadable for ``DAMAGED_SECONDS``, said on the Live line and in its
    tooltip, skipped by this auto-convert while unchanged, and tried again by the next (a new Live session, or
    auto-convert off and on), so a lock never loses a shot for good."""
    monkeypatch.setattr(convert, "DAMAGED_SECONDS", 0.0)  # (At its first failed read.)
    original = convert._read_raw

    def locked(shot: Any, beat: Any) -> bytes | str:
        if shot.shot == 1:
            raise PermissionError(13, "Permission denied", shot.path)
        return original(shot, beat)
    monkeypatch.setattr(convert, "_read_raw", locked)
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache = explorer.model.cache
    session = explorer.live
    assert session is not None and session.convert is not None
    cycle(qtbot, explorer, path, tmp_path)  # (Records.)
    write_raw(Path(path), 1, raw_bytes(10_000))
    cycle(qtbot, explorer, path, tmp_path)  # (Seen once.)
    _, sent = cycle(qtbot, explorer, path, tmp_path)
    [refused] = of(sent, "shot_unconvertible")
    assert refused["reason"] == convert.READ_FAILED and refused["message"].startswith("Couldn't be read for ")
    assert session.convert.unconvertible == {"d1.txt": refused["message"]} and not session.convert.waiting
    text = explorer.live_control.convert_line(session)[0]
    assert "1 unconvertible" in text and "waiting" not in text, text
    tooltip = "\n".join(explorer.live_control.convert_line(session)[1])
    assert "Can't be converted (1): d1.txt: Couldn't be read for" in tooltip
    assert "d1.txt: couldn't be read; Live off and on, or Convert this folder…, tries it again." in tooltip
    # This auto-convert skips it while unchanged.
    request, _ = cycle(qtbot, explorer, path, tmp_path)
    assert [entry[0] for entry in request.payload["skip"]] == ["d1.txt"]
    # Off and on (or a new Live session): its first conversion tries it again.
    explorer.live_control.set_auto_convert(False)
    time.sleep(0.01)  # (A later start than the refusal's, on any clock's resolution.)
    explorer.live_control.set_auto_convert(True)
    request, sent = cycle(qtbot, explorer, path, tmp_path)
    assert request.payload["skip"] == []
    assert [event["raw_name"] for event in of(sent, "shot_waiting")] == ["d1.txt"]  # (Not in seen: a second look.)
    explorer.stop_live(save=False)
    explorer.close_cleanup()


def test_the_low_count_threshold_is_read_once_until_it_is_set_or_settings_close(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The Live line and Folder details ask for it with each render (28 of the lab's stall stacks read it from
    Settings): read once, then from memory, until the Auto-convert menu sets it or Settings close (Save, or
    Reset all, which clears the store underneath)."""
    from types import SimpleNamespace
    from helab.utils.settings_defaults import CONVERT_LOW_HITS_SETTING
    from helab.utils.settings_store import app_settings
    from helab.views import HelabMainWindow as main_window
    from helab.utils.settings_defaults import read_setting
    reads: list[str] = []

    def counted(settings: Any, key: str, **kwargs: Any) -> Any:
        reads.append(key)
        return read_setting(settings, key, **kwargs)
    monkeypatch.setattr("helab.views.explorer_live.read_setting", counted)
    explorer_live.forget_low_hits()
    assert explorer_live.low_hits_threshold() == 100 and explorer_live.low_hits_threshold() == 100
    assert reads == [CONVERT_LOW_HITS_SETTING]
    explorer_live.set_low_hits_threshold(7)
    assert explorer_live.low_hits_threshold() == 7 and len(reads) == 2
    app_settings().clear()  # (Settings › Reset all.)
    assert explorer_live.low_hits_threshold() == 7  # (Memory, until Settings close.)
    fake = SimpleNamespace(settle_seconds=None)
    monkeypatch.setattr(main_window, "get_io_service", lambda: fake)
    monkeypatch.setattr(main_window, "get_folder_cache", lambda service: SimpleNamespace())
    main_window.HelabMainWindow._apply_live_settings(app_settings())
    assert explorer_live.low_hits_threshold() == 100 and len(reads) == 3


def test_a_plots_source_line_is_set_only_when_it_changes(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """The main window asks with every change of Folder details (29 of the lab's stall stacks were in it): what the
    line shows is worked out from the dock's properties, and its labels are set only when that changes, found among
    their wrapper's own children (never by searching the plot's widget tree). A replaced plot's content gets its
    lines anew."""
    from PyQt6.QtWidgets import QDockWidget, QLabel, QWidget
    from helab.views.ElidedLabel import ElidedLabel
    from helab.views.plots.workspace import PlotWorkspace
    sets: list[str] = []
    original = ElidedLabel.setText

    def counted(self: ElidedLabel, text: str | None) -> None:
        sets.append(text or "")
        original(self, text)
    monkeypatch.setattr(ElidedLabel, "setText", counted)
    dock = QDockWidget()
    qtbot.addWidget(dock)
    content = QWidget()
    for _ in range(50):
        QLabel("a plot's own label", content)
    PlotWorkspace._wrap_plot(dock, content)
    dock.setProperty("dataSourcePath", "/data/run_1")
    dock.setProperty("plotSourceRevision", "revision 1")
    sets.clear()
    for _ in range(5):
        PlotWorkspace._update_plot_source_label(dock, None)
    assert sets == ["Showing previously loaded data: run_1 · revision 1"]
    label = dock.findChild(QLabel, "plot_data_source")
    assert label is not None and label.toolTip() == "/data/run_1"
    dock.setProperty("plotSourceRevision", "revision 2")
    dock.setProperty("plotError", "no totals")
    PlotWorkspace._update_plot_source_label(dock, None)
    assert sets[-1].endswith("revision 2") and dock.property("plotSourceText") == sets[-1]
    error = dock.findChild(QLabel, "plot_error")
    assert error is not None and error.text() == "⚠ no totals" and not error.isHidden()
    PlotWorkspace._wrap_plot(dock, QWidget())  # (A released plot's picture in its place.)
    sets.clear()
    PlotWorkspace._update_plot_source_label(dock, None)
    assert sets == ["Showing previously loaded data: run_1 · revision 2"]


@pytest.mark.parametrize("answer", ["shots_missing", "too_large"])
def test_a_retry_clicked_between_a_stopping_answer_and_its_done_is_its_own(
        qtbot: QtBot, service: IOService, tmp_path: Path, answer: str) -> None:
    """The cause's kin: a check that stops Live (shots missing, or too large) answers before its helper's ``done``;
    Retry clicked in between must start a check of its own, never join the one that has already answered."""
    explorer, path = watching_raw_folder(qtbot, tmp_path, auto_convert=False)
    cache = explorer.model.cache
    session = explorer.live
    assert session is not None
    cache.live_interval = 30.0
    qtbot.waitUntil(lambda: job_of(cache, path) is not None)
    request = producer(cache, path, "load")
    stop: dict[str, Any] = ({"kind": "shots_missing", "reason": "missing", "missing": [1], "missing_count": 1,
                             "known_count": 1, "listed_count": 0} if answer == "shots_missing"
                            else {"kind": "too_large", "estimate": 10**12, "refused": True})
    cache.service.pending.remove(request)
    deliver(cache, request, [stop])
    assert session.error and session.request == "" and job_of(cache, path) is None
    explorer.live_control.resume_live()  # (Retry, in the drain gap.)
    qtbot.waitUntil(lambda: job_of(cache, path) is not None, timeout=2_000)
    retry = job_of(cache, path)
    deliver(cache, request, [{"kind": "done"}])  # (The answered check's, late: to no one.)
    assert job_of(cache, path) is retry and session.request == "check" and not session.error
    explorer.stop_live(save=False)
    explorer.close_cleanup()
