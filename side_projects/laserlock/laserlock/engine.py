"""The loop thread: reads the wavemeter, runs the PID step on each new measurement, writes the DG1022.

Writes go out at most every `out.min_interval` (100 ms): the latest wanted voltage is written when its turn
comes, so a fast wavemeter never queues commands. The GUI reads `snapshot()` and `drain()`; it never waits on
an instrument. An instrument that stops answering ends the lock (mode "fault") and leaves the voltage where
it was.
"""

from __future__ import annotations

import collections
import csv
import logging
import statistics
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .controller import Hop, HopDetector, LockSettings, PILock, suggest_gains
from .devices import (HARD_V_MAX, HARD_V_MIN, DeviceFault, FrequencySource, Reading, VoltageOutput,
                      WavemeterTiming)

log = logging.getLogger("laserlock.engine")


@dataclass(frozen=True)
class Sample:
    t: float
    thz: float | None
    error_mhz: float | None
    volts: float
    locked: bool
    hop: bool = False  # a mode hop was confirmed at this reading


@dataclass(frozen=True)
class HopEvent:
    t: float  # unix time of the first reading at the new level
    hop: Hop
    volts: float  # the output then
    locked: bool


@dataclass(frozen=True)
class Snapshot:
    mode: str  # "idle", "locked", "calibrating", "sweeping", "fault"
    reading: Reading
    error_mhz: float | None
    volts: float
    state: str  # the last PI step's state, or what the engine is doing
    message: str
    update_s: float | None  # median time between new measurements
    hops: int = 0  # mode hops seen since start
    last_hop: HopEvent | None = None
    wavemeter: WavemeterTiming | None = None  # None: this source's timing can't be read
    d_term: float = 0.0  # V, the lock's D share of the output now


class Engine:
    def __init__(self, source: FrequencySource, out: VoltageOutput, settings: LockSettings,
                 log_dir: Path | None = None, hops: HopDetector | None = None) -> None:
        self.source, self.out = source, out
        self._settings = settings
        self.pi = PILock(replace(settings))
        self._lock = threading.Lock()
        self._mode = "idle"
        self._state = "idle"
        self._message = ""
        self._target: float | None = None  # wanted voltage not yet written
        self._volts = out.get()
        self._reading = source.read()
        self._error: float | None = None
        self._samples: collections.deque[Sample] = collections.deque(maxlen=100_000)
        self.hops = hops or HopDetector()
        self._hop_events: collections.deque[HopEvent] = collections.deque(maxlen=1000)
        self._hop_count = 0
        self._recent: collections.deque[tuple[float, float]] = collections.deque(maxlen=32)  # (reading t, volts)
        self._periods: collections.deque[float] = collections.deque(maxlen=50)
        self._last_seq = self._reading.seq
        self._last_write = 0.0
        self._stop = threading.Event()
        self._cal_request: tuple[float, float, float] | None = None
        self._abort = threading.Event()
        self._cal_seq = -1
        self._sweep_request: SweepRequest | None = None
        self._sweep_points: list[SweepPoint] = []
        self._sweep_choice: LockPoint | None = None
        self.log_dir = log_dir
        self._csv: csv.writer | None = None  # type: ignore[valid-type]
        self._csv_file = None
        self._wm_timing: WavemeterTiming | None = None
        self._wm_request: dict[str, int | bool] = {}
        self._wm_read_at = 0.0
        self._thread = threading.Thread(target=self._run, name="laserlock-engine", daemon=True)

    # ---------------------------------------------------------------- commands (any thread)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._abort.set()
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        self.set_logging(False)

    def settings(self) -> LockSettings:
        with self._lock:
            return replace(self._settings)

    def update_settings(self, settings: LockSettings) -> None:
        with self._lock:
            self._settings = replace(settings)
            self.pi.s = replace(settings)

    def engage(self) -> None:
        with self._lock:
            if self._mode == "fault":
                return
            if self._settings.setpoint_thz <= 0:
                self._message = "set a setpoint first"
                return
            self.pi.engage(self._volts)
            self._mode, self._message = "locked", "lock engaged"
        log.info("lock engaged at %.4f V, setpoint %.7f THz", self._volts, self._settings.setpoint_thz)

    def release(self) -> None:
        with self._lock:
            if self._mode == "locked":
                self._mode, self._state, self._message = "idle", "idle", f"lock released, holding {self._volts:.4f} V"
                log.info("lock released at %.4f V", self._volts)

    def set_voltage(self, volts: float) -> None:
        """Manual output (only while not locked or calibrating)."""
        with self._lock:
            if self._mode == "idle":
                s = self._settings
                self._target = min(max(volts, s.v_min), s.v_max)

    def calibrate(self, step_v: float, settle_s: float, average_s: float) -> None:
        with self._lock:
            if self._mode == "idle":
                self._cal_request = (step_v, settle_s, average_s)
                self._abort.clear()
                self._mode, self._message = "calibrating", "calibrating…"

    def abort_calibration(self) -> None:
        self._abort.set()

    def abort(self) -> None:
        """Stops a calibration or sweep (a sweep then returns to where it started)."""
        self._abort.set()

    def sweep(self, v_start: float, v_stop: float, step: float, settle_s: float, dwell_s: float,
              lock_thz: float | None = None) -> None:
        """Steps the output from v_start to v_stop, recording the frequency at each step. With `lock_thz`,
        then goes to where that frequency is crossed without a mode hop and locks there (auto-lock);
        otherwise returns to where it started."""
        with self._lock:
            if self._mode == "idle" and step > 0:
                self._sweep_request = SweepRequest(v_start, v_stop, step, settle_s, dwell_s, lock_thz)
                self._abort.clear()
                self._mode, self._message = "sweeping", "sweep: starting"  # at once, so no one sees "idle" in between

    def sweep_data(self) -> tuple[list[SweepPoint], LockPoint | None]:
        with self._lock:
            return list(self._sweep_points), self._sweep_choice

    def snapshot(self) -> Snapshot:
        with self._lock:
            update = statistics.median(self._periods) if self._periods else None
            last = self._hop_events[-1] if self._hop_events else None
            return Snapshot(self._mode, self._reading, self._error, self._volts, self._state, self._message, update,
                            self._hop_count, last, self._wm_timing, self.pi.d_term if self._mode == "locked" else 0.0)

    def set_wavemeter(self, **changes: int | bool) -> None:
        """Changes the wavemeter's timing (keys of `WavemeterTiming`), on the loop thread."""
        with self._lock:
            self._wm_request.update(changes)

    def hop_events(self) -> list[HopEvent]:
        with self._lock:
            return list(self._hop_events)

    def set_hop_threshold(self, mhz: float) -> None:
        with self._lock:
            self.hops.min_jump_mhz = mhz

    def drain(self) -> list[Sample]:
        with self._lock:
            out = list(self._samples)
            self._samples.clear()
            return out

    def set_logging(self, on: bool) -> Path | None:
        with self._lock:
            if self._csv_file is not None:
                self._csv_file.close()
                self._csv_file, self._csv = None, None
            if not on or self.log_dir is None:
                return None
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / time.strftime("laserlock-%Y%m%d-%H%M%S.csv")
            self._csv_file = path.open("w", newline="")
            self._csv = csv.writer(self._csv_file)
            self._csv.writerow(["unix_time", "thz", "setpoint_thz", "error_mhz", "volts", "locked", "status", "hop"])
            return path

    # ---------------------------------------------------------------- the loop thread

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._cal_request is not None:
                    self._calibrate(*self._cal_request)
                    continue
                if self._sweep_request is not None:
                    self._sweep(self._sweep_request)
                    continue
                self._wavemeter_timing()
                self._tick()
                self._flush_output()
            except DeviceFault as e:
                log.error("%s", e)
                with self._lock:
                    self._mode, self._state, self._message = "fault", "fault", str(e)
                    self._target = None
                self._stop.wait(0.5)
                continue
            except Exception:
                log.exception("engine loop")
                with self._lock:
                    self._mode, self._message = "fault", "internal error (see the log)"
            self._stop.wait(POLL_S)

    def _wavemeter_timing(self) -> None:
        """Applies a requested timing change, and reads the timing back about once a second (auto exposure
        changes it by itself)."""
        set_timing = getattr(self.source, "set_timing", None)
        get_timing = getattr(self.source, "timing", None)
        if get_timing is None:
            return
        with self._lock:
            request, self._wm_request = self._wm_request, {}
        now = time.monotonic()
        if request and set_timing is not None:
            set_timing(**request)
            log.info("wavemeter timing: %s", request)
            with self._lock:
                self._periods.clear()  # the update period changes
        elif now - self._wm_read_at < 1.0:
            return
        self._wm_read_at = now
        timing = get_timing()
        with self._lock:
            self._wm_timing = timing

    def _tick(self) -> None:
        r = self.source.read()
        if r.seq == self._last_seq:
            return
        prev_t = self._reading.t
        self._last_seq = r.seq
        with self._lock:
            if r.thz is not None and self._reading.thz is not None:
                self._periods.append(r.t - prev_t)
            self._reading = r
            s = self._settings
            locked = self._mode == "locked"
            if locked:
                step = self.pi.update(r.thz, r.t)
                self._target, self._error, self._state = step.voltage, step.error_mhz, step.state
            else:
                self._error = None if r.thz is None or s.setpoint_thz <= 0 else (r.thz - s.setpoint_thz) * 1e6
            self._recent.append((r.t, self._volts))
            hop = self.hops.update(r.thz, r.t)
            now = time.time()
            if hop is not None:
                # the output when the first reading at the new level came, not now (3 readings later)
                volts = next((v for t, v in self._recent if t >= hop.t), self._volts)
                event = HopEvent(now - (time.monotonic() - hop.t), hop, volts, locked)
                self._hop_events.append(event)
                self._hop_count += 1
                log.warning("mode hop %+.3f GHz (%.7f -> %.7f THz) at %.4f V%s", hop.jump_mhz / 1e3, hop.from_thz,
                            hop.to_thz, volts, " while locked" if locked else "")
            sample = Sample(now, r.thz, self._error, self._volts, locked, hop is not None)
            self._samples.append(sample)
            if self._csv is not None:
                self._csv.writerow([f"{sample.t:.3f}", "" if r.thz is None else f"{r.thz:.9f}", f"{s.setpoint_thz:.9f}",
                                    "" if self._error is None else f"{self._error:.3f}", f"{self._volts:.4f}",
                                    int(locked), r.status, int(hop is not None)])

    def _flush_output(self) -> None:
        with self._lock:
            target = self._target
        if target is None or abs(target - self._volts) < 5e-5:
            return
        if time.monotonic() - self._last_write < self.out.min_interval:
            return
        applied = self.out.set(target)  # outside the lock: may wait for the DG1022's turn
        self._last_write = time.monotonic()
        with self._lock:
            self._volts = applied
            if self._target == target:
                self._target = None

    def _collect(self, seconds: float) -> list[float]:
        values: list[float] = []
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._abort.is_set():
            self._tick()
            r = self._reading
            if r.thz is not None and r.seq != self._cal_seq:
                values.append(r.thz)
                self._cal_seq = r.seq
            self._stop.wait(POLL_S)
        return values

    def _calibrate(self, step_v: float, settle_s: float, average_s: float) -> None:
        """Measures at V0 and at V0 + step (the step may be negative), fits the slope, returns to V0, suggests
        gains. A one-sided step keeps the laser to one side of where it is (away from a mode hop on the other)."""
        with self._lock:
            self._cal_request = None
            self._mode, self._state, self._message = "calibrating", "calibrating", "calibrating…"
            s = self._settings
        v0 = self._volts
        lo, hi = v0, min(max(v0 + step_v, s.v_min), s.v_max)
        result = "calibration aborted"
        if abs(hi - lo) < 1e-3:
            with self._lock:
                self._mode, self._state = "idle", "idle"
                self._message = (f"calibration: no room for a {step_v:+.4f} V step from {v0:.4f} V inside "
                                 f"{s.v_min:g}–{s.v_max:g} V (try the other sign)")
            return
        try:
            means = []
            for v in (lo, hi):
                self._volts = self.out.set(v)
                self._collect(settle_s)
                vals = self._collect(average_s)
                if self._abort.is_set() or len(vals) < 3:
                    result = "calibration aborted" if self._abort.is_set() else "calibration: too few readings"
                    break
                means.append(statistics.fmean(vals))
            else:
                slope = (means[1] - means[0]) * 1e6 / (hi - lo)
                update = statistics.median(self._periods) if self._periods else 0.1
                try:
                    sign, kp, ki = suggest_gains(slope, update)
                    with self._lock:
                        self._settings = replace(self._settings, sign=sign, kp=kp, ki=ki)
                        self.pi.s = replace(self._settings)
                    result = f"tuning {slope:+.1f} MHz/V → sign {sign:+d}, kp {kp:.3g} V/MHz, ki {ki:.3g} V/(MHz·s)"
                except ValueError:
                    result = "calibration: no frequency change seen"
        finally:
            self._volts = self.out.set(v0)
            with self._lock:
                self._mode, self._state, self._message = "idle", "idle", result
            log.info("%s", result)

    # ---------------------------------------------------------------- sweep and auto-lock

    def _set_progress(self, message: str) -> None:
        with self._lock:
            self._message = message

    def _ramp_to(self, v: float, step: float | None = None) -> None:
        """Moves the output to v in steps of at most `step` (RAMP_STEP_V; one per DG1022 turn), reading as it goes."""
        step = RAMP_STEP_V if step is None else step
        v = min(max(v, HARD_V_MIN), HARD_V_MAX)
        while abs(v - self._volts) > 5e-5 and not self._abort.is_set():
            nxt = self._volts + max(min(v - self._volts, step), -step)
            self._volts = self.out.set(nxt)
            self._tick()

    def _sweep(self, req: SweepRequest) -> None:
        with self._lock:
            self._sweep_request = None
            self._mode, self._state = "sweeping", "sweeping"
            self._sweep_points = []
            self._sweep_choice = None
        v_back = self._volts
        result = "sweep aborted"
        locked = False
        try:
            if not self.out.output_on():
                result = "the DG1022's output is off: switch it on at the front panel first"
                return
            lo, hi = sorted((min(max(req.v_start, HARD_V_MIN), HARD_V_MAX), min(max(req.v_stop, HARD_V_MIN), HARD_V_MAX)))
            up = req.v_stop >= req.v_start
            n = max(int(round((hi - lo) / req.step)), 1)
            vs = [lo + (hi - lo) * i / n for i in range(n + 1)]
            if not up:
                vs.reverse()
            self._set_progress(f"sweep: ramping to {vs[0]:.3f} V")
            self._ramp_to(vs[0])
            for i, v in enumerate(vs):
                if self._abort.is_set():
                    return
                self._volts = self.out.set(v)
                self._collect(req.settle_s)
                vals = self._collect(req.dwell_s)
                point = sweep_point(self._volts, vals)
                with self._lock:
                    self._sweep_points.append(point)
                    self._message = f"sweep {i + 1}/{len(vs)}: {v:.3f} V"
            points = list(self._sweep_points)
            if req.lock_thz is None:
                result = f"sweep done: {len(points)} points"
                return
            choice = choose_lock_point(points, req.lock_thz)
            with self._lock:
                self._sweep_choice = choice
            if choice is None:
                got = [p.thz for p in points if p.thz is not None]
                span = f"{min(got):.6f}–{max(got):.6f} THz" if got else "no readings"
                result = f"auto-lock: {req.lock_thz:.7f} THz isn't crossed without a mode hop (sweep reached {span})"
                return
            # approach from the sweep's start side, as the sweep did (piezo hysteresis)
            self._set_progress(f"auto-lock: approaching {choice.volts:.4f} V")
            self._ramp_to(vs[0])
            self._ramp_to(choice.volts)
            self._collect(req.settle_s + 0.3)
            update = statistics.median(self._periods) if self._periods else 0.1
            sign, kp, ki = suggest_gains(choice.mhz_per_v, update)
            with self._lock:
                self._settings = replace(self._settings, setpoint_thz=req.lock_thz, sign=sign, kp=kp, ki=ki,
                                         v_min=choice.v_lo, v_max=choice.v_hi,
                                         capture_mhz=max(self._settings.capture_mhz, 2 * abs(choice.mhz_per_v) * req.step))
                self.pi.s = replace(self._settings)
                self.pi.engage(self._volts)
                self._mode, self._state = "locked", "locked"
                locked = True
            result = (f"auto-lock engaged at {choice.volts:.4f} V (tuning {choice.mhz_per_v:+.0f} MHz/V, "
                      f"hop-free {choice.v_lo:.3f}–{choice.v_hi:.3f} V kept as the output range)")
        finally:
            if not locked:
                if self._volts != v_back and "output is off" not in result:
                    self._set_progress("sweep: returning")
                    self._abort.clear()
                    self._ramp_to(v_back)
                with self._lock:
                    self._mode, self._state = "idle", "idle"
            with self._lock:
                self._message = result
            log.info("%s", result)


POLL_S = 0.01  # the wavemeter is polled every 10 ms (it measures every ~40 ms here)
RAMP_STEP_V = 0.05  # V per write when ramping (one write per 100 ms: 0.5 V/s)
HOP_MIN_MHZ = 300.0  # a jump between sweep points at least this big (and well off the trend) is a mode hop


@dataclass(frozen=True)
class SweepRequest:
    v_start: float
    v_stop: float
    step: float
    settle_s: float
    dwell_s: float
    lock_thz: float | None  # None: sweep only, then return


@dataclass(frozen=True)
class SweepPoint:
    volts: float
    thz: float | None  # median of the largest group of readings within 1 GHz (drops the far outliers)
    spread_mhz: float | None
    n: int


@dataclass(frozen=True)
class LockPoint:
    volts: float
    mhz_per_v: float
    v_lo: float  # the hop-free stretch around it
    v_hi: float


def sweep_point(volts: float, vals: list[float]) -> SweepPoint:
    if not vals:
        return SweepPoint(volts, None, None, 0)
    # the largest group of readings within 1 GHz of each other (the median of two far groups is in neither)
    groups = [[w for w in vals if abs(w - v) < 1e-3] for v in vals]
    near = max(groups, key=len)
    med = statistics.median(near)
    spread = statistics.pstdev(near) * 1e6 if len(near) > 1 else 0.0
    return SweepPoint(volts, med, spread, len(near))


def split_sweep(points: list[SweepPoint]) -> tuple[list[SweepPoint], list[tuple[int, int]], list[float], float]:
    """The sweep's points by voltage, its hop-free stretches (index ranges), the voltages of its mode hops
    (midway between the two points), and the typical step (MHz). A stretch ends at a missing reading or at a
    jump well off the trend (more than 5x the typical step and at least HOP_MIN_MHZ)."""
    pts = sorted(points, key=lambda p: p.volts)
    steps = [(b.thz - a.thz) * 1e6 for a, b in zip(pts, pts[1:]) if a.thz is not None and b.thz is not None]
    if not steps:
        return pts, [], [], 0.0
    typical = statistics.median(steps)
    limit = max(5 * abs(typical), HOP_MIN_MHZ)
    stretches: list[tuple[int, int]] = []
    hops: list[float] = []
    start = 0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if a.thz is None or b.thz is None or abs((b.thz - a.thz) * 1e6 - typical) >= limit:
            stretches.append((start, i))
            start = i + 1
            if a.thz is not None and b.thz is not None:
                hops.append((a.volts + b.volts) / 2)
    stretches.append((start, len(pts) - 1))
    return pts, stretches, hops, typical


def sweep_hops(points: list[SweepPoint]) -> list[float]:
    return split_sweep(points)[2]


def choose_lock_point(points: list[SweepPoint], target_thz: float) -> LockPoint | None:
    """Where the sweep crosses `target_thz` inside a hop-free stretch, choosing the crossing with the most room
    to either side."""
    if len(points) < 3:
        return None
    pts, stretches, _, typical = split_sweep(points)
    if not stretches:
        return None
    best: tuple[float, LockPoint] | None = None
    for a, b in stretches:
        if b - a < 2:
            continue
        for i in range(a, b):
            f1, f2 = pts[i].thz, pts[i + 1].thz
            assert f1 is not None and f2 is not None
            if not (min(f1, f2) <= target_thz <= max(f1, f2)) or f1 == f2:
                continue
            v = pts[i].volts + (target_thz - f1) / (f2 - f1) * (pts[i + 1].volts - pts[i].volts)
            lo_i, hi_i = max(a, i - 3), min(b, i + 4)  # local slope over a few points
            fa, fb = pts[lo_i].thz, pts[hi_i].thz
            assert fa is not None and fb is not None
            slope = (fb - fa) * 1e6 / (pts[hi_i].volts - pts[lo_i].volts)
            if slope == 0 or (slope > 0) != (typical > 0):
                continue
            room = min(v - pts[a].volts, pts[b].volts - v)
            cand = LockPoint(v, slope, pts[a].volts, pts[b].volts)
            if best is None or room > best[0]:
                best = (room, cand)
    return None if best is None else best[1]
