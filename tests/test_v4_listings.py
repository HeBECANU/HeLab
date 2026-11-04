"""store-v4's cached data as listings, scans and Make room's adopt see it (found by the switch-on run): a folder
cached in store-v4 has views and TXY layers, not a ``datasets`` row, so ``read_dataset_infos`` answers from its
view (the one asked for, else the most recently used) with the bytes of the layers it names; a scan's mismatch
rule reads the view's MATLAB shots; an adopted save's ``cache_info`` is its view's. Temp stores only."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from helab.io_ops.admin import cache_admin
from helab.io_ops import stores
from helab.io_ops.browse import list_folder
from helab.io_ops.scanning import _check_cached_shots
from helab.utils import file_kinds

from test_txy_loading import data_folder, first, opened, run_load, v4_options


def test_a_listing_finds_a_folder_cached_in_store_v4_from_its_view(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    with opened(options, source) as store:
        layers = store.txy_layers(str(source)).value or {}
        info = store.read_dataset_infos([str(source)])[str(source)].value
        assert store.read_dataset_row(str(source)).missing  # (No datasets row: its view and layers.)
    assert info is not None and info["bytes"] == sum(layer.bytes for layer in layers.values()) > 0
    assert info["source_bytes"] > 0 and info["ram_bytes"] > 0 and info["info"]
    events: list[dict[str, Any]] = []
    list_folder(str(source.parent), events.append, options)  # type: ignore[arg-type]
    [entry] = [entry for event in events if event["kind"] == "entries" for entry in event["entries"]
               if entry["path"] == str(source)]
    assert entry["disk_cached"] is True and entry["cache_info"]["disk_bytes"] == info["bytes"]


def test_the_view_asked_for_answers_else_the_most_recently_used(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options, txy={"source": "matlab-only"})
    time.sleep(0.01)
    run_load(source, tmp_path, options, txy={"source": "matlab-priority"})
    with opened(options, source) as store:
        views = sorted(store.folder_views(str(source)), key=lambda view: view[2])
        assert len(views) == 2
        older, newer = (view[:2] for view in views)
        latest = store.read_dataset_infos([str(source)])[str(source)].value
        asked = store.read_dataset_infos([str(source)], wanted=(older[0], older[1]))[str(source)].value
        newest = store.read_view(str(source), *newer).value
        oldest = store.read_view(str(source), *older).value
    assert latest is not None and asked is not None and newest is not None and oldest is not None
    assert latest["last_used"] == newest.last_used and asked["last_used"] == oldest.last_used


def test_a_scan_finds_a_store_v4_folder_lost_shots(tmp_path: Path) -> None:
    source = data_folder(tmp_path, range(1, 4))
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    sent: list[dict[str, Any]] = []
    with opened(options, source) as store:
        assert store.cached_matlab_shots(str(source)).value == {1, 2, 3}
        _check_cached_shots(store, str(source), {file_kinds.TXY.name: {1, 3}}, sent.append)  # type: ignore[arg-type]
    assert [event["missing"] for event in sent if event["kind"] == "cache_mismatch"] == [[2]]


def test_an_adopted_save_answers_with_its_views_cache_info(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    held = next(event for event in run_load(source, tmp_path, {**options, "budget": 1, "budget_set_at": time.time()})
                if event["kind"] == "cache_full")
    sent: list[dict[str, Any]] = []
    cache_admin({**options, "budget_set_at": time.time()}, "adopt", sent.append,  # type: ignore[arg-type]
                pending_id=held["pending_id"])
    result = first(sent, "admin_result")
    assert result["adopted"] is True and result["cache_info"]


def test_a_damaged_view_is_an_error_for_its_folder_and_the_others_list_on(tmp_path: Path) -> None:
    """SV-1: one folder's unreadable view record answers an error for that folder only (as store-v3 does for a
    dataset), never "not cached", and never fails the listing of the others."""
    source = data_folder(tmp_path)
    other = data_folder(tmp_path / "other")
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    run_load(other, tmp_path, options)
    for damage in ("not json", "[[1]]", "[5]"):
        with stores._cache_store(options["directory"], [str(source), str(other)]) as store:
            with store.transaction():
                store._conn.execute("UPDATE txy_views SET fingerprint = ? WHERE path = ?",
                                    (damage, store._path_key(str(source))))
            found = store.read_dataset_infos([str(source), str(other)])
        assert found[str(source)].failed and "unreadable" in found[str(source)].error, damage
        assert found[str(other)].value is not None, damage


def test_a_load_of_another_txy_choice_says_the_folder_is_disk_cached(tmp_path: Path) -> None:
    """A folder cached in store-v4 under one TXY choice is disk cached when a load of another choice (its view not
    saved yet) says so: its badge doesn't drop until that save lands (the switch-on CI, 41482722171)."""
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)  # (No TXY choice: its own view.)
    other = {"source": "helab-priority", "profile_hash": "f" * 64, "profile_tag": "zz1"}
    with opened(options, source) as store:
        assert store.read_view(str(source), "helab-priority", "f" * 64).missing
    loaded = first(run_load(source, tmp_path, options, txy=other), "loaded")
    assert loaded["disk_cached"] is True
