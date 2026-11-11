"""The lock's PI loop, free of hardware and Qt.

The error is the measured frequency minus the setpoint, in MHz. `sign` is the sign of df/dV (+1: more voltage
raises the frequency), so the correction is -sign * (kp * error + ki * integral). The output is the integrator
plus the proportional term, so engaging starts from the voltage already applied (no jump).

Safety, per update:
- the output stays within [v_min, v_max] and moves at most `max_step` from the last output;
- when either limit cuts the output, the integrator is set to what was applied minus the P term
  (back-calculation), so it never winds up beyond what the output can do;
- no reading, or an error beyond `capture_mhz` (a mode hop, a wrong wavelength): hold the voltage, don't
  integrate.
"""

from __future__ import annotations

from dataclasses import dataclass

C_NM_THZ = 299_792.458  # c in nm·THz: λ(nm) = C_NM_THZ / f(THz)


def thz_to_nm(thz: float) -> float:
    return C_NM_THZ / thz


def nm_to_thz(nm: float) -> float:
    return C_NM_THZ / nm


@dataclass
class LockSettings:
    setpoint_thz: float = 0.0
    kp: float = 0.0  # V per MHz
    ki: float = 0.0  # V per MHz per s
    sign: int = 1  # sign of df/dV
    v_min: float = 0.0
    v_max: float = 7.0
    max_step: float = 0.01  # V per update
    capture_mhz: float = 1000.0  # |error| beyond this: hold
    max_dt: float = 1.0  # s: a longer gap between readings integrates as this


@dataclass
class Step:
    voltage: float
    error_mhz: float | None
    state: str  # "locked", "limited", "no reading", "out of capture"


class PILock:
    def __init__(self, settings: LockSettings) -> None:
        self.s = settings
        self.integral = 0.0  # V, the integrator's share of the output
        self.voltage = 0.0
        self.last_t: float | None = None

    def engage(self, voltage_now: float) -> None:
        """Start from the voltage already applied."""
        self.voltage = self.integral = min(max(voltage_now, self.s.v_min), self.s.v_max)
        self.last_t = None

    def update(self, thz: float | None, t: float) -> Step:
        s = self.s
        if thz is None:
            self.last_t = None
            return Step(self.voltage, None, "no reading")
        err = (thz - s.setpoint_thz) * 1e6
        if abs(err) > s.capture_mhz:
            self.last_t = None
            return Step(self.voltage, err, "out of capture")
        dt = 0.0 if self.last_t is None else min(max(t - self.last_t, 0.0), s.max_dt)
        self.last_t = t
        direction = -1.0 if s.sign >= 0 else 1.0
        p = direction * s.kp * err
        self.integral += direction * s.ki * err * dt
        wanted = self.integral + p
        out = min(max(wanted, self.voltage - s.max_step), self.voltage + s.max_step)
        out = min(max(out, s.v_min), s.v_max)
        state = "locked"
        if out != wanted:
            self.integral = out - p
            state = "limited"
        self.voltage = out
        return Step(out, err, state)


def suggest_gains(mhz_per_v: float, update_s: float) -> tuple[int, float, float]:
    """Sign, kp and ki from the tuning slope and the wavemeter's update period.

    P corrects a fifth of an error per update; I closes it with a time constant of about ten updates (at
    least 1 s), well inside the wavemeter's delay of about one update."""
    k = abs(mhz_per_v)
    if k == 0:
        raise ValueError("no tuning slope")
    tau = max(1.0, 10 * update_s)
    return (1 if mhz_per_v > 0 else -1), 0.2 / k, 1.0 / (k * tau)
