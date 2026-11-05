"""The XT histogram (Basic plots v2): the chosen shots' events binned in XT, the third axis summed
(``helab.scripts.standard_v2.histograms_2d``)."""
from __future__ import annotations

from helab.scripts.standard_v2.histograms_2d import Histogram2DPlot


class XTHistogram(Histogram2DPlot):
    @property
    def plane(self) -> str:
        return "XT"
