"""A plot's TXY choice saved with its records (Q14.2 = Q23.4, A47.5): the record format
(``helab.analysis.presets.TxyChoice``), its check against the sources and profiles, the plot's
"Keep this plot's TXY choice" box, reopening with the choice, never reading the folder by itself
to load it (D4), and script presets (a preset without a choice leaves a plot's as it is, D2).
No real data: datasets are made in memory and helpers never run (requests stay pending)."""
from __future__ import annotations

import json
from typing import Any, List

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from helab.analysis.presets import (Arrangement, SavedPlot, ScriptPreset, ScriptRef, TxyChoice, check_plot, check_txy,
                                    parse)
from helab.analysis.identity import AnalysisIdentity
from helab.utils.folder_cache import Dataset, FolderCache
from helab.utils.settings_defaults import OPEN_PLOTS_SETTING
from helab.utils.settings_store import app_settings
from helab.views.plots.arrangement import PlotReopen
from helab.views.plots.instance import AnalysisInstance
from test_presets_plots import (Windows, cache, folder, fresh_presets, load_through_the_cache, new_window,  # noqa: F401
                                no_disk_cache, runner, windows)

REF = ScriptRef("tests.counted", "Plot", "1")
PROFILES = {"matlab-2019": "m19v1", "plates-2022": "p22v1"}


# The record and its check (Qt-free)


def test_a_plots_txy_choice_round_trips_and_old_records_have_none() -> None:
    plot = SavedPlot(REF, "/data/run", values={"bins": 3}, txy=TxyChoice("helab-only", "plates-2022", "p22v1"),
                     txy_keep=True)
    again = parse(Arrangement((plot,)).dumps()).plots[0]
    assert again.txy == TxyChoice("helab-only", "plates-2022", "p22v1") and again.txy_keep is True
    off = SavedPlot(REF, "/data/run", txy_keep=False)
    data = Arrangement((off,)).to_json()["plots"][0]
    assert "txy" not in data and data["txy_keep"] is False
    assert parse(Arrangement((off,)).dumps()).plots[0].txy_keep is False
    # Saved before: no field, so as the folder's tab, Keep on.
    old = SavedPlot.from_json({"script": REF.to_json(), "path": "/data/run"})
    assert old.txy is None and old.txy_keep is True
    assert SavedPlot.from_json({"script": REF.to_json(), "path": "/data/run", "txy": "nonsense"}).txy is None
    # Script presets too.
    preset = ScriptPreset("p", REF, {"bins": 3}, txy=TxyChoice("matlab-only"))
    assert ScriptPreset.from_json("p", json.loads(json.dumps(preset.to_json()))).txy == TxyChoice("matlab-only")
    assert ScriptPreset.from_json("p", {"format": 1, "script": REF.to_json(), "values": {}}).txy is None
    assert TxyChoice().label() == "As the folder's tab"
    assert TxyChoice("helab-only", "plates-2022", "p22v1").label() == "HeLab's only (p22v1)"


@pytest.mark.parametrize("saved, applied, problem, note", [
    (None, None, "", ""),
    (TxyChoice(), TxyChoice(), "", ""),
    (TxyChoice("helab-only"), TxyChoice("helab-only"), "", ""),
    (TxyChoice("helab-only", "plates-2022", "p22v1"), TxyChoice("helab-only", "plates-2022", "p22v1"), "", ""),
    # Renamed since: found by its tag (its files' name), and said.
    (TxyChoice("helab-only", "plates-2022-old", "p22v1"), TxyChoice("helab-only", "plates-2022", "p22v1"), "",
     "TXY profile “plates-2022-old” is now “plates-2022” (the same tag, p22v1)"),
    # Known by neither: not applied (as the tab), named.
    (TxyChoice("helab-only", "gone", "g1"), None, "TXY profile: saved “gone” (tag g1) isn't a known profile now", ""),
    (TxyChoice("helab-first"), None, "TXY: saved “helab-first” is no longer a source", ""),
    # MATLAB's alone reads no HeLab profile.
    (TxyChoice("matlab-only", "gone", "g1"), TxyChoice("matlab-only"), "", ""),
])
def test_a_saved_txy_choice_is_checked(saved: TxyChoice | None, applied: TxyChoice | None, problem: str,
                                       note: str) -> None:
    choice, found, said = check_txy(saved, PROFILES)
    assert choice == applied and said == note
    if problem:
        assert found is not None and found.text().startswith(problem)
    else:
        assert found is None
    # In a whole plot's check: a problem like any setting's, the choice to apply.
    check = check_plot(SavedPlot(REF, "/data/run", txy=saved), AnalysisIdentity("tests.counted", "1"), [], [], (),
                       PROFILES)
    assert check.txy == applied and bool(check.problems) == bool(problem) and (note in check.notes or not note)


def test_without_profiles_the_profile_isnt_checked() -> None:
    assert check_txy(TxyChoice("helab-only", "any", "a1"), None) == (TxyChoice("helab-only", "any", "a1"), None, "")


# The plot (helpers never run: requests stay pending)


def loads(cache: FolderCache) -> List[Any]:
    """The plots' own TXY loads asked of helpers (a tab's has no ``no_cache``)."""
    return [request for request in cache.service.pending if request.operation == "load"
            and "txy" in request.payload and request.payload.get("no_cache") is True]


def reopened(qtbot: QtBot, cache: FolderCache, windows: Windows, plot: SavedPlot) -> AnalysisInstance:
    window = new_window(qtbot, cache, windows)
    app_settings().setValue(OPEN_PLOTS_SETTING, Arrangement((plot,)).dumps())
    [instance] = PlotReopen(window.plots, window.scripts).restore()
    return instance


def test_a_reopened_plot_takes_its_saved_choice_and_loads_it_once_its_folder_was_read(
        qtbot: QtBot, cache: FolderCache, windows: Windows) -> None:
    path = folder("read")
    load_through_the_cache(cache, path, range(1, 4), "v1", allow_missing=False)  # A tab's load: the folder read.
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, values={"bins": 3},
                                                         txy=TxyChoice("helab-only", "plates-2022", "p22v1")))
    assert instance.txy_source == "helab-only" and instance.txy_profile is not None
    assert instance.txy_profile.name == "plates-2022"
    assert instance.txy_row is not None and instance.txy_row.source() == "helab-only"
    qtbot.waitUntil(lambda: bool(loads(cache)), timeout=10_000)
    [request] = loads(cache)
    assert request.payload["txy"]["source"] == "helab-only" and request.payload["txy"]["profile_tag"] == "p22v1"
    assert request.payload["no_cache"] is True
    assert instance.txy_saved() == TxyChoice("helab-only", "plates-2022", "p22v1")


def test_a_reopened_plot_never_reads_its_folder_by_itself_for_its_choice(
        qtbot: QtBot, cache: FolderCache, windows: Windows) -> None:
    """D4: its folder's data found in RAM from the disk cache alone (not read this session): it waits
    for a select or Rerun."""
    path = folder("cached")
    data = {shot: np.full((10, 3), float(shot)) for shot in range(1, 4)}
    cached = Dataset(path, "sig-cached", data, {"fingerprint": [[shot, 100 + shot, 1_000 + shot] for shot in data],
                                                "bytes": 720, "verified": False}, 0)
    cache.datasets[cache.dataset_key(cached)] = cached
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, txy=TxyChoice("helab-only")))
    qtbot.waitUntil(lambda: instance._own_waits, timeout=10_000)
    assert loads(cache) == [] and "or Rerun, to load HeLab's only" in instance.status_label.text()
    instance.run()  # Rerun: the user's word.
    assert len(loads(cache)) == 1 and not instance._own_waits


def test_a_tab_load_of_the_folder_lets_a_waiting_choice_load(qtbot: QtBot, cache: FolderCache,
                                                            windows: Windows) -> None:
    path = folder("later")
    data = {shot: np.full((10, 3), float(shot)) for shot in range(1, 3)}
    cached = Dataset(path, "sig-later", data, {"fingerprint": [[shot, 100 + shot, 1_000 + shot] for shot in data],
                                               "bytes": 480, "verified": False}, 0)
    cache.datasets[cache.dataset_key(cached)] = cached
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, txy=TxyChoice("matlab-only")))
    qtbot.waitUntil(lambda: instance._own_waits, timeout=10_000)
    load_through_the_cache(cache, path, range(1, 4), "v2", allow_missing=False)
    qtbot.waitUntil(lambda: bool(loads(cache)), timeout=10_000)
    assert not instance._own_waits and loads(cache)[0].payload["txy"]["source"] == "matlab-only"


def test_keep_off_saves_no_choice_and_reopens_off(qtbot: QtBot, cache: FolderCache, windows: Windows) -> None:
    path = folder("keep")
    load_through_the_cache(cache, path, range(1, 4), "v1", allow_missing=False)
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, txy=TxyChoice("helab-only")))
    assert instance.txy_row is not None
    box = instance.txy_row.keep_box
    assert box.isChecked() and box.objectName() == "txy_keep" and box.accessibleName() == "Keep this plot's TXY choice"
    box.click()
    assert instance.txy_keep is False and instance.txy_saved() is None
    saved = instance.saved_plot()
    assert saved.txy is None and saved.txy_keep is False
    again = reopened(qtbot, cache, windows, saved)
    assert again.txy_keep is False and again.txy_row is not None and not again.txy_row.keep_box.isChecked()
    assert again.on_tab_choice()  # Started as the folder's tab.


def test_an_old_record_reopens_as_the_tab(qtbot: QtBot, cache: FolderCache, windows: Windows) -> None:
    path = folder("old")
    load_through_the_cache(cache, path, range(1, 4), "v1", allow_missing=False)
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, values={"bins": 3}))
    qtbot.waitUntil(lambda: instance.shown is not None, timeout=10_000)
    assert instance.on_tab_choice() and instance.txy_keep and loads(cache) == []
    assert instance.txy_saved() == TxyChoice()  # Saved from now on: as the tab, explicitly.


def test_a_script_preset_carries_the_choice_and_one_without_leaves_it(
        qtbot: QtBot, cache: FolderCache, windows: Windows, monkeypatch: pytest.MonkeyPatch) -> None:
    path = folder("preset")
    load_through_the_cache(cache, path, range(1, 4), "v1", allow_missing=False)
    instance = reopened(qtbot, cache, windows, SavedPlot(REF, path, values={"bins": 3}))
    qtbot.waitUntil(lambda: instance.shown is not None, timeout=10_000)
    switched: List[tuple[str, str]] = []
    monkeypatch.setattr(instance, "set_txy_source", lambda source, profile="": switched.append((source, profile)))
    full = {"bins": 4, "mode": "counts"}
    instance.apply_saved(ScriptPreset("without", instance.script_ref(), full, "PyQtGraph"), "left as they were")
    assert switched == []  # D2: the preset says nothing of TXY.
    instance.apply_saved(ScriptPreset("with", instance.script_ref(), full, "PyQtGraph",
                                      txy=TxyChoice("helab-only", "plates-2022", "p22v1")), "left as they were")
    assert switched == [("helab-only", "plates-2022")]
    # Saving a preset from the plot holds its choice (none while Keep is off).
    written: List[ScriptPreset] = []
    def write(preset: ScriptPreset) -> str:
        written.append(preset)
        return ""

    monkeypatch.setattr("helab.views.plots.presets.write_script_preset", write)
    assert instance.presets is not None
    instance.presets._save_as("mine", ask=False)
    assert written[-1].txy == TxyChoice()
    instance.set_txy_keep(False)
    instance.presets._save_as("mine, no TXY", ask=False)
    assert written[-1].txy is None
