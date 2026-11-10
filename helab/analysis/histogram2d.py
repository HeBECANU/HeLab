"""2D histograms of a selection's events, the third axis summed (flattened): XY, XT and YT (Basic plots v2).

Each shown axis covers the exact shortest range holding the auto-crop share of its events
(``stats.shortest_range``, as the 1D histograms), or the manual bounds set for it. The flattened axis isn't
cut by auto-crop, so every event of the chosen shots counts; manual bounds set for it limit the events summed
(a T window on the XY histogram images one cloud). Bins are automatic per axis (Freedman–Diaconis, at most
``MAX_AUTO_BINS``) or set (at most ``MAX_BINS``). The image shown may be filtered (``image_filters``) and its
colour range compressed (``compress``), as the DLD port's Density images.

Qt-free (``tests/test_headless_imports.py``'s ``PURE``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, cast

import numpy as np
import numpy.typing as npt

from helab.analysis.dataset_view import Events
from helab.analysis.stats import AXES, freedman_diaconis_bins, shortest_range

# The plane's (horizontal, vertical, summed) axes. Never rotated: XY has X across and Y up; T runs up (a space axis
# across every plane, so that they can share its scale).
PLANES = {"XY": ("X", "Y", "T"), "XT": ("X", "T", "Y"), "YT": ("Y", "T", "X")}
MAX_AUTO_BINS = 1000  # Automatic bins per axis, for an image.
MAX_BINS = 20_000  # Bins per axis set by hand (above ``stats.MAX_BINS``, the 1D histograms' limit).
Bounds = Optional[tuple[float, float]]
# Memory a plane takes a bin, for ``estimated_bytes``: held while the plot is open, its int64 counts
# (``Histogram2D.counts``) and float64 image (v2's ``PlaneCounts.image``); for a moment, one plane at a time, the
# colouring on the GUI thread (v2's ``colour_positions``: the image over its peak, held through ``compress``, its
# clip and, for log, two more float64 arrays alive at once; it also covers the Gaussian, box, median and denoise
# filters, about four images at most), or the adaptive KDE's steps (about eight: ``image_filters.adaptive``).
HELD_BYTES_PER_BIN = 16
MOMENT_BYTES_PER_BIN = 32
ADAPTIVE_BYTES_PER_BIN = 64


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


def estimated_bytes(plane_bins: Sequence[int], adaptive: bool = False) -> int:
    """The most memory planes of ``plane_bins`` bins each take at once (bytes): every plane's counts and image
    held, and the largest plane's moment (colouring, or the adaptive KDE when on), as planes run one at a time."""
    if not plane_bins:
        return 0
    moment = ADAPTIVE_BYTES_PER_BIN if adaptive else MOMENT_BYTES_PER_BIN
    return HELD_BYTES_PER_BIN * sum(plane_bins) + moment * max(plane_bins)


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


# The image shown (as the DLD port's Density images): counts, optionally blurred and per shot, its colour range
# compressed in the colour map only (the values stay linear, and the colour bar reads them).
LINEAR, SQRT, LOG, POWER = "linear", "sqrt", "log", "power γ"
SCALES = (LINEAR, SQRT, LOG, POWER)


def bin_area(item: Histogram2D) -> float:
    """One bin's area in the plane's units (m², or m·s)."""
    return float(item.h_edges[1] - item.h_edges[0]) * float(item.v_edges[1] - item.v_edges[0])


def compress(position: npt.NDArray[np.float64], scale: str, gamma: float = 0.5, decades: int = 3
             ) -> npt.NDArray[np.float64]:
    """Where in the colour map a value sits, from its linear position in the colour bar's range (0…1): the
    colour range compression. Monotonic, 0 → 0 and 1 → 1. sqrt and power γ < 1 bring out faint regions; log
    spans ``decades`` below the maximum (lower values share the darkest colour)."""
    x = np.clip(position, 0.0, 1.0)
    if scale == SQRT:
        return np.sqrt(x)
    if scale == POWER:
        return np.asarray(x ** gamma, dtype=np.float64)
    if scale == LOG:
        floor = 10.0 ** -decades
        return np.clip(np.log10(np.maximum(x, floor)) / decades + 1.0, 0.0, 1.0)
    return x


def scale_text(scale: str, gamma: float = 0.5, decades: int = 3) -> str:
    """A compressed colour scale in a few words ("" for linear): ``log, 3 decades``, ``power γ 0.5``."""
    return {SQRT: "sqrt", LOG: f"log, {decades} decades", POWER: f"power γ {gamma:g}"}.get(scale, "")
