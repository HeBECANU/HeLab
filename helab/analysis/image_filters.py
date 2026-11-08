"""Filters for a binned image (Basic plots v2's XY, XT, YT histograms), each turned on by itself and run as a chain
in the order chosen.

- ``GAUSSIAN``: a Gaussian blur, σ in bins (the same on both axes).
- ``UNITS``: a Gaussian blur, σ in the axes' units (m, s), so it means the same size in every plane whatever its bins.
- ``BOX``: the mean over a square of bins (top-hat).
- ``MEDIAN``: the median over a square of bins: takes out lone hot bins and keeps edges; it doesn't keep the total.
- ``DENOISE``: for counts (Poisson noise): the Anscombe transform (2√(n + 3/8), whose noise is about 1 whatever the
  count), a Gaussian blur there, and back; scaled to keep the total.
- ``ADAPTIVE``: an adaptive (sample-point) kernel density estimate on the bins, Abramson's: a pilot Gaussian blur
  sets each bin's own σ, σ × (pilot / its geometric mean)^-α within ¼ … 4 times σ, so that faint regions are smoothed
  more than bright cores; each bin's counts spread with its σ (one of ``LEVELS`` steps), keeping the total.

Gaussian, Gaussian in units and box are linear and shift-invariant, so they commute: their order among themselves
changes nothing. Median, denoise and adaptive KDE are not linear: where they sit in the chain matters. Edges reflect.

Qt-free (``tests/test_headless_imports.py``'s ``PURE``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, cast

import numpy as np
import numpy.typing as npt

Image = npt.NDArray[np.float64]

MEDIAN, DENOISE, ADAPTIVE, GAUSSIAN, UNITS, BOX = "median", "denoise", "adaptive", "gaussian", "units", "box"
FILTERS = (MEDIAN, DENOISE, ADAPTIVE, GAUSSIAN, UNITS, BOX)
"""Every filter, in the default order of the chain (an equal order runs in this order)."""
LINEAR = frozenset({GAUSSIAN, UNITS, BOX})
"""The filters that commute with one another (linear, shift-invariant)."""
KEEPS_TOTAL = frozenset({GAUSSIAN, UNITS, BOX, DENOISE, ADAPTIVE})
"""The filters that keep the image's total (all but the median)."""
LEVELS = 9  # The adaptive KDE's σ steps, ¼ … 4 times its σ (log-spaced).
ADAPTIVE_RANGE = 4.0  # The adaptive σ's widest factor either way.


@dataclass(frozen=True)
class Step:
    """One filter in the chain.

    Attributes:
        kind: One of ``FILTERS``.
        order: Its place in the chain (lower first; an equal order keeps ``FILTERS``' order).
        sigma: In bins, per axis (horizontal, vertical): the Gaussians', denoise's and the adaptive KDE's pilot.
        size: In bins: the box's and median's side.
        alpha: The adaptive KDE's sensitivity (0: a plain Gaussian; Abramson's ½).
        text: How the plot names it ("median 3 × 3 bins").
    """
    kind: str
    order: int = 0
    sigma: tuple[float, float] = (0.0, 0.0)
    size: int = 1
    alpha: float = 0.5
    text: str = ""


def limit(length: int) -> float:
    """The widest σ used on an axis of ``length`` bins: a quarter of it (at least 1)."""
    return max(1.0, length / 4)


def chain(steps: Sequence[Step]) -> list[Step]:
    """``steps`` in the order they run."""
    return sorted(steps, key=lambda step: (step.order, FILTERS.index(step.kind)))


def gaussian(image: Image, sigma: tuple[float, float]) -> Image:
    from scipy.ndimage import gaussian_filter

    return cast(Image, gaussian_filter(image, sigma=sigma, mode="reflect"))


def adaptive(image: Image, sigma: tuple[float, float], alpha: float) -> Image:
    """Abramson's adaptive KDE on the bins (sample point: each bin's content spread with its own σ)."""
    occupied = image > 0
    if not occupied.any() or alpha <= 0:
        return gaussian(image, sigma)
    pilot = gaussian(image, sigma)
    scale = float(np.exp(np.mean(np.log(np.maximum(pilot[occupied], 1e-300)))))
    with np.errstate(divide="ignore"):
        factor = np.where(pilot > 0, (np.maximum(pilot, 1e-300) / scale) ** -alpha, ADAPTIVE_RANGE)
    factor = np.clip(factor, 1 / ADAPTIVE_RANGE, ADAPTIVE_RANGE)
    ladder = np.geomspace(1 / ADAPTIVE_RANGE, ADAPTIVE_RANGE, LEVELS)
    level = np.abs(np.log(factor)[..., None] - np.log(ladder)).argmin(axis=-1)
    caps = (limit(image.shape[0]), limit(image.shape[1]))
    out = np.zeros_like(image)
    for index, times in enumerate(ladder):
        chosen = occupied & (level == index)
        if chosen.any():
            out += gaussian(np.where(chosen, image, 0.0),
                            (min(sigma[0] * times, caps[0]), min(sigma[1] * times, caps[1])))
    return out


def denoise(image: Image, sigma: tuple[float, float]) -> Image:
    """The Anscombe transform, a Gaussian blur there, and back (algebraic inverse, at least 0), scaled to keep the
    total."""
    total = float(image.sum())
    smooth = gaussian(2.0 * np.sqrt(np.maximum(image, 0.0) + 3 / 8), sigma)
    back = np.maximum((smooth / 2) ** 2 - 3 / 8, 0.0)
    found = float(back.sum())
    return back * (total / found) if found > 0 else back


def run(step: Step, image: Image) -> tuple[Image, str]:
    """``image`` through ``step``, and a note when a setting was capped ("" when not)."""
    from scipy.ndimage import median_filter, uniform_filter

    if step.kind in (MEDIAN, BOX):
        largest = max(1, min(image.shape))
        size = min(step.size, largest)
        note = f"{step.text}: at most {size} bins used" if size < step.size else ""
        filtered = (median_filter(image, size=size, mode="reflect") if step.kind == MEDIAN
                    else uniform_filter(image, size=size, mode="reflect"))
        return cast(Image, filtered), note
    caps = (limit(image.shape[0]), limit(image.shape[1]))
    sigma = (min(step.sigma[0], caps[0]), min(step.sigma[1], caps[1]))
    note = (f"{step.text}: σ over a quarter of the image, {sigma[0]:.3g} × {sigma[1]:.3g} bins used"
            if sigma != step.sigma else "")
    if step.kind == DENOISE:
        return denoise(image, sigma), note
    if step.kind == ADAPTIVE:
        return adaptive(image, sigma, step.alpha), note
    return gaussian(image, sigma), note


def apply(counts: npt.NDArray[np.int64] | Image, steps: Sequence[Step]
          ) -> tuple[Image, tuple[str, ...], tuple[str, ...]]:
    """``counts`` through ``steps`` in their order: the image, the steps' texts in that order, and notes on
    settings capped. No step: the counts as they are (a copy)."""
    image = np.asarray(counts, dtype=np.float64).copy()
    texts, notes = [], []
    if not image.size:
        return image, (), ()
    for step in chain(steps):
        image, note = run(step, image)
        texts.append(step.text)
        if note:
            notes.append(note)
    return image, tuple(texts), tuple(notes)
