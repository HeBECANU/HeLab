"""Finds a screen's own outline near its box, so the boxes needn't be drawn by hand (Tony, 2026-11-02).

From the box's middle, the screen's colour (the median of the box's middle 40 %) is grown outwards over pixels
of about that colour (Lab distance under a tolerance, optionally stopped at strong edges), closed across what the
screen shows (a trace, text, a needle) and opened to drop specks; the connected part holding the box's centre is
the screen. Its convex hull is reduced to four corners. Several tolerances and edge stops are tried, and the
largest outline that is a solid four-sided shape (its pixels fill 90–115 % of the four-sided shape) and stays
inside the searched area (the box grown to three times its size) wins. Search and outline are 3x oversampled.

Tried on 2026-11-02's frames: both left scopes and the lock-in meter fit their screens; the scope-dot screen
(grey on a beige bezel, little contrast at 720p) does not, so `find` returns ok=False there (the outline leaks
into the bezel or misses the screen's top) and its box stays as drawn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .config import Corners, ordered
from .detectors import Image

UP = 3
TOLERANCES = (10.0, 15.0, 20.0, 25.0, 30.0)
EDGE_STOPS = (80.0, 90.0, None)  # percentile of the brightness gradient that stops the growing (None: no stop)
SOLID = (0.9, 1.15)
SIZE = (0.6, 1.6)  # the outline's area against the box's


@dataclass
class Found:
    corners: Corners
    ok: bool
    why: str
    ratio: float = 0.0  # area against the box's


def _quad(points: np.ndarray) -> np.ndarray:
    hull = cv2.convexHull(points)
    perimeter = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.12, 40):
        approx = cv2.approxPolyDP(hull, float(eps) * perimeter, True)
        if len(approx) == 4:
            quad: np.ndarray = approx.reshape(4, 2).astype(np.float64)
            return quad
    box: np.ndarray = cv2.boxPoints(cv2.minAreaRect(points)).astype(np.float64)
    return box


def find(frame: Image, corners: Corners) -> Found:
    c = np.array(corners, np.float64)
    cx, cy = c.mean(axis=0)
    w, h = float(np.ptp(c[:, 0])), float(np.ptp(c[:, 1]))
    fh, fw = frame.shape[:2]
    x0, y0 = int(max(0, cx - w)), int(max(0, cy - h))
    x1, y1 = int(min(fw, cx + w)), int(min(fh, cy + h))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return Found(corners, False, "box too small or outside the frame")
    area = cv2.resize(frame[y0:y1, x0:x1], None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(area, cv2.COLOR_BGR2LAB).astype(np.float32)
    middle = ((c.mean(axis=0) + (c - c.mean(axis=0)) * 0.4 - [x0, y0]) * UP).astype(np.int32)
    inside = np.zeros(area.shape[:2], np.uint8)
    cv2.fillPoly(inside, [middle], 1)
    screen = np.median(lab[inside > 0], axis=0)
    distance = np.linalg.norm(lab - screen, axis=2)
    lightness = cv2.GaussianBlur(lab[:, :, 0], (0, 0), 1.5)
    gradient = np.hypot(cv2.Sobel(lightness, cv2.CV_32F, 1, 0), cv2.Sobel(lightness, cv2.CV_32F, 0, 1))
    seed = (int((cy - y0) * UP), int((cx - x0) * UP))
    box_area = abs(cv2.contourArea(c.astype(np.float32)))
    best: tuple[float, np.ndarray, float] | None = None
    tried = 0
    for tol in TOLERANCES:
        for stop in EDGE_STOPS:
            limit = np.percentile(gradient, stop) if stop is not None else np.inf
            mask = ((distance < tol) & (gradient < limit)).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            part = labels[seed]
            if part == 0:
                continue
            tried += 1
            points = np.column_stack(np.nonzero(labels == part)[::-1]).astype(np.int32)
            touches = (points[:, 0].min() <= 1 or points[:, 1].min() <= 1
                       or points[:, 0].max() >= area.shape[1] - 2 or points[:, 1].max() >= area.shape[0] - 2)
            quad = _quad(points)
            quad_area = abs(cv2.contourArea(quad.astype(np.float32)))
            solidity = stats[part, cv2.CC_STAT_AREA] / max(1.0, quad_area)
            ratio = quad_area / UP**2 / max(1.0, box_area)
            if touches or not SOLID[0] <= solidity <= SOLID[1] or not SIZE[0] <= ratio <= SIZE[1]:
                continue
            if best is None or quad_area > best[0]:
                best = (quad_area, quad / UP + [x0, y0], ratio)
    if best is None:
        return Found(corners, False, "no solid four-sided screen found" if tried else "the box's middle isn't screen-coloured")
    found = ordered([(round(float(x), 1), round(float(y), 1)) for x, y in best[1]])
    return Found(found, True, "", round(best[2], 2))


@dataclass
class Snapped:
    corners: Corners
    sides: list[bool]  # per side (top, right, bottom, left), whether a clear edge was found near it
    moved: float  # largest corner move, px


SIDE_REACH = 0.2  # how far each side is searched, as a fraction of the drawn box's smaller size (plus 3 px)
SIDE_TURN = 5.0  # degrees a side may turn from the drawn one
LINES = 21  # lines across each side


def snap_drawn(frame: Image, drawn: Corners) -> Snapped:
    """Each side of a drawn box moved to the screen's edge near it (Tony, 2026-11-02: draw a box, it snaps).

    Along lines across each side, from inside out, the colour's distance from the screen's (the median of the box's
    middle 40 %) is followed; each line's edge is the first place, from inside, where that distance rises at least half as fast as
    its fastest rise on the line (the screen's own edge, not the bezel's or a shadow's further out). The side's edge is a straight
    fit through those places where they agree (within 3 px of their median); a side whose lines don't agree, or
    whose fit turns more than SIDE_TURN, keeps the drawn side (or moves parallel by the median). Corners are where
    adjacent sides meet. Everything is searched near the drawn box only, so the bezel or a menu column further out
    can't pull a side away.
    """
    pts = np.array(ordered(drawn), np.float64)
    centre = pts.mean(axis=0)
    h, w = frame.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(frame, (3, 3), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    middle = np.round(centre + (pts - centre) * 0.4).astype(np.int32)
    inside = np.zeros((h, w), np.uint8)
    cv2.fillPoly(inside, [middle], 1)
    screen = np.median(lab[inside > 0], axis=0)
    reach = SIDE_REACH * min(math.dist(tuple(pts[i]), tuple(pts[(i + 1) % 4])) for i in range(4)) + 3
    steps = np.arange(-reach, reach + 0.01, 0.5)
    lines: list[tuple[np.ndarray, np.ndarray]] = []
    found: list[bool] = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        along = (b - a) / max(1e-9, float(np.linalg.norm(b - a)))
        normal = np.array([along[1], -along[0]])
        if np.dot(normal, centre - (a + b) / 2) > 0:
            normal = -normal  # outwards
        hits, offsets = [], []
        for t in np.linspace(0.12, 0.88, LINES):
            base = a + (b - a) * t
            xy = base[None, :] + normal[None, :] * steps[:, None]
            xs, ys = xy[:, 0], xy[:, 1]
            if xs.min() < 0 or ys.min() < 0 or xs.max() > w - 1 or ys.max() > h - 1:
                continue
            colours = cv2.remap(lab, xs.astype(np.float32)[None, :], ys.astype(np.float32)[None, :], cv2.INTER_LINEAR)[0]
            distance = np.linalg.norm(colours - screen, axis=1)
            rise = np.convolve(np.diff(distance), np.ones(3) / 3, "same")
            peak = float(rise.max())
            if peak < 2.0:  # no edge along this line
                continue
            # The first strong rise from inside: the screen's own edge, not the bezel's or a shadow's further out.
            k = int(np.argmax(rise >= 0.5 * peak))
            hits.append(base + normal * (steps[k] + 0.25))
            offsets.append(steps[k] + 0.25)
        side = (a, along)
        ok = False
        if len(offsets) >= LINES // 2:
            median = float(np.median(offsets))
            agree = [p for p, o in zip(hits, offsets) if abs(o - median) <= 3]
            if len(agree) >= LINES // 2:
                ok = True
                vx, vy, x0, y0 = cv2.fitLine(np.array(agree, np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
                direction = np.array([vx, vy], np.float64)
                turn = math.degrees(math.acos(min(1.0, abs(float(np.dot(direction, along))))))
                side = (np.array([x0, y0], np.float64), direction) if turn <= SIDE_TURN else (a + normal * median, along)
        lines.append(side)
        found.append(ok)
    corners = []
    for i in range(4):
        (p, d), (q, e) = lines[(i - 1) % 4], lines[i]
        m = np.array([d, -e]).T
        if abs(np.linalg.det(m)) < 1e-9:
            corners.append(pts[i])
            continue
        t, _ = np.linalg.solve(m, q - p)
        corners.append(p + t * d)
    moved = max(math.dist(tuple(x), tuple(y)) for x, y in zip(pts, corners))
    return Snapped([(round(float(x), 1), round(float(y), 1)) for x, y in corners], found, round(moved, 1))
