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
