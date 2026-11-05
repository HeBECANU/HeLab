"""2D histograms of a selection's events, the third axis summed (flattened): XY, XT and YT (Basic plots v2).

Each shown axis covers the exact shortest range holding the auto-crop share of its events
(``stats.shortest_range``, as the 1D histograms), or the manual bounds set for it. The flattened axis isn't
cut by auto-crop, so every event of the chosen shots counts; manual bounds set for it limit the events summed
(a T window on the XY histogram images one cloud). Bins are automatic per axis (Freedman–Diaconis, at most
``MAX_AUTO_BINS``) or set.

Qt-free (``tests/test_headless_imports.py``'s ``PURE``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import numpy.typing as npt

from helab.analysis.dataset_view import Events
from helab.analysis.stats import AXES, MAX_BINS, freedman_diaconis_bins, shortest_range

# The plane's (horizontal, vertical, summed) axes. Never rotated: XY has X across and Y up; T runs across.
PLANES = {"XY": ("X", "Y", "T"), "XT": ("T", "X", "Y"), "YT": ("T", "Y", "X")}
MAX_AUTO_BINS = 1000  # Automatic bins per axis, for an image (set by hand: up to ``stats.MAX_BINS``).
Bounds = Optional[tuple[float, float]]


@dataclass(frozen=True)
class Histogram2D:
    """Counts of the events in a plane.

    Attributes:
        plane: "XY", "XT" or "YT".
        counts: Events per bin, shape (horizontal bins, vertical bins).
        h_edges: The horizontal axis's bin edges.
        v_edges: The vertical axis's bin edges.
        automatic: Whether each axis's bin count was automatic (horizontal, vertical).
        total: The events of the chosen shots.
        summed: Those inside the flattened axis's bounds (all when it has none).
        flattened: The flattened axis's manual bounds, None when every event counts.
    """

    plane: str
    counts: npt.NDArray[np.int64]
    h_edges: npt.NDArray[np.float64]
    v_edges: npt.NDArray[np.float64]
    automatic: tuple[bool, bool]
    total: int
    summed: int
    flattened: Bounds = None

    @property
    def axes(self) -> tuple[str, str, str]:
        """The (horizontal, vertical, summed) axes."""
        horizontal, vertical, summed = PLANES[self.plane]
        return horizontal, vertical, summed

    @property
    def inside(self) -> int:
        """The events counted in the image's bins."""
        return int(self.counts.sum())

    @property
    def outside(self) -> int:
        """The summed events outside the shown ranges."""
        return self.summed - self.inside


def _range(values: npt.NDArray[np.float64], keep: float, bounds: Bounds) -> tuple[float, float]:
    lower, upper = bounds if bounds is not None else shortest_range(values, keep)
    if not len(values) and bounds is None:
        return 0.0, 1.0
    if not upper > lower:  # (One value: one bin around it.)
        lower, upper = lower - 0.5, upper + 0.5
    return lower, upper


def _bins(values: npt.NDArray[np.float64], lower: float, upper: float, bins: int) -> int:
    if bins > 0:
        return min(bins, MAX_BINS)
    return min(freedman_diaconis_bins(values, lower, upper), MAX_AUTO_BINS)


def histogram2d(events: Events, plane: str, keep: float, bins: tuple[int, int] = (0, 0),
                bounds: tuple[Bounds, Bounds, Bounds] = (None, None, None),
                check: Callable[[], None] = lambda: None) -> Histogram2D:
    """``events`` (n × 3: T, X, Y) binned in ``plane``, the third axis summed. ``keep``: the auto-crop share of
    each shown axis without ``bounds`` (by axis T, X, Y); a bound on the summed axis limits the events summed.
    ``bins``: per shown axis, 0 for automatic. ``check`` raises to cancel (the runner's)."""
    horizontal, vertical, summed = (AXES.index(name) for name in PLANES[plane])
    total = len(events)
    limit = bounds[summed]
    if limit is not None and total:
        column = events[:, summed]
        events = events[(column >= limit[0]) & (column <= limit[1])]
    check()
    h_values = np.ascontiguousarray(events[:, horizontal], dtype=np.float64)
    v_values = np.ascontiguousarray(events[:, vertical], dtype=np.float64)
    h_range = _range(h_values, keep, bounds[horizontal])
    v_range = _range(v_values, keep, bounds[vertical])
    check()
    h_bins = _bins(h_values, *h_range, bins[0])
    v_bins = _bins(v_values, *v_range, bins[1])
    counts, h_edges, v_edges = np.histogram2d(h_values, v_values, bins=(h_bins, v_bins), range=(h_range, v_range))
    return Histogram2D(plane, counts.astype(np.int64), h_edges, v_edges, (bins[0] <= 0, bins[1] <= 0), total,
                       len(events), limit)


def log_image(counts: npt.NDArray[np.int64]) -> npt.NDArray[np.float64]:
    """``log10`` of the counts, empty bins NaN (drawn as the background). A new array."""
    values = counts.astype(np.float64)
    with np.errstate(divide="ignore"):
        return np.where(values > 0, np.log10(np.where(values > 0, values, 1.0)), math.nan)
