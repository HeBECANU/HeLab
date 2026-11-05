"""T, X, Y histograms (Basic plots v2): v1's (``helab.scripts.standard.basic_plots``, which stays as it is)
under v2's analysis id, so that v2's results and presets are its own and later changes go to v2 only. Its
PyQtGraph title leaves out the folder and revision, which the dock's line above it shows."""
from __future__ import annotations

from typing import Optional

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget

from helab.analysis.results import AnalysisResult
from helab.scripts.base import ScriptMetadata
from helab.scripts.standard import basic_plots as v1
from helab.scripts.standard_v2 import group


def drawing_title(widget: QWidget, result: AnalysisResult) -> None:
    """The title of a PyQtGraph drawing without its input (shown on the dock's line and in Plot info)."""
    label = getattr(widget, "title_label", None)
    if isinstance(widget, pg.GraphicsLayoutWidget) and label is not None:
        label.setText(v1.histograms_title(result).removeprefix(f"{result.input.short()} · "))


class TxyHistograms(v1.TxyHistograms):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata(
            name="T, X, Y histograms",
            description="Distributions of the loaded events' T, X and Y",
            group=group.NAME,
            file_path=__file__,
            analysis_id="helab.v2.txy_histograms",
            version="1",
        )

    def draw(self, result: AnalysisResult, backend: str, parent: Optional[QWidget] = None) -> QWidget:
        widget = super().draw(result, backend, parent)
        drawing_title(widget, result)
        return widget

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        done = super().update(widget, result)
        if done:
            drawing_title(widget, result)
        return done


