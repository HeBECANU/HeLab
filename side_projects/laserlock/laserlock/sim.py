"""A simulated laser, wavemeter and DG1022, for trying the lock and the window without the lab.

The laser's frequency is f0 + slope * V + drift + noise; the drift is a slow sine plus a random walk. The
wavemeter measures every `period` s and reports a measurement one period late, like an exposure.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable

from .devices import HARD_V_MAX, HARD_V_MIN, Reading


class SimLaser:
    def __init__(self, f0_thz: float = 276.732, mhz_per_v: float = 300.0, noise_mhz: float = 0.5,
                 walk_mhz_per_rt_s: float = 2.0, sine_mhz: float = 20.0, sine_period_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic, seed: int | None = None,
                 hop_every_v: float = 0.0, hop_mhz: float = 0.0, output: bool = True) -> None:
        self.f0, self.slope, self.noise = f0_thz, mhz_per_v, noise_mhz
        self.walk, self.sine, self.sine_period = walk_mhz_per_rt_s, sine_mhz, sine_period_s
        self.clock = clock
        self.hop_every_v, self.hop_mhz, self.output = hop_every_v, hop_mhz, output
        self.rng = random.Random(seed)
        self.volts = 0.0
        self._walk_mhz = 0.0
        self._t = clock()
        self._t0 = self._t
        self._lock = threading.Lock()

    def thz(self) -> float:
        with self._lock:
            now = self.clock()
            dt = max(now - self._t, 0.0)
            self._t = now
            self._walk_mhz += self.rng.gauss(0.0, self.walk * math.sqrt(dt))
            drift = self.sine * math.sin(2 * math.pi * (now - self._t0) / self.sine_period) + self._walk_mhz
            v = self.volts if self.output else 0.0
            hops = math.floor(v / self.hop_every_v) if self.hop_every_v > 0 else 0
            mhz = self.slope * v - self.hop_mhz * hops + drift + self.rng.gauss(0.0, self.noise)
            return self.f0 + mhz * 1e-6


class SimWavemeter:
    def __init__(self, laser: SimLaser, period: float = 0.03) -> None:
        self.laser, self.period = laser, period
        self._next = laser.clock() + period
        self._pending = laser.thz()
        self._reading = Reading(laser.clock(), None, "no value", 0)

    def read(self) -> Reading:
        now = self.laser.clock()
        while now >= self._next:  # one exposure ended: report the previous one, start the next
            self._reading = Reading(self._next, self._pending, "ok", self._reading.seq + 1)
            self._pending = self.laser.thz()
            self._next += self.period
        return self._reading

    def describe(self) -> str:
        return f"simulated wavemeter ({self.period * 1e3:.0f} ms)"

    def close(self) -> None:
        pass


class SimDG1022:
    def __init__(self, laser: SimLaser, min_interval: float = 0.05, volts: float = 3.5) -> None:
        self.laser, self.min_interval = laser, min_interval
        self.laser.volts = volts
        self._last = -1e9
        self.writes = 0

    def get(self) -> float:
        return self.laser.volts

    def set(self, volts: float) -> float:
        gap = self._last + self.min_interval - self.laser.clock()
        if gap > 0 and self.laser.clock is time.monotonic:
            time.sleep(gap)
        v = round(min(max(volts, HARD_V_MIN), HARD_V_MAX), 4)
        self.laser.volts = v
        self._last = self.laser.clock()
        self.writes += 1
        return v

    def readback(self) -> float:
        return self.laser.volts

    def output_on(self) -> bool:
        return self.laser.output

    def describe(self) -> str:
        return "simulated DG1022 CH1"

    def close(self) -> None:
        pass
