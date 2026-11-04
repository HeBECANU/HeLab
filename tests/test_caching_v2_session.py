"""Caching v2's integration check (stage 1, step 7), the ``store_v4`` switch on, in temp stores: one session
as the helpers run it. Load, ``raw_fill``, each raw layer equal to its file (the TXY made from the layer is
the file's byte for byte), Clear, Make room's order (other folders' datasets, then raw layers whose files
are there, then only copies, and exactly what it named), and a cache move with both stores. Through all of
it store-v3 is opened only by ``LegacyStore`` and its files stay as they were (SQLite's ``-wal``/``-shm``
aside). Synthetic data under ``tmp_path`` and the test's own cache folder only."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import time
import traceback
from typing import Any

import numpy as np
import pytest

from helab import cache_cli
from helab.convert import raw_layer
from helab.convert.pipeline import convert_raw
from helab.convert.profile import MATLAB_2019
from helab.convert.reconstruct import reconstruct
from helab.convert.txy import format_txy
from helab.io_ops import stores
from helab.io_ops.admin import cache_admin
from helab.io_ops.loading import load
from helab.io_ops.raw_fill import raw_fill
from helab.utils import cache_move
from helab.utils.cache_move import COPY
from helab.utils.cache_store import CacheStore, txy_item
from helab.utils.folder_cache import store_options

from test_store_v4 import files, switch_on, v3_with_state  # noqa: F401  (switch_on: a fixture)

ROOT = Path(__file__).resolve().parents[1]
CASE = (ROOT / "tests" / "data" / "convert" / "cases" / "basic" / "d1.txt").read_bytes()
OLD = 1_700_000_000


def synthetic(shot: int, rows: int) -> bytes:
    """A raw file of ``rows`` pulses at random times (so its layer doesn't compress to nothing)."""
    rng = np.random.default_rng(shot * rows)
    times = 100_000 * shot + np.cumsum(rng.integers(1, 1 << 20, rows))
    channels = rng.integers(1, 9, rows)
    channels[0] = 5
    return "".join(f"{channel},{time}\r\n" for channel, time in zip(channels.tolist(), times.tolist())).encode()


def folder(data: Path, name: str, raw: dict[int, bytes], txy: bool = False) -> Path:
    path = data / name
    path.mkdir(parents=True)
    for shot, text in raw.items():
        (path / f"d{shot}.txt").write_bytes(text)
        if txy:
            converted = convert_raw(text, MATLAB_2019)
            assert converted
            (path / f"d_txy_forc{shot}.txt").write_bytes(converted)
    for file in path.iterdir():
        os.utime(file, (OLD, OLD))
    return path


def loaded(source: Path, tmp_path: Path, options: dict[str, Any], **changes: Any) -> dict[str, Any]:
    output = tmp_path / f"artifacts-{time.monotonic_ns()}"
    output.mkdir()
    sent: list[dict[str, Any]] = []
    load(str(source), str(output), sent.append, {**options, **changes})  # type: ignore[arg-type]
    [answer] = [event for event in sent if event["kind"] in ("cache_saved", "cache_full", "cache_approval")]
    return answer


def filled(source: Path, options: dict[str, Any]) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []
    raw_fill(str(source), options, sent.append)  # type: ignore[arg-type]
    [done] = [event for event in sent if event["kind"] == "raw_fill_done"]
    return done


def opened(options: dict[str, Any], *sources: Path) -> CacheStore:
    return stores._cache_store(options["directory"], [str(source) for source in sources])


def test_a_session_with_store_v4_live_leaves_store_v3_as_it_was(switch_on: None, private_store: str,  # noqa: F811
                                                                tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    options = store_options()
    assert options["directory"] == os.path.join(private_store, "store-v4")  # (The switch, as the app reads it.)
    caches = Path(private_store)
    v3_with_state(caches)  # (An older HeLab's store beside it.)
    v3 = caches / "store-v3"
    before = files(v3)
    v3_opens: list[str] = []
    connect = sqlite3.connect

    def watched(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        if "store-v3" in str(database) and not any(frame.filename.endswith("legacy_store.py")
                                                   for frame in traceback.extract_stack()):
            v3_opens.append(str(database))
        connection: sqlite3.Connection = connect(database, *args, **kwargs)
        return connection
    monkeypatch.setattr(sqlite3, "connect", watched)
    roots: list[str] = []
    init = CacheStore.__init__

    def recorded(self: CacheStore, root: str, **kwargs: Any) -> None:
        roots.append(root)
        init(self, root, **kwargs)
    monkeypatch.setattr(CacheStore, "__init__", recorded)

    data = tmp_path / "data"
    run = folder(data, "run", {1: CASE, 2: CASE, 3: CASE}, txy=True)

    # Load, then raw_fill (as FolderCache queues it after the save).
    assert loaded(run, tmp_path, options)["kind"] == "cache_saved"
    assert filled(run, options)["saved"] == 3 and filled(run, options)["saved"] == 0  # (Once.)

    # Each layer equals its file: the same bytes read, and the TXY made from the layer is the file's.
    with opened(options, run) as store:
        saved = store.raw_rows(str(run)).value or {}
        assert sorted(saved) == [1, 2, 3]
        for shot in saved:
            read = store.read_raw(str(run), shot).value
            assert read is not None
            row, hlb_bytes = read
            text = (run / f"d{shot}.txt").read_bytes()
            assert row.sha256 == hashlib.sha256(text).hexdigest() and row.size == len(text)
            layer, header = raw_layer.from_hlb(hlb_bytes)
            assert header["meta"]["facts"] == raw_layer.encode(text).facts.to_json()
            assert format_txy(reconstruct(raw_layer.decode(layer), MATLAB_2019)) == convert_raw(
                text, MATLAB_2019) == (run / f"d_txy_forc{shot}.txt").read_bytes()

    # Clear (Settings › Cache's Clear all): every kind, raw pulses and (stage 2) TXY layers too.
    sent: list[Any] = []
    cache_admin(options, "clear", sent.append)
    removed = [event for event in sent if event["kind"] == "removed"]
    assert [kind for event in removed for kind in event["kinds"]][-2:] == ["raw", "txy"]
    assert next(event for event in removed if "raw" in event["kinds"])["raw"] == 3
    with opened(options, run) as store:
        assert store.raw_rows(str(run)).value == {} and store.txy_layers(str(run)).value == {}
        assert store.read_dataset_row(str(run)).missing  # (Stage 2: loads write TXY layers, never datasets.)

    # Make room's order: X's MATLAB layer (its TXY files there), Y's raw layers (files there), Z's (the only copy,
    # gone from its folder).
    x = folder(data, "x", {1: CASE}, txy=True)
    assert loaded(x, tmp_path, options)["kind"] == "cache_saved"
    y = folder(data, "y", {1: synthetic(1, 3000), 2: synthetic(2, 3000)})
    z_text = {1: synthetic(1, 20000), 2: synthetic(2, 20000)}  # (Larger than X and Y together.)
    z = folder(data, "z", z_text)
    assert filled(y, options)["saved"] == 2 and filled(z, options)["saved"] == 2
    for shot in z_text:
        (z / f"d{shot}.txt").unlink()
    filled(z, options)  # (Seen gone: the only copy.)
    held = loaded(run, tmp_path, options, budget=1, budget_set_at=time.time())
    assert held["kind"] == "cache_full"
    pending = held["pending_id"]
    with opened(options, run, x, y, z) as store:
        x_layers = store.txy_layers(str(x)).value or {}
        assert set(x_layers) == {"matlab"} and store.read_dataset_row(str(x)).missing
        x_bytes = x_layers["matlab"].bytes
        y_bytes = sum(row.bytes for row in (store.raw_rows(str(y)).value or {}).values())
        z_bytes = sum(row.bytes for row in (store.raw_rows(str(z)).value or {}).values())
        assert z_bytes > x_bytes + y_bytes
        assert store.inventory()["raw"]["only_copy"] == 2
        everything = store.room_plan(pending, 1 << 40)
        assert everything.possible and everything.items == ()  # (Fits: nothing to remove.)
        # Find the budget that needs X's layer and Y's raw layers, then one that needs part of Z's too.
        # (Stepping the budget down: the first plan that needs Y's raw layers.)
        enough = next(budget for budget in range(store.usage() + held["bytes"], 0, -256)
                      if f"raw:{y}" in store.room_plan(pending, budget).items)
        plan = store.room_plan(pending, enough)
        x_item = txy_item("txy-seen:", str(x), "matlab")
        assert plan.items == (x_item, f"raw:{y}")  # (Z's only copy stays, though it alone would do.)
        deeper = store.room_plan(pending, enough - z_bytes // 2)
        assert deeper.items == (x_item, f"raw:{y}", f"raw-only:{z}")
    sent.clear()
    cache_admin({**options, "budget": enough, "budget_set_at": time.time()}, "adopt", sent.append,
                pending_id=pending, make_room=True, room_paths=list(plan.items))
    [result] = [event for event in sent if event["kind"] == "admin_result"]
    assert result["adopted"] is True
    with opened(options, run, x, y, z) as store:
        assert store.txy_layers(str(run)).value and store.txy_layers(str(x)).value == {}
        assert store.read_dataset_row(str(run)).missing
        assert store.raw_rows(str(y)).value == {} and sorted(store.raw_rows(str(z)).value or {}) == [1, 2]

    # store-v3 as it was, and opened by nothing but LegacyStore.
    assert files(v3) == before
    assert v3_opens == [] and not any(root.endswith("store-v3") for root in roots)

    # A cache move with both stores: each verified, store-v3's files carried as they were.
    app, target = tmp_path / "app", tmp_path / "moved" / "caches"
    record = cache_move.start(str(caches), str(target), str(app), COPY)
    assert set(record["store_ids"]) == {"store-v4", "store-v3"}
    record = cache_move.move(record, str(app), lambda done, total: None, lambda: False)
    assert cache_move.verify(str(target), record["store_id"], record["store_ids"]) == ""
    assert files(target / "store-v3") == before == files(v3)
    assert v3_opens == [] and not any(root.endswith("store-v3") for root in roots)

    # The moved store's only copy still exports (read only) to what Z's raw files held.
    out = tmp_path / "exported"
    assert cache_cli.main(["export", "--folder", str(z), "--cache", str(target), "--out", str(out)]) == 0
    for shot, text in z_text.items():
        with np.load(out / f"d{shot}.npz") as exported:
            assert np.array_equal(exported["time_bins"], raw_layer.columns(raw_layer.encode(text))["time_bins"])


def test_a_stage_2_session_with_layers_leaves_store_v3_as_it_was(switch_on: None, private_store: str,  # noqa: F811
                                                                 tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage 2's integration check (brief step 6), the switch on, as the helpers run it, beside an older HeLab's
    store-v3:
    1. a conversion into the cache folder saves raw layers;
    2. the tab's load makes its HeLab shots from the raw layer (no TXY text read) into a HeLab layer, a plot's
       own choice is cached under its own view, and the next load is served from the layers;
    3. Live's autosaves append a segment each and compact;
    4. Clear all takes layers and raw pulses;
    5. Make room's order: rebuildable HeLab layers, then seen MATLAB layers;
    6. store-v3's files are unchanged and only LegacyStore opens it;
    7. a cache move verifies both stores, and the moved store's TXY layer exports."""
    from helab.io_ops import infra
    from helab.io_ops.convert import convert_folder
    from helab.io_ops.save_held import save_held
    from helab.utils.cache_store import COMPACT_SEGMENTS
    options = store_options()
    assert options["directory"] == os.path.join(private_store, "store-v4") and options["policy"] == "raw+used"
    caches = Path(private_store)
    v3_with_state(caches)
    v3 = caches / "store-v3"
    before = files(v3)
    v3_opens: list[str] = []
    connect = sqlite3.connect

    def watched(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        if "store-v3" in str(database) and not any(frame.filename.endswith("legacy_store.py")
                                                   for frame in traceback.extract_stack()):
            v3_opens.append(str(database))
        connection: sqlite3.Connection = connect(database, *args, **kwargs)
        return connection
    monkeypatch.setattr(sqlite3, "connect", watched)
    data = tmp_path / "data"
    helab = "helab:" + MATLAB_2019.content_hash()

    def convert(source: Path) -> None:
        request: dict[str, Any] = {"path": str(source), "profile": MATLAB_2019.to_dict(),
                                   "temps": str(tmp_path / "temps"), "seen": None, "destination": "cache",
                                   "workers": 1, "cache": options}
        convert_folder(str(source), request, lambda event: None)  # type: ignore[arg-type]

    tab_txy = {"source": "helab-priority", "profile_hash": MATLAB_2019.content_hash(), "profile_tag": "m19v1",
               "cache_base": private_store, "temps": str(tmp_path / "temps")}

    def run(source: Path, txy: dict[str, Any] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        output = tmp_path / f"artifacts-{time.monotonic_ns()}"
        output.mkdir()
        sent: list[dict[str, Any]] = []
        load(str(source), str(output), sent.append, {**options, **kwargs.pop("cache", {})},  # type: ignore[arg-type]
             txy=dict(txy or tab_txy), **kwargs)
        return sent

    def loaded_of(sent: list[dict[str, Any]]) -> dict[str, Any]:
        return next(event for event in sent if event["kind"] == "loaded")

    # 1-2. A conversion, then the tab's load from the raw layer, a plot's choice, and a load from the layers.
    x = folder(data, "x", {1: CASE, 2: CASE})
    convert(x)
    read = infra._read_txy_file

    def refuse_helab(filename: str, reason: str) -> Any:
        assert "d_txy_helab_" not in os.path.basename(filename), filename
        return read(filename, reason)
    monkeypatch.setattr(infra, "_read_txy_file", refuse_helab)
    first_load = loaded_of(run(x))
    assert first_load["txy"]["origins"] and first_load["problematic"] == []
    with opened(options, x) as store:
        layer = (store.txy_layers(str(x)).value or {})[helab]
        assert {entry.kind for entry in layer.entries.values()} == {"raw"} and store.read_dataset_row(str(x)).missing
    monkeypatch.setattr(infra, "_read_txy_file", read)
    y = folder(data, "y", {1: CASE, 2: CASE}, txy=True)
    run(y, {"source": "matlab-only", "tab": False}, no_cache=True)  # (A plot's own choice: cached quietly.)
    with opened(options, y) as store:
        assert store.read_view(str(y), "matlab-only", "").found and "matlab" in (store.txy_layers(str(y)).value or {})
    again = loaded_of(run(x))
    assert again["cached"] and again["source"] == "disk"

    # 3. Live: one segment per autosave of the new shot, compacted when they pile up.
    live = folder(data, "live", {1: CASE}, txy=True)
    held = [list(entry) for entry in loaded_of(run(live, {"source": "matlab-only"}))["fingerprint"]]
    held_dir = tmp_path / "held"
    held_dir.mkdir()
    np.save(held_dir / "1.npy", np.zeros((2, 3)), allow_pickle=False)
    for shot in range(2, COMPACT_SEGMENTS + 3):
        folder(data, f"live-{shot}", {shot: CASE}, txy=True)  # (A finished shot: moved in as Live finds it.)
        for name in (f"d{shot}.txt", f"d_txy_forc{shot}.txt"):
            os.replace(data / f"live-{shot}" / name, live / name)
        np.save(held_dir / f"{shot}.npy", np.full((2, 3), float(shot)), allow_pickle=False)
        info = (live / f"d_txy_forc{shot}.txt").stat()
        held.append([shot, info.st_size, info.st_mtime_ns])
        sent: list[dict[str, Any]] = []
        save_held(str(live), sent.append, options, held, [], str(held_dir),  # type: ignore[arg-type]
                  txy={"source": "matlab-only"})
        assert any(event["kind"] == "cache_saved" for event in sent)
    with opened(options, live) as store:
        key = store._path_key(str(live))
        assert store._conn.execute("SELECT COUNT(*) FROM txy_segments WHERE path = ?", (key,)).fetchone()[0] <= 2
        assert len(store.read_txy_shots(str(live), "matlab").value or {}) == COMPACT_SEGMENTS + 2

    # 4. Clear all: datasets, records, raw pulses and TXY layers.
    cleared: list[Any] = []
    cache_admin(options, "clear", cleared.append)
    assert {kind for event in cleared if event["kind"] == "removed" for kind in event["kinds"]} >= {"raw", "txy"}
    with opened(options, x, y, live) as store:
        assert store.inventory()["txy"]["layers"] == 0 and store.inventory()["raw"]["count"] == 0

    # 5. Make room's order: X's HeLab layer (made again from its raw layer here), then Y's MATLAB layer.
    convert(x)  # (Its HeLab TXY are still current: nothing converts again, so no raw rows from it.)
    run(x)
    raw_fill(str(x), options, lambda event: None)  # (As the app queues after that load's save.)
    run(y, {"source": "matlab-only"})
    with opened(options, x, y) as store:
        with store.transaction():
            store._conn.execute("UPDATE txy_layers SET last_used = 1 WHERE path = ?", (store._path_key(str(y)),))
    z = folder(data, "z", {1: CASE, 2: CASE}, txy=True)
    held_unit = next(event for event in run(z, {"source": "matlab-only"}, cache={"budget": 1,
                                                                               "budget_set_at": time.time()})
                     if event["kind"] == "cache_full")
    with opened(options, x, y, z) as store:
        low, high = 1, store.usage() + held_unit["bytes"]
        while low < high:
            middle = (low + high) // 2
            low, high = ((low, middle) if store.room_plan(held_unit["pending_id"], middle).possible
                         else (middle + 1, high))
        items = store.room_plan(held_unit["pending_id"], low).items
        x_item, y_item = txy_item("txy:", str(x), helab), txy_item("txy-seen:", str(y), "matlab")
        assert x_item in items and y_item in items and items.index(x_item) < items.index(y_item)

    # 6. store-v3 as it was, and opened by nothing but LegacyStore.
    assert files(v3) == before and v3_opens == []

    # 7. A cache move with both stores, each verified (segments included), store-v3 carried as it was.
    app, target = tmp_path / "app", tmp_path / "moved" / "caches"
    record = cache_move.start(str(caches), str(target), str(app), COPY)
    record = cache_move.move(record, str(app), lambda done, total: None, lambda: False)
    assert cache_move.verify(str(target), record["store_id"], record["store_ids"]) == ""
    assert files(target / "store-v3") == before and v3_opens == []
    out = tmp_path / "exported"
    assert cache_cli.main(["export", "--folder", str(x), "--kind", "txy", "--cache", str(target), "--out", str(out),
                           "--layer", "m19v1"]) == 0
    assert sorted(os.listdir(out)) == ["d_txy1.npz", "d_txy2.npz"]


def test_a_stage_3_session_converts_on_read_and_leaves_store_v3_as_it_was(
        switch_on: None, private_store: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Stage 3's integration check (design step 3d), the switch on, beside an older HeLab's store-v3:
    1. the tab's load of a folder of raw files only converts them on read (no TXY text anywhere), keeps them in
       the HeLab layer, and the next load is served from it;
    2. after ``raw_fill``, a load of another (user) profile, sent whole, converts from the raw layer without
       reading a raw file (A47.1);
    3. Live converts a new shot on read; an unfinished one waits;
    4. Clear all takes it all; store-v3's files are unchanged and only LegacyStore opens it."""
    import dataclasses
    from helab.io_ops import convert as convert_ops
    from helab.io_ops.live import live_check
    options = store_options()
    caches = Path(private_store)
    v3_with_state(caches)
    v3 = caches / "store-v3"
    before = files(v3)
    v3_opens: list[str] = []
    connect = sqlite3.connect

    def watched(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        if "store-v3" in str(database) and not any(frame.filename.endswith("legacy_store.py")
                                                   for frame in traceback.extract_stack()):
            v3_opens.append(str(database))
        connection: sqlite3.Connection = connect(database, *args, **kwargs)
        return connection
    monkeypatch.setattr(sqlite3, "connect", watched)
    data = tmp_path / "data"
    tab_txy = {"source": "helab-priority", "profile_hash": MATLAB_2019.content_hash(), "profile_tag": "m19v1",
               "cache_base": private_store, "temps": str(tmp_path / "temps"), "profile_def": MATLAB_2019.to_dict()}

    def run(source: Path, txy: dict[str, Any]) -> dict[str, Any]:
        output = tmp_path / f"artifacts-{time.monotonic_ns()}"
        output.mkdir()
        sent: list[dict[str, Any]] = []
        load(str(source), str(output), sent.append, options, txy=dict(txy))  # type: ignore[arg-type]
        return next(event for event in sent if event["kind"] == "loaded")

    # 1. Raw files only: converted on read, kept, and served from the layer next time.
    x = folder(data, "x", {1: CASE, 2: CASE})
    first_load = run(x, tab_txy)
    assert first_load["load_counts"]["converted"] == 2 and first_load["txy"]["on_read"] == [1, 2]
    assert not list(tmp_path.rglob("d_txy_helab_*")) and not list(caches.rglob("d_txy_helab_*"))
    with opened(options, x) as store:
        layer = (store.txy_layers(str(x)).value or {})["helab:" + MATLAB_2019.content_hash()]
        assert {entry.kind for entry in layer.entries.values()} == {"raw"}
    again = run(x, tab_txy)
    assert again["cached"] and again["load_counts"].get("converted", 0) == 0

    # 2. The raw layer, then a user profile's load from it: no raw file read.
    assert filled(x, options)["saved"] == 2
    mine = dataclasses.replace(MATLAB_2019, name="mine", v_perp_x=500_000.0)
    with monkeypatch.context() as patch:
        patch.setattr(convert_ops, "_read_raw", lambda *args: (_ for _ in ()).throw(AssertionError("read raw")))
        theirs = run(x, {**tab_txy, "profile_hash": mine.content_hash(), "profile_tag": "mine1",
                         "profile_def": mine.to_dict()})
    assert theirs["problematic"] == [] and theirs["files"] == 2

    # 3. Live: a new shot converted on read; an unfinished one waits.
    folder(data, "incoming", {3: CASE})
    os.replace(data / "incoming" / "d3.txt", x / "d3.txt")
    (x / "d4.txt").write_bytes(CASE[:-3])  # (Still being written: ends mid-line.)
    os.utime(x / "d4.txt", (time.time() - 10, time.time() - 10))
    memory = [list(entry) for entry in again["fingerprint"]]
    origins = {str(shot): origin for shot, origin in again["txy"]["origins"].items()}
    live_txy = {**tab_txy, "on_read": True}

    def check(seen: Any = None) -> list[dict[str, Any]]:
        output = tmp_path / f"live-{time.monotonic_ns()}"
        output.mkdir()
        sent: list[dict[str, Any]] = []
        live_check(str(x), str(output), sent.append, memory=memory, seen=seen,  # type: ignore[arg-type]
                   txy=live_txy, memory_origins=origins)
        return sent
    first_check = check()
    state = [event for event in first_check if event["kind"] in ("loaded", "live_unchanged")][-1]
    second = check(state["live_seen"])
    shots = [event["shot"] for event in second if event["kind"] == "shot"]
    assert shots == [3] and not any(event["kind"] == "file_started" for event in second)
    final = [event for event in second if event["kind"] in ("loaded", "live_unchanged")][-1]
    assert final["unsettled_files"] >= 1 and 4 not in final.get("problematic", [])

    # 4. Clear all, and store-v3 as it was, opened by nothing but LegacyStore.
    cleared: list[Any] = []
    cache_admin(options, "clear", cleared.append)
    with opened(options, x) as store:
        assert store.inventory()["txy"]["layers"] == 0 and store.inventory()["raw"]["count"] == 0
    assert files(v3) == before and v3_opens == []


def test_a_stage_4_session_txy_only_removes_raw_pulses_only_when_asked(
        switch_on: None, private_store: str, tmp_path: Path) -> None:  # noqa: F811
    """Stage 4's check (S4~1), the switch on, as the helpers run it: a folder set to TXY only reports its raw
    pulses and keeps them; raw_fill then keeps none for it; removing them is a separate, asked-for clear_raw of
    that folder; its next load still converts on read from the raw files (the d files untouched); Settings' TXY
    only removes only the folders that follow it."""
    options = store_options()
    data = tmp_path / "data"
    x, y = folder(data, "x", {1: CASE, 2: CASE}), folder(data, "y", {1: CASE})
    for source in (x, y):
        assert filled(source, options)["saved"] >= 1
    sent: list[dict[str, Any]] = []
    cache_admin(options, "folder_choice", sent.append, path=str(x), policy="txy", set_at=5.0)  # type: ignore[arg-type]
    report = next(event for event in sent if event["kind"] == "admin_result")["folder_raw"]
    assert report["shots"] == 2 and report["bytes"] > 0
    with opened(options, x) as store:
        assert len(store.raw_rows(str(x)).value or {}) == 2  # (Kept until the user says.)
    (x / "d3.txt").write_bytes(CASE)
    os.utime(x / "d3.txt", (OLD, OLD))
    assert filled(x, options)["reason"] == "policy"  # (TXY only: no new raw pulses.)
    cache_admin(options, "clear_raw", lambda event: None, paths=[str(x)])  # (The user's yes.)
    with opened(options, x, y) as store:
        assert store.raw_rows(str(x)).value == {} and store.raw_rows(str(y)).value
    raw_before = {name: (x / name).read_bytes() for name in ("d1.txt", "d2.txt", "d3.txt")}
    output = tmp_path / "out"
    output.mkdir()
    events: list[dict[str, Any]] = []
    txy = {"source": "helab-only", "profile_hash": MATLAB_2019.content_hash(), "profile_tag": "m19v1",
           "profile_def": MATLAB_2019.to_dict()}
    load(str(x), str(output), events.append, options, txy=txy)  # type: ignore[arg-type]
    assert next(event for event in events if event["kind"] == "loaded")["load_counts"]["converted"] == 3
    assert {name: (x / name).read_bytes() for name in raw_before} == raw_before
    cache_admin(options, "folder_choice", lambda event: None, path=str(y), policy="raw+used", set_at=6.0)
    cache_admin(options, "clear_raw", lambda event: None, following=True)
    with opened(options, y) as store:
        assert store.raw_rows(str(y)).value  # (Its own policy: kept.)
