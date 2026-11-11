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

    def lock_excl(self, timeout: int = 0) -> None:
        self.locked = True

    def unlock(self) -> None:
        self.locked = False

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
    assert fake.locked  # no other VISA program can interleave commands
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


# ---------------------------------------------------------------- sweep and auto-lock

from laserlock.engine import SweepPoint, choose_lock_point  # noqa: E402


def _points(slope: float, hop_every: float, hop: float, f0: float = F0) -> list[SweepPoint]:
    import math

    pts = []
    for i in range(71):
        v = i * 0.1
        mhz = slope * v - (hop * math.floor(v / hop_every) if hop_every else 0)
        pts.append(SweepPoint(v, f0 + mhz * 1e-6, 1.0, 5))
    return pts


def test_choose_lock_point_avoids_hops_and_picks_most_room() -> None:
    pts = _points(300.0, 2.0, 600.0)  # a sawtooth: each 2 V stretch spans 600 MHz
    target = F0 + 300e-6  # crossed at 1.0, 3.0, 5.0 V (and near the hop edges)
    choice = choose_lock_point(pts, target)
    assert choice is not None
    assert choice.mhz_per_v == pytest.approx(300.0, rel=0.05)
    assert choice.volts == pytest.approx(round(choice.volts), abs=0.06)  # the middle of a stretch
    assert choice.v_hi - choice.v_lo == pytest.approx(1.9, abs=0.11)  # never across a hop
    assert choose_lock_point(pts, F0 + 5000e-6) is None  # never reached


def test_choose_lock_point_negative_slope_and_gaps() -> None:
    pts = _points(-500.0, 0, 0)
    pts[10] = SweepPoint(1.0, None, None, 0)  # a missing reading splits the stretch
    choice = choose_lock_point(pts, F0 - 2000e-6)  # at 4.0 V
    assert choice is not None and choice.volts == pytest.approx(4.0, abs=0.01)
    assert choice.mhz_per_v == pytest.approx(-500.0, rel=0.02)
    assert choice.v_lo == pytest.approx(1.1)


def _wait(eng: Engine, until: Any, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not until(eng.snapshot()):
        time.sleep(0.05)


def test_auto_lock_on_simulated_laser_with_hops() -> None:
    laser = SimLaser(f0_thz=F0, mhz_per_v=300.0, noise_mhz=0.3, walk_mhz_per_rt_s=0.3, sine_mhz=0.0, seed=4,
                     hop_every_v=1.5, hop_mhz=400.0)
    wm, out = SimWavemeter(laser, period=0.02), SimDG1022(laser, volts=2.0)
    eng = Engine(wm, out, LockSettings())
    target = F0 + (300 * 4.0 - 400 * 2) * 1e-6  # crossed at 4.0 V (the 3.0-4.5 V stretch) and elsewhere
    eng.start()
    try:
        eng.sweep(2.5, 5.5, 0.1, 0.05, 0.1, lock_thz=target)
        _wait(eng, lambda s: s.mode in ("locked", "idle", "fault") and not s.message.startswith("sweep"), 40)
        snap = eng.snapshot()
        assert snap.mode == "locked", snap.message
        points, choice = eng.sweep_data()
        assert len(points) == 31 and choice is not None
        s = eng.settings()
        assert s.setpoint_thz == target and s.sign == 1
        assert 3.0 <= s.v_min < s.v_max <= 4.5  # kept inside the hop-free stretch
        time.sleep(3)
        snap = eng.snapshot()
        assert snap.error_mhz is not None and abs(snap.error_mhz) < 5, snap
        assert out.get() == pytest.approx(4.0, abs=0.05)
    finally:
        eng.stop()


def test_sweep_refuses_with_output_off_and_returns_after_plain_sweep() -> None:
    laser = SimLaser(f0_thz=F0, seed=5, output=False)
    out = SimDG1022(laser, volts=1.0)
    eng = Engine(SimWavemeter(laser, period=0.02), out, LockSettings())
    eng.start()
    try:
        eng.sweep(0.0, 1.0, 0.1, 0.0, 0.05)
        _wait(eng, lambda s: "output is off" in s.message, 5)
        assert "output is off" in eng.snapshot().message
        assert out.writes == 0  # nothing was written
        laser.output = True
        eng.sweep(1.0, 1.5, 0.1, 0.0, 0.05)
        _wait(eng, lambda s: s.message.startswith("sweep done"), 15)
        assert eng.snapshot().mode == "idle"
        assert out.get() == pytest.approx(1.0)  # back where it was
        assert len(eng.sweep_data()[0]) == 6
    finally:
        eng.stop()


def test_sweep_point_takes_the_largest_group() -> None:
    from laserlock.engine import sweep_point

    p = sweep_point(1.0, [F0, F0 + 1e-6, F0 - 11e-3, F0 - 11e-3 + 2e-6])  # two far groups of 2: median in neither
    assert p.thz is not None and p.n == 2
    p = sweep_point(1.0, [F0, F0 + 2e-6, F0 + 1e-6, F0 + 19.7e-3])
    assert p.thz == pytest.approx(F0 + 1e-6) and p.n == 3


def test_presets_and_hiding_plots(tmp_path: Any) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from laserlock.gui import MainWindow, preset_label, preset_thz

    assert preset_thz({"nm": 1083.33064456}) == pytest.approx(299792.458 / 1083.33064456)
    assert "THz" in preset_label({"thz": 276.767676767677}) and "nm" in preset_label({"thz": 276.767676767677})
    cfg = config.load(tmp_path)  # defaults only
    assert cfg["lock"]["setpoint_thz"] == pytest.approx(276.767676767677)
    app = QApplication.instance() or QApplication([])
    laser = SimLaser(f0_thz=F0, seed=6)
    eng = Engine(SimWavemeter(laser), SimDG1022(laser), config.lock_settings(cfg))
    win = MainWindow(eng, cfg["calibration"], lambda s, c: None, presets=cfg["presets"], ui={"show_sweep": False})
    win.show()
    app.processEvents()
    assert win.preset_box.count() == 2 and win.preset_box.currentIndex() == 0  # the default setpoint is preset 1
    assert win.set_thz.value() == pytest.approx(276.767676768, abs=1e-9)
    win._preset_chosen(1)
    assert win.set_nm.value() == pytest.approx(1083.33064456, abs=1e-8)
    assert eng.settings().setpoint_thz == pytest.approx(299792.458 / 1083.33064456, abs=1e-9)
    win.set_thz.setValue(276.5)
    assert win.preset_box.currentIndex() == -1
    win._add_preset()
    assert win.preset_box.count() == 3 and win.preset_box.currentIndex() == 2
    win._remove_preset()
    assert len(win.presets()) == 2
    assert not win.sweep_panel.isVisible() and win.time_panel.isVisible()
    win.show_plots.setChecked(False)
    assert not win.right.isVisible()
    win.show_sweep.setChecked(True)
    assert win.right.isVisible() and win.sweep_panel.isVisible()
    assert win.ui_state() == {"show_plots": False, "show_sweep": True}
    win.close()


def test_history_keeps_newest_in_order() -> None:
    from laserlock.engine import Sample
    from laserlock.gui import History

    h = History(cap=10)
    for start in range(0, 37, 3):  # batches of 3
        h.add([Sample(float(i), 276.0 + i, None, 0.1 * i, i % 2 == 0) for i in range(start, start + 3)], 0.0)
    t, thz, volts, locked = h.since(-1.0)
    assert list(t) == sorted(t) and t[-1] == 38.0 and h.n <= 10
    assert thz[-1] == 276.0 + 38 and locked[-1] and not locked[-2]
    t2, *_ = h.since(36.0)
    assert list(t2) == [36.0, 37.0, 38.0]
    h.add([Sample(100.0 + i, 1.0, None, 0.0, False) for i in range(25)], 0.0)  # more than cap at once
    assert h.n == 10 and h.t[h.n - 1] == 124.0
