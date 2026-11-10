"""GT-5: saved status removed from the disk cache (Settings › Cache's Clear, a ``.helab-root`` deleted) is
re-derived once per folder, not once per subfolder, and the tab's summary is rebuilt once, not once a row: per
child it was O(n²) in one slot (17.5 s at 8,000 subfolders)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.models.SnapshotFileSystemModel import FolderNode, SnapshotFileSystemModel
from helab.utils.io_service import IOService
from helab.views.FolderExplorer import FolderExplorer
from test_large_folder import frozen, make_explorer

CHILDREN = 300


def listed(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, root: str) -> tuple[FolderExplorer, IOService, list[str]]:
    """A tab whose top folder lists ``CHILDREN`` subfolders, each showing a saved "something"."""
    service, cache = frozen(monkeypatch)
    names = [f"run_{index:04d}" for index in range(CHILDREN)]
    explorer, _, _ = make_explorer(qtbot, service, cache, root, dict.fromkeys(names))
    paths = [os.path.join(root, name) for name in names]
    model = explorer.model
    for path in paths:
        model._restore_summary(model.nodes[path], {"status": "something", "count": 1, "raw": [1], "txy": [1],
                                                   "scanned_at": 1_700_000_000.0})
    model._derive(model.nodes[root])
    return explorer, service, paths


def test_removed_saved_status_derives_each_folder_once_and_says_so_once(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    root = str(tmp_path)
    explorer, service, paths = listed(qtbot, monkeypatch, root)
    model = explorer.model
    derived: dict[str, int] = {}
    derive = SnapshotFileSystemModel._derive

    def counting(self: SnapshotFileSystemModel, node: FolderNode) -> bool:
        derived[node.path] = derived.get(node.path, 0) + 1
        return derive(self, node)
    monkeypatch.setattr(SnapshotFileSystemModel, "_derive", counting)
    said: list[Any] = []
    model.activityChanged.connect(lambda: said.append(None))
    try:
        model._cache_removed(None, ["summaries"])  # (Settings › Cache's Clear: every row.)
        assert derived[root] == 1  # (Once per child before: 300.)
        assert all(derived[path] == 1 for path in paths)
        assert len(said) == 1
        assert all(not model.nodes[path].cached_report and model.nodes[path].report is None for path in paths)
        assert not derive(model, model.nodes[root])  # (Derived from its final subfolders: nothing left to change.)
    finally:
        explorer.close_cleanup()
        service.shutdown()


def test_some_rows_removed_derive_their_parent_and_ancestors_as_one_row_did(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    root = str(tmp_path)
    explorer, service, paths = listed(qtbot, monkeypatch, root)
    model = explorer.model
    try:
        model._cache_removed(paths[:-1], ["summaries"])  # (One subfolder still shows its saved data.)
        assert model.nodes[paths[-1]].cached_report and not model._derive(model.nodes[root])
        model._cache_removed(paths[-1:], ["summaries"])
        assert not model.nodes[paths[-1]].cached_report and not model._derive(model.nodes[root])
        with model.one_activity():
            with model.one_activity():
                model.changed(model.nodes[root])
            assert model._activity_held  # (Said at the outer end only.)
        assert not model._activity_held
    finally:
        explorer.close_cleanup()
        service.shutdown()
