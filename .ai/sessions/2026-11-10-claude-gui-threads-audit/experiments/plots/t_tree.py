import os, time
base = "/private/tmp/claude-501/gt-audit-plots"
os.environ["HELAB_APP_DIR_OVERRIDE"] = base + "/app"; os.environ["HELAB_DIR_CACHES_OVERRIDE"] = base + "/caches"; os.environ["HELAB_DIR_TEMPS_OVERRIDE"] = base + "/temps"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6 import QtWebEngineWidgets
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from helab.analysis.parameter_tree import build_tree, settings_widget
from helab.analysis.backends import backend_specs
from helab.scripts.standard_v2.histograms_2d import PlaneHistograms
from helab.views.plots.instance import identify_parameters
s = PlaneHistograms(); specs = [*s.parameters("Plot"), *backend_specs(s.backends("Plot"))]
for i in range(3):
    t = time.perf_counter(); root = build_tree(specs); w = identify_parameters(settings_widget(root, specs)); w.show(); app.processEvents()
    print(f"settings page ({len(specs)} params): {time.perf_counter()-t:.3f}s", flush=True)
