"""3D scatter (Basic plots v2): v1's 3D scatter (``helab.scripts.standard.scatter_3d``, which stays as it
is) under v2's analysis id, so that v2's results and presets are its own and later changes go to v2 only."""
from __future__ import annotations

from helab.scripts.base import ScriptMetadata
from helab.scripts.standard import scatter_3d as v1
from helab.scripts.standard_v2 import group


class Scatter3D(v1.Scatter3D):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata(
            name="3D scatter",
            description="T/X/Y events of the loaded folder, cropped to the region holding most events",
            group=group.NAME,
            file_path=__file__,
            analysis_id="helab.v2.scatter_3d",
            version="1",
        )
