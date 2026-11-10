import time, threading, sys
import numpy as np
from scipy.ndimage import gaussian_filter, median_filter
def gil_gap(label, fn):
    stop = False; gaps = [0.0]
    def tick():
        last = time.perf_counter()
        while not stop:
            time.sleep(0.001); now = time.perf_counter(); gaps[0] = max(gaps[0], now - last); last = now
    th = threading.Thread(target=tick); th.start(); time.sleep(0.05)
    s = time.perf_counter(); fn(); d = time.perf_counter() - s
    stop = True; th.join(); print(f"{label}: {d:.2f}s, longest stall of another thread {gaps[0]*1000:.0f} ms", flush=True)
n = 10_000_000
ev = np.random.rand(n, 3)
gil_gap("np.histogram2d 10M events 1000x1000", lambda: np.histogram2d(ev[:, 1], ev[:, 2], bins=(1000, 1000)))
gil_gap("np.histogram2d 10M events 8000x8000", lambda: np.histogram2d(ev[:, 1], ev[:, 2], bins=(8000, 8000)))
gil_gap("np.sort 10M", lambda: np.sort(ev[:, 0]))
gil_gap("np.partition/quantile 10M", lambda: np.quantile(ev[:, 0], [0.005, 0.995]))
img = np.random.rand(4000, 4000)
gil_gap("gaussian_filter 4000^2 sigma 5", lambda: gaussian_filter(img, 5))
gil_gap("median_filter 2000^2 size 5", lambda: median_filter(img[:2000, :2000], 5))
gil_gap("tolist 10M", lambda: ev[:, 0].tolist())
