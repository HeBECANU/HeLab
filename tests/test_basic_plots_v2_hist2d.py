"""Basic plots v2's XY, XT, YT histograms (LR-13): one plot of the chosen shots' events binned in up to three planes,
each turned on or off, the third axis summed over the selection; ranges from auto-crop (the summed axis whole) or manual bounds (the summed axis's
bounds limiting the events summed, unless "Sum the whole summed axis"); automatic or set bins; the DLD port's
image options (Tony's choice): blur filters, each on by itself, chained in the order set (``image_filters``), counts or a rate per shot, colour compression in the colour map only;
every library, in place."""
from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
import pytest
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from helab.analysis.backends import BACKENDS, MATPLOTLIB, PLOTLY, PYQTGRAPH, MatplotlibPane
from helab.analysis.dataset_view import DatasetView, build_view
from helab.analysis.identity import file_hash
from helab.analysis import image_filters
from helab.analysis.histogram2d import (LINEAR, LOG, MAX_AUTO_BINS, PLANES, POWER, SCALES, SQRT, bin_area, compress,
                                        histogram2d, scale_text)
from helab.analysis.image_filters import ADAPTIVE, BOX, DENOISE, FILTERS, GAUSSIAN, MEDIAN, UNITS, Step
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import effective
from helab.analysis.results import AnalysisContext, AnalysisResult, Cancelled
from helab.analysis.stats import shortest_range
from helab.scripts import standard_v2
from helab.scripts.standard_v2 import histograms_2d
from helab.scripts.scripts_manager import ScriptsManager
from helab.scripts.standard_v2.histograms_2d import DENSITY, DOTS, NO_COLOUR, SUMMED, PlaneCounts, PlaneHistograms
from helab.utils.folder_cache import Dataset


def only(plane: str) -> dict[str, Any]:
    """The values that turn on ``plane`` alone."""
    return {f"show_{name.lower()}": name == plane for name in PLANES}


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


def result_of(script: PlaneHistograms, data: DatasetView, values: dict[str, Any] | None = None) -> AnalysisResult:
    context = AnalysisContext("a1", "Plot", data, effective(script.parameters("Plot"), values),
                              script.get_metadata().identity())
    return AnalysisResult.of(context, "completed", script.compute("Plot", context))


def plane_of(plane: str, data: DatasetView, values: dict[str, Any] | None = None) -> PlaneCounts:
    """``plane``'s counts in a run showing it alone."""
    items = result_of(PlaneHistograms(), data, {**only(plane), **(values or {})}).data.items
    assert [item.histogram.plane for item in items] == [plane]
    item: PlaneCounts = items[0]
    return item


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


def test_colour_compression_is_monotonic_from_0_to_1() -> None:
    x = np.linspace(0.0, 1.0, 101)
    for scale in SCALES:
        y = compress(x, scale, 0.4, 2)
        assert y[0] == pytest.approx(0.0, abs=1e-12) and y[-1] == pytest.approx(1.0) and (np.diff(y) >= 0).all()
    assert compress(np.array([0.25]), SQRT)[0] == pytest.approx(0.5)
    assert compress(np.array([0.01]), LOG, decades=2)[0] == pytest.approx(0.0)  # Two decades below: darkest.
    assert compress(np.array([0.1]), LOG, decades=2)[0] == pytest.approx(0.5)
    assert compress(np.array([0.25]), POWER, gamma=2.0)[0] == pytest.approx(0.0625)
    assert np.array_equal(compress(x, LINEAR), x)
    assert scale_text(LINEAR) == "" and scale_text(LOG, decades=3) == "log, 3 decades"
    assert scale_text(POWER, gamma=0.5) == "power γ 0.5" and scale_text(SQRT) == "sqrt"


def spot(shape: tuple[int, int] = (40, 30)) -> Any:
    """A Gaussian spot of counts on a faint Poisson floor, and one hot bin."""
    rng = np.random.default_rng(5)
    h, v = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    counts = rng.poisson(1.0 + 80.0 * np.exp(-((h - 20) ** 2 + (v - 15) ** 2) / 18.0)).astype(np.float64)
    counts[5, 5] = 500.0
    return counts


def step(kind: str, order: int = 0, **values: Any) -> Step:
    return Step(kind, order, text=kind, **values)


@pytest.mark.parametrize("kind", [kind for kind in FILTERS if kind != MEDIAN])
def test_every_filter_but_the_median_keeps_the_total(kind: str) -> None:
    counts = spot()
    image, texts, notes = image_filters.apply(counts, [step(kind, sigma=(1.5, 1.5), size=3)])
    assert image.sum() == pytest.approx(counts.sum()) and image.max() < counts.max() and (image >= 0).all()
    assert texts == (kind,) and notes == ()
    assert image_filters.apply(counts, [])[0] is not counts and np.array_equal(image_filters.apply(counts, [])[0],
                                                                                 counts)


def test_the_median_takes_out_a_hot_bin_and_keeps_the_spot() -> None:
    counts = spot()
    image = image_filters.apply(counts, [step(MEDIAN, size=3)])[0]
    assert image[5, 5] < 10 and image[20, 15] > 0.5 * counts[20, 15]
    assert image.sum() != pytest.approx(counts.sum())  # (It doesn't keep the total.)


def test_the_adaptive_kde_smooths_faint_regions_more_than_bright_ones() -> None:
    counts = spot()
    plain = image_filters.apply(counts, [step(GAUSSIAN, sigma=(2.0, 2.0))])[0]
    adapted = image_filters.apply(counts, [step(ADAPTIVE, sigma=(2.0, 2.0), alpha=0.5)])[0]
    assert adapted[20, 15] > plain[20, 15]  # The bright core is kept sharper...
    floor = (slice(30, 40), slice(0, 10))
    assert adapted[floor].std() < plain[floor].std()  # ...and the faint floor smoothed more.
    flat = image_filters.apply(counts, [step(ADAPTIVE, sigma=(2.0, 2.0), alpha=0.0)])[0]
    assert np.allclose(flat, plain)  # α 0: a plain Gaussian.


def test_the_adaptive_kde_picks_the_nearest_sigma_step() -> None:
    """Each bin's σ step is the ladder's nearest (on a log scale), as the broadcast over every step found it."""
    rng = np.random.default_rng(4)
    factor = np.exp(rng.uniform(np.log(1 / image_filters.ADAPTIVE_RANGE), np.log(image_filters.ADAPTIVE_RANGE),
                                (300, 200)))
    ladder = np.geomspace(1 / image_filters.ADAPTIVE_RANGE, image_filters.ADAPTIVE_RANGE, image_filters.LEVELS)
    nearest = np.abs(np.log(factor)[..., None] - np.log(ladder)).argmin(axis=-1)
    assert np.array_equal(image_filters.levels(factor.copy()), nearest)
    assert image_filters.levels(ladder.copy()).tolist() == list(range(image_filters.LEVELS))


def test_the_adaptive_kde_needs_a_few_images_of_memory() -> None:
    """Not one image per σ step (the broadcast over the 9 steps peaked at about 20 images)."""
    import tracemalloc

    rng = np.random.default_rng(5)
    counts = rng.poisson(rng.uniform(0.0, 3.0, (600, 600))).astype(np.float64)
    tracemalloc.start()
    try:
        image_filters.apply(counts, [step(ADAPTIVE, sigma=(2.0, 2.0), alpha=0.5)])
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 12 * counts.nbytes  # (About 8 here: scipy's Gaussian alone takes 4.)


def test_the_filters_can_be_cancelled_between_steps_and_sigma_steps() -> None:
    calls: list[int] = []

    def check() -> None:
        calls.append(1)
        if len(calls) == 4:
            raise InterruptedError

    with pytest.raises(InterruptedError):
        image_filters.apply(spot(), [step(GAUSSIAN, sigma=(1.0, 1.0)), step(ADAPTIVE, sigma=(2.0, 2.0))], check)
    # Before the Gaussian, before the adaptive KDE, then before each of its σ steps: cancelled at the second.
    assert len(calls) == 4
    calls.clear()
    image_filters.apply(spot(), [step(GAUSSIAN, sigma=(1.0, 1.0)), step(MEDIAN, size=3)], lambda: calls.append(1))
    assert len(calls) == 2


def test_the_plot_cancels_inside_the_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """The run's check reaches the filters: a cancel during the adaptive KDE stops the plot there."""
    script = PlaneHistograms()
    context = AnalysisContext("a1", "Plot", view(),
                              effective(script.parameters("Plot"), {**only("XY"), "blur_adaptive": True}),
                              script.get_metadata().identity())
    gaussian = image_filters.gaussian

    def cancelling(image: Any, sigma: tuple[float, float]) -> Any:
        context.cancel_event.set()  # (Cancelled during the pilot blur: the next σ step's check stops it.)
        return gaussian(image, sigma)

    monkeypatch.setattr(image_filters, "gaussian", cancelling)
    with pytest.raises(Cancelled):
        script.compute("Plot", context)


def test_denoise_flattens_poisson_noise() -> None:
    rng = np.random.default_rng(2)
    counts = rng.poisson(4.0, (60, 60)).astype(np.float64)
    image = image_filters.apply(counts, [step(DENOISE, sigma=(2.0, 2.0))])[0]
    assert image.std() < 0.5 * counts.std() and image.mean() == pytest.approx(counts.mean())


def test_linear_filters_commute_and_the_others_dont() -> None:
    counts = spot()
    gauss, box, median = step(GAUSSIAN, sigma=(1.5, 1.0)), step(BOX, size=3), step(MEDIAN, size=3)

    def run(*steps: Step) -> Any:
        return image_filters.apply(counts, [Step(item.kind, order, item.sigma, item.size, item.alpha, item.text)
                                            for order, item in enumerate(steps)])[0]

    assert np.allclose(run(gauss, box), run(box, gauss))
    assert not np.allclose(run(median, gauss), run(gauss, median))
    assert image_filters.LINEAR == {GAUSSIAN, UNITS, BOX}


def test_the_chain_runs_in_its_order_then_the_default_one() -> None:
    steps = [step(BOX, 1), step(MEDIAN, 2), step(GAUSSIAN, 1)]
    assert [item.kind for item in image_filters.chain(steps)] == [GAUSSIAN, BOX, MEDIAN]
    texts = image_filters.apply(spot(), steps)[1]
    assert texts == (GAUSSIAN, BOX, MEDIAN)


def test_a_wide_sigma_is_capped_and_said() -> None:
    counts = spot((8, 12))
    image, _, notes = image_filters.apply(counts, [step(GAUSSIAN, sigma=(50.0, 50.0))])
    assert image.sum() == pytest.approx(counts.sum()) and len(notes) == 1 and "2 × 3 bins used" in notes[0]
    assert image_filters.limit(20) == 5.0 and image_filters.limit(2) == 1.0


def test_bins_are_capped() -> None:
    rng = np.random.default_rng(1)
    data = np.column_stack((rng.uniform(0, 1, 200_000), rng.uniform(0, 1, 200_000), rng.uniform(0, 1, 200_000)))
    item = histogram2d(data, "XY", 1.0)
    assert max(item.counts.shape) <= MAX_AUTO_BINS
    assert histogram2d(data, "XY", 1.0, bins=(10_000, 20_000)).counts.shape == (10_000, 10_000)


# The plot


def test_one_plot_in_the_package_with_every_plane_on() -> None:
    assert histograms_2d in standard_v2.MODULES
    metadata = PlaneHistograms().get_metadata()
    assert (metadata.name, metadata.analysis_id, metadata.version, metadata.group) == (
        "XY, XT, YT histograms", "helab.v2.plane_histograms", "1", "Basic plots v2")
    names = [spec.name for spec in PlaneHistograms().parameters("Plot")]
    assert names[names.index("include_outside"):names.index("blur_median")] == [
        "include_outside", "draw", "dot_colour", "max_dots", "dot_background", "bins_t", "bins_x", "bins_y", "quantity"]
    assert "range_mode" in names
    assert names[-3:] == ["colour_scale", "gamma", "log_decades"]
    assert [name for name in names if name.startswith("blur_") and name.count("_") == 1] == [
        f"blur_{kind}" for kind in FILTERS]
    assert {"show_xy", "show_xt", "show_yt"} <= set(names)
    result = result_of(PlaneHistograms(), view())
    assert [item.histogram.plane for item in result.data.items] == ["XY", "XT", "YT"]


def test_the_identity_hashes_the_file() -> None:
    """The plot's compute and drawing are histograms_2d.py's, so its identity names that file and carries its hash:
    an edit there is new code for result reuse and the presets' "script changed" note."""
    manager = ScriptsManager()
    for module in standard_v2.MODULES:
        manager.load_module(module)
    planes = [metadata for metadata in manager.get_scripts_in_group("Basic plots v2")
              if metadata.analysis_id == "helab.v2.plane_histograms"]
    assert [metadata.name for metadata in planes] == ["XY, XT, YT histograms"]
    assert planes[0].file_hash == file_hash(histograms_2d.__file__) and planes[0].file_hash
    assert planes[0].identity().file_name == "histograms_2d.py"


def test_planes_turn_on_and_off_and_bins_are_per_axis() -> None:
    script, data = PlaneHistograms(), view()
    result = result_of(script, data, {"show_xy": False, "bins_t": 50, "bins_x": 20})
    assert [item.histogram.plane for item in result.data.items] == ["XT", "YT"]
    xt, yt = result.data.items
    assert xt.histogram.axes[:2] == ("X", "T") and yt.histogram.axes[:2] == ("Y", "T")  # T up both.
    assert xt.histogram.counts.shape[1] == yt.histogram.counts.shape[1] == 50
    assert xt.histogram.counts.shape[0] == 20 and yt.histogram.automatic == (True, False)
    values = effective(script.parameters("Plot"), {"show_xy": False, "bins_t": 50, "bins_x": 20})
    assert script.describe_run("Plot", values, data)[1].startswith("XT, YT")
    assert "bins T 50, X 20, Y auto" in script.describe_run("Plot", values, data)[1]
    none = {f"show_{plane.lower()}": False for plane in PLANES}
    assert script.parameter_warnings("Plot", effective(script.parameters("Plot"), none))
    assert not script.parameter_warnings("Plot", effective(script.parameters("Plot"), {}))


def test_no_plane_on_says_so(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {f"show_{plane.lower()}": False for plane in PLANES})
    widget = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    assert isinstance(widget, QLabel) and "Planes" in widget.text()


@pytest.mark.parametrize("plane", list(PLANES))
def test_the_run_sums_the_chosen_shots(plane: str) -> None:
    script = PlaneHistograms()
    data = view()
    result = result_of(script, data, {**only(plane), "shots": "last N", "last_shots": 2})
    item = result.data.items[0].histogram
    assert result.data.shots == (3, 4) and item.total == len(data.shots[3]) + len(data.shots[4])
    used, settings = script.describe_run("Plot", effective(script.parameters("Plot"), {"colour_scale": "log"}), data)
    assert "bins auto" in settings and "colours log, 3 decades" in settings and "auto-crop 99 %" in settings
    title = histograms_2d.plane_title(result.data.items[0])
    assert f"{PLANES[plane][2]} summed" in title and "bins (automatic)" in title and "run_2d" not in title
    assert histograms_2d.planes_title(result.data) == "shots 3–4 (2 of 4)"


@pytest.mark.parametrize("scale", list(SCALES))
@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("shown", ["all", "XT"])
def test_every_library_draws_and_updates_in_place(shown: str, backend: str, scale: str, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    planes = {} if shown == "all" else only(shown)
    first = result_of(script, view(range(1, 3)), {**planes, "colour_scale": scale})
    widget = script.draw(first, backend)
    qtbot.addWidget(widget)
    assert isinstance(widget, {PLOTLY: PlotlyPane, MATPLOTLIB: MatplotlibPane}.get(backend, pg.GraphicsLayoutWidget))
    if isinstance(widget, MatplotlibPane):
        widget.canvas.draw()  # type: ignore[no-untyped-call]
    assert script.update(widget, result_of(script, view(range(1, 4)), {**planes, "colour_scale": scale}))
    if backend == PYQTGRAPH:
        other = LOG if scale == LINEAR else LINEAR
        assert not script.update(widget, result_of(script, view(range(1, 4)), {**planes, "colour_scale": other}))
        assert not script.update(widget, result_of(script, view(range(1, 4)), {"show_yt": False,
                                                                                 "colour_scale": scale}))


# Dots


DOT_COLOURS = [NO_COLOUR, SUMMED, DENSITY]


@pytest.mark.parametrize("plane", list(PLANES))
def test_dots_are_the_events_in_the_view_range_coloured_as_chosen(plane: str) -> None:
    data = view()
    item = plane_of(plane, data, {"draw": DOTS, "dot_colour": SUMMED})
    dots, histogram = item.dots, item.histogram
    assert dots is not None and dots.drawn == dots.inside == histogram.inside  # Under the cap: every event.
    across, up, summed = (("T", "X", "Y").index(name) for name in PLANES[plane])
    every = data.events(tuple(data.shots))
    inside = every[(every[:, across] >= histogram.h_edges[0]) & (every[:, across] <= histogram.h_edges[-1])
                   & (every[:, up] >= histogram.v_edges[0]) & (every[:, up] <= histogram.v_edges[-1])]
    assert np.array_equal(dots.h, inside[:, across]) and np.array_equal(dots.v, inside[:, up])
    assert np.array_equal(dots.values, inside[:, summed])
    assert dots.span == (inside[:, summed].min(), inside[:, summed].max())
    # Local density: each dot's bin's value in the image, the densest last.
    dense = plane_of(plane, data, {"draw": DOTS, "dot_colour": DENSITY, "bins_t": 20, "bins_x": 20, "bins_y": 20})
    assert dense.dots is not None and np.all(np.diff(dense.dots.values) >= 0)
    assert dense.dots.values.max() == dense.image.max() and dense.dots.values.min() >= 1
    plain = plane_of(plane, data, {"draw": DOTS, "dot_colour": NO_COLOUR})
    assert plain.dots is not None and not len(plain.dots.values) and plain.dots.drawn == histogram.inside
    assert plane_of(plane, data).dots is None  # The histogram by default.


def test_dots_beyond_the_cap_are_a_fixed_sample_and_said() -> None:
    data = view()
    first = plane_of("XY", data, {"draw": DOTS, "max_dots": 1_000})
    again = plane_of("XY", data, {"draw": DOTS, "max_dots": 1_000})
    assert first.dots is not None and again.dots is not None
    assert first.dots.drawn == 1_000 < first.dots.inside == first.histogram.inside
    assert np.array_equal(first.dots.h, again.dots.h)
    assert "1,000 dots (a sample of" in histograms_2d.plane_title(first)
    # The density and the bins still count every event.
    assert first.histogram.inside == plane_of("XY", data).histogram.inside


def test_dots_summed_axis_colour_bar_in_units_for_one_plane_else_low_to_high() -> None:
    one = result_of(PlaneHistograms(), view(), {**only("XY"), "draw": DOTS, "dot_colour": SUMMED}).data
    assert one.real_summed and one.bar_range == one.items[0].dots.span
    assert "T (s)" in histograms_2d.bar_label(one, histograms_2d.Colours())
    three = result_of(PlaneHistograms(), view(), {"draw": DOTS, "dot_colour": SUMMED}).data
    assert not three.real_summed and three.bar_range == (0.0, 1.0)
    for item in three.items:
        values = histograms_2d.dot_values(item, three)
        assert values.min() == pytest.approx(0.0) and values.max() == pytest.approx(1.0)
        assert "colour " in histograms_2d.plane_title(item)
    density = result_of(PlaneHistograms(), view(), {"draw": DOTS}).data
    assert density.bar_range == (0.0, density.top)
    script = PlaneHistograms()
    settings = effective(script.parameters("Plot"), {"draw": DOTS, "dot_colour": SUMMED})
    assert "dots, summed axis" in script.describe_run("Plot", settings, view())[1]


@pytest.mark.parametrize("colour", DOT_COLOURS)
@pytest.mark.parametrize("backend", BACKENDS)
def test_dots_draw_in_every_library_and_update_in_place(backend: str, colour: str, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    values = {"draw": DOTS, "dot_colour": colour, "colour_scale": SQRT}
    widget: Any = script.draw(result_of(script, view(range(1, 3)), values), backend)
    qtbot.addWidget(widget)
    if isinstance(widget, MatplotlibPane):
        widget.canvas.draw()  # type: ignore[no-untyped-call]
    later = result_of(script, view(range(1, 4)), values)
    assert script.update(widget, later)
    if backend == PYQTGRAPH:
        layout: Any = widget  # (The Matplotlib check above narrowed it.)
        for panel, item in zip(layout.plane_panels, later.data.items):
            assert panel.dots is not None and len(panel.dots.data) == item.dots.drawn
            assert not panel.image.isVisible()
        assert layout.plane_bar.isVisible() == (colour != NO_COLOUR)
        # Back to the histogram, or another colouring: drawn anew.
        assert not script.update(widget, result_of(script, view(range(1, 4)), {"colour_scale": SQRT}))
        other = SUMMED if colour != SUMMED else DENSITY
        assert not script.update(widget, result_of(script, view(range(1, 4)), {**values, "dot_colour": other}))
    if backend == PLOTLY:
        figure: Any = histograms_2d.planes_plotly(later)
        assert [trace.type for trace in figure.data] == ["scattergl"] * 3
        assert figure.layout.coloraxis.showscale == (colour != NO_COLOUR)


@pytest.mark.parametrize("colour", [NO_COLOUR, DENSITY])
def test_dots_on_a_black_or_white_plot_area(colour: str, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    black = {"draw": DOTS, "dot_colour": colour, "dot_background": "black"}
    result = result_of(script, view(), black)
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    for panel in widget.plane_panels:
        assert panel.plot.getViewBox().background.brush().color().name() == "#000000"
    if colour == NO_COLOUR:
        assert widget.plane_panels[0].dots.opts["brush"].color().name() == "#ffffff"
    assert script.update(widget, result_of(script, view(), {**black, "dot_background": "white"}))
    assert not widget.plane_panels[0].plot.getViewBox().background.isVisible()
    figure: Any = histograms_2d.planes_plotly(result)
    assert figure.layout.plot_bgcolor == "#000000" and figure.layout.xaxis.gridcolor == histograms_2d.DARK_GRID
    white: Any = histograms_2d.planes_plotly(result_of(script, view(), {"draw": DOTS}))
    assert white.layout.plot_bgcolor == "#ffffff"
    pane = histograms_2d.planes_matplotlib(result).axes[0]
    assert pane.get_facecolor()[:3] == (0.0, 0.0, 0.0)
    # The histogram keeps its white area whatever the setting.
    assert histograms_2d.background({"draw": "histogram", "dot_background": "black"}) == "white"
    values = effective(script.parameters("Plot"), black)
    assert "on black" in script.describe_run("Plot", values, view())[1]


def test_pyqtgraph_image_orientation_aspect_and_update(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view())
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    assert len(widget.plane_panels) == 3 and "run_2d" not in widget.title_label.text
    for panel, data in zip(widget.plane_panels, result.data.items):
        item = data.histogram
        image = panel.image
        assert image.image.shape == item.counts.shape  # [across, up] (col-major)
        rect = image.mapRectToParent(image.boundingRect())
        assert rect.left() == pytest.approx(item.h_edges[0]) and rect.right() == pytest.approx(item.h_edges[-1])
        assert rect.top() == pytest.approx(item.v_edges[0]) and rect.bottom() == pytest.approx(item.v_edges[-1])
        plane = item.plane
        assert panel.plot.getAxis("bottom").labelText == PLANES[plane][0]
        assert panel.plot.getAxis("left").labelText == PLANES[plane][1]
        assert bool(panel.plot.getViewBox().state["aspectLocked"]) == (plane == "XY")
        assert plane in panel.label.text
    images = [panel.image for panel in widget.plane_panels]
    assert script.update(widget, result_of(script, view(range(1, 6))))
    assert [panel.image for panel in widget.plane_panels] == images  # The same items, the new images.


def scales(widget: Any) -> list[float]:
    """Metres per pixel on each panel's space axes: across, and up for XY."""
    found = []
    for panel in widget.plane_panels:
        box = panel.plot.getViewBox()
        (x0, x1), (y0, y1) = box.viewRange()
        found.append((x1 - x0) / box.width())
        if panel.axes[1] != "T":
            found.append((y1 - y0) / box.height())
    return found


def test_every_space_axis_shares_one_scale_and_follows_a_zoom(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    widget: Any = script.draw(result_of(script, view()), PYQTGRAPH)
    qtbot.addWidget(widget)
    widget.resize(1200, 420)
    widget.show()
    xy, xt, yt = widget.plane_panels
    boxes = [panel.plot.getViewBox() for panel in widget.plane_panels]

    def fitted() -> bool:
        found = scales(widget)
        return max(found) == pytest.approx(min(found), rel=1e-3)

    def in_view() -> bool:
        return all(box.viewRange()[0][0] <= panel.extent[0][0] and box.viewRange()[0][1] >= panel.extent[0][1]
                   and box.viewRange()[1][0] <= panel.extent[1][0] and box.viewRange()[1][1] >= panel.extent[1][1]
                   and np.ptp(box.viewRange()[0]) < 1.0 for panel, box in zip(widget.plane_panels, boxes))

    qtbot.waitUntil(lambda: in_view() and fitted(), timeout=5_000)
    # Every image in view at one scale (waited for), and T the same in XT and YT.
    assert boxes[1].viewRange()[1] == pytest.approx(boxes[2].viewRange()[1])
    # A zoom on XT: XY's X and YT's Y follow its scale, XY's X its range; YT's T its T.
    before = float(np.ptp(boxes[1].viewRange()[0]))
    boxes[1].scaleBy((0.5, 0.5))
    boxes[1].sigRangeChangedManually.emit([True, True])

    def followed() -> bool:
        (x0, x1), time = boxes[1].viewRange()
        return (x1 - x0 < 0.7 * before and fitted()
                and middle(boxes[0].viewRange()[0]) == pytest.approx(middle((x0, x1)))
                and list(boxes[2].viewRange()[1]) == pytest.approx(list(time)))

    qtbot.waitUntil(followed, timeout=5_000)
    assert widget.plane_scale.last is xt
    zoomed = [float(value) for span in boxes[1].viewRange() for value in span]
    # Live's next shots keep the zoom: the zoomed view's range stays, the others follow it at one scale (their
    # widths may change a little: the colour bar's labels follow the new peak).
    assert script.update(widget, result_of(script, view(range(1, 6))))
    qtbot.waitUntil(lambda: fitted() and not widget.plane_scale.timer.isActive(), timeout=5_000)
    assert [float(value) for span in boxes[1].viewRange() for value in span] == pytest.approx(zoomed)
    assert (xy.axes, xt.axes, yt.axes) == (("X", "Y"), ("X", "T"), ("Y", "T"))


def middle(span: Any) -> float:
    return (float(span[0]) + float(span[1])) / 2


def test_compressed_colours_with_real_values_on_the_bar(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {**only("XY"), "colour_scale": SQRT})
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    panel, data = widget.plane_panels[0], result.data.items[0]
    shown = panel.image.image
    peak = float(data.image.max())
    assert shown.max() == pytest.approx(1.0) and shown.min() >= 0.0  # Colour positions over plain viridis.
    assert np.allclose(shown, np.sqrt(data.image / peak))
    assert widget.plane_bar.levels() == pytest.approx((0.0, peak))  # The bar reads real values.
    assert "colours sqrt, values linear" in widget.legend_label.text


@pytest.mark.parametrize("scale,gamma,decades", [(LINEAR, 0.5, 3), (SQRT, 0.5, 3), (LOG, 0.5, 8), (POWER, 0.05, 3)])
def test_every_planes_colours_match_the_shared_legend(scale: str, gamma: float, decades: int, qtbot: QtBot) -> None:
    from plotly.colors import sample_colorscale, unlabel_rgb

    script = PlaneHistograms()
    settings = {"quantity": "rate per shot", "colour_scale": scale, "gamma": gamma, "log_decades": decades}
    result = result_of(script, view(), settings)
    data = result.data
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    colours = histograms_2d.Colours.of(result.parameters)
    fractions = np.concatenate(([0.0], np.geomspace(1e-10, 1.0, 100)))
    transformed = compress(fractions, scale, gamma, decades)
    expected = histograms_2d.viridis().map(transformed, mode="byte")
    groups = histograms_2d.colour_groups(data)
    assert [[item.histogram.plane for item in group.items] for group in groups] == [["XY"], ["XT", "YT"]]
    assert len(widget.plane_bars) == 2
    assert groups[0].top != pytest.approx(groups[1].top)
    for bar, label, group in zip(widget.plane_bars, widget.bar_labels, groups):
        found = bar.colorMap().map(fractions, mode="byte")
        assert np.max(np.abs(found.astype(float) - expected.astype(float))) <= 2
        assert bar.axis.style["showValues"]
        assert bar.axis.range == pytest.approx(group.bar_range)
        assert all(item.histogram.plane in label.text for item in group.items)
    assert "mm²" in widget.bar_labels[0].text and "mm·ms" in widget.bar_labels[1].text
    for panel, item in zip(widget.plane_panels, data.items):
        group = histograms_2d.colour_group(data, item)
        assert np.allclose(panel.image.image, compress(item.image / group.peak, scale, gamma, decades))
    # Plotly interpolates RGB between its stops: faint values must agree even across eight decades.
    figure: Any = histograms_2d.planes_plotly(result)
    for name, group in zip(("coloraxis", "coloraxis2"), groups):
        axis = figure.layout[name]
        stops = axis.colorscale
        positions = np.array([entry[0] for entry in stops])
        rgb = np.array([unlabel_rgb(entry[1]) for entry in stops])
        interpolated = np.column_stack([np.interp(fractions, positions, rgb[:, channel]) for channel in range(3)])
        target = np.array([unlabel_rgb(value) for value in sample_colorscale("Viridis", transformed.tolist())])
        assert np.max(np.abs(interpolated - target)) <= 2
        assert axis.cmax == pytest.approx(group.top)
        assert axis.colorbar.title.text == histograms_2d.group_label(group, colours).replace(" · ", "<br>").replace(": ", "<br>")
    for trace, item, name in zip(figure.data, data.items, ("coloraxis", "coloraxis2", "coloraxis2")):
        assert trace.coloraxis == name and np.array_equal(trace.z, item.image.T)
    drawn = histograms_2d.planes_matplotlib(result)
    assert len(drawn.axes) == 5
    for axes, item in zip(drawn.axes[:3], data.items):
        mesh = axes.collections[0]
        group = histograms_2d.colour_group(data, item)
        assert np.allclose(mesh.norm(fractions * group.top), transformed)
    for legend, group in zip(drawn.axes[3:], groups):
        assert legend.get_ylabel() == histograms_2d.group_label(group, colours).replace(" · ", "\n").replace(": ", "\n")


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("draw", ["histogram", DOTS])
def test_rate_colour_groups_update_with_their_own_ticks(backend: str, draw: str, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    values = {"quantity": "rate per shot", "draw": draw, "colour_scale": SQRT}
    first = result_of(script, view(range(1, 3)), values)
    widget: Any = script.draw(first, backend)
    qtbot.addWidget(widget)
    later = result_of(script, view(range(1, 5)), values)
    bars: list[Any] = []
    if backend == PYQTGRAPH:
        bars = list(widget.plane_bars)
    assert script.update(widget, later)
    if backend == PYQTGRAPH:
        assert widget.plane_bars == bars
        for bar, group in zip(bars, histograms_2d.colour_groups(later.data)):
            assert bar.levels() == pytest.approx(group.bar_range)
        for panel, item in zip(widget.plane_panels, later.data.items):
            group = histograms_2d.colour_group(later.data, item)
            if draw == DOTS:
                assert item.dots is not None
                expected = histograms_2d.dot_brushes(item, later.data, histograms_2d.Colours(SQRT))
                assert [brush.color().getRgb() for brush in panel.dots.data["brush"]] == [
                    brush.color().getRgb() for brush in expected]
            else:
                assert np.allclose(panel.image.image, np.sqrt(item.image / group.peak))
        # Counts use one shared numerical range, so this needs a new layout.
        assert not script.update(widget, result_of(script, view(), {"draw": draw, "colour_scale": SQRT}))


@pytest.mark.parametrize("shown", [("XY",), ("XT",), ("YT",), ("XY", "XT"), ("XY", "YT"), ("XT", "YT")])
def test_rate_legends_follow_the_planes_shown(shown: tuple[str, ...], qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {"quantity": "rate per shot",
        **{f"show_{plane.lower()}": plane in shown for plane in PLANES}})
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    expected: list[tuple[str, ...]] = [("XY",)] if "XY" in shown else []
    timed = tuple(plane for plane in shown if plane != "XY")
    if timed:
        expected.append(timed)
    groups = histograms_2d.colour_groups(result.data)
    assert [tuple(item.histogram.plane for item in group.items) for group in groups] == expected
    assert len(widget.plane_bars) == len(expected)
    widget.resize(1000, 500)
    widget.show()
    qtbot.waitUntil(lambda: all(panel.plot.getViewBox().height() > 50 for panel in widget.plane_panels))
    for bar, group in zip(widget.plane_bars, groups):
        if group.items[0].histogram.plane == "XY":
            assert bar.sceneBoundingRect().right() <= widget.plane_panels[0].plot.sceneBoundingRect().left()
        else:
            assert bar.sceneBoundingRect().left() >= widget.plane_panels[-1].plot.sceneBoundingRect().right()
    figure: Any = histograms_2d.planes_plotly(result)
    for trace, item in zip(figure.data, result.data.items):
        axis = figure.layout[trace.coloraxis]
        group = histograms_2d.colour_group(result.data, item)
        assert axis.cmax == pytest.approx(group.top)
        assert (axis.colorbar.x < 0) == (item.histogram.plane == "XY")
    drawn = histograms_2d.planes_matplotlib(result)
    assert len(drawn.axes) == len(shown) + len(expected)
    drawn.set_size_inches(10, 5)
    drawn.canvas.draw()
    for bar_axes, group in zip(drawn.axes[len(shown):], groups):
        if group.items[0].histogram.plane == "XY":
            assert bar_axes.get_position().x1 < drawn.axes[0].get_position().x0
        else:
            assert bar_axes.get_position().x0 > drawn.axes[len(shown) - 1].get_position().x1


@pytest.mark.parametrize("draw", ["histogram", DOTS])
def test_xy_alone_redraws_its_bar_on_its_side_when_show_changes(draw: str, qtbot: QtBot) -> None:
    """XY alone: its counts bar on the right, its rate bar on the left. A change of Show between them is the
    same planes and groups, but another side, so PyQtGraph draws it anew rather than filling the old bar."""
    script = PlaneHistograms()
    values = {**only("XY"), "draw": draw}
    counts = result_of(script, view(), values)
    rate = result_of(script, view(), {**values, "quantity": "rate per shot"})
    for first, second in ((counts, rate), (rate, counts)):
        widget: Any = script.draw(first, PYQTGRAPH)
        qtbot.addWidget(widget)
        fresh: Any = script.draw(second, PYQTGRAPH)
        qtbot.addWidget(fresh)
        assert fresh.plane_bar.inset_column != widget.plane_bar.inset_column
        assert not script.update(widget, second)  # (Drawn anew, its bar where a fresh drawing puts it.)


@pytest.mark.parametrize("backend", BACKENDS)
def test_toggling_planes_removes_and_restores_their_rate_bars(backend: str, qtbot: QtBot,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    updated_figures: list[Any] = []
    original_update = PlotlyPane.update_figure

    def capture_update(pane: PlotlyPane, figure: Any) -> None:
        updated_figures.append(figure)
        original_update(pane, figure)

    monkeypatch.setattr(PlotlyPane, "update_figure", capture_update)
    script = PlaneHistograms()
    widget: Any = None
    for shown in [("XY", "XT", "YT"), ("XY",), ("XT",), ("YT",), ("XY", "YT"), ("XT", "YT"), (),
                  ("XY", "XT", "YT")]:
        result = result_of(script, view(), {"quantity": "rate per shot",
            **{f"show_{plane.lower()}": plane in shown for plane in PLANES}})
        updated = widget is not None and script.update(widget, result)
        if not updated:
            if widget is not None:
                widget.close()
                widget.deleteLater()
            widget = script.draw(result, backend)
            qtbot.addWidget(widget)
        if not shown:
            assert isinstance(widget, QLabel)  # No plane: no colour bar remains.
            continue
        current: Any = widget
        count = int("XY" in shown) + int(any(plane != "XY" for plane in shown))
        if backend == PYQTGRAPH:
            assert len(current.plane_bars) == count
            assert all(bar.isVisible() for bar in current.plane_bars)
            assert [panel.axes for panel in current.plane_panels] == [PLANES[plane][:2] for plane in shown]
        elif backend == MATPLOTLIB:
            assert len(current.figure.axes) == len(shown) + count
        elif updated:
            figure = updated_figures[-1]
            assert [trace.name for trace in figure.data] == list(shown)
            axes = [key for key in figure.layout if key.startswith("coloraxis")]
            assert len(axes) == count
            assert all(figure.layout[key].showscale for key in axes)


@pytest.mark.parametrize("width,height", [(640, 360), (1200, 600)])
def test_colour_tick_numbers_stay_inside_and_keep_physical_values_after_resize(
        width: int, height: int, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {"quantity": "rate per shot", "colour_scale": LOG})
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    widget.resize(width, height)
    widget.show()
    qtbot.waitUntil(lambda: all(panel.plot.getViewBox().height() > 50 for panel in widget.plane_panels))
    widget.grab()  # Exercise the actual axis painter, including text generation and clipping.
    groups = histograms_2d.colour_groups(result.data)
    for bar, group in zip(widget.plane_bars, groups):
        axis = bar.axis
        assert axis.range == pytest.approx(group.bar_range)
        assert axis.linkedView() is None
        assert axis.width() == 0  # Tick text reserves no space outside the gradient.
        assert axis.label_rects
        for rect in axis.label_rects:
            mapped = axis.mapRectToItem(bar.vb, rect)
            assert bar.vb.boundingRect().adjusted(-1, -1, 1, 1).contains(mapped)
    widget.resize(width + 80, height + 40)
    qtbot.wait(20)
    widget.grab()
    for bar, group in zip(widget.plane_bars, groups):
        assert bar.axis.range == pytest.approx(group.bar_range)
    figure: Any = histograms_2d.planes_plotly(result)
    assert figure.layout.coloraxis.colorbar.ticklabelposition == "inside"
    assert figure.layout.coloraxis2.colorbar.ticklabelposition == "inside"


@pytest.mark.parametrize("size", [(6.4, 3.6), (12.0, 6.0)])
@pytest.mark.parametrize("decades", [1, 3])
def test_matplotlib_major_and_minor_numbers_fit_inside_the_gradient(size: tuple[float, float], decades: int) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    result = result_of(PlaneHistograms(), view(), {"quantity": "rate per shot", "colour_scale": LOG,
                                                 "log_decades": decades})
    figure = histograms_2d.planes_matplotlib(result)
    figure.set_size_inches(*size)
    canvas: Any = FigureCanvasAgg(figure)
    canvas.draw()
    renderer = canvas.get_renderer()
    for axes in figure.axes[3:]:
        bounds = axes.get_window_extent(renderer)
        labels = [text for text in axes.get_yticklabels(which="both") if text.get_visible() and text.get_text()]
        assert labels
        for text in labels:
            label = text.get_window_extent(renderer)
            assert label.x0 >= bounds.x0 and label.x1 <= bounds.x1


def test_inside_tick_labels_keep_precision_for_a_narrow_summed_time_range(qtbot: QtBot) -> None:
    t = np.linspace(2.12345678, 2.12345679, 100)
    events = np.column_stack((t, np.linspace(-0.01, 0.01, 100), np.linspace(-0.01, 0.01, 100)))
    data = build_view(Dataset("/data/root/narrow", "sig", {1: events}, {}, 0))
    script = PlaneHistograms()
    result = result_of(script, data, {**only("XY"), "draw": DOTS, "dot_colour": SUMMED})
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    widget.resize(640, 360)
    widget.show()
    qtbot.wait(20)
    widget.grab()
    bar = widget.plane_bar
    assert bar.axis.gradient_width > histograms_2d.BAR_WIDTH
    assert len(bar.axis.label_rects) >= 2
    assert bar.axis.range == pytest.approx(result.data.bar_range)
    for rect in bar.axis.label_rects:
        assert bar.vb.boundingRect().adjusted(-1, -1, 1, 1).contains(bar.axis.mapRectToItem(bar.vb, rect))


@pytest.mark.parametrize("width,height", [(640, 360), (1200, 600)])
def test_the_full_colour_legend_fits_the_plot(width: int, height: int, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {"quantity": "rate per shot", "colour_scale": LOG})
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    widget.resize(width, height)
    widget.show()
    label = widget.legend_label
    qtbot.waitUntil(lambda: widget.sceneRect().contains(label.sceneBoundingRect()))
    assert "log, 3 decades" in label.text
    assert "mm²" in widget.bar_labels[0].text and "mm·ms" in widget.bar_labels[1].text
    for item in [*widget.bar_labels, *widget.plane_bars]:
        assert widget.sceneRect().contains(item.sceneBoundingRect())
    qtbot.waitUntil(lambda: all(panel.plot.getViewBox().height() > 50 for panel in widget.plane_panels))


def test_one_colour_bar_over_every_plane(qtbot: QtBot) -> None:
    """The planes share one colour bar: every image over 0 … the highest bin of the planes shown."""
    script = PlaneHistograms()
    result = result_of(script, view())
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    bars = [item for item in widget.ci.items if isinstance(item, pg.ColorBarItem)]
    assert bars == [widget.plane_bar]
    peak = max(float(item.image.max()) for item in result.data.items)
    assert result.data.peak == peak and widget.plane_bar.levels() == pytest.approx((0.0, peak))
    for panel, item in zip(widget.plane_panels, result.data.items):
        assert np.allclose(panel.image.image, item.image / peak)
    assert max(float(panel.image.image.max()) for panel in widget.plane_panels) == pytest.approx(1.0)
    assert histograms_2d.planes_quantity(result.data) == "Events per bin"
    rate = result_of(script, view(), {"quantity": "rate per shot"}).data
    assert "XY per mm², XT and YT per mm·ms" in histograms_2d.planes_quantity(rate)
    xt_yt = result_of(script, view(), {"quantity": "rate per shot", "show_xy": False}).data
    assert histograms_2d.planes_quantity(xt_yt) == "Events / (mm·ms) / shot"
    figure: Any = histograms_2d.planes_plotly(result)
    assert all(trace.coloraxis == "coloraxis" for trace in figure.data)
    assert figure.layout.coloraxis.cmax == pytest.approx(peak)
    assert len(histograms_2d.planes_matplotlib(result).axes) == 4  # Three images, one bar.


@pytest.mark.parametrize("plane", list(PLANES))
def test_rate_integrates_to_events_per_shot_in_millimetres_and_milliseconds(plane: str) -> None:
    data = view()
    item = plane_of(plane, data, {"quantity": "rate per shot"})
    histogram = item.histogram
    # Every shown axis converts by 1,000: metres to mm, seconds to ms.
    widths_h = np.diff(histogram.h_edges) * 1_000
    widths_v = np.diff(histogram.v_edges) * 1_000
    assert float((item.image * widths_h[:, None] * widths_v[None, :]).sum()) == pytest.approx(
        histogram.inside / len(data.shots))


def test_blur_rate_per_shot_and_the_whole_summed_axis() -> None:
    script = PlaneHistograms()
    data = view()
    plain = plane_of("XY", data, {"bins_x": 30, "bins_y": 30})
    smooth = plane_of("XY", data, {"bins_x": 30, "bins_y": 30, "blur_gaussian": True, "blur_gaussian_sigma": 2.0})
    assert smooth.filters == ("Gaussian σ 2 bins",)
    assert smooth.image.sum() == pytest.approx(float(plain.histogram.counts.sum()))
    assert smooth.image.max() < plain.image.max() and "blur Gaussian σ 2 bins" in histograms_2d.plane_title(smooth)
    assert "(filtered)" in histograms_2d.quantity_text(smooth)
    capped = plane_of("XY", data, {"bins_x": 8, "bins_y": 8, "blur_gaussian": True, "blur_gaussian_sigma": 50.0})
    assert any("over a quarter" in note and note.startswith("XY: ") for note in capped.notes)
    rate = plane_of("XY", data, {"bins_x": 30, "bins_y": 30, "quantity": "rate per shot"})
    assert rate.per_shot and np.allclose(rate.image, plain.image / len(data.shots) / (bin_area(rate.histogram) * 1e6))
    assert histograms_2d.quantity_text(rate) == "Events / mm² / shot"
    xt = plane_of("XT", data, {"quantity": "rate per shot"})
    assert histograms_2d.quantity_text(xt) == "Events / (mm·ms) / shot"
    # Manual bounds on T limit the XY sum, unless the whole summed axis is asked for.
    window = {"range_mode": "manual", "t_min": 2.09, "t_max": 2.11, "x_min": -0.01, "x_max": 0.01,
              "y_min": -0.01, "y_max": 0.01}
    cut = plane_of("XY", data, window).histogram
    whole = plane_of("XY", data, {**window, "include_outside": True}).histogram
    assert cut.flattened == (2.09, 2.11) and whole.flattened is None
    assert whole.summed == whole.total > cut.summed
    assert (whole.h_edges[0], whole.h_edges[-1]) == (-0.01, 0.01)  # The shown axes are still cut.
    settings = script.describe_run("Plot", effective(script.parameters("Plot"),
                                                     {**window, **only("XY"), "include_outside": True}), data)[1]
    assert "whole T" in settings


def test_blur_filters_chain_in_the_order_set() -> None:
    script, data = PlaneHistograms(), view()
    values = {"blur_median": True, "blur_gaussian": True, "blur_gaussian_sigma": 1.5, "blur_box": True,
              "blur_box_size": 5}
    item = plane_of("XY", data, values)
    assert item.filters == ("median 3 × 3 bins", "Gaussian σ 1.5 bins", "box 5 × 5 bins")  # The default order.
    tied = plane_of("XY", data, {**values, "blur_median_order": 6})  # Box's order too: as listed.
    assert tied.filters == ("Gaussian σ 1.5 bins", "median 3 × 3 bins", "box 5 × 5 bins")
    moved = plane_of("XY", data, {**values, "blur_median_order": 6, "blur_box_order": 5})
    assert moved.filters == ("Gaussian σ 1.5 bins", "box 5 × 5 bins", "median 3 × 3 bins")
    assert not np.allclose(item.image, moved.image)  # The median doesn't commute.
    settings = script.describe_run("Plot", effective(script.parameters("Plot"), {**values, "blur_median_order": 6,
                                                                                "blur_box_order": 5}),
                                   data)[1]
    assert "blur Gaussian → box → median" in settings
    # Off, a filter's settings don't apply (hidden, and left out of the result's key).
    specs = {spec.name: spec for spec in script.parameters("Plot")}
    assert not specs["blur_box_size"].applies({"blur_box": False}) and specs["blur_box_size"].applies(values)


def test_a_gaussian_in_units_is_the_same_size_in_every_plane() -> None:
    data = view()
    values = {"bins_t": 30, "bins_x": 60, "bins_y": 40, "blur_units": True, "blur_units_space": 5e-4,
              "blur_units_time": 2e-3}
    result = result_of(PlaneHistograms(), data, values).data
    for item in result.items:
        histogram = item.histogram
        widths = (np.diff(histogram.h_edges)[0], np.diff(histogram.v_edges)[0])
        sizes = [2e-3 if axis == "T" else 5e-4 for axis in histogram.axes[:2]]
        steps = histograms_2d.blur_steps(effective(PlaneHistograms().parameters("Plot"), values), histogram)
        assert steps[0].sigma == pytest.approx((sizes[0] / widths[0], sizes[1] / widths[1]))
        assert item.image.sum() == pytest.approx(float(histogram.counts.sum()))
    assert "500 µm" in result.items[0].filters[0] and "2 ms" in result.items[1].filters[0]


def test_plotly_and_matplotlib_keep_the_input_in_their_titles() -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {**only("XT"), "colour_scale": "log"})
    figure: Any = histograms_2d.planes_plotly(result)
    assert "run_2d" in figure.layout.title.text and figure.data[0].type == "heatmap"
    assert figure.layout.xaxis.title.text == "X (m)" and figure.layout.yaxis.title.text == "T (s)"
    drawn = histograms_2d.planes_matplotlib(result)
    assert "run_2d" in drawn.texts[0].get_text() and drawn.axes[0].get_ylabel() == "T (s)"
    every: Any = histograms_2d.planes_plotly(result_of(script, view()))
    assert [trace.name for trace in every.data] == ["XY", "XT", "YT"]
    # One scale on every space axis (XY's Y, XT's X, YT's Y at XY's X), T matched between XT and YT.
    layout = every.layout
    assert layout.yaxis.scaleanchor == layout.xaxis2.scaleanchor == layout.xaxis3.scaleanchor == "x"
    assert layout.yaxis2.scaleanchor is None and layout.yaxis3.matches == "y2"
    assert layout.xaxis2.title.text == "X (m)" and layout.xaxis3.title.text == "Y (m)"
    assert layout.yaxis3.title.text == "T (s)"
    drawn_all = histograms_2d.planes_matplotlib(result_of(script, view()))
    assert len(drawn_all.axes) == 4  # Three images, one bar.
    spans = [np.ptp(drawn_all.axes[index].get_xlim()) for index in (1, 2)]  # XT, YT (XY's may widen to fit).
    assert spans[0] == pytest.approx(spans[1])


def test_nothing_to_sum_says_why(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {**only("XY"), "range_mode": "manual", "t_min": 5.0, "t_max": 6.0})
    widget = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    assert isinstance(widget, QLabel) and "summed axis" in widget.text()
    # With other planes to show, the empty one says so in its own title.
    both = result_of(script, view(), {"show_yt": False, "range_mode": "manual", "t_min": 5.0, "t_max": 6.0,
                                      "include_outside": False, "x_min": -1.0, "x_max": 1.0})
    drawn: Any = script.draw(both, PYQTGRAPH)
    qtbot.addWidget(drawn)
    assert "no events inside the summed axis's bounds" in drawn.plane_panels[0].label.text
    none = result_of(script, view(), {"shots": "range", "first_shot": 50, "last_shot": 60})
    label = script.draw(none, PYQTGRAPH)
    qtbot.addWidget(label)
    assert isinstance(label, QLabel) and "chosen" in label.text()


def test_the_input_is_left_unchanged() -> None:
    data = view()
    before = {shot: np.array(values) for shot, values in data.shots.items()}
    result_of(PlaneHistograms(), data, {"range_mode": "manual", "t_min": 2.0, "t_max": 2.2})
    assert all(np.array_equal(before[shot], data.shots[shot]) for shot in before)


@pytest.mark.parametrize("plane", list(PLANES))
def test_manual_axes_left_unset_or_reversed_use_their_full_extent(plane: str) -> None:
    """As v1 and the note say: in the manual View range, a shown axis whose min = max (unset) or min > max covers
    every event of the summed selection, whatever "Auto-crop: keep" was left at (hidden in manual mode)."""
    script, data = PlaneHistograms(), view()
    across, up, summed = (("T", "X", "Y").index(name) for name in PLANES[plane])
    name = PLANES[plane][2].lower()
    window = {**only(plane), "range_mode": "manual", "keep_percent": 50.0, f"{name}_min": -10.0,
              f"{name}_max": 10.0}
    every = np.concatenate([data.shots[shot] for shot in sorted(data.shots)])
    for values in (window, {**window, **{f"{axis}_min": 1.0 for axis in "txy" if axis != name},
                            **{f"{axis}_max": -1.0 for axis in "txy" if axis != name}}):
        result = result_of(script, data, values).data
        item = result.items[0].histogram
        assert (item.h_edges[0], item.h_edges[-1]) == (every[:, across].min(), every[:, across].max())
        assert (item.v_edges[0], item.v_edges[-1]) == (every[:, up].min(), every[:, up].max())
        assert item.outside == 0 and item.inside == item.summed == len(every)
    assert len(result.notes) == 2 and all("using full extent" in note for note in result.notes)
    del summed
