"""Keeps the boxes on their instruments if the camera is nudged: each frame is matched to a reference frame.

ORB features on a 3/4-size grey copy, a similarity transform (shift, turn, scale) by RANSAC. The boxes are
drawn in the reference frame's coordinates and moved by that transform. Too few matches means the camera
moved too far (or something blocks it): the last good transform is kept and the page says so.

Each box then gets its own transform from the matches near it (`refine`, Tony 2026-11-03: a bump turned the camera
3° and shifted it 50 px; the far rack followed the frame's transform but the scopes nearer the camera were 50 px
off, from parallax and the wide lens). Without enough matches near it a box follows its last own transform plus
the frame's change since. A new own transform is taken only once two checks agree on it (within SETTLE px), and
small changes are ignored, so a box doesn't jitter or jump on one odd match. A box is stored through its own
transform (`for_box(...).back`), so moving it back out gives the same place.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .config import Corners
from .detectors import Image

log = logging.getLogger("labcam.align")

SCALE = 0.75  # 0.5 left too few matches near the smaller boxes for their own transforms
MIN_INLIERS = 25
LOCAL_MIN = 10  # matches near a box that must agree on its own transform
LOCAL_RADIUS = 120.0  # px (frame): matches this near a box's centre, or twice its size if larger
STILL = 1.5  # px: a box's own transform changing its corners by less is kept as it was
SETTLE = 2.0  # px: two checks agreeing within this make a new own transform


@dataclass
class Alignment:
    matrix: NDArray[np.float64]  # 2x3, reference → current frame
    inliers: int
    ok: bool
    note: str = ""

    @property
    def shift(self) -> tuple[float, float]:
        return float(self.matrix[0, 2]), float(self.matrix[1, 2])

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.matrix[1, 0], self.matrix[0, 0]))

    def move(self, corners: Corners) -> Corners:
        """Reference-frame points → current frame."""
        points = np.column_stack([np.array(corners, np.float64), np.ones(len(corners))])
        return [(float(x), float(y)) for x, y in points @ self.matrix.T]

    def back(self, corners: Corners) -> Corners:
        """Current-frame points → reference frame."""
        inverse = cv2.invertAffineTransform(self.matrix)
        points = np.column_stack([np.array(corners, np.float64), np.ones(len(corners))])
        return [(float(x), float(y)) for x, y in points @ inverse.T]


IDENTITY = Alignment(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), 0, True, "no reference frame yet")


class Aligner:
    def __init__(self) -> None:
        self.orb = cv2.ORB.create(nfeatures=4000)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.reference: Image | None = None
        self._ref_features: tuple[list[cv2.KeyPoint], Image] | None = None
        self.current = IDENTITY
        self._matches: tuple[NDArray[np.float32], NDArray[np.float32]] | None = None  # reference, current points
        self.local: dict[str, tuple[Alignment, NDArray[np.float64]]] = {}  # box → (its transform, the frame's then)
        self._candidate: dict[str, NDArray[np.float64]] = {}

    def set_reference(self, frame: Image) -> None:
        self.reference = frame.copy()
        self._ref_features = self._features(frame)
        self.current = Alignment(IDENTITY.matrix.copy(), len(self._ref_features[0]), True, "reference set")
        self.local.clear()  # boxes stored through their own transforms keep their places: same frame, identity
        self._candidate.clear()
        self._matches = None
        log.info("reference frame set (%d features)", len(self._ref_features[0]))

    def _features(self, frame: Image) -> tuple[list[cv2.KeyPoint], Image]:
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), None, fx=SCALE, fy=SCALE)
        keypoints, descriptors = self.orb.detectAndCompute(small, None)
        return list(keypoints), (descriptors if descriptors is not None else np.zeros((0, 32), np.uint8))

    def update(self, frame: Image) -> Alignment:
        if self._ref_features is None:
            return self.current
        ref_points, ref_desc = self._ref_features
        points, desc = self._features(frame)
        if len(points) < MIN_INLIERS or len(ref_points) < MIN_INLIERS:
            return self._lost(f"too few features ({len(points)})")
        matches = self.matcher.match(ref_desc, desc)
        if len(matches) < MIN_INLIERS:
            return self._lost(f"too few matches ({len(matches)})")
        src = np.array([ref_points[m.queryIdx].pt for m in matches], np.float32) / SCALE
        dst = np.array([points[m.trainIdx].pt for m in matches], np.float32) / SCALE
        matrix, inlier_mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
        if matrix is None or inliers < MIN_INLIERS:
            return self._lost(f"only {inliers} consistent matches")
        self._matches = (src, dst)
        was_ok = self.current.ok
        self.current = Alignment(matrix.astype(np.float64), inliers, True)
        dx, dy = self.current.shift
        if not was_ok:
            log.info("alignment found again: shift %.1f, %.1f px, %d matches", dx, dy, inliers)
        if math.hypot(dx, dy) > 5:
            self.current.note = f"camera moved {dx:+.0f}, {dy:+.0f} px since the reference"
        return self.current

    def for_box(self, name: str) -> Alignment:
        """The transform a box is moved by: its own, else the frame's."""
        own = self.local.get(name)
        return own[0] if own is not None else self.current

    def refine(self, name: str, corners: Corners) -> None:
        """Updates a box's own transform (`corners` in the reference frame) from the last update's matches."""
        if self._matches is None or not self.current.ok:
            return
        src, dst = self._matches
        c = np.array(corners, np.float64)
        centre = c.mean(axis=0)
        radius = max(LOCAL_RADIUS, 2.0 * float(max(np.ptp(c[:, 0]), np.ptp(c[:, 1]))))
        near = np.linalg.norm(src - centre, axis=1) < radius
        estimate: NDArray[np.float64] | None = None
        if int(near.sum()) >= LOCAL_MIN:
            matrix, mask = cv2.estimateAffinePartial2D(src[near], dst[near], method=cv2.RANSAC,
                                                       ransacReprojThreshold=3.0)
            if matrix is not None and mask is not None and int(mask.sum()) >= LOCAL_MIN:
                scale = math.hypot(matrix[0, 0], matrix[1, 0])
                if 0.8 < scale < 1.25:
                    estimate = matrix.astype(np.float64)
        own = self.local.get(name)
        if estimate is None:
            if own is None:
                return  # the frame's transform, as it is
            # Its own transform as last taken, plus however the frame moved since.
            then = np.vstack([own[1], [0, 0, 1]])
            now = np.vstack([self.current.matrix, [0, 0, 1]])
            estimate = (now @ np.linalg.inv(then) @ np.vstack([own[0].matrix, [0, 0, 1]]))[:2]
        def place(m: NDArray[np.float64]) -> NDArray[np.float64]:
            return np.column_stack([c, np.ones(4)]) @ m.T
        used = own[0].matrix if own is not None else self.current.matrix
        if own is not None and float(np.abs(place(estimate) - place(used)).max()) < STILL:
            self._candidate.pop(name, None)
            return
        candidate = self._candidate.get(name)
        if own is not None and (candidate is None or float(np.abs(place(estimate) - place(candidate)).max()) > SETTLE):
            self._candidate[name] = estimate
            return
        self._candidate.pop(name, None)
        if own is not None:
            moved = place(estimate).mean(axis=0) - place(used).mean(axis=0)
            log.info("%s: box moved %+.0f, %+.0f px with what's around it", name, moved[0], moved[1])
        self.local[name] = (Alignment(estimate, int(near.sum()), True), self.current.matrix.copy())

    def _lost(self, why: str) -> Alignment:
        if self.current.ok:
            log.warning("alignment lost: %s; keeping the last boxes", why)
        self.current = Alignment(self.current.matrix, 0, False, f"alignment lost: {why}")
        return self.current
