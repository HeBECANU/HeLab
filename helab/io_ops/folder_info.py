"""Folder info's read (``cache_admin`` "folder_info", Q64.1–Q64.10): everything the disk cache and HeLab's
converted-TXY index hold for one folder, as one bounded ``folder_info`` event.

It reads the store (one read transaction, ``CacheStore.folder_contents``) and each base's
``converted-txy/index.sqlite``, read only, and never the source folder: no ``stat``, listing or open of it
or anything in it. A part that can't be read is an error of its own, never "nothing saved"; the store
failing to read at all is the job's ``StoreError``. Nothing grows with a folder's shots: counts, ranges and
dates only, at most ``MAX_RESULTS`` results and ``MAX_ROWS`` layers and views, settings texts cut to
``SETTINGS_SHORT`` and ``SETTINGS_FULL`` characters.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Mapping, TypeVar

from helab.io_ops import helab_txy
from helab.io_ops.events import (FolderConvertedBase, FolderConvertedTag, FolderInfoEvent, FolderInfoPart,
                                 FolderLayerField, FolderRawField, FolderResultRow, FolderResultsInfo,
                                 FolderViewField)

if TYPE_CHECKING:
    from helab.utils.cache_store import CacheStore, Read

# The bounds of one answer (a folder with thousands of shots or results never makes a large event).
MAX_RESULTS = 200
MAX_ROWS = 32
SETTINGS_SHORT = 160
SETTINGS_FULL = 2000
# The parts an answer names (``parts``), in the window's order.
PARTS = ("raw", "layers", "views", "seed", "results", "prefs", "convert_prefs", "choices", "constants", "history",
         "summary", "listing", "converted")
STORE_V4_PARTS = ("raw", "layers", "views", "seed", "results")

T = TypeVar("T")
RootState = Literal["rooted", "no_root", "unverified"]


def folder_info(store: CacheStore, path: str, cache_directory: str, temps: str = "",
                now: Callable[[], float] = time.time) -> FolderInfoEvent:
    """The ``folder_info`` event for ``path`` from ``store`` (opened by the admin job) and the converted-TXY indexes
    of the cache folder (``cache_directory``'s parent) and ``temps``."""
    from helab.utils.data_roots import NoDataRoot, VolumeUnverified
    from helab.utils.cache_paths import UnresolvedRemotePath
    event: FolderInfoEvent = {
        "kind": "folder_info", "path": path, "key": "", "root_state": "rooted", "layout": int(store.layout),
        "read_at": now(), "store": store.store_id, "parts": {}, "raw": None, "layers": [], "layers_more": 0,
        "views": [], "views_more": 0, "seed_bytes": 0, "results": None, "prefs": None, "convert_prefs": None,
        "choices": None, "constants": None, "history": None, "summary": None, "listing_at": None, "converted": []}
    parts = event["parts"]
    state: RootState = "rooted"
    why = ""
    try:
        event["key"] = folder_key(store, path)
    except VolumeUnverified as exc:
        state, why = "unverified", str(exc) or "its drive isn't verified yet this session"
    except (NoDataRoot, UnresolvedRemotePath) as exc:
        state, why = "no_root", str(exc) or "no .helab-root found here or above"
    event["root_state"] = state
    if state != "rooted":
        for name in PARTS[:-1]:
            parts[name] = {"status": "skipped", "error": why}
    gone: frozenset[int] = frozenset()
    if state == "rooted":
        gone = _store_parts(store, path, event)
    event["converted"] = converted(path, event["key"], cache_directory, temps, gone)
    statuses = {base["status"] for base in event["converted"]}
    parts["converted"] = ({"status": "error", "error": next(base["error"] for base in event["converted"]
                                                             if base["status"] == "error")}
                          if "error" in statuses else {"status": "found" if "found" in statuses else "missing",
                                                       "error": ""})
    return event


def folder_key(store: CacheStore, path: str) -> str:
    """``path``'s store key, as the admin job's opener resolves it. A folder on a mount whose volume this session
    hasn't verified raises ``VolumeUnverified`` (the opener leaves that mount out and raises plain ``NoDataRoot``
    for it, as ``constants`` and the offline listing find through ``store._unverified_mounts``): never "no data
    root", which would read as RAM only. No data root at all raises ``NoDataRoot``."""
    from helab.utils.cache_paths import _inside, _normal
    from helab.utils.data_roots import NoDataRoot, VolumeUnverified
    try:
        return store._path_key(path)
    except VolumeUnverified:
        raise
    except NoDataRoot:
        if any(_inside(_normal(path), _normal(mount)) for mount in store._unverified_mounts):
            raise VolumeUnverified(path) from None
        raise


def _part(read: Read[Any]) -> FolderInfoPart:
    return {"status": read.status, "error": read.error}


def _store_parts(store: CacheStore, path: str, event: FolderInfoEvent) -> frozenset[int]:
    """Fill ``event`` from the store's parts; the shots whose d files a listing found gone (for ``converted``)."""
    from helab.utils import store_v4
    contents = store.folder_contents(path, max_results=MAX_RESULTS)
    parts = event["parts"]
    v4 = store.layout >= store_v4.LAYOUT
    for name in PARTS[:-1]:
        read: Read[Any] = getattr(contents, name)
        parts[name] = ({"status": "skipped", "error": "store-v3"} if name in STORE_V4_PARTS and not v4
                       else _part(read))
    gone: frozenset[int] = frozenset()
    if contents.raw.found and contents.raw.value is not None:
        raw = contents.raw.value
        gone = frozenset(raw.get("gone_shots") or ())
        if int(raw["shots"] or 0) == 0:
            parts["raw"] = {"status": "missing", "error": ""}
        event["raw"] = _raw(raw)
    if contents.layers.found and contents.layers.value is not None:
        layers = contents.layers.value
        if not layers:
            parts["layers"] = {"status": "missing", "error": ""}
        event["layers"] = [_layer(layer) for layer in layers[:MAX_ROWS]]
        event["layers_more"] = max(0, len(layers) - MAX_ROWS)
    if contents.views.found and contents.views.value is not None:
        views = contents.views.value
        if not views:
            parts["views"] = {"status": "missing", "error": ""}
        event["views"] = [FolderViewField(source=str(view["source"]), tag=str(view["tag"]),
                                          last_used=float(view["last_used"])) for view in views[:MAX_ROWS]]
        event["views_more"] = max(0, len(views) - MAX_ROWS)
    if contents.seed.found:
        event["seed_bytes"] = int(contents.seed.value or 0)
        if not event["seed_bytes"]:
            parts["seed"] = {"status": "missing", "error": ""}
    if contents.results.found and contents.results.value is not None:
        found = contents.results.value
        if not found["count"]:
            parts["results"] = {"status": "missing", "error": ""}
        rows = [result_row(row) for row in found["rows"]]
        event["results"] = FolderResultsInfo(count=int(found["count"]), bytes=int(found["bytes"]), rows=rows,
                                             more=max(0, int(found["count"]) - len(rows)))
    def value(read: Read[dict[str, Any]]) -> dict[str, Any] | None:
        return dict(read.value or {}) if read.found else None
    event["prefs"], event["convert_prefs"] = value(contents.prefs), value(contents.convert_prefs)
    event["choices"], event["constants"] = value(contents.choices), value(contents.constants)
    event["history"] = value(contents.history)
    if contents.summary.found and isinstance(contents.summary.value, dict):
        summary = contents.summary.value
        event["summary"] = {name: summary.get(name) for name in (
            "status", "count", "raw_count", "txy_count", "scanned_at", "empty", "has_dirs")}
    if contents.listing.found and isinstance(contents.listing.value, dict):
        listed = contents.listing.value.get("listed_at")
        event["listing_at"] = float(listed) if isinstance(listed, (int, float)) else None
    return gone


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _raw(raw: Mapping[str, Any]) -> FolderRawField:
    def shot(value: Any) -> int | None:
        return None if value is None else int(value)
    return FolderRawField(
        shots=int(raw["shots"] or 0), bytes=int(raw["bytes"] or 0), first=shot(raw["first"]), last=shot(raw["last"]),
        saved_first=_number(raw["saved_first"]), saved_last=_number(raw["saved_last"]),
        last_used=_number(raw["last_used"]), seen_at=_number(raw["seen_at"]), only_copy=int(raw["only_copy"] or 0),
        only_copy_bytes=int(raw["only_copy_bytes"] or 0), gone_first=_number(raw["gone_first"]),
        gone_last=_number(raw["gone_last"]))


def _layer(layer: Mapping[str, Any]) -> FolderLayerField:
    return FolderLayerField(
        layer=str(layer["layer"]), tags=[str(tag) for tag in layer["tags"]][:MAX_ROWS], shots=int(layer["shots"]),
        first=layer["first"], last=layer["last"], rows=int(layer["rows"]), bytes=int(layer["bytes"]),
        precision=str(layer["precision"]), saved_at=float(layer["saved_at"]), last_used=float(layer["last_used"]),
        seen_at=float(layer["seen_at"]), gone_at=_number(layer["gone_at"]), group=str(layer["group"]))


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:max(0, limit - 1)] + "…"


def setting_text(value: Any) -> str:
    """One setting's value as a short text: numbers with up to 6 significant digits, text as it is."""
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}" if math.isfinite(value) else str(value)
    if isinstance(value, (int, str)):
        return str(value)
    try:
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def settings_texts(parameters: Mapping[str, Any], unused: Any = ()) -> tuple[str, str]:
    """A result's settings in short (``name=value`` joined by " · ", cut to ``SETTINGS_SHORT``) and in full (one per
    line, cut to ``SETTINGS_FULL``); the parameters the run didn't use are left out."""
    skipped = set(unused or ())
    pairs = [f"{name}={setting_text(value)}" for name, value in sorted(parameters.items()) if name not in skipped]
    return _cut(" · ".join(pairs), SETTINGS_SHORT), _cut("\n".join(pairs), SETTINGS_FULL)


def result_row(row: Mapping[str, Any]) -> FolderResultRow:
    """A saved result's row for the event, its record decoded for the script and settings (no data: a record holds
    none); a record that can't be decoded keeps its row, ``damaged``."""
    analysis_id, version, file_name, short, full, damaged = str(row["analysis_id"]), "", "", "", "", False
    try:
        from helab.analysis import result_cache
        result = result_cache.result_from(json.loads(str(row["record"])), None)
        analysis_id = result.analysis.analysis_id or analysis_id
        version, file_name = str(result.analysis.version), str(result.analysis.file_name)
        short, full = settings_texts(result.parameters, result.unused)
    except Exception:  # (A damaged or foreign record: shown as unreadable, never left out.)
        damaged = True
    return FolderResultRow(
        result_id=str(row["result_id"]), analysis_id=analysis_id, version=version, file_name=file_name,
        action=str(row["action"]), settings=short, settings_full=full, bytes=int(row["bytes"]),
        computed_at=float(row["computed_at"]), saved_at=float(row["saved_at"]), last_used=float(row["last_used"]),
        damaged=damaged)


def converted(path: str, key: str, cache_directory: str, temps: str,
              gone: frozenset[int] = frozenset()) -> list[FolderConvertedBase]:
    """HeLab's converted TXY of ``path`` in each base's folder for it (``helab_txy.folders``: the cache folder by
    key, the temp folder by key and by path), as each base's index records them, read only. ``gone``: the shots
    whose d files HeLab last saw gone; their TXY in HeLab's folders (never beside ones) count as only copies."""
    from helab.convert.provenance import INDEX_NAME, open_index
    cache_root = helab_txy.converted_root(cache_directory) if cache_directory else ""
    options = {"cache_base": os.path.dirname(os.path.abspath(cache_directory)) if cache_directory else "",
               "temps": temps}
    found: list[FolderConvertedBase] = []
    for folder in helab_txy.folders(path, options, key):
        root, name = os.path.dirname(folder), os.path.basename(folder)
        entry = FolderConvertedBase(base="cache" if cache_root and os.path.normcase(root) == os.path.normcase(cache_root)
                                    else "temp", folder=folder, status="missing", error="", last_used=None, tags=[])
        found.append(entry)
        index = open_index(root, write=False)
        if index is None:
            if os.path.isfile(os.path.join(root, INDEX_NAME)):  # (HeLab's own folder, never a source folder.)
                entry["status"] = "error"
                entry["error"] = ("HeLab's TXY index here can't be read (damaged, busy, or a newer HeLab's): its shots "
                                  "only convert again")
            continue
        try:
            groups: dict[tuple[str, str], FolderConvertedTag] = {}
            for record in index.shots(name).values():
                group = groups.setdefault((record.profile_tag, record.output), FolderConvertedTag(
                    tag=record.profile_tag, profile=record.profile_name, version=int(record.profile_version),
                    output=record.output, shots=0, bytes=0, newest=None, only_copy=0, only_copy_bytes=0))
                group["shots"] += 1
                group["bytes"] += int(record.txy_size)
                if record.output != "beside" and int(record.shot) in gone:
                    group["only_copy"] += 1
                    group["only_copy_bytes"] += int(record.txy_size)
                group["newest"] = max(group["newest"] or 0.0, float(record.converted_at))
            used = next((row[4] for row in index.folders() if row[0] == name), None)
        except Exception as exc:  # (sqlite3.Error, or a row of another shape.)
            entry["status"], entry["error"] = "error", f"HeLab's TXY index here can't be read ({exc})"
            continue
        finally:
            index.close()
        entry["status"] = "found" if groups else "missing"
        entry["last_used"] = None if used is None else float(used)
        entry["tags"] = sorted(groups.values(), key=lambda tag: (tag["output"], tag["tag"]))[:MAX_ROWS]
    return found
