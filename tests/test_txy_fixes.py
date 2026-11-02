"""Caching v2 stage 2, the step 3 review's fixes. S3-1: in store-v4 a folder's Clear data cache (``invalidate``)
and a purge of cached data by age take its TXY layers, views and seen raw layers too; only copies stay. S3-2: a
HeLab shot converted from the raw layer is converted before any file is announced, under the converter's ticker.
Temp stores only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

import pytest

from helab.io_ops.admin import cache_admin
from test_txy_loading import data_folder, first, opened, run_load, v4_options


def test_clear_data_cache_takes_a_folders_layers_and_views_in_store_v4(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """S3-1: the helper's ``invalidate`` (FolderExplorer.clear_data_cache) in store-v4: the folder's layers and
    views go, so the next load reads its files; an only copy (another folder's, its TXY gone) stays."""
    from test_helper_dispatch import send
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    gone = data_folder(tmp_path / "other")
    run_load(gone, tmp_path, options)
    with opened(options, gone) as store:
        store.mark_txy_seen(str(gone), {"txy": {}}, time.time() + 60)  # (Its TXY gone: the only copy.)
    for folder in (source, gone):
        events = send(monkeypatch, capsys, {"operation": "invalidate", "path": str(folder), "cache": options})
        assert any(event["kind"] == "removed" for event in events)
    with opened(options, source) as store:
        assert store.txy_layers(str(source)).value == {} and store.read_view(str(source), "", "").missing
    with opened(options, gone) as store:
        assert store.txy_layers(str(gone)).value  # (Only a question that names it may take it.)
    loaded = first(run_load(source, tmp_path, options), "loaded")
    assert loaded["load_counts"]["read"] == 2 and not loaded["cached"]


def test_a_purge_by_age_takes_old_layers_but_not_only_copies(tmp_path: Path) -> None:
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    run_load(source, tmp_path, options)
    kept = data_folder(tmp_path / "other")
    run_load(kept, tmp_path, options)
    with opened(options, kept) as store:
        store.mark_txy_seen(str(kept), {"txy": {}}, time.time() + 60)
    events: list[Any] = []
    cache_admin(options, "purge", events.append, what="datasets", cutoff=time.time() + 3600)
    assert any(event["kind"] == "removed" and event["kinds"] == ["txy"] for event in events)
    with opened(options, source) as store:
        assert store.txy_layers(str(source)).value == {} and store.read_view(str(source), "", "").missing
    with opened(options, kept) as store:
        assert store.txy_layers(str(kept)).value


def test_a_conversion_from_the_raw_layer_comes_before_any_file_and_keeps_heartbeats_going(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S3-2: a slow decode (a large shot on a slow PC) isn't inside a file's 15 s window: no ``file_started``
    for the shot, and heartbeats go on meanwhile."""
    import threading
    from helab.convert import raw_layer
    from helab.convert.profile import MATLAB_2019
    from helab.io_ops.convert import convert_folder
    from helab.io_ops.infra import Heartbeat
    from test_convert_helab import raw_bytes, write_raw
    source = tmp_path / "data" / "run"
    source.mkdir(parents=True)
    write_raw(source, 1, raw_bytes(10_000, 20_000))
    options = v4_options(tmp_path)
    request: dict[str, Any] = {"path": str(source), "profile": MATLAB_2019.to_dict(), "temps": str(tmp_path / "temps"),
                               "seen": None, "destination": "cache", "workers": 1, "cache": options}
    convert_folder(str(source), request, lambda event: None)  # type: ignore[arg-type]
    monkeypatch.setattr(Heartbeat, "INTERVAL", 0.02)
    events: list[dict[str, Any]] = []
    beating = threading.Event()
    decode = raw_layer.decode

    def slow(layer: Any) -> Any:
        beating.wait(10)  # (Until heartbeats came: a long conversion.)
        return decode(layer)
    monkeypatch.setattr(raw_layer, "decode", slow)

    def collect(event: dict[str, Any]) -> None:
        events.append(event)
        if sum(item["kind"] == "heartbeat" for item in events) >= 3:
            beating.set()
    from helab.io_ops.loading import load
    output = tmp_path / "out"
    output.mkdir()
    txy = {"source": "helab-only", "profile_hash": MATLAB_2019.content_hash(), "profile_tag": "m19v1",
           "cache_base": str(tmp_path / "caches"), "temps": str(tmp_path / "temps")}
    load(str(source), str(output), collect, options, txy=txy)  # type: ignore[arg-type]
    assert beating.is_set() and first(events, "loaded")["files"] == 1
    assert not any(event["kind"] == "file_started" and "d_txy_helab_" in os.path.basename(event["filename"])
                   for event in events)
