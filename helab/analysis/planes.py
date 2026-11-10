"""Planes in velocity space and the events flattened onto them (Basic plots v2's Plane projections).

A plane has a centre **c** and an orthonormal basis: **u** across, **v** up and the normal **n** = **u** × **v**.
An event at **e** lands on it at (u·(e − c), v·(e − c)); with a thickness d > 0 only events within d/2 of the
plane (|n·(e − c)| ≤ d/2) are kept, with d = 0 every event is (the normal axis summed whole, as the XY, XT and YT
histograms sum their third axis).

The orientation is set by three angles in degrees:

- ``across`` (α): the direction of the across axis in the horizontal v_x–v_y plane, from +v_x towards +v_y;
- ``tilt`` (θ): how far the plane is tilted up from horizontal about that axis (0 horizontal, 90 vertical);
- ``spin`` (ψ): a rotation of the two in-plane axes about the normal (anticlockwise as drawn).

With ψ = 0: u = (cos α, sin α, 0), n = (sin θ sin α, −sin θ cos α, cos θ) and v = n × u, so the plane's up
axis always climbs (v_z ≥ 0). The presets are the special cases: XY (v_x across, v_y up) is α = θ = 0; XT (v_x
across, v_z up) is α = 0, θ = 90; YT (v_y across, v_z up) is α = 90, θ = 90, their vectors exact.

Vectors are in (v_x, v_y, v_z) order (``XYZ``); ``velocity``'s columns are (v_z, v_x, v_y), and ``as_xyz``
reorders them. Qt-free (``tests/test_headless_imports.py``'s ``PURE``); inputs are never written to.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import numpy.typing as npt

from helab.analysis.histogram2d import MAX_AUTO_BINS, MAX_BINS
from helab.analysis.stats import freedman_diaconis_bins, shortest_range

Array = npt.NDArray[np.float64]
XYZ = ("v_x", "v_y", "v_z")
FROM_VELOCITY = (1, 2, 0)  # (v_z, v_x, v_y) columns → (v_x, v_y, v_z)
XY, XT, YT, CUSTOM = "XY", "XT", "YT", "custom"
# Each preset's (across, tilt) angles and exact (u, v, n).
PRESET_ANGLES = {XY: (0.0, 0.0), XT: (0.0, 90.0), YT: (90.0, 90.0)}
PRESET_AXES = {XY: ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
               XT: ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
               YT: ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))}
PRESET_NAMES = {XY: ("v_x", "v_y"), XT: ("v_x", "v_z"), YT: ("v_y", "v_z")}


def as_xyz(velocities: npt.ArrayLike) -> Array:
    """``velocity``'s (v_z, v_x, v_y) rows as a new (n, 3) array in (v_x, v_y, v_z) order."""
    data = np.asarray(velocities, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 3:
        raise ValueError("velocities must be an (n, 3) array")
    return np.ascontiguousarray(data[:, FROM_VELOCITY])


@dataclass(frozen=True)
class Plane:
    """One plane: ``preset`` (XY, XT, YT or custom: the angles are used only for custom), its angles in degrees
    (``across``, ``tilt``, ``spin``; see the module docstring), ``centre`` (v_x, v_y, v_z) in m/s and
    ``thickness`` in m/s (0: every event). ``label`` names it in the plot (Plane 1…)."""
    label: str
    preset: str = XY
    across: float = 0.0
    tilt: float = 0.0
    spin: float = 0.0
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
    thickness: float = 0.0

    def angles(self) -> tuple[float, float, float]:
        """(across, tilt, spin) in degrees: the preset's for a preset (spin still applies)."""
        across, tilt = PRESET_ANGLES.get(self.preset, (self.across, self.tilt))
        return across, tilt, self.spin

    def axes(self) -> tuple[Array, Array, Array]:
        """(u, v, n), each a unit vector in (v_x, v_y, v_z)."""
        if self.preset in PRESET_AXES:
            u0, v0, n = (np.array(axis) for axis in PRESET_AXES[self.preset])
        else:
            alpha, theta = math.radians(self.across), math.radians(self.tilt)
            u0 = np.array([math.cos(alpha), math.sin(alpha), 0.0])
            n = np.array([math.sin(theta) * math.sin(alpha), -math.sin(theta) * math.cos(alpha), math.cos(theta)])
            v0 = np.cross(n, u0)
        if not self.spin:
            return u0, v0, n
        psi = math.radians(self.spin)
        c, s = math.cos(psi), math.sin(psi)
        return c * u0 + s * v0, -s * u0 + c * v0, n

    def axis_names(self) -> tuple[str, str]:
        """What the across and up axes are: ``v_x``, ``v_z`` for an unspun preset, else ``u``, ``v``."""
        if self.preset in PRESET_NAMES and not self.spin:
            return PRESET_NAMES[self.preset]
        return "u", "v"

    def orientation_text(self) -> str:
        """``XT`` (a preset unspun), ``α 30°, θ 45°, ψ 0°`` (custom), ``XY, ψ 15°``."""
        if self.preset in PRESET_ANGLES:
            return self.preset + (f", ψ {self.spin:g}°" if self.spin else "")
        return f"α {self.across:g}°, θ {self.tilt:g}°, ψ {self.spin:g}°"


def project(xyz: Array, plane: Plane) -> tuple[Array, Array, int]:
    """The events (n × 3, v_x, v_y, v_z) kept by ``plane`` flattened onto it: (across, up, kept)."""
    u, v, n = plane.axes()
    offset = xyz - np.asarray(plane.centre, dtype=np.float64)
    if plane.thickness > 0:
        inside = np.abs(offset @ n) <= plane.thickness / 2
        offset = offset[inside]
    return offset @ u, offset @ v, len(offset)


@dataclass(frozen=True)
class PlaneImage:
    """A plane's counts: ``counts`` (across bins, up bins) over ``h_edges`` and ``v_edges`` (m/s, from the
    centre), ``kept`` the events within the thickness (every event for 0), ``total`` the events given,
    ``automatic`` whether each axis's bins were automatic."""
    plane: Plane
    counts: npt.NDArray[np.int64]
    h_edges: Array
    v_edges: Array
    kept: int
    total: int
    automatic: tuple[bool, bool] = (True, True)

    @property
    def inside(self) -> int:
        """The events counted in the image's bins."""
        return int(self.counts.sum())

    @property
    def peak(self) -> int:
        return int(self.counts.max()) if self.counts.size else 0

    def corners(self) -> Array:
        """The image's four corners in (v_x, v_y, v_z), m/s, in order round the edge: for drawing the plane."""
        u, v, _ = self.plane.axes()
        centre = np.asarray(self.plane.centre, dtype=np.float64)
        h0, h1 = float(self.h_edges[0]), float(self.h_edges[-1])
        v0, v1 = float(self.v_edges[0]), float(self.v_edges[-1])
        return np.array([centre + a * u + b * v for a, b in ((h0, v0), (h1, v0), (h1, v1), (h0, v1))])


def _span(values: Array, keep: float, half_width: float) -> tuple[float, float]:
    if half_width > 0:
        return -half_width, half_width
    if not len(values):
        return -1.0, 1.0
    lower, upper = shortest_range(values, keep)
    if not upper > lower:
        lower, upper = lower - 0.5e-3, upper + 0.5e-3
    return lower, upper


def _bins(values: Array, lower: float, upper: float, bins: int) -> int:
    if bins > 0:
        return min(bins, MAX_BINS)
    return max(1, min(freedman_diaconis_bins(values, lower, upper), MAX_AUTO_BINS))


def plane_image(xyz: Array, plane: Plane, keep: float = 0.99, bins: int = 0, half_width: float = 0.0,
                check: Callable[[], None] = lambda: None) -> PlaneImage:
    """``xyz`` (n × 3, m/s) flattened onto ``plane`` and binned. Each axis spans ``(−half_width, half_width)``
    about the centre when it is above 0, else the shortest range holding ``keep`` of the kept events; ``bins``
    per axis, 0 for automatic (Freedman–Diaconis, at most ``MAX_AUTO_BINS``). ``check`` raises to cancel."""
    across, up, kept = project(xyz, plane)
    check()
    h_range, v_range = _span(across, keep, half_width), _span(up, keep, half_width)
    h_bins, v_bins = _bins(across, *h_range, bins), _bins(up, *v_range, bins)
    check()
    counts, h_edges, v_edges = np.histogram2d(across, up, bins=(h_bins, v_bins), range=(h_range, v_range))
    return PlaneImage(plane, counts.astype(np.int64), h_edges, v_edges, kept, len(xyz), (bins <= 0, bins <= 0))
