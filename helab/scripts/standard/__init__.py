"""HeLab's bundled analyses, imported normally (not scanned from a folder) so that
packaged builds include them; the Scripts panel registers ``MODULES``. They share the
group ``group.NAME`` ("Basic plots v1"), whose version marks this first set of plots.

The Scripts panel shows this group with the second set ("Basic plots v2",
``helab.scripts.standard_v2``) as one entry, ``FAMILY`` ("Basic Plots"): each set is a
version node in its tree, newest first (``FAMILY_GROUPS``: group name and node label)."""
from helab.scripts.standard import basic_plots, scatter_3d, transfer_fractions
from helab.scripts.standard import group
from helab.scripts.standard_v2 import group as group_v2

MODULES = (scatter_3d, basic_plots, transfer_fractions)

FAMILY = "Basic Plots"
FAMILY_GROUPS = ((group_v2.NAME, f"v{group_v2.VERSION}"), (group.NAME, f"v{group.VERSION}"))
