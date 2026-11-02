"""A load's disk cache, as ``loading`` and ``save_held`` use it (caching v2 stage 2, design addendum §4–§6).

In store-v3 (the switch off) this is the folder's dataset row and file, as before. In store-v4 the data is in
the folder's TXY layers and a **view** (``txy_views``, one per source identity and profile asked for) stands
in for the row. ``Access`` gives ``loading._load`` the same calls either way, so its checks (the quick check,
``whole``, ``same_kind``, the missing-shot rule) are unchanged:

- ``row`` and ``full``: the view as a dataset row (its fingerprint is the composition's: each shot's chosen
  TXY file, as today), and a loader for its shots' arrays from their layers;
- ``confirm``: a load that found every shot unchanged writes the view's ``info`` only, the signature and the
  TXY record included (A40.3): in store-v4 a signature-only change never rewrites data;
- ``write``: one save unit (``CacheStore.save_txy``): per layer, a segment of the shots its entries lack
  or hold under another key, and the view. Shots already in a layer under their current key aren't
  written again, and a held shot the layers have isn't read from the share again for the save.

A layer entry's key (Q45.3): MATLAB's shots by their TXY file; HeLab's by the raw file wherever one is
listed (a re-conversion, or a Clear of ``converted-txy/``, is then the same data), else by the TXY file.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING

from helab.io_ops.infra import Emit, _entry_stat
from helab.utils import txy_sources

if TYPE_CHECKING:
    from helab.utils.cache_store import CacheStore, Read, SaveGuard

LAYERED_FORMAT = "txy-views-1"


def layered(store: CacheStore | None) -> bool:
    """Whether ``store`` keeps TXY layers (store-v4)."""
    from helab.utils.store_v4 import LAYOUT
    return store is not None and store.layout >= LAYOUT


def view_key(txy_source: str, txy: Mapping[str, Any]) -> tuple[str, str]:
    """A composition's view: the source as identities name it (the two priority modes share one, S~4) and
    the HeLab profile asked for (its content hash, else its tag; "" when no HeLab TXY is read)."""
    if not txy_sources.wants_helab(txy_source):
        return txy_sources.identity_source(txy_source), ""
    return txy_sources.identity_source(txy_source), str(txy.get("profile_hash") or txy.get("profile_tag") or "")


def layer_of(origin: str) -> str:
    """The layer a shot of this origin (``""``: MATLAB's; ``helab:<hash>``) is kept in."""
    from helab.convert import txy_layer
    return txy_layer.helab_layer(origin.split(":", 1)[1]) if origin else txy_layer.MATLAB


def builtin_for_tag(tag: str) -> dict[str, Any] | None:
    """A built-in profile's TXY options by its tag (``profile_hash``, ``profile_tag``, ``profile``), or None."""
    from helab.convert.profile import BUILTIN_PROFILES, file_tag
    for profile in BUILTIN_PROFILES.values():
        if file_tag(profile) == tag:
            return {"profile_hash": profile.content_hash(), "profile_tag": tag,
                    "profile": {"name": profile.name, "version": profile.version, "calibrated": profile.calibrated}}
    return None


def entry_keys(fingerprint: Sequence[Sequence[int]], origins: Mapping[int, str],
               raw_entries: Mapping[int, os.DirEntry[str]]) -> dict[int, tuple[int, int, str]]:
    """Each shot's layer key: (size, mtime_ns, kind) of its raw file (HeLab's, where listed) or its TXY file."""
    keys: dict[int, tuple[int, int, str]] = {}
    for shot, size, modified in fingerprint:
        entry = raw_entries.get(int(shot)) if origins.get(int(shot)) else None
        if entry is not None:
            try:
                info = _entry_stat(entry, "load: raw key")
                keys[int(shot)] = (int(info.st_size), int(info.st_mtime_ns), "raw")
                continue
            except OSError:
                pass  # (Gone meanwhile: keyed by its TXY file.)
        keys[int(shot)] = (int(size), int(modified), "txy")
    return keys


class Access:
    """One load's (or Live save's) disk cache: a store-v3 folder's dataset, or a store-v4 view and its layers."""

    def __init__(self, store: CacheStore, txy_source: str, txy: Mapping[str, Any]) -> None:
        self.store = store
        self.layered = layered(store)
        self.key = view_key(txy_source, txy)
        self.layers: dict[int, str] = {}  # (The last view read: each shot's layer.)
        self.info: dict[str, Any] = {}
        # Where the row came from when the folder has no view yet (store-v4): "datasets" (its own, from stage
        # 1, Q45.4) or "legacy" (store-v3's under Keep, Q45.5). A load then copies its shots into the layers.
        self.seed = ""

    @classmethod
    def for_cached_read(cls, store: CacheStore, path: str, txy: Mapping[str, Any] | None) -> Access:
        """A cached read's access: the view of ``txy``'s source; without one (a read that doesn't say), the
        folder's view used last, the priority modes' (identity "") first."""
        if txy or not layered(store):
            source = txy_sources.requested_source((txy or {}).get("source"))
            return cls(store, source, txy or {})
        access = cls(store, txy_sources.DEFAULT_SOURCE, {})
        views = store.folder_views(path)
        if views:
            access.key = min(views, key=lambda item: (item[0] != "", -item[2]))[:2]
        return access

    @property
    def signature_matters(self) -> bool:
        """Whether a signature-only change makes the cached data not whole (store-v3's rewrite, io-5); in
        store-v4 it only updates the view (A40.3)."""
        return not self.layered

    def row(self, path: str) -> Read[Any]:
        if not self.layered:
            return self.store.read_dataset_row(path)
        return self._view_row(path)

    def full(self, path: str) -> Read[tuple[Any, Callable[[], dict[int, Any] | None]]]:
        """The row with a loader of its data (``None`` from the loader: unreadable or incomplete)."""
        from helab.utils.cache_store import _found, unpack_dataset
        if not self.layered:
            found = self.store.read_dataset(path)
            if found.value is None:
                return found  # type: ignore[return-value]
            row, packed = found.value
            return _found((row, lambda: unpack_dataset(packed)))
        read = self._view_row(path)
        if read.value is None:
            return read
        if self.seed:
            seeded = (self.store.read_dataset(path) if self.seed == "datasets" else self.store.legacy_dataset(path))
            if seeded.value is None:
                return seeded  # type: ignore[return-value]
            seed_row, packed = seeded.value
            return _found((seed_row, lambda: unpack_dataset(packed)))
        row = read.value
        return _found((row, lambda: self._read_data(path, row)))

    def _view_row(self, path: str) -> Read[Any]:
        from helab.utils.cache_store import TXY_ROW_BYTES, _error, _found
        self.seed = ""
        found = self.store.read_view(path, *self.key)
        if found.value is None:
            return found if found.failed else self._seed_row(path)
        view = found.value
        layers = self.store.txy_layers(path)
        if layers.failed:
            return _error(layers.error)
        held = layers.value or {}
        self.layers = {int(entry[0]): str(entry[4]) for entry in view.fingerprint}
        rows = sum(held[layer].entries[shot].rows for shot, layer in self.layers.items()
                   if layer in held and shot in held[layer].entries)
        self.info = dict(view.info)
        return _found({"path": view.path, "file": "", "fingerprint": [list(entry[:3]) for entry in view.fingerprint],
                       "problematic": view.problematic, "raw_times": view.raw_times, "info": view.info,
                       "rows": rows, "shots": len(view.fingerprint), "ram_bytes": rows * TXY_ROW_BYTES,
                       "bytes": sum(held[layer].bytes for layer in set(self.layers.values()) if layer in held),
                       "last_used": view.last_used, "job_seq": view.job_seq})

    def _seed_row(self, path: str) -> Read[Any]:
        """No view yet: store-v4's own ``datasets`` row of the folder (stage 1's, Q45.4), else store-v3's under
        Keep (Q45.5), as the load's cached data; both read only. A load's save then writes them into layers."""
        own = self.store.read_dataset_row(path)
        if own.value is not None or own.failed:
            self.seed = "datasets" if own.value is not None else ""
            return own
        legacy = self.store.legacy_dataset(path, with_file=False)
        if legacy.value is None:
            return legacy
        self.seed = "legacy"
        from helab.utils.cache_store import _found
        return _found(legacy.value[0])

    def _read_data(self, path: str, row: Mapping[str, Any]) -> dict[int, Any] | None:
        """The view's shots from their layers; the shots a layer no longer holds are left out (a policy
        that writes no HeLab layer, a Make room since). None when a layer can't be read."""
        by_layer: dict[str, list[int]] = {}
        for shot, layer in self.layers.items():
            by_layer.setdefault(layer, []).append(shot)
        data: dict[int, Any] = {}
        for layer, shots in by_layer.items():
            read = self.store.read_txy_shots(path, layer, shots)
            if read.failed:
                return None
            data.update(read.value or {})
        return data

    def from_raw(self, path: str, shot: int, key: tuple[int, int, str] | None, origin: str) -> Any | None:
        """The loading order's second step (design addendum §4): a HeLab shot from the raw layer instead of
        its TXY text, when the raw layer holds the raw file's current fingerprint with the current parser and
        the shot's profile is a built-in (its hash). Converted and formatted as the converter writes it, then
        parsed as a TXY file is (``infra._read_txy_file``), so the data is the text's exactly. None when it
        can't be (the text is read)."""
        if not self.layered or key is None or key[2] != "raw" or not origin:
            return None
        import io
        import numpy as np
        import pandas as pd
        from helab.convert import raw_layer
        from helab.convert.profile import BUILTIN_PROFILES
        from helab.convert.reconstruct import reconstruct
        from helab.convert.txy import format_txy
        wanted = origin.split(":", 1)[1]
        profile = next((item for item in BUILTIN_PROFILES.values() if item.content_hash() == wanted), None)
        if profile is None:
            return None
        read = self.store.read_raw(path, shot)
        if read.value is None:
            return None
        row, packed = read.value
        if (row.size, row.mtime_ns, row.parser) != (key[0], key[1], raw_layer.RAW_PARSER_VERSION):
            return None
        try:
            layer, _ = raw_layer.from_hlb(packed)
            text = format_txy(reconstruct(raw_layer.decode(layer), profile))
        except Exception:  # (A layer or backend that can't: the text is read.)
            return None
        if not text:
            return np.empty((0, 3), dtype=np.float64)
        frame = pd.read_csv(io.BytesIO(text), sep=",", names=["t", "x", "y"], dtype=np.float64)
        return np.asarray(frame.dropna(), dtype=np.float64)

    def touch(self, path: str) -> None:
        if not self.layered or self.seed:
            from helab.io_ops.fingerprints import _touch
            _touch(self.store, path)
            return
        self.store.touch_txy(path, set(self.layers.values()), self.key)

    def confirm(self, path: str, fingerprint: Sequence[Sequence[int]], names: list[str], listed_at: float,
                guard: SaveGuard, txy_guard: SaveGuard | None, raw_times: list[list[int]] | None,
                folder_mtime_ns: int | None, *, signature: str, txy_record: Mapping[str, Any]) -> None:
        """A load found the cache whole: it dates from this listing. In store-v4 also the signature and TXY
        record (with HeLab's folders), so the next quick check passes (A40.3)."""
        if not self.layered:
            self.store.confirm_dataset(path, fingerprint, names, listed_at, guard, raw_times, folder_mtime_ns)
            return
        if txy_guard is None:
            return
        info = {**self.info, "names": names, "snapshot_at": listed_at, "unsettled": 0, "signature": signature,
                txy_sources.TXY_FIELD: dict(txy_record)}
        if folder_mtime_ns is not None or "folder_mtime_ns" not in info:
            info["folder_mtime_ns"] = folder_mtime_ns
        view = [[int(shot), int(size), int(modified), "txy", self.layers.get(int(shot), layer_of(""))]
                for shot, size, modified in fingerprint]
        self.store.confirm_view(path, *self.key, view, info, txy_guard, raw_times=raw_times)

    def lacking(self, path: str, shots: set[int], keys: Mapping[int, tuple[int, int, str]],
                origins: Mapping[int, str]) -> set[int]:
        """Of ``shots`` (held by the caller, not in the load's data), those a save must read again: all of them
        in store-v3 (a dataset is written whole); in store-v4 only those no layer holds under their key."""
        if not self.layered:
            return set(shots)
        held = self.store.txy_layers(path).value or {}
        missing: set[int] = set()
        for shot in shots:
            layer = held.get(layer_of(origins.get(shot, "")))
            entry = layer.entries.get(shot) if layer is not None else None
            if entry is None or (entry.size, entry.mtime_ns, entry.kind) != keys.get(shot):
                missing.add(shot)
        return missing

    def mark_seen(self, path: str, raw_shots: Sequence[int], txy_shots: Sequence[int], listed_at: float) -> None:
        """A full listing's sources, for Make room's only copies (Q45.6); best effort."""
        if not self.layered or self.store.read_only:
            return
        from helab.utils.cache_store import StoreError
        try:
            self.store.mark_txy_seen(path, {"raw": {int(shot): (0, 0) for shot in raw_shots},
                                            "txy": {int(shot): (0, 0) for shot in txy_shots}}, listed_at)
        except StoreError:
            pass

    def write(self, path: str, txy_guard: SaveGuard, data: Mapping[int, Any], fingerprint: Sequence[Sequence[int]],
              problematic: Sequence[int], info: dict[str, Any], keys: Mapping[int, tuple[int, int, str]],
              origins: Mapping[int, str], raw_times: list[list[int]], txy_record: Mapping[str, Any],
              cache_options: Mapping[str, Any], send: Emit, *, hold: bool = True,
              seen_at: float | None = None) -> None:
        """store-v4's save of one load or Live save (design addendum §5): a part per layer with the shots it
        lacks, and the view; the same events as a dataset save (``cache_saved``, or the pending question).
        Raises on failure (``_save_failed``)."""
        from helab.convert import txy_layer
        from helab.utils import store_v4
        from helab.utils.cache_store import TxyPart, TxyShot, ViewRecord
        held = self.store.txy_layers(path).value or {}
        flagged = {int(shot) for shot in problematic}
        groups: dict[str, dict[int, Any]] = {}
        for shot, _, _ in fingerprint:
            shot = int(shot)
            if shot not in data:
                continue
            layer = layer_of(origins.get(shot, ""))
            entry = held[layer].entries.get(shot) if layer in held else None
            if entry is not None and (entry.size, entry.mtime_ns, entry.kind) == keys[shot] and (
                    entry.problematic == (shot in flagged)):
                continue  # (Already kept under its key.)
            groups.setdefault(layer, {})[shot] = data[shot]
        tag = str(txy_record.get("profile_tag") or "")
        maker = self.store._maker_record()
        parts: list[TxyPart] = []
        for layer, shots in sorted(groups.items()):
            tags = (tag,) if tag and layer != txy_layer.MATLAB else ()
            # (Read from TXY text: the values its 8 significant figures parse to. A full-precision layer, Q19.6,
            # comes with conversion from the raw layer.)
            precision = "g8"
            file = self.store.write_txy_file(txy_layer.pack_segment(
                shots, layer=layer, problematic=[shot for shot in shots if shot in flagged], tags=tags,
                precision=precision, maker=maker))
            parts.append(TxyPart(layer, file, tuple(
                TxyShot(shot, *keys[shot][:2], keys[shot][2], len(array), shot in flagged)
                for shot, array in sorted(shots.items())), tags, precision))
        saved_info = {**info, "format": LAYERED_FORMAT}
        view: ViewRecord = {
            "fingerprint": [[int(shot), int(size), int(modified), "txy", layer_of(origins.get(int(shot), ""))]
                            for shot, size, modified in fingerprint],
            "problematic": sorted(flagged), "info": saved_info, "raw_times": raw_times}
        result = self.store.save_txy(path, *self.key, parts, view, txy_guard,
                                     budget=cache_options.get("budget"),
                                     budget_set_at=cache_options.get("budget_set_at"),
                                     default_policy=str(cache_options.get("policy") or store_v4.DEFAULT_POLICY),
                                     hold=hold, seen_at=seen_at)
        from helab.io_ops.stores import _deadline
        if result.reason and not hold:
            send({"kind": "cache_warning", "message": "Not cached: it doesn't fit the disk budget"})
            return
        if result.reason:
            send(pending_event(self.store, path, result, txy_guard.job_seq))
            return
        for layer in result.saved:
            self.compact(path, layer, txy_guard, cache_options, send)
        send({"kind": "cache_saved", "cache_info": saved_info, "superseded": [], "job_seq": txy_guard.job_seq,
              "next_deadline": _deadline(self.store), "usage": result.usage,
              "usage_seq": [self.store.store_id, result.usage_seq]})
        send({"kind": "disk_cached", "disk_cached": True})

    def compact(self, path: str, layer: str, txy_guard: SaveGuard, cache_options: Mapping[str, Any],
                send: Emit) -> bool:
        """Q45.7: after a save, a layer of many segments (Live's, one per autosave) or mostly superseded bytes
        is rewritten as one, in the same job, only if that fits beside the old ones; else it waits for a later
        save and never asks. Under the converter's ticker (a large layer's rewrite is progress). Best effort:
        whether it did."""
        from helab.io_ops.convert import _Ticker, compute_budget
        from helab.utils.cache_store import StoreError
        row = (self.store.txy_layers(path).value or {}).get(layer)
        if row is None or not self.store.compaction_due(row):
            return False
        try:
            with _Ticker(send, "compacting", compute_budget(4 * row.bytes)):
                return self.store.compact_txy(path, layer, txy_guard, budget=cache_options.get("budget"),
                                              budget_set_at=cache_options.get("budget_set_at"))
        except (StoreError, OSError):
            return False


def pending_event(store: CacheStore, path: str, result: Any, job_seq: int) -> Any:
    """``cache_full`` or ``cache_approval`` for a waiting unit (as ``loading._pending_event`` for a dataset)."""
    from dataclasses import asdict
    from helab.io_ops.stores import _deadline
    from helab.utils.cache_store import SaveRejected, StoreError
    event: dict[str, Any] = {
        "kind": "cache_full" if result.reason == "over_budget" else "cache_approval",
        "pending_id": result.pending_id, "path": path, "reason": result.reason, "bytes": result.bytes,
        "usage": result.usage, "usage_seq": [store.store_id, result.usage_seq], "created_at": time.time(),
        "budget": result.budget, "job_seq": job_seq, "replaces": 0, "superseded": [],
        "next_deadline": _deadline(store)}
    if result.reason == "over_budget" and result.budget is not None:
        try:
            event["room"] = asdict(store.room_plan(result.pending_id, result.budget))
        except (SaveRejected, StoreError):
            pass
    return event
