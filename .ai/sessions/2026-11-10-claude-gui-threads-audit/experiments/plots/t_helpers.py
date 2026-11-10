import os, sys, time
base = "/private/tmp/claude-501/gt-audit-plots"
os.environ["HELAB_APP_DIR_OVERRIDE"] = base + "/app"; os.environ["HELAB_DIR_CACHES_OVERRIDE"] = base + "/caches"; os.environ["HELAB_DIR_TEMPS_OVERRIDE"] = base + "/temps"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6 import QtWebEngineWidgets
from PyQt6.QtWidgets import QApplication
app = QApplication([])
import helab.views.HelabMainWindow, matplotlib.backends.backend_qtagg, scipy.ndimage, scipy.optimize, dash, plotly.graph_objs
from helab.scripts.scripts_manager import ScriptsManager
os.makedirs(base + "/scripts", exist_ok=True)
m = ScriptsManager()
print("modules:", len(sys.modules))
t = time.perf_counter()
for _ in range(10): m.helper_modules(base + "/scripts")
print(f"helper_modules: {(time.perf_counter()-t)/10*1000:.1f} ms per call")
t = time.perf_counter()
for _ in range(10): m.stamp(m.watched_files(base + "/scripts"))
print(f"stamp(watched_files): {(time.perf_counter()-t)/10*1000:.1f} ms per call")
