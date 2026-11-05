"""Folder info's helper job (``cache_admin`` "folder_info", ``helab/io_ops/folder_info.py``; Q64.1–Q64.10): one read of
the store and HeLab's converted-TXY index for a folder, with each part found, missing, an error or skipped, never per-shot
data, bounded, and never the source folder (it doesn't exist in these tests, and nothing under it is touched). Make
room's groups (``_txy_groups``) are unchanged by the shared rule (``cache_store.layer_group``). And the per-folder Clears
(Q~6, Q64.6 b): only that folder's raw pulses, saved results or converted TXY go, other folders' stay, beside TXY are
never touched, a save or conversion running can't bring them back, only copies are named, and a refused or failed Clear
removes nothing. Temp stores only."""
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


def ask(path: Path, temps: Path | None = None, **params: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    cache_admin(store_options(), "folder_info", sent.append, path=str(path),  # type: ignore[arg-type]
                temps=str(temps or ""), **params)
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


@pytest.fixture
def usb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[str]]:
    """A run on a disk whose mount hint the store keeps (a listing recorded it) with raw pulses, a saved result and a
    converted TXY in the temp folder by path; and the disk's (mount, source) to pass as verified. The real opener and
    resolver, as ``test_store_migration``'s constants on an unverified volume."""
    import uuid
    from helab.io_ops.browse import list_folder
    from helab.utils import cache_paths, data_roots
    from helab.utils.cache_paths import Mount
    disk = tmp_path / "USB"
    run = disk / "run"
    run.mkdir(parents=True)
    (disk / ".helab-root").write_text(json.dumps({"helab": "root", "version": 1, "uuid": str(uuid.uuid4()),
                                                  "label": "USB", "created_at": "2026-10-20T00:00:00Z"}),
                                      encoding="utf-8")
    mount = Mount("/dev/disk4s1", str(disk), "apfs")
    monkeypatch.setattr(cache_paths, "current_mounts", lambda: [mount])
    monkeypatch.setattr(data_roots, "_volume_id", lambda _: "disk-a")
    list_folder(str(disk), lambda _: None, store_options())
    with opened(run) as store:
        store.save_raw_batch(str(run), [raw_entry(store, shot) for shot in (1, 2)], store.start_raw_job(str(run)))
        store.save_result(str(run), "k1", "f", record({"bins": 5}), store.write_result_file(b"z" * 80),
                          store.start_result_job(str(run)), analysis_id="tests.corr", action="Plot", computed_at=1.0)
    converted_folder(str(tmp_path / "temps"), "path:" + os.path.abspath(run), run, {1: "cache"})
    return run, [mount.path, mount.source]


def test_an_unverified_drive_says_so_never_ram_only(usb: tuple[Path, list[str]], tmp_path: Path) -> None:
    """FI-2: the admin opener leaves an unverified mount out of its resolver (plain ``NoDataRoot`` there); the read says
    "unverified", never "no data root" (which reads as RAM only, nothing cached)."""
    run, verified = usb
    info, _ = ask(run, tmp_path / "temps", verified_volumes=[])
    assert info["root_state"] == "unverified" and info["key"] == ""
    assert {part["status"] for name, part in info["parts"].items() if name != "converted"} == {"skipped"}
    assert "not yet verified" in info["parts"]["raw"]["error"]
    info, _ = ask(run, tmp_path / "temps", verified_volumes=[verified])
    assert info["root_state"] == "rooted" and info["raw"]["shots"] == 2


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


# The per-folder Clears (Q~6, Q64.6 b; Tony 2026-11-05): Folder info's Clear raw pulses…, Clear this folder's saved
# results… and Clear this folder's converted TXY…, through the store's own removals scoped to one folder.

def clear(action: str, **params: Any) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    cache_admin(store_options(), action, sent.append, **params)  # type: ignore[arg-type]
    assert sent[-1]["kind"] == "admin_result" and sent[-1]["action"] == action
    return sent


def other_folder(tmp_path: Path) -> Path:
    """A second folder below the same data root, with raw pulses and a saved result of its own."""
    y = tmp_path / "data" / "y"
    with opened(y) as store:
        store.save_raw_batch(str(y), [raw_entry(store, shot) for shot in (1, 2)], store.start_raw_job(str(y)))
        store.save_result(str(y), "k1", "f", record({"bins": 5}), store.write_result_file(b"z" * 80),
                          store.start_result_job(str(y)), analysis_id="tests.corr", action="Plot", computed_at=1000.0)
    return y


def counts(path: Path) -> tuple[int, int, int]:
    """(raw rows, TXY layers, saved results) the store holds for ``path``."""
    with opened(path) as store, store.transaction(write=False):
        key = store._path_key(str(path))
        return tuple(int(store._conn.execute(f"SELECT COUNT(*) FROM {table} WHERE path = ?", (key,)).fetchone()[0])
                     for table in ("raw_layers", "txy_layers", "results"))  # type: ignore[return-value]


def test_clear_raw_pulses_takes_this_folders_only_and_names_its_only_copies(tmp_path: Path,
                                                                            untouched: list[str]) -> None:
    from helab.utils import folder_info as model
    x, y = seed(tmp_path), other_folder(tmp_path)
    info, _ = ask(x)
    question = model.clear_question(info, "clear_raw", str(x), time.time())
    assert question is not None and question.warn and question.accept == "Remove cached raw pulses"
    assert question.text.startswith(f"Remove HeLab's cached raw pulses of x ({model.size(info['raw']['bytes'])})? "
                                    "Your d files aren't touched.")
    assert "1 of them are the only copy: their raw files are gone from the folder" in question.text
    with opened(x) as store:
        running = store.start_raw_job(str(x))  # (A raw_fill that started before the Clear.)
    sent = clear("clear_raw", paths=[str(x)])
    [removed] = [event for event in sent if event["kind"] == "removed"]
    assert removed["kinds"] == ["raw"] and removed["paths"] == [str(x)] and removed["raw"] == 3
    assert removed["bytes"] == info["raw"]["bytes"]
    assert counts(x) == (0, 3, 3) and counts(y) == (2, 0, 1)  # (Its layers and results stay; y untouched.)
    with opened(x) as store, pytest.raises(cache_store.SaveRejected):
        store.save_raw_batch(str(x), [raw_entry(store, 4)], running)  # (Fenced: it can't bring them back.)
    assert untouched == []


def test_clear_saved_results_takes_this_folders_only(tmp_path: Path) -> None:
    from helab.utils import folder_info as model
    x, y = seed(tmp_path), other_folder(tmp_path)
    info, _ = ask(x)
    question = model.clear_question(info, "clear_results", str(x), time.time())
    assert question is not None and not question.warn and question.accept == "Remove saved results"
    assert question.text.startswith(f"Remove the 3 saved plot results of x ({model.size(250)})?")
    with opened(x) as store:
        running = store.start_result_job(str(x))
    sent = clear("clear_results", paths=[str(x)])
    [removed] = [event for event in sent if event["kind"] == "removed"]
    assert (removed["kinds"], removed["paths"], removed["results"], removed["bytes"]) == (["results"], [str(x)], 3, 250)
    assert counts(x) == (3, 3, 0) and counts(y) == (2, 0, 1)
    with opened(x) as store, pytest.raises(cache_store.SaveRejected):
        store.save_result(str(x), "k9", "f", record({"bins": 1}), store.write_result_file(b"q"), running,
                          analysis_id="tests.corr", action="Plot", computed_at=1.0)


def converted_folder(base: str, key: str, source: Path, shots: dict[int, str]) -> str:
    """HeLab's folder for ``source`` in ``base``: each shot's TXY file (output cache) or a beside row, in its index."""
    folder = folder_for(base, key)
    os.makedirs(folder, exist_ok=True)
    index = open_index(os.path.dirname(folder), write=True)
    try:
        for shot, output in shots.items():
            entry = provenance(shot, "m19v1", output, 1000 + shot)
            if output != "beside":
                txy = Path(folder, entry.txy_name)
                txy.write_bytes(b"t" * entry.txy_size)
                entry = Provenance(**{**{field.name: getattr(entry, field.name) for field in fields(Provenance)},
                                      "txy_mtime_ns": txy.stat().st_mtime_ns})
            index.record(os.path.basename(folder), key, str(source), entry, 500.0)
    finally:
        index.close()
    return folder


def test_clear_converted_txy_takes_this_folders_only_never_beside_and_names_only_copies(
        tmp_path: Path, untouched: list[str]) -> None:
    from helab.convert.provenance import fence_of
    from helab.utils import folder_info as model
    x, y = seed(tmp_path), other_folder(tmp_path)  # (x's shot 3: raw pulses whose d file was gone.)
    with opened(x) as store:
        keys = store._path_key(str(x)), store._path_key(str(y))
    cache_base = os.path.dirname(store_options()["directory"])
    mine = converted_folder(cache_base, keys[0], x, {1: "cache", 3: "cache", 4: "beside"})
    theirs = converted_folder(cache_base, keys[1], y, {1: "cache"})
    root = os.path.dirname(mine)
    before = fence_of(root)
    info, _ = ask(x)
    [base] = [base for base in info["converted"] if base["base"] == "cache"]
    assert [(tag["output"], tag["shots"], tag["only_copy"]) for tag in base["tags"]] == [("beside", 1, 0),
                                                                                         ("cache", 2, 1)]
    question = model.clear_question(info, "clear_converted", str(x), time.time())
    assert question is not None and question.warn and question.accept == "Remove converted TXY"
    assert question.text.startswith(f"Remove HeLab's converted TXY of x: 2 shots ({model.size(2004)}) in HeLab's cache "
                                    "folder? Your d files aren't touched, nor TXY written beside them")
    assert f"1 of them ({model.size(1003)}) are the only copy of that TXY" in question.text
    sent = clear("clear_converted_txy", path=str(x))
    [removed] = [event for event in sent if event["kind"] == "removed"]
    assert removed["kinds"] == ["converted_txy"] and removed["paths"] == [str(x)] and removed["bytes"] == 2004
    assert not os.path.exists(mine) or os.listdir(mine) == []
    assert sorted(os.listdir(theirs)) == ["d_txy_helab_m19v1_1.txt"]
    index = open_index(root, write=False)
    assert index is not None
    try:
        assert [(record.shot, record.output) for record in index.shots(os.path.basename(mine)).values()] == [
            (4, "beside")]  # (The beside TXY's row stays: the only account of how it was made.)
        assert list(index.shots(os.path.basename(theirs))) == [("m19v1", 1)]
    finally:
        index.close()
    assert fence_of(root) != before  # (Fenced: a conversion running into this base writes no TXY after it.)
    assert untouched == []  # (The source folder, where beside TXY are, is never looked at.)


def test_a_refused_or_failed_clear_says_so_and_removes_nothing(usb: tuple[Path, list[str]], tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """FI-2: on a drive not verified this session (the real opener) each Clear refuses as unverified, the converted one
    too (never falling back to the temp folder's by-path folder); a failing store removes nothing either."""
    from helab.utils.data_roots import VolumeUnverified
    run, verified = usb
    temps = str(tmp_path / "temps")
    by_path = folder_for(temps, "path:" + os.path.abspath(run))
    for action, params in (("clear_raw", {"paths": [str(run)]}), ("clear_results", {"paths": [str(run)]}),
                           ("clear_converted_txy", {"path": str(run), "temps": temps})):
        with pytest.raises(VolumeUnverified):
            cache_admin(store_options(), action, lambda event: None, verified_volumes=[], **params)
    assert counts(run) == (2, 0, 1) and os.listdir(by_path) == ["d_txy_helab_m19v1_1.txt"]

    def failing(self: CacheStore, *args: Any, **kwargs: Any) -> Any:
        raise cache_store.StoreError("Disk cache could not be written: disk I/O error")
    with monkeypatch.context() as patched, pytest.raises(cache_store.StoreError, match="disk I/O error"):
        patched.setattr(cache_store.CacheStore, "remove_raw", failing)
        cache_admin(store_options(), "clear_raw", lambda event: None, paths=[str(run)], verified_volumes=[verified])
    assert counts(run) == (2, 0, 1)
    clear("clear_raw", paths=[str(run)], verified_volumes=[verified])  # (Verified: it clears.)
    assert counts(run) == (0, 0, 1)


def test_the_app_clears_one_folder_on_the_local_lane_with_its_verified_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    from helab.utils.folder_cache import FolderCache
    from helab.utils.io_service import IOService
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    cache = FolderCache(service)
    try:
        owners = {part: cache.clear_folder("/data/x", part) for part in ("raw", "results", "converted")}
        sent = {part: next(r for r in service.pending if r.owner == owner).payload for part, owner in owners.items()}
        assert [(payload["action"], {name: value for name, value in payload["params"].items()
                                     if name in ("path", "paths")}) for payload in sent.values()] == [
            ("clear_raw", {"paths": ["/data/x"]}), ("clear_results", {"paths": ["/data/x"]}),
            ("clear_converted_txy", {"path": "/data/x"})]
        assert all("verified_volumes" in payload["params"] for payload in sent.values())
        assert sent["converted"]["params"]["temps"]
        with pytest.raises(ValueError):
            cache.clear_folder("/data/x", "everything")
    finally:
        service.shutdown()
