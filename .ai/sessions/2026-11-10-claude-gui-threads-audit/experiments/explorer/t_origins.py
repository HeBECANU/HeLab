import sys, time, timeit
sys.path.insert(0, ".")  # (Run from the checkout root.)
from helab.utils import txy_sources as ts
import numpy as np
for n in (1000, 10_000, 100_000):
    origins = {str(i): ts.HELAB_ORIGIN + "abcdef0123456789" for i in range(n)}
    meta = {ts.TXY_FIELD: {"source": "x", "origins": origins}}
    arr = np.zeros((5, 3))
    data = {i: arr for i in range(n)}
    t = timeit.timeit(lambda: ts.empty_helab_shots(meta, data), number=5) / 5
    print(f"empty_helab_shots n={n}: {t*1000:.1f} ms")
