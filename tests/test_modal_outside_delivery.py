"""GT-1: no modal box, dialog or menu is opened while IOService or the analysis runner delivers results.

A box's ``exec()`` inside a slot of IOService's timer (``_tick``) runs a nested event loop in which that timer
never fires again: every helper's events, slot frees and timeouts stop until the box is answered. Code reached
from a delivery opens its box through ``gui_delivery.outside``, once the delivery has returned. Each of the
audit's paths is driven here from inside a delivery; conftest's ``no_modal_in_delivery`` fails any other.
"""
from __future__ import annotations

import os
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from helab.utils import data_roots, gui_delivery
from helab.utils.folder_cache import FolderCache
from helab.utils.io_service import IORequest, IOService
from helab.views.DataRootDialogs import ManualMarkerDialog
from helab.views.HelabMainWindow import HelabMainWindow
from test_cache_mover import Run, keep_cache_dir  # noqa: F401  (keep_cache_dir: a fixture)
from test_large_folder import frozen, make_explorer, select


def heartbeats_during_a_box(qtbot: QtBot, deferred: bool) -> int:
    """Another request's heartbeats a real IOService delivers while a 0.4 s nested loop (a box's ``exec()``)
    runs, opened from a ``resultReady`` slot directly or through ``gui_delivery.outside``."""
    service = IOService()
    asker = IORequest("dialog-owner", 0, "/nowhere/a", "list", {}, 60.0)
    other = IORequest("live-owner", 0, "/nowhere/b", "live", {}, 60.0)
    during: list[float] = []
    state = {"in_loop": False, "opened": False, "closed": False}

    def box() -> None:
        loop = QEventLoop()
        QTimer.singleShot(400, loop.quit)
        state["in_loop"] = True
        loop.exec()
        state["in_loop"], state["closed"] = False, True

    def slot(request: IORequest, event: dict[str, Any]) -> None:
        if request is asker and not state["opened"]:
            state["opened"] = True
            gui_delivery.outside(box) if deferred else box()
        elif request is other and state["in_loop"]:
            during.append(time.monotonic())

    service.resultReady.connect(slot)
    stop = threading.Event()

    def reader() -> None:  # (A helper's reader thread: a heartbeat every 20 ms.)
        while not stop.is_set():
            service._put(other, {"kind": "heartbeat"})
            time.sleep(0.02)
    thread = threading.Thread(target=reader, daemon=True)
    try:
        service._put(asker, {"kind": "entries", "entries": []})
        thread.start()
        qtbot.waitUntil(lambda: state["closed"], timeout=5000)
    finally:
        stop.set()
        thread.join()
        service.shutdown()
    return len(during)


def test_a_box_opened_outside_the_delivery_leaves_every_helpers_events_flowing(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # (The nested loop here is a plain QEventLoop, which the guard doesn't watch.)
    assert heartbeats_during_a_box(qtbot, deferred=True) >= 5
    assert heartbeats_during_a_box(qtbot, deferred=False) == 0  # (What GT-1 found.)


def test_outside_runs_at_once_unless_a_result_is_being_delivered(qtbot: QtBot) -> None:
    ran: list[str | None] = []
    gui_delivery.outside(lambda: ran.append(gui_delivery.current()))
    assert ran == [None]
    with gui_delivery.delivering("io"):
        gui_delivery.outside(lambda: ran.append(gui_delivery.current()))
        assert gui_delivery.current() == "io" and ran == [None]
    qtbot.waitUntil(lambda: len(ran) == 2)
    assert ran == [None, None] and gui_delivery.current() is None


def test_the_guard_fails_a_box_opened_inside_a_delivery(no_modal_in_delivery: list[str]) -> None:
    with gui_delivery.delivering("analysis"):
        with pytest.raises(AssertionError, match="QMessageBox.information opened while delivering 'analysis'"):
            QMessageBox.information(None, "title", "text")
    assert len(no_modal_in_delivery) == 1 and "test_modal_outside_delivery.py" in no_modal_in_delivery[0]
    no_modal_in_delivery.clear()  # (Else it fails this test at teardown, as it should any other.)


def test_io_and_a_plots_run_end_are_delivered_inside_the_flag(qtbot: QtBot) -> None:
    from helab.views.plots.instance import AnalysisInstance
    service = IOService()
    seen: list[str | None] = []
    request = IORequest("owner", 0, "/nowhere", "list", {}, 60.0)
    service.resultReady.connect(lambda _request, _event: seen.append(gui_delivery.current()))
    try:
        service._put(request, {"kind": "entries", "entries": []})
        qtbot.waitUntil(lambda: bool(seen))
    finally:
        service.shutdown()
    # (A plot's end of its run: its render and update.)
    plot = types.SimpleNamespace(is_closed=False, job_id="job", _ended=lambda _result: seen.append(gui_delivery.current()))
    AnalysisInstance._finished(plot, types.SimpleNamespace(job_id="job"))  # type: ignore[arg-type]
    assert seen == ["io", "analysis"]


def recording(monkeypatch: pytest.MonkeyPatch, name: str) -> list[tuple[str | None, tuple[Any, ...]]]:
    """``QMessageBox.<name>`` replaced by a recorder of what was being delivered when it was called."""
    calls: list[tuple[str | None, tuple[Any, ...]]] = []

    def record(*args: Any, **kwargs: Any) -> Any:
        calls.append((gui_delivery.current(), args))
        return QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, name, staticmethod(record) if name != "exec" else record)
    return calls


def test_a_large_folders_question_asked_for_from_a_result_waits_for_the_delivery(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """(a) A conversion's end (``explorer_convert._passed``) or Live at launch asks to load a large folder."""
    service, cache = frozen(monkeypatch)
    root = str(tmp_path)
    explorer, asked, answers = make_explorer(qtbot, service, cache, root, {"big": 20_000})
    big = os.path.join(root, "big")
    during: list[str | None] = []
    question = explorer.confirm_large
    assert question is not None

    def confirm(path: str, estimate: int) -> bool:
        during.append(gui_delivery.current())
        return question(path, estimate)
    explorer.confirm_large = confirm
    try:
        select(qtbot, explorer, big)
        assert not asked and explorer.large_state(big) == (20_000, False)
        answers.append(True)
        with gui_delivery.delivering("io"):
            assert explorer.queue_load(big) is False  # (Not yet: "Load anyway…" until asked.)
            explorer.queue_load(big)  # (Asked once.)
            assert not asked
        qtbot.waitUntil(lambda: bool(asked))
        assert asked == [(big, 20_000)] and during == [None]
        assert ("load", big) in cache.jobs and explorer.large_state(big) is None
        # Cancelled before the question: not asked.
        cache.cancel(explorer.model.owner)
        with gui_delivery.delivering("io"):
            explorer.queue_load(big)
            explorer._cancel_count += 1  # (Cancel, as ``cancel_loading`` counts it.)
        QApplication.processEvents()
        assert len(asked) == 1
    finally:
        explorer.close_cleanup()
        service.shutdown()


@pytest.mark.parametrize("failed", ["_folder_prefs_failed", "_folder_constants_failed"])
def test_a_flag_or_constants_save_that_failed_warns_once_the_delivery_returns(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failed: str,
) -> None:
    """(b) ``FolderCache._prefs_not_saved`` / ``_constants_not_saved``, from an admin helper's end."""
    service, cache = frozen(monkeypatch)
    explorer, _, _ = make_explorer(qtbot, service, cache, str(tmp_path), {})
    warned = recording(monkeypatch, "warning")
    try:
        with gui_delivery.delivering("io"):
            getattr(explorer, failed)(str(tmp_path), "the disk is full", explorer.model.owner)
            assert not warned
        qtbot.waitUntil(lambda: bool(warned))
        assert [during for during, _ in warned] == [None] and "the disk is full" in warned[0][1][2]
    finally:
        explorer.close_cleanup()
        service.shutdown()


def test_the_io_traces_answers_wait_for_the_delivery(qtbot: QtBot) -> None:
    """(c) Help › Record I/O trace: the helper's check answered; its questions and notes follow."""
    checked: list[tuple[str | None, dict[str, Any]]] = []
    window = types.SimpleNamespace(_closing=False, _trace_owner="trace", _trace_check=3,
                                   _trace_checked=lambda event: checked.append((gui_delivery.current(), event)))
    event = {"kind": "trace_folder", "problem": "on a network drive (smbfs)", "earlier": []}
    with gui_delivery.delivering("io"):
        HelabMainWindow._on_trace_check(window, IORequest("trace", 3, "/t", "trace_check", {}, 10.0),  # type: ignore[arg-type]
                                        event)
        assert not checked and window._trace_check is None
    qtbot.waitUntil(lambda: bool(checked))
    assert checked == [(None, event)]


def test_the_cache_moves_question_and_reports_wait_for_the_delivery(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """(d) The move's check answered (its question), and a report from a helper's event."""
    run = Run(qtbot, monkeypatch, tmp_path)
    during: list[str | None] = []
    confirm = run.mover.confirm

    def asked(text: str) -> bool:
        during.append(gui_delivery.current())
        return confirm(text)
    run.mover.confirm = asked
    shown = recording(monkeypatch, "exec")
    try:
        run.mover.change(run.target, run.parent)
        with gui_delivery.delivering("io"):
            run.send(run.request("check"), {"kind": "move_check", "problem": "", "method": "copy", "bytes": 1,
                                            "free": 9})
            assert not run.confirmed
        qtbot.waitUntil(lambda: bool(run.confirmed))
        assert during == [None]
        with gui_delivery.delivering("io"):
            run.mover._report("Old cache folder not fully deleted", "It is safe to delete.", [])
            assert not shown
        qtbot.waitUntil(lambda: bool(shown))
        assert [during for during, _ in shown] == [None]
    finally:
        run.close()


def test_a_marker_saved_by_hand_warns_once_the_delivery_returns(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """(e) Save to folder… for a ``.helab-root``: refused, or its helper failed."""
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    folder = str(tmp_path / "share")
    _, contents = data_roots.new_marker(folder)
    dialog = ManualMarkerDialog(None, FolderCache(service), folder, ".helab-root", contents.decode("utf-8"),
                                "Read-only file system")
    qtbot.addWidget(dialog)
    warned = recording(monkeypatch, "warning")
    try:
        request = IORequest(dialog.owner, 0, folder, "save_marker_copy", {}, 10.0)
        with gui_delivery.delivering("io"):
            dialog._result(request, {"kind": "marker_save_refused", "reason": "it is read only"})
            dialog._result(request, {"kind": "error", "message": "the helper stopped"})
            assert not warned
        qtbot.waitUntil(lambda: len(warned) == 2)
        assert [during for during, _ in warned] == [None, None]
        assert "it is read only" in warned[0][1][2] and "the helper stopped" in warned[1][1][2]
    finally:
        service.shutdown()
