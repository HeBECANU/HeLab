"""A per-shot plot's X axis: the shot ID, or the shot's time (Basic plots v2's "X axis" setting).

A shot's time is when it was taken: its raw ``d<N>.txt`` file's modification time
(``DatasetView.shot_time``). A shot without a raw file takes its TXY file's time, which is when it was
converted (``DatasetView.fallback_times``): plots mark those points and count them. A shot with no time
at all is left out of a time axis and counted. Long gaps between shots (a stall, the next run) break the
plot's line rather than join its ends.

Qt-free (``tests/test_headless_imports.py``'s ``PURE``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from helab.analysis.dataset_view import DatasetView
from helab.analysis.parameters import ParameterSpec

SHOT_ID, SHOT_TIME = "Shot ID", "Shot time"
X_AXIS_NAME = "x_axis"
# A gap this many times the shots' median interval breaks the line: the plot shows the gap, not a long diagonal.
GAP_FACTOR = 10.0
FALLBACK_COLOUR = (230, 140, 0)  # The marks of TXY times (as the DLD port's Shot times draws them).
TOOLTIP = ("A shot's time is its raw d<N>.txt file's modification time; amber triangles have no raw file, so "
           "their time is the TXY file's: when it was converted. A copied or rewritten file has a new "
           "modification time.")


def x_axis_spec(group: str) -> ParameterSpec:
    """The "X axis" setting: Shot ID (the default) or Shot time."""
    return ParameterSpec(X_AXIS_NAME, "X axis", "choice", SHOT_ID, choices=(SHOT_ID, SHOT_TIME), group=group,
                         tip="Shot ID, or when the shot was taken: its raw d<N>.txt file's time, else its TXY file's "
                             "(amber triangles: when it was converted). Shots without a time are left out.")


def axis_mode(values: Mapping[str, Any]) -> str:
    """The X axis chosen in ``values`` (Shot ID when unset)."""
    return SHOT_TIME if values.get(X_AXIS_NAME) == SHOT_TIME else SHOT_ID


def axis_brief(values: Mapping[str, Any]) -> str:
    """The settings' short form: "against shot time", or "" for the default."""
    return "against shot time" if axis_mode(values) == SHOT_TIME else ""


def fallback_text(count: int) -> str:
    return f"{count:,} TXY time{'' if count == 1 else 's'} (no raw file)"


def untimed_text(count: int) -> str:
    return f"{count:,} without a time left out"


def time_text(seconds: float) -> str:
    """A shot's time on the local clock: ``2026-11-05 14:03:12``."""
    return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class ShotAxis:
    """The chosen shots as a per-shot plot draws them, in drawing order.

    Attributes:
        mode: ``SHOT_ID`` or ``SHOT_TIME``.
        shots: The shots drawn: by shot ID, every chosen shot ascending; by time, those with a time,
            ascending by time (then ID).
        x: Their shot IDs, or their times (s since the epoch).
        fallback: By time, whether a shot's time is its TXY file's (no raw file); by ID, all False.
        untimed: By time, the chosen shots left out for having no time at all.
    """

    mode: str
    shots: npt.NDArray[np.int64]
    x: npt.NDArray[np.float64]
    fallback: npt.NDArray[np.bool_]
    untimed: tuple[int, ...] = ()

    @property
    def by_time(self) -> bool:
        return self.mode == SHOT_TIME

    @property
    def label(self) -> str:
        """The axis's title."""
        return SHOT_TIME if self.by_time else SHOT_ID

    @property
    def fallbacks(self) -> int:
        return int(self.fallback.sum())

    def breaks(self) -> npt.NDArray[np.bool_]:
        """Where the line breaks before a point: by time, after a gap over ``GAP_FACTOR`` times the median
        interval between the shots (none with fewer than three); by ID, nowhere."""
        breaks = np.zeros(len(self.x), dtype=np.bool_)
        if not self.by_time or len(self.x) < 3:
            return breaks
        gaps = np.diff(self.x)
        positive = gaps[gaps > 0]
        if not len(positive):
            return breaks
        breaks[1:] = gaps > GAP_FACTOR * float(np.median(positive))
        return breaks

    def notes(self) -> list[str]:
        """The title's notes: the TXY times (a warning) and the shots without a time."""
        notes = [f"⚠ {fallback_text(self.fallbacks)}"] if self.fallbacks else []
        return notes + ([untimed_text(len(self.untimed))] if self.untimed else [])

    def point_text(self, index: int) -> str:
        """One point's hover text: ``shot 1235 · 2026-11-05 14:03:12 (TXY time)``."""
        shot = int(self.shots[index])
        if not self.by_time:
            return f"shot {shot}"
        return f"shot {shot} · {time_text(float(self.x[index]))}" + (" (TXY time)" if self.fallback[index] else "")


def shot_axis(view: DatasetView, shots: Sequence[int], mode: str) -> ShotAxis:
    """The chosen ``shots`` on the X axis ``mode`` (``SHOT_ID`` or ``SHOT_TIME``)."""
    chosen = sorted(int(shot) for shot in shots)
    if mode != SHOT_TIME:
        numbers = np.asarray(chosen, dtype=np.int64)
        return ShotAxis(SHOT_ID, numbers, numbers.astype(np.float64), np.zeros(len(numbers), dtype=np.bool_))
    timed = view.shot_times(chosen)
    order = sorted(timed, key=lambda shot: (timed[shot], shot))
    fallbacks = set(view.fallback_times(order))
    numbers = np.asarray(order, dtype=np.int64)
    return ShotAxis(SHOT_TIME, numbers, np.asarray([timed[shot] for shot in order], dtype=np.float64),
                    np.asarray([shot in fallbacks for shot in order], dtype=np.bool_),
                    tuple(shot for shot in chosen if shot not in timed))


def broken(x: npt.NDArray[np.float64], y: npt.NDArray[np.float64], breaks: npt.NDArray[np.bool_]
           ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """``x`` and ``y`` with a NaN point before each break, so that a line drawn through the finite points
    (PyQtGraph's ``connect="finite"``, Plotly and Matplotlib by default) stops there. New arrays."""
    if not breaks.any():
        return x.astype(np.float64), y.astype(np.float64)
    at = np.flatnonzero(breaks)
    return (np.insert(x.astype(np.float64), at, np.nan), np.insert(y.astype(np.float64), at, np.nan))
