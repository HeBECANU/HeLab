"""Re-review (step 3): undo one fix in memory, to see that its tests fail without it. A pytest plugin:
``GT_MUTANT=<name> PYTHONPATH=.ai/sessions/2026-11-10-claude-gui-threads-audit pytest -p mutants <tests>``.
Nothing in the checkout changes; each mutant is an autouse fixture's monkeypatch, applied after conftest.

- ``gt1``: ``gui_delivery.outside`` runs its function at once, as before the fix (a box inside the delivery).
- ``gt5``: ``SnapshotFileSystemModel._rederive`` re-derives per touched folder as before (``_update_ancestors``
  then ``changed`` for each), and ``one_activity`` holds nothing.
- ``gt6``: a probe's reads are never fresh (``FolderReads.fresh`` is False), so the GUI's import reads the folder.
- ``fcmark`` (a probe, not a mutant): ``FolderCache._on_event`` runs inside ``delivering("io")``, so guard 2 sees
  boxes opened from helper events that tests emit directly. Run with the whole suite; failures name such boxes.
- ``gt10``: ``DockTabCloser.dock_at`` ignores the docks its caller found, walking the area for each tab.
"""
from __future__ import annotations

import contextlib
import os
from typing import Any, Iterator

import pytest

MUTANT = os.environ.get("GT_MUTANT", "")


@pytest.fixture(autouse=True)
def _gt_mutant(monkeypatch: pytest.MonkeyPatch) -> None:
    if MUTANT == "gt1":
        from helab.utils import gui_delivery
        monkeypatch.setattr(gui_delivery, "outside", lambda fn: fn())
    elif MUTANT == "gt5":
        from helab.models.SnapshotFileSystemModel import SnapshotFileSystemModel

        def rederive(self: Any, touched: list[Any]) -> None:
            for node in touched:
                self._update_ancestors(node)
                self.changed(node)

        @contextlib.contextmanager
        def one_activity(self: Any) -> Iterator[None]:
            yield
        monkeypatch.setattr(SnapshotFileSystemModel, "_rederive", rederive)
        monkeypatch.setattr(SnapshotFileSystemModel, "one_activity", one_activity)
    elif MUTANT == "gt6":
        from helab.scripts.scripts_manager import FolderReads
        monkeypatch.setattr(FolderReads, "fresh", lambda self, directory: False)
    elif MUTANT == "fcmark":
        # Not a mutant: guard 2 made to see deliveries tests make by emitting ``resultReady`` themselves (they
        # bypass ``IOService._tick``), by marking FolderCache's dispatcher, which every helper event goes through.
        from helab.utils import gui_delivery
        from helab.utils.folder_cache import FolderCache
        dispatch = FolderCache._on_event

        def marked(self: Any, producer: Any, event: Any) -> None:
            with gui_delivery.delivering("io"):
                dispatch(self, producer, event)
        monkeypatch.setattr(FolderCache, "_on_event", marked)
    elif MUTANT == "gt10":
        from helab.views.plots.dock import DockTabCloser
        original = DockTabCloser.dock_at
        monkeypatch.setattr(DockTabCloser, "dock_at", lambda self, bar, index, docks=None: original(self, bar, index))
