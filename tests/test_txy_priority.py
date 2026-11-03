"""TXY priority lists (Q53.2, block 53): the list model, the identity rule (the four modes keep their identities
exactly; any other list is its own), and a load of a folder under a list, where each shot comes from the first
entry with a TXY file, and a raw-only shot is converted on read with the first HeLab entry that can convert
(Q~1, store-v4 only). Temp folders and stores only."""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any

import numpy as np
import pytest

from helab.convert.pipeline import convert_shot
from helab.convert.profile import MATLAB_2019, MATLAB_2023_LAB_EDIT, PLATES_2022, file_tag
from helab.io_ops import helab_txy
from helab.io_ops.txy_cache import builtin_for_tag, txy_array, view_key
from helab.utils import txy_sources
from helab.utils.txy_sources import CONVERSION, EXTERNAL

from test_convert_helab import OLD, raw_bytes, write_raw
from test_txy_loading import first, opened, run_load, v4_options

H19, H23 = MATLAB_2019.content_hash(), MATLAB_2023_LAB_EDIT.content_hash()
M19, M23 = file_tag(MATLAB_2019), file_tag(MATLAB_2023_LAB_EDIT)


def conversion(profile: Any = MATLAB_2019) -> dict[str, Any]:
    """A tab load's options before its list is applied: the conversion profile's (``FolderCache.with_txy``)."""
    return {"source": txy_sources.HELAB_PRIORITY, "profile_hash": profile.content_hash(), "profile_tag": file_tag(profile),
            "profile": {"name": profile.name, "version": profile.version, "calibrated": profile.calibrated}}


# --- the list model -----------------------------------------------------------------------------------------

def test_modes_and_lists_read_and_write_in_their_old_form() -> None:
    assert txy_sources.list_of(txy_sources.HELAB_PRIORITY) == (CONVERSION, EXTERNAL)
    assert txy_sources.list_of(txy_sources.MATLAB_PRIORITY, "m23v1") == (EXTERNAL, "m23v1")
    assert txy_sources.parse_list("helab") == (CONVERSION, EXTERNAL)  # (A legacy value.)
    assert txy_sources.parse_list("matlab-only", "m23v1") == (EXTERNAL,)
    assert txy_sources.parse_list("m23v1>m19v1>External") == ("m23v1", "m19v1", EXTERNAL)
    assert txy_sources.parse_list("helab-only@m23v1") == ("m23v1",)
    for junk in ("", "both", "m23v1", "helab-only@", "helab-only@M2", "nope@m23v1", "m23v1>m23v1", "External>External", "Matlab>m19v1", "M23v1>External", "m23v1>>External", None, 3):
        assert txy_sources.parse_list(junk) is None
    # Every list of one or two entries with at most one HeLab entry is a mode; any other has a ">".
    for source in txy_sources.SOURCES:
        for tag in ("", "p22v1"):
            entries = txy_sources.list_of(source, tag)
            assert txy_sources.mode_of(entries) == (source, "" if source == txy_sources.MATLAB_ONLY else tag or CONVERSION)
            assert txy_sources.folder_row(entries) == (source, "" if source == txy_sources.MATLAB_ONLY else tag)
            assert txy_sources.setting_text(entries) == (source if not tag or source == txy_sources.MATLAB_ONLY
                                                         else f"{source}@{tag}")
            assert txy_sources.parse_list(txy_sources.setting_text(entries)) == entries
    general = ("m23v1", "m19v1", EXTERNAL)
    assert txy_sources.mode_of(general) is None and txy_sources.mode_of(("m23v1", "m19v1")) is None
    assert txy_sources.setting_text(general) == "m23v1>m19v1>External"
    assert txy_sources.folder_row(general) == ("m23v1>m19v1>External", "")
    assert txy_sources.source_text("m23v1>m19v1>External") == "m23v1>m19v1>External"
    assert txy_sources.source_text("m23v1>External") is None  # (A mode's list is sent as the mode.)
    assert txy_sources.resolve((CONVERSION, "m19v1", EXTERNAL), "m19v1") == ("m19v1", EXTERNAL)
    assert txy_sources.summary((CONVERSION, "m23v1", EXTERNAL), "m19v1") == "Conversion (m19v1) › m23v1 › External"


def test_the_four_modes_keep_their_identities_exactly() -> None:
    """A list equal to a mode is sent as that mode, its profile the same as before (``Conversion`` and the tag it
    resolves to alike), so its choice, identity and view key are the mode's byte for byte."""
    base = conversion()
    for source in txy_sources.SOURCES:
        before = {**base, "source": source}
        for entries in (txy_sources.list_of(source), txy_sources.list_of(source, M19)):
            after = txy_sources.with_list(base, entries, builtin_for_tag)
            assert after == before, (source, entries)
            assert view_key(after["source"], after) == view_key(source, before)
        assert txy_sources.identity_source(source) == ("" if source in (txy_sources.HELAB_PRIORITY,
                                                                         txy_sources.MATLAB_PRIORITY) else source)
    # A pinned tag other than the conversion profile's: the mode with that profile, as a plot's pick was.
    pinned = txy_sources.with_list(base, (M23, EXTERNAL), builtin_for_tag)
    assert (pinned["source"], pinned["profile_hash"], pinned["profile_tag"]) == (txy_sources.HELAB_PRIORITY, H23, M23)
    assert txy_sources.identity_source(pinned["source"]) == ""


def test_any_other_list_is_its_own_identity() -> None:
    payload = txy_sources.with_list(conversion(), (M23, CONVERSION, EXTERNAL), builtin_for_tag)
    text = "m23v1>m19v1>External"
    assert payload["source"] == text
    assert [item.get("tag") for item in payload["entries"]] == [M23, M19, None]
    assert payload["entries"][0]["profile_hash"] == H23 and payload["entries"][1]["profile_hash"] == H19
    assert txy_sources.identity_source(text) == text and txy_sources.choice_text(text, M19) == text
    assert txy_sources.source_of_choice(text) == text
    assert view_key(text, payload) == (text, f"{H23}>{H19}")
    assert not txy_sources.same_choice(text, "") and not txy_sources.same_choice(text, "helab-priority@m19v1")
    # Its identity differs from every mode's and every other list's.
    others = {txy_sources.identity_source(source) for source in txy_sources.SOURCES} | {"m19v1>m23v1>External"}
    assert text not in others
    # A tag no profile is known by: its TXY in HeLab's folders whatever made them (hash "").
    unknown = txy_sources.with_list(conversion(), ("u0123abcd", M19), builtin_for_tag)
    assert unknown["entries"][0] == {"tag": "u0123abcd", "profile_hash": "", "profile": {"name": "u0123abcd"}}


def test_a_lists_record_names_its_entries() -> None:
    payload = txy_sources.with_list(conversion(), (M23, M19), builtin_for_tag)
    record = helab_txy.record(payload["source"], {1: "helab:" + H23}, {}, None, payload, [])
    assert record["source"] == "m23v1>m19v1" and record["entries"] == [[M23, H23], [M19, H19]]
    assert (record["profile_hash"], record["profile_tag"]) == ("", "")
    assert helab_txy.saved_wanted(record) == helab_txy.wanted_key(payload)
    assert txy_sources.source_of({"txy": record}) == "m23v1>m19v1" and txy_sources.tag_of({"txy": record}) == ""
    assert txy_sources.metadata_choice({"txy": record}) == "m23v1>m19v1"
    # A mode's record is as before.
    mode = helab_txy.record(txy_sources.HELAB_PRIORITY, {}, {}, None, conversion(), [])
    assert "entries" not in mode and (mode["profile_hash"], mode["profile_tag"]) == (H19, M19)


def test_convert_on_read_follows_q1_for_lists() -> None:
    """Q~1: a list converts only shots no entry has a file of; External blocks unless it isn't in the list."""
    assert not txy_sources.converts_over_matlab("m23v1>m19v1>External")
    assert txy_sources.converts_over_matlab("m23v1>m19v1")
    assert not txy_sources.converts_over_matlab("External>m23v1>m19v1")


# --- a load under a list ------------------------------------------------------------------------------------

RAW = {shot: raw_bytes(10_000 * shot, 20_000 * shot) for shot in range(1, 6)}


def write_text(source: Path, name: str, value: float, mtime: float) -> None:
    (source / name).write_text(f"{value},2,3\n")
    os.utime(source / name, (mtime, mtime))


def mixed_folder(tmp_path: Path) -> Path:
    """Shot 1: External, m19v1 and m23v1; 2: External and m19v1; 3: External; 4: m19v1; 5: raw only. HeLab's
    TXY beside the raw files, current (newer than them); each text's value says which it is."""
    source = tmp_path / "data" / "run"
    source.mkdir(parents=True)
    for shot in RAW:
        write_raw(source, shot, RAW[shot])
    newer = OLD + 60
    for shot in (1, 2, 3):
        write_text(source, f"d_txy_forc{shot}.txt", shot + 0.1, OLD)
    for shot in (1, 2, 4):
        write_text(source, f"d_txy_helab_{M19}_{shot}.txt", shot + 0.19, newer)
    write_text(source, f"d_txy_helab_{M23}_1.txt", 1.23, newer)
    return source


def converted(shot: int, profile: Any) -> Any:
    return txy_array(convert_shot(RAW[shot], profile).txy)


def shots_of(events: list[dict[str, Any]]) -> dict[int, Any]:
    return {event["shot"]: np.load(event["artifact"]) for event in events if event["kind"] == "shot"}


def three(tmp_path: Path) -> dict[str, Any]:
    return txy_sources.with_list({**conversion(), "cache_base": "", "temps": str(tmp_path / "temps")},
                                 (M23, M19, EXTERNAL), builtin_for_tag)


@pytest.mark.parametrize("v4", [True, False], ids=["store-v4", "store-v3"])
def test_each_shot_comes_from_the_first_entry_with_a_txy(tmp_path: Path, v4: bool) -> None:
    source = mixed_folder(tmp_path)
    options = v4_options(tmp_path) if v4 else {"directory": str(tmp_path / "caches" / "store-v3"),
                                               "budget": 8 << 30, "budget_set_at": 1.0}
    txy = three(tmp_path)
    events = run_load(source, tmp_path, options, txy=txy)
    loaded, shots = first(events, "loaded"), shots_of(events)
    values = {shot: float(array[0][0]) for shot, array in shots.items() if shot != 5}
    assert values == {1: 1.23, 2: 2.19, 3: 3.1, 4: 4.19}
    origins = loaded["txy"]["origins"]
    expected_origins = {"1": "helab:" + H23, "2": "helab:" + H19, "4": "helab:" + H19}
    if v4:
        # Shot 5, raw only: converted on read with m23v1, the first HeLab entry (a built-in, so it can convert).
        assert np.array_equal(shots[5], converted(5, MATLAB_2023_LAB_EDIT))
        expected_origins["5"] = "helab:" + H23
        assert loaded["txy"]["on_read"] == [5]
        with opened(options, source) as store:
            assert store.read_view(str(source), *view_key(txy["source"], txy)).value is not None
    else:
        assert 5 not in shots  # (store-v3 never converts on read.)
    assert origins == expected_origins
    assert loaded["txy"]["source"] == "m23v1>m19v1>External"
    assert loaded["txy"]["entries"] == [[M23, H23], [M19, H19]]
    # The next load finds it unchanged (same list, same HeLab folders).
    memory = [list(entry) for entry in loaded["fingerprint"]]
    quick = first(run_load(source, tmp_path, options, txy=txy, memory=memory, base_signature=loaded["signature"],
                           memory_origins=origins), "loaded")
    assert quick.get("unchanged") is True or quick["load_counts"]["read"] == 0


def test_a_list_without_external_leaves_externals_shots_out(tmp_path: Path) -> None:
    source = mixed_folder(tmp_path)
    txy = txy_sources.with_list(conversion(), (M23, M19), builtin_for_tag)
    shots = shots_of(run_load(source, tmp_path, v4_options(tmp_path), txy=txy))
    # Shots 3 (External's alone, not in the list) and 5 (raw only): no entry has a file of them, so they are
    # converted on read with m23v1 (Q~1; as HeLab only converts over MATLAB's TXY).
    assert sorted(shots) == [1, 2, 3, 4, 5] and float(shots[1][0][0]) == 1.23
    assert np.array_equal(shots[3], converted(3, MATLAB_2023_LAB_EDIT))
    # store-v3 (no conversion on read): External's shot 3 is left out, not missing.
    v3 = {"directory": str(tmp_path / "caches" / "store-v3"), "budget": 8 << 30, "budget_set_at": 1.0}
    loaded = first(run_load(source, tmp_path, v3, txy=txy), "loaded")
    assert sorted(int(shot) for shot, *_ in loaded["fingerprint"]) == [1, 2, 4]


def test_a_first_entry_still_being_written_leaves_the_shot_out(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """A shot never falls through to a later entry because its first entry's file is still settling."""
    from helab.io_ops import fingerprints
    monkeypatch.setattr(fingerprints, "SETTLE_SECONDS", 5.0)
    source = mixed_folder(tmp_path)
    write_text(source, f"d_txy_helab_{M23}_3.txt", 3.23, time.time())  # (Just written.)
    shots = shots_of(run_load(source, tmp_path, v4_options(tmp_path), txy=three(tmp_path)))
    assert 3 not in shots and float(shots[2][0][0]) == 2.19


def test_the_modes_load_as_before_through_lists(tmp_path: Path) -> None:
    """HeLab priority and MATLAB priority as lists give the same shots and origins as the modes."""
    source = mixed_folder(tmp_path)
    for source_name, entries in ((txy_sources.HELAB_PRIORITY, (CONVERSION, EXTERNAL)),
                                 (txy_sources.MATLAB_PRIORITY, (EXTERNAL, CONVERSION))):
        as_mode = first(run_load(source, tmp_path, v4_options(tmp_path / f"a{source_name}"),
                                 txy={**conversion(), "source": source_name}), "loaded")
        as_list = first(run_load(source, tmp_path, v4_options(tmp_path / f"b{source_name}"),
                                 txy=txy_sources.with_list(conversion(), entries, builtin_for_tag)), "loaded")
        assert as_mode["txy"] == as_list["txy"] and as_mode["fingerprint"] == as_list["fingerprint"]
    # (HeLab priority: m19v1 where made, External for the rest, and shot 5 converted on read with m19v1.)
    shots = shots_of(run_load(source, tmp_path, v4_options(tmp_path / "c"), txy=conversion()))
    assert float(shots[3][0][0]) == 3.1 and np.array_equal(shots[5], converted(5, MATLAB_2019))


def test_profiles_of_one_output_share_an_origin() -> None:
    """m19v1 and p22v1 share a hash (one output): a list naming both gives their shots one origin."""
    assert PLATES_2022.content_hash() == H19
    payload = txy_sources.with_list(conversion(), (file_tag(PLATES_2022), M19, EXTERNAL), builtin_for_tag)
    assert [item["profile_hash"] for item in payload["entries"] if "tag" in item] == [H19, H19]


# --- the app's side: Settings, a folder's row, a plot's list -------------------------------------------------

def test_folder_cache_resolves_the_settings_the_folders_and_a_plots_list(monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path) -> None:
    from test_raw_fill import frozen
    service, cache = frozen(monkeypatch)
    try:
        path = str(tmp_path)
        cache.set_convert_profile(MATLAB_2019)
        # The default list, [Conversion, External]: HeLab priority with the conversion profile, as before.
        cache.set_tab_source("helab-priority")
        assert cache.tab_list() == (CONVERSION, EXTERNAL)
        tab = cache.with_txy(path, {})["txy"]
        assert (tab["source"], tab["profile_tag"], tab["tab"]) == (txy_sources.HELAB_PRIORITY, M19, True)
        assert "entries" not in tab and tab["conversion"]["profile_tag"] == M19
        assert cache.tab_choice() == f"helab-priority@{M19}"
        # Settings holding a list.
        cache.set_tab_source("m23v1>Conversion>External")
        tab = cache.with_txy(path, {})["txy"]
        assert tab["source"] == "m23v1>m19v1>External" and [item.get("tag") for item in tab["entries"]] == [M23, M19, None]
        assert cache.tab_choice() == "m23v1>m19v1>External" and cache.tab_source() == "m23v1>m19v1>External"
        # Settings pinning a tag of a mode: saved as mode@tag, sent as the mode with that profile.
        cache.set_tab_source(txy_sources.setting_text((M23,)))
        assert cache._tab_source == "helab-only@m23v1"
        tab = cache.with_txy(path, {})["txy"]
        assert (tab["source"], tab["profile_hash"]) == (txy_sources.HELAB_ONLY, H23)
        # A folder's own list wins for the tab's loads only.
        cache.set_tab_source("helab-priority")
        cache.remember_choices(path, {"policy": "", "source": "m23v1>m19v1", "tag": "", "source_set_at": 2.0})
        assert cache.folder_list(path) == (M23, M19) and cache.folder_source(path) == "m23v1>m19v1"
        assert cache.with_txy(path, {})["txy"]["source"] == "m23v1>m19v1"
        # A plot's own list ("list", Conversion among it), not the tab's.
        plot = cache.with_txy(path, {"txy": {"list": [EXTERNAL, CONVERSION]}})["txy"]
        assert (plot["source"], plot["profile_tag"], plot["tab"]) == (txy_sources.MATLAB_PRIORITY, M19, False)
        plot = cache.with_txy(path, {"txy": {"list": [M23, CONVERSION]}})["txy"]
        assert plot["source"] == "m23v1>m19v1" and plot["tab"] is False
        # The folder's row as the store keeps it.
        assert txy_sources.folder_row((CONVERSION, EXTERNAL)) == (txy_sources.HELAB_PRIORITY, "")
    finally:
        service.shutdown()


def test_a_folders_row_holds_a_list_and_refuses_junk(tmp_path: Path) -> None:
    from test_txy_loading import data_folder
    source = data_folder(tmp_path)
    options = v4_options(tmp_path)
    with opened(options, source) as store:
        store.set_txy_source_pref(str(source), "m23v1>m19v1>External", "", 5.0)
        row = store.read_folder_choices([str(source)])[str(source)].value
        assert row is not None and row["source"] == "m23v1>m19v1>External"
        with pytest.raises(ValueError):
            store.set_txy_source_pref(str(source), "both", "", 6.0)
    # A tab load follows it.
    events = run_load(source, tmp_path, options, txy={**conversion(), "source": "", "tab": True,
                                                       "conversion": conversion()})
    assert first(events, "loaded")["txy"]["source"] == "m23v1>m19v1>External"


def test_the_setting_reads_lists_old_values_and_junk(tmp_path: Path) -> None:
    from PyQt6.QtCore import QSettings
    from helab.utils import constants
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    for value, read in (("helab", "helab-priority"), ("matlab-only", "matlab-only"), ("both", "helab-priority"),
                        ("m23v1>m19v1>External", "m23v1>m19v1>External"), ("helab-only@m23v1", "helab-only@m23v1"),
                        ("m23v1", "helab-priority"), ("", "helab-priority")):
        settings.setValue(constants.TXY_SOURCE_SETTING, value)
        assert constants.read_txy_source(settings) == read, value
