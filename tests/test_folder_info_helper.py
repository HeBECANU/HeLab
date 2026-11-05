"""Folder info's helper job (``cache_admin`` "folder_info", ``helab/io_ops/folder_info.py``; Q64.1–Q64.10): one read of
the store and HeLab's converted-TXY index for a folder, with each part found, missing, an error or skipped, never per-shot
data, bounded, and never the source folder (it doesn't exist in these tests, and nothing under it is touched). Make
room's groups (``_txy_groups``) are unchanged by the shared rule (``cache_store.layer_group``). Temp stores only."""
from __future__ import annotations

from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator

import pytest

from helab.analysis import result_cache
from helab.analysis.dataset_view import build_view
from helab.analysis.identity import AnalysisIdentity
from helab.analysis.physics import resolve
from helab.analysis.results import AnalysisContext, AnalysisResult, Coverage
from helab.convert import raw_layer, txy_layer
from helab.convert.provenance import INDEX_NAME, Provenance, open_index
from helab.io_ops import folder_info as job
from helab.io_ops import stores
from helab.io_ops.admin import cache_admin
from helab.io_ops.convert import folder_for
from helab.utils import cache_store, scan_history
from helab.utils.cache_store import CacheStore, RawEntry, TxyPart, TxyShot
from helab.utils.folder_cache import Dataset, store_options

MTIME = 1_700_000_000_000_000_000
HELAB = txy_layer.helab_layer("abc123")
MATLAB = txy_layer.MATLAB


def raw_text(shot: int, rows: int = 50) -> bytes:
    return "".join(f"{5 if i == 0 else 1 + i % 8},{1000 * shot + 37 * i}\r\n" for i in range(rows)).encode()


def raw_entry(store: CacheStore, shot: int) -> RawEntry:
    data = raw_text(shot)
    layer = raw_layer.encode(data)
    file = store.write_raw_file(raw_layer.to_hlb(layer, meta={"name": f"d{shot}.txt"}))
    return RawEntry(shot, f"d{shot}.txt", len(data), MTIME, hashlib.sha256(data).hexdigest(),
                    raw_layer.RAW_PARSER_VERSION, layer.encoding, layer.facts.to_json(), layer.pulses, file)


def txy_part(store: CacheStore, layer: str, shots: list[int], kind: str, tags: tuple[str, ...] = ()) -> TxyPart:
    import numpy as np
    data = {shot: np.full((10, 3), float(shot)) for shot in shots}
    file = store.write_txy_file(txy_layer.pack_segment(data, layer=layer, tags=tags))
    return TxyPart(layer, file, tuple(TxyShot(shot, len(raw_text(shot)) if kind == "raw" else 2000 + shot, MTIME, kind,
                                              10) for shot in shots), tags)


def record(parameters: dict[str, Any], version: str = "3") -> Any:
    import numpy as np
    view = build_view(Dataset("/data/x", "sig", {1: np.zeros((2, 3))}, {"fingerprint": [[1, 2, 3]]}, 0))
    context = AnalysisContext("job", "Plot", view, parameters, AnalysisIdentity("tests.corr", version, "corr.py", "h"),
                              threading.Event(), Coverage.of(view), resolved_constants=resolve())
    return result_cache.record_of(AnalysisResult.of(context, "completed", None, started_at=1.0))


def opened(source: Path) -> CacheStore:
    return stores._cache_store(store_options()["directory"], [str(source)])


def ask(path: Path, temps: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    cache_admin(store_options(), "folder_info", sent.append, path=str(path),  # type: ignore[arg-type]
                temps=str(temps or ""))
    [info] = [event for event in sent if event["kind"] == "folder_info"]
    assert sent[-1]["kind"] == "admin_result" and sent[-1]["action"] == "folder_info"
    return info, sent


@pytest.fixture
def untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every ``os`` call naming the source folder ``tmp_path/data`` (none expected: it never exists here)."""
    calls: list[str] = []
    data = os.path.normcase(str(tmp_path / "data"))
    for name in ("stat", "lstat", "scandir", "listdir", "open"):
        original = getattr(os, name)

        def traced(*args: Any, _original: Any = original, _name: str = name, **kwargs: Any) -> Any:
            if args and isinstance(args[0], (str, os.PathLike)) and os.path.normcase(os.fspath(args[0])).startswith(data):
                calls.append(f"{_name} {args[0]}")
            return _original(*args, **kwargs)
        monkeypatch.setattr(os, name, traced)
    yield calls


def seed(tmp_path: Path) -> Path:
    """A folder with each kind of row: raw pulses (shot 3 an only copy), a rebuildable HeLab layer, a seen MATLAB one and
    an only-copy layer, a view, three results (one damaged), flags, converter flags, a TXY list, a policy, constants,
    a failed scan's history, a basic scan's summary and a listing."""
    x = tmp_path / "data" / "x"
    with opened(x) as store:
        guard = store.start_raw_job(str(x))
        store.save_raw_batch(str(x), [raw_entry(store, shot) for shot in (1, 2, 3)], guard)
        store.save_txy(str(x), "", "", [txy_part(store, HELAB, [1, 2], "raw", ("m19v1",)),
                                       txy_part(store, MATLAB, [1, 2], "txy")],
                       {"fingerprint": [[1, 2001, MTIME, "txy", MATLAB]], "problematic": [], "info": {"signature": "s"}},
                       store.start_txy_job(str(x)))
        store.save_txy(str(x), "helab-only", "u1", [txy_part(store, txy_layer.helab_layer("ffff"), [3], "txy", ("u1",))],
                       None, store.start_txy_job(str(x)))
        later = time.time() + 60
        store.mark_raw_seen(str(x), {1: (len(raw_text(1)), MTIME), 2: (len(raw_text(2)), MTIME)}, later)
        store.mark_txy_seen(str(x), {"raw": {1: (0, 0), 2: (0, 0)}, MATLAB: {1: (0, 0), 2: (0, 0)}}, later)
        for lookup, parameters in (("k1", {"bins": 10, "mode": "fast", "width": 0.125}), ("k2", {"bins": 20})):
            store.save_result(str(x), lookup, "f", record(parameters), store.write_result_file(b"x" * 100),
                              store.start_result_job(str(x)), analysis_id="tests.corr", action="Plot",
                              computed_at=1000.0)
        store.save_result(str(x), "k3", "f", {"not": "a record"}, store.write_result_file(b"y" * 50),
                          store.start_result_job(str(x)), analysis_id="tests.other", action="Fit", computed_at=2000.0)
        store.set_prefs(str(x), True, False, 10.0)
        store.set_convert_prefs(str(x), True, 11.0)
        store.set_txy_source_pref(str(x), "helab-priority", "m19v1", 12.0)
        store.set_cache_policy(str(x), "raw", 13.0)
        store.set_constants(str(x), {"fall_distance": 0.848}, 14.0)
        records = store.guard([str(x)], ("histories", "summaries", "listings"))
        history = scan_history.apply_outcome(scan_history.empty_history(), {
            "kind": "error", "revision": 1, "operation_id": "op", "at": 1500.0, "attempts": 1, "reason": "timed out"})
        store.save_record("histories", str(x), dict(history), records)
        store.save_record("summaries", str(x), {"version": 1, "signature": "s", "status": "ok", "count": 3,
                                                 "raw_count": 3, "txy_count": 2, "scanned_at": 1400.0}, records)
        store.save_record("listings", str(x), {"version": 1, "names": [], "listed_at": 1450.0}, records)
    return x


def test_every_part_of_a_folder_is_read_without_touching_it(tmp_path: Path, untouched: list[str]) -> None:
    x = seed(tmp_path)
    info, _ = ask(x)
    assert untouched == [] and not (tmp_path / "data").exists()
    assert info["root_state"] == "rooted" and info["key"].startswith("root://") and info["layout"] == 4
    assert {name for name, part in info["parts"].items() if part["status"] != "found"} == {"seed", "converted"}
    raw = info["raw"]
    assert (raw["shots"], raw["first"], raw["last"], raw["only_copy"]) == (3, 1, 3, 1)
    assert raw["only_copy_bytes"] > 0 and raw["gone_first"] is not None and raw["bytes"] > raw["only_copy_bytes"]
    groups = {layer["layer"]: layer["group"] for layer in info["layers"]}
    assert groups == {HELAB: "rebuildable", MATLAB: "seen", txy_layer.helab_layer("ffff"): "only"}
    helab = next(layer for layer in info["layers"] if layer["layer"] == HELAB)
    assert (helab["tags"], helab["shots"], helab["first"], helab["last"], helab["rows"]) == (["m19v1"], 2, 1, 2, 20)
    assert [view["source"] for view in info["views"]] == [""]
    results = info["results"]
    assert (results["count"], results["bytes"], results["more"]) == (3, 250, 0)
    rows = {row["result_id"]: row for row in results["rows"]}
    good = sorted((row for row in rows.values() if not row["damaged"]), key=lambda row: row["settings"])
    assert [row["settings"] for row in good] == ["bins=10 · mode=fast · width=0.125", "bins=20"]
    assert good[0]["version"] == "3" and good[0]["file_name"] == "corr.py" and good[0]["settings_full"].count("\n") == 2
    [damaged] = [row for row in rows.values() if row["damaged"]]
    assert (damaged["analysis_id"], damaged["action"], damaged["settings"], damaged["bytes"]) == ("tests.other", "Fit", "", 50)
    assert info["prefs"] == {"no_cache": True, "no_auto_load": False, "set_at": 10.0}
    assert info["convert_prefs"] == {"write_beside": True, "set_at": 11.0}
    assert (info["choices"] or {})["source"] == "helab-priority" and (info["choices"] or {})["policy"] == "raw"
    assert (info["constants"] or {})["values"] == {"fall_distance": 0.848}
    assert (info["history"] or {})["blocked"] and (info["history"] or {})["failures"][0]["reason"] == "timed out"
    assert info["summary"] == {"status": "ok", "count": 3, "raw_count": 3, "txy_count": 2, "scanned_at": 1400.0,
                               "empty": None, "has_dirs": None}
    assert info["listing_at"] == 1450.0
    json.dumps(info)  # (JSON, as the helper sends it.)


def test_a_folder_with_nothing_saved_reads_missing_never_an_error(tmp_path: Path) -> None:
    info, _ = ask(tmp_path / "data" / "empty")
    statuses = {part["status"] for part in info["parts"].values()}
    assert statuses == {"missing"} and info["results"] == {"count": 0, "bytes": 0, "rows": [], "more": 0}
    assert info["raw"] is not None and info["raw"]["shots"] == 0


@pytest.mark.no_auto_data_root
def test_a_folder_without_a_data_root_is_ram_only_not_an_error(tmp_path: Path) -> None:
    info, sent = ask(tmp_path / "data" / "x")
    assert info["root_state"] == "no_root" and info["key"] == ""
    assert {part["status"] for name, part in info["parts"].items() if name != "converted"} == {"skipped"}
    assert not any(event["kind"] == "error" for event in sent)


def test_an_unverified_drive_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from helab.utils.data_roots import VolumeUnverified

    def unverified(self: CacheStore, path: str) -> str:
        raise VolumeUnverified(path)
    monkeypatch.setattr(cache_store.CacheStore, "folder_contents", lambda *args, **kwargs: pytest.fail("read"))
    original = stores._cache_store

    def opener(*args: Any, **kwargs: Any) -> CacheStore:
        store = original(*args, **kwargs)
        store._path_key = lambda path: unverified(store, path)
        return store
    monkeypatch.setattr(stores, "_cache_store", opener)
    info, _ = ask(tmp_path / "data" / "x")
    assert info["root_state"] == "unverified" and info["parts"]["raw"]["status"] == "skipped"


def test_a_part_that_cant_be_read_is_its_own_error(tmp_path: Path) -> None:
    x = seed(tmp_path)
    with opened(x) as store:
        store._conn.execute("UPDATE txy_layers SET entries = 'not json' WHERE layer = ?", (MATLAB,))
        store._conn.commit()
    info, _ = ask(x)
    assert info["parts"]["layers"]["status"] == "error" and "could not be read" in info["parts"]["layers"]["error"]
    assert info["layers"] == [] and info["parts"]["raw"]["status"] == "found" and info["results"] is not None


def test_a_store_that_cant_be_read_fails_the_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(self: CacheStore, path: str, **kwargs: Any) -> Any:
        raise cache_store.StoreError("Disk cache could not be read: disk I/O error")
    monkeypatch.setattr(cache_store.CacheStore, "folder_contents", broken)
    with pytest.raises(cache_store.StoreError):
        cache_admin(store_options(), "folder_info", lambda event: None, path=str(tmp_path / "data" / "x"))


def test_store_v3s_store_parts_are_skipped(tmp_path: Path) -> None:
    with CacheStore(str(tmp_path / "caches" / "store-v3")) as store:
        store.set_prefs("root://a/x", False, True, 1.0)
        info = job.folder_info(store, "root://a/x", store.root)
    assert info["layout"] == 3 and info["prefs"] == {"no_cache": False, "no_auto_load": True, "set_at": 1.0}
    assert {name for name, part in info["parts"].items() if part["status"] == "skipped"} == set(job.STORE_V4_PARTS)


def test_results_and_layers_are_bounded(tmp_path: Path) -> None:
    x = tmp_path / "data" / "x"
    with opened(x) as store:
        guard = store.start_raw_job(str(x))
        store.save_raw_batch(str(x), [raw_entry(store, shot) for shot in range(1, 41)], guard)
        long = {f"p{index}": "v" * 200 for index in range(30)}
        for index in range(job.MAX_RESULTS + 40):
            store.save_result(str(x), f"k{index}", "f", record(long), store.write_result_file(b"r"),
                              store.start_result_job(str(x)), analysis_id="tests.corr", action="Plot",
                              computed_at=float(index))
    info, _ = ask(x)
    results = info["results"]
    assert results["count"] == job.MAX_RESULTS + 40 and len(results["rows"]) == job.MAX_RESULTS and results["more"] == 40
    row = results["rows"][0]
    assert len(row["settings"]) == job.SETTINGS_SHORT and len(row["settings_full"]) == job.SETTINGS_FULL
    assert row["settings"].endswith("…") and info["raw"]["shots"] == 40
    assert len(json.dumps(info)) < 600_000


def provenance(shot: int, tag: str, output: str, size: int) -> Provenance:
    values: dict[str, Any] = {field.name: 0 for field in fields(Provenance)}
    values.update(shot=shot, raw_name=f"d{shot}.txt", raw_sha256="", profile_name="matlab-2019", profile_hash="h",
                  profile_tag=tag, profile_calibrated=False, backend="numpy", output=output,
                  txy_name=f"d_txy_helab_{tag}_{shot}.txt", txy_size=size, txy_sha256="", converted_at=100.0 + shot,
                  helab_version="0", profile_version=1)
    return Provenance(**values)


def test_converted_txy_come_from_each_bases_index_read_only(tmp_path: Path, untouched: list[str]) -> None:
    x = tmp_path / "data" / "x"
    with opened(x) as store:
        key = store._path_key(str(x))
    cache_base = os.path.dirname(store_options()["directory"])
    temps = tmp_path / "temps"
    folder = folder_for(cache_base, key)
    index = open_index(os.path.dirname(folder), write=True)
    for shot in (1, 2):
        index.record(os.path.basename(folder), key, str(x), provenance(shot, "m19v1", "cache", 1000), 500.0)
    index.record(os.path.basename(folder), key, str(x), provenance(3, "m19v1", "beside", 700), 600.0)
    index.close()
    damaged = folder_for(str(temps), key)
    os.makedirs(os.path.dirname(damaged))
    Path(os.path.dirname(damaged), INDEX_NAME).write_bytes(b"not a database")
    info, _ = ask(x, temps)
    cache, temp, by_path = info["converted"]
    assert (cache["base"], cache["status"], cache["last_used"]) == ("cache", "found", 600.0)
    assert [(tag["output"], tag["tag"], tag["shots"], tag["bytes"], tag["newest"]) for tag in cache["tags"]] == [
        ("beside", "m19v1", 1, 700, 103.0), ("cache", "m19v1", 2, 2000, 102.0)]
    assert temp["base"] == "temp" and temp["status"] == "error" and "can't be read" in temp["error"]
    assert by_path["status"] == "error" and info["parts"]["converted"]["status"] == "error"
    assert untouched == []


def test_make_rooms_groups_are_unchanged_by_the_shared_rule(tmp_path: Path) -> None:
    """``_txy_groups`` through ``layer_group`` gives what its own rule gave (C~1): the rule as it was, inline."""
    x = seed(tmp_path)
    with opened(x) as store, store.transaction(write=False):
        groups = store._txy_groups(None)
        expected: dict[str, list[tuple[str, str]]] = {"rebuildable": [], "seen": [], "only": []}
        for key, layer, entries, gone_at in store._conn.execute(
                "SELECT path, layer, entries, gone_at FROM txy_layers ORDER BY last_used, path, layer").fetchall():
            if gone_at is not None:
                expected["only"].append((key, layer))
                continue
            held = {(int(s), int(z), int(m)) for s, z, m in store._conn.execute(
                "SELECT shot, size, mtime_ns FROM raw_layers WHERE path = ?", (key,))}
            parsed = [cache_store.TxyEntry.from_json(entry) for entry in json.loads(entries)]
            rebuildable = layer.startswith("helab:") and all(
                entry.kind == "raw" and (entry.shot, entry.size, entry.mtime_ns) in held for entry in parsed)
            expected["rebuildable" if rebuildable else "seen"].append((key, layer))
    assert groups == expected and all(groups.values())


def test_the_app_asks_on_the_local_lane_and_hears_the_answer_by_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    from helab.utils.folder_cache import FolderCache
    from helab.utils.io_service import IOService
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    cache = FolderCache(service)
    heard: list[tuple[str, Any]] = []
    ended: list[tuple[str, str, str]] = []
    cache.folderInfoRead.connect(lambda owner, event: heard.append((owner, event)))
    cache.cacheAdminDone.connect(lambda *args: ended.append(args))
    try:
        owner = cache.folder_info("/data/x")
        request = next(r for r in service.pending if r.owner == owner)
        assert request.operation == "cache_admin" and request.priority and request.payload["action"] == "folder_info"
        params = request.payload["params"]
        assert params["path"] == "/data/x" and "verified_volumes" in params and params["temps"]
        answer = {"kind": "folder_info", "path": "/data/x", "store": ""}
        for event in (answer, {"kind": "admin_result", "action": "folder_info", "next_deadline": None},
                      {"kind": "done"}):
            service.resultReady.emit(request, event)
        assert heard == [(owner, answer)] and ended == [(owner, "folder_info", "")]
    finally:
        service.shutdown()
