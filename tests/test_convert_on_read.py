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
