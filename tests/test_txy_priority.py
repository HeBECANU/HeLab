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
    """Q~1, Q~2.3: a list converts only shots no stage of its chain has a file of; a list's chain always has
    External (TP-4: as find_list decides), so it blocks unless CONVERT_OVER_MATLAB, External not first."""
    for text in ("m23v1>m19v1>External", "m23v1>m19v1", "External>m23v1>m19v1"):
        assert not txy_sources.converts_over_matlab(text)
    assert txy_sources.converts_over_matlab(txy_sources.HELAB_ONLY)  # (One entry: no chain, as before.)


def test_convert_over_matlab_for_lists_follows_find_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(txy_sources, "CONVERT_OVER_MATLAB", True)
    assert txy_sources.converts_over_matlab("m23v1>m19v1") and txy_sources.converts_over_matlab("m23v1>m19v1>External")
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


def test_a_list_without_external_falls_back_before_converting(tmp_path: Path) -> None:
    """Q~2: a list of several entries falls back to Settings' list, External, then any HeLab TXY; convert on
    read only when nothing in that chain has a file (Q~2.3)."""
    source = mixed_folder(tmp_path)
    txy = txy_sources.with_list(conversion(), (M23, M19), builtin_for_tag)
    events = run_load(source, tmp_path, v4_options(tmp_path), txy=txy)
    shots, record = shots_of(events), first(events, "loaded")["txy"]
    # Shot 3 (External's alone): from the fallback, External; shot 5 (raw only): converted with m23v1.
    assert sorted(shots) == [1, 2, 3, 4, 5] and float(shots[1][0][0]) == 1.23 and float(shots[3][0][0]) == 3.1
    assert np.array_equal(shots[5], converted(5, MATLAB_2023_LAB_EDIT))
    assert record["fallback"] == [3] and "3" not in record["origins"] and record["on_read"] == [5]
    # store-v3 (no conversion on read): shot 5 isn't there.
    v3 = {"directory": str(tmp_path / "caches" / "store-v3"), "budget": 8 << 30, "budget_set_at": 1.0}
    loaded = first(run_load(source, tmp_path, v3, txy=txy), "loaded")
    assert sorted(int(shot) for shot, *_ in loaded["fingerprint"]) == [1, 2, 3, 4]


def test_a_one_entry_list_never_falls_back(tmp_path: Path) -> None:
    source = mixed_folder(tmp_path)
    txy = txy_sources.with_list(conversion(), (M23,), builtin_for_tag)  # (HeLab only of m23v1.)
    shots = shots_of(run_load(source, tmp_path, v4_options(tmp_path), txy=txy))
    # Only m23v1: shot 1's text, and the rest converted from their raw files (External doesn't block one entry).
    assert float(shots[1][0][0]) == 1.23 and all(np.array_equal(shots[shot], converted(shot, MATLAB_2023_LAB_EDIT))
                                                 for shot in (2, 3, 4, 5))


def test_a_plot_falls_back_to_its_folders_list_then_settings(tmp_path: Path) -> None:
    """A plot's chain (Q~2.1): its own list → the folder's (tab's) → Settings' → any TXY."""
    source = mixed_folder(tmp_path)
    for shot in (2, 4):  # (No m19v1 now: shots 2 and 4 only if a fallback names a tag that has them.)
        (source / f"d_txy_helab_{M19}_{shot}.txt").rename(source / f"d_txy_helab_p22v1_{shot}.txt")
    p22 = builtin_for_tag("p22v1")
    assert p22 is not None
    folder = txy_sources.items_of(conversion(), ("p22v1", EXTERNAL), builtin_for_tag)
    txy = {**txy_sources.with_list(conversion(), (M23, EXTERNAL), builtin_for_tag), "fallback": folder}
    # [m23v1, External] own: 1 m23v1, 2 and 3 External; 4 from the folder's p22v1 (fallback); 5 converted.
    record = first(run_load(source, tmp_path, v4_options(tmp_path), txy=txy), "loaded")["txy"]
    assert record["origins"] == {"1": "helab:" + H23, "4": "helab:" + H19, "5": "helab:" + H23}
    assert record["fallback"] == [4] and record["fallback_entries"] == [["p22v1", H19]]


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
        plot = cache.with_txy(path, {"txy": {"list": [M23]}})["txy"]
        assert (plot["source"], plot["profile_hash"]) == (txy_sources.HELAB_ONLY, H23)  # (One entry: a mode.)
        plot = cache.with_txy(path, {"txy": {"list": [M23, CONVERSION]}})["txy"]
        assert plot["source"] == "m23v1>m19v1" and plot["tab"] is False
        # Q~2's fallback: the plot's, the folder's list then Settings'; the folder's tab, Settings'; Settings', none.
        tags = [item.get("tag") for item in plot["fallback"]]
        assert tags == [M23, M19, None]  # (The folder's m23v1 › m19v1, then Settings' Conversion › External.)
        tab = cache.with_txy(path, {})["txy"]
        assert [item.get("tag") for item in tab["fallback"]] == [M19, None]
        assert tab["known"][M19]["profile_hash"] == H19
        assert "fallback" not in cache.with_txy(str(tmp_path / "other"), {})["txy"]
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


# --- the list editor (helab/views/txy_list.py) -------------------------------------------------------------

def test_the_list_editor_ticks_orders_and_follows(qtbot: Any) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialogButtonBox
    from helab.views.txy_list import TxyListDialog
    names = {M19: "matlab-2019", M23: "matlab-2023-lab-edit", "p22v1": "plates-2022"}
    dialog = TxyListDialog("TXY", "", (M23, EXTERNAL), M19, names, "As Settings", "Conversion (m19v1) › External")
    qtbot.addWidget(dialog)
    editor = dialog.editor
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok is not None and ok.isEnabled()
    assert editor.entries() == (M23, EXTERNAL) and editor.summary.text() == "m23v1 › External"
    texts = [editor.list.item(row).text() for row in range(editor.list.count())]  # type: ignore[union-attr]
    assert texts[:3] == ["matlab-2023-lab-edit (m23v1)", "External (MATLAB converter)", "Conversion profile (m19v1)"]
    # Move External up, tick Conversion: the order is the list's.
    editor.list.setCurrentRow(1)
    editor.move_entry(-1)
    conversion = editor.list.item(2)
    assert conversion is not None
    conversion.setCheckState(Qt.CheckState.Checked)
    assert editor.entries() == (EXTERNAL, M23, CONVERSION)
    assert editor.summary.text() == "External › m23v1 › Conversion (m19v1)"
    # Nothing ticked: OK off; the follow box: OK on, the list off, None chosen.
    editor.set_ticked(())
    assert not ok.isEnabled() and editor.summary.text() == "Nothing ticked"
    assert editor.follow_box is not None
    editor.follow_box.setChecked(True)
    assert ok.isEnabled() and editor.entries() is None and not editor.list.isEnabled()
    assert editor.summary.text() == "Conversion (m19v1) › External"
    # A saved tag no profile is known by is still offered, and said so.
    other = TxyListDialog("TXY", "", ("u0123abcd",), M19, names)
    qtbot.addWidget(other)
    first_item = other.editor.list.item(0)
    assert first_item is not None and first_item.text() == "u0123abcd (no profile known by this tag)"


def test_the_fallback_is_said_in_the_plots_line_and_folder_details() -> None:
    from helab.views.FolderDetailsPanel import FolderDetailsPanel
    profiles = {H19: {"name": "matlab-2019", "version": 1}, H23: {"name": "matlab-2023-lab-edit", "version": 1}}
    text = txy_sources.describe("m23v1>m19v1", {1: "helab:" + H23, 2: "helab:" + H23, 3: "helab:" + H19}, profiles, 4,
                                fallback={3: "helab:" + H19, 4: ""})
    assert text.endswith("; 2 shots from the fallback (External, matlab-2019 v1)")
    meta = {"load_counts": {"txy_matlab": 1, "txy_helab": 3},
            "txy": {"source": "m23v1>m19v1", "origins": {"3": "helab:" + H19}, "profiles": profiles,
                    "profile_tag": "", "fallback": [3, 4]}}
    row, tip = FolderDetailsPanel._txy_row(meta)
    assert row.endswith("· 2 fallback") and "(External, matlab-2019 v1)" in tip


def test_a_one_entry_folder_offers_its_profile_to_auto_convert(monkeypatch: pytest.MonkeyPatch,
                                                                tmp_path: Path) -> None:
    """Q~2.2: a folder whose list is one profile Auto-convert doesn't convert with offers it (this session);
    a list of several entries offers nothing (it falls back to the conversion profile's TXY)."""
    from test_raw_fill import frozen
    service, cache = frozen(monkeypatch)
    try:
        path = str(tmp_path)
        cache.set_convert_profile(MATLAB_2019)
        assert cache.auto_convert_offer(path) is None  # (Settings' [Conversion, External].)
        cache.remember_choices(path, {"policy": "", "source": "helab-only", "tag": M23, "source_set_at": 2.0})
        offer = cache.auto_convert_offer(path)
        assert offer is not None and offer.name == "matlab-2023-lab-edit"
        assert cache.auto_convert_profile(path).name == "matlab-2019"
        cache.set_convert_with(path, offer)
        assert cache.auto_convert_profile(path) is offer and cache.auto_convert_offer(path) is None
        assert cache.convert("live", path, profile_used=cache.auto_convert_profile(path))
        [request] = [r for r in service.pending if r.operation == "convert"]
        assert request.payload["profile"]["name"] == "matlab-2023-lab-edit"
        cache.set_convert_with(path, None)
        cache.remember_choices(path, {"source": "m23v1>m19v1", "tag": "", "source_set_at": 3.0})
        assert cache.auto_convert_offer(path) is None
    finally:
        service.shutdown()


# --- review fixes (TP-1 …) ----------------------------------------------------------------------------------

MINE = MATLAB_2019.replace(name="mine", search_depth=40)
UTAG, HUSER = file_tag(MINE), MINE.content_hash()


def app_payload(entries: tuple[str, ...]) -> dict[str, Any]:
    """A tab load's options as FolderCache sends them, the user's profile ``mine`` known by its tag."""
    user = {"profile_hash": HUSER, "profile_tag": UTAG, "profile": {"name": "mine", "version": 1, "calibrated": False}}
    base = {**conversion(), "conversion": conversion(), "tab": True,
            "known": {UTAG: {"profile_hash": HUSER, "profile": user["profile"]}}}
    return txy_sources.with_list(base, entries, lambda tag: user if tag == UTAG else builtin_for_tag(tag))


@pytest.mark.parametrize("row", [("helab-only", UTAG), (f"{UTAG}>m23v1>External", "")], ids=["mode", "list"])
def test_a_folder_row_naming_a_user_profile_stays_that_profile_in_the_helper(tmp_path: Path,
                                                                           row: tuple[str, str]) -> None:
    """TP-1: the helper applies the folder's row (store-v4) over the app's options; a user profile's tag resolves
    to that profile (``known``), never to the conversion profile."""
    from test_txy_loading import data_folder  # noqa: F401  (the store's data root, as a load records it)
    source = mixed_folder(tmp_path)
    write_text(source, f"d_txy_helab_{UTAG}_2.txt", 2.77, OLD + 60)
    options = v4_options(tmp_path)
    with opened(options, source) as store:
        store.set_txy_source_pref(str(source), row[0], row[1], 5.0)
    entries = txy_sources.parse_list(row[0], row[1])
    assert entries is not None
    loaded = first(run_load(source, tmp_path, options, txy=app_payload(entries)), "loaded")
    record = loaded["txy"]
    assert record["origins"]["2"] == "helab:" + HUSER
    if row[1]:
        assert (record["source"], record["profile_hash"], record["profile_tag"]) == ("helab-only", HUSER, UTAG)
    else:
        assert record["entries"][0] == [UTAG, HUSER]


def test_resolving_a_list_for_a_tooltip_never_reads_the_profile_folder(monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Path) -> None:
    """TP-2: tooltips and summaries resolve lists from memory; the profile folder is read once on a request's
    path (``with_txy``), or handed over by Settings' Save."""
    from helab.convert import user_profiles
    from test_raw_fill import frozen
    reads: list[str] = []

    def profiles(self: Any) -> dict[str, Any]:
        reads.append("read")
        return {"mine": MINE}
    monkeypatch.setattr(user_profiles.ProfileLibrary, "profiles", profiles)
    service, cache = frozen(monkeypatch)
    try:
        path = str(tmp_path)
        cache.set_convert_profile(MATLAB_2019)
        cache.remember_choices(path, {"policy": "", "source": f"{UTAG}>m19v1", "tag": "", "source_set_at": 2.0})
        for asked in (cache.folder_source, cache.converts_on_read):  # (A tooltip's.)
            asked(path)
        cache.on_read_shots(path, 3, 1)
        assert reads == [] and cache.profile_by_tag(UTAG) is None  # (Not read yet: unknown, never read here.)
        txy = cache.with_txy(path, {})["txy"]
        assert reads == ["read"] and txy["entries"][0]["profile_hash"] == HUSER and UTAG in txy["known"]
        cache.with_txy(path, {})
        cache.folder_source(path)
        cache.set_convert_profile(MATLAB_2023_LAB_EDIT)  # (Settings' Save: no read either.)
        cache.set_user_profiles([MINE])
        cache.with_txy(path, {})
        assert reads == ["read"] and cache.profile_by_tag(UTAG) is MINE
    finally:
        service.shutdown()


def live_events(source: Path, tmp_path: Path, txy: dict[str, Any], memory: list[Any], origins: dict[str, str],
                **kwargs: Any) -> list[dict[str, Any]]:
    from helab.io_ops.live import live_check
    output = tmp_path / f"live-{time.monotonic_ns()}"
    output.mkdir()
    events: list[dict[str, Any]] = []
    live_check(str(source), str(output), events.append, memory, txy=txy,  # type: ignore[arg-type]
               memory_origins=origins, check_level="full", **kwargs)
    return events


def test_live_under_a_list_reclaims_fallback_shots_converts_and_records_the_fallback(tmp_path: Path) -> None:
    """TP-3: Live under m23v1 › m19v1 (its fallback External, then any HeLab TXY): a shot held from External as a
    fallback is read again once m23v1 has it (never a mismatch); a shot held from m19v1 (an own entry) keeps
    it; a new External-only shot comes from the fallback and the record says so; a new raw-only shot is
    converted on read with m23v1."""
    source = mixed_folder(tmp_path)
    txy = {**txy_sources.with_list(conversion(), (M23, M19), builtin_for_tag), "on_read": True}
    first_load = first(run_load(source, tmp_path, v4_options(tmp_path), txy=txy), "loaded")
    memory = first_load["fingerprint"]
    origins = first_load["txy"]["origins"]
    assert first_load["txy"]["fallback"] == [3] and "3" not in origins and origins["2"] == "helab:" + H19
    newer = OLD + 120
    write_text(source, f"d_txy_helab_{M23}_3.txt", 3.23, newer)  # (m23v1 has shot 3 now: reclaimed.)
    write_text(source, f"d_txy_helab_{M23}_2.txt", 2.23, newer)  # (Held from m19v1, an own entry: kept.)
    write_text(source, "d_txy_forc7.txt", 7.1, OLD)  # (External only: the fallback.)
    write_raw(source, 7, RAW[1])
    write_raw(source, 8, RAW[2])  # (Raw only: converted on read.)
    look = live_events(source, tmp_path, txy, memory, origins)
    assert not [event for event in look if event["kind"] == "shots_missing"]
    seen = [event for event in look if event["kind"] == "live_unchanged"][-1]["live_seen"]
    assert sorted(entry[0] for entry in seen) == [3, 7, 8]
    events = live_events(source, tmp_path, txy, memory, origins, seen=seen)
    assert not [event for event in events if event["kind"] == "shots_missing"]
    result = first(events, "loaded")
    shots = {event["shot"]: np.load(event["artifact"]) for event in events if event["kind"] == "shot"}
    assert [entry["shot"] for entry in result["live_reread"]] == [3] and float(shots[3][0][0]) == 3.23
    assert float(shots[7][0][0]) == 7.1 and np.array_equal(shots[8], converted(2, MATLAB_2023_LAB_EDIT))
    record = result["txy"]
    assert record["origins"]["3"] == "helab:" + H23 and record["origins"]["2"] == "helab:" + H19
    assert record["origins"]["8"] == "helab:" + H23 and 8 in record["on_read"]
    assert record["fallback"] == [7] and record["source"] == "m23v1>m19v1"


def test_lives_save_under_a_list_keeps_held_shots_and_records_the_fallback(tmp_path: Path) -> None:
    """TP-3: ``save_held`` under a list keeps each held shot's TXY while it is there (a shot held from the
    fallback isn't a change when an own entry has it now: Live reads it again, not the save), and its record
    keeps the fallback shots."""
    from helab.io_ops.save_held import save_held
    source = mixed_folder(tmp_path)
    txy = txy_sources.with_list(conversion(), (M23, M19), builtin_for_tag)
    events = run_load(source, tmp_path, v4_options(tmp_path), txy=txy)
    first_load = first(events, "loaded")
    held_dir = tmp_path / "held"
    held_dir.mkdir()
    for shot, array in shots_of(events).items():
        np.save(held_dir / f"{shot}.npy", array)
    write_text(source, f"d_txy_helab_{M23}_3.txt", 3.23, OLD + 120)
    saved: list[dict[str, Any]] = []
    save_held(str(source), saved.append, v4_options(tmp_path), first_load["fingerprint"], [],  # type: ignore[arg-type]
              str(held_dir), txy=txy, held_txy=first_load["txy"])
    assert not [event for event in saved if event["kind"] in ("shots_missing", "error")]
    record = first(saved, "loaded")["txy"]
    assert record["fallback"] == [3] and record["origins"] == first_load["txy"]["origins"]
