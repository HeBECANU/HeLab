from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from helab.utils import txy_sources
from helab.utils.folder_cache import Dataset
from helab.utils.io_service import IOService
from helab.views.FolderExplorer import FolderExplorer
from helab.views.FolderDetailsPanel import FolderDetailsPanel
from helab.views.explorer_live import AutoConvert, LiveSession


def frozen_service(monkeypatch: pytest.MonkeyPatch) -> IOService:
    service = IOService()
    service.timer.stop()
    monkeypatch.setattr(service, "_dispatch", lambda: None)
    return service


@pytest.mark.parametrize("n", [10_000, 100_000])
def test_live_tick_cost(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, n: int) -> None:
    service = frozen_service(monkeypatch)
    monkeypatch.setattr("helab.models.SnapshotFileSystemModel.get_io_service", lambda: service)
    root = str(tmp_path)
    explorer = FolderExplorer(root, root, root, [0, 4, 5])
    qtbot.addWidget(explorer)
    explorer.show()
    qtbot.wait(50)
    arr = np.zeros((3, 3))
    data = {i: arr for i in range(n)}
    origins = {str(i): txy_sources.HELAB_ORIGIN + "0" * 16 for i in range(n)}
    meta = {"files": n, "rows": 3 * n, "bytes": 72 * n, "fingerprint": [[i, 100, 1_700_000_000_000_000_000] for i in range(n)],
            txy_sources.TXY_FIELD: {"source": "helab-only", "origins": origins, "profiles": {}}}
    dataset = Dataset(root, "sig", data, meta, 0)
    explorer.displayed_dataset = dataset
    explorer.folder_opened_path = root
    session = LiveSession(root, time.time(), set(data), dataset)
    session.convert = AutoConvert(time.time())
    explorer.live = session
    explorer.live_control._live_sessions[root] = session
    k = 20
    t0 = time.perf_counter()
    for _ in range(k):
        explorer._update_activity()
    t1 = time.perf_counter()
    panel = FolderDetailsPanel()
    qtbot.addWidget(panel)
    t2 = time.perf_counter()
    for _ in range(k):
        panel.show_explorer(explorer, service)
    t3 = time.perf_counter()
    session.convert = None
    t4 = time.perf_counter()
    for _ in range(k):
        explorer._update_activity()
    t5 = time.perf_counter()
    for _ in range(k):
        panel.show_explorer(explorer, service)
    t6 = time.perf_counter()
    print(f"\nn={n}: Live+convert: summary tick {1000*(t1-t0)/k:.2f} ms, Folder details {1000*(t3-t2)/k:.2f} ms; "
          f"Live only: summary {1000*(t5-t4)/k:.2f} ms, details {1000*(t6-t5)/k:.2f} ms")
    explorer.live = None
    explorer.live_control._live_sessions.clear()
    explorer.close_cleanup()
    service.shutdown()
