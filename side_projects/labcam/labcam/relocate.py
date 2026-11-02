"""Finds an instrument that was moved on its own (the camera didn't move, so alignment can't follow it).

While an instrument reads normally, labcam keeps an `Anchor`: a grey patch of the frame around its box (the screen
grown by half, so the bezel, buttons and labels around it), with the screen itself masked out because what it
shows changes. When its surroundings have changed for a while with nobody in front, `find` looks for that patch up
to `reach` px around where it was. A clear match elsewhere (strong, well above the match where it was, and well
above any other place) is the instrument's new place; anything less and the box stays where it is.

Tried on the shelf of scopes moved on 2026-11-01: left middle 11, -18 px (best 0.60, -0.08 where it was, 0.39
elsewhere); left top 16, -13 px (0.73, 0.14, 0.59).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import Corners
from .detectors import Image

GROW = 1.5  # the patch: the box grown about its centre by this
HOLE = 0.9  # masked out: the box shrunk by this (the screen; its edge stays in)
MIN_SCORE = 0.5  # normalised correlation the new place must reach
MIN_LEAD_HERE = 0.2  # over the match where it was
MIN_LEAD_OTHER = 0.1  # over the best other place (APART px or more away)
MIN_SHIFT = 3.0  # px: less is noise, the box stays
APART = 12  # px: places at least this far from the best count as elsewhere


@dataclass
class Anchor:
    patch: np.ndarray  # grey, float32
    mask: np.ndarray  # 1 where compared
    origin: tuple[int, int]  # the patch's top-left in the frame it was taken from
    centre: tuple[float, float]  # the box's centre then


@dataclass
class Found:
    shift: tuple[float, float]  # px, from where it was expected
    score: float
    here: float  # the match where it was expected
    other: float  # the best match elsewhere
    moved: bool  # a clear new place


def _grey(frame: Image) -> np.ndarray:
    grey: np.ndarray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return grey


def anchor(frame: Image, corners: Corners) -> Anchor | None:
    """The patch around a box, or None when it doesn't fit in the frame."""
    points = np.array(corners, np.float64)
    centre = points.mean(axis=0)
    outer = centre + (points - centre) * GROW
    x0, y0 = np.floor(outer.min(axis=0)).astype(int)
    x1, y1 = np.ceil(outer.max(axis=0)).astype(int)
    h, w = frame.shape[:2]
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 8 or y1 - y0 < 8:
        return None
    patch = _grey(frame[y0:y1, x0:x1])
    mask = np.ones_like(patch)
    hole = np.round(centre + (points - centre) * HOLE - [x0, y0]).astype(np.int32)
    cv2.fillPoly(mask, [hole], 0.0)
    return Anchor(patch, mask, (int(x0), int(y0)), (float(centre[0]), float(centre[1])))


def find(a: Anchor, frame: Image, corners: Corners, reach: int = 60) -> Found | None:
    """Where the anchor's patch is now, near the box at `corners` (where it's expected). None if the search area
    leaves the frame."""
    centre = np.array(corners, np.float64).mean(axis=0)
    # Where the patch should be: as when taken, plus however far the box's expected place moved since (the
    # camera, through alignment).
    ex = a.origin[0] + int(round(centre[0] - a.centre[0]))
    ey = a.origin[1] + int(round(centre[1] - a.centre[1]))
    ph, pw = a.patch.shape
    h, w = frame.shape[:2]
    x0, y0 = max(0, ex - reach), max(0, ey - reach)
    x1, y1 = min(w, ex + pw + reach), min(h, ey + ph + reach)
    if x1 - x0 < pw + 2 or y1 - y0 < ph + 2:
        return None
    scores = cv2.matchTemplate(_grey(frame[y0:y1, x0:x1]), a.patch, cv2.TM_CCOEFF_NORMED, mask=a.mask)
    scores[~np.isfinite(scores)] = -1.0
    _, best, _, (bx, by) = cv2.minMaxLoc(scores)
    hx, hy = ex - x0, ey - y0  # the expected place in `scores`
    here = float(scores[hy, hx]) if 0 <= hy < scores.shape[0] and 0 <= hx < scores.shape[1] else -1.0
    others = scores.copy()
    others[max(0, by - APART):by + APART + 1, max(0, bx - APART):bx + APART + 1] = -1.0
    other = float(others.max())
    shift = (float(bx - hx), float(by - hy))
    moved = (best >= MIN_SCORE and best - other >= MIN_LEAD_OTHER and best - here >= MIN_LEAD_HERE
             and float(np.hypot(*shift)) >= MIN_SHIFT)
    return Found(shift, round(float(best), 3), round(here, 3), round(other, 3), moved)


def save(a: Anchor, path: Path) -> None:
    """Keeps the anchor for the next start (an instrument moved while labcam was off is then found from it)."""
    path.parent.mkdir(exist_ok=True)
    partial = path.with_suffix(".partial.npz")
    np.savez_compressed(partial, patch=a.patch.astype(np.uint8), mask=a.mask.astype(np.uint8),
                        origin=np.array(a.origin), centre=np.array(a.centre))
    partial.replace(path)


def load(path: Path) -> Anchor | None:
    try:
        with np.load(path) as data:
            origin, centre = data["origin"], data["centre"]
            return Anchor(data["patch"].astype(np.float32), data["mask"].astype(np.float32),
                          (int(origin[0]), int(origin[1])), (float(centre[0]), float(centre[1])))
    except (OSError, KeyError, ValueError):
        return None
