"""GT audit: how ``DockTabCloser.fit`` scales with the number of tabbed plot docks.

Run as ``QT_QPA_PLATFORM=offscreen python .ai/sessions/2026-11-10-claude-gui-threads-audit/dock_fit_scaling.py``
(it sets HeLab's folder overrides to a scratch folder before importing ``helab``). N docks, each holding a widget
tree of ``CHILDREN`` widgets (a plot's canvas, settings and parameter rows), are tabbed together in one
``QMainWindow``; one ``fit`` is timed for each N.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

scratch = tempfile.mkdtemp(prefix="gt-dock-")
for name in ("HELAB_DIR_TEMPS_OVERRIDE", "HELAB_DIR_CACHES_OVERRIDE", "HELAB_APP_DIR_OVERRIDE"):
    os.environ[name] = os.path.join(scratch, name.lower())
os.environ["HELAB_TEST_SETTINGS_FILE"] = os.path.join(scratch, "settings.ini")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget  # noqa: E402

from helab.views.plots.dock import DockTabCloser  # noqa: E402

CHILDREN = 300


def main() -> int:
    app = QApplication(sys.argv)
    for count in (5, 10, 20, 40, 80):
        area = QMainWindow()
        closer = DockTabCloser(area)
        docks = []
        for i in range(count):
            dock = QDockWidget(f"Plot {i}", area)
            body = QWidget()
            layout = QVBoxLayout(body)
            for j in range(CHILDREN):
                layout.addWidget(QLabel(f"row {j}"))
            dock.setWidget(body)
            area.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            if docks:
                area.tabifyDockWidget(docks[0], dock)
            docks.append(dock)
        area.show()
        app.processEvents()
        start = time.perf_counter()
        closer.fit()
        took = time.perf_counter() - start
        print(f"{count:3d} tabbed docks x {CHILDREN} widgets: fit {took * 1000:8.1f} ms")
        area.close()
        area.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
