"""Basic plots v2's XY, XT and YT histograms (LR-13): the chosen shots' events binned in a plane, the third axis
summed over the selection; ranges from auto-crop (the summed axis whole) or manual bounds (the summed axis's
bounds limiting the events summed); automatic or set bins; linear or log colour; every library, in place."""
from __future__ import annotations

from typing import Any, Callable, cast

import numpy as np
import pyqtgraph as pg
import pytest
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from helab.analysis.backends import BACKENDS, MATPLOTLIB, PLOTLY, PYQTGRAPH, MatplotlibPane
from helab.analysis.dataset_view import DatasetView, build_view
from helab.analysis.histogram2d import MAX_AUTO_BINS, PLANES, histogram2d, log_image
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import effective
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.stats import shortest_range
from helab.scripts import standard_v2
from helab.scripts.standard_v2 import histograms_2d, xt_histogram, xy_histogram, yt_histogram
from helab.scripts.standard_v2.histograms_2d import Histogram2DPlot
from helab.utils.folder_cache import Dataset

PLOTS: dict[str, Callable[[], Histogram2DPlot]] = {"XY": xy_histogram.XYHistogram, "XT": xt_histogram.XTHistogram, "YT": yt_histogram.YTHistogram}


def events(seed: int = 3, count: int = 4_000) -> Any:
    """T around 2.1 s (two clouds), X and Y around 0 with a wider X; a few far events."""
    rng = np.random.default_rng(seed)
    t = np.concatenate((rng.normal(2.10, 0.002, count // 2), rng.normal(2.13, 0.002, count // 2)))
    x, y = rng.normal(0.0, 0.004, count), rng.normal(0.001, 0.002, count)
    data = np.column_stack((t, x, y))
    data[:10] += 1.0  # Far away: auto-crop leaves them out of the shown ranges.
    data.setflags(write=False)
    return data


def view(shots: range = range(1, 5)) -> DatasetView:
    data = {shot: events(shot) for shot in shots}
    fingerprint = [[shot, 100 + shot, 1_000 + shot] for shot in shots]
    return build_view(Dataset("/data/root/run_2d", "sig-1", data, {"fingerprint": fingerprint, "source": "files",
                                                                   "loaded_at": 1_700_000_000.0}, 0))


def result_of(script: Histogram2DPlot, data: DatasetView, values: dict[str, Any] | None = None) -> AnalysisResult:
    context = AnalysisContext("a1", "Plot", data, effective(script.parameters("Plot"), values),
                              script.get_metadata().identity())
    return AnalysisResult.of(context, "completed", script.compute("Plot", context))


# helab.analysis.histogram2d


@pytest.mark.parametrize("plane", list(PLANES))
def test_counts_match_numpy_and_the_summed_axis_is_whole(plane: str) -> None:
    data = events()
    item = histogram2d(data, plane, 0.99)
    across, up, summed = (("T", "X", "Y").index(name) for name in PLANES[plane])
    assert item.axes == PLANES[plane] and item.total == item.summed == len(data) and item.flattened is None
    # Each shown axis: its shortest range holding 99 % of its events, as the 1D histograms.
    assert (item.h_edges[0], item.h_edges[-1]) == pytest.approx(shortest_range(data[:, across], 0.99))
    assert (item.v_edges[0], item.v_edges[-1]) == pytest.approx(shortest_range(data[:, up], 0.99))
    expected, _, _ = np.histogram2d(data[:, across], data[:, up], bins=(item.h_edges, item.v_edges))
    assert np.array_equal(item.counts, expected.astype(np.int64))
    assert item.inside + item.outside == len(data) and item.outside >= 10
    assert all(item.automatic) and 1 <= item.counts.shape[0] <= MAX_AUTO_BINS
    del summed


def test_set_bins_and_manual_bounds_on_the_summed_axis() -> None:
    data = events()
    item = histogram2d(data, "XY", 0.99, (40, 30), (None, (-0.01, 0.01), (-0.01, 0.01)))
    assert item.counts.shape == (40, 30) and item.automatic == (False, False)
    assert (item.h_edges[0], item.h_edges[-1]) == (-0.01, 0.01)
    # A T window on XY images one cloud: only the events inside it are summed.
    window = (2.09, 2.11)
    one = histogram2d(data, "XY", 0.99, (40, 30), (window, (-0.01, 0.01), (-0.01, 0.01)))
    inside = int(((data[:, 0] >= window[0]) & (data[:, 0] <= window[1])).sum())
    assert one.summed == inside and one.flattened == window and one.total == len(data)
    assert one.inside < item.inside


def test_empty_and_single_valued_input() -> None:
    empty = histogram2d(np.empty((0, 3)), "XT", 0.99)
    assert empty.total == empty.summed == empty.inside == 0 and empty.counts.sum() == 0
    same = histogram2d(np.array([[1.0, 2.0, 3.0]] * 5), "XY", 0.99)
    assert same.inside == 5 and same.h_edges[-1] > same.h_edges[0]


def test_log_image_leaves_empty_bins_blank() -> None:
    image = log_image(np.array([[0, 1], [10, 100]], dtype=np.int64))
    assert np.isnan(image[0, 0]) and image[0, 1] == 0.0 and image[1, 0] == 1.0 and image[1, 1] == 2.0


def test_bins_are_capped() -> None:
    rng = np.random.default_rng(1)
    data = np.column_stack((rng.uniform(0, 1, 200_000), rng.uniform(0, 1, 200_000), rng.uniform(0, 1, 200_000)))
    item = histogram2d(data, "XY", 1.0)
    assert max(item.counts.shape) <= MAX_AUTO_BINS


# The plots


def test_three_plots_in_the_package_in_order() -> None:
    names = [module.__name__.rsplit(".", 1)[1] for module in standard_v2.MODULES]
    assert names.index("xy_histogram") < names.index("xt_histogram") < names.index("yt_histogram")
    for plane, cls in PLOTS.items():
        metadata = cls().get_metadata()
        assert (metadata.name, metadata.analysis_id, metadata.version, metadata.group) == (
            f"{plane} histogram", f"helab.v2.{plane.lower()}_histogram", "1", "Basic plots v2")
    names = [spec.name for spec in PLOTS["XY"]().parameters("Plot")]
    assert names[-3:] == ["bins_across", "bins_up", "colour_scale"] and "range_mode" in names


@pytest.mark.parametrize("plane", list(PLOTS))
def test_the_run_sums_the_chosen_shots(plane: str) -> None:
    script = PLOTS[plane]()
    data = view()
    result = result_of(script, data, {"shots": "last N", "last_shots": 2})
    item = result.data.histogram
    assert result.data.shots == (3, 4) and item.total == len(data.shots[3]) + len(data.shots[4])
    used, settings = script.describe_run("Plot", effective(script.parameters("Plot"), {"colour_scale": "log"}), data)
    assert "bins auto" in settings and "log colour" in settings and "auto-crop 99 %" in settings
    title = histograms_2d.plane_title(result.data)
    assert f"{PLANES[plane][2]} summed" in title and "bins (automatic)" in title and "run_2d" not in title


@pytest.mark.parametrize("scale", ["linear", "log"])
@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("plane", list(PLOTS))
def test_every_library_draws_and_updates_in_place(plane: str, backend: str, scale: str, qtbot: QtBot) -> None:
    script = PLOTS[plane]()
    first = result_of(script, view(range(1, 3)), {"colour_scale": scale})
    widget = script.draw(first, backend)
    qtbot.addWidget(widget)
    assert isinstance(widget, {PLOTLY: PlotlyPane, MATPLOTLIB: MatplotlibPane}.get(backend, pg.GraphicsLayoutWidget))
    if isinstance(widget, MatplotlibPane):
        widget.canvas.draw()  # type: ignore[no-untyped-call]
    assert script.update(widget, result_of(script, view(range(1, 4)), {"colour_scale": scale}))
    if backend == PYQTGRAPH:
        other = "log" if scale == "linear" else "linear"
        assert not script.update(widget, result_of(script, view(range(1, 4)), {"colour_scale": other}))


def test_pyqtgraph_image_orientation_aspect_and_update(qtbot: QtBot) -> None:
    for plane, cls in PLOTS.items():
        script = cls()
        result = result_of(script, view())
        widget: Any = script.draw(result, PYQTGRAPH)
        qtbot.addWidget(widget)
        item = result.data.histogram
        image = widget.plane_image
        assert image.image.shape == item.counts.shape  # [across, up] (col-major)
        rect = image.mapRectToParent(image.boundingRect())
        assert rect.left() == pytest.approx(item.h_edges[0]) and rect.right() == pytest.approx(item.h_edges[-1])
        assert rect.top() == pytest.approx(item.v_edges[0]) and rect.bottom() == pytest.approx(item.v_edges[-1])
        plot = widget.plane_plot
        assert plot.getAxis("bottom").labelText == PLANES[plane][0] and plot.getAxis("left").labelText == PLANES[plane][1]
        assert bool(plot.getViewBox().state["aspectLocked"]) == (plane == "XY")
        assert "run_2d" not in widget.title_label.text
        assert script.update(widget, result_of(script, view(range(1, 6))))
        assert widget.plane_image is image  # The same items, the new image.


def test_log_scale_blank_bins_in_pyqtgraph(qtbot: QtBot) -> None:
    script = PLOTS["XY"]()
    widget: Any = script.draw(result_of(script, view(), {"colour_scale": "log"}), PYQTGRAPH)
    qtbot.addWidget(widget)
    assert np.isnan(widget.plane_image.image).any()
    low, high = widget.plane_bar.levels()
    assert low >= 0 and high > low


def test_plotly_and_matplotlib_keep_the_input_in_their_titles() -> None:
    script = PLOTS["XT"]()
    result = result_of(script, view(), {"colour_scale": "log"})
    figure: Any = histograms_2d.plane_plotly(result)
    assert "run_2d" in figure.layout.title.text and figure.data[0].type == "heatmap"
    assert figure.layout.xaxis.title.text == "T (s)" and figure.layout.yaxis.title.text == "X (m)"
    drawn = histograms_2d.plane_matplotlib(result)
    assert "run_2d" in drawn.texts[0].get_text() and drawn.axes[0].get_xlabel() == "T (s)"
    xy: Any = histograms_2d.plane_plotly(result_of(PLOTS["XY"](), view()))
    assert xy.layout.yaxis.scaleanchor == "x"


def test_nothing_to_sum_says_why(qtbot: QtBot) -> None:
    script = PLOTS["XY"]()
    result = result_of(script, view(), {"range_mode": "manual", "t_min": 5.0, "t_max": 6.0})
    widget = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    assert isinstance(widget, QLabel) and "summed axis" in widget.text()
    none = result_of(script, view(), {"shots": "range", "first_shot": 50, "last_shot": 60})
    label = script.draw(none, PYQTGRAPH)
    qtbot.addWidget(label)
    assert isinstance(label, QLabel) and "chosen" in label.text()


def test_the_input_is_left_unchanged() -> None:
    data = view()
    before = {shot: np.array(values) for shot, values in data.shots.items()}
    for cls in PLOTS.values():
        result_of(cls(), data, {"range_mode": "manual", "t_min": 2.0, "t_max": 2.2})
    assert all(np.array_equal(before[shot], data.shots[shot]) for shot in before)
