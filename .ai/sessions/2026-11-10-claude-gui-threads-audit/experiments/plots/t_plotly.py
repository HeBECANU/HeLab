import time, threading
import numpy as np
import plotly.graph_objs as go
from plotly.io.json import to_json_plotly
def t(label, fn):
    s = time.perf_counter(); r = fn(); print(f"{label}: {time.perf_counter()-s:.3f}s", flush=True); return r
def gil_gap(fn):
    stop = False; gaps = [0.0]
    def tick():
        last = time.perf_counter()
        while not stop:
            time.sleep(0.001); now = time.perf_counter(); gaps[0] = max(gaps[0], now - last); last = now
    th = threading.Thread(target=tick); th.start()
    s = time.perf_counter(); r = fn(); d = time.perf_counter() - s
    stop = True; th.join(); return d, gaps[0], r
for n in (1000, 4000):
    z = np.random.rand(n, n)
    fig = t(f"Figure Heatmap {n}^2 + customdata", lambda: go.Figure(go.Heatmap(z=z.T, customdata=z.T, x=np.arange(n), y=np.arange(n))))
    d, g, s = gil_gap(lambda: to_json_plotly(fig))
    print(f"  to_json {n}^2: {d:.3f}s, json {len(s)/1e6:.1f} MB, longest stall of a ticking thread {g*1000:.0f} ms")
for k in (200_000, 1_000_000, 5_000_000):
    x, y, c = np.random.rand(k), np.random.rand(k), np.random.rand(k)
    fig = t(f"Figure Scattergl {k}", lambda: go.Figure(go.Scattergl(x=x, y=y, mode="markers", marker=dict(color=c))))
    d, g, s = gil_gap(lambda: to_json_plotly(fig))
    print(f"  to_json {k}: {d:.3f}s, json {len(s)/1e6:.1f} MB, longest stall {g*1000:.0f} ms")
