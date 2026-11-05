"""XY, XT and YT histograms (Basic plots v2, LR-13): the chosen shots' events binned in a plane, the third
axis summed over the selection (``helab.analysis.histogram2d``), with the DLD port's Density images' options
(Tony's choice): a Gaussian blur (σ in bins, the total kept), counts per bin or a rate per shot, and the colour
range compressed (sqrt, log, power γ) in the colour map only, so the colour bar reads real values. In s and m
with SI prefixes (Basic plots' units). Drawn with PyQtGraph (``ImageItem``) by default, or Plotly or
Matplotlib; updated in place as Live adds shots. XY keeps equal scales (both lengths); T runs across XT and YT.

The three plots are this module's ``Histogram1XY``, ``Histogram2XT`` and ``Histogram3YT``, so that their identity
names this file and carries its hash (an edit here is new code). They are numbered because the Scripts panel lists a
module's scripts in the order of their class names."""
from __future__ import annotations

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
from helab.analysis.histogram2d import (LINEAR, LOG, MAX_AUTO_BINS, PLANES, POWER, SCALES, Histogram2D, bin_area,
                                        blur_limit, blurred, compress, histogram2d, scale_text)
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.selection import (MANUAL, RANGE_GROUP, RANGE_MODE, SHOT_SPECS, keep_fraction, manual,
                                      manual_bounds, range_brief, range_specs, range_text, range_warnings,
                                      reversed_axes, select_shots, selection_text, shots_brief, shots_text)
from helab.analysis.stats import AXES, MAX_BINS, UNITS
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.scripts.standard.basic_plots import matplotlib_update, plotly_update
from helab.scripts.standard_v2 import group
from helab.scripts.standard_v2.common import notes_html, source_title

RANGE = range_specs(
    "Each shown axis covers the exact shortest range holding this share of its events; the summed axis isn't "
    "cut (every event of the chosen shots counts). 100 % covers every event.")
OUTSIDE = ParameterSpec(
    "include_outside", "Sum the whole summed axis", "bool", False, group=RANGE_GROUP, when=(RANGE_MODE.name, MANUAL),
    tip="On: the bounds set on the summed axis are left out, so every event of the chosen shots along it counts "
        "and the bounds cut only the two shown axes. Off: they limit the events summed (a T window on XY "
        "images one cloud).")
IMAGE_GROUP = "Image"
BINS_ACROSS = ParameterSpec(
    "bins_across", "Bins across (0 = auto)", "int", 0, (0, MAX_BINS), group=IMAGE_GROUP,
    tip=f"Bins on the horizontal axis. 0 = automatic (Freedman–Diaconis on that axis, at most {MAX_AUTO_BINS:,}).")
BINS_UP = ParameterSpec(
    "bins_up", "Bins up (0 = auto)", "int", 0, (0, MAX_BINS), group=IMAGE_GROUP,
    tip=f"Bins on the vertical axis. 0 = automatic (Freedman–Diaconis on that axis, at most {MAX_AUTO_BINS:,}).")
BLUR = ParameterSpec("blur", "Blur σ", "float", 0.0, (0.0, 50.0), " bins", group=IMAGE_GROUP,
                     tip="Gaussian blur of the image, its σ in bins; 0 = off. The total is kept (edges reflect). "
                         "At most a quarter of the image's longer side is used (the plot says so).")
COUNTS, PER_SHOT = "counts per bin", "rate per shot"
QUANTITY = ParameterSpec("quantity", "Show", "choice", COUNTS, choices=(COUNTS, PER_SHOT), group=IMAGE_GROUP,
                         tip="Counts per bin, or a rate per shot: counts / shots chosen / bin area (per m² for XY; "
                             "per m per s for XT and YT).")
COLOUR_GROUP = "Colour"
SCALE = ParameterSpec("colour_scale", "Colour scale", "choice", LINEAR, choices=SCALES, group=COLOUR_GROUP,
                      tip="Compresses the colour range only: the image's values stay linear and the colour bar "
                          "reads them. sqrt and power γ below 1 bring out faint regions; log spans the decades "
                          "below the maximum.")
GAMMA = ParameterSpec("gamma", "γ", "float", 0.5, (0.05, 5.0), group=COLOUR_GROUP, when=(SCALE.name, POWER),
                      tip="Colour position = value^γ (of the colour bar's range): below 1 brings out faint regions, "
                          "above 1 the bright ones.")
DECADES = ParameterSpec("log_decades", "Decades", "int", 3, (1, 8), group=COLOUR_GROUP, when=(SCALE.name, LOG),
                        tip="How many decades below the maximum the colours span; lower values share the darkest "
                            "colour.")
COLOUR_MAP = "viridis"
LUT_SIZE = 1024


@dataclass(frozen=True)
class PlaneCounts:
    """A plane's counts (``histogram``) and the image shown (``image``: blurred, per shot if chosen)."""
    histogram: Histogram2D
    image: npt.NDArray[np.float64]
    shots: tuple[int, ...]
    total_shots: int
    per_shot: bool = False
    blur: float = 0.0  # the σ used, in bins (0: none)
    notes: tuple[str, ...] = ()  # settings not followed as given

    @property
    def peak(self) -> float:
        return float(self.image.max()) if self.image.size else 0.0


@dataclass(frozen=True)
class Colours:
    """The colour scale chosen: compression, γ, decades."""
    scale: str = LINEAR
    gamma: float = 0.5
    decades: int = 3

    @classmethod
    def of(cls, values: Mapping[str, Any]) -> "Colours":
        return cls(str(values.get(SCALE.name, LINEAR)), float(values.get(GAMMA.name, GAMMA.default)),
                   int(values.get(DECADES.name, DECADES.default)))

    def text(self) -> str:
        return scale_text(self.scale, self.gamma, self.decades)


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
    if data.blur:
        parts.append(f"blur σ {data.blur:g} bins")
    return " · ".join(parts)


def notes(data: PlaneCounts) -> list[str]:
    return [f"⚠ {note}" for note in data.notes]


def plain_title(result: AnalysisResult) -> str:
    data: PlaneCounts = result.data
    return " · ".join([source_title(result, plane_title(data)), *notes(data)])


def axis_label(name: str) -> str:
    return f"{name} ({UNITS[AXES.index(name)]})"


def quantity_text(data: PlaneCounts) -> str:
    """The colour bar's quantity: events per bin, or per area per shot in s and m."""
    blur = " (blurred)" if data.blur else ""
    if not data.per_shot:
        return f"Events per bin{blur}"
    across, up, _ = data.histogram.axes
    area = "m²" if "T" not in (across, up) else "(m·s)"
    return f"Events / {area} / shot{blur}"


def bar_label(data: PlaneCounts, colours: Colours) -> str:
    """The quantity, and with a compressed colour scale, that only the colours are (the numbers are real)."""
    how = colours.text()
    return quantity_text(data) + (f" · colours {how}, values linear" if how else "")


def colour_positions(data: PlaneCounts, colours: Colours) -> npt.NDArray[np.float64]:
    """Each bin's place in the colour map (0…1): its value over the peak, compressed."""
    peak = data.peak
    return compress(data.image / peak if peak > 0 else np.zeros_like(data.image), colours.scale, colours.gamma,
                    colours.decades)


def viridis() -> Any:
    return pg.colormap.get(COLOUR_MAP)


def bar_map(colours: Colours) -> pg.ColorMap:
    """Viridis resampled so that a linear value shows the colour of its compressed position: the colour bar's
    gradient over its linear axis in real values (the image itself is drawn from ``colour_positions``)."""
    positions = np.linspace(0.0, 1.0, LUT_SIZE)
    picked = viridis().map(compress(positions, colours.scale, colours.gamma, colours.decades), mode="byte")
    return pg.ColorMap(positions, picked, name=f"{COLOUR_MAP} ({colours.scale})")


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
        return [*SHOT_SPECS, *RANGE, OUTSIDE, BINS_ACROSS, BINS_UP, BLUR, QUANTITY, SCALE, GAMMA, DECADES]

    def describe_run(self, action_name: str, values: Mapping[str, Any], view: DatasetView) -> tuple[str, str]:
        across, up = int(values[BINS_ACROSS.name]), int(values[BINS_UP.name])
        bins = "bins auto" if not across and not up else f"bins {across or 'auto'} × {up or 'auto'}"
        blur = float(values.get(BLUR.name, 0.0))
        colours = Colours.of(values)
        settings = (shots_brief(values), range_brief(values),
                    f"whole {PLANES[self.plane][2]}" if manual(values) and values.get(OUTSIDE.name) else "", bins,
                    f"blur σ {blur:g}" if blur else "", "per shot" if values.get(QUANTITY.name) == PER_SHOT else "",
                    f"colours {colours.text()}" if colours.text() else "")
        return selection_text(view, values), " · ".join(part for part in settings if part)

    def parameter_warnings(self, action_name: str, values: Mapping[str, Any]) -> List[str]:
        return list(range_warnings(values))

    def minimum_size(self, action_name: str) -> tuple[int, int]:
        return 240, 260  # An image and its colour bar under a title.

    def compute(self, action_name: str, context: AnalysisContext) -> Any:
        values = context.parameters
        shots = select_shots(context.view, values)
        events = context.view.events(shots)
        bounds = list(manual_bounds(values)) if manual(values) else [None, None, None]
        if values.get(OUTSIDE.name):
            bounds[AXES.index(PLANES[self.plane][2])] = None  # The bounds cut only the shown axes.
        # Manual: a shown axis without bounds (unset or reversed) covers its full extent, as v1's and the note say.
        item = histogram2d(events, self.plane, 1.0 if manual(values) else keep_fraction(values),
                           (int(values[BINS_ACROSS.name]), int(values[BINS_UP.name])),
                           (bounds[0], bounds[1], bounds[2]), context.check)
        context.check()
        wanted = float(values.get(BLUR.name, 0.0))
        sigma = min(wanted, blur_limit(item.counts.shape)) if wanted > 0 else 0.0
        kept = (f"blur σ {wanted:g} bins is over a quarter of the image: {sigma:g} used",) if sigma < wanted else ()
        image = blurred(item.counts.astype(np.float64), sigma)
        per_shot = values.get(QUANTITY.name) == PER_SHOT
        if per_shot and shots:
            image = image / len(shots) / bin_area(item)
        warnings = tuple(f"{axis}: min > max, using full extent" for axis in reversed_axes(values))
        return PlaneCounts(item, image, shots, len(context.view.shots), per_shot, sigma, (*warnings, *kept))

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
        # image[across, up], as the counts are; drawn from each bin's compressed colour position over plain
        # viridis (exact at any depth), the bar a legend in real values, never attached to the image.
        image = pg.ImageItem(axisOrder="col-major")
        image.setLookupTable(viridis().getLookupTable(nPts=LUT_SIZE, alpha=False))
        plot.addItem(image)
        colours = Colours.of(result.parameters)
        bar = pg.ColorBarItem(values=(0.0, 1.0), colorMap=bar_map(colours), interactive=False,
                              label=bar_label(data, colours))
        widget.addItem(bar, row=1, col=1)
        widget.plane_plot, widget.plane_image, widget.plane_bar = plot, image, bar
        widget.plane_layout = (self.plane, colours)
        fill(widget, result)
        return cast(QWidget, widget)

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        """A rerun (e.g. Live's next shots) updates the image in place, in every library: a zoom or pan stays,
        else the axes follow the new ranges. Another colour scale draws it anew in PyQtGraph."""
        data: PlaneCounts = result.data
        if not data.histogram.summed:
            return False
        if isinstance(widget, pg.GraphicsLayoutWidget):
            if getattr(widget, "plane_layout", None) != (self.plane, Colours.of(result.parameters)):
                return False
            fill(cast(Any, widget), result)
            return True
        return (plotly_update(widget, plane_plotly(result))
                or matplotlib_update(widget, lambda figure: plane_matplotlib(result, figure)))


class Histogram1XY(Histogram2DPlot):
    """The XY histogram: X across, Y up (equal scales), T summed."""

    @property
    def plane(self) -> str:
        return "XY"


class Histogram2XT(Histogram2DPlot):
    """The XT histogram: T across, X up, Y summed."""

    @property
    def plane(self) -> str:
        return "XT"


class Histogram3YT(Histogram2DPlot):
    """The YT histogram: T across, Y up, X summed."""

    @property
    def plane(self) -> str:
        return "YT"


def fill(widget: Any, result: AnalysisResult) -> None:
    data: PlaneCounts = result.data
    item = data.histogram
    colours = Colours.of(result.parameters)
    widget.title_label.setText(plane_title(data) + notes_html(notes(data)))
    widget.plane_image.setImage(colour_positions(data, colours), levels=(0.0, 1.0))
    h0, h1 = float(item.h_edges[0]), float(item.h_edges[-1])
    v0, v1 = float(item.v_edges[0]), float(item.v_edges[-1])
    widget.plane_image.setRect(QRectF(h0, v0, h1 - h0, v1 - v0))
    peak = data.peak
    widget.plane_bar.setLevels((0.0, peak if peak > 0 else 1.0))
    widget.plane_bar.getAxis("left").setLabel(bar_label(data, colours))  # (ColorBarItem labels its left axis.)


def plotly_scale(colours: Colours, stops: int = 64) -> list[list[Any]]:
    """A Plotly colour scale over the bar's linear range showing each value's compressed colour."""
    from plotly.colors import sample_colorscale

    positions = np.linspace(0.0, 1.0, stops)
    picked = sample_colorscale("Viridis", compress(positions, colours.scale, colours.gamma, colours.decades).tolist())
    return [[float(position), colour] for position, colour in zip(positions, picked)]


def plane_plotly(result: AnalysisResult) -> go.Figure:
    data: PlaneCounts = result.data
    item = data.histogram
    across, up, _ = item.axes
    colours = Colours.of(result.parameters)
    centres_h = (item.h_edges[:-1] + item.h_edges[1:]) / 2
    centres_v = (item.v_edges[:-1] + item.v_edges[1:]) / 2
    figure = go.Figure(go.Heatmap(
        z=data.image.T, x=centres_h, y=centres_v, colorscale=plotly_scale(colours), zmin=0.0,
        zmax=data.peak if data.peak > 0 else 1.0, colorbar=dict(title=bar_label(data, colours)),
        customdata=item.counts.T,
        hovertemplate=f"{across} %{{x:.6g}}<br>{up} %{{y:.6g}}<br>%{{customdata:,}} events · %{{z:.4g}}"
                      f"<extra></extra>"))
    figure.update_layout(title=dict(text=plain_title(result), x=0.01, font=dict(size=13)), template="plotly_white",
                         margin=dict(l=60, r=20, t=50, b=50), uirevision=f"helab.v2.{item.plane.lower()}_histogram",
                         xaxis_title=axis_label(across), yaxis_title=axis_label(up))
    if item.plane == "XY":
        figure.update_yaxes(scaleanchor="x", scaleratio=1)
    return figure


def plane_matplotlib(result: AnalysisResult, figure: Any = None) -> Any:
    from matplotlib import colors as typed_colors

    mpl_colors: Any = typed_colors  # (Its classes are untyped.)
    data: PlaneCounts = result.data
    item = data.histogram
    across, up, _ = item.axes
    colours = Colours.of(result.parameters)
    peak = data.peak if data.peak > 0 else 1.0
    if colours.scale == LOG:
        norm: Any = mpl_colors.LogNorm(vmin=peak * 10.0 ** -colours.decades, vmax=peak, clip=True)
    elif colours.scale == LINEAR:
        norm = mpl_colors.Normalize(vmin=0.0, vmax=peak)
    else:
        gamma = 0.5 if colours.scale != POWER else colours.gamma
        norm = mpl_colors.PowerNorm(gamma, vmin=0.0, vmax=peak, clip=True)
    from matplotlib import colormaps

    cmap = colormaps[COLOUR_MAP].with_extremes(bad=colormaps[COLOUR_MAP](0.0), under=colormaps[COLOUR_MAP](0.0))
    figure = mpl_figure(figure)
    axes = figure.add_subplot()
    shown = np.where(data.image.T > 0, data.image.T, np.nan) if colours.scale == LOG else data.image.T
    mesh = axes.pcolormesh(item.h_edges, item.v_edges, shown, cmap=cmap, norm=norm, shading="flat")
    figure.colorbar(mesh, ax=axes, label=quantity_text(data))
    axes.set_xlabel(axis_label(across), fontsize=8)
    axes.set_ylabel(axis_label(up), fontsize=8)
    axes.tick_params(labelsize=7)
    if item.plane == "XY":
        axes.set_aspect("equal")
    figure.suptitle(plain_title(result), fontsize=9, wrap=True)
    return figure
