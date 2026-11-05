"""What Basic plots v2's plots share: a per-shot X axis by shot ID or shot time in each library
(``helab.analysis.shot_axis``), with the TXY-time points marked, and the titles.

A v2 plot's PyQtGraph title holds what describes the drawing (shots, events, bins, notes): the
folder and revision are on the dock's line just above it, and in Plot info. Its Plotly and Matplotlib
titles keep them, since those figures leave HeLab (Open in browser, a saved figure)."""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Optional, Sequence, TypeVar

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg

from helab.analysis.results import AnalysisResult
from helab.analysis.shot_axis import FALLBACK_COLOUR, ShotAxis, broken

NOTE_COLOUR = "#b06000"  # The notes under a title (as v1's Transfer fractions writes them).
FALLBACK_SIZE = 9


def source_title(result: AnalysisResult, text: str) -> str:
    """``text`` after the input (folder · rev N), for a figure that leaves HeLab."""
    return f"{result.input.short()} · {text}"


def notes_html(notes: Sequence[str]) -> str:
    """The notes as a second line of a PyQtGraph title (escaped), "" for none."""
    return f'<br><span style="color: {NOTE_COLOUR}">{html.escape(" · ".join(notes))}</span>' if notes else ""


AXIS_MODE = "shot_axis_mode"  # The attribute a drawing keeps its X axis in (``drawn_on``, ``same_axis``).


Drawing = TypeVar("Drawing")


def drawn_on(widget: Drawing, axis: ShotAxis) -> Drawing:
    """``widget``, a per-shot drawing in any library, marked with its X axis (``same_axis``)."""
    setattr(widget, AXIS_MODE, axis.mode)
    return widget


def same_axis(widget: Any, axis: ShotAxis) -> bool:
    """Whether ``widget`` was drawn on ``axis``'s X axis: another (Shot ID or Shot time) is drawn anew in every
    library, so the old axis's zoom never carries over (a shot-ID range read as dates in 1970)."""
    return getattr(widget, AXIS_MODE, None) == axis.mode


# PyQtGraph


def bottom_axis(axis: ShotAxis) -> Optional[dict[str, Any]]:
    """The ``axisItems`` of a per-shot plot: a date axis for shot times, else PyQtGraph's own."""
    return {"bottom": pg.DateAxisItem(orientation="bottom")} if axis.by_time else None


class ShotSeries:
    """One per-shot series of a PyQtGraph plot: a line with a circle per shot (broken at long gaps by shot
    time), and amber triangles over the shots whose time is their TXY file's."""

    def __init__(self, plot: Any, colour: tuple[int, int, int], name: Optional[str] = None,
                 fallback_brush: Optional[tuple[int, int, int]] = None) -> None:
        self.line = pg.PlotDataItem(name=name, connect="finite", pen=pg.mkPen(colour, width=1.5 if name else 1),
                                    symbol="o", symbolSize=4, symbolBrush=colour, symbolPen=None)
        # Triangles, pointing down (PyQtGraph's "t", Shot times' ▼; Plotly and Matplotlib the same): in the
        # series' colour outlined in amber for one of several (the order stays readable), else amber.
        brush = fallback_brush or FALLBACK_COLOUR
        pen = pg.mkPen(FALLBACK_COLOUR, width=1.5) if fallback_brush is not None else None
        self.fallback = pg.PlotDataItem(pen=None, symbol="t", symbolSize=FALLBACK_SIZE, symbolBrush=brush,
                                        symbolPen=pen)
        plot.addItem(self.line)
        plot.addItem(self.fallback)

    def set(self, axis: ShotAxis, values: npt.NDArray[Any]) -> None:
        y = np.asarray(values, dtype=np.float64)
        self.line.setData(*broken(axis.x, y, axis.breaks()))
        flagged = axis.fallback & np.isfinite(y)
        self.fallback.setData(axis.x[flagged], y[flagged])


# Plotly


def plotly_x(axis: ShotAxis, x: npt.NDArray[np.float64]) -> list[Any]:
    """X values for Plotly: shot IDs, or local times as text Plotly reads as dates (None at a break)."""
    if not axis.by_time:
        return [None if not np.isfinite(value) else int(value) for value in x]
    return [None if not np.isfinite(value) else datetime.fromtimestamp(float(value)).isoformat(sep=" ")
            for value in x]


def plotly_series(axis: ShotAxis, values: npt.NDArray[Any], **trace: Any) -> list[dict[str, Any]]:
    """A Plotly series' traces (as keyword arguments for ``go.Scatter``): the line broken at long gaps, with
    each point's hover text, and the TXY-time triangles (none without such points)."""
    y = np.asarray(values, dtype=np.float64)
    x, y_broken = broken(axis.x, y, axis.breaks())
    texts = [axis.point_text(index) for index in range(len(axis.x))]
    text: list[Optional[str]] = list(texts)
    for at in reversed(np.flatnonzero(axis.breaks()).tolist()):
        text.insert(at, None)
    colour = trace.pop("colour")
    label = trace.pop("value_label", "%{y:,}")
    traces = [dict(x=plotly_x(axis, x), y=y_broken, mode="lines+markers", text=text, connectgaps=False,
                   line=dict(color=colour, width=trace.pop("width", 1)), marker=dict(size=5, color=colour),
                   hovertemplate=f"%{{text}}<br>{label}<extra></extra>", **trace)]
    flagged = axis.fallback & np.isfinite(y)
    if flagged.any():
        traces.append(dict(x=plotly_x(axis, axis.x[flagged]), y=y[flagged], mode="markers", showlegend=False,
                           text=[texts[index] for index in np.flatnonzero(flagged)],
                           marker=dict(symbol="triangle-down", size=10, color=colour,
                                       line=dict(color=f"rgb{FALLBACK_COLOUR}", width=2)),
                           hovertemplate=f"%{{text}}<br>{label}<extra></extra>"))
    return traces


def plotly_axis(axis: ShotAxis) -> dict[str, Any]:
    return dict(title_text=axis.label, type="date" if axis.by_time else "linear")


# Matplotlib


def matplotlib_x(axis: ShotAxis, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """X values for Matplotlib: shot IDs, or local times as Matplotlib's date numbers (NaN kept)."""
    if not axis.by_time:
        return x
    from matplotlib import dates as typed_dates

    dates: Any = typed_dates  # (Its functions are untyped.)
    return np.array([dates.date2num(datetime.fromtimestamp(float(value))) if np.isfinite(value) else np.nan
                     for value in x], dtype=np.float64)


def matplotlib_series(axes: Any, axis: ShotAxis, values: npt.NDArray[Any], colour: Any, **line: Any) -> None:
    """A Matplotlib series: the line broken at long gaps, and the TXY-time triangles."""
    y = np.asarray(values, dtype=np.float64)
    x, y_broken = broken(axis.x, y, axis.breaks())
    axes.plot(matplotlib_x(axis, x), y_broken, "-o", color=colour, markersize=3, **line)
    flagged = axis.fallback & np.isfinite(y)
    if flagged.any():
        axes.plot(matplotlib_x(axis, axis.x[flagged]), y[flagged], "v", color=colour, markersize=7,
                  markeredgecolor=tuple(value / 255 for value in FALLBACK_COLOUR), markeredgewidth=1.5)


def matplotlib_axis(axes: Any, axis: ShotAxis) -> None:
    axes.set_xlabel(axis.label, fontsize=8)
    if axis.by_time:
        from matplotlib import dates as typed_dates

        dates: Any = typed_dates  # (Its functions are untyped.)
        locator = dates.AutoDateLocator()
        axes.xaxis.set_major_locator(locator)
        axes.xaxis.set_major_formatter(dates.ConciseDateFormatter(locator))
