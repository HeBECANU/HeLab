from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.utils.io_service import IORequest, IOService
from helab.views.FolderExplorer import FolderExplorer


def frozen_service(monkeypatch: pytest.MonkeyPatch) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    return service


@pytest.mark.parametrize("n", [20000, 50000])
def test_details_entries_cost(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, n: int) -> None:
    service = frozen_service(monkeypatch)
    monkeypatch.setattr("helab.models.SnapshotFileSystemModel.get_io_service", lambda: service)
    root = str(tmp_path)
    explorer = FolderExplorer(root, root, root, [0, 4, 5])
    qtbot.addWidget(explorer)
    explorer.show()
    qtbot.wait(50)
    model = explorer.model
    calls = {"n": 0}
    original = explorer._update_activity

    def counted() -> None:
        calls["n"] += 1
    model.activityChanged.connect(counted)
    entries = [{"path": os.path.join(root, f"run_{i:06d}"), "name": f"run_{i:06d}"} for i in range(n)]
    listing = IORequest(model.owner, model.generation, root, "list", {}, 15.0)
    service.resultReady.emit(listing, {"kind": "queued"})
    service.resultReady.emit(listing, {"kind": "started"})
    t0 = time.perf_counter()
    service.resultReady.emit(listing, {"kind": "entries", "entries": entries})
    t1 = time.perf_counter()
    first = calls["n"]
    details = IORequest(model.owner, model.generation, root, "details", {}, 15.0)
    dated = [{**e, "modified": time.time(), "modified_observed_at": time.time()} for e in entries]
    t2 = time.perf_counter()
    service.resultReady.emit(details, {"kind": "entries", "entries": dated})
    t3 = time.perf_counter()
    t4 = time.perf_counter()
    for _ in range(50):
        original()
    t5 = time.perf_counter()
    print(f"\nn={n}: list entries {1000*(t1-t0):.0f} ms ({first} summary rebuilds); details entries "
          f"{1000*(t3-t2):.0f} ms ({calls['n']-first} summary rebuilds); one _update_activity {1000*(t5-t4)/50:.2f} ms")
    explorer.close_cleanup()
    service.shutdown()
