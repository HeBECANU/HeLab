from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from helab.utils.io_service import IORequest, IOService
from helab.views.FolderExplorer import FolderExplorer


def frozen_service(monkeypatch: pytest.MonkeyPatch) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    return service


@pytest.mark.parametrize("n", [2000, 20000])
def test_child_status_cost(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, n: int) -> None:
    service = frozen_service(monkeypatch)
    monkeypatch.setattr("helab.models.SnapshotFileSystemModel.get_io_service", lambda: service)
    root = str(tmp_path)
    explorer = FolderExplorer(root, root, root, [0, 4, 5])
    qtbot.addWidget(explorer)
    explorer.show()
    qtbot.wait(50)
    model = explorer.model
    entries = [{"path": os.path.join(root, f"run_{i:06d}"), "name": f"run_{i:06d}"} for i in range(n)]
    listing = IORequest(model.owner, model.generation, root, "list", {}, 15.0)
    service.resultReady.emit(listing, {"kind": "queued"})
    service.resultReady.emit(listing, {"kind": "started"})
    for start in range(0, n, 128):
        service.resultReady.emit(listing, {"kind": "entries", "entries": entries[start:start + 128]})
    service.resultReady.emit(listing, {"kind": "done"})
    k = 200
    t0 = time.perf_counter()
    for i in range(k):
        path = entries[i]["path"]
        request = IORequest(model.owner, model.generation, path, "scan", {}, 15.0)
        service.resultReady.emit(request, {"kind": "queued"})
        service.resultReady.emit(request, {"kind": "status", "status": "nothing", "count": 0, "raw": [], "txy": [],
                                           "metadata_only": True, "empty": True, "has_dirs": False})
        service.resultReady.emit(request, {"kind": "done"})
    t1 = time.perf_counter()
    per = (t1 - t0) / k
    print(f"\nn={n}: per child status {1000*per:.2f} ms; all {n} children (Check folder status) ≈ {per*n:.1f} s of GUI time")
    explorer.close_cleanup()
    service.shutdown()
