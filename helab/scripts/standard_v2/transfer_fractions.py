"""Transfer fractions (Basic plots v2): v1's (``helab.scripts.standard.transfer_fractions``, which stays as it
is, its orders found and counted the same way) with an X axis setting on the fractions: each shot's share of
each order against its shot ID or its time, the shots whose time is their TXY file's marked. The T histogram
below is v1's. Its PyQtGraph title leaves out the folder and revision, which the dock's line above it shows."""
from __future__ import annotations

import html
from dataclasses import dataclass, field, fields
from typing import Any, List, Mapping, Optional, cast

import numpy as np
import numpy.typing as npt
import plotly.graph_objs as go
import pyqtgraph as pg
from plotly.subplots import make_subplots
from PyQt6.QtWidgets import QWidget

from helab.analysis.backends import (MATPLOTLIB, PLOTLY, MatplotlibPane, WrappingLabel, matplotlib_pane, mpl_colour,
                                     rgb, set_title)
from helab.analysis.dataset_view import DatasetView
from helab.analysis.empty import empty_pane
from helab.analysis.orders import Fractions, order_label
from helab.analysis.overlay import overlay_newest
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.shot_axis import (SHOT_ID, SHOT_TIME, TOOLTIP, ShotAxis, axis_brief, axis_mode, fallback_text,
                                      shot_axis, x_axis_spec)
from helab.analysis.selection import select_shots
from helab.scripts.base import ScriptMetadata
from helab.scripts.standard import transfer_fractions as v1
from helab.scripts.standard_v2 import group
from helab.scripts.standard_v2.common import (ShotSeries, bottom_axis, drawn_on, matplotlib_axis,
                                              matplotlib_series, plotly_axis, plotly_series, same_axis)

X_AXIS = x_axis_spec("Fractions")
UI_REVISION = "helab.v2.transfer_fractions"


@dataclass(frozen=True)
class TimedFractions(Fractions):
    """v1's ``Fractions`` with the counted shots on the X axis chosen: ``rows`` are their rows in drawing order
    (by time: those with a time, ascending by time)."""
    axis: ShotAxis = field(default_factory=lambda: ShotAxis(SHOT_ID, np.empty(0, np.int64), np.empty(0),
                                                             np.empty(0, np.bool_)))
    rows: npt.NDArray[np.intp] = field(default_factory=lambda: np.empty(0, np.intp))

    @property
    def drawn(self) -> npt.NDArray[np.float64]:
        """Each drawn shot's fractions (rows: ``axis.shots``; columns: the orders)."""
        return self.fractions[self.rows] if len(self.rows) else np.empty((0, len(self.orders.numbers)))

    @property
    def notes_all(self) -> tuple[str, ...]:
        return (*self.notes, *self.axis.notes())


def timed(data: Fractions, view: DatasetView, mode: str) -> TimedFractions:
    """``data`` with its counted shots on the X axis ``mode``."""
    axis = shot_axis(view, data.shots.tolist(), mode)
    position = {int(shot): row for row, shot in enumerate(data.shots)}
    rows = np.fromiter((position[int(shot)] for shot in axis.shots), dtype=np.intp, count=len(axis.shots))
    return TimedFractions(**{item.name: getattr(data, item.name) for item in fields(Fractions)}, axis=axis, rows=rows)


def plain_title(result: AnalysisResult) -> str:
    """v1's title with the input, for a figure that leaves HeLab."""
    return v1.fractions_title(result)


def drawing_title(result: AnalysisResult) -> str:
    """The PyQtGraph title: v1's without its input (on the dock's line and in Plot info)."""
    return v1.fractions_title(result).removeprefix(f"{result.input.short()} · ")


class TransferFractions(v1.TransferFractions):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata(
            name="Transfer fractions",
            description="Share of each shot's atoms in each order (found in the T histogram), against its shot "
                        "ID or when it was taken; from Momentum_Bells_test's monitor_momentum.m",
            group=group.NAME,
            file_path=__file__,
            analysis_id="helab.v2.transfer_fractions",
            version="1",
        )

    def parameters(self, action_name: str) -> List[ParameterSpec]:
        return [*super().parameters(action_name), X_AXIS]

    def describe_run(self, action_name: str, values: Mapping[str, Any], view: DatasetView) -> tuple[str, str]:
        used, settings = super().describe_run(action_name, values, view)
        if axis_mode(values) == SHOT_TIME:
            fallbacks = len(view.fallback_times(select_shots(view, values)))
            used += f" · ⚠ {fallback_text(fallbacks)}" if fallbacks else ""
        return used, " · ".join(part for part in (settings, axis_brief(values)) if part)

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        return timed(super().compute(action_name, context), context.view, axis_mode(context.parameters))

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        """A rerun (e.g. Live's next shots) updates the plot in place, in every library: a zoom or pan stays,
        else the axes follow the new data. Another X axis draws it anew in every library, as do, in PyQtGraph,
        other orders or another highlight or colour."""
        data: TimedFractions = result.data
        if empty_text(data) or not same_axis(widget, data.axis):
            return False
        if isinstance(widget, PlotlyPane):
            widget.update_figure(plotly_figure(result))
            return True
        if isinstance(widget, pg.GraphicsLayoutWidget):
            if getattr(widget, "drawn_layout", None) != layout(data):
                return False
            fill_pyqtgraph(widget, result)
            return True
        pane = matplotlib_pane(widget)
        if pane is None:
            return False
        pane.redraw(lambda figure: matplotlib_figure(result, figure))
        return True

    def draw(self, result: AnalysisResult, backend: str, parent: Optional[QWidget] = None) -> QWidget:
        data: TimedFractions = result.data
        orders = data.orders
        if text := empty_text(data):
            return empty_pane(text, parent)
        if backend == PLOTLY:
            return drawn_on(PlotlyPane(plotly_figure(result), parent=parent), data.axis)
        if backend == MATPLOTLIB:
            return drawn_on(MatplotlibPane(matplotlib_figure(result), parent), data.axis)
        widget: Any = pg.GraphicsLayoutWidget(parent)
        widget.setBackground("w")
        widget.title_label = WrappingLabel("")
        widget.addItem(widget.title_label, row=0, col=0)
        colours = v1.order_colours(orders)
        plot = widget.addPlot(row=1, col=0, axisItems=bottom_axis(data.axis))
        plot.setLabel("bottom", data.axis.label)
        plot.setLabel("left", "Transfer fraction")
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.addLegend(offset=(-10, 10))
        if data.axis.by_time:
            plot.setToolTip(TOOLTIP)
        widget.fraction_series = [ShotSeries(plot, colour, f"order {order_label(order)}", fallback_brush=colour)
                                  for order, colour in zip(orders.numbers, colours)]
        times = widget.addPlot(row=2, col=0)
        widget.times_plot = times
        times.setLabel("bottom", "T (s)")
        times.setLabel("left", "Events")
        widget.times_curve = pg.PlotDataItem(stepMode="center", fillLevel=0, pen=pg.mkPen((60, 60, 60)),
                                             brush=(60, 60, 60, 60))
        times.addItem(widget.times_curve)
        widget.newest_view = widget.newest_scaled = None
        if data.newest_shot is not None:
            left = times.getAxis("left")
            left.setPen(pg.mkPen((60, 60, 60)))
            left.setTextPen(pg.mkPen((60, 60, 60)))
            times.setLabel("left", "Events (all)")
            edges, counts = data.histogram
            scale = v1.newest_scale(counts, data.newest)
            widget.newest_scaled = pg.PlotDataItem(edges, data.newest * scale, stepMode="center",
                                                   pen=pg.mkPen((0, 0, 0, 0)))
            times.addItem(widget.newest_scaled)
            widget.newest_view = overlay_newest(times, edges, data.newest.astype(np.int64), scale, data.colour,
                                                False, f"shot {data.newest_shot}")
        widget.order_windows = []
        for column, order in enumerate(orders.numbers):
            region = pg.LinearRegionItem(orders.window(order), movable=False, brush=(*colours[column], 50),
                                         pen=pg.mkPen(None))
            times.addItem(region)
            label = pg.TextItem(order_label(order), color=colours[column], anchor=(0.5, 0))
            times.addItem(label)
            widget.order_windows.append((region, label))
        widget.ci.layout.setRowStretchFactor(1, 3)
        widget.ci.layout.setRowStretchFactor(2, 2)
        widget.drawn_layout = layout(data)
        fill_pyqtgraph(widget, result)
        return cast(QWidget, drawn_on(widget, data.axis))


def empty_text(data: TimedFractions) -> str:
    """Why there is nothing to draw ("" when there is): v1's reasons, or no counted shot with a time."""
    if text := v1.empty_reason(data):
        return text
    if data.axis.by_time and not len(data.axis.shots):
        return f"None of the {len(data.shots):,} counted shots has a time"
    return ""


def layout(data: TimedFractions) -> tuple[Any, ...]:
    """What a PyQtGraph drawing is built for: a newer result with the same is shown in it."""
    return (*v1.pyqtgraph_layout(data), data.axis.mode)


def fill_pyqtgraph(widget: Any, result: AnalysisResult) -> None:
    """``result`` in a PyQtGraph drawing built for its layout (``layout``)."""
    data: TimedFractions = result.data
    orders = data.orders
    notes = " · ".join(data.notes_all)
    notes = f'<br><span style="color: #b06000">{html.escape(notes)}</span>' if notes else ""
    widget.title_label.setText(html.escape(drawing_title(result)) + notes)
    drawn = data.drawn
    for column, series in enumerate(widget.fraction_series):
        series.set(data.axis, drawn[:, column])
    edges, counts = data.histogram
    set_title(widget.times_plot, v1.times_title(data))
    if len(counts):
        widget.times_curve.setData(edges, counts)
    else:
        widget.times_curve.clear()
    if widget.newest_view is not None:
        scale = v1.newest_scale(counts, data.newest)
        widget.newest_scaled.setData(edges, data.newest * scale)
        widget.newest_view.curve.setData(edges, data.newest)
        widget.times_plot.setLabel("right", f"shot {data.newest_shot} events", color=pg.mkColor(data.colour).name())
        widget.newest_view.set_ratio(scale)
    top = float(counts.max()) if len(counts) else 1.0
    for order, (region, label) in zip(orders.numbers, widget.order_windows):
        region.setRegion(orders.window(order))
        label.setPos(orders.centre + order * orders.spacing, top)


def plotly_figure(result: AnalysisResult) -> go.Figure:
    """v1's figure, its fractions drawn on the X axis chosen."""
    data: TimedFractions = result.data
    figure = v1.plotly_figure(result)
    colours = v1.order_colours(data.orders)
    count = len(data.orders.numbers)
    # v1's first traces are the orders' fractions against shot number: drawn again on this axis.
    others = list(figure.data[count:])
    figure.data = ()
    drawn = data.drawn
    for column, order in enumerate(data.orders.numbers):
        for trace in plotly_series(data.axis, drawn[:, column], colour=rgb(colours[column]), width=1.5,
                                   name=f"order {order_label(order)}",
                                   value_label=f"order {order_label(order)}: %{{y:.3f}}"):
            figure.add_trace(go.Scatter(**trace), row=1, col=1)
    for trace in others:
        figure.add_trace(trace, row=2, col=1)
    figure.update_xaxes(row=1, col=1, **plotly_axis(data.axis))
    figure.update_layout(uirevision=UI_REVISION)
    if data.axis.notes():
        notes = " · ".join(data.notes_all)
        figure.update_layout(title=dict(text=f'{html.escape(plain_title(result))}<br><span style="color: #b06000; '
                                             f'font-size: 11px">{html.escape(notes)}</span>'),
                             margin=dict(t=90))
    return figure


def matplotlib_figure(result: AnalysisResult, figure: Any = None) -> Any:
    """v1's figure, its fractions drawn on the X axis chosen."""
    data: TimedFractions = result.data
    figure = v1.matplotlib_figure(result, figure)
    shares = figure.axes[0]
    for line in list(shares.lines):
        line.remove()
    colours = v1.order_colours(data.orders)
    drawn = data.drawn
    for column, order in enumerate(data.orders.numbers):
        matplotlib_series(shares, data.axis, drawn[:, column], mpl_colour(colours[column]), linewidth=1.5,
                          label=f"order {order_label(order)}")
    shares.relim()
    shares.autoscale_view()
    matplotlib_axis(shares, data.axis)
    shares.legend(fontsize=7, loc="upper right")
    if data.axis.notes():
        shares.set_title(" · ".join(data.notes_all), fontsize=7, color=(0.69, 0.38, 0.0), wrap=True)
    return figure

