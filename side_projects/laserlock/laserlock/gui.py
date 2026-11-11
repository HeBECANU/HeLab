"""The window: readings, setpoint, gains, limits, lock and calibrate buttons, and two plots (error and voltage).

It never waits on an instrument: a 10 Hz timer reads the engine's snapshot and new samples.
"""

from __future__ import annotations

import collections
import time
from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget)

from .controller import LockSettings, nm_to_thz, thz_to_nm
from .devices import HARD_V_MAX, HARD_V_MIN
from .engine import Engine

SPANS = {"30 s": 30.0, "2 min": 120.0, "10 min": 600.0, "1 h": 3600.0}
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


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine, calibration: dict[str, float], on_save: Callable[[LockSettings, dict[str, float]], None],
                 title: str = "Laser lock", sweep: dict[str, float] | None = None) -> None:
        super().__init__()
        self.engine, self.on_save = engine, on_save
        self.setWindowTitle(title)
        s = engine.settings()
        self._t0 = time.time()
        self._data: collections.deque[tuple[float, float, float, float]] = collections.deque(maxlen=200_000)
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

        # setpoint
        self.set_thz = spin(0.0, 2000.0, 7, 1e-6, s.setpoint_thz, " THz")
        self.set_nm = spin(0.0, 1e6, 6, 1e-6, thz_to_nm(s.setpoint_thz) if s.setpoint_thz > 0 else 0.0, " nm")
        use_now = QPushButton("Use current")
        use_now.clicked.connect(self._use_current)
        self.set_thz.valueChanged.connect(self._thz_changed)
        self.set_nm.valueChanged.connect(self._nm_changed)
        setbox = QGroupBox("Setpoint")
        f = QFormLayout(setbox)
        f.addRow("Frequency", self.set_thz)
        f.addRow("Wavelength (vac)", self.set_nm)
        f.addRow("", use_now)

        # gains and limits
        self.kp = spin(0.0, 10.0, 8, 1e-5, s.kp, " V/MHz")
        self.ki = spin(0.0, 10.0, 8, 1e-5, s.ki, " V/(MHz·s)")
        self.sign = QComboBox()
        self.sign.addItems(["+ (more V → higher f)", "− (more V → lower f)"])
        self.sign.setCurrentIndex(0 if s.sign >= 0 else 1)
        self.v_min = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_min, " V")
        self.v_max = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_max, " V")
        self.max_step = spin(0.0001, 1.0, 4, 0.001, s.max_step, " V")
        self.capture = spin(1.0, 1e6, 1, 100.0, s.capture_mhz, " MHz")
        gains = QGroupBox("Loop")
        f = QFormLayout(gains)
        f.addRow("P gain", self.kp)
        f.addRow("I gain", self.ki)
        f.addRow("Tuning sign", self.sign)
        f.addRow("Output min", self.v_min)
        f.addRow("Output max", self.v_max)
        f.addRow("Max step / update", self.max_step)
        f.addRow("Capture range ±", self.capture)
        for w in (self.kp, self.ki, self.v_min, self.v_max, self.max_step, self.capture):
            w.valueChanged.connect(self._push_settings)
        self.sign.currentIndexChanged.connect(self._push_settings)

        # output and actions
        self.manual = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.001, engine.snapshot().volts, " V")
        self.manual.valueChanged.connect(self._manual)
        self.lock_btn = QPushButton("Lock")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setMinimumHeight(40)
        self.lock_btn.toggled.connect(self._toggle_lock)
        self.cal_step = spin(0.001, 1.0, 4, 0.01, calibration["step_v"], " V")
        self.cal_settle = spin(0.1, 30.0, 1, 0.5, calibration["settle_s"], " s")
        self.cal_avg = spin(0.1, 30.0, 1, 0.5, calibration["average_s"], " s")
        self.cal_btn = QPushButton("Calibrate tuning")
        self.cal_btn.setToolTip("Steps the output by ± the step around its value, measures the frequency, "
                                "and sets the sign and gains from the slope.")
        self.cal_btn.clicked.connect(self._calibrate)
        self.log_box = QCheckBox("Log to CSV")
        self.log_box.toggled.connect(self._log)
        outbox = QGroupBox("Output (DG1022 DC offset, hard limit 0–7 V)")
        f = QFormLayout(outbox)
        f.addRow("Now", self.volt_label)
        f.addRow("Manual", self.manual)
        f.addRow(self.lock_btn)
        f.addRow("Cal. step ±", self.cal_step)
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

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(self.mode_label)
        lv.addWidget(readout)
        lv.addWidget(setbox)
        lv.addWidget(gains)
        lv.addWidget(outbox)
        lv.addWidget(swbox)
        lv.addWidget(self.message_label)
        lv.addStretch(1)

        # plots
        pg.setConfigOptions(antialias=True)
        self.span = QComboBox()
        self.span.addItems(list(SPANS))
        self.span.setCurrentText("2 min")
        plots = pg.GraphicsLayoutWidget()
        self.err_plot = plots.addPlot(row=0, col=0)
        self.err_plot.setLabel("left", "f − setpoint", units="Hz")
        self.err_plot.showGrid(x=True, y=True, alpha=0.3)
        self.err_curve = self.err_plot.plot(pen=pg.mkPen("#0969da", width=1.5))
        self.err_plot.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine))
        self.v_plot = plots.addPlot(row=1, col=0)
        self.v_plot.setLabel("left", "Output", units="V")
        self.v_plot.setLabel("bottom", "time", units="s")
        self.v_plot.showGrid(x=True, y=True, alpha=0.3)
        self.v_plot.setXLink(self.err_plot)
        self.v_curve = self.v_plot.plot(pen=pg.mkPen("#bf3989", width=1.5))
        self.sw_plot = plots.addPlot(row=0, col=1, rowspan=2)
        self.sw_plot.setLabel("left", "f − setpoint", units="Hz")
        self.sw_plot.setLabel("bottom", "output", units="V")
        self.sw_plot.setTitle("Sweep")
        self.sw_plot.showGrid(x=True, y=True, alpha=0.3)
        self.sw_curve = self.sw_plot.plot(pen=pg.mkPen("#8250df", width=1), symbol="o", symbolSize=4,
                                          symbolBrush="#8250df", symbolPen=None)
        self.sw_plot.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine))
        self.sw_choice = pg.InfiniteLine(angle=90, pen=pg.mkPen("#1a7f37", width=2))
        self.sw_range = pg.LinearRegionItem(movable=False, brush=(26, 127, 55, 40))
        for item in (self.sw_choice, self.sw_range):
            item.setVisible(False)
            self.sw_plot.addItem(item)
        self._sweep_n = -1
        right = QWidget()
        rv = QVBoxLayout(right)
        top = QHBoxLayout()
        top.addWidget(QLabel("Show"))
        top.addWidget(self.span)
        top.addStretch(1)
        self.rms_label = QLabel("")
        top.addWidget(self.rms_label)
        rv.addLayout(top)
        rv.addWidget(plots)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.resize(1300, 820)

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
                       ki=self.ki.value(), sign=1 if self.sign.currentIndex() == 0 else -1,
                       v_min=self.v_min.value(), v_max=max(self.v_max.value(), self.v_min.value()),
                       max_step=self.max_step.value(), capture_mhz=self.capture.value())

    def _push_settings(self) -> None:
        self.engine.update_settings(self._current_settings())

    def _thz_changed(self, thz: float) -> None:
        self.set_nm.blockSignals(True)
        self.set_nm.setValue(thz_to_nm(thz) if thz > 0 else 0.0)
        self.set_nm.blockSignals(False)
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

        setpoint = self.set_thz.value()
        for smp in self.engine.drain():
            if smp.thz is not None:
                ref = setpoint if setpoint > 0 else smp.thz
                self._data.append((smp.t - self._t0, (smp.thz - ref) * 1e12, smp.volts, float(smp.locked)))
        if self._data:
            arr = np.asarray(self._data)
            now = time.time() - self._t0
            keep = arr[:, 0] >= now - SPANS[self.span.currentText()]
            arr = arr[keep]
            self.err_curve.setData(arr[:, 0], arr[:, 1])
            self.v_curve.setData(arr[:, 0], arr[:, 2])
            locked_part = arr[arr[:, 3] > 0, 1]
            if setpoint > 0 and locked_part.size > 2:
                self.rms_label.setText(f"locked: rms {np.sqrt(np.mean(locked_part ** 2)) / 1e6:.2f} MHz, "
                                       f"mean {np.mean(locked_part) / 1e6:+.2f} MHz over the shown span")
            else:
                self.rms_label.setText("")

    def _show_settings(self) -> None:
        """The engine changed the settings (calibration, auto-lock): show them without sending them back."""
        s = self.engine.settings()
        for w, v in ((self.kp, s.kp), (self.ki, s.ki), (self.v_min, s.v_min), (self.v_max, s.v_max),
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
