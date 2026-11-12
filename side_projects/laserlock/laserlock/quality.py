"""Labels stretches of a frequency trace: fast up-and-down flicker, and sharp jumps (free of Qt).

Both are judged against the trace's own step-to-step noise (a robust sigma from the median absolute
deviation of the steps), so the normal scatter of a locked or a free-running laser isn't flagged:

- a *big* step is at least max(`flicker_min_mhz`, 6 sigma);
- *flicker*: big steps reversing direction at least `reversals` times within `window_s` (a lock ringing, a
  laser flicking between modes, a bad wavemeter signal); every reading in such a stretch is flagged;
- a *jump*: a step of at least max(`jump_min_mhz`, 10 sigma) that isn't part of flicker (a mode hop, or a
  sudden step); both readings of the step are flagged, so the drawn segment between them is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Quality:
    flicker: np.ndarray  # bool per reading
    jump: np.ndarray  # bool per reading (both ends of each jump step)
    jumps: int  # jump steps
    flicker_s: float  # time spent flickering
    sigma_mhz: float  # the steps' robust noise


def classify(t: np.ndarray, f_mhz: np.ndarray, flicker_min_mhz: float = 5.0, jump_min_mhz: float = 50.0,
             window_s: float = 1.0, reversals: int = 3) -> Quality:
    n = len(f_mhz)
    flicker = np.zeros(n, dtype=bool)
    jump = np.zeros(n, dtype=bool)
    if n < 3:
        return Quality(flicker, jump, 0, 0.0, 0.0)
    d = np.diff(f_mhz)
    sigma = 1.4826 * float(np.median(np.abs(d - np.median(d))))
    big = np.abs(d) >= max(flicker_min_mhz, 6 * sigma)
    idx = np.flatnonzero(big)
    if idx.size >= 2:
        sign = np.sign(d[idx])
        when = t[idx + 1]
        rev = (sign[1:] != sign[:-1]) & (np.diff(when) <= window_s)
        rev_t = when[1:][rev]
        if rev_t.size:
            lo = np.searchsorted(rev_t, t - window_s / 2, side="left")
            hi = np.searchsorted(rev_t, t + window_s / 2, side="right")
            flicker = (hi - lo) >= reversals
    steps = np.flatnonzero((np.abs(d) >= max(jump_min_mhz, 10 * sigma)) & ~(flicker[:-1] | flicker[1:]))
    jump[steps] = True
    jump[steps + 1] = True
    dt = np.diff(t)
    flicker_s = float(np.sum(dt[flicker[1:] & flicker[:-1]]))
    return Quality(flicker, jump, int(steps.size), flicker_s, sigma)
