import os, time
base = "/private/tmp/claude-501/gt-audit-plots"
os.environ["HELAB_APP_DIR_OVERRIDE"] = base + "/app"; os.environ["HELAB_DIR_CACHES_OVERRIDE"] = base + "/caches"; os.environ["HELAB_DIR_TEMPS_OVERRIDE"] = base + "/temps"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from helab.analysis.budget import RamBudget
from helab.utils.ram_buffers import buffers
class Cache(QObject):
    datasetChanged = pyqtSignal(str)
    def __init__(s, budget, plots_ref): super().__init__(); s.max_data_bytes = budget; s.ram_users = set(); s.plots_ref = plots_ref
    def memory_usage(s): return 0, 0, 0
    def plot_bytes(s):
        m = {}
        for u in s.ram_users: m.update(u.ram_buffers())
        return sum(m.values())
    def evict_to(s, t):
        s.plot_bytes(); return []
    def shown_buffers(s): return {}
    def held_sizes(s): return []
class Dock:
    def isVisible(s): return False
class Plot:
    def __init__(s, arrays): s.views = [buffers(arrays)] * 4; s.dock_widget = Dock(); s.is_released = False
    def ram_buffers(s):
        m = {}
        for v in s.views: m.update(v)
        return m
    def releasable(s): return True
    def release(s, frees=None): return False
    def picture_cost(s): return 10**15  # picture "too big": every plot stays, the worst case for the loop
    def recently_reloaded(s): return False
    def ram_label(s): return "p"
for P, S in ((10, 1000), (20, 5000), (40, 5000)):
    arrays = [np.empty((10, 3)) for _ in range(S)]
    plots = [Plot(arrays) for _ in range(P)]
    cache = Cache(1, plots); b = RamBudget(cache)
    for p in plots: b.plots.append(p); cache.ram_users.add(p)
    s = time.perf_counter(); b.check(); print(f"P={P} plots, S={S} shots: check {time.perf_counter()-s:.2f}s", flush=True)
calls = [0]
orig = RamBudget.frees
def frees(self, plot, staying):
    calls[0] += 1; return orig(self, plot, staying)
RamBudget.frees = frees
P, S = 40, 5000
arrays = [np.empty((10, 3)) for _ in range(S)]
# distinct arrays per plot (plots of different folders): no shared buffers
plots = [Plot([np.empty((10, 3)) for _ in range(S)]) for _ in range(P)]
cache = Cache(1, plots); b = RamBudget(cache)
for p in plots: b.plots.append(p); cache.ram_users.add(p)
s = time.perf_counter(); b.check(); print(f"distinct: P={P} S={S}: check {time.perf_counter()-s:.2f}s, frees calls {calls[0]}", flush=True)
