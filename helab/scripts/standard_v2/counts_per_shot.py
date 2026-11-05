"""Counts per shot (Basic plots v2): the events in each chosen shot against its shot ID or its time
(X axis), with the shots whose time is their TXY file's marked. Drawn with PyQtGraph by default, or
Plotly or Matplotlib (Drawing › Library), updated in place as Live adds shots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, cast

import numpy as np
import numpy.typing as npt
import plotly.graph_objs as go
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget

from helab.analysis.backends import MATPLOTLIB, PLOTLY, PYQTGRAPH, MatplotlibPane, mpl_colour, mpl_figure, rgb, set_title
from helab.analysis.dataset_view import DatasetView
from helab.analysis.empty import empty_pane, empty_text
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.selection import SHOT_SPECS, select_shots, selection_text, shots_brief, shots_text
from helab.analysis.shot_axis import (SHOT_TIME, TOOLTIP, ShotAxis, axis_brief, axis_mode, fallback_text, shot_axis,
                                      x_axis_spec)
from helab.analysis.stats import counts_per_shot
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.scripts.standard.basic_plots import matplotlib_update, plotly_update
from helab.scripts.standard_v2 import group
from helab.scripts.standard_v2.common import (ShotSeries, bottom_axis, matplotlib_axis, matplotlib_series, notes_html,
                                              plotly_axis, plotly_series, source_title)

PLOT_GROUP = "Plot"
X_AXIS = x_axis_spec(PLOT_GROUP)
COLOUR = (40, 90, 170)
UI_REVISION = "helab.v2.counts_per_shot"  # Constant: a newer Plotly figure keeps the user's zoom and pan.


@dataclass(frozen=True)
class ShotCounts:
    """The chosen shots' events, in drawing order (``axis``)."""
    axis: ShotAxis
    counts: npt.NDArray[np.int64]
    unsettled_files: int
    total_shots: int  # the shots loaded
    chosen: int  # the shots the Shots settings chose (by time, some may have no time)

    @property
    def total(self) -> int:
        return int(self.counts.sum())


def counts_title(data: ShotCounts) -> str:
    title = f"{shots_text(sorted(data.axis.shots.tolist()), data.total_shots)} · {data.total:,} events"
    if data.unsettled_files:
        title += f" · {data.unsettled_files} files still being written left out"
    return title


def notes(data: ShotCounts) -> list[str]:
    return data.axis.notes()


def plain_title(result: AnalysisResult) -> str:
    """The title for a figure that leaves HeLab: the input first, the notes after."""
    data: ShotCounts = result.data
    return " · ".join([source_title(result, counts_title(data)), *notes(data)])


class CountsPerShot(DatasetAnalysis):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata(
            name="Counts per shot",
            description="Number of events in each loaded shot, against its shot ID or when it was taken",
            group=group.NAME,
            file_path=__file__,
            analysis_id="helab.v2.counts_per_shot",
            version="1",
        )

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def parameters(self, action_name: str) -> List[ParameterSpec]:
        return [*SHOT_SPECS, X_AXIS]

    def describe_run(self, action_name: str, values: Mapping[str, Any], view: DatasetView) -> tuple[str, str]:
        used = selection_text(view, values)
        if axis_mode(values) == SHOT_TIME:
            fallbacks = len(view.fallback_times(select_shots(view, values)))
            used += f" · ⚠ {fallback_text(fallbacks)}" if fallbacks else ""
        settings = (shots_brief(values), axis_brief(values))
        return used, " · ".join(part for part in settings if part)

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        view = context.view
        chosen = select_shots(view, context.parameters)
        axis = shot_axis(view, chosen, axis_mode(context.parameters))
        _, counts = counts_per_shot(view, axis.shots.tolist())
        return ShotCounts(axis, counts, view.provenance.unsettled_files, len(view.shots), len(chosen))

    def backends(self, action_name: str) -> Sequence[str]:
        return (PYQTGRAPH, PLOTLY, MATPLOTLIB)

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        return self.draw(result, PYQTGRAPH, parent)

    def draw(self, result: AnalysisResult, backend: str, parent: Optional[QWidget] = None) -> QWidget:
        data: ShotCounts = result.data
        if not data.total:
            # No shots, none chosen, none with a time, or chosen shots without events: say which.
            untimed = data.chosen and not len(data.axis.shots)
            return empty_pane("None of the chosen shots has a time" if untimed
                              else empty_text(data.total_shots, data.chosen, 0), parent)
        if backend == PLOTLY:
            return PlotlyPane(counts_plotly(result), parent=parent)
        if backend == MATPLOTLIB:
            return MatplotlibPane(counts_matplotlib(result), parent)
        plot: Any = pg.PlotWidget(parent, axisItems=bottom_axis(data.axis))
        plot.setBackground("w")
        plot.setLabel("bottom", data.axis.label)
        plot.setLabel("left", "Events")
        plot.showGrid(x=True, y=True, alpha=0.3)
        if data.axis.by_time:
            plot.setToolTip(TOOLTIP)
        plot.counts_series = ShotSeries(plot, COLOUR)
        plot.axis_mode = data.axis.mode
        fill(plot, data)
        return cast(QWidget, plot)

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        """A rerun (e.g. Live's next shots) updates the plot in place, in every library: a zoom or pan stays,
        else the axes follow the new data. Another X axis draws it anew."""
        data: ShotCounts = result.data
        if not data.total:
            return False
        if isinstance(widget, pg.PlotWidget):
            if getattr(widget, "axis_mode", None) != data.axis.mode or not hasattr(widget, "counts_series"):
                return False
            fill(cast(Any, widget), data)
            return True
        return (plotly_update(widget, counts_plotly(result))
                or matplotlib_update(widget, lambda figure: counts_matplotlib(result, figure)))


def fill(plot: Any, data: ShotCounts) -> None:
    set_title(plot, counts_title(data) + notes_html(notes(data)))
    plot.counts_series.set(data.axis, data.counts)


def counts_plotly(result: AnalysisResult) -> go.Figure:
    data: ShotCounts = result.data
    figure = go.Figure([go.Scatter(**trace) for trace in plotly_series(
        data.axis, data.counts, colour=rgb(COLOUR), name="events", value_label="%{y:,} events")])
    figure.update_layout(title=dict(text=plain_title(result), x=0.01, font=dict(size=13)),
                         yaxis_title="Events", template="plotly_white", showlegend=False,
                         margin=dict(l=60, r=20, t=50, b=50), uirevision=UI_REVISION)
    figure.update_xaxes(**plotly_axis(data.axis))
    return figure


def counts_matplotlib(result: AnalysisResult, figure: Any = None) -> Any:
    data: ShotCounts = result.data
    figure = mpl_figure(figure)
    axes = figure.add_subplot()
    matplotlib_series(axes, data.axis, data.counts, mpl_colour(COLOUR), linewidth=1)
    matplotlib_axis(axes, data.axis)
    axes.set_ylabel("Events", fontsize=8)
    axes.grid(True, alpha=0.3)
    figure.suptitle(plain_title(result), fontsize=9, wrap=True)
    return figure
