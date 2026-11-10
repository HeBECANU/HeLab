import os, time
base = "/private/tmp/claude-501/gt-audit-plots"
os.environ["HELAB_APP_DIR_OVERRIDE"] = base + "/app"; os.environ["HELAB_DIR_CACHES_OVERRIDE"] = base + "/caches"; os.environ["HELAB_DIR_TEMPS_OVERRIDE"] = base + "/temps"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import numpy as np
from PyQt6 import QtWebEngineWidgets
from PyQt6.QtWidgets import QApplication
app = QApplication([])
import pyqtgraph as pg
from helab.views.plots.pictures import snapshot
from PyQt6.QtCore import QSize
for w, h in ((1200, 800), (2400, 1600), (3600, 2400)):
    wid = pg.GraphicsLayoutWidget(); wid.resize(w, h); p = wid.addPlot(); im = pg.ImageItem(); p.addItem(im)
    im.setImage(np.random.rand(1000, 1000))
    t = time.perf_counter(); pic = snapshot(wid, QSize(w, h)); print(f"snapshot {w}x{h}: {time.perf_counter()-t:.3f}s, png {len(pic.png)/1e6:.1f} MB", flush=True)
