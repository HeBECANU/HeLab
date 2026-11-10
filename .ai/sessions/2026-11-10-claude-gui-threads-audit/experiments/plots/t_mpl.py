import time
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
for n in (1000, 2000, 4000):
    fig = Figure(layout="constrained"); FigureCanvasAgg(fig); ax = fig.add_subplot()
    e = np.linspace(0, 1, n + 1); z = np.random.rand(n, n)
    s = time.perf_counter(); m = ax.pcolormesh(e, e, z.T, cmap="viridis"); fig.colorbar(m, ax=ax); b = time.perf_counter()
    fig.canvas.draw(); d = time.perf_counter()
    print(f"pcolormesh {n}^2: build {b-s:.2f}s, draw {d-b:.2f}s", flush=True)
for k in (200_000, 1_000_000, 5_000_000):
    fig = Figure(layout="constrained"); FigureCanvasAgg(fig); ax = fig.add_subplot()
    x, y, c = np.random.rand(k), np.random.rand(k), np.random.rand(k)
    s = time.perf_counter(); ax.scatter(x, y, c=c, s=1, marker="s", linewidths=0, rasterized=True); b = time.perf_counter()
    fig.canvas.draw(); d = time.perf_counter()
    print(f"scatter {k}: build {b-s:.2f}s, draw {d-b:.2f}s", flush=True)
