"""Caching v2 stage 2, step 3a: loads and Live's save in store-v4 (design addendum §4–§7). A load writes the
folder's TXY layers and its view, never a dataset; a later load reuses the layers and appends only new or
changed shots; a load that finds every shot unchanged rewrites nothing, its new signature included (A40.3);
a cached read is served from the view; a listing marks a layer whose TXY files are gone as the only copy;
Live's save writes only what its layers lack. Store-v3 loads are unchanged (the rest of the suite). Temp
stores only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

import numpy as np

from helab.io_ops.loading import load, read_cached
from helab.io_ops.save_held import save_held
from helab.io_ops import stores
from helab.utils.cache_store import CacheStore


def data_folder(tmp_path: Path, shots: range = range(1, 3)) -> Path:
    source = tmp_path / "data" / "run"
    source.mkdir(parents=True, exist_ok=True)
    for shot in shots:
        write_shot(source, shot)
    return source


def write_shot(source: Path, shot: int, rows: int = 2) -> None:
    (source / f"d{shot}.txt").write_text(f"5,{shot}\n")
    (source / f"d_txy_forc{shot}.txt").write_text("".join(f"{shot}.{i},2,3\n" for i in range(rows)))
    old = time.time() - 600  # (Settled.)
    for name in (f"d{shot}.txt", f"d_txy_forc{shot}.txt"):
        os.utime(source / name, (old, old))


def v4_options(tmp_path: Path) -> dict[str, Any]:
    return {"directory": str(tmp_path / "caches" / "store-v4"), "budget": 8 << 30, "budget_set_at": 1.0}


def run_load(source: Path, tmp_path: Path, options: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
    output = tmp_path / f"artifacts-{time.monotonic_ns()}"
    output.mkdir()
    events: list[dict[str, Any]] = []
    load(str(source), str(output), events.append, options, **kwargs)  # type: ignore[arg-type]
    return events


def first(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(event for event in events if event["kind"] == kind)


def opened(options: dict[str, Any], source: Path) -> CacheStore:
    return stores._cache_store(options["directory"], [str(source)])


def segments(options: dict[str, Any], source: Path) -> list[tuple[int, int]]:
    with opened(options, source) as store:
        key = store._path_key(str(source))
        return [(int(seq), int(count)) for seq, count in store._conn.execute(
            "SELECT seq, all_shots FROM txy_segments WHERE path = ? ORDER BY seq", (key,))]


def test_a_load_writes_layers_and_a_view_and_the_next_one_reuses_them(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    events = run_load(source, tmp_path, options)
    assert first(events, "cache_saved")["cache_info"]["format"] == "txy-views-1"
    with opened(options, source) as store:
        assert store.read_dataset_row(str(source)).missing  # (Q45.4: never a dataset in store-v4.)
        layers = store.txy_layers(str(source)).value or {}
        assert set(layers) == {"matlab"} and sorted(layers["matlab"].entries) == [1, 2]
        assert {entry.kind for entry in layers["matlab"].entries.values()} == {"txy"}
        view = store.read_view(str(source), "", "").value
        assert view is not None and [entry[4] for entry in view.fingerprint] == ["matlab", "matlab"]
    again = run_load(source, tmp_path, options)
    loaded = first(again, "loaded")
    assert loaded["source"] == "disk" and loaded["cached"] and loaded["load_counts"]["read"] == 0
    assert not any(event["kind"] == "cache_saved" for event in again)  # (Nothing new: nothing written.)
    assert segments(options, source) == [(1, 2)]
    memory = [list(entry) for entry in loaded["fingerprint"]]
    quick = first(run_load(source, tmp_path, options, memory=memory, base_signature=loaded["signature"]), "loaded")
    assert quick.get("unchanged") is True  # (The quick check reads the view.)


def test_a_new_shot_appends_a_segment_of_that_shot_alone(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    write_shot(source, 3, rows=5)
    events = run_load(source, tmp_path, options)
    assert first(events, "loaded")["load_counts"]["read"] == 1 and first(events, "cache_saved")
    assert segments(options, source) == [(1, 2), (2, 1)]  # (Shots 1 and 2 aren't written again.)
    with opened(options, source) as store:
        assert len((store.read_txy_shots(str(source), "matlab").value or {})[3]) == 5


def test_a_signature_only_change_rewrites_nothing(tmp_path: Path) -> None:
    """A40.3: every shot unchanged, the folder's signature not the view's (as when a MATLAB TXY arrives for a
    shot taken from HeLab's): the layers are reused whole and only the view's info is written."""
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    with opened(options, source) as store:
        key = store._path_key(str(source))
        (info,) = store._conn.execute("SELECT info FROM txy_views WHERE path = ?", (key,)).fetchone()
        with store.transaction():
            store._conn.execute("UPDATE txy_views SET info = ? WHERE path = ?",
                                (json.dumps({**json.loads(info), "signature": "an older one"}), key))
    events = run_load(source, tmp_path, options)
    loaded = first(events, "loaded")
    assert loaded["cached"] and loaded["load_counts"]["read"] == 0 and segments(options, source) == [(1, 2)]
    with opened(options, source) as store:
        view = store.read_view(str(source), "", "").value
        assert view is not None and view.info["signature"] == loaded["signature"] != "an older one"


def test_a_cached_read_is_served_from_the_view(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    output = tmp_path / "cached"
    output.mkdir()
    events: list[dict[str, Any]] = []
    read_cached(str(source), str(output), events.append, options)  # type: ignore[arg-type]
    shots = [event for event in events if event["kind"] == "shot"]
    assert sorted(event["shot"] for event in shots) == [1, 2] and first(events, "loaded")["disk_cached"]
    assert np.array_equal(np.load(shots[0]["artifact"]), np.array([[shots[0]["shot"] + 0.0, 2, 3],
                                                                   [shots[0]["shot"] + 0.1, 2, 3]]))


def test_a_listing_without_a_layers_files_makes_it_the_only_copy(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    write_shot(source, 3)  # (So a load still has a file.)
    (source / "d_txy_forc1.txt").unlink()
    run_load(source, tmp_path, options, allow_missing=True)
    with opened(options, source) as store:
        assert (store.txy_layers(str(source)).value or {})["matlab"].gone_at is not None


def test_lives_save_writes_only_what_its_layers_lack(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    loaded = first(run_load(source, tmp_path, options), "loaded")
    held_dir = tmp_path / "held"
    held_dir.mkdir()
    for shot in (1, 2):
        np.save(held_dir / f"{shot}.npy", np.array([[shot + 0.0, 2, 3], [shot + 0.1, 2, 3]]), allow_pickle=False)
    sent: list[dict[str, Any]] = []
    save_held(str(source), sent.append, options, loaded["fingerprint"], [], str(held_dir))  # type: ignore[arg-type]
    assert first(sent, "cache_saved") and segments(options, source) == [(1, 2)]  # (Both kept already.)
    write_shot(source, 3)
    info = (source / "d_txy_forc3.txt").stat()
    np.save(held_dir / "3.npy", np.array([[3.0, 2, 3], [3.1, 2, 3]]), allow_pickle=False)
    sent.clear()
    held = [*loaded["fingerprint"], [3, info.st_size, info.st_mtime_ns]]
    save_held(str(source), sent.append, options, held, [], str(held_dir))  # type: ignore[arg-type]
    assert first(sent, "cache_saved") and segments(options, source) == [(1, 2), (2, 1)]


def test_a_cached_read_follows_its_source_and_without_one_the_last_used_view(tmp_path: Path) -> None:
    """The ``cached`` request carries the tab's TXY source (FolderCache, stage 2): its view is read. An older
    request without one reads the folder's view used last."""
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)  # (The priority modes' view, "".)
    run_load(source, tmp_path, options, txy={"source": "matlab-only"})
    with opened(options, source) as store:
        assert sorted(view[0] for view in store.folder_views(str(source))) == ["", "matlab-only"]
        key = store._path_key(str(source))
        with store.transaction():  # (The priority view used last.)
            store._conn.execute("UPDATE txy_views SET last_used = 10 WHERE path = ? AND source = 'matlab-only'", (key,))

    def read(txy: dict[str, Any] | None) -> dict[str, Any]:
        output = tmp_path / f"cached-{time.monotonic_ns()}"
        output.mkdir()
        events: list[dict[str, Any]] = []
        read_cached(str(source), str(output), events.append, options, txy=txy)  # type: ignore[arg-type]
        return first(events, "loaded")
    assert read({"source": "matlab-only"})["txy"]["source"] == "matlab-only"
    assert read(None)["txy"]["source"] != "matlab-only"


def test_folder_cache_sends_the_tabs_source_with_a_cached_read(monkeypatch: Any, tmp_path: Path) -> None:
    from test_raw_fill import frozen
    service, cache = frozen(monkeypatch)
    try:
        assert cache.submit("tab", 0, str(tmp_path), "cached", {"cache": {}})
        request = next(item for item in service.pending if item.operation == "cached")
        assert request.payload["txy"]["source"] == cache.tab_source()
    finally:
        service.shutdown()


def test_a_plots_own_choice_is_cached_quietly_in_store_v4(tmp_path: Path) -> None:
    """Q19.3: a plot's TXY choice (a ``no_cache`` request) is cached under its own view in store-v4, sends none of
    the tab's cache events and never waits for an answer; the folder's Don't cache flag still keeps it RAM only."""
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    choice = {"source": "matlab-only"}
    events = run_load(source, tmp_path, options, no_cache=True, txy=choice)
    loaded = first(events, "loaded")
    assert not any(event["kind"] in ("cache_saved", "disk_cached", "cache_full", "cache_approval") for event in events)
    assert "disk_cached" not in loaded and loaded["disk_cache_pending"] is False
    with opened(options, source) as store:
        assert store.read_view(str(source), "matlab-only", "").found and store.read_view(str(source), "", "").missing
    again = first(run_load(source, tmp_path, options, no_cache=True, txy=choice), "loaded")
    assert again["source"] == "disk" and again["load_counts"]["read"] == 0  # (From its layers now.)
    write_shot(source, 3)
    over = run_load(source, tmp_path, {**options, "budget": 1, "budget_set_at": time.time()}, no_cache=True, txy=choice)
    with opened(options, source) as store:
        assert not store._conn.execute("SELECT 1 FROM pending_saves").fetchone()  # (Never asks.)
        assert 3 not in (store.txy_layers(str(source)).value or {})["matlab"].entries
    assert not any(event["kind"] == "cache_full" for event in over)
    other = data_folder(tmp_path / "other")
    with opened(options, other) as store:
        store.set_prefs(str(other), True, False, time.time())
    run_load(other, tmp_path, options, no_cache=True, txy=choice)
    with opened(options, other) as store:
        assert store.txy_layers(str(other)).value == {} and store.read_view(str(other), "matlab-only", "").missing


def test_a_plots_own_choice_stays_ram_only_in_store_v3(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = {"directory": str(tmp_path / "caches" / "store-v3")}
    run_load(source, tmp_path, options, no_cache=True, txy={"source": "matlab-only"})
    with opened(options, source) as store:
        assert store.read_dataset_row(str(source)).missing
