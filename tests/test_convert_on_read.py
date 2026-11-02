"""Caching v2 stage 3a (store-v4 only, R~1): a load converts on read. A raw file without a current HeLab TXY of
the profile asked for is converted in the helper, as the converter would, and kept in the HeLab layer keyed by
the raw file; no TXY text is written (Q19.1) and no raw row (R~2). The source's rule still picks between it and
MATLAB's TXY; an unfinished raw file waits, a damaged one is unreadable; the profile sent whole lets a user
profile convert (A47.1). store-v3 is unchanged. Temp stores only."""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
import pytest

from helab.convert.pipeline import convert_shot
from helab.convert.profile import MATLAB_2019, DetectorProfile
from helab.io_ops.txy_cache import txy_array
from helab.utils import txy_sources

from test_convert_helab import raw_bytes, write_raw
from test_txy_loading import first, opened, run_load, v4_options

HITS = {1: raw_bytes(10_000, 20_000), 2: raw_bytes(10_000, 20_000, 30_000), 3: raw_bytes(40_000)}


def raw_folder(tmp_path: Path, shots: tuple[int, ...] = (1, 2)) -> Path:
    source = tmp_path / "data" / "run"
    source.mkdir(parents=True, exist_ok=True)
    for shot in shots:
        write_raw(source, shot, HITS[shot])
    return source


def asked(source: str = txy_sources.HELAB_ONLY, profile: DetectorProfile = MATLAB_2019,
          whole: bool = False) -> dict[str, Any]:
    txy: dict[str, Any] = {"source": source, "profile_hash": profile.content_hash(), "profile_tag": "m19v1"}
    if whole:
        txy["profile_def"] = profile.to_dict()
    return txy


def expected(shot: int, profile: DetectorProfile = MATLAB_2019) -> Any:
    return txy_array(convert_shot(HITS[shot], profile).txy)


def shots_of(events: list[dict[str, Any]]) -> dict[int, Any]:
    return {event["shot"]: np.load(event["artifact"]) for event in events if event["kind"] == "shot"}


def test_a_load_converts_raw_files_on_read_and_keeps_them_in_the_layer(tmp_path: Path) -> None:
    source = raw_folder(tmp_path)
    options = v4_options(tmp_path)
    events = run_load(source, tmp_path, options, txy=asked())
    loaded = first(events, "loaded")
    shots = shots_of(events)
    assert sorted(shots) == [1, 2] and all(np.array_equal(shots[shot], expected(shot)) for shot in shots)
    assert loaded["load_counts"]["helab_on_read"] == 2 and loaded["load_counts"]["converted"] == 2
    assert not any(event["kind"] == "file_started" for event in events)  # (No TXY file read.)
    assert not list(tmp_path.rglob("d_txy_helab_*"))  # (No text written anywhere, Q19.1.)
    with opened(options, source) as store:
        layer = (store.txy_layers(str(source)).value or {})["helab:" + MATLAB_2019.content_hash()]
        assert {entry.kind for entry in layer.entries.values()} == {"raw"}
        assert not store.raw_rows(str(source)).value  # (R~2: raw_fill's, not the load's.)
    again = run_load(source, tmp_path, options, txy=asked())
    assert first(again, "loaded")["load_counts"].get("converted", 0) == 0  # (Served from the layer.)


def test_the_sources_rule_still_picks_matlabs_txy_where_it_wins(tmp_path: Path) -> None:
    source = raw_folder(tmp_path)
    (source / "d_txy_forc1.txt").write_text("1.5,2,3\n")
    old = time.time() - 600
    os.utime(source / "d_txy_forc1.txt", (old, old))
    options = v4_options(tmp_path)
    shots = shots_of(run_load(source, tmp_path, options, txy=asked(txy_sources.MATLAB_PRIORITY)))
    assert np.array_equal(shots[1], [[1.5, 2, 3]]) and np.array_equal(shots[2], expected(2))
    shots = shots_of(run_load(source, tmp_path, options, txy=asked(txy_sources.HELAB_PRIORITY)))
    assert np.array_equal(shots[1], expected(1)) and np.array_equal(shots[2], expected(2))
    shots = shots_of(run_load(source, tmp_path, options, txy=asked(txy_sources.MATLAB_ONLY)))
    assert sorted(shots) == [1]


def test_an_unfinished_raw_file_waits_and_a_damaged_one_is_unreadable(tmp_path: Path) -> None:
    source = raw_folder(tmp_path, (1,))
    cut = HITS[2][:-3]  # (Ends mid-line: still being written.)
    write_raw(source, 2, cut, mtime=time.time() - 10)
    options = v4_options(tmp_path)
    events = run_load(source, tmp_path, options, txy=asked())
    loaded = first(events, "loaded")
    assert sorted(shots_of(events)) == [1] and 2 not in loaded["problematic"]
    assert loaded["unsettled_files"] >= 1  # (Late: the next load tries again.)
    write_raw(source, 2, cut, mtime=time.time() - 600)  # (Unchanged for long: damaged.)
    loaded = first(run_load(source, tmp_path, options, txy=asked()), "loaded")
    assert 2 in loaded["problematic"]


def test_a_user_profile_converts_on_read_when_sent_whole(tmp_path: Path) -> None:
    """A47.1: a profile the helper doesn't know converts when the request carries it; else no conversion."""
    mine = dataclasses.replace(MATLAB_2019, name="mine", v_perp_x=500_000.0)
    assert mine.content_hash() != MATLAB_2019.content_hash()
    source = raw_folder(tmp_path)
    options = v4_options(tmp_path)
    with pytest.raises(ValueError, match="No current HeLab TXY"):
        run_load(source, tmp_path, options, txy=asked(profile=mine))
    shots = shots_of(run_load(source, tmp_path, options, txy=asked(profile=mine, whole=True)))
    assert sorted(shots) == [1, 2] and np.array_equal(shots[2], expected(2, mine))


def test_store_v3_never_converts_on_read(tmp_path: Path) -> None:
    source = raw_folder(tmp_path)
    options = {"directory": str(tmp_path / "caches" / "store-v3"), "budget": 8 << 30, "budget_set_at": 1.0}
    with pytest.raises(ValueError, match="No current HeLab TXY"):
        run_load(source, tmp_path, options, txy=asked(whole=True))


def test_folder_cache_sends_the_conversion_profile_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_cache_tab import frozen_cache
    service, cache = frozen_cache(monkeypatch)
    try:
        txy = cache.with_txy("/data/run", {})[txy_sources.TXY_FIELD]
        assert DetectorProfile.from_dict(txy["profile_def"]).content_hash() == txy["profile_hash"]
        other = cache.with_txy("/data/run", {txy_sources.TXY_FIELD: {"profile_hash": "other", "source": "helab-only"}})
        assert "profile_def" not in other[txy_sources.TXY_FIELD]
    finally:
        service.shutdown()


# 3b: Live converts on read (S3~4), and A40.2

def live(source: Path, tmp_path: Path, txy: dict[str, Any], memory: list[list[int]] | None = None,
         seen: list[list[int]] | None = None, known: list[list[int]] | None = None,
         origins: dict[str, str] | None = None) -> list[dict[str, Any]]:
    from helab.io_ops.live import live_check
    output = tmp_path / f"live-{time.monotonic_ns()}"
    output.mkdir()
    sent: list[dict[str, Any]] = []
    live_check(str(source), str(output), sent.append, memory=[] if memory is None else memory,  # type: ignore[arg-type]
               known=known, seen=seen, txy=txy, memory_origins=origins)
    return sent


def last_state(sent: list[dict[str, Any]]) -> dict[str, Any]:
    return [event for event in sent if event["kind"] in ("loaded", "live_unchanged")][-1]


def test_live_converts_a_new_raw_shot_on_read_only_in_store_v4(tmp_path: Path) -> None:
    source = raw_folder(tmp_path, (1,))
    for on_read, expect in ((False, []), (True, [1])):
        txy = {**asked(), **({"on_read": True} if on_read else {})}
        first_check = live(source, tmp_path, txy)
        assert not shots_of(first_check)  # (Seen once: read once unchanged a check apart.)
        second = live(source, tmp_path, txy, seen=last_state(first_check)["live_seen"])
        shots = shots_of(second)
        assert sorted(shots) == expect
    assert np.array_equal(shots[1], expected(1)) and not any(event["kind"] == "file_started" for event in second)
    assert last_state(second)["txy"]["on_read"] == [1]
    assert not list(tmp_path.rglob("d_txy_helab_*"))


def test_a_shot_live_converted_on_read_isnt_read_again_when_its_text_appears(tmp_path: Path) -> None:
    source = raw_folder(tmp_path, (1,))
    raw = (source / "d1.txt").stat()
    origin = txy_sources.helab_origin(MATLAB_2019.content_hash())
    beside = source / "d_txy_helab_m19v1_1.txt"  # (Auto-convert wrote it since: the same data by contract.)
    beside.write_bytes(convert_shot(HITS[1], MATLAB_2019).txy)
    newer = time.time() - 120
    os.utime(beside, (newer, newer))
    txy = {**asked(txy_sources.HELAB_PRIORITY), "on_read": True}
    memory = [[1, raw.st_size, raw.st_mtime_ns]]
    sent = live(source, tmp_path, txy, memory, origins={"1": origin})
    sent += live(source, tmp_path, txy, memory, seen=last_state(sent)["live_seen"], origins={"1": origin})
    assert not shots_of(sent) and all(event["kind"] != "file_started" for event in sent)


def test_a_held_helab_shot_whose_new_txy_is_unreadable_keeps_its_held_data(tmp_path: Path) -> None:
    """A40.2: the held data stays until a readable TXY is read, and the unreadable file isn't read again while
    unchanged (``live_failed``, sent back with ``known``)."""
    source = raw_folder(tmp_path, (1,))
    origin = txy_sources.helab_origin(MATLAB_2019.content_hash())
    beside = source / "d_txy_helab_m19v1_1.txt"
    beside.write_bytes(b"1,2,3\n")
    then = time.time() - 300
    os.utime(beside, (then, then))
    memory = [[1, beside.stat().st_size, beside.stat().st_mtime_ns]]
    beside.write_bytes(b"t,x,y\nnot,a,number\n")  # (Converted again: unreadable.)
    now = time.time() - 120
    os.utime(beside, (now, now))
    txy = {**asked(txy_sources.HELAB_ONLY)}
    sent = live(source, tmp_path, txy, memory, origins={"1": origin})
    sent = live(source, tmp_path, txy, memory, seen=last_state(sent)["live_seen"], origins={"1": origin})
    state = last_state(sent)
    assert not shots_of(sent) and state["kind"] == "live_unchanged"
    failed = state["live_failed"]
    assert failed == [[1, beside.stat().st_size, beside.stat().st_mtime_ns]]
    again = live(source, tmp_path, txy, memory, seen=state["live_seen"], known=failed, origins={"1": origin})
    assert not any(event["kind"] == "file_started" for event in again) and last_state(again)["live_failed"] == failed
    beside.write_bytes(b"1.5,2,3\n")  # (A readable one: read, replacing the held data.)
    os.utime(beside, (now + 1, now + 1))
    sent = live(source, tmp_path, txy, memory, known=failed, origins={"1": origin})
    sent = live(source, tmp_path, txy, memory, seen=last_state(sent)["live_seen"], known=failed, origins={"1": origin})
    assert np.array_equal(shots_of(sent)[1], [[1.5, 2, 3]]) and last_state(sent)["live_failed"] == []


def test_lives_session_sends_its_failed_held_shots_back_with_known() -> None:
    from types import SimpleNamespace
    from helab.views.explorer_live import LiveController
    session = SimpleNamespace(seen=[], seen_names=[], listed_mtime=None, identity="x", identity_root=None,
                              held_failed=[])
    LiveController._live_observed(session, {"live_failed": [[1, 2, 3]]})  # type: ignore[arg-type]
    assert session.held_failed == [[1, 2, 3]]
    LiveController._live_observed(session, {"live_seen": []})  # type: ignore[arg-type]
    assert session.held_failed == [[1, 2, 3]]  # (A check that didn't list keeps it.)


def test_folder_cache_asks_live_to_convert_on_read_only_with_store_v4(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    from helab.utils import folder_cache
    from test_cache_tab import frozen_cache
    service, cache = frozen_cache(monkeypatch)
    try:
        assert "on_read" not in cache.with_txy("/data/run", {})[txy_sources.TXY_FIELD]
        monkeypatch.setattr(folder_cache, "store_root", lambda folder: str(tmp_path / "caches" / "store-v4"))
        assert cache.with_txy("/data/run", {})[txy_sources.TXY_FIELD]["on_read"] is True
    finally:
        service.shutdown()


# 3c: what users see (S3~5, S3~6)

def test_folder_cache_says_which_folders_convert_on_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from helab.utils import folder_cache
    from test_cache_tab import frozen_cache
    service, cache = frozen_cache(monkeypatch)
    try:
        assert not cache.converts_on_read("/data/run") and cache.on_read_shots("/data/run", 5, 2) == 0  # (store-v3.)
        monkeypatch.setattr(folder_cache, "store_root", lambda folder: str(tmp_path / "caches" / "store-v4"))
        # (S3R-2: as the load decides. HeLab priority, the default, converts over MATLAB's TXY too: every raw file.)
        assert cache.tab_source() == txy_sources.HELAB_PRIORITY
        assert cache.converts_on_read("/data/run") and cache.on_read_shots("/data/run", 5, 2) == 5
        cache.remember_choices("/data/mp", {"policy": "", "source": txy_sources.MATLAB_PRIORITY, "tag": "",
                                            "source_set_at": 1.0})
        assert cache.on_read_shots("/data/mp", 5, 2) == 3 and cache.on_read_shots("/data/mp", 2, 2) == 0
        cache.remember_choices("/data/ho", {"policy": "", "source": txy_sources.HELAB_ONLY, "tag": "",
                                            "source_set_at": 1.0})
        assert cache.on_read_shots("/data/ho", 2, 2) == 2
        from types import SimpleNamespace
        loaded = SimpleNamespace(metadata={"load_counts": {"txy_matlab": 2, "txy_helab": 1, "helab_on_read": 4}})
        monkeypatch.setattr(cache, "latest_dataset", lambda path, choice=None: loaded)
        assert cache.on_read_shots("/data/run", 5, 2) == 4  # (Its load counted them: a HeLab TXY was read for one.)
        cache.remember_choices("/data/mat", {"policy": "", "source": txy_sources.MATLAB_ONLY, "tag": "",
                                             "source_set_at": 1.0})
        assert not cache.converts_on_read("/data/mat")  # (Its own source reads MATLAB's only.)
        cache.remember_prefs("/data/off", {"no_cache": True, "no_auto_load": False, "set_at": 1.0})
        assert not cache.converts_on_read("/data/off")  # (Not cached: RAM only, no layers to keep them in.)
    finally:
        service.shutdown()


def test_the_wording_names_shots_converted_from_raw() -> None:
    from types import SimpleNamespace
    from helab.models.SnapshotFileSystemModel import SnapshotFileSystemModel
    from helab.views.FolderDetailsPanel import FolderDetailsPanel
    origin = txy_sources.helab_origin("h")
    profiles = {"h": {"name": "matlab-2019", "version": 1}}
    assert txy_sources.describe(txy_sources.HELAB_ONLY, {1: origin, 2: origin}, profiles, 2, 2) == \
        "TXY: HeLab's (matlab-2019 v1), converted from raw"
    assert txy_sources.describe(txy_sources.HELAB_PRIORITY, {1: origin, 2: origin}, profiles, 3, 1) == \
        "TXY: HeLab's (matlab-2019 v1) for 2 of 3 shots (1 converted from raw), MATLAB's for the rest"
    assert txy_sources.describe(txy_sources.HELAB_ONLY, {1: origin, 2: origin}, profiles, 2) == \
        "TXY: HeLab's (matlab-2019 v1)"
    meta = {"load_counts": {"txy_matlab": 0, "txy_helab": 1, "helab_on_read": 2},
            txy_sources.TXY_FIELD: {"profile_tag": "m19v1"}}
    text, tip = FolderDetailsPanel._txy_row(meta)
    assert text == "0 MATLAB · 1 m19v1 · 2 m19v1 converted from raw" and "HeLab m19v1, converted from raw" in tip
    cache = SimpleNamespace(on_read_shots=lambda path, raw, txy: raw - txy)
    node = SimpleNamespace(path="/data/run", raw_count=5, txy_count=2, report=object())
    text = SnapshotFileSystemModel._on_read_text(SimpleNamespace(cache=cache), node)  # type: ignore[arg-type]
    assert text == " · 3 converted when loaded"
    assert txy_sources.on_read_of({txy_sources.TXY_FIELD: {"on_read": [2, 1]}}) == {1, 2}
    assert txy_sources.on_read_of({}) == set()


def test_a_views_on_read_shots_follow_its_revisions() -> None:
    from helab.analysis.dataset_view import DatasetView, ViewIdentity
    origin = txy_sources.helab_origin("h")
    view = DatasetView(ViewIdentity("/data/run", "", "s", "helab-only", "c"), 1,
                       {1: np.zeros((1, 3)), 2: np.zeros((1, 3))}, {}, None, None,  # type: ignore[arg-type]
                       origins={1: origin, 2: origin}, on_read=frozenset({1}))
    assert view.txy_text() == "TXY: HeLab's (profile h) (1 converted from raw)"
    later = view.with_shots({3: np.zeros((1, 3)), 1: np.zeros((1, 3))}, origins={3: origin, 1: origin}, on_read=[3])
    assert later.on_read == frozenset({3}) and later.txy_text().endswith("(1 converted from raw)")


def test_a_raw_file_read_that_stalls_sends_no_heartbeats_of_the_conversion(tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """S3R-1: the raw file is read with a heartbeat per block only, so a share read that hangs times out; the
    converter's ticker covers only the checks and the conversion (as ``convert_folder``)."""
    from helab.io_ops import convert as convert_ops
    from helab.io_ops import txy_cache
    from helab.io_ops.infra import Heartbeat
    source = raw_folder(tmp_path, (1,))
    raw = source / "d1.txt"
    monkeypatch.setattr(Heartbeat, "INTERVAL", 0.02)
    sent: list[dict[str, Any]] = []
    during: list[int] = []
    real = convert_ops._read_raw

    def stalling(shot: Any, beat: Any) -> Any:
        before = len(sent)
        time.sleep(0.3)  # (A share that stops answering mid-file.)
        during.append(len(sent) - before)
        return real(shot, beat)
    monkeypatch.setattr(convert_ops, "_read_raw", stalling)
    outcome, array = txy_cache.convert_raw_file(str(raw), 1, raw.stat().st_size, raw.stat().st_mtime_ns, MATLAB_2019,
                                                "", sent.append)
    assert outcome == txy_cache.CONVERTED and np.array_equal(array, expected(1))
    assert during == [0]  # (No heartbeat while the read hangs.)
