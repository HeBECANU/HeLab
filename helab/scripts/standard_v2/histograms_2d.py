"""XY, XT and YT histograms (Basic plots v2, LR-13): the chosen shots' events binned in a plane, the third
axis summed over the selection (``helab.analysis.histogram2d``). An image with a colour bar, linear or log,
drawn with PyQtGraph (``ImageItem``) by default, or Plotly or Matplotlib; updated in place as Live adds shots.
XY keeps equal scales on its axes (both lengths); T runs across XT and YT. In s and m with SI prefixes.

The plots are ``xy_histogram``, ``xt_histogram`` and ``yt_histogram`` (a module each, so the Scripts panel lists
them in that order); this module is their shared code, not registered itself."""
from __future__ import annotations

import math
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, cast

import numpy as np
import numpy.typing as npt
import plotly.graph_objs as go
import pyqtgraph as pg
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QWidget

from helab.analysis.backends import MATPLOTLIB, PLOTLY, PYQTGRAPH, MatplotlibPane, WrappingLabel, mpl_figure
from helab.analysis.dataset_view import DatasetView
from helab.analysis.empty import empty_pane, empty_text
from helab.analysis.histogram2d import MAX_AUTO_BINS, PLANES, Histogram2D, histogram2d, log_image
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.selection import (SHOT_SPECS, keep_fraction, manual, manual_bounds, range_brief, range_specs,
                                      range_text, range_warnings, reversed_axes, select_shots, selection_text,
                                      shots_brief, shots_text)
from helab.analysis.stats import AXES, MAX_BINS, UNITS
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.scripts.standard.basic_plots import matplotlib_update, plotly_update
from helab.scripts.standard_v2 import group
from helab.scripts.standard_v2.common import notes_html, source_title

LINEAR, LOG = "linear", "log"
RANGE = range_specs(
    "Each shown axis covers the exact shortest range holding this share of its events; the summed axis isn't "
    "cut (every event of the chosen shots counts). In manual, bounds set on the summed axis limit the events "
    "summed. 100 % covers every event.")
HISTOGRAM_GROUP = "Histogram"
BINS_ACROSS = ParameterSpec(
    "bins_across", "Bins across (0 = auto)", "int", 0, (0, MAX_BINS), group=HISTOGRAM_GROUP,
    tip=f"Bins on the horizontal axis. 0 = automatic (Freedman–Diaconis on that axis, at most {MAX_AUTO_BINS:,}).")
BINS_UP = ParameterSpec(
    "bins_up", "Bins up (0 = auto)", "int", 0, (0, MAX_BINS), group=HISTOGRAM_GROUP,
    tip=f"Bins on the vertical axis. 0 = automatic (Freedman–Diaconis on that axis, at most {MAX_AUTO_BINS:,}).")
SCALE = ParameterSpec("colour_scale", "Colour scale", "choice", LINEAR, choices=(LINEAR, LOG), group=HISTOGRAM_GROUP,
                      tip="Events per bin on a linear or logarithmic colour scale; with log, empty bins are left "
                          "blank.")
COLOUR_MAP = "viridis"


@dataclass(frozen=True)
class PlaneCounts:
    histogram: Histogram2D
    shots: tuple[int, ...]
    total_shots: int
    reversed: tuple[str, ...] = ()  # axes whose manual min > max: shown over their full extent


def bins_text(item: Histogram2D) -> str:
    across, up = item.counts.shape
    how = ("automatic" if all(item.automatic) else "set" if not any(item.automatic)
           else "automatic across" if item.automatic[0] else "automatic up")
    return f"{across:,} × {up:,} bins ({how})"


def plane_title(data: PlaneCounts) -> str:
    """What the image shows, for its title (the input is on the dock's line and in Plot info)."""
    item = data.histogram
    summed = item.axes[2]
    flattened = (f"{summed} summed over {range_text(AXES.index(summed), *item.flattened)}" if item.flattened
                 else f"{summed} summed")
    parts = [shots_text(data.shots, data.total_shots), bins_text(item),
             f"{item.inside:,} of {item.total:,} events", flattened]
    if item.outside:
        parts.append(f"{item.outside:,} outside the range")
    return " · ".join(parts)


def notes(data: PlaneCounts) -> list[str]:
    return [f"⚠ {axis}: min > max, using full extent" for axis in data.reversed]


def plain_title(result: AnalysisResult) -> str:
    data: PlaneCounts = result.data
    return " · ".join([source_title(result, plane_title(data)), *notes(data)])


def axis_label(name: str) -> str:
    return f"{name} ({UNITS[AXES.index(name)]})"


def is_log(result: AnalysisResult) -> bool:
    return result.parameters.get(SCALE.name) == LOG


def image_of(result: AnalysisResult) -> npt.NDArray[np.float64]:
    """The image's values: counts, or log10 counts with empty bins NaN."""
    counts = result.data.histogram.counts
    return log_image(counts) if is_log(result) else counts.astype(np.float64)


def levels(values: npt.NDArray[np.float64]) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return 0.0, 1.0
    low, high = float(finite.min()), float(finite.max())
    return (low, high) if high > low else (low, low + 1.0)


class Histogram2DPlot(DatasetAnalysis):
    """A plane's histogram; each subclass names its ``plane`` ("XY", "XT" or "YT")."""

    @property
    @abstractmethod
    def plane(self) -> str: ...

    def get_metadata(self) -> ScriptMetadata:
        across, up, summed = PLANES[self.plane]
        return self.create_metadata(
            name=f"{self.plane} histogram",
            description=f"The loaded events' {across} against {up}, binned, {summed} summed over the chosen shots",
            group=group.NAME,
            file_path=__file__,
            analysis_id=f"helab.v2.{self.plane.lower()}_histogram",
            version="1",
        )

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def parameters(self, action_name: str) -> List[ParameterSpec]:
        return [*SHOT_SPECS, *RANGE, BINS_ACROSS, BINS_UP, SCALE]

    def describe_run(self, action_name: str, values: Mapping[str, Any], view: DatasetView) -> tuple[str, str]:
        across, up = int(values[BINS_ACROSS.name]), int(values[BINS_UP.name])
        bins = "bins auto" if not across and not up else f"bins {across or 'auto'} × {up or 'auto'}"
        settings = (shots_brief(values), range_brief(values), bins,
                    "log colour" if values.get(SCALE.name) == LOG else "")
        return selection_text(view, values), " · ".join(part for part in settings if part)

    def parameter_warnings(self, action_name: str, values: Mapping[str, Any]) -> List[str]:
        return list(range_warnings(values))

    def minimum_size(self, action_name: str) -> tuple[int, int]:
        return 240, 260  # An image and its colour bar under a title.

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        values = context.parameters
        shots = select_shots(context.view, values)
        events = context.view.events(shots)
        bounds = manual_bounds(values) if manual(values) else (None, None, None)
        item = histogram2d(events, self.plane, keep_fraction(values),
                           (int(values[BINS_ACROSS.name]), int(values[BINS_UP.name])),
                           (bounds[0], bounds[1], bounds[2]), context.check)
        return PlaneCounts(item, shots, len(context.view.shots), reversed_axes(values))

    def backends(self, action_name: str) -> Sequence[str]:
        return (PYQTGRAPH, PLOTLY, MATPLOTLIB)

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return self.draw(result, PYQTGRAPH, parent)

    def draw(self, result: AnalysisResult, backend: str, parent: Optional[QWidget] = None) -> QWidget:
        data: PlaneCounts = result.data
        if not data.histogram.summed:
            return empty_pane(empty_text(data.total_shots, len(data.shots), data.histogram.total)
                              or "No events inside the summed axis's bounds (View range)", parent)
        if backend == PLOTLY:
            return PlotlyPane(plane_plotly(result), parent=parent)
        if backend == MATPLOTLIB:
            return MatplotlibPane(plane_matplotlib(result), parent)
        across, up, _ = data.histogram.axes
        widget: Any = pg.GraphicsLayoutWidget(parent)
        widget.setBackground("w")
        widget.title_label = WrappingLabel("")
        widget.addItem(widget.title_label, row=0, col=0, colspan=2)
        plot = widget.addPlot(row=1, col=0)
        plot.setLabel("bottom", across, units=UNITS[AXES.index(across)])
        plot.setLabel("left", up, units=UNITS[AXES.index(up)])
        if self.plane == "XY":
            plot.setAspectLocked(True)  # Both lengths: equal scales.
        image = pg.ImageItem(axisOrder="col-major")  # image[across, up], as the counts are
        plot.addItem(image)
        values = image_of(result)
        bar = pg.ColorBarItem(values=levels(values), colorMap=COLOUR_MAP, interactive=False,
                              label="log₁₀ events" if is_log(result) else "Events")
        bar.setImageItem(image)
        widget.addItem(bar, row=1, col=1)
        widget.plane_plot, widget.plane_image, widget.plane_bar = plot, image, bar
        widget.plane_layout = (self.plane, is_log(result))
        fill(widget, result)
        return cast(QWidget, widget)

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        """A rerun (e.g. Live's next shots) updates the image in place, in every library: a zoom or pan stays,
        else the axes follow the new ranges. Another colour scale draws it anew."""
        data: PlaneCounts = result.data
        if not data.histogram.summed:
            return False
        if isinstance(widget, pg.GraphicsLayoutWidget):
            if getattr(widget, "plane_layout", None) != (self.plane, is_log(result)):
                return False
            fill(cast(Any, widget), result)
            return True
        return (plotly_update(widget, plane_plotly(result))
                or matplotlib_update(widget, lambda figure: plane_matplotlib(result, figure)))


def fill(widget: Any, result: AnalysisResult) -> None:
    data: PlaneCounts = result.data
    item = data.histogram
    widget.title_label.setText(plane_title(data) + notes_html(notes(data)))
    values = image_of(result)
    widget.plane_image.setImage(values, autoLevels=False)
    h0, h1 = float(item.h_edges[0]), float(item.h_edges[-1])
    v0, v1 = float(item.v_edges[0]), float(item.v_edges[-1])
    widget.plane_image.setRect(QRectF(h0, v0, h1 - h0, v1 - v0))
    widget.plane_bar.setLevels(levels(values))


def plane_plotly(result: AnalysisResult) -> go.Figure:
    data: PlaneCounts = result.data
    item = data.histogram
    across, up, _ = item.axes
    values = image_of(result)
    bar: dict[str, Any] = dict(title="log₁₀ events" if is_log(result) else "Events")
    finite = values[np.isfinite(values)]
    if is_log(result) and len(finite):
        decades = list(range(math.floor(float(finite.min())), math.ceil(float(finite.max())) + 1))
        bar.update(tickvals=decades, ticktext=[f"{10 ** decade:,}" if decade >= 0 else f"1e{decade}"
                                                for decade in decades])
    centres_h = (item.h_edges[:-1] + item.h_edges[1:]) / 2
    centres_v = (item.v_edges[:-1] + item.v_edges[1:]) / 2
    figure = go.Figure(go.Heatmap(
        z=values.T, x=centres_h, y=centres_v, colorscale=COLOUR_MAP.capitalize(), colorbar=bar,
        customdata=item.counts.T,
        hovertemplate=f"{across} %{{x:.6g}}<br>{up} %{{y:.6g}}<br>%{{customdata:,}} events<extra></extra>"))
    figure.update_layout(title=dict(text=plain_title(result), x=0.01, font=dict(size=13)), template="plotly_white",
                         margin=dict(l=60, r=20, t=50, b=50), uirevision=f"helab.v2.{item.plane.lower()}_histogram",
                         xaxis_title=axis_label(across), yaxis_title=axis_label(up))
    if item.plane == "XY":
        figure.update_yaxes(scaleanchor="x", scaleratio=1)
    return figure


def plane_matplotlib(result: AnalysisResult, figure: Any = None) -> Any:
    from matplotlib.colors import LogNorm

    data: PlaneCounts = result.data
    item = data.histogram
    across, up, _ = item.axes
    figure = mpl_figure(figure)
    axes = figure.add_subplot()
    counts = item.counts.T.astype(np.float64)
    if is_log(result):
        shown = np.where(counts > 0, counts, np.nan)
        norm: Any = LogNorm(vmin=max(1.0, float(np.nanmin(shown))) if np.isfinite(shown).any() else 1.0,
                            vmax=float(np.nanmax(shown)) if np.isfinite(shown).any() else 10.0)
    else:
        shown, norm = counts, None
    mesh = axes.pcolormesh(item.h_edges, item.v_edges, shown, cmap=COLOUR_MAP, norm=norm, shading="flat")
    figure.colorbar(mesh, ax=axes, label="Events")
    axes.set_xlabel(axis_label(across), fontsize=8)
    axes.set_ylabel(axis_label(up), fontsize=8)
    axes.tick_params(labelsize=7)
    if item.plane == "XY":
        axes.set_aspect("equal")
    figure.suptitle(plain_title(result), fontsize=9, wrap=True)
    return figure

