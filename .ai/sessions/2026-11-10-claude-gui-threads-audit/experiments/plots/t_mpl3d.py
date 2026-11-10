import time
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
for k in (100_000, 500_000, 2_000_000):
    fig = Figure(layout="constrained"); FigureCanvasAgg(fig); ax = fig.add_subplot(projection="3d")
    p = np.random.rand(k, 3)
    ax.scatter(p[:, 0], p[:, 1], p[:, 2], s=2.25, linewidths=0, depthshade=False, alpha=0.4)
    s = time.perf_counter(); fig.canvas.draw(); d = time.perf_counter()
    ax.view_init(30, 40); fig.canvas.draw(); e = time.perf_counter()
    print(f"mpl 3D scatter {k}: draw {d-s:.2f}s, redraw after rotate {e-d:.2f}s", flush=True)
