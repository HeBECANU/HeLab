"""The window: readings, setpoint, gains, limits, lock and calibrate buttons, the wavemeter's timing, and the
plots (error and output against time, and the sweep), each with its own y-axis range (auto or fixed).

It never waits on an instrument: a 10 Hz timer reads the engine's snapshot and new samples.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QSpinBox, QSplitter,
                             QVBoxLayout, QWidget)

from .controller import LockSettings, nm_to_thz, thz_to_nm
from .devices import HARD_V_MAX, HARD_V_MIN
from .engine import Engine, HopEvent, sweep_hops

def preset_thz(entry: dict[str, Any]) -> float | None:
    """A preset is {"thz": f} or {"nm": vacuum wavelength}, with an optional "name"."""
    if entry.get("thz"):
        return float(entry["thz"])
    if entry.get("nm"):
        return nm_to_thz(float(entry["nm"]))
    return None


def preset_label(entry: dict[str, Any]) -> str:
    thz = preset_thz(entry) or 0.0
    name = f"{entry['name']}: " if entry.get("name") else ""
    return f"{name}{thz:.9f} THz  ·  {thz_to_nm(thz):.8f} nm" if thz else f"{name}(empty)"


def light_grid(plot: Any) -> None:
    """A light-grey grid on the major ticks only: showGrid also draws the minor ticks' lines, which cost about
    40 % of a core at 5 redraws a second (2026-11-11)."""
    for side in ("left", "bottom"):
        axis = plot.getAxis(side)
        axis.setTickPen(pg.mkPen("#d8d8d8"))
        axis.setTextPen(pg.mkPen("k"))
        axis.setPen(pg.mkPen("#888"))
        axis.setGrid(255)
        axis.setStyle(maxTickLevel=0)  # major lines only


HOP_COLOUR = "#cf222e"
HOP_LINES_MAX = 30  # hop lines per time plot: the newest in the shown span (dots show all of them)
HOP_PEN = pg.mkPen(HOP_COLOUR, width=1, style=Qt.PenStyle.DashLine)


SPANS: dict[str, float | None] = {"30 s": 30.0, "2 min": 120.0, "10 min": 600.0, "1 h": 3600.0, "All": None}
MODE_COLOURS = {"idle": "#666", "locked": "#1a7f37", "calibrating": "#9a6700", "sweeping": "#9a6700",
                "fault": "#cf222e"}


def spin(lo: float, hi: float, decimals: int, step: float, value: float, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setKeyboardTracking(False)  # act on Enter or arrows, not on every typed digit
    if suffix:
        s.setSuffix(suffix)
    return s


class TimeAxis(pg.AxisItem):
    """A time axis whose values are seconds since `t0` (a whole hour, so ticks at whole minutes fall on whole
    minutes of the clock): labels are the clock time, or the seconds since `start` (the window opened)."""

    STEPS = (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200)

    def __init__(self, t0: float, start: float) -> None:
        super().__init__("bottom")
        self.t0, self.start, self.clock = t0, start, True
        self.enableAutoSIPrefix(False)

    def set_clock(self, clock: bool) -> None:
        self.clock = clock
        self.picture = None
        self.update()

    def tickSpacing(self, minVal: float, maxVal: float, size: float) -> list[tuple[float, float]]:
        span = maxVal - minVal
        if span <= 0 or size <= 0:
            return [(1.0, 0.0)]
        want = span / max(size / 90.0, 1.0)  # about one label per 90 px
        major = next((s for s in self.STEPS if s >= want), self.STEPS[-1])
        return [(float(major), 0.0)]

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:
        if not self.clock:
            return [f"{v - (self.start - self.t0):.{1 if spacing < 1 else 0}f}" for v in values]
        fmt = "%H:%M" if spacing >= 60 else "%H:%M:%S"
        out = []
        for v in values:
            text = time.strftime(fmt, time.localtime(self.t0 + v))
            if spacing < 1:
                text += f".{int(round((v % 1) * 10)) % 10}"
            out.append(text)
        return out


class YRange(QWidget):
    """A plot's y range: auto, or fixed between two values (in `unit`; the plot's data are `scale` times
    that). Zooming the y axis with the mouse switches to fixed and shows the range; the plot's own "A" button
    is followed too."""

    def __init__(self, plot: Any, scale: float, unit: str, lo: float, hi: float, decimals: int = 3,
                 state: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.plot, self.scale = plot, scale
        state = state or {}
        self.auto = QCheckBox("auto")
        self.auto.setChecked(bool(state.get("auto", True)))
        self.auto.setToolTip("Fit the y axis to the data; untick to keep the range in the boxes")
        step = 10 ** -decimals * 100
        self.lo = spin(-1e9, 1e9, decimals, step, float(state.get("lo", lo)), f" {unit}")
        self.hi = spin(-1e9, 1e9, decimals, step, float(state.get("hi", hi)), f" {unit}")
        for w in (self.lo, self.hi):
            w.setToolTip("The y range while auto is off")
            w.setMaximumWidth(150)
            w.valueChanged.connect(self._typed)
        self.auto.toggled.connect(self._apply)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.auto)
        h.addWidget(self.lo)
        h.addWidget(QLabel("to"))
        h.addWidget(self.hi)
        plot.getViewBox().sigRangeChangedManually.connect(self._mouse)
        self._apply()

    def _typed(self) -> None:
        if self.auto.isChecked():
            self.auto.setChecked(False)  # applies
        else:
            self._apply()

    def _apply(self) -> None:
        if self.auto.isChecked():
            self.plot.enableAutoRange(axis="y")
        else:
            lo, hi = sorted((self.lo.value(), self.hi.value()))
            if hi == lo:
                hi = lo + 10 ** -self.lo.decimals()
            self.plot.setYRange(lo * self.scale, hi * self.scale, padding=0)

    def _mouse(self, mask: Any) -> None:
        if mask is not None and len(mask) > 1 and not mask[1]:
            return
        lo, hi = self.plot.getViewBox().viewRange()[1]
        for w, v in ((self.lo, lo), (self.hi, hi)):
            w.blockSignals(True)
            w.setValue(v / self.scale)
            w.blockSignals(False)
        self.auto.blockSignals(True)
        self.auto.setChecked(False)
        self.auto.blockSignals(False)

    def sync(self) -> None:
        """Follows the plot's own auto-range button."""
        auto = bool(self.plot.getViewBox().state["autoRange"][1])
        if auto != self.auto.isChecked():
            self.auto.blockSignals(True)
            self.auto.setChecked(auto)
            self.auto.blockSignals(False)

    def state(self) -> dict[str, Any]:
        return {"auto": self.auto.isChecked(), "lo": self.lo.value(), "hi": self.hi.value()}


class History:
    """The time plots' samples in preallocated arrays (no per-tick rebuild): time (s since start), frequency
    (THz, absolute, so the plot follows a changed setpoint), output (V), locked. Keeps the newest `cap`."""

    def __init__(self, cap: int = 200_000) -> None:
        self.cap, self.n = cap, 0
        self.t = np.empty(cap)
        self.thz = np.empty(cap)
        self.volts = np.empty(cap)
        self.locked = np.empty(cap, dtype=bool)

    def add(self, samples: list[Any], t0: float) -> None:
        rows = [(s.t - t0, s.thz, s.volts, s.locked) for s in samples if s.thz is not None]
        if not rows:
            return
        rows = rows[-self.cap:]
        k = len(rows)
        if self.n + k > self.cap:  # keep the newest half (at most) and make room, in one move
            keep = min(self.n, self.cap // 2, self.cap - k)
            for a in (self.t, self.thz, self.volts, self.locked):
                a[:keep] = a[self.n - keep:self.n]
            self.n = keep
        cols = list(zip(*rows))
        sl = slice(self.n, self.n + k)
        self.t[sl], self.thz[sl], self.volts[sl], self.locked[sl] = cols
        self.n += k

    def since(self, t_min: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        i = int(np.searchsorted(self.t[:self.n], t_min))
        return self.t[i:self.n], self.thz[i:self.n], self.volts[i:self.n], self.locked[i:self.n]


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine, calibration: dict[str, float], on_save: Callable[[LockSettings, dict[str, float]], None],
                 title: str = "Laser lock", sweep: dict[str, float] | None = None,
                 presets: list[dict[str, Any]] | None = None, ui: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.engine, self.on_save = engine, on_save
        self.setWindowTitle(title)
        s = engine.settings()
        self._start = time.time()
        self._t0 = math.floor(self._start / 3600) * 3600  # a whole hour: time ticks fall on whole minutes
        self._hist = History()
        self._tick_n = 0
        self._shown_cal = ""

        big = QFont()
        big.setPointSize(20)
        big.setBold(True)
        self.freq_label, self.nm_label, self.err_label = QLabel("—"), QLabel("—"), QLabel("—")
        for lab in (self.freq_label, self.nm_label, self.err_label):
            lab.setFont(big)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label, self.volt_label, self.mode_label = QLabel(""), QLabel("—"), QLabel("idle")
        self.mode_label.setFont(big)
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)

        readout = QGroupBox("Wavemeter")
        g = QGridLayout(readout)
        g.addWidget(QLabel("Frequency"), 0, 0)
        g.addWidget(self.freq_label, 0, 1)
        g.addWidget(QLabel("Wavelength (vac)"), 1, 0)
        g.addWidget(self.nm_label, 1, 1)
        g.addWidget(QLabel("Error"), 2, 0)
        g.addWidget(self.err_label, 2, 1)
        g.addWidget(self.status_label, 3, 0, 1, 2)
        self.hop_label = QLabel("Mode hops: none")
        self.hop_label.setToolTip("Mode hops seen since start (red lines on the plots). A hop: a jump of at least "
                                  "the threshold in Loop that holds for a few readings; a lone far reading isn't one.")
        g.addWidget(self.hop_label, 4, 0, 1, 2)
        # its timing (the server's own settings, read back about once a second)
        self.wm_exposure = QSpinBox()
        self.wm_exposure.setRange(1, 9999)
        self.wm_exposure.setSuffix(" ms")
        self.wm_exposure.setKeyboardTracking(False)
        self.wm_exposure.setToolTip("The exposure (CCD 1). Setting it turns auto exposure off.")
        self.wm_auto = QCheckBox("auto")
        self.wm_auto.setToolTip("The wavemeter sets its exposure itself from the signal")
        self.wm_interval = QSpinBox()
        self.wm_interval.setRange(1, 100_000)
        self.wm_interval.setSuffix(" ms")
        self.wm_interval.setKeyboardTracking(False)
        self.wm_interval.setToolTip("With interval on, the wavemeter measures once per interval instead of "
                                    "as fast as the exposure allows: the lock's sample rate")
        self.wm_interval_on = QCheckBox("on")
        self.wm_interval_on.setToolTip("Measure once per interval (off: continuously)")
        self.wm_exposure.valueChanged.connect(lambda v: self.engine.set_wavemeter(exposure_ms=v))
        self.wm_auto.toggled.connect(lambda on: self.engine.set_wavemeter(auto=on))
        self.wm_interval.valueChanged.connect(lambda v: self.engine.set_wavemeter(interval_ms=v))
        self.wm_interval_on.toggled.connect(lambda on: self.engine.set_wavemeter(interval_on=on))
        g.addWidget(QLabel("Exposure"), 5, 0)
        g.addWidget(self._pair(self.wm_exposure, self.wm_auto), 5, 1)
        g.addWidget(QLabel("Measure every"), 6, 0)
        g.addWidget(self._pair(self.wm_interval, self.wm_interval_on), 6, 1)
        self._wm_widgets = (self.wm_exposure, self.wm_auto, self.wm_interval, self.wm_interval_on)
        for w in self._wm_widgets:
            w.setEnabled(False)  # until the timing has been read

        # setpoint
        self.set_thz = spin(0.0, 2000.0, 9, 1e-6, s.setpoint_thz, " THz")
        self.set_nm = spin(0.0, 1e6, 8, 1e-6, thz_to_nm(s.setpoint_thz) if s.setpoint_thz > 0 else 0.0, " nm")
        use_now = QPushButton("Use current")
        use_now.clicked.connect(self._use_current)
        self.set_thz.valueChanged.connect(self._thz_changed)
        self.set_nm.valueChanged.connect(self._nm_changed)
        self._presets: list[dict[str, Any]] = [dict(e) for e in (presets or []) if preset_thz(e)]
        self.preset_box = QComboBox()
        self.preset_box.setToolTip("Saved setpoints; choosing one sets the setpoint")
        self.preset_box.activated.connect(self._preset_chosen)
        add_preset, del_preset = QPushButton("Save setpoint"), QPushButton("Remove")
        add_preset.setToolTip("Adds the setpoint above to the saved setpoints")
        del_preset.setToolTip("Removes the chosen saved setpoint")
        add_preset.clicked.connect(self._add_preset)
        del_preset.clicked.connect(self._remove_preset)
        self._fill_presets()
        setbox = QGroupBox("Setpoint")
        f = QFormLayout(setbox)
        f.addRow("Saved", self.preset_box)
        f.addRow("", self._pair(add_preset, del_preset))
        f.addRow("Frequency", self.set_thz)
        f.addRow("Wavelength (vac)", self.set_nm)
        f.addRow("", use_now)
        self.nudge = spin(0.001, 1e5, 3, 1.0, 10.0, " MHz")
        self.nudge.setToolTip("How far the − and + buttons move the setpoint (also while locked)")
        down, up = QPushButton("−"), QPushButton("+")
        down.setToolTip("Setpoint down by the nudge")
        up.setToolTip("Setpoint up by the nudge")
        for b in (down, up):
            b.setMaximumWidth(32)
        down.clicked.connect(lambda: self._nudge(-1))
        up.clicked.connect(lambda: self._nudge(+1))
        nudge = QWidget()
        nh = QHBoxLayout(nudge)
        nh.setContentsMargins(0, 0, 0, 0)
        nh.addWidget(down)
        nh.addWidget(self.nudge)
        nh.addWidget(up)
        f.addRow("Nudge", nudge)

        # gains and limits
        self.kp = spin(0.0, 10.0, 8, 1e-5, s.kp, " V/MHz")
        self.ki = spin(0.0, 10.0, 8, 1e-5, s.ki, " V/(MHz·s)")
        self.kd = spin(0.0, 10.0, 8, 1e-5, s.kd, " V/(MHz/s)")
        self.kd.setToolTip("D acts on the measured frequency's rate (no kick when the setpoint changes); "
                           "0 is a PI lock. Calibrate sets P and I and leaves D alone.")
        self.d_filter = spin(0.0, 60.0, 2, 0.1, s.d_filter_s, " s")
        self.d_filter.setToolTip("The D term's low-pass time constant (the wavemeter's noise differentiates badly)")
        self.sign = QComboBox()
        self.sign.addItems(["+ (more V → higher f)", "− (more V → lower f)"])
        self.sign.setCurrentIndex(0 if s.sign >= 0 else 1)
        self.v_min = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_min, " V")
        self.v_max = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_max, " V")
        self.max_step = spin(0.0001, 1.0, 4, 0.001, s.max_step, " V")
        self.capture = spin(1.0, 1e6, 1, 100.0, s.capture_mhz, " MHz")
        self.hop_mhz = spin(10.0, 1e6, 0, 100.0, engine.hops.min_jump_mhz, " MHz")
        self.hop_mhz.setToolTip("A jump at least this big that holds for a few readings counts as a mode hop")
        self.hop_mhz.valueChanged.connect(self.engine.set_hop_threshold)
        gains = QGroupBox("Loop")
        f = QFormLayout(gains)
        f.addRow("P gain", self.kp)
        f.addRow("I gain", self.ki)
        f.addRow("D gain", self.kd)
        f.addRow("D filter", self.d_filter)
        f.addRow("Tuning sign", self.sign)
        f.addRow("Output min", self.v_min)
        f.addRow("Output max", self.v_max)
        f.addRow("Max step / update", self.max_step)
        f.addRow("Capture range ±", self.capture)
        f.addRow("Mode hop ≥", self.hop_mhz)
        for w in (self.kp, self.ki, self.kd, self.d_filter, self.v_min, self.v_max, self.max_step, self.capture):
            w.valueChanged.connect(self._push_settings)
        self.sign.currentIndexChanged.connect(self._push_settings)

        # output and actions
        self.manual = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.001, engine.snapshot().volts, " V")
        self.manual.valueChanged.connect(self._manual)
        self.lock_btn = QPushButton("Lock")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setMinimumHeight(40)
        self.lock_btn.toggled.connect(self._toggle_lock)
        self.cal_step = spin(-1.0, 1.0, 4, 0.01, calibration["step_v"], " V")
        self.cal_step.setToolTip("Calibrate measures at the output now and at the output plus this step; "
                                 "negative steps down (e.g. near the top limit or a mode hop above)")
        self.cal_settle = spin(0.1, 30.0, 1, 0.5, calibration["settle_s"], " s")
        self.cal_avg = spin(0.1, 30.0, 1, 0.5, calibration["average_s"], " s")
        self.cal_btn = QPushButton("Calibrate tuning")
        self.cal_btn.setToolTip("Measures the frequency at the output now and at the output plus the step, "
                                "returns, and sets the sign and the P and I gains from the slope.")
        self.cal_btn.clicked.connect(self._calibrate)
        self.log_box = QCheckBox("Log to CSV")
        self.log_box.toggled.connect(self._log)
        outbox = QGroupBox("Output (DG1022 DC offset, hard limit 0–7 V)")
        f = QFormLayout(outbox)
        f.addRow("Now", self.volt_label)
        f.addRow("Manual", self.manual)
        f.addRow(self.lock_btn)
        f.addRow("Cal. step", self.cal_step)
        f.addRow("Cal. settle", self.cal_settle)
        f.addRow("Cal. average", self.cal_avg)
        f.addRow(self.cal_btn)
        f.addRow(self.log_box)

        sw = {"v_start": 0.0, "v_stop": 7.0, "step": 0.05, "settle_s": 0.1, "dwell_s": 0.2, **(sweep or {})}
        self.sw_start = spin(HARD_V_MIN, HARD_V_MAX, 3, 0.1, sw["v_start"], " V")
        self.sw_stop = spin(HARD_V_MIN, HARD_V_MAX, 3, 0.1, sw["v_stop"], " V")
        self.sw_step = spin(0.001, 1.0, 3, 0.01, sw["step"], " V")
        self.sw_settle = spin(0.0, 5.0, 2, 0.05, sw["settle_s"], " s")
        self.sw_dwell = spin(0.05, 5.0, 2, 0.05, sw["dwell_s"], " s")
        self.sweep_btn = QPushButton("Sweep")
        self.sweep_btn.setToolTip("Steps the output from start to stop and plots the frequency at each step, "
                                  "then returns to where it was.")
        self.sweep_btn.clicked.connect(self._sweep_only)
        self.auto_btn = QPushButton("Auto-lock to setpoint")
        self.auto_btn.setToolTip("Sweeps, finds where the setpoint is crossed without a mode hop (the crossing "
                                 "with the most room), approaches it from the sweep's start side, sets the gains "
                                 "from the local slope, limits the output to that hop-free stretch, and locks.")
        self.auto_btn.clicked.connect(self._auto_lock)
        swbox = QGroupBox("Sweep / auto-lock")
        f = QFormLayout(swbox)
        f.addRow("From", self.sw_start)
        f.addRow("To", self.sw_stop)
        f.addRow("Step", self.sw_step)
        f.addRow("Settle / dwell", self._pair(self.sw_settle, self.sw_dwell))
        f.addRow(self._pair(self.sweep_btn, self.auto_btn))

        ui = {"show_plots": True, "show_sweep": True, "span": "2 min", "clock": True, **(ui or {})}
        self.show_plots = QCheckBox("Time plots")
        self.show_sweep = QCheckBox("Sweep plot")
        self.show_plots.setChecked(bool(ui["show_plots"]))
        self.show_sweep.setChecked(bool(ui["show_sweep"]))
        self.show_plots.toggled.connect(self._plots_shown)
        self.show_sweep.toggled.connect(self._plots_shown)
        view = QHBoxLayout()
        view.addWidget(QLabel("Show:"))
        view.addWidget(self.show_plots)
        view.addWidget(self.show_sweep)
        view.addStretch(1)

        left_inner = QWidget()
        lv = QVBoxLayout(left_inner)
        lv.addLayout(view)
        lv.addWidget(self.mode_label)
        lv.addWidget(readout)
        lv.addWidget(setbox)
        lv.addWidget(gains)
        lv.addWidget(outbox)
        lv.addWidget(swbox)
        lv.addWidget(self.message_label)
        lv.addStretch(1)
        left = QScrollArea()  # the controls scroll on a short screen
        left.setWidget(left_inner)
        left.setWidgetResizable(True)
        left.setMinimumWidth(left_inner.sizeHint().width() + 24)

        # plots
        pg.setConfigOptions(antialias=False, background="w", foreground="k")  # antialiasing costs a lot of CPU
        self.span = QComboBox()
        self.span.addItems(list(SPANS))
        self.span.setCurrentText(str(ui["span"]) if ui["span"] in SPANS else "2 min")
        self.span.setToolTip("The time shown (it scrolls with the newest reading unless paused)")
        self.pause = QCheckBox("Pause")
        self.pause.setToolTip("Freeze the time plots to pan and zoom with the mouse (readings keep being "
                              "recorded); dragging the time axis pauses too")
        self.time_kind = QComboBox()
        self.time_kind.addItems(["clock", "since start"])
        self.time_kind.setCurrentIndex(0 if ui["clock"] else 1)
        self.time_kind.setToolTip("The time axis: the clock time, or seconds since the window opened")
        self.time_kind.currentIndexChanged.connect(self._time_kind)
        clear = QPushButton("Clear")
        clear.setToolTip("Forget the time plots' readings so far (the CSV log, if on, keeps them)")
        clear.clicked.connect(self._clear)
        plots = pg.GraphicsLayoutWidget()
        self._time_axes = [TimeAxis(self._t0, self._start), TimeAxis(self._t0, self._start)]
        self.err_plot = plots.addPlot(row=0, col=0, axisItems={"bottom": self._time_axes[0]})
        self.err_plot.setLabel("left", "f − setpoint", units="Hz")
        light_grid(self.err_plot)
        self.err_curve = self.err_plot.plot(pen=pg.mkPen("#0969da", width=1))
        self.err_plot.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine)).setZValue(-10)  # under the trace
        self.v_plot = plots.addPlot(row=1, col=0, axisItems={"bottom": self._time_axes[1]})
        self.v_plot.setLabel("left", "Output", units="V")
        light_grid(self.v_plot)
        self.v_plot.setXLink(self.err_plot)
        for plot in (self.err_plot, self.v_plot):
            plot.getViewBox().sigRangeChangedManually.connect(self._time_dragged)
            plot.getAxis("left").setWidth(72)  # equal widths: linked time axes line up and don't shift
        self._time_kind()
        self.v_curve = self.v_plot.plot(pen=pg.mkPen("#bf3989", width=1))
        self.hop_dots = self.v_plot.plot(pen=None, symbol="o", symbolSize=9, symbolBrush=HOP_COLOUR, symbolPen=None)
        self._hop_pool: list[tuple[Any, Any]] = []  # (error-plot line, output-plot line), reused
        self._hops_drawn = (0, 0.0)  # (count, when)
        for curve in (self.err_curve, self.v_curve):  # draw at most about one point per pixel
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)
            curve.setZValue(5)  # above the grid and the zero line
        sweep_plots = pg.GraphicsLayoutWidget()
        self.sw_plot = sweep_plots.addPlot()
        self.sw_plot.setLabel("left", "f − setpoint", units="Hz")
        self.sw_plot.setLabel("bottom", "output", units="V")
        self.sw_plot.setTitle("Sweep")
        light_grid(self.sw_plot)
        self.err_range = YRange(self.err_plot, 1e6, "MHz", -50.0, 50.0, 3, ui.get("err_y"))
        self.v_range = YRange(self.v_plot, 1.0, "V", HARD_V_MIN, HARD_V_MAX, 4, ui.get("v_y"))
        self.sw_y = YRange(self.sw_plot, 1e6, "MHz", -5000.0, 5000.0, 1, ui.get("sweep_y"))
        self.sw_curve = self.sw_plot.plot(pen=pg.mkPen("#8250df", width=1), symbol="o", symbolSize=4,
                                          symbolBrush="#8250df", symbolPen=None)
        self.sw_plot.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine)).setZValue(-10)
        self.sw_choice = pg.InfiniteLine(angle=90, pen=pg.mkPen("#1a7f37", width=2))
        self.sw_range = pg.LinearRegionItem(movable=False, brush=(26, 127, 55, 40))
        self._sw_hop_lines: list[Any] = []
        for item in (self.sw_choice, self.sw_range):
            item.setVisible(False)
            self.sw_plot.addItem(item)
        self._sweep_n = -1
        right = self.right = QWidget()
        rv = QVBoxLayout(right)
        top = QHBoxLayout()
        top.addWidget(QLabel("Show"))
        top.addWidget(self.span)
        top.addWidget(self.pause)
        top.addWidget(QLabel("Time"))
        top.addWidget(self.time_kind)
        top.addWidget(clear)
        top.addStretch(1)
        self.rms_label = QLabel("")
        top.addWidget(self.rms_label)
        yrow = QHBoxLayout()
        yrow.addWidget(QLabel("Error y"))
        yrow.addWidget(self.err_range)
        yrow.addSpacing(16)
        yrow.addWidget(QLabel("Output y"))
        yrow.addWidget(self.v_range)
        yrow.addStretch(1)
        self.time_panel = QWidget()
        tv = QVBoxLayout(self.time_panel)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addLayout(top)
        tv.addLayout(yrow)
        tv.addWidget(plots)
        self.sweep_panel = QWidget()
        sv = QVBoxLayout(self.sweep_panel)
        sv.setContentsMargins(0, 0, 0, 0)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Sweep y"))
        srow.addWidget(self.sw_y)
        srow.addStretch(1)
        sv.addLayout(srow)
        sv.addWidget(sweep_plots)
        plot_split = QSplitter()
        plot_split.addWidget(self.time_panel)
        plot_split.addWidget(self.sweep_panel)
        plot_split.setStretchFactor(0, 3)
        plot_split.setStretchFactor(1, 2)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(plot_split)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.resize(1400, 860)
        self._plots_shown()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(100)

    # ---------------------------------------------------------------- user actions

    @staticmethod
    def _pair(a: QWidget, b: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(b)
        return w

    def _fill_presets(self) -> None:
        self.preset_box.clear()
        for e in self._presets:
            self.preset_box.addItem(preset_label(e))
        current = self.set_thz.value()
        for i, e in enumerate(self._presets):
            if abs((preset_thz(e) or 0) - current) < 5e-10:
                self.preset_box.setCurrentIndex(i)
                break
        else:
            self.preset_box.setCurrentIndex(-1)

    def _preset_chosen(self, i: int) -> None:
        if 0 <= i < len(self._presets):
            thz = preset_thz(self._presets[i])
            if thz:
                self.set_thz.setValue(thz)

    def _add_preset(self) -> None:
        thz = self.set_thz.value()
        if thz > 0 and all(abs((preset_thz(e) or 0) - thz) >= 5e-10 for e in self._presets):
            self._presets.append({"thz": thz})
        self._fill_presets()

    def _remove_preset(self) -> None:
        i = self.preset_box.currentIndex()
        if 0 <= i < len(self._presets):
            del self._presets[i]
        self._fill_presets()

    def presets(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._presets]

    def _plots_shown(self) -> None:
        self.time_panel.setVisible(self.show_plots.isChecked())
        self.sweep_panel.setVisible(self.show_sweep.isChecked())
        any_shown = self.show_plots.isChecked() or self.show_sweep.isChecked()
        if self.right.isVisible() != any_shown or not self.isVisible():
            self.right.setVisible(any_shown)
            if not any_shown and self.isVisible():
                self.resize(self.minimumSizeHint().width(), self.height())

    def ui_state(self) -> dict[str, Any]:
        return {"show_plots": self.show_plots.isChecked(), "show_sweep": self.show_sweep.isChecked(),
                "span": self.span.currentText(), "clock": self.time_kind.currentIndex() == 0,
                "err_y": self.err_range.state(), "v_y": self.v_range.state(), "sweep_y": self.sw_y.state()}

    def _time_kind(self) -> None:
        clock = self.time_kind.currentIndex() == 0
        for axis in self._time_axes:
            axis.set_clock(clock)
        self.v_plot.setLabel("bottom", "time" if clock else "time since start (s)")

    def _time_dragged(self, mask: Any) -> None:
        if mask is None or len(mask) < 1 or mask[0]:
            self.pause.setChecked(True)

    def _clear(self) -> None:
        self._hist.n = 0
        self.err_curve.setData([], [])
        self.v_curve.setData([], [])
        self.rms_label.setText("")

    def _nudge(self, direction: int) -> None:
        self.set_thz.setValue(self.set_thz.value() + direction * self.nudge.value() * 1e-6)

    def _sweep_only(self) -> None:
        self._sweep(False)

    def _auto_lock(self) -> None:
        self._sweep(True)

    def _sweep(self, lock: bool) -> None:
        if self.engine.snapshot().mode == "sweeping":
            self.engine.abort()
            return
        self._push_settings()
        target = self.set_thz.value() if lock else None
        if lock and not target:
            self.message_label.setText("set a setpoint first")
            return
        self._sweep_n = -1
        self.engine.sweep(self.sw_start.value(), self.sw_stop.value(), self.sw_step.value(),
                          self.sw_settle.value(), self.sw_dwell.value(), target)

    def sweep_settings(self) -> dict[str, float]:
        return {"v_start": self.sw_start.value(), "v_stop": self.sw_stop.value(), "step": self.sw_step.value(),
                "settle_s": self.sw_settle.value(), "dwell_s": self.sw_dwell.value()}

    def _current_settings(self) -> LockSettings:
        return replace(self.engine.settings(), setpoint_thz=self.set_thz.value(), kp=self.kp.value(),
                       ki=self.ki.value(), kd=self.kd.value(), d_filter_s=self.d_filter.value(),
                       sign=1 if self.sign.currentIndex() == 0 else -1,
                       v_min=self.v_min.value(), v_max=max(self.v_max.value(), self.v_min.value()),
                       max_step=self.max_step.value(), capture_mhz=self.capture.value())

    def _push_settings(self) -> None:
        self.engine.update_settings(self._current_settings())

    def _thz_changed(self, thz: float) -> None:
        self.set_nm.blockSignals(True)
        self.set_nm.setValue(thz_to_nm(thz) if thz > 0 else 0.0)
        self.set_nm.blockSignals(False)
        self._fill_presets()
        self._push_settings()

    def _nm_changed(self, nm: float) -> None:
        if nm > 0:
            self.set_thz.setValue(nm_to_thz(nm))

    def _use_current(self) -> None:
        r = self.engine.snapshot().reading
        if r.thz is not None:
            self.set_thz.setValue(round(r.thz, 7))

    def _manual(self, v: float) -> None:
        self.engine.set_voltage(v)

    def _toggle_lock(self, on: bool) -> None:
        if on:
            self._push_settings()
            self.engine.engage()
        else:
            self.engine.release()

    def _calibrate(self) -> None:
        if self.engine.snapshot().mode == "calibrating":
            self.engine.abort_calibration()
        else:
            self.engine.calibrate(self.cal_step.value(), self.cal_settle.value(), self.cal_avg.value())

    def _log(self, on: bool) -> None:
        path = self.engine.set_logging(on)
        if path is not None:
            self.message_label.setText(f"logging to {path}")

    # ---------------------------------------------------------------- refresh

    def _refresh(self) -> None:
        snap = self.engine.snapshot()
        r = snap.reading
        if r.thz is not None:
            self.freq_label.setText(f"{r.thz:.7f} THz")
            self.nm_label.setText(f"{thz_to_nm(r.thz):.6f} nm")
            self.status_label.setText(f"ok, new value every {snap.update_s * 1e3:.0f} ms" if snap.update_s else "ok")
        else:
            self.status_label.setText(f"<b style='color:#cf222e'>{r.status}</b>")
        self.err_label.setText("—" if snap.error_mhz is None else f"{snap.error_mhz:+.2f} MHz")
        self.volt_label.setText(f"{snap.volts:.4f} V")
        mode = snap.mode if snap.mode != "locked" or snap.state == "locked" else f"locked ({snap.state})"
        self.mode_label.setText(mode)
        self.mode_label.setStyleSheet(f"color: {MODE_COLOURS.get(snap.mode, '#666')}")
        if snap.message:
            self.message_label.setText(snap.message)
        locked = snap.mode == "locked"
        if self.lock_btn.isChecked() != locked:
            self.lock_btn.blockSignals(True)
            self.lock_btn.setChecked(locked)
            self.lock_btn.blockSignals(False)
        self.lock_btn.setText("Unlock" if locked else "Lock")
        busy = snap.mode in ("calibrating", "fault")
        self.lock_btn.setEnabled(snap.mode in ("idle", "locked"))
        sweeping = snap.mode == "sweeping"
        self.sweep_btn.setText("Abort" if sweeping else "Sweep")
        self.auto_btn.setText("Abort" if sweeping else "Auto-lock to setpoint")
        self.sweep_btn.setEnabled(snap.mode in ("idle", "sweeping"))
        self.auto_btn.setEnabled(snap.mode in ("idle", "sweeping"))
        self._refresh_sweep()
        self.manual.setEnabled(snap.mode == "idle")
        self.cal_btn.setText("Abort calibration" if snap.mode == "calibrating" else "Calibrate tuning")
        self.cal_btn.setEnabled(snap.mode in ("idle", "calibrating"))
        if snap.message.startswith("auto-lock engaged") and snap.message != self._shown_cal:
            self._shown_cal = snap.message
            self._show_settings()
        if snap.mode != "idle" or busy:
            self.manual.blockSignals(True)
            self.manual.setValue(snap.volts)
            self.manual.blockSignals(False)
        if snap.message.startswith("tuning") and snap.message != self._shown_cal:  # calibration set the gains
            self._shown_cal = snap.message
            self._show_settings()

        self._show_timing(snap)
        self._hist.add(self.engine.drain(), self._t0)
        if snap.hops:
            h = snap.last_hop
            assert h is not None
            self.hop_label.setText(f"<b style='color:{HOP_COLOUR}'>Mode hops: {snap.hops}</b> · last "
                                   f"{h.hop.jump_mhz / 1e3:+.3f} GHz at {time.strftime('%H:%M:%S', time.localtime(h.t))}"
                                   f" ({h.volts:.4f} V)")
        self._tick_n += 1
        # the time plots: every other tick (5 Hz), only while shown, only the visible span
        if self._tick_n % 2 or self.isMinimized():
            return
        for r_ in (self.err_range, self.v_range, self.sw_y):
            r_.sync()
        if not self.time_panel.isVisible() or not self._hist.n or self.pause.isChecked():
            return
        now = time.time() - self._t0
        span = SPANS[self.span.currentText()]
        t, thz, volts, locked = self._hist.since(now - span if span else -math.inf)
        self.v_plot.setXRange(now - span if span else (float(t[0]) if t.size else now - 1), now, padding=0)
        setpoint = self.set_thz.value()
        ref = setpoint if setpoint > 0 else float(thz[0]) if thz.size else 0.0
        err = (thz - ref) * 1e12  # Hz
        self.err_curve.setData(t, err)
        self.v_curve.setData(t, volts)
        self._draw_hops(snap.hops, now - span if span else -math.inf)
        # the lock's quality: locked readings within the capture range (not the time spent in another mode)
        in_capture = np.abs(err) <= self.capture.value() * 1e6
        locked_part = err[locked & in_capture]
        left_out = int(np.count_nonzero(locked & ~in_capture))
        if setpoint > 0 and locked_part.size > 2:
            note = f" ({left_out} off-mode readings left out)" if left_out else ""
            self.rms_label.setText(f"locked: rms {np.sqrt(np.mean(locked_part ** 2)) / 1e6:.2f} MHz, "
                                   f"mean {np.mean(locked_part) / 1e6:+.2f} MHz over the shown span{note}")
        else:
            self.rms_label.setText("")

    def _show_timing(self, snap: Any) -> None:
        """The wavemeter's timing, unless the user is changing it."""
        timing = snap.wavemeter
        if timing is None:
            return
        for w in self._wm_widgets:
            w.setEnabled(True)
        for w, v in ((self.wm_exposure, timing.exposure_ms), (self.wm_interval, timing.interval_ms)):
            if not w.hasFocus() and w.value() != v:
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
        for b, on in ((self.wm_auto, timing.auto), (self.wm_interval_on, timing.interval_on)):
            if b.isChecked() != on:
                b.blockSignals(True)
                b.setChecked(on)
                b.blockSignals(False)

    def _show_settings(self) -> None:
        """The engine changed the settings (calibration, auto-lock): show them without sending them back."""
        s = self.engine.settings()
        for w, v in ((self.kp, s.kp), (self.ki, s.ki), (self.kd, s.kd), (self.d_filter, s.d_filter_s),
                     (self.v_min, s.v_min), (self.v_max, s.v_max),
                     (self.capture, s.capture_mhz), (self.set_thz, s.setpoint_thz)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.set_nm.blockSignals(True)
        self.set_nm.setValue(thz_to_nm(s.setpoint_thz) if s.setpoint_thz > 0 else 0.0)
        self.set_nm.blockSignals(False)
        self.sign.blockSignals(True)
        self.sign.setCurrentIndex(0 if s.sign >= 0 else 1)
        self.sign.blockSignals(False)
        self._fill_presets()

    def _draw_hops(self, count: int, t_from: float) -> None:
        """Red dashed lines on both time plots at the newest HOP_LINES_MAX hops in the shown span, and red dots
        on the output at all of them. At most once a second, and the lines are reused, not rebuilt: a laser
        flipping between modes hops twice a second, and rebuilding hundreds of lines froze the window
        (2026-11-12)."""
        now = time.monotonic()
        if count == self._hops_drawn[0] or now - self._hops_drawn[1] < 1.0:
            return
        self._hops_drawn = (count, now)
        shown: list[HopEvent] = [e for e in self.engine.hop_events() if e.t - self._t0 >= t_from]
        lines = shown[-HOP_LINES_MAX:]
        while len(self._hop_pool) < len(lines):
            pair = []
            for plot in (self.err_plot, self.v_plot):
                line = pg.InfiniteLine(angle=90, pen=HOP_PEN)
                plot.addItem(line, ignoreBounds=True)
                pair.append(line)
            self._hop_pool.append((pair[0], pair[1]))
        for k, (a, b) in enumerate(self._hop_pool):
            if k < len(lines):
                x = lines[k].t - self._t0
                a.setValue(x)
                b.setValue(x)
            a.setVisible(k < len(lines))
            b.setVisible(k < len(lines))
        self.hop_dots.setData([e.t - self._t0 for e in shown], [e.volts for e in shown])

    def _refresh_sweep(self) -> None:
        points, choice = self.engine.sweep_data()
        key = len(points) * 2 + (choice is not None)
        if key == self._sweep_n:
            return
        self._sweep_n = key
        ref = self.set_thz.value()
        good = [p for p in points if p.thz is not None]
        if good:
            if ref <= 0:
                ref = good[0].thz or 0.0
            self.sw_curve.setData([p.volts for p in good], [((p.thz or 0.0) - ref) * 1e12 for p in good])
        else:
            self.sw_curve.setData([], [])
        for line in self._sw_hop_lines:
            self.sw_plot.removeItem(line)
        self._sw_hop_lines = []
        for v in sweep_hops(points):
            line = pg.InfiniteLine(pos=v, angle=90, pen=HOP_PEN)
            self.sw_plot.addItem(line, ignoreBounds=True)
            self._sw_hop_lines.append(line)
        self.sw_choice.setVisible(choice is not None)
        self.sw_range.setVisible(choice is not None)
        if choice is not None:
            self.sw_choice.setValue(choice.volts)
            self.sw_range.setRegion((choice.v_lo, choice.v_hi))

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.timer.stop()
        self.on_save(self._current_settings(), {"step_v": self.cal_step.value(), "settle_s": self.cal_settle.value(),
                                                "average_s": self.cal_avg.value()})
        super().closeEvent(event)
