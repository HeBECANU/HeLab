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
from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox,
                             QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                             QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget,
                             QTableWidgetItem, QToolButton, QVBoxLayout, QWidget, QMenu)

from .controller import LockSettings, nm_to_thz, thz_to_nm
from .devices import HARD_V_MAX, HARD_V_MIN
from .quality import Quality, classify
from .engine import Engine, HopEvent, ScanRequest, ScanResult, Stretch, sweep_hops

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


_MONO: QFont | None = None


def mono() -> QFont:
    """The font for numbers (digits line up as they change)."""
    global _MONO
    if _MONO is None:
        _MONO = QFont("Consolas")
        _MONO.setStyleHint(QFont.StyleHint.Monospace)
    return QFont(_MONO)


def mono_label(label: QLabel, size: float | None = None, bold: bool = False) -> QLabel:
    f = mono()
    if size:
        f.setPointSizeF(size)
    f.setBold(bold)
    label.setFont(f)
    return label


def set_text(label: QLabel, text: str) -> None:
    """Sets a label's text only when it changed (each change repaints it)."""
    if label.text() != text:
        label.setText(text)


def light_grid(plot: Any) -> None:
    """A light-grey grid: labelled major lines about every 60 px and fainter minor ones between them.
    (pyqtgraph's showGrid at its default density cost about 40 % of a core at 5 redraws a second, 2026-11-11;
    this draws far fewer lines.)"""
    for side in ("left", "bottom"):
        axis = plot.getAxis(side)
        axis.setTickPen(pg.mkPen("#dfe2e5"))
        axis.setTextPen(pg.mkPen("k"))
        axis.setPen(pg.mkPen("#888"))
        axis.setGrid(255)
        axis.setTickDensity(1.6)
        axis.setStyle(maxTickLevel=0, tickFont=mono(), tickLength=-6)
        axis.setZValue(-1000)  # the grid under the traces: opaque lines drawn over them hid a trace lying on one


HOP_COLOUR = "#cf222e"
HOP_LINES_MAX = 30
FOLLOW_S = 20.0  # the error axis's auto range fits the newest this many seconds  # hop lines per time plot: the newest in the shown span (dots show all of them)
HOP_PEN = pg.mkPen(HOP_COLOUR, width=1, style=Qt.PenStyle.DashLine)


PLOT_POINTS_MAX = 8000  # a longer shown span is thinned to each bin's extremes before plotting


def minmax_bins(bins: int, columns: tuple[np.ndarray, ...], flags: tuple[np.ndarray, ...]
                ) -> tuple[np.ndarray, ...]:
    """Indices that keep, in `bins` equal bins, each column's smallest and largest value (in time order), so a
    thinned trace keeps its spikes; and each flag, true for a kept index when any reading in its bin was."""
    n = len(columns[0])
    k = max(n // bins, 1)
    m = (n // k) * k
    base = np.arange(0, m, k)[:, None]
    picks = [base[:, 0]]
    for c in columns:
        block = c[:m].reshape(-1, k)
        picks += [base[:, 0] + block.argmin(axis=1), base[:, 0] + block.argmax(axis=1)]
    head = np.sort(np.stack(picks, axis=1), axis=1)  # each bin's picks, in time order
    idx = np.concatenate([head.ravel(), np.arange(m, n)])
    out_flags = []
    for f in flags:
        per_bin = f[:m].reshape(-1, k).any(axis=1)
        out_flags.append(np.concatenate([np.repeat(per_bin, head.shape[1]), f[m:]]))
    return (idx, *out_flags)


REDRAW_HZ = {"1 Hz": 1.0, "2 Hz": 2.0, "5 Hz": 5.0}
SPANS: dict[str, float | None] = {"30 s": 30.0, "2 min": 120.0, "10 min": 600.0, "1 h": 3600.0, "All": None}
ERR_COLOUR, OUT_COLOUR = "#0969da", "#24292f"
FLICKER_COLOUR, JUMP_COLOUR = "#e8590c", "#cf222e"
LOCKED_BAND = (226, 242, 230)  # light green behind locked stretches (opaque: cheaper to draw)
LOST_PEN = pg.mkPen("#cf222e", width=1.5, style=Qt.PenStyle.DotLine)
LOCK_MARKS_MAX = 40
MODE_COLOURS = {"idle": "#666", "locked": "#1a7f37", "calibrating": "#9a6700", "sweeping": "#9a6700",
                "fault": "#cf222e"}


def digit_step(box: Any, steps: int) -> bool:
    """Steps the digit just left of the text cursor (the units digit when it is at the decimal point), and
    keeps the cursor on that digit. False: no digit to step (the caller steps normally)."""
    le = box.lineEdit()
    text, pos = le.text(), le.cursorPosition()
    pre, suf = len(box.prefix()), len(box.suffix())
    num = text[pre:len(text) - suf]
    point = box.locale().decimalPoint() if isinstance(box, QDoubleSpinBox) else "."
    d = num.find(point)
    d = len(num) if d < 0 else d
    i = min(max(pos - pre, 0), len(num)) - 1
    while i >= 0 and not num[i].isdigit():  # at the point, a sign or a space: the digit further left
        i -= 1
    if i < 0:
        i = next((k for k, c in enumerate(num) if c.isdigit()), -1)
        if i < 0:
            return False
    power = (d - i - 1) if i < d else -(i - d)
    from_point = (i + 1) - d  # the cursor's place relative to the point, kept after the change
    if isinstance(box, QDoubleSpinBox):
        box.setValue(box.value() + steps * 10.0 ** power)
    else:
        box.setValue(int(box.value() + steps * 10 ** max(power, 0)))
    text = le.text()
    num = text[pre:len(text) - suf]
    d = num.find(point)
    d = len(num) if d < 0 else d
    le.setCursorPosition(min(max(pre + d + from_point, pre), len(text) - suf))
    return True


class Spin(QDoubleSpinBox):
    """A number box the mouse wheel never changes (the wheel scrolls the panel), whose arrow keys step the digit
    left of the cursor while it is being edited."""

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: Any) -> None:
        e.ignore()

    def stepBy(self, steps: int) -> None:
        if not (self.lineEdit().hasFocus() and digit_step(self, steps)):
            super().stepBy(steps)


class IntSpin(QSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setFont(mono())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: Any) -> None:
        e.ignore()

    def stepBy(self, steps: int) -> None:
        if not (self.lineEdit().hasFocus() and digit_step(self, steps)):
            super().stepBy(steps)


class Combo(QComboBox):
    """A drop-down the mouse wheel never changes."""

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: Any) -> None:
        e.ignore()


def spin(lo: float, hi: float, decimals: int, step: float, value: float, suffix: str = "") -> QDoubleSpinBox:
    s = Spin()
    s.setFont(mono())
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
        want = span / max(size / 70.0, 1.0)  # about one label per 70 px
        k = next((i for i, s in enumerate(self.STEPS) if s >= want), len(self.STEPS) - 1)
        major = self.STEPS[k]
        minor = next((m for m in reversed(self.STEPS[:k]) if major / m in (2, 3, 4, 5, 6) and major / m * 12 <= size / 4),
                     None)  # a step that divides the major one, at least ~12 px apart
        return [(float(major), 0.0)] + ([(float(minor), 0.0)] if minor else [])

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
    """A y range: auto, or fixed between two values (in `unit`; the data are `scale` times that), for one or
    more views (a plot, or a plot's second y axis) showing the same quantity; `current` is the one shown.
    Zooming the y axis with the mouse switches to fixed and shows the range; the plot's own "A" button is
    followed too."""

    def __init__(self, views: list[Any], scale: float, unit: str, lo: float, hi: float, decimals: int = 3,
                 state: dict[str, Any] | None = None, follow: bool = False,
                 presets: list[tuple[str, float, float]] | None = None) -> None:
        super().__init__()
        self.views = [v if isinstance(v, pg.ViewBox) else v.getViewBox() for v in views]
        self.scale, self.current = scale, 0
        self.follow = follow  # auto is set by the window (fit()) instead of pyqtgraph
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
        to = QLabel("to")
        to.setToolTip("The y range while auto is off: from the left box to the right one")
        h.addWidget(to)
        h.addWidget(self.hi)
        self.preset_buttons: list[QPushButton] = []
        for label, p_lo, p_hi in presets or []:
            b = QPushButton(label)
            b.setToolTip(f"y from {p_lo:g} to {p_hi:g} {unit}")
            b.setMaximumWidth(max(44, 9 * len(label) + 16))
            b.clicked.connect(self._preset_clicked)
            b.setProperty("range", (p_lo, p_hi))
            h.addWidget(b)
            self.preset_buttons.append(b)
        for vb in self.views:
            vb.sigRangeChangedManually.connect(self._mouse)
        self._apply()

    def _preset_clicked(self) -> None:
        b = self.sender()
        if isinstance(b, QPushButton):
            lo, hi = b.property("range")
            self.set_fixed(lo, hi)

    def set_fixed(self, lo: float, hi: float) -> None:
        for w, v in ((self.lo, lo), (self.hi, hi)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        if self.auto.isChecked():
            self.auto.setChecked(False)  # applies
        else:
            self._apply()

    def _typed(self) -> None:
        if self.auto.isChecked():
            self.auto.setChecked(False)  # applies
        else:
            self._apply()

    def _apply(self) -> None:
        for vb in self.views:
            if self.auto.isChecked():
                if self.follow:
                    vb.disableAutoRange(axis=pg.ViewBox.YAxis)
                else:
                    vb.enableAutoRange(y=True)
            else:
                lo, hi = sorted((self.lo.value(), self.hi.value()))
                if hi == lo:
                    hi = lo + 10 ** -self.lo.decimals()
                vb.setYRange(lo * self.scale, hi * self.scale, padding=0)

    def _mouse(self, mask: Any) -> None:
        if mask is not None and len(mask) > 1 and not mask[1]:
            return
        lo, hi = self.views[self.current].viewRange()[1]
        for w, v in ((self.lo, lo), (self.hi, hi)):
            w.blockSignals(True)
            w.setValue(v / self.scale)
            w.blockSignals(False)
        self.auto.blockSignals(True)
        self.auto.setChecked(False)
        self.auto.blockSignals(False)
        self._apply()  # the other views follow

    def sync(self) -> None:
        """Follows the shown plot's own auto-range button."""
        auto = bool(self.views[self.current].state["autoRange"][1])
        if self.follow:
            if auto:  # its "A" button: auto, done here
                self.views[self.current].disableAutoRange(axis=pg.ViewBox.YAxis)
                if not self.auto.isChecked():
                    self.auto.setChecked(True)
            return
        if auto != self.auto.isChecked():
            self.auto.setChecked(auto)  # applies to the others too

    def fit(self, values: Any) -> None:
        """Auto with `follow`: the shown view's range from these values (the newest readings)."""
        if not (self.follow and self.auto.isChecked()) or len(values) == 0:
            return
        lo, hi = float(np.min(values)), float(np.max(values))
        pad = max((hi - lo) * 0.08, 1e-9 * self.scale, abs(hi) * 1e-12)
        self.views[self.current].setYRange(lo - pad, hi + pad, padding=0)

    def state(self) -> dict[str, Any]:
        return {"auto": self.auto.isChecked(), "lo": self.lo.value(), "hi": self.hi.value()}


STYLE = """
QFrame#header { background: #f6f8fa; border-bottom: 1px solid #d0d7de; }
QLabel#caption { color: #57606a; font-size: 8pt; }
QLabel#reading { font-size: 17pt; font-weight: 600; font-family: Consolas, "Cascadia Mono", monospace; }
QLabel#mode { font-size: 15pt; font-weight: 700; color: white; border-radius: 6px; padding: 8px 14px; }
QLabel#message { color: #57606a; }
QPushButton#lockButton { font-size: 14pt; font-weight: 700; padding: 6px 18px; }
QPushButton#lockButton:checked { background: #1a7f37; color: white; border: 1px solid #116329; border-radius: 4px; }
QPushButton#primary { font-weight: 600; }
QPushButton#inputsLock { padding: 6px 12px; }
QPushButton#inputsLock:checked { background: #fff8c5; color: #4d2d00; border: 1px solid #d4a72c; border-radius: 4px;
                                 font-weight: 600; }
QFrame#section { background: white; border: 1px solid #d0d7de; border-radius: 6px; }
QFrame#section QLabel { background: transparent; }
QToolButton#sectionHeader { border: none; font-weight: 600; font-size: 10pt; padding: 5px 4px; color: #24292f; }
QAbstractSpinBox[readOnly="true"] { background: #eef1f4; color: #57606a; }
QPushButton#pause:checked { background: #fff8c5; color: #4d2d00; border: 1px solid #d4a72c; border-radius: 4px;
                            font-weight: 600; padding: 3px 10px; }
QLabel#miniValue { font-size: 15pt; font-weight: 600; font-family: Consolas, "Cascadia Mono", monospace; }
"""


class Section(QFrame):
    """A titled panel whose body its header shows or hides; rows get a label and a tooltip."""

    def __init__(self, key: str, title: str, tip: str, collapsed: bool = False) -> None:
        super().__init__()
        self.key = key
        self.setObjectName("section")
        self.head = QToolButton()
        self.head.setObjectName("sectionHeader")
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setChecked(not collapsed)
        self.head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.head.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.head.setToolTip(f"{tip}. Click to show or hide.")
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(10, 0, 10, 8)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        lay.addWidget(self.head)
        lay.addWidget(self.body)
        self.head.toggled.connect(self._toggled)
        self._toggled(self.head.isChecked())

    def _toggled(self, shown: bool) -> None:
        self.body.setVisible(shown)
        self.head.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

    @property
    def collapsed(self) -> bool:
        return not self.head.isChecked()

    def row(self, label: str, widget: QWidget, tip: str) -> None:
        lab = QLabel(label)
        lab.setToolTip(tip)
        if not widget.toolTip():
            widget.setToolTip(tip)
        for child in widget.findChildren(QWidget):
            if not child.toolTip():
                child.setToolTip(tip)
        self.form.addRow(lab, widget)

    def full(self, widget: QWidget) -> None:
        self.form.addRow(widget)


class HoverSlot:
    """A plot widget's mouse-move slot: hands the position to the window with that widget's plots."""

    def __init__(self, window: Any, plots: list[Any]) -> None:
        self.window, self.plots = window, plots

    def __call__(self, args: Any) -> None:
        self.window._hovered(args[0], self.plots)


class PlotMenu:
    """Stands in for a ViewBox's raiseContextMenu: shows the window's own menu."""

    def __init__(self, window: Any, vb: Any) -> None:
        self.window, self.vb = window, vb

    def __call__(self, ev: Any) -> None:
        self.window._plot_menu(self.vb, ev)
        ev.accept()


class MiniWindow(QWidget):
    """A small always-on-top window: the lock's state, error and output, and a button back to the full one."""

    def __init__(self, main: Any) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.main = main
        self.setWindowTitle("Laser lock")
        self.mode = QLabel("IDLE")
        self.mode.setObjectName("mode")
        self.mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode.setMinimumWidth(150)
        self.mode.setToolTip("What the lock is doing (as in the full window)")
        self.error, self.output = QLabel("—"), QLabel("—")
        self.error.setToolTip("Frequency − setpoint")
        self.output.setToolTip("The DG1022 output now")
        for lab in (self.error, self.output):
            lab.setObjectName("miniValue")
            lab.setMinimumWidth(150)
            lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.expand = QPushButton("Full")
        self.expand.setToolTip("Back to the full window")
        self.expand.setMaximumWidth(60)
        self.expand.clicked.connect(main.show_full)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.addWidget(self.mode)
        h.addWidget(self.error)
        h.addWidget(self.output)
        h.addWidget(self.expand)
        self.setStyleSheet(STYLE)

    def show_state(self, mode: str, colour: str, error: str, output: str) -> None:
        if self.mode.text() != mode:
            self.mode.setText(mode)
        self.mode.setStyleSheet(f"background: {colour}; font-size: 12pt; padding: 5px 10px")
        self.error.setText(error)
        self.output.setText(output)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.main.show_full()  # closing the small window brings the full one back
        if event is not None:
            event.ignore()


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
        self._mode_colour = ""
        self._last_draw = 0.0

        ui = {"show_plots": True, "show_sweep": True, "span": "2 min", "clock": True, "combined": False,
              "line_width": 1.0, "hop_lines": False, "collapsed": [], "inputs_locked": False, **(ui or {})}
        collapsed = set(ui.get("collapsed") or [])
        self._guarded: list[QWidget] = []  # what the input lock freezes

        # ---- the header: state, readings, Lock, input lock
        self.mode_label = QLabel("idle")
        self.mode_label.setObjectName("mode")
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setMinimumWidth(170)
        self.mode_label.setToolTip("What the lock is doing: idle, locked (with why if it is holding: out of "
                                   "capture, limited, no reading), calibrating, sweeping, LOCK LOST, or fault "
                                   "(an instrument stopped answering)")
        self.freq_label, self.nm_label, self.err_label, self.volt_label = (QLabel("—") for _ in range(4))
        readings = QHBoxLayout()
        readings.setSpacing(36)
        for title, lab, tip in (
                ("Frequency", self.freq_label, "The wavemeter's latest reading of the laser (channel 1)"),
                ("Wavelength (vacuum)", self.nm_label, "The same reading as a vacuum wavelength"),
                ("Error", self.err_label, "Frequency − setpoint. While locked, the lock drives this to zero"),
                ("Output", self.volt_label, "The DG1022 CH1 DC offset now: what steers the laser (hard limit 0–7 V)")):
            lab.setObjectName("reading")
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            readings.addWidget(self._caption(title, lab, tip))
        readings.addStretch(1)
        self.lock_btn = QPushButton("Lock")
        self.lock_btn.setObjectName("lockButton")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setMinimumSize(130, 52)
        self.lock_btn.setToolTip("Lock: hold the laser at the setpoint, starting from the output now (no jump). "
                                 "Unlock: stop correcting and hold the output where it is.")
        self.lock_btn.toggled.connect(self._toggle_lock)
        self.inputs_lock = QPushButton()
        self.inputs_lock.setObjectName("inputsLock")
        self.inputs_lock.setCheckable(True)
        self.inputs_lock.setChecked(bool(ui["inputs_locked"]))
        self.inputs_lock.setMinimumHeight(52)
        self.inputs_lock.setToolTip("Lock the inputs against accidental clicks, keys or typing: number boxes "
                                    "become read-only, lists, ticks and action buttons are disabled (Abort stays "
                                    "available while something runs). The plots' view controls still work.")
        self.inputs_lock.toggled.connect(self._apply_input_lock)
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("message")
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message_label.setToolTip("The last thing the lock did or reported (also in logs/laserlock.log)")
        header = QFrame()
        header.setObjectName("header")
        hl = QGridLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.addWidget(self.mode_label, 0, 0)
        hl.addLayout(readings, 0, 1)
        hl.addWidget(self.lock_btn, 0, 2)
        hl.addWidget(self.inputs_lock, 0, 3)
        self.mini_btn = QPushButton("Mini window")
        self.mini_btn.setMinimumHeight(52)
        self.mini_btn.setToolTip("Swap to a small always-on-top window with just the state, error and output "
                                 "(the lock keeps running; Full there brings this window back)")
        self.mini_btn.clicked.connect(self.show_mini)
        hl.addWidget(self.mini_btn, 0, 4)
        self.retry_btn = QPushButton("Retry instruments")
        self.retry_btn.setMinimumHeight(52)
        self.retry_btn.setToolTip("After a fault (an instrument stopped answering): ask the wavemeter and the DG1022 "
                                  "again; if both answer, the lock is back to idle with the output read back. A hung "
                                  "DG1022 needs a power cycle first")
        self.retry_btn.clicked.connect(self.engine.retry)
        self.retry_btn.setVisible(False)
        hl.addWidget(self.retry_btn, 0, 5)
        hl.addWidget(self.message_label, 1, 0, 1, 6)
        self.mini = MiniWindow(self)
        hl.setColumnStretch(1, 1)
        self.header = header

        # ---- Setpoint
        self.set_thz = spin(0.0, 2000.0, 9, 1e-6, s.setpoint_thz, " THz")
        self.set_nm = spin(0.0, 1e6, 8, 1e-6, thz_to_nm(s.setpoint_thz) if s.setpoint_thz > 0 else 0.0, " nm")
        self.set_thz.valueChanged.connect(self._thz_changed)
        self.set_nm.valueChanged.connect(self._nm_changed)
        use_now = QPushButton("Use current")
        use_now.setToolTip("Make the wavemeter's reading now the setpoint")
        use_now.clicked.connect(self._use_current)
        self._presets: list[dict[str, Any]] = [dict(e) for e in (presets or []) if preset_thz(e)]
        self.preset_box = Combo()
        self.preset_box.activated.connect(self._preset_chosen)
        add_preset, del_preset = QPushButton("Save"), QPushButton("Remove")
        add_preset.setToolTip("Add the setpoint below to the saved setpoints (kept in config.local.json)")
        del_preset.setToolTip("Remove the chosen saved setpoint")
        add_preset.clicked.connect(self._add_preset)
        del_preset.clicked.connect(self._remove_preset)
        self._fill_presets()
        self.nudge = spin(0.001, 1e5, 3, 1.0, 10.0, " MHz")
        down, up = QPushButton("−"), QPushButton("+")
        down.setToolTip("Move the setpoint down by the nudge (also while locked)")
        up.setToolTip("Move the setpoint up by the nudge (also while locked)")
        for b in (down, up):
            b.setMaximumWidth(34)
        down.clicked.connect(self._nudge_down)
        up.clicked.connect(self._nudge_up)
        nudge = QWidget()
        nh = QHBoxLayout(nudge)
        nh.setContentsMargins(0, 0, 0, 0)
        nh.addWidget(down)
        nh.addWidget(self.nudge, 1)
        nh.addWidget(up)
        sec_set = Section("setpoint", "Setpoint", "The frequency the lock holds the laser at", "setpoint" in collapsed)
        sec_set.row("Saved", self._pair(self.preset_box, add_preset, del_preset, stretch=0),
                    "Saved setpoints, as frequency and vacuum wavelength; choosing one makes it the setpoint")
        sec_set.row("Frequency", self.set_thz, "The setpoint in THz (9 decimals: 1 kHz). ↑/↓ step the digit left of "
                    "the cursor")
        sec_set.row("Wavelength", self.set_nm, "The setpoint as a vacuum wavelength (follows the frequency)")
        sec_set.row("Nudge", nudge, "How far − and + move the setpoint")
        sec_set.full(use_now)
        self._guarded += [self.set_thz, self.set_nm, self.preset_box, add_preset, del_preset, self.nudge, down, up,
                          use_now]

        # ---- Lock loop
        self.kp = spin(0.0, 10.0, 8, 1e-5, s.kp, " V/MHz")
        self.ki = spin(0.0, 10.0, 8, 1e-5, s.ki, " V/(MHz·s)")
        self.kd = spin(0.0, 10.0, 8, 1e-5, s.kd, " V/(MHz/s)")
        self.d_filter = spin(0.0, 60.0, 2, 0.1, s.d_filter_s, " s")
        self.sign = Combo()
        self.sign.addItems(["+ (more V → higher f)", "− (more V → lower f)"])
        self.sign.setCurrentIndex(0 if s.sign >= 0 else 1)
        sec_loop = Section("loop", "Lock loop", "The PID gains. Calibrate (below) or Find stable range set P, I and "
                           "the sign from the measured tuning", "loop" in collapsed)
        sec_loop.row("P gain", self.kp, "Proportional: volts per MHz of error, applied at once")
        sec_loop.row("I gain", self.ki, "Integral: volts per MHz of error per second; removes a steady error")
        sec_loop.row("D gain", self.kd, "Derivative: acts on the measured frequency's rate (no kick when the "
                     "setpoint changes); 0 is a PI lock. Calibrate leaves it alone")
        sec_loop.row("D filter", self.d_filter, "The D term's low-pass time constant (the wavemeter's noise "
                     "differentiates badly)")
        sec_loop.row("Tuning sign", self.sign, "Which way more voltage moves the laser's frequency")
        self._guarded += [self.kp, self.ki, self.kd, self.d_filter, self.sign]

        # ---- Calibrate
        self.cal_step = spin(-1.0, 1.0, 4, 0.01, calibration["step_v"], " V")
        self.cal_settle = spin(0.1, 30.0, 1, 0.5, calibration["settle_s"], " s")
        self.cal_avg = spin(0.1, 30.0, 1, 0.5, calibration["average_s"], " s")
        self.cal_btn = QPushButton("Calibrate tuning")
        self.cal_btn.setToolTip("Measure the frequency at the output now and at the output plus the step, "
                                "return, and set the sign and the P and I gains from the slope (unlocked only)")
        self.cal_btn.clicked.connect(self._calibrate)
        sec_cal = Section("calibrate", "Calibrate", "Measures the tuning slope (MHz/V) and sets the gains from it",
                          "calibrate" in collapsed)
        sec_cal.row("Step", self.cal_step, "The second point is the output now plus this step; negative steps down "
                    "(near the top limit, or with a mode hop just above). It moves the laser by slope × step: keep "
                    "it small enough not to hop")
        sec_cal.row("Settle", self.cal_settle, "Wait this long after each step before averaging")
        sec_cal.row("Average", self.cal_avg, "Average the frequency for this long at each point")
        sec_cal.full(self.cal_btn)
        self._guarded += [self.cal_step, self.cal_settle, self.cal_avg]

        # ---- Limits and safety
        self.v_min = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_min, " V")
        self.v_max = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.1, s.v_max, " V")
        self.max_step = spin(0.0001, 1.0, 4, 0.001, s.max_step, " V")
        self.capture = spin(1.0, 1e6, 1, 100.0, s.capture_mhz, " MHz")
        self.lost_after = spin(0.1, 600.0, 1, 0.5, s.lost_after_s, " s")
        self.hop_mhz = spin(10.0, 1e6, 0, 100.0, engine.hops.min_jump_mhz, " MHz")
        self.hop_mhz.valueChanged.connect(self.engine.set_hop_threshold)
        sec_lim = Section("limits", "Limits and safety", "What the lock may do, and when it gives up",
                          "limits" in collapsed)
        sec_lim.row("Output min", self.v_min, "The lock never sets the output below this (inside the hard 0–7 V)")
        sec_lim.row("Output max", self.v_max, "The lock never sets the output above this (inside the hard 0–7 V)")
        sec_lim.row("Max step", self.max_step, "The most the output may move per update (one wavemeter reading)")
        sec_lim.row("Capture ±", self.capture, "A reading further than this from the setpoint holds the output "
                    "(it doesn't chase a far reading or another mode)")
        sec_lim.row("Lost after", self.lost_after, "Out of the capture range this long, or a mode hop out of it, and "
                    "the lock is lost: it lets go, holds the output, and says LOCK LOST")
        sec_lim.row("Mode hop ≥", self.hop_mhz, "A jump at least this big that holds for 3 readings and 0.2 s counts "
                    "as a mode hop (red dots on the output plot)")
        for w in (self.kp, self.ki, self.kd, self.d_filter, self.v_min, self.v_max, self.max_step, self.capture,
                  self.lost_after):
            w.valueChanged.connect(self._push_settings)
        self.sign.currentIndexChanged.connect(self._push_settings)
        self._guarded += [self.v_min, self.v_max, self.max_step, self.capture, self.lost_after, self.hop_mhz]

        # ---- Output
        self.manual = spin(HARD_V_MIN, HARD_V_MAX, 4, 0.001, engine.snapshot().volts, " V")
        self.manual.valueChanged.connect(self._manual)
        self.log_box = QCheckBox("Log readings to CSV")
        self.log_box.setToolTip("Write every reading (time, frequency, error, output, locked, hop) to "
                                "logs/laserlock-<date>-<time>.csv while ticked")
        self.log_box.toggled.connect(self._log)
        sec_out = Section("output", "Output", "The DG1022 CH1 DC offset (hard limit 0–7 V)", "output" in collapsed)
        sec_out.row("Manual", self.manual, "Set the output by hand (unlocked only); it goes out at most every 100 ms")
        sec_out.full(self.log_box)
        self._guarded += [self.manual, self.log_box]

        # ---- Wavemeter
        self.status_label = mono_label(QLabel(""))
        self.status_label.setToolTip("The wavemeter's state and how often a new reading comes (the lock's rate)")
        self.hop_label = mono_label(QLabel("Mode hops: none"))
        self.hop_label.setToolTip("Mode hops seen since start: the count, and the last one's jump, time and output")
        self.wm_exposure = IntSpin()
        self.wm_exposure.setRange(1, 9999)
        self.wm_exposure.setSuffix(" ms")
        self.wm_exposure.setKeyboardTracking(False)
        self.wm_auto = QCheckBox("auto")
        self.wm_auto.setToolTip("The wavemeter picks the exposure itself from the signal")
        self.wm_interval = IntSpin()
        self.wm_interval.setRange(1, 100_000)
        self.wm_interval.setSuffix(" ms")
        self.wm_interval.setKeyboardTracking(False)
        self.wm_interval_on = QCheckBox("on")
        self.wm_interval_on.setToolTip("Measure once per interval (off: as fast as the exposure allows)")
        self.wm_exposure.valueChanged.connect(self._wm_exposure)
        self.wm_auto.toggled.connect(self._wm_auto)
        self.wm_interval.valueChanged.connect(self._wm_interval)
        self.wm_interval_on.toggled.connect(self._wm_interval_on)
        self._wm_widgets = (self.wm_exposure, self.wm_auto, self.wm_interval, self.wm_interval_on)
        self._wm_seen = False
        for w in self._wm_widgets:
            w.setEnabled(False)  # until the timing has been read
        sec_wm = Section("wavemeter", "Wavemeter", "The HighFinesse WS8's state and timing (its server's own "
                         "settings: changing them here changes them in the WLM program too)", "wavemeter" in collapsed)
        sec_wm.full(self.status_label)
        sec_wm.full(self.hop_label)
        self.wm_exposure.setFont(mono())
        sec_wm.row("Exposure", self._pair(self.wm_exposure, self.wm_auto), "The exposure (CCD 1); setting one turns "
                   "auto off")
        sec_wm.row("Measure every", self._pair(self.wm_interval, self.wm_interval_on), "With on, one measurement per "
                   "interval: sets the lock's sample rate")
        self._guarded += list(self._wm_widgets)

        # ---- Sweep and find stable range
        sw = {"v_start": 0.0, "v_stop": 7.0, "step": 0.05, "settle_s": 0.1, "dwell_s": 0.2, **(sweep or {})}
        self.sw_start = spin(HARD_V_MIN, HARD_V_MAX, 3, 0.1, sw["v_start"], " V")
        self.sw_stop = spin(HARD_V_MIN, HARD_V_MAX, 3, 0.1, sw["v_stop"], " V")
        self.sw_step = spin(0.001, 1.0, 3, 0.01, sw["step"], " V")
        self.sw_settle = spin(0.0, 5.0, 2, 0.05, sw["settle_s"], " s")
        self.sw_dwell = spin(0.05, 5.0, 2, 0.05, sw["dwell_s"], " s")
        self.sweep_btn = QPushButton("Sweep")
        self.sweep_btn.setToolTip("Step the output From → To, plot the frequency at each step, then return")
        self.sweep_btn.clicked.connect(self._sweep_only)
        self.auto_btn = QPushButton("Auto-lock")
        self.auto_btn.setToolTip("Sweep, then go to where the setpoint is crossed without a mode hop (the crossing "
                                 "with the most room), from the sweep's start side, set the gains from the local "
                                 "slope, keep the output in that stretch, and lock")
        self.auto_btn.clicked.connect(self._auto_lock)
        self.scan_margin = spin(0.0, 3.5, 2, 0.05, float(sw.get("margin_v", 0.3)), " V")
        self.scan_hold = spin(0.0, 600.0, 1, 1.0, float(sw.get("hold_s", 5.0)), " s")
        self.scan_btn = QPushButton("Find stable range → lock")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setToolTip("Sweep From → To → From and find the output ranges that are mode-hop free both "
                                 "ways. If the setpoint is in one with the margin to spare: go there from below, "
                                 "hold, and lock if no hop comes. Otherwise return and list the stable ranges with "
                                 "the laser shift each needs (tune the hardware, then press again)")
        self.scan_btn.clicked.connect(self._find_stable)
        self.relock = QCheckBox("On LOCK LOST: find stable range → relock")
        self.relock.setChecked(bool(sw.get("relock", False)))
        self.relock.setToolTip("When the lock is lost, run Find stable range with these settings and relock if the "
                               "setpoint is in a stable stretch (once per loss). It sweeps the whole range")
        self.relock.toggled.connect(self._push_relock)
        self.scan_table = QTableWidget(0, 5)
        self.scan_table.setHorizontalHeaderLabels(["Output", "Setpoint", "Width", "Tuning", "Frequency (THz)"])
        self.scan_table.setToolTip("The last scan's mode-hop-free stretches, widest first. Setpoint: where it "
                                   "falls, or how far to shift the laser (hardware: + raises its frequency) to "
                                   "centre the setpoint there")
        self.scan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.scan_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.scan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scan_table.verticalHeader().setVisible(False)
        self.scan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.scan_table.setMinimumHeight(110)
        self.scan_table.setFont(mono())
        self.scan_table.itemSelectionChanged.connect(self._scan_selected)
        self.stretch_btn = QPushButton("Lock at selected stretch")
        self.stretch_btn.setToolTip("Go to the chosen stretch's centre (from below), make the frequency there the "
                                    "setpoint, and lock with the output kept inside the stretch")
        self.stretch_btn.clicked.connect(self._lock_selected)
        self.stretch_btn.setEnabled(False)
        self._stretches: list[Stretch] = []
        self._scan_shown = -1
        sec_sw = Section("sweep", "Sweep and find stable range", "Sweeps the output to map the laser's tuning and "
                         "its mode hops, and finds where it can lock", "sweep" in collapsed)
        sec_sw.row("From / to", self._pair(self.sw_start, self.sw_stop), "The output range swept")
        sec_sw.row("Step", self.sw_step, "The output step between points")
        sec_sw.row("Settle / dwell", self._pair(self.sw_settle, self.sw_dwell), "At each point: wait (settle), then "
                   "read the frequency (dwell)")
        sec_sw.full(self._pair(self.sweep_btn, self.auto_btn))
        sec_sw.row("Margin / hold", self._pair(self.scan_margin, self.scan_hold), "Find stable range: the setpoint "
                   "must be at least the margin from its stretch's ends, and the laser must hold there this long "
                   "without a hop before it locks")
        sec_sw.full(self.scan_btn)
        sec_sw.full(self.relock)
        sec_sw.full(self.scan_table)
        sec_sw.full(self.stretch_btn)
        self._guarded += [self.sw_start, self.sw_stop, self.sw_step, self.sw_settle, self.sw_dwell, self.scan_margin,
                          self.scan_hold, self.relock]
        self.sections = [sec_set, sec_loop, sec_cal, sec_lim, sec_out, sec_wm, sec_sw]

        self.show_plots = QCheckBox("Time plots")
        self.show_sweep = QCheckBox("Sweep plot")
        self.show_plots.setToolTip("Show the error and output against time")
        self.show_sweep.setToolTip("Show the last sweep or scan (frequency against output)")
        self.show_plots.setChecked(bool(ui["show_plots"]))
        self.show_sweep.setChecked(bool(ui["show_sweep"]))
        self.show_plots.toggled.connect(self._plots_shown)
        self.show_sweep.toggled.connect(self._plots_shown)

        left_inner = QWidget()
        lv = QVBoxLayout(left_inner)
        lv.setContentsMargins(6, 6, 6, 6)
        lv.setSpacing(6)
        for sec in self.sections:
            lv.addWidget(sec)
        lv.addStretch(1)
        left = QScrollArea()  # the controls scroll on a short screen
        left.setWidget(left_inner)
        left.setWidgetResizable(True)
        left.setFrameShape(QFrame.Shape.NoFrame)
        left.setMinimumWidth(left_inner.sizeHint().width() + 24)

        # plots
        pg.setConfigOptions(antialias=False, background="w", foreground="k")  # antialiasing costs a lot of CPU
        self.span = Combo()
        self.span.addItems(list(SPANS))
        self.span.setCurrentText(str(ui["span"]) if ui["span"] in SPANS else "2 min")
        self.span.setToolTip("The time shown (it scrolls with the newest reading unless paused)")
        self.pause = QPushButton("⏸ Pause")
        self.pause.setObjectName("pause")
        self.pause.setCheckable(True)
        self.pause.toggled.connect(self._pause_toggled)
        self.pause.setToolTip("Freeze the time plots to pan and zoom with the mouse (readings keep being "
                              "recorded); dragging the time axis pauses too")
        self.time_kind = Combo()
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
        self.err_curve = self.err_plot.plot(pen=pg.mkPen(ERR_COLOUR, width=1))
        self.err_plot.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine)).setZValue(-10)  # under the trace
        self.v_plot = plots.addPlot(row=1, col=0, axisItems={"bottom": self._time_axes[1]})
        self.v_plot.setLabel("left", "Output", units="V")
        light_grid(self.v_plot)
        self.v_plot.setXLink(self.err_plot)
        for plot in (self.err_plot, self.v_plot):
            plot.getViewBox().sigRangeChangedManually.connect(self._time_dragged)
            plot.getAxis("left").setWidth(72)  # equal widths: linked time axes line up and don't shift
        self._time_kind()
        self.v_curve = self.v_plot.plot(pen=pg.mkPen(OUT_COLOUR, width=1))
        self.hop_dots = self.v_plot.plot(pen=None, symbol="o", symbolSize=9, symbolBrush=HOP_COLOUR, symbolPen=None)
        self._hop_pool: list[tuple[Any, Any]] = []  # (error-plot line, output-plot line), reused
        self._hops_drawn = (0, 0.0)  # (count, when)
        # the same two on one plot: error on the left axis, output on the right
        self.comb_widget = pg.GraphicsLayoutWidget()
        self._time_axes.append(TimeAxis(self._t0, self._start))
        self.comb = self.comb_widget.addPlot(axisItems={"bottom": self._time_axes[2]})
        self.comb.setLabel("left", "f − setpoint", units="Hz", color=ERR_COLOUR)
        light_grid(self.comb)
        self.comb.addLine(y=0, pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine)).setZValue(-10)
        self.comb_vb = pg.ViewBox()
        self.comb.showAxis("right")
        self.comb.scene().addItem(self.comb_vb)
        right_axis = self.comb.getAxis("right")
        right_axis.linkToView(self.comb_vb)
        right_axis.setLabel("Output", units="V", color=OUT_COLOUR)
        right_axis.setPen(pg.mkPen("#888"))
        right_axis.setTextPen(pg.mkPen("k"))
        right_axis.setZValue(-1000)
        self.comb_vb.setXLink(self.comb)
        self.comb.getViewBox().sigResized.connect(self._comb_geometry)
        self.comb.getViewBox().sigRangeChangedManually.connect(self._time_dragged)
        self.c_err = self.comb.plot(pen=pg.mkPen(ERR_COLOUR, width=1))
        self.c_v = pg.PlotDataItem(pen=pg.mkPen(OUT_COLOUR, width=1))
        self.c_hops = pg.PlotDataItem(pen=None, symbol="o", symbolSize=9, symbolBrush=HOP_COLOUR, symbolPen=None)
        self.comb_vb.addItem(self.c_v)
        self.comb_vb.addItem(self.c_hops)
        self._time_kind()
        for curve in (self.err_curve, self.v_curve, self.c_err, self.c_v):  # at most about one point per pixel
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)
            curve.setZValue(5)  # above the grid and the zero line
        # flicker (orange) and jumps (red) drawn over each trace: the same data, NaN where the reading is good
        self._marks: dict[Any, tuple[Any, Any]] = {}
        for curve, owner in ((self.err_curve, self.err_plot), (self.v_curve, self.v_plot), (self.c_err, self.comb),
                             (self.c_v, self.comb_vb)):
            pair = []
            for colour in (FLICKER_COLOUR, JUMP_COLOUR):
                item = pg.PlotDataItem(pen=pg.mkPen(colour, width=1.5), connect="finite")
                item.setClipToView(True)
                item.setZValue(6)
                owner.addItem(item)
                pair.append(item)
            self._marks[curve] = (pair[0], pair[1])
        self._quality: Quality | None = None
        # locked stretches (light green bands) and lost locks (dotted red lines), reused, per time plot
        self._lock_bands: dict[Any, list[Any]] = {p: [] for p in (self.err_plot, self.v_plot, self.comb)}
        self._lost_lines: dict[Any, list[Any]] = {p: [] for p in (self.err_plot, self.v_plot, self.comb)}
        self._quality_t = np.empty(0)
        sweep_plots = pg.GraphicsLayoutWidget()
        self.sw_plot = sweep_plots.addPlot()
        self.sw_plot.setLabel("left", "f − setpoint", units="Hz")
        self.sw_plot.setLabel("bottom", "output", units="V")
        self.sw_plot.setTitle("Sweep")
        light_grid(self.sw_plot)
        self.err_range = YRange([self.err_plot, self.comb], 1e6, "MHz", -50.0, 50.0, 3, ui.get("err_y"), follow=True,
                                presets=[(f"±{w:g}", -w, w) for w in (1, 10, 100, 1000)])
        self.err_range.auto.setToolTip(f"Fit the error axis to the newest {FOLLOW_S:.0f} s of readings, so it follows "
                                       "the laser (an older jump, e.g. a mode hop, scrolls off); untick to keep "
                                       "the range in the boxes")
        self.v_range = YRange([self.v_plot, self.comb_vb], 1.0, "V", HARD_V_MIN, HARD_V_MAX, 4, ui.get("v_y"),
                              presets=[("0–7 V", HARD_V_MIN, HARD_V_MAX)])
        self.sw_y = YRange([self.sw_plot], 1e6, "MHz", -5000.0, 5000.0, 1, ui.get("sweep_y"))
        # plot options
        self.layout_kind = Combo()
        self.layout_kind.addItems(["two plots", "one plot, two y axes"])
        self.layout_kind.setCurrentIndex(1 if ui["combined"] else 0)
        self.layout_kind.setToolTip("Error and output on separate plots, or on one (error left, output right)")
        self.layout_kind.currentIndexChanged.connect(self._layout_changed)
        self.line_width = spin(0.5, 5.0, 1, 0.5, float(ui["line_width"]), " px")
        self.line_width.setToolTip("The traces' line width (wider costs a little more to draw)")
        self.line_width.valueChanged.connect(self._pens)
        self.hop_lines = QCheckBox("Hop lines")
        self.hop_lines.setChecked(bool(ui["hop_lines"]))
        self.hop_lines.setToolTip("Also mark mode hops with vertical lines (the red dots on the output are always "
                                  "there)")
        self.hop_lines.toggled.connect(self._hop_lines_toggled)
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
        self.sw_down = self.sw_plot.plot(pen=pg.mkPen("#bc4c00", width=1), symbol="t", symbolSize=5,
                                         symbolBrush="#bc4c00", symbolPen=None)
        self._stretch_regions: list[Any] = []
        self.sw_plot.addLegend(offset=(10, 10))
        self.sw_plot.legend.addItem(self.sw_curve, "sweep / up")
        self.sw_plot.legend.addItem(self.sw_down, "down")
        right = self.right = QWidget()
        rv = QVBoxLayout(right)
        top = QHBoxLayout()
        top.addWidget(self._lab("Show", "Which plot panels to show"))
        top.addWidget(self.show_plots)
        top.addWidget(self.show_sweep)
        top.addSpacing(14)
        top.addWidget(self._lab("Span", "The time shown"))
        top.addWidget(self.span)
        top.addWidget(self.pause)
        top.addWidget(self._lab("Time", "How the time axis is labelled"))
        top.addWidget(self.time_kind)
        top.addWidget(clear)
        top.addWidget(self._lab("Redraw", "How often the time plots are redrawn: drawing is most of the window's CPU "
                                "(about 5 % of a core at 1 Hz, 9 % at 2 Hz, 18 % at 5 Hz on this PC). The readings "
                                "and the lock run at their own rate whatever this is"))
        self.redraw = Combo()
        self.redraw.addItems(list(REDRAW_HZ))
        self.redraw.setCurrentText(str(ui.get("redraw", "2 Hz")) if ui.get("redraw") in REDRAW_HZ else "2 Hz")
        self.redraw.setToolTip("How often the time plots are redrawn (lower: less CPU)")
        self.redraw.currentIndexChanged.connect(self._redraw_changed)
        top.addWidget(self.redraw)
        top.addStretch(1)
        self.rms_label = mono_label(QLabel(""))
        self.rms_label.setToolTip("The lock's quality over the shown span: rms and mean of the error while locked, "
                                  "leaving out readings beyond the capture range")
        top.addWidget(self.rms_label)
        yrow = QHBoxLayout()
        yrow.addWidget(self._lab("Error y", "The error axis: auto (the newest 20 s) or a fixed range"))
        yrow.addWidget(self.err_range)
        yrow.addSpacing(16)
        yrow.addWidget(self._lab("Output y", "The output axis: auto (the shown span) or a fixed range"))
        yrow.addWidget(self.v_range)
        yrow.addStretch(1)
        orow = QHBoxLayout()
        orow.addWidget(self._lab("Plot", "Error and output on two plots, or on one with two y axes"))
        orow.addWidget(self.layout_kind)
        orow.addWidget(self._lab("Line", "The traces' line width"))
        orow.addWidget(self.line_width)
        orow.addWidget(self.hop_lines)
        orow.addSpacing(14)
        orow.addWidget(self._lab("Flag", "Colour the traces: orange where the frequency flickers up and down, red at "
                                 "a sharp jump; the rest is normal. Judged against the trace's own step noise; these "
                                 "are the smallest steps that count"))
        self.flicker_min = spin(0.1, 1e5, 1, 1.0, float(ui.get("flicker_min_mhz", 5.0)), " MHz")
        self.flicker_min.setToolTip("Flicker: steps at least this big (and 6× the normal step noise) that reverse "
                                    "direction 3 times within 1 s. Shown orange")
        self.jump_min = spin(1.0, 1e6, 0, 10.0, float(ui.get("jump_min_mhz", 50.0)), " MHz")
        self.jump_min.setToolTip("Jump: one step at least this big (and 10× the normal step noise) that isn't part "
                                 "of flicker, e.g. a mode hop. Shown red")
        for w in (self.flicker_min, self.jump_min):
            w.setMaximumWidth(120)
            w.valueChanged.connect(self._draw_time_now)
        orow.addWidget(self._lab("flicker ≥", self.flicker_min.toolTip()))
        orow.addWidget(self.flicker_min)
        orow.addWidget(self._lab("jump ≥", self.jump_min.toolTip()))
        orow.addWidget(self.jump_min)
        self.quality_label = mono_label(QLabel(""))
        self.quality_label.setToolTip("Over the shown span: how many sharp jumps (red) and how long it flickered "
                                      "(orange)")
        orow.addWidget(self.quality_label)
        orow.addStretch(1)
        self.time_panel = QWidget()
        tv = QVBoxLayout(self.time_panel)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addLayout(yrow)
        tv.addLayout(orow)
        tv.addWidget(plots)
        tv.addWidget(self.comb_widget)
        self.sep_widget = plots
        self._layout_changed()
        self._pens()
        for vb in (self.err_plot.getViewBox(), self.v_plot.getViewBox(), self.comb.getViewBox(), self.comb_vb,
                   self.sw_plot.getViewBox()):
            vb.raiseContextMenu = PlotMenu(self, vb)
        for plot in (self.err_plot, self.v_plot, self.comb, self.sw_plot):
            plot.hideButtons()  # the "A" button: auto is in the toolbar and the menu
        # hover: the nearest reading's time and value, at the cursor
        self._hover: dict[Any, tuple[Any, Any]] = {}
        for plot in (self.err_plot, self.v_plot, self.comb, self.sw_plot):
            text = pg.TextItem(color="#24292f", fill=pg.mkBrush(255, 255, 255, 225), border=pg.mkPen("#d0d7de"),
                               anchor=(0, 1))
            text.setFont(mono())
            dot = pg.ScatterPlotItem(size=9, pen=pg.mkPen("#24292f", width=1.5), brush=None)
            for item in (text, dot):
                item.setZValue(50)
                item.setVisible(False)
                plot.addItem(item, ignoreBounds=True)
            self._hover[plot] = (text, dot)
        self._hover_dot2 = pg.ScatterPlotItem(size=9, pen=pg.mkPen("#24292f", width=1.5), brush=None)
        self._hover_dot2.setZValue(50)
        self._hover_dot2.setVisible(False)
        self.comb_vb.addItem(self._hover_dot2, ignoreBounds=True)
        self._hover_proxies = []
        for widget, plots_in in ((self.sep_widget, [self.err_plot, self.v_plot]), (self.comb_widget, [self.comb]),
                                 (sweep_plots, [self.sw_plot])):
            self._hover_proxies.append(pg.SignalProxy(widget.scene().sigMouseMoved, rateLimit=30,
                                                      slot=HoverSlot(self, plots_in)))
            widget.installEventFilter(self)
        self.sweep_panel = QWidget()
        sv = QVBoxLayout(self.sweep_panel)
        sv.setContentsMargins(0, 0, 0, 0)
        srow = QHBoxLayout()
        srow.addWidget(self._lab("Sweep y", "The sweep plot's frequency axis: auto or a fixed range"))
        srow.addWidget(self.sw_y)
        srow.addStretch(1)
        sv.addLayout(srow)
        sv.addWidget(sweep_plots)
        plot_split = QSplitter()
        plot_split.addWidget(self.time_panel)
        plot_split.addWidget(self.sweep_panel)
        plot_split.setStretchFactor(0, 3)
        plot_split.setStretchFactor(1, 2)
        rv.setContentsMargins(4, 6, 6, 4)
        rv.addLayout(top)
        rv.addWidget(plot_split, 1)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        central = QWidget()
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self.header)
        cv.addWidget(split, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(STYLE)
        self.resize(1500, 900)
        self._plots_shown()
        self._apply_input_lock()

        self.timer = QTimer(self)  # readings, state and buttons
        self.timer.timeout.connect(self._refresh)
        self.timer.start(200)
        self.plot_timer = QTimer(self)  # the time plots (drawing is most of the window's CPU)
        self.plot_timer.timeout.connect(self._plot_tick)
        self._redraw_changed()

    # ---------------------------------------------------------------- user actions

    @staticmethod
    def _pair(*widgets: QWidget, stretch: int = 1) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for k, x in enumerate(widgets):
            h.addWidget(x, 1 if (stretch or k == 0) else 0)
        return w

    @staticmethod
    def _lab(text: str, tip: str) -> QLabel:
        lab = QLabel(text)
        lab.setToolTip(tip)
        return lab

    @staticmethod
    def _caption(title: str, value: QLabel, tip: str) -> QWidget:
        """A header reading: a small caption over a big value."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        cap = QLabel(title)
        cap.setObjectName("caption")
        v.addWidget(cap)
        v.addWidget(value)
        for x in (w, cap, value):
            x.setToolTip(tip)
        return w

    def show_mini(self) -> None:
        self.mini.move(self.geometry().topRight().x() - self.mini.sizeHint().width(), self.geometry().top())
        self.mini.show()
        self.hide()
        self._refresh()

    def show_full(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.mini.hide()

    def _apply_input_lock(self) -> None:
        locked = self.inputs_lock.isChecked()
        self.inputs_lock.setText("🔒  Inputs locked" if locked else "🔓  Inputs unlocked")
        for w in self._guarded:
            if isinstance(w, QAbstractSpinBox):
                w.setReadOnly(locked)
                w.style().unpolish(w)
                w.style().polish(w)
            elif w in self._wm_widgets:
                w.setEnabled(self._wm_seen and not locked)
            else:
                w.setEnabled(not locked)
        self._refresh_buttons(self.engine.snapshot())

    def _nudge_down(self) -> None:
        self._nudge(-1)

    def _nudge_up(self) -> None:
        self._nudge(+1)

    def _wm_exposure(self, v: int) -> None:
        self.engine.set_wavemeter(exposure_ms=v)

    def _wm_auto(self, on: bool) -> None:
        self.engine.set_wavemeter(auto=on)

    def _wm_interval(self, v: int) -> None:
        self.engine.set_wavemeter(interval_ms=v)

    def _wm_interval_on(self, on: bool) -> None:
        self.engine.set_wavemeter(interval_on=on)

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
                "combined": self.layout_kind.currentIndex() == 1, "line_width": self.line_width.value(),
                "hop_lines": self.hop_lines.isChecked(),
                "redraw": self.redraw.currentText(),
                "flicker_min_mhz": self.flicker_min.value(), "jump_min_mhz": self.jump_min.value(),
                "collapsed": [sec.key for sec in self.sections if sec.collapsed],
                "inputs_locked": self.inputs_lock.isChecked(),
                "err_y": self.err_range.state(), "v_y": self.v_range.state(), "sweep_y": self.sw_y.state()}

    def _comb_geometry(self) -> None:
        self.comb_vb.setGeometry(self.comb.getViewBox().sceneBoundingRect())
        self.comb_vb.linkedViewChanged(self.comb.getViewBox(), self.comb_vb.XAxis)

    def _layout_changed(self) -> None:
        combined = self.layout_kind.currentIndex() == 1
        self.sep_widget.setVisible(not combined)
        self.comb_widget.setVisible(combined)
        self.err_range.current = self.v_range.current = 1 if combined else 0
        self._hops_drawn = (-1, 0.0)
        self._draw_time()

    def _pens(self) -> None:
        w = self.line_width.value()
        for curve, colour in ((self.err_curve, ERR_COLOUR), (self.c_err, ERR_COLOUR), (self.v_curve, OUT_COLOUR),
                              (self.c_v, OUT_COLOUR)):
            curve.setPen(pg.mkPen(colour, width=w))
            flick_item, jump_item = self._marks[curve]
            flick_item.setPen(pg.mkPen(FLICKER_COLOUR, width=w + 0.5))
            jump_item.setPen(pg.mkPen(JUMP_COLOUR, width=w + 0.5))

    def _draw_lock_marks(self, t: np.ndarray, locked: np.ndarray, t_from: float, plots: tuple[Any, ...]) -> None:
        """A light green band behind each locked stretch, and a dotted red line where the lock was lost (the newest
        LOCK_MARKS_MAX of each in the shown span; the items are reused)."""
        bands: list[tuple[float, float]] = []
        if t.size:
            edges = np.diff(np.concatenate(([0], locked.astype(np.int8), [0])))
            starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
            bands = [(float(t[a]), float(t[b])) for a, b in zip(starts, ends)][-LOCK_MARKS_MAX:]
        lost = [x - self._t0 for x in self.engine.lost_events() if x - self._t0 >= t_from][-LOCK_MARKS_MAX:]
        for plot in (self.err_plot, self.v_plot, self.comb):
            shown = plot in plots
            pool = self._lock_bands[plot]
            while shown and len(pool) < len(bands):
                band = pg.LinearRegionItem(movable=False, brush=pg.mkBrush(LOCKED_BAND), pen=pg.mkPen(None))
                band.setZValue(-20)
                plot.addItem(band, ignoreBounds=True)
                pool.append(band)
            for k, band in enumerate(pool):
                on = shown and k < len(bands)
                if on:
                    band.setRegion(bands[k])
                band.setVisible(on)
            lines = self._lost_lines[plot]
            while shown and len(lines) < len(lost):
                line = pg.InfiniteLine(angle=90, pen=LOST_PEN)
                line.setZValue(7)
                plot.addItem(line, ignoreBounds=True)
                lines.append(line)
            for k, line in enumerate(lines):
                on = shown and k < len(lost)
                if on:
                    line.setValue(lost[k])
                line.setVisible(on)

    def _draw_time_now(self) -> None:
        self._draw_time()

    def _quality_at(self, x: float) -> str:
        q, t = self._quality, self._quality_t
        if q is None or not t.size:
            return ""
        i = int(np.clip(np.searchsorted(t, x), 0, t.size - 1))
        if i > 0 and abs(t[i - 1] - x) < abs(t[i] - x):
            i -= 1
        return "  · jump" if q.jump[i] else "  · flicker" if q.flicker[i] else ""

    def _hop_lines_toggled(self) -> None:
        self._hops_drawn = (-1, 0.0)
        self._sweep_n = -1
        self._draw_time()

    def _time_kind(self) -> None:
        clock = self.time_kind.currentIndex() == 0
        for axis in self._time_axes:
            axis.set_clock(clock)
        self.v_plot.setLabel("bottom", "time" if clock else "time since start (s)")
        if hasattr(self, "comb"):
            self.comb.setLabel("bottom", "time" if clock else "time since start (s)")

    def _pause_toggled(self, paused: bool) -> None:
        self.pause.setText("▶ Resume (paused)" if paused else "⏸ Pause")

    def _resume(self) -> None:
        """Follow the newest readings again, with the axes on auto."""
        self.pause.setChecked(False)
        self.err_range.auto.setChecked(True)
        self.v_range.auto.setChecked(True)
        self._draw_time()

    def _plot_menu(self, vb: Any, ev: Any) -> None:
        """A right-click menu that fits this window (pyqtgraph's own offers transforms, FFT and log axes, and its
        View All quietly paused the plots)."""
        menu = QMenu(self)
        if vb is self.sw_plot.getViewBox():
            a = menu.addAction("Auto-range")
            a.triggered.connect(self._sweep_auto)
            yr = self.sw_y
        else:
            a = menu.addAction("Resume: follow the newest, axes on auto")
            a.triggered.connect(self._resume)
            a = menu.addAction("Pause (pan and zoom with the mouse)")
            a.setCheckable(True)
            a.setChecked(self.pause.isChecked())
            a.toggled.connect(self.pause.setChecked)
            yr = self.v_range if vb in (self.v_plot.getViewBox(), self.comb_vb) else self.err_range
        menu.addSeparator()
        a = menu.addAction("y: auto")
        a.setCheckable(True)
        a.setChecked(yr.auto.isChecked())
        a.toggled.connect(yr.auto.setChecked)
        for b in yr.preset_buttons:
            a = menu.addAction(f"y: {b.text()}")
            a.triggered.connect(b.click)
        if vb is not self.sw_plot.getViewBox() and self.layout_kind.currentIndex() == 1:
            other = self.err_range if yr is self.v_range else self.v_range
            menu.addSeparator()
            a = menu.addAction(("Error" if other is self.err_range else "Output") + " y: auto")
            a.setCheckable(True)
            a.setChecked(other.auto.isChecked())
            a.toggled.connect(other.auto.setChecked)
            for b in other.preset_buttons:
                a = menu.addAction(("Error" if other is self.err_range else "Output") + f" y: {b.text()}")
                a.triggered.connect(b.click)
        menu.addSeparator()
        a = menu.addAction("Export (image or CSV)…")
        a.triggered.connect(vb.scene().showExportDialog)
        menu.popup(ev.screenPos().toPoint())
        self._menu = menu  # kept alive while shown

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if event.type() == QEvent.Type.Leave:
            self._hide_hover()
        return super().eventFilter(obj, event)

    def _hide_hover(self) -> None:
        for text, dot in self._hover.values():
            text.setVisible(False)
            dot.setVisible(False)
        self._hover_dot2.setVisible(False)

    def _time_text(self, x: float) -> str:
        if self.time_kind.currentIndex() == 0:
            t = self._t0 + x
            return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t % 1) * 10)}"
        return f"{x - (self._start - self._t0):.1f} s"

    @staticmethod
    def _nearest(curve: Any, x: float) -> tuple[float, float] | None:
        xs, ys = curve.getData()
        if xs is None or len(xs) == 0:
            return None
        i = int(np.clip(np.searchsorted(xs, x), 1, len(xs) - 1)) if len(xs) > 1 else 0
        if len(xs) > 1 and abs(xs[i - 1] - x) < abs(xs[i] - x):
            i -= 1
        return float(xs[i]), float(ys[i])

    def _hovered(self, pos: Any, plots: list[Any]) -> None:
        """Shows the reading nearest the cursor (in time; on the sweep, in output) with its value. `plots`: the
        ones in the widget the mouse moved over (each widget has its own scene)."""
        self._hide_hover()
        for plot in plots:
            vb = plot.getViewBox()
            if not vb.sceneBoundingRect().contains(pos):
                continue
            x = vb.mapSceneToView(pos).x()
            text, dot = self._hover[plot]
            lines: list[str] = []
            if plot is self.sw_plot:
                xs, ys = self.sw_curve.getData()
                xd, yd = self.sw_down.getData()
                pts = [(a, b) for a, b in zip(list(xs if xs is not None else []) + list(xd if xd is not None else []),
                                             list(ys if ys is not None else []) + list(yd if yd is not None else []))]
                if not pts:
                    return
                vx, vy = min(pts, key=lambda q: abs(q[0] - x))
                lines = [f"{vx:.4f} V", f"{vy / 1e6:+.3f} MHz"]
                where = (vx, vy)
            elif plot is self.comb:
                e = self._nearest(self.c_err, x)
                v = self._nearest(self.c_v, x)
                if e is None:
                    return
                lines = [self._time_text(e[0]) + self._quality_at(e[0]), f"error {e[1] / 1e6:+.3f} MHz"]
                if v is not None:
                    lines.append(f"output {v[1]:.4f} V")
                    self._hover_dot2.setData([v[0]], [v[1]])
                    self._hover_dot2.setVisible(True)
                where = e
            else:
                curve = self.err_curve if plot is self.err_plot else self.v_curve
                n = self._nearest(curve, x)
                if n is None:
                    return
                value = f"{n[1] / 1e6:+.3f} MHz" if plot is self.err_plot else f"{n[1]:.4f} V"
                lines = [self._time_text(n[0]) + self._quality_at(n[0]), value]
                where = n
            (x0, x1), (y0, y1) = vb.viewRange()
            text.setAnchor((1 if where[0] > (x0 + x1) / 2 else 0, 0 if where[1] > (y0 + y1) / 2 else 1))
            text.setText("\n".join(lines))
            text.setPos(*where)
            dot.setData([where[0]], [where[1]])
            text.setVisible(True)
            dot.setVisible(True)
            return

    def _sweep_auto(self) -> None:
        self.sw_y.auto.setChecked(True)
        self.sw_plot.enableAutoRange()

    def _time_dragged(self, mask: Any) -> None:
        if mask is None or len(mask) < 1 or mask[0]:
            self.pause.setChecked(True)

    def _clear(self) -> None:
        self._hist.n = 0
        for curve in (self.err_curve, self.v_curve, self.c_err, self.c_v):
            curve.setData([], [])
            for item in self._marks[curve]:
                item.setData([], [])
        self.rms_label.setText("")
        self.quality_label.setText("")
        self._quality = None

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
                "settle_s": self.sw_settle.value(), "dwell_s": self.sw_dwell.value(),
                "margin_v": self.scan_margin.value(), "hold_s": self.scan_hold.value(),
                "relock": self.relock.isChecked()}

    def _push_relock(self) -> None:
        req = None
        if self.relock.isChecked():
            lo, hi = sorted((self.sw_start.value(), self.sw_stop.value()))
            req = ScanRequest(lo, hi, self.sw_step.value(), self.sw_settle.value(), self.sw_dwell.value(),
                              self.set_thz.value(), self.scan_margin.value(), self.scan_hold.value())
        self.engine.set_relock(req)

    def _find_stable(self) -> None:
        if self.engine.snapshot().mode == "sweeping":
            self.engine.abort()
            return
        self._push_settings()
        target = self.set_thz.value()
        if not target:
            self.message_label.setText("set a setpoint first")
            return
        self.engine.find_stable(self.sw_start.value(), self.sw_stop.value(), self.sw_step.value(),
                                self.sw_settle.value(), self.sw_dwell.value(), target,
                                self.scan_margin.value(), self.scan_hold.value())

    def _selected_stretch(self) -> Stretch | None:
        rows = {i.row() for i in self.scan_table.selectedIndexes()}
        return self._stretches[rows.pop()] if len(rows) == 1 and 0 <= min(rows) < len(self._stretches) else None

    def _scan_selected(self) -> None:
        self._refresh_buttons(self.engine.snapshot())
        self._sweep_n = -1
        self._scan_shown = -1  # redraw: the chosen stretch is darker

    def _lock_selected(self) -> None:
        st = self._selected_stretch()
        if st is not None:
            self._push_settings()
            self.engine.lock_stretch(st)

    def _current_settings(self) -> LockSettings:
        return replace(self.engine.settings(), setpoint_thz=self.set_thz.value(), kp=self.kp.value(),
                       ki=self.ki.value(), kd=self.kd.value(), d_filter_s=self.d_filter.value(),
                       lost_after_s=self.lost_after.value(),
                       sign=1 if self.sign.currentIndex() == 0 else -1,
                       v_min=self.v_min.value(), v_max=max(self.v_max.value(), self.v_min.value()),
                       max_step=self.max_step.value(), capture_mhz=self.capture.value())

    def _push_settings(self) -> None:
        self.engine.update_settings(self._current_settings())
        if hasattr(self, "relock"):
            self._push_relock()

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
            set_text(self.freq_label, f"{r.thz:.7f} THz")
            set_text(self.nm_label, f"{thz_to_nm(r.thz):.6f} nm")
            set_text(self.status_label, f"ok, new value every {snap.update_s * 1e3:.0f} ms" if snap.update_s else "ok")
        else:
            set_text(self.status_label, f"<b style='color:#cf222e'>{r.status}</b>")
        set_text(self.err_label, "—" if snap.error_mhz is None else f"{snap.error_mhz:+.2f} MHz")
        set_text(self.volt_label, f"{snap.volts:.4f} V")
        mode = snap.mode if snap.mode != "locked" or snap.state == "locked" else f"locked · {snap.state}"
        colour = MODE_COLOURS.get(snap.mode, "#6e7781")
        if snap.state == "lost" and snap.mode == "idle":
            mode, colour = "LOCK LOST", "#cf222e"
        elif snap.mode == "locked" and snap.state != "locked":
            colour = "#9a6700"  # holding: out of capture, limited, no reading
        if self.mode_label.text() != mode.upper() or self._mode_colour != colour:
            set_text(self.mode_label, mode.upper())
            self.mode_label.setStyleSheet(f"background: {colour}")
            self._mode_colour = colour
        if self.mini.isVisible():
            self.mini.show_state(mode.upper(), colour, self.err_label.text(), self.volt_label.text())
        if snap.message:
            set_text(self.message_label, snap.message)
        locked = snap.mode == "locked"
        if self.lock_btn.isChecked() != locked:
            self.lock_btn.blockSignals(True)
            self.lock_btn.setChecked(locked)
            self.lock_btn.blockSignals(False)
        self.lock_btn.setText("Unlock" if locked else "Lock")
        busy = snap.mode in ("calibrating", "fault")
        self._refresh_buttons(snap)
        if self.retry_btn.isVisible() != (snap.mode == "fault"):
            self.retry_btn.setVisible(snap.mode == "fault")
        if (snap.message.startswith(("find stable range: locked", "locked at ")) and snap.message != self._shown_cal):
            self._shown_cal = snap.message
            self._show_settings()
        self._refresh_sweep()
        self.manual.setEnabled(snap.mode == "idle")
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
            set_text(self.hop_label, f"<b style='color:{HOP_COLOUR}'>Mode hops: {snap.hops}</b> · last "
                                   f"{h.hop.jump_mhz / 1e3:+.3f} GHz at {time.strftime('%H:%M:%S', time.localtime(h.t))}"
                                   f" ({h.volts:.4f} V)")

    def _plot_tick(self) -> None:
        """The time plots, at the Redraw rate: only while shown and not paused, only the visible span."""
        if self.isMinimized() or not self.isVisible():
            return
        for r_ in (self.err_range, self.v_range, self.sw_y):
            r_.sync()
        if self.pause.isChecked():
            return
        # skip a redraw that would scroll the plots by less than a pixel (a long span)
        span = SPANS[self.span.currentText()] or (float(self._hist.t[self._hist.n - 1] - self._hist.t[0])
                                                  if self._hist.n else 0.0)
        width = (self.comb if self.layout_kind.currentIndex() == 1 else self.v_plot).getViewBox().width()
        if time.monotonic() - self._last_draw < span / max(width, 1.0):
            return
        self._draw_time()

    def _redraw_changed(self) -> None:
        hz = REDRAW_HZ.get(self.redraw.currentText(), 2.0)
        self.plot_timer.start(int(1000 / hz))

    def _refresh_buttons(self, snap: Any) -> None:
        """The action buttons for the mode now; with the inputs locked only Abort stays available."""
        free = not self.inputs_lock.isChecked()
        idle, sweeping = snap.mode == "idle", snap.mode == "sweeping"
        self.lock_btn.setEnabled(free and snap.mode in ("idle", "locked"))
        self.sweep_btn.setText("Abort" if sweeping else "Sweep")
        self.auto_btn.setText("Abort" if sweeping else "Auto-lock")
        self.scan_btn.setText("Abort" if sweeping else "Find stable range → lock")
        for b in (self.sweep_btn, self.auto_btn, self.scan_btn):
            b.setEnabled(sweeping or (idle and free))
        self.stretch_btn.setEnabled(free and idle and self._selected_stretch() is not None)
        calibrating = snap.mode == "calibrating"
        self.cal_btn.setText("Abort calibration" if calibrating else "Calibrate tuning")
        self.cal_btn.setEnabled(calibrating or (idle and free))

    def _draw_time(self, hops: int | None = None) -> None:
        """The time plots of the shown layout (only while shown and not paused)."""
        if not self.time_panel.isVisible() or not self._hist.n or self.pause.isChecked():
            return
        combined = self.layout_kind.currentIndex() == 1
        now = time.time() - self._t0
        span = SPANS[self.span.currentText()]
        t, thz, volts, locked = self._hist.since(now - span if span else -math.inf)
        (self.comb if combined else self.v_plot).setXRange(now - span if span else (float(t[0]) if t.size else now - 1),
                                                            now, padding=0)
        setpoint = self.set_thz.value()
        ref = setpoint if setpoint > 0 else float(thz[0]) if thz.size else 0.0
        err = (thz - ref) * 1e12  # Hz
        q = classify(t, err / 1e6, self.flicker_min.value(), self.jump_min.value())
        self._quality, self._quality_t = q, t
        self._last_draw = time.monotonic()
        # a long span: plot each bin's extremes only (a few per pixel); the flags and hover use every reading
        tp, ep, vp, fp, jp = t, err, volts, q.flicker, q.jump
        if t.size > PLOT_POINTS_MAX:
            idx, fp, jp = minmax_bins(PLOT_POINTS_MAX // 4, (err, volts), (q.flicker, q.jump))
            tp, ep, vp = t[idx], err[idx], volts[idx]
        pairs = ((self.c_err, ep), (self.c_v, vp)) if combined else ((self.err_curve, ep), (self.v_curve, vp))
        for curve, y in pairs:
            curve.setData(tp, y)
            flick_item, jump_item = self._marks[curve]
            flick_item.setData(tp, np.where(fp, y, np.nan))
            jump_item.setData(tp, np.where(jp, y, np.nan))
        bits = []
        if q.jumps:
            bits.append(f"<span style='color:{JUMP_COLOUR}'>■ {q.jumps} jump{'s' if q.jumps != 1 else ''}</span>")
        if q.flicker_s > 0:
            bits.append(f"<span style='color:{FLICKER_COLOUR}'>■ flicker {q.flicker_s:.1f} s</span>")
        self.quality_label.setText("  ".join(bits) if bits else "no flicker or jumps")
        self.err_range.fit(err[t >= now - min(FOLLOW_S, span or FOLLOW_S)])
        self._draw_hops(self.engine.snapshot().hops if hops is None else hops, now - span if span else -math.inf)
        self._draw_lock_marks(t, locked, now - span if span else -math.inf,
                              (self.comb,) if combined else (self.err_plot, self.v_plot))
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
        if not self._wm_seen:
            self._wm_seen = True
            for w in self._wm_widgets:
                w.setEnabled(isinstance(w, QAbstractSpinBox) or not self.inputs_lock.isChecked())
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
        combined = self.layout_kind.currentIndex() == 1
        lines = shown[-HOP_LINES_MAX:] if self.hop_lines.isChecked() and not combined else []
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
        xs, ys = [e.t - self._t0 for e in shown], [e.volts for e in shown]
        (self.c_hops if combined else self.hop_dots).setData(xs, ys)
        (self.hop_dots if combined else self.c_hops).setData([], [])

    def _refresh_scan(self) -> bool:
        """Draws the last find-stable-range scan (both directions, the stable stretches) and fills the table.
        Returns whether there is one (then the plain sweep's drawing is left alone)."""
        seq, scan = self.engine.scan_data()
        if scan is None:
            if self._scan_shown != -2:
                self._scan_shown = -2
                self._sweep_n = -1  # the plain sweep redraws its curve
                self.sw_down.setData([], [])
                self._set_stretches([], None)
            return False
        if seq == self._scan_shown:
            return True
        self._scan_shown = seq
        ref = self.set_thz.value() or scan.request.target_thz
        for curve, pts in ((self.sw_curve, scan.up), (self.sw_down, scan.down)):
            good = [p for p in pts if p.thz is not None]
            curve.setData([p.volts for p in good], [((p.thz or 0.0) - ref) * 1e12 for p in good])
        for line in self._sw_hop_lines:
            self.sw_plot.removeItem(line)
        self._sw_hop_lines = []
        self.sw_choice.setVisible(scan.choice is not None and scan.choice.target_v is not None)
        if scan.choice is not None and scan.choice.target_v is not None:
            self.sw_choice.setValue(scan.choice.target_v)
        self.sw_range.setVisible(False)
        self._set_stretches(scan.stretches, scan.choice)
        return True

    def _set_stretches(self, stretches: list[Stretch], choice: Stretch | None) -> None:
        picked = self._selected_stretch()
        for item in self._stretch_regions:
            self.sw_plot.removeItem(item)
        self._stretch_regions = []
        for st in stretches:
            dark = st == choice or st == picked
            region = pg.LinearRegionItem((st.v_lo, st.v_hi), movable=False,
                                         brush=(26, 127, 55, 70 if dark else 25), pen=pg.mkPen(None))
            region.setZValue(-20)
            self.sw_plot.addItem(region, ignoreBounds=True)
            self._stretch_regions.append(region)
        if stretches == self._stretches:
            return
        self._stretches = list(stretches)
        self.scan_table.blockSignals(True)
        self.scan_table.setRowCount(len(stretches))
        for row, st in enumerate(stretches):
            if st.target_v is not None:
                where = f"in: {st.target_v:.3f} V, {st.room_v:.2f} V room"
            else:
                where = f"shift {st.shift_mhz / 1e3:+.2f} GHz"
            cells = (f"{st.v_lo:.2f}–{st.v_hi:.2f} V", where, f"{st.width_mhz / 1e3:.2f} GHz",
                     f"{st.mhz_per_v:+.0f} MHz/V", f"{st.f_lo:.6f}–{st.f_hi:.6f}")
            for col, text in enumerate(cells):
                self.scan_table.setItem(row, col, QTableWidgetItem(text))
        self.scan_table.clearSelection()
        self.scan_table.blockSignals(False)

    def _refresh_sweep(self) -> None:
        if self._refresh_scan():
            return
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
        for v in sweep_hops(points) if self.hop_lines.isChecked() else []:
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
        self.mini.hide()
        self.mini.deleteLater()
        self.on_save(self._current_settings(), {"step_v": self.cal_step.value(), "settle_s": self.cal_settle.value(),
                                                "average_s": self.cal_avg.value()})
        super().closeEvent(event)
