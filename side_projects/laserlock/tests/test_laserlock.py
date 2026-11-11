from __future__ import annotations

import os
import time
from typing import Any

import pytest

from laserlock import config
from laserlock.controller import LockSettings, PILock, nm_to_thz, suggest_gains, thz_to_nm
from laserlock.devices import DG1022, HARD_V_MAX, DeviceFault
from laserlock.engine import Engine
from laserlock.sim import SimDG1022, SimLaser, SimWavemeter

F0 = 276.732


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_units() -> None:
    assert thz_to_nm(nm_to_thz(1083.33)) == pytest.approx(1083.33)
    assert thz_to_nm(299.792458) == pytest.approx(1000.0)


def test_pi_moves_against_the_error_with_sign() -> None:
    for sign in (1, -1):
        pi = PILock(LockSettings(setpoint_thz=F0, kp=0.001, ki=0.0, sign=sign, v_min=0, v_max=7, max_step=1))
        pi.engage(3.0)
        step = pi.update(F0 + 10e-6, 0.0)  # 10 MHz high
        assert step.error_mhz == pytest.approx(10.0)
        assert step.voltage == pytest.approx(3.0 - sign * 0.01)


def test_pi_limits_step_and_range_without_windup() -> None:
    pi = PILock(LockSettings(setpoint_thz=F0, kp=0.0, ki=1.0, sign=1, v_min=0, v_max=3.05, max_step=0.01))
    pi.engage(3.0)
    vs = [pi.update(F0 - 100e-6, t * 0.1).voltage for t in range(20)]  # far low: wants a big rise
    assert all(b - a <= 0.01 + 1e-12 for a, b in zip(vs, vs[1:]))
    assert max(vs) == pytest.approx(3.05)
    # integrator was held at what was applied: the first opposite error turns the output back at once
    assert pi.update(F0 + 1e-6, 2.1).voltage < 3.05


def test_pi_holds_on_no_reading_and_out_of_capture() -> None:
    pi = PILock(LockSettings(setpoint_thz=F0, kp=0.01, ki=0.1, capture_mhz=100))
    pi.engage(2.0)
    assert pi.update(None, 0.0).state == "no reading"
    step = pi.update(F0 + 500e-6, 0.1)
    assert (step.state, step.voltage) == ("out of capture", 2.0)


def test_engage_never_leaves_hard_limits() -> None:
    s = config.clamp(LockSettings(v_min=-3, v_max=12))
    assert (s.v_min, s.v_max) == (0.0, HARD_V_MAX)


def test_closed_loop_on_simulated_laser() -> None:
    clock = Clock()
    laser = SimLaser(f0_thz=F0, mhz_per_v=300.0, noise_mhz=0.3, walk_mhz_per_rt_s=2.0, sine_mhz=20.0,
                     sine_period_s=30.0, clock=clock, seed=1)
    wm, out = SimWavemeter(laser, period=0.03), SimDG1022(laser, volts=3.0)
    setpoint = F0 + 300e-6 * 3.0 + 50e-6  # 50 MHz above where it starts: needs about +0.17 V
    sign, kp, ki = suggest_gains(300.0, 0.03)
    pi = PILock(LockSettings(setpoint_thz=setpoint, kp=kp, ki=ki, sign=sign, max_step=0.02))
    pi.engage(out.get())
    errors, seq, last_write = [], 0, -1.0
    while clock.t < 60.0:
        clock.t += 0.005
        r = wm.read()
        if r.seq != seq:
            seq = r.seq
            step = pi.update(r.thz, r.t)
            if clock.t - last_write >= 0.05:
                out.set(step.voltage)
                last_write = clock.t
            if clock.t > 20:
                errors.append(step.error_mhz)
    rms = (sum(e * e for e in errors) / len(errors)) ** 0.5
    assert rms < 3.0, rms  # free-running it drifts by tens of MHz


def test_engine_locks_and_calibrates_with_sim() -> None:
    laser = SimLaser(f0_thz=F0, mhz_per_v=300.0, noise_mhz=0.2, walk_mhz_per_rt_s=0.5, sine_mhz=0.0, seed=2)
    wm, out = SimWavemeter(laser, period=0.02), SimDG1022(laser, volts=3.0)
    eng = Engine(wm, out, LockSettings())
    eng.start()
    try:
        eng.calibrate(0.05, 0.2, 0.4)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not eng.snapshot().message.startswith(("tuning", "calibration")):
            time.sleep(0.05)
        snap = eng.snapshot()
        assert snap.message.startswith("tuning"), snap.message
        s = eng.settings()
        assert s.sign == 1 and s.ki > 0
        assert out.get() == pytest.approx(3.0)  # back where it started
        eng.update_settings(LockSettings(**{**s.__dict__, "setpoint_thz": F0 + 300e-6 * 3.0 + 20e-6}))
        eng.engage()
        time.sleep(4)
        snap = eng.snapshot()
        assert snap.mode == "locked"
        assert snap.error_mhz is not None and abs(snap.error_mhz) < 3, snap
        assert out.get() == pytest.approx(3.0 + 20 / 300, abs=0.01)
        assert out.writes < 4 / 0.05 + 30  # never faster than one write per 50 ms (+ the calibration's)
    finally:
        eng.stop()


class FakeVisa:
    """Answers like the DG1022, records every command and when it came."""

    def __init__(self) -> None:
        self.log: list[tuple[float, str]] = []
        self.offset = 0.0
        self.reply = ""

    def write(self, cmd: str) -> None:
        self.log.append((time.monotonic(), cmd))
        if cmd.startswith("VOLT:OFFS "):
            self.offset = float(cmd.split()[1])
        self.reply = {"*IDN?": "RIGOL TECHNOLOGIES,DG1022 ,DG1D0,03.03", "APPL?": 'CH1:"ARB,1.0e+03,5.0e+00,0.0e+00"',
                      "OUTP?": "ON", "VOLT:OFFS?": f"{self.offset:e}"}.get(cmd, "")

    def read(self) -> str:
        return self.reply

    def close(self) -> None:
        pass


@pytest.fixture
def dg(monkeypatch: pytest.MonkeyPatch) -> tuple[DG1022, FakeVisa]:
    import pyvisa

    fake = FakeVisa()

    class RM:
        def list_resources(self) -> tuple[str, ...]:
            return ("USB0::0x0957::0x5707::X::INSTR", "USB0::0x0400::0x09C4::DG1D0::INSTR")

        def open_resource(self, *a: Any, **k: Any) -> FakeVisa:
            return fake

    monkeypatch.setattr(pyvisa, "ResourceManager", RM)
    return DG1022(), fake


def test_dg1022_finds_rounds_clamps_and_paces(dg: tuple[DG1022, FakeVisa]) -> None:
    d, fake = dg
    assert d.resource.startswith("USB0::0x0400::0x09C4")
    assert d.output == "ON"
    assert d.set(1.234567) == 1.2346
    assert d.set(9.0) == HARD_V_MAX
    assert d.set(-1.0) == 0.0
    sets = [c for c in fake.log if c[1].startswith("VOLT:OFFS ")]
    assert [c for _, c in sets] == ["VOLT:OFFS 1.2346", "VOLT:OFFS 7.0000", "VOLT:OFFS 0.0000"]
    times = [t for t, _ in fake.log]
    assert min(b - a for a, b in zip(times, times[1:])) >= 0.05 - 0.002
    assert all(not c.startswith(("OUTP ", "APPL:", "FUNC", "VOLT ")) for _, c in fake.log)  # only the offset


def test_dg1022_hang_is_a_fault(dg: tuple[DG1022, FakeVisa]) -> None:
    import pyvisa

    d, fake = dg

    def hang(cmd: str) -> None:
        raise pyvisa.errors.VisaIOError(-1073807339)

    fake.write = hang  # type: ignore[method-assign]
    with pytest.raises(DeviceFault):
        d.set(1.0)


def test_window_runs_with_sim(tmp_path: Any) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from laserlock.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    laser = SimLaser(f0_thz=F0, seed=3)
    eng = Engine(SimWavemeter(laser), SimDG1022(laser), LockSettings(), log_dir=tmp_path)
    saved: list[Any] = []
    win = MainWindow(eng, {"step_v": 0.05, "settle_s": 0.5, "average_s": 0.5}, lambda s, c: saved.append(s))
    eng.start()
    try:
        win.show()
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        win._use_current()
        win.lock_btn.setChecked(True)
        assert eng.snapshot().mode == "locked"
        win.log_box.setChecked(True)
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        assert win.freq_label.text().endswith("THz")
        win.close()
        assert saved and saved[0].setpoint_thz > 0
    finally:
        eng.stop()
    assert list(tmp_path.glob("laserlock-*.csv"))
