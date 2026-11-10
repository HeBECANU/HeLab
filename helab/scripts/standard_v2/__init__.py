"""HeLab's second set of bundled plots ("Basic plots v2"), imported normally (not scanned from a
folder) so that packaged builds include them; the Scripts panel registers ``MODULES`` before the
first set's (``helab.scripts.standard``), which stays exactly as it was. Their analysis ids are
``helab.v2.*``, so no result or preset of the first set is taken for theirs."""
from helab.scripts.standard_v2 import (counts_per_shot, histograms_2d, plane_projections, scatter_3d,
                                       transfer_fractions, txy_histograms)

MODULES = (scatter_3d, counts_per_shot, txy_histograms, histograms_2d, plane_projections, transfer_fractions)
