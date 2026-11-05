"""Throwaway trial (Tony, Q~8 follow-up): bin synthetic DLD-like events into an XY image with NumPy (what
Basic plots v2 does), Datashader and mpl-scatter-density, and time each. Not part of HeLab; imports no helab.
Run with the floor's venv after `uv pip install --python venv/bin/python datashader mpl-scatter-density`."""
from __future__ import annotations

import time

import numpy as np


def events(count: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = rng.normal(2.1375, 0.002, count)
    x, y = rng.normal(0.0, 0.004, count), rng.normal(0.001, 0.002, count)
    return np.column_stack((t, x, y))


def timed(label: str, run, repeat: int = 3) -> float:
    run()  # (Warm up: Numba compiles on the first call.)
    start = time.perf_counter()
    for _ in range(repeat):
        run()
    seconds = (time.perf_counter() - start) / repeat
    print(f"{label:46s} {seconds * 1e3:8.1f} ms")
    return seconds


def main() -> None:
    import pandas as pd
    import datashader as ds
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import mpl_scatter_density  # noqa: F401  (registers the projection)

    bins, span = 400, ((-0.02, 0.02), (-0.02, 0.02))
    for count in (1_000_000, 5_000_000):
        data = events(count)
        print(f"-- {count:,} events, {bins} x {bins} bins")
        reference, _, _ = np.histogram2d(data[:, 1], data[:, 2], bins=bins, range=span)
        timed("numpy.histogram2d (v2's XY histogram)", lambda: np.histogram2d(data[:, 1], data[:, 2], bins=bins,
                                                                            range=span))

        def by_bincount() -> np.ndarray:
            ix = ((data[:, 1] - span[0][0]) / (span[0][1] - span[0][0]) * bins).astype(np.intp)
            iy = ((data[:, 2] - span[1][0]) / (span[1][1] - span[1][0]) * bins).astype(np.intp)
            keep = (ix >= 0) & (ix < bins) & (iy >= 0) & (iy < bins)
            return np.bincount(ix[keep] * bins + iy[keep], minlength=bins * bins).reshape(bins, bins)
        timed("numpy.bincount (a faster NumPy binning)", by_bincount)
        assert np.array_equal(by_bincount(), reference.astype(np.int64))
        frame = pd.DataFrame({"x": data[:, 1], "y": data[:, 2]})

        def by_datashader() -> np.ndarray:
            canvas = ds.Canvas(plot_width=bins, plot_height=bins, x_range=span[0], y_range=span[1])
            return np.asarray(canvas.points(frame, "x", "y", ds.count()).values)
        timed("datashader Canvas.points (Numba)", by_datashader)
        shaded = by_datashader().T  # (y, x) -> (x, y)
        print(f"{'  datashader vs numpy: events per image':46s} {int(shaded.sum()):,} vs {int(reference.sum()):,}")

        def by_scatter_density() -> None:
            figure = Figure(figsize=(4, 4), dpi=100)
            FigureCanvasAgg(figure)
            axes = figure.add_subplot(projection="scatter_density")
            axes.scatter_density(data[:, 1], data[:, 2])
            axes.set_xlim(*span[0])
            axes.set_ylim(*span[1])
            figure.canvas.draw()
        timed("mpl-scatter-density, a figure drawn (Agg)", by_scatter_density, repeat=1)


if __name__ == "__main__":
    main()
