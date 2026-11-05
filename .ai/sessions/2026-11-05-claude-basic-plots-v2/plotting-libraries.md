# Other plotting libraries for HeLab (Tony's question with Q~8)

Basic plots v2 floor, 2026-11-05. Tony asked which other plotting libraries could fit. This note compares the candidates
and reports a throwaway trial of the top two on synthetic data. Nothing joins the app or the requirements without
Tony's OK. The trial packages went into this floor's venv only and were uninstalled afterwards.

## What HeLab needs from a plotting library

- **It paints on the lab PCs.** The Lab Side PC can't paint QtWebEngine (Sandy Bridge, no D3D11; memory
  `results/lab-pc-qtwebengine-black-render.md`). So a plot drawn natively in Qt, or as an image Qt shows, works
  everywhere. A browser canvas works only through "Open in browser".
- **Live redraws are fast** and keep zoom and pan (`update` in place).
- **It handles millions of events**: a folder holds thousands of shots of thousands of events each.
- **It builds frozen with PyInstaller and has Python 3.13 wheels** on macOS, Windows and Linux.

Today HeLab has PyQtGraph (native Qt, the default for 2D), Plotly through the Dash server (3D, browser), and Matplotlib
(`Figure`, never `pyplot`, for publication). Each Basic plot can be drawn with all three.

## Candidates

| Library | What it is | Fits? | Why |
|---|---|---|---|
| **Datashader** | Aggregates points into an image on the CPU (Numba), for display anywhere | **Best fit, if one is needed** | Turns millions of events into an image fast (below), which PyQtGraph's `ImageItem` already shows natively: no web, so it paints on the lab PCs. It costs numba, llvmlite, xarray, param, colorcet, multipledispatch, pyct and toolz (pandas is already there). That is about 100 MB more, plus Numba's first-call compile and its PyInstaller hooks. |
| **mpl-scatter-density** | A Matplotlib projection that draws a scatter as a density image, re-binned at each draw (fast-histogram) | Small, narrow | Small (fast-histogram only), and works in `Figure`. But Matplotlib is HeLab's slow, publication path, and v2's 2D histograms already draw a density image in all three libraries. |
| **fastplotlib** | GPU plotting (wgpu: Vulkan, Metal or D3D12), embeds in Qt | Not for the lab PCs | Very fast for millions of points and live images on a modern GPU. But wgpu needs Vulkan or D3D12, which the Sandy Bridge Lab Side PC lacks (no D3D11 even), and its API is young. Not tried: it needs a GPU, so it can't run offscreen. |
| **Bokeh** | Browser canvas (static HTML or a server) | No | It's a second web stack beside Plotly and Dash, with the same QtWebEngine problem on the lab PCs and no gain over Plotly's "Open in browser". |
| **VisPy, PyVista** | OpenGL and VTK scenes | Avoided (AGENTS.md) | AGENTS.md avoids them for their known data-point issues with large files. Both need working OpenGL, which the lab PCs don't reliably have. |
| (**PyQtGraph**, kept) | Native Qt, with an optional OpenGL 3D view | Already the default | It paints everywhere and redraws fast for Live. Its `ImageItem` shows any binned image, whichever library binned it. |

## Trial (`library_trial.py`, in this folder)

The events are synthetic DLD-like data (a Gaussian cloud in X and Y), binned into an XY image of 400 × 400 bins over
±20 mm. Times are the mean of 3 runs after a warm-up (Numba compiles on the first call), on Tony's Mac (M-series,
Python 3.13). The log is in `.ai/temp/library_trial.txt` and isn't committed.

| Binning | 1,000,000 events | 5,000,000 events | Counts |
|---|---:|---:|---|
| `numpy.histogram2d` (v2's XY histogram today) | 83.9 ms | 420.5 ms | reference |
| `numpy.bincount` on computed bin indices (NumPy only) | 4.8 ms | 25.5 ms | identical to `histogram2d` (asserted) |
| Datashader `Canvas.points` + `count()` (Numba) | 1.3 ms | 5.4 ms | the same totals (4,999,998 of 5,000,000 in range) |
| mpl-scatter-density, one figure drawn (Agg) | 16.8 ms | 26.5 ms | (drawn, not compared) |

## Proposal

- **No new library now.** At today's folder sizes the v2 2D histograms bin quickly enough on the worker thread, and
  every library they draw with paints on the lab PCs.
- **First, a free speed-up (A~):** bin `helab/analysis/histogram2d.py` with `np.bincount` on computed indices instead
  of `np.histogram2d`. It's about 17× faster here, with the same counts, NumPy only. The edge rule must match
  `histogram2d`'s (the last bin includes its right edge), and a test against `np.histogram2d` already pins the counts.
  The DLD port's Density images could do the same, on its own floor.
- **Datashader later (Q~), only if** Live on very large folders (over about 10 M events per image) shows the 2D plots
  lagging even after that. It would bin, and PyQtGraph would still draw, so nothing changes on the lab PCs. It
  needs Tony's OK for the dependencies and the frozen-build size.
