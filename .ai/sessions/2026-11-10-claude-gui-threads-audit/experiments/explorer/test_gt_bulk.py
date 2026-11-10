from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from helab.models.StatusReport import StatusReport
from helab.utils.io_service import IORequest, IOService
from helab.views.FolderExplorer import FolderExplorer


def frozen_service(monkeypatch: pytest.MonkeyPatch) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    return service


@pytest.mark.parametrize("n", [2000, 8000])
def test_bulk_signals(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, n: int) -> None:
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
    t0 = time.perf_counter()
    model._result_counts_changed(None)
    t1 = time.perf_counter()
    for entry in entries:
        node = model.nodes[entry["path"]]
        node.report = StatusReport(node.path, "nothing", 0, [], [], [])
        node.cached_report = True
    t2 = time.perf_counter()
    model._cache_removed(None, ["summaries"])
    t3 = time.perf_counter()
    print(f"\nn={n}: _result_counts_changed(None) {1000*(t1-t0):.0f} ms; _cache_removed(None, summaries) {1000*(t3-t2):.0f} ms")
    explorer.close_cleanup()
    service.shutdown()
