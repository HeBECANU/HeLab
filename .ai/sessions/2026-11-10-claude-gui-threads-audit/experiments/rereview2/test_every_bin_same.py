"""Re-review 2: Q~1's "every bin" draws exactly as before (684b027). The same results, drawn by each library, are
written to ``$GT_OUT`` (an ``.npz``) by the code before Q~1 (a checkout of ``9a7d16c``, no ``draw_at``) and after it
(``GT_EVERY=1``: ``draw_at`` = every bin); ``compare_every_bin.py`` then compares the two files array by array.

Run from a checkout's root: ``PYTHONPATH=tests python -m pytest -p conftest <this file> -q`` with ``GT_OUT`` set.
"""
from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
from pytestqt.qtbot import QtBot

from helab.analysis.backends import PYQTGRAPH
from helab.scripts.standard_v2 import histograms_2d
from helab.scripts.standard_v2.histograms_2d import PlaneHistograms
from test_basic_plots_v2_hist2d import only, result_of, view

CASES: dict[str, dict[str, Any]] = {
    "wide": {**only("XY"), "bins_x": 5_000, "bins_y": 10},
    "auto_all": {},
    "big_xt": {**only("XT"), "bins_x": 3_000, "bins_t": 2_500},
    "log": {**only("YT"), "bins_y": 2_600, "bins_t": 40, "colour_scale": "log"},
    "dots": {**only("XY"), "draw": "dots"},
    "dots_plain": {**only("XY"), "draw": "dots", "dot_colour": "none"},
}


def test_draw_every_case(qtbot: QtBot) -> None:
    out: dict[str, Any] = {}
    script = PlaneHistograms()
    for name, values in CASES.items():
        values = {**values, **({"draw_at": "every bin"} if os.environ.get("GT_EVERY") else {})}
        result = result_of(script, view(), values)
        widget: Any = script.draw(result, PYQTGRAPH)
        qtbot.addWidget(widget)
        for index, panel in enumerate(widget.plane_panels):
            out[f"{name}.pg{index}.image"] = np.asarray(panel.image.image)
            out[f"{name}.pg{index}.auto"] = np.asarray(bool(panel.image.autoDownsample))
            out[f"{name}.pg{index}.label"] = np.asarray(panel.label.text)
            if panel.dots is not None and panel.dots.data is not None and len(panel.dots.data):
                points = panel.dots.data
                out[f"{name}.pg{index}.dots"] = np.column_stack((points["x"], points["y"]))
                out[f"{name}.pg{index}.brushes"] = np.asarray(
                    [brush.color().rgba() if brush is not None else -1 for brush in points["brush"]], dtype=np.int64)
        out[f"{name}.plotly"] = np.asarray(json.dumps(histograms_2d.planes_plotly(result).to_plotly_json(),
                                                      default=lambda value: np.asarray(value).tolist(), sort_keys=True))
        figure = histograms_2d.planes_matplotlib(result)
        for index, axes in enumerate(figure.axes):
            out[f"{name}.mpl{index}.title"] = np.asarray(axes.get_title())
            out[f"{name}.mpl{index}.kinds"] = np.asarray([type(c).__name__ for c in axes.collections]
                                                         + [type(i).__name__ for i in axes.images])
            for number, collection in enumerate(axes.collections):
                array = collection.get_array()
                if array is not None:
                    out[f"{name}.mpl{index}.c{number}.array"] = np.ma.filled(np.ma.asarray(array, dtype=float), -1.0)
                out[f"{name}.mpl{index}.c{number}.offsets"] = np.asarray(collection.get_offsets())
                if hasattr(collection, "get_coordinates"):
                    out[f"{name}.mpl{index}.c{number}.coords"] = np.asarray(collection.get_coordinates())
    np.savez_compressed(os.environ["GT_OUT"], **out)
