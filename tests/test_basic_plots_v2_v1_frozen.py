"""Basic plots v1 stays as it is (LR-10): its plot files byte for byte, since each file's SHA-256 is in its
results' reuse keys and its presets' checks (an edit would make every saved v1 result outdated), its
analysis ids, versions, names and parameters, and the helpers Basic plots v2 imports from it.

A deliberate change to v1 updates this test in the same commit, saying why."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from helab.scripts import standard
from helab.scripts.base import DatasetAnalysis
from helab.scripts.standard import basic_plots, group, scatter_3d, transfer_fractions

# SHA-256 of each file with its line endings as committed (LF; Windows checks them out with CRLF).
HASHES = {
    "scatter_3d.py": "18ec008133ed2d87120d189b0b4abd37541a8f333f0831c511d3192a507365f1",
    "basic_plots.py": "51d485b0cbb5c5da3ab4ad6e25356e158d362d1a58c4349aa7150df49ea4db6d",
    "transfer_fractions.py": "9d5bef287d5357951a292863b98377bdfb47dcc824933ac141ef715a3bded157",
}
SHOTS = (("shots", "choice", "all"), ("first_shot", "int", 0), ("last_shots", "int", 50), ("last_shot", "int", 0))
RANGE = (("range_mode", "choice", "auto-crop"), ("keep_percent", "float", 99.0), ("t_min", "float", 0.0),
         ("t_max", "float", 0.0), ("x_min", "float", 0.0), ("x_max", "float", 0.0), ("y_min", "float", 0.0),
         ("y_max", "float", 0.0))
NEWEST = (("highlight_newest", "bool", False), ("newest_colour", "choice", "red"))
SCRIPTS = {
    ("helab.scatter_3d", "3", "3D scatter"): (*SHOTS, *RANGE, ("point_size", "float", 1.5), ("opacity", "float", 0.5),
                                              ("display_cap", "int", 100000), *NEWEST),
    ("helab.counts_per_shot", "2", "Counts per shot"): SHOTS,
    ("helab.txy_histograms", "3", "T, X, Y histograms"): (*SHOTS, *RANGE, ("bins", "int", 0), ("log_y", "bool", False),
                                                          *NEWEST),
    ("helab.transfer_fractions", "8", "Transfer fractions"): (
        *SHOTS, ("orders_mode", "choice", "auto"), ("orders_each_side", "int", 2), ("centre", "float", 2.1375),
        ("spacing", "float", 0.015), ("reference_spacing", "float", 0.015), ("half_width", "float", 0.0),
        ("search_min", "float", 0.0), ("search_max", "float", 0.0), ("xy_half", "float", 0.03),
        ("min_counts", "int", 50), *NEWEST),
}
# What Basic plots v2 imports from v1 (helab/scripts/standard_v2/): their names stay.
IMPORTED = {
    basic_plots: ("TxyHistograms", "histograms_title", "matplotlib_update", "plotly_update"),
    scatter_3d: ("Scatter3D",),
    transfer_fractions: ("TransferFractions", "empty_reason", "fractions_title", "matplotlib_figure", "newest_scale",
                         "order_colours", "plotly_figure", "pyqtgraph_layout", "times_title"),
}


def test_v1_files_are_unchanged() -> None:
    for module in standard.MODULES:
        path = Path(module.__file__ or "")
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert digest == HASHES[path.name], f"{path.name} changed: v1 stays as it is (update this test if meant)"
    assert sorted(HASHES) == sorted(Path(module.__file__ or "").name for module in standard.MODULES)


def test_v1_ids_versions_and_parameters_are_unchanged() -> None:
    assert group.NAME == "Basic plots v1" and group.VERSION == 1
    found = {}
    for module in standard.MODULES:
        for _, member in inspect.getmembers(module, inspect.isclass):
            if issubclass(member, DatasetAnalysis) and member.__module__ == module.__name__:
                script = member()
                metadata = script.get_metadata()
                assert metadata.group == group.NAME and script.get_actions() == ["Plot"]
                found[(metadata.analysis_id, metadata.version, metadata.name)] = tuple(
                    (spec.name, spec.kind, spec.default) for spec in script.parameters("Plot"))
    assert found == SCRIPTS


def test_the_helpers_v2_imports_are_there() -> None:
    for module, names in IMPORTED.items():
        for name in names:
            assert callable(getattr(module, name, None)), f"{module.__name__}.{name}"
