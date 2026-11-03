"""What v0.0.7a1 (released; ``e03c32a`` on main) makes of a TXY priority list (Q53.2) that this version saves where
it reads: a store-v3 dataset or result (the hidden ``store_v4=false`` fallback writes the same cache folder) and
the ``txy_source`` setting (both share the native settings). The functions below are 0.0.7a1's, copied verbatim
(``helab/utils/txy_sources.py``, ``helab/io_ops/loading.py``'s ``_helab_unchanged`` source check,
``FolderCache._with_choice``'s relabel, ``constants.read_txy_source``), run on what this code makes. The answer
(design.md §2, "What v0.0.7a1 makes of a list"): no list text is a 0.0.7 source, so its quick checks never take
list data as current, its cache-first read shows it as its tab's source until its check reads again every shot
of another origin (origins keep their old form), its results never match a list's, and the setting reads as its
default."""
from __future__ import annotations

from typing import Any, Mapping

from helab.convert.profile import MATLAB_2019, MATLAB_2023_LAB_EDIT, file_tag
from helab.io_ops import helab_txy
from helab.io_ops.txy_cache import builtin_for_tag
from helab.utils import txy_sources
from helab.utils.txy_sources import CONVERSION, EXTERNAL

# --- v0.0.7a1, verbatim -------------------------------------------------------------------------------------
MATLAB = "matlab"
HELAB = "helab"
HELAB_PRIORITY = "helab-priority"
MATLAB_PRIORITY = "matlab-priority"
HELAB_ONLY = "helab-only"
MATLAB_ONLY = "matlab-only"
SOURCES = (HELAB_PRIORITY, MATLAB_PRIORITY, HELAB_ONLY, MATLAB_ONLY)
DEFAULT_SOURCE = HELAB_PRIORITY
LEGACY = {MATLAB: MATLAB_PRIORITY, HELAB: HELAB_PRIORITY}


def normal_source(value: Any) -> str | None:
    """A source as saved or sent (an old name too), or None if it names none."""
    if not isinstance(value, str):
        return None
    value = LEGACY.get(value, value)
    return value if value in SOURCES else None


def identity_source(source: str) -> str:
    return "" if source in (HELAB_PRIORITY, MATLAB_PRIORITY) else source


def read_txy_source(value: Any) -> str:  # (constants.read_txy_source, with the setting's value given.)
    return normal_source(value) or DEFAULT_SOURCE


def helab_unchanged_by_source(source: str, saved: dict[str, Any]) -> bool | None:
    """``loading._helab_unchanged`` up to its source check: False when it says changed there, None when it goes
    on to compare HeLab's folders."""
    if not saved.get("source"):
        if source == HELAB_ONLY:
            return False
    elif normal_source(saved.get("source")) != source:
        return False
    return None


def with_choice(tab_source: str, asked: Mapping[str, Any], given: Mapping[str, Any]) -> dict[str, Any]:
    """``FolderCache._with_choice`` (its ``payload_source`` the tab's when the request names none)."""
    record: dict[str, Any] = dict(given)
    if normal_source(record.get("source")) is None:
        record["source"] = normal_source(asked.get("source")) or tab_source
    if not record.get("profile_tag"):
        record["profile_tag"] = str(asked.get("profile_tag") or "m19v1")
    record["tab"] = bool(asked.get("tab", True))
    return record
# --- end of v0.0.7a1 ----------------------------------------------------------------------------------------


H19, H23 = MATLAB_2019.content_hash(), MATLAB_2023_LAB_EDIT.content_hash()
M19, M23 = file_tag(MATLAB_2019), file_tag(MATLAB_2023_LAB_EDIT)
LISTS = [(M23, M19, EXTERNAL), (M23, M19), (EXTERNAL, M23, M19), (CONVERSION, M23, EXTERNAL), (M19, M23)]


def payload(entries: tuple[str, ...]) -> dict[str, Any]:
    return txy_sources.with_list({"source": txy_sources.HELAB_PRIORITY, "profile_hash": H19, "profile_tag": M19,
                                  "profile": {"name": "matlab-2019", "version": 1, "calibrated": False}},
                                 entries, builtin_for_tag)


def test_no_list_text_is_a_v007_source_and_the_modes_still_are() -> None:
    for entries in LISTS:
        source = payload(entries)["source"]
        assert txy_sources.is_list(source) and normal_source(source) is None
        assert normal_source(txy_sources.setting_text(entries)) is None
        assert normal_source(txy_sources.folder_row(entries)[0]) is None
    # A list that is a mode is saved as the mode, which 0.0.7 reads exactly.
    for source in SOURCES:
        entries = txy_sources.list_of(source)
        assert normal_source(txy_sources.setting_text(entries)) == source
        assert normal_source(payload(entries)["source"]) == source


def test_v007_never_takes_a_lists_dataset_as_current() -> None:
    """Both quick paths go through ``_helab_unchanged``: a list's record is "changed" for every 0.0.7 source."""
    for entries in LISTS:
        txy = payload(entries)
        record = helab_txy.record(txy["source"], {1: "helab:" + H23}, {}, None, txy, [])
        for source in SOURCES:
            assert helab_unchanged_by_source(source, record) is False


def test_v007s_cache_first_read_relabels_a_list_as_its_tab_and_its_check_reads_other_origins_again() -> None:
    txy = payload((M23, M19, EXTERNAL))
    origins = {1: "helab:" + H23, 2: "helab:" + H19}
    record = helab_txy.record(txy["source"], origins, {}, None, txy, [])
    for tab in SOURCES:
        relabelled = with_choice(tab, {"tab": True}, record)
        assert relabelled["source"] == tab and relabelled["tab"] is True
    # The origins keep 0.0.7's form ({"<shot>": "helab:<hash>"}, External's absent), which its check compares
    # shot by shot (``held_origins.get(shot, "") == origins.get(shot, "")``): shot 1 (m23v1) differs from what
    # 0.0.7's HeLab priority with m19v1 composes, so it is read again.
    assert record["origins"] == {"1": "helab:" + H23, "2": "helab:" + H19}
    assert helab_txy.origins_from(record["origins"]) == origins


def test_a_lists_saved_results_never_match_v007s() -> None:
    """0.0.7 reuses a result only on an exact key match; a key carries ``txy_source`` only when the identity
    source isn't "" (``AnalysisResult.reuse_key``)."""
    old = {identity_source(source) for source in SOURCES}
    for entries in LISTS:
        source = payload(entries)["source"]
        assert txy_sources.identity_source(source) not in old


def test_the_setting_holding_a_list_reads_as_v007s_default() -> None:
    for entries in LISTS:
        assert read_txy_source(txy_sources.setting_text(entries)) == DEFAULT_SOURCE
    assert read_txy_source(txy_sources.setting_text((CONVERSION, EXTERNAL))) == HELAB_PRIORITY
    assert read_txy_source(txy_sources.setting_text((EXTERNAL, CONVERSION))) == MATLAB_PRIORITY
