"""Focused tests for the automated analogue RGA heat-map visualiser."""

from datetime import datetime
from pathlib import Path

import pytest

from side_projects.rga_visualiser.analog_heatmap_visualiser import (
    HeatmapData,
    build_figure,
    delta_values,
    discover_analog_files,
    high_end_log_colorscale,
    load_heatmap_data,
    parse_analog_timestamp,
    scan_time_edges,
    transformed_values,
)
from side_projects.rga_visualiser.rga_visualiser import RGAData, Scan


def sample_heatmap_data() -> HeatmapData:
    return HeatmapData(
        masses=(1.0, 2.0, 3.0),
        times=(datetime(2026, 8, 20, 12, 0), datetime(2026, 8, 20, 12, 1)),
        values=((1e-10, 0.0, 1e-8), (1e-9, -1e-12, 1e-5)),
        source_files=2,
    )


def test_parse_analog_timestamp_includes_milliseconds() -> None:
    timestamp = parse_analog_timestamp(Path("Analog-20260820-122531-053.rgadata"))
    assert timestamp == datetime(2026, 8, 20, 12, 25, 31, 53000)


def test_parse_analog_timestamp_rejects_other_names() -> None:
    with pytest.raises(ValueError, match="does not contain"):
        parse_analog_timestamp(Path("manual.rgadata"))


def test_discover_analog_files_filters_and_sorts(tmp_path: Path) -> None:
    later = tmp_path / "Analog-20260820-122531-053.rgadata"
    earlier = tmp_path / "Analog-20260819-122531-053.rgadata"
    later.write_bytes(b"")
    earlier.write_bytes(b"")
    (tmp_path / "manual.rgadata").write_bytes(b"")
    (tmp_path / "Analog-20260821-122531-053.rgaview").write_bytes(b"")
    assert discover_analog_files(tmp_path) == [earlier, later]


def test_load_limit_returns_exact_newest_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [
        Path("Analog-20260819-120000-000.rgadata"),
        Path("Analog-20260820-120000-000.rgadata"),
    ]
    parsed_paths: list[Path] = []

    def fake_parse(path: Path) -> RGAData:
        parsed_paths.append(path)
        return RGAData(
            metadata={},
            masses=(1.0, 2.0),
            scans=tuple(
                Scan(0, float(index), (float(index), float(index + 1)))
                for index in range(4)
            ),
        )

    monkeypatch.setattr(
        "side_projects.rga_visualiser.analog_heatmap_visualiser.parse_rgadata",
        fake_parse,
    )
    data = load_heatmap_data(paths, max_scans=3)

    assert parsed_paths == [paths[-1]]
    assert len(data.times) == 3
    assert data.times[0] == datetime(2026, 8, 20, 12, 0, 1)
    assert data.source_files == 1


def test_log_transform_omits_non_positive_values() -> None:
    transformed = transformed_values(sample_heatmap_data().values, True)
    assert transformed[0] == (-10.0, None, -8.0)
    assert transformed[1] == (-9.0, None, -5.0)


def test_log_colorscale_expands_the_top_four_decades() -> None:
    scale = high_end_log_colorscale(((-10.0, -9.0), (-8.0, -5.0)))
    assert not isinstance(scale, str)
    assert scale[0] == [0.0, "#440154"]
    assert scale[1][0] == pytest.approx(1.0 / 5.0)
    assert scale[1][1] == "#482878"
    assert scale[-1] == [1.0, "#fde725"]


def test_log_colorscale_keeps_normal_viridis_within_four_decades() -> None:
    assert high_end_log_colorscale(((-10.0, -9.0), (-7.0, -6.0))) == "Viridis"


def test_heatmap_uses_mass_horizontal_and_time_vertical() -> None:
    figure = build_figure(sample_heatmap_data(), surface=False, log_colour=True)
    trace = figure.data[0]
    assert trace.type == "heatmap"
    assert tuple(trace.x) == (1.0, 2.0, 3.0)
    assert tuple(trace.y) == (
        "2026-08-20 12:00:00.000",
        "2026-08-20 12:01:00.000",
    )
    assert figure.layout.xaxis.title.text == "Mass-to-charge ratio (amu/e)"
    assert figure.data[0].colorscale[1][0] == pytest.approx(1.0 / 5.0)
    assert [annotation.text for annotation in figure.layout.annotations] == [
        "H2 (2)",
        "He3 (3)",
    ]
    assert not figure.layout.shapes


def test_surface_and_top_down_camera() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=True, log_colour=False, top_down=True
    )
    assert figure.data[0].type == "surface"
    assert len(figure.data) == 1
    assert figure.layout.scene.camera.projection.type == "orthographic"
    assert figure.layout.scene.camera.eye.z == 2.5
    assert figure.layout.scene.xaxis.tickmode is None
    assert [annotation.text for annotation in figure.layout.scene.annotations] == [
        "H2",
        "He3",
    ]
    assert all(
        annotation.y == "2026-08-20 12:01:00.000"
        for annotation in figure.layout.scene.annotations
    )
    assert all(
        annotation.textangle == -45
        for annotation in figure.layout.scene.annotations
    )


def test_common_gas_labels_can_be_hidden() -> None:
    figure = build_figure(
        sample_heatmap_data(),
        surface=False,
        log_colour=True,
        gas_labels=False,
    )
    assert not figure.layout.shapes
    assert not figure.layout.annotations

    surface = build_figure(
        sample_heatmap_data(),
        surface=True,
        log_colour=True,
        gas_labels=False,
    )
    assert surface.layout.scene.xaxis.tickmode is None
    assert not surface.layout.scene.annotations


def test_scan_time_edges_hold_until_next_scan() -> None:
    times = (
        datetime(2026, 8, 20, 12, 0),
        datetime(2026, 8, 20, 12, 1),
        datetime(2026, 8, 20, 12, 3),
        datetime(2026, 8, 20, 18, 0),
    )
    edges = scan_time_edges(times)
    assert edges[:-1] == times
    # The newest scan gets the median interval (2 minutes here).
    assert edges[-1] == datetime(2026, 8, 20, 18, 2)
    assert scan_time_edges(times[:1])[-1] == datetime(2026, 8, 20, 12, 1)
    assert scan_time_edges(()) == ()


def test_time_scaled_heatmap_uses_date_axis_and_edges() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=False, log_colour=True, time_scaled=True
    )
    trace = figure.data[0]
    assert figure.layout.yaxis.type == "date"
    assert tuple(trace.y) == (
        "2026-08-20 12:00:00.000",
        "2026-08-20 12:01:00.000",
        "2026-08-20 12:02:00.000",
    )
    assert len(trace.z) == 2


def test_time_scaled_surface_draws_flat_steps() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=True, log_colour=False, time_scaled=True
    )
    trace = figure.data[0]
    assert figure.layout.scene.yaxis.type == "date"
    assert tuple(trace.y) == (
        "2026-08-20 12:00:00.000",
        "2026-08-20 12:00:59.999",
        "2026-08-20 12:01:00.000",
        "2026-08-20 12:01:59.999",
    )
    assert trace.z[0] == trace.z[1]
    assert trace.z[2] == trace.z[3]
    assert trace.z[1] != trace.z[2]


def test_delta_values_subtract_reference_and_keep_missing() -> None:
    values = ((1.0, None, 3.0), (2.0, 5.0, None))
    assert delta_values(values, 1) == ((-1.0, None, None), (0.0, 0.0, None))


def test_delta_heatmap_is_in_decades_and_centred_on_zero() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=False, log_colour=True, reference_index=1
    )
    trace = figure.data[0]
    assert trace.zmid == 0.0
    assert tuple(trace.z[1]) == (0.0, None, 0.0)
    assert trace.z[0][0] == pytest.approx(-1.0)
    assert trace.z[0][2] == pytest.approx(-3.0)
    assert trace.colorbar.title.text == "Δ log10 ion current (decades)"
    assert "2026-08-20 12:01:00.000" in figure.layout.title.text


def test_delta_surface_is_linear_without_log_colour() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=True, log_colour=False, reference_index=0
    )
    trace = figure.data[0]
    assert trace.cmid == 0.0
    assert tuple(trace.z[0]) == (0.0, 0.0, 0.0)
    assert trace.z[1][2] == pytest.approx(1e-5 - 1e-8)


def test_delta_opacity_heatmap_fades_to_transparent_at_zero() -> None:
    figure = build_figure(
        sample_heatmap_data(),
        surface=False,
        log_colour=True,
        reference_index=1,
        delta_opacity=True,
    )
    trace = figure.data[0]
    # Largest |Δ| is 3 decades, so the range is symmetric at ±3.
    assert (trace.zmin, trace.zmax) == (pytest.approx(-3.0), pytest.approx(3.0))
    stops = [tuple(stop) for stop in trace.colorscale]
    assert stops[0] == (0.0, "rgba(33,102,172,1)")
    assert stops[1] == (0.5, "rgba(33,102,172,0)")
    assert stops[-1] == (1.0, "rgba(178,24,43,1)")


def test_delta_opacity_surface_uses_opacityscale() -> None:
    figure = build_figure(
        sample_heatmap_data(),
        surface=True,
        log_colour=False,
        reference_index=0,
        delta_opacity=True,
    )
    trace = figure.data[0]
    assert [tuple(stop) for stop in trace.opacityscale] == [
        (0.0, 1.0),
        (0.5, 0.0),
        (1.0, 1.0),
    ]
    assert trace.cmax == pytest.approx(1e-5 - 1e-8)
    assert trace.cmin == pytest.approx(-(1e-5 - 1e-8))


def test_delta_opacity_needs_a_reference() -> None:
    figure = build_figure(
        sample_heatmap_data(), surface=True, log_colour=True, delta_opacity=True
    )
    assert figure.data[0].opacityscale is None


def _write_rgadata(path: Path, scans: list[list[float]], mtime: float) -> None:
    import json as json_module
    import os
    import struct

    from side_projects.rga_visualiser.rga_visualiser import BLOCK_MARKER, MAGIC

    config = json_module.dumps(
        {"cfgs": [{"startMass": 1, "stopMass": 2, "pointsPerAmu": 1}]}
    ).encode()
    body = bytearray(MAGIC + BLOCK_MARKER + struct.pack("<I", len(config)) + config)
    body += BLOCK_MARKER + struct.pack("<I", 0)
    for index, values in enumerate(scans):
        if index:
            body += struct.pack("<I", 1000 * index)
        body += struct.pack("<II", 0, len(values)) + struct.pack(
            f"<{len(values)}f", *values
        )
    path.write_bytes(bytes(body))
    os.utime(path, (mtime, mtime))


def test_scan_cache_serves_unchanged_files_and_rereads_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from side_projects.rga_visualiser import scan_cache
    from side_projects.rga_visualiser.rga_visualiser import parse_rgadata

    source = tmp_path / "Analog-20260820-120000-000.rgadata"
    old = time.time() - 3600
    _write_rgadata(source, [[1e-9, 2e-9], [3e-9, 4e-9]], old)
    expected = parse_rgadata(source)

    database = tmp_path / "cache" / "scans.sqlite"
    with scan_cache.ScanCache(database) as cache:
        assert cache.load(source) == expected
        assert cache.hits == 0

    decoded: list[Path] = []

    def counting_parse(path: Path) -> object:
        decoded.append(path)
        return parse_rgadata(path)

    monkeypatch.setattr(scan_cache, "parse_rgadata", counting_parse)
    with scan_cache.ScanCache(database) as cache:
        assert cache.load(source) == expected
        assert cache.hits == 1
    assert decoded == []

    _write_rgadata(source, [[5e-9, 6e-9]], old + 1)
    with scan_cache.ScanCache(database) as cache:
        changed = cache.load(source)
        assert cache.hits == 0
    assert len(changed.scans) == 1
    assert decoded == [source]


def test_scan_cache_never_caches_a_file_still_being_written(tmp_path: Path) -> None:
    import time

    from side_projects.rga_visualiser import scan_cache

    source = tmp_path / "Analog-20260820-120000-000.rgadata"
    _write_rgadata(source, [[1e-9, 2e-9]], time.time())
    database = tmp_path / "scans.sqlite"
    for _ in range(2):
        with scan_cache.ScanCache(database) as cache:
            cache.load(source)
            assert cache.hits == 0


def test_damaged_cache_falls_back_to_decoding(tmp_path: Path) -> None:
    import time

    from side_projects.rga_visualiser import scan_cache

    source = tmp_path / "Analog-20260820-120000-000.rgadata"
    database = tmp_path / "scans.sqlite"
    database.write_bytes(b"not a database" * 100)
    _write_rgadata(source, [[1e-9, 2e-9]], time.time() - 3600)
    with scan_cache.ScanCache(database) as cache:
        assert len(cache.load(source).scans) == 1
        assert cache.problem is not None


def test_scan_cache_remembers_rejected_files_until_they_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from side_projects.rga_visualiser import scan_cache
    from side_projects.rga_visualiser.rga_visualiser import parse_rgadata

    source = tmp_path / "Analog-20260820-120000-000.rgadata"
    old = time.time() - 3600
    source.write_bytes(b"not an RGA file")
    import os

    os.utime(source, (old, old))
    database = tmp_path / "scans.sqlite"
    with scan_cache.ScanCache(database) as cache:
        with pytest.raises(ValueError, match="not an SRS RGASoft"):
            cache.load(source)

    decoded: list[Path] = []

    def counting_parse(path: Path) -> object:
        decoded.append(path)
        return parse_rgadata(path)

    monkeypatch.setattr(scan_cache, "parse_rgadata", counting_parse)
    with scan_cache.ScanCache(database) as cache:
        with pytest.raises(ValueError, match="not an SRS RGASoft"):
            cache.load(source)
        assert cache.hits == 1
    assert decoded == []

    _write_rgadata(source, [[1e-9, 2e-9]], old + 1)
    with scan_cache.ScanCache(database) as cache:
        assert len(cache.load(source).scans) == 1
    assert decoded == [source]
