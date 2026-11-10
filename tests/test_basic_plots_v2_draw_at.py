"""Q~1 (Tony, 2026-11-10; GT-4 of the GUI-thread audit): XY, XT, YT histograms draw at screen resolution by default
(Image › Draw at), beside every bin. An image of more than ``DISPLAY_SIDE`` bins a side is drawn from the mean of
blocks of bins made on the worker, at most that a side (Plotly ``PLOTLY_SIDE``); PyQtGraph also averages what the
screen can't show (``autoDownsample``) and Matplotlib draws one raster (``imshow``); PyQtGraph and Matplotlib draw at
most ``DRAWN_DOTS`` dots. The bins, the counts and the image stay as set; the plane's title says how it is drawn; the
memory estimate follows the setting. Every bin draws as before."""
from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from helab.analysis import histogram2d as histogram2d_module
from helab.analysis.backends import MATPLOTLIB, PLOTLY, PYQTGRAPH
from helab.analysis.histogram2d import DISPLAY_SIDE, PLOTLY_SIDE, block_edges, block_mean, display_factors, display_shape
from helab.analysis.parameters import effective
from helab.scripts.standard_v2 import histograms_2d
from helab.scripts.standard_v2.histograms_2d import DOTS, EVERY_BIN, SCREEN, PlaneHistograms
from test_basic_plots_v2_hist2d import only, result_of, view

# XY alone at 5,000 × 10 bins: drawn 1,667 × 10 (means of 3 × 1 bins), and by Plotly 834 × 10 (6 × 1).
WIDE = {**only("XY"), "bins_x": 5_000, "bins_y": 10}


def test_blocks_are_whole_bins_their_means_and_edges() -> None:
    assert (DISPLAY_SIDE, PLOTLY_SIDE) == (2048, 1000)
    assert display_factors((5_000, 10)) == (3, 1) and display_shape((5_000, 10)) == (1_667, 10)
    assert display_factors((2_048, 2_048)) == (1, 1) and display_factors((20_000, 20_000)) == (10, 10)
    image = np.arange(35, dtype=np.float64).reshape(5, 7)
    means = block_mean(image, (2, 3))
    assert means.dtype == np.float32 and means.shape == (3, 3)
    assert means[0, 0] == pytest.approx(image[:2, :3].mean()) and means[2, 2] == pytest.approx(image[4:, 6:].mean())
    edges = np.linspace(0.0, 1.0, 8)
    assert np.array_equal(block_edges(edges, 3), [edges[0], edges[3], edges[6], edges[7]])
    assert np.array_equal(block_edges(edges, 7), [edges[0], edges[7]])


def test_the_worker_makes_the_drawn_image_and_keeps_every_bin() -> None:
    script = PlaneHistograms()
    screen, every = (result_of(script, view(), {**WIDE, "draw_at": at}).data.items[0] for at in (SCREEN, EVERY_BIN))
    assert screen.histogram.counts.shape == every.histogram.counts.shape == (5_000, 10)
    assert np.array_equal(screen.image, every.image) and every.display is None
    display = screen.display
    assert display is not None and display.image.shape == (1_667, 10) and display.factors == (3, 1)
    assert display.h_edges[0] == screen.histogram.h_edges[0] and display.h_edges[-1] == screen.histogram.h_edges[-1]
    sizes = np.diff(np.append(np.arange(0, 5_000, 3), 5_000))
    assert float((display.image.astype(np.float64) * sizes[:, None]).sum()) == pytest.approx(float(screen.image.sum()))
    assert screen.peak == pytest.approx(float(display.image.max()))  # (The colour bar reads what is drawn.)
    assert "drawn at 1,667 × 10, each the mean of 3 × 1 bins" in histograms_2d.plane_title(screen)
    assert "drawn at" not in histograms_2d.plane_title(every)
    small = result_of(script, view(), only("XY")).data.items[0]  # (Automatic bins: no smaller drawing.)
    assert small.display is None
    assert script.describe_run("Plot", effective(script.parameters("Plot"), {"draw_at": EVERY_BIN}),
                               view())[1].count("every bin drawn") == 1
    assert "every bin" not in script.describe_run("Plot", effective(script.parameters("Plot"), {}), view())[1]


@pytest.mark.parametrize("at", [SCREEN, EVERY_BIN])
def test_each_library_draws_the_drawn_image(at: str, qtbot: QtBot) -> None:
    script = PlaneHistograms()
    result = result_of(script, view(), {**WIDE, "draw_at": at})
    item = result.data.items[0]
    screen = at == SCREEN
    widget: Any = script.draw(result, PYQTGRAPH)
    qtbot.addWidget(widget)
    image = widget.plane_panels[0].image
    assert image.image.shape == ((1_667, 10) if screen else (5_000, 10)) and image.autoDownsample is screen
    assert ("drawn at" in widget.plane_panels[0].label.text) is screen
    figure: Any = histograms_2d.planes_plotly(result)
    trace = figure.data[0]
    assert np.asarray(trace.z).shape == ((10, 834) if screen else (10, 5_000))
    assert (trace.customdata is None) is screen  # (A block's mean has no one bin's events.)
    assert ("each the mean of 6 × 1 bins" in figure.layout.annotations[0].text) is screen
    drawn = histograms_2d.planes_matplotlib(result)
    axes = drawn.axes[0]
    if screen:
        assert len(axes.images) == 1 and not axes.collections
        assert axes.images[0].get_array().shape == (10, 1_667)
        assert "drawn at 1,667 × 10" in axes.get_title()
    else:
        assert not axes.images and len(axes.collections) == 1  # (pcolormesh, a quad a bin, as before.)
    assert item.histogram.counts.shape == (5_000, 10)


def test_switching_draw_at_draws_anew_in_pyqtgraph(qtbot: QtBot) -> None:
    script = PlaneHistograms()
    widget: Any = script.draw(result_of(script, view(), WIDE), PYQTGRAPH)
    qtbot.addWidget(widget)
    assert script.update(widget, result_of(script, view(range(1, 4)), WIDE))
    assert not script.update(widget, result_of(script, view(range(1, 4)), {**WIDE, "draw_at": EVERY_BIN}))


@pytest.mark.parametrize("backend", [PYQTGRAPH, MATPLOTLIB, PLOTLY])
@pytest.mark.parametrize("at", [SCREEN, EVERY_BIN])
def test_pyqtgraph_and_matplotlib_draw_at_most_their_dots(backend: str, at: str, qtbot: QtBot,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(histograms_2d, "DRAWN_DOTS", 100)
    script = PlaneHistograms()
    result = result_of(script, view(), {**only("XY"), "draw": DOTS, "draw_at": at})
    item = result.data.items[0]
    assert item.dots is not None and item.dots.drawn > 100 and item.display is None
    capped = at == SCREEN and backend != PLOTLY
    expected = 100 if capped else item.dots.drawn
    if backend == PYQTGRAPH:
        widget: Any = script.draw(result, backend)
        qtbot.addWidget(widget)
        assert len(widget.plane_panels[0].dots.data) == expected
        assert ("100 of them drawn" in widget.plane_panels[0].label.text) is capped
    elif backend == MATPLOTLIB:
        axes = histograms_2d.planes_matplotlib(result).axes[0]
        assert len(axes.collections[0].get_offsets()) == expected
        assert ("100 of them drawn" in axes.get_title()) is capped
    else:
        figure: Any = histograms_2d.planes_plotly(result)
        assert len(figure.data[0].x) == expected  # (WebGL: every dot.)


def test_the_estimate_follows_draw_at() -> None:
    script = PlaneHistograms()

    def estimate(values: dict[str, Any]) -> int:
        return script.estimated_bytes("Plot", effective(script.parameters("Plot"), values))
    big = {"bins_x": 20_000, "bins_y": 20_000, "bins_t": 20_000}
    bins, drawn = 400_000_000, 2_000 * 2_000
    # Held: counts and image (16 B a bin) and the drawn image (4 B a cell); colouring at the drawn size.
    assert estimate(big) == 16 * 3 * bins + 4 * 3 * drawn + 32 * drawn
    assert estimate({**big, "draw_at": EVERY_BIN}) == 16 * 3 * bins + 32 * bins
    # A filter still runs on every bin.
    assert estimate({**big, "blur_gaussian": True}) == 16 * 3 * bins + 4 * 3 * drawn + 32 * bins
    assert estimate({}) == estimate({"draw_at": EVERY_BIN}) == 16 * 3 * 1_000_000 + 32 * 1_000_000
    assert estimate({**big, "draw": DOTS}) == 16 * 3 * bins + 32 * bins  # (Dots: as before.)
    assert histogram2d_module.estimated_bytes([10, 10], drawn=[10, 4]) == 16 * 20 + 4 * 4 + 32 * 10


def test_draw_at_sits_beside_the_bins() -> None:
    names = [spec.name for spec in PlaneHistograms().parameters("Plot")]
    assert names.index("draw_at") == names.index("bins_y") + 1
    spec = histograms_2d.DRAW_AT
    assert spec.default == SCREEN and spec.choices == (SCREEN, EVERY_BIN) and spec.group == "Image"
