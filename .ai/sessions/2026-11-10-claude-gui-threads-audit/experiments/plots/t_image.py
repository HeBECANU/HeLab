import os, sys, time
base = "/private/tmp/claude-501/gt-audit-plots"
os.environ["HELAB_APP_DIR_OVERRIDE"] = base + "/app"
os.environ["HELAB_DIR_CACHES_OVERRIDE"] = base + "/caches"
os.environ["HELAB_DIR_TEMPS_OVERRIDE"] = base + "/temps"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import numpy as np
from PyQt6 import QtWebEngineWidgets
from PyQt6.QtWidgets import QApplication
app = QApplication([])
import pyqtgraph as pg
from helab.analysis.histogram2d import compress
from helab.scripts.standard_v2 import histograms_2d as h2
def t(label, fn):
    s = time.perf_counter(); r = fn(); print(f"{label}: {time.perf_counter()-s:.3f}s", flush=True); return r
for n in (1000, 4000, 8000):
    img = np.random.poisson(3, (n, n)).astype(np.float64)
    pos = t(f"compress log {n}^2", lambda: compress(img / img.max(), "log", 0.5, 3))
    w = pg.GraphicsLayoutWidget(); w.resize(1200, 800)
    p = w.addPlot(); item = pg.ImageItem(axisOrder="col-major")
    item.setLookupTable(h2.viridis().getLookupTable(nPts=1024, alpha=False)); p.addItem(item)
    t(f"setImage {n}^2", lambda: item.setImage(pos, levels=(0.0, 1.0)))
    t(f"grab (paint) {n}^2", lambda: w.grab())
    del img, pos, w
for k in (200_000, 1_000_000, 5_000_000):
    table = [pg.mkBrush(*c) for c in h2.viridis().getLookupTable(nPts=1024, alpha=False)]
    steps = np.random.randint(0, 1024, k)
    brushes = t(f"brush list {k}", lambda: [table[s] for s in steps])
    w = pg.GraphicsLayoutWidget(); w.resize(1200, 800); p = w.addPlot()
    sc = pg.ScatterPlotItem(pxMode=True, size=2, symbol="s", pen=None); p.addItem(sc)
    x, y = np.random.rand(k), np.random.rand(k)
    t(f"scatter setData {k}", lambda: sc.setData(x=x, y=y, brush=brushes))
    t(f"grab (paint) dots {k}", lambda: w.grab())
    del w, sc, brushes
