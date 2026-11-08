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
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.stats import shortest_range
from helab.scripts import standard_v2
from helab.scripts.standard_v2 import histograms_2d
from helab.scripts.scripts_manager import ScriptsManager
from helab.scripts.standard_v2.histograms_2d import PlaneCounts, PlaneHistograms
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


# The plot


def test_one_plot_in_the_package_with_every_plane_on() -> None:
    assert histograms_2d in standard_v2.MODULES
    metadata = PlaneHistograms().get_metadata()
    assert (metadata.name, metadata.analysis_id, metadata.version, metadata.group) == (
        "XY, XT, YT histograms", "helab.v2.plane_histograms", "1", "Basic plots v2")
    names = [spec.name for spec in PlaneHistograms().parameters("Plot")]
    assert names[names.index("include_outside"):names.index("blur_median")] == [
        "include_outside", "bins_t", "bins_x", "bins_y", "quantity"] and "range_mode" in names
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
    assert "colours sqrt, values linear" in widget.plane_bar.getAxis("left").labelText


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
    assert "XY per m², XT and YT per m·s" in histograms_2d.planes_quantity(rate)
    xt_yt = result_of(script, view(), {"quantity": "rate per shot", "show_xy": False}).data
    assert histograms_2d.planes_quantity(xt_yt) == "Events / (m·s) / shot"
    figure: Any = histograms_2d.planes_plotly(result)
    assert all(trace.coloraxis == "coloraxis" for trace in figure.data)
    assert figure.layout.coloraxis.cmax == pytest.approx(peak)
    assert len(histograms_2d.planes_matplotlib(result).axes) == 4  # Three images, one bar.


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
    assert rate.per_shot and np.allclose(rate.image, plain.image / len(data.shots) / bin_area(rate.histogram))
    assert histograms_2d.quantity_text(rate) == "Events / m² / shot"
    xt = plane_of("XT", data, {"quantity": "rate per shot"})
    assert histograms_2d.quantity_text(xt) == "Events / (m·s) / shot"
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
