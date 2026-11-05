"""Basic plots v2's per-shot X axis (LR-10): Shot ID or Shot time (the raw file's time), the shots whose time is
their TXY file's marked and counted, shots without a time left out and counted, long gaps breaking the line;
Counts per shot and Transfer fractions in every library and both modes, updated in place as Live adds shots.
Also v2's T, X, Y histograms and 3D scatter: v1's plots under v2's ids."""
from __future__ import annotations

from typing import Any, Callable, cast

import numpy as np
import plotly.graph_objs as go
import pyqtgraph as pg
import pytest
from PyQt6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

from helab.analysis import shot_axis
from helab.analysis.backends import BACKENDS, MATPLOTLIB, PLOTLY, PYQTGRAPH, MatplotlibPane
from helab.analysis.dataset_view import DatasetView, build_view
from helab.analysis.panes import PlotlyPane
from helab.analysis.parameters import effective
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.shot_axis import GAP_FACTOR, SHOT_ID, SHOT_TIME, broken
from helab.scripts.base import DatasetAnalysis
from helab.scripts import standard_v2
from helab.scripts.standard import transfer_fractions as v1_fractions
from helab.scripts.standard_v2 import common, counts_per_shot, scatter_3d, transfer_fractions, txy_histograms
from helab.utils.folder_cache import Dataset

NS = 1_000_000_000
START = 1_762_300_000.0  # 2025-11-05, s since the epoch
CENTRE, SPACING = 2.1375, 0.0125
FALLBACK, UNTIMED, AFTER_GAP = 3, 7, 5  # shot 3: a TXY time only; 7: no time at all; 5: after a long gap


def shot_events(rng: np.random.Generator, shot: int) -> Any:
    """Orders −2…+2 in T around ``CENTRE``, a small cloud in X and Y."""
    parts = []
    for order, count in {-2: 20, -1: 100, 0: 600, 1: 250 + 10 * shot, 2: 30}.items():
        times = rng.normal(CENTRE + order * SPACING, 0.001, count)
        parts.append(np.column_stack((times, rng.normal(0, 0.005, (count, 2)))))
    events = np.concatenate(parts)
    events.setflags(write=False)
    return events


def raw_time(shot: int) -> float:
    """Shots every 10 s, with a stall of an hour before ``AFTER_GAP``."""
    return START + 10.0 * shot + (3600.0 if shot >= AFTER_GAP else 0.0)


def view(shots: range = range(1, 10)) -> DatasetView:
    rng = np.random.default_rng(7)
    data = {shot: shot_events(rng, shot) for shot in shots}
    fingerprint = [[shot, 100 + shot, int((raw_time(shot) + 600) * NS)] for shot in shots if shot != UNTIMED]
    raw = [[shot, int(raw_time(shot) * NS)] for shot in shots if shot not in (FALLBACK, UNTIMED)]
    return build_view(Dataset("/data/root/run_long_named_folder", "sig-1", data,
                              {"fingerprint": fingerprint, "raw_times": raw, "source": "files",
                               "loaded_at": 1_700_000_000.0}, 0))


def result_of(script: DatasetAnalysis, data: DatasetView, values: dict[str, Any] | None = None) -> AnalysisResult:
    context = AnalysisContext("a1", "Plot", data, effective(script.parameters("Plot"), values),
                              script.get_metadata().identity())
    return AnalysisResult.of(context, "completed", script.compute("Plot", context))


BY_TIME = {"x_axis": SHOT_TIME}


# helab.analysis.shot_axis


def test_by_shot_id_every_chosen_shot_in_order() -> None:
    axis = shot_axis.shot_axis(view(), [4, 2, 9, 7], SHOT_ID)
    assert axis.shots.tolist() == [2, 4, 7, 9] and axis.x.tolist() == [2.0, 4.0, 7.0, 9.0]
    assert not axis.fallback.any() and axis.untimed == () and not axis.breaks().any() and axis.notes() == []
    assert axis.label == "Shot ID" and not axis.by_time and axis.point_text(0) == "shot 2"


def test_by_shot_time_raw_times_fallbacks_and_untimed() -> None:
    data = view()
    axis = shot_axis.shot_axis(data, list(data.shots), SHOT_TIME)
    assert UNTIMED not in axis.shots and axis.untimed == (UNTIMED,)
    assert axis.x.tolist() == sorted(axis.x.tolist())  # By time.
    times = dict(zip(axis.shots.tolist(), axis.x.tolist()))
    assert times[1] == pytest.approx(raw_time(1)) and times[FALLBACK] == pytest.approx(raw_time(FALLBACK) + 600)
    assert axis.shots[axis.fallback].tolist() == [FALLBACK] and axis.fallbacks == 1
    assert axis.notes() == ["⚠ 1 TXY time (no raw file)", "1 without a time left out"]
    assert axis.label == "Shot time" and "(TXY time)" in axis.point_text(int(np.flatnonzero(axis.fallback)[0]))


def test_a_long_gap_breaks_the_line_and_only_there() -> None:
    data = view()
    axis = shot_axis.shot_axis(data, [shot for shot in data.shots if shot not in (FALLBACK, UNTIMED)], SHOT_TIME)
    breaks = axis.breaks()
    assert axis.shots[breaks].tolist() == [AFTER_GAP] and breaks.sum() == 1
    x, y = broken(axis.x, np.arange(len(axis.x), dtype=np.float64), breaks)
    assert len(x) == len(axis.x) + 1 and np.isnan(x[list(axis.shots).index(AFTER_GAP)])
    assert np.isnan(y).sum() == 1
    # The rule: a gap over GAP_FACTOR times the median interval.
    assert (3600 + 10) > GAP_FACTOR * 10 > 10
    few = shot_axis.shot_axis(data, [1, AFTER_GAP], SHOT_TIME)
    assert not few.breaks().any()  # (Fewer than three shots: no median to compare with.)


def test_the_setting_and_its_wording() -> None:
    spec = shot_axis.x_axis_spec("Plot")
    assert (spec.name, spec.title, spec.kind, spec.default, spec.choices) == (
        "x_axis", "X axis", "choice", "Shot ID", ("Shot ID", "Shot time"))
    assert shot_axis.axis_mode({}) == SHOT_ID and shot_axis.axis_mode(BY_TIME) == SHOT_TIME
    assert shot_axis.axis_brief({}) == "" and shot_axis.axis_brief(BY_TIME) == "against shot time"
    assert shot_axis.fallback_text(2) == "2 TXY times (no raw file)"


# Counts per shot v2


def test_counts_per_shot_in_both_modes() -> None:
    script = counts_per_shot.CountsPerShot()
    data = view()
    by_id = result_of(script, data).data
    assert by_id.axis.shots.tolist() == list(data.shots) and by_id.counts.tolist() == [len(data.shots[s]) for s in data.shots]
    by_time = result_of(script, data, BY_TIME).data
    assert by_time.chosen == len(data.shots) and len(by_time.counts) == len(data.shots) - 1
    assert by_time.counts.tolist() == [len(data.shots[int(s)]) for s in by_time.axis.shots]
    used, settings = script.describe_run("Plot", effective(script.parameters("Plot"), BY_TIME), data)
    assert "⚠ 1 TXY time (no raw file)" in used and settings.endswith("against shot time")
    assert "TXY time" not in script.describe_run("Plot", effective(script.parameters("Plot"), {}), data)[0]


def points(item: Any) -> tuple[Any, Any]:
    """A PyQtGraph data item's x and y (empty when it has none)."""
    x, y = item.getData()
    return (np.asarray([] if x is None else x, dtype=np.float64), np.asarray([] if y is None else y, dtype=np.float64))


def drawn_series(widget: Any) -> common.ShotSeries:
    return cast(common.ShotSeries, widget.counts_series)


def test_counts_per_shot_pyqtgraph_axis_marks_and_title(qtbot: QtBot) -> None:
    script = counts_per_shot.CountsPerShot()
    by_time = script.draw(result_of(script, view(), BY_TIME), PYQTGRAPH)
    qtbot.addWidget(by_time)
    plot = cast(Any, by_time).getPlotItem()
    assert isinstance(plot.getAxis("bottom"), pg.DateAxisItem)
    series = drawn_series(by_time)
    x, y = points(series.line)
    # Broken at the stall, and before shot 3's TXY time (converted 10 minutes later: a gap of its own).
    assert np.isnan(x).sum() == 2
    assert len(points(series.fallback)[0]) == 1
    title = plot.titleLabel.text
    assert "run_long_named_folder" not in title and "TXY time (no raw file)" in title and "without a time" in title
    assert "modification time" in by_time.toolTip()
    by_id = script.draw(result_of(script, view()), PYQTGRAPH)
    qtbot.addWidget(by_id)
    assert not isinstance(cast(Any, by_id).getPlotItem().getAxis("bottom"), pg.DateAxisItem)
    assert len(points(drawn_series(by_id).fallback)[0]) == 0


@pytest.mark.parametrize("values", [{}, BY_TIME])
@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("script_class", [counts_per_shot.CountsPerShot, transfer_fractions.TransferFractions])
def test_shot_axis_plots_draw_and_follow_live_in_every_library(
        script_class: Callable[[], DatasetAnalysis], backend: str, values: dict[str, Any], qtbot: QtBot) -> None:
    script = script_class()
    first = result_of(script, view(range(1, 9)), values)
    widget = script.draw(first, backend)
    qtbot.addWidget(widget)
    assert isinstance(widget, {PLOTLY: PlotlyPane, MATPLOTLIB: MatplotlibPane}.get(backend, QWidget))
    if isinstance(widget, MatplotlibPane):
        widget.canvas.draw()  # type: ignore[no-untyped-call]
    # Live's next shot shows in place, in either mode.
    later = result_of(script, view(range(1, 11)), dict(first.parameters))
    assert script.update(widget, later)
    # Another X axis is drawn anew.
    other = {"x_axis": SHOT_ID if values else SHOT_TIME}
    switched = result_of(script, view(range(1, 11)), {**dict(first.parameters), **other})
    if backend == PYQTGRAPH:
        assert not script.update(widget, switched)


def test_counts_per_shot_pyqtgraph_update_keeps_the_items(qtbot: QtBot) -> None:
    script = counts_per_shot.CountsPerShot()
    widget = script.draw(result_of(script, view(range(1, 9)), BY_TIME), PYQTGRAPH)
    qtbot.addWidget(widget)
    series = drawn_series(widget)
    assert script.update(widget, result_of(script, view(range(1, 11)), BY_TIME))
    assert drawn_series(widget) is series
    x, _ = points(series.line)
    assert np.isfinite(x).sum() == 9  # 1–10 less the untimed shot 7 (shot 3's TXY time is drawn).


def test_counts_per_shot_plotly_and_matplotlib_by_time() -> None:
    script = counts_per_shot.CountsPerShot()
    result = result_of(script, view(), BY_TIME)
    figure: Any = counts_per_shot.counts_plotly(result)
    assert figure.layout.xaxis.type == "date" and figure.layout.xaxis.title.text == "Shot time"
    assert "run_long_named_folder" in figure.layout.title.text  # It leaves HeLab: the input stays.
    line, triangles = figure.data
    assert None in line.x and str(line.x[0]).startswith("20")  # Local times, broken at the stall.
    assert len(triangles.x) == 1 and triangles.marker.symbol == "triangle-down"
    drawn = counts_per_shot.counts_matplotlib(result)
    axes = drawn.axes[0]
    assert axes.get_xlabel() == "Shot time" and len(axes.lines) == 2
    assert "run_long_named_folder" in drawn.texts[0].get_text()


def test_nothing_to_draw_says_why(qtbot: QtBot) -> None:
    script = counts_per_shot.CountsPerShot()
    only_untimed = result_of(script, view(), {**BY_TIME, "shots": "range", "first_shot": UNTIMED,
                                              "last_shot": UNTIMED})
    widget = script.draw(only_untimed, PYQTGRAPH)
    qtbot.addWidget(widget)
    assert isinstance(widget, QLabel) and widget.text() == "None of the chosen shots has a time"


# Transfer fractions v2


def test_transfer_fractions_counts_as_v1_and_draws_on_the_chosen_axis() -> None:
    data = view()
    v1 = result_of(v1_fractions.TransferFractions(), data).data
    v2 = result_of(transfer_fractions.TransferFractions(), data, BY_TIME).data
    assert isinstance(v2, transfer_fractions.TimedFractions)
    assert v2.shots.tolist() == v1.shots.tolist() and np.array_equal(v2.counts, v1.counts)
    assert v2.orders == v1.orders and v2.notes == v1.notes
    assert UNTIMED not in v2.axis.shots and v2.axis.untimed == (UNTIMED,)
    rows = {int(shot): row for row, shot in enumerate(v1.shots)}
    expected = np.array([v1.fractions[rows[int(shot)]] for shot in v2.axis.shots])
    assert np.array_equal(v2.drawn, expected, equal_nan=True)
    assert v2.notes_all[-2:] == ("⚠ 1 TXY time (no raw file)", "1 without a time left out")
    detected = transfer_fractions.TransferFractions().detected_parameters("Plot", result_of(
        transfer_fractions.TransferFractions(), data, BY_TIME))
    assert set(detected) <= {"centre", "spacing"}


def test_transfer_fractions_titles(qtbot: QtBot) -> None:
    script = transfer_fractions.TransferFractions()
    result = result_of(script, view(), BY_TIME)
    widget = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    text = cast(Any, widget).title_label.text
    assert "run_long_named_folder" not in text and "order 0 at" in text and "TXY time" in text
    assert isinstance(cast(Any, widget).getItem(1, 0).getAxis("bottom"), pg.DateAxisItem)
    figure: Any = transfer_fractions.plotly_figure(result)
    assert "run_long_named_folder" in figure.layout.title.text and figure.layout.xaxis.type == "date"
    assert isinstance(figure, go.Figure)


# v2's T, X, Y histograms and 3D scatter: v1's plots, v2's ids


def test_v2_ids_and_the_package() -> None:
    ids = []
    for module in standard_v2.MODULES:
        for script_class in (counts_per_shot.CountsPerShot, txy_histograms.TxyHistograms, scatter_3d.Scatter3D,
                             transfer_fractions.TransferFractions):
            if script_class.__module__ == module.__name__:
                metadata = script_class().get_metadata()
                ids.append(metadata.analysis_id)
                assert metadata.group == "Basic plots v2" and metadata.version == "1"
    assert sorted(ids) == ["helab.v2.counts_per_shot", "helab.v2.scatter_3d", "helab.v2.transfer_fractions",
                           "helab.v2.txy_histograms"]


def test_v2_histograms_title_leaves_out_the_input(qtbot: QtBot) -> None:
    script = txy_histograms.TxyHistograms()
    result = result_of(script, view())
    widget = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    title = cast(Any, widget).title_label.text
    assert "run_long_named_folder" not in title and "events" in title
    assert script.update(widget, result_of(script, view(range(1, 11))))
    assert "run_long_named_folder" not in cast(Any, widget).title_label.text


def test_v2_plots_leave_their_input_unchanged() -> None:
    data = view()
    before = {shot: np.array(events) for shot, events in data.shots.items()}
    for script in (counts_per_shot.CountsPerShot(), transfer_fractions.TransferFractions(),
                   txy_histograms.TxyHistograms(), scatter_3d.Scatter3D()):
        for values in ({}, BY_TIME):
            known = {key: value for key, value in values.items()
                     if key in {spec.name for spec in script.parameters("Plot")}}
            result_of(script, data, known)
    assert all(np.array_equal(before[shot], data.shots[shot]) for shot in before)
    assert all(not events.flags.writeable for events in data.shots.values())
