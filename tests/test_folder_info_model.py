"""The Folder info window's model (``helab/utils/folder_info.py``; Q64.1–Q64.10) from fake reads and memory: each
section's lines and actions, the only-copy wording with when HeLab last looked (Q64.8), "nothing saved" only from a read
that worked, a failed read never saying so, RAM only, store-v3, long lists shortened with a detail list (Q64.7), memory
against the store, Copy as text, and ``Reads``: one read in flight, a newer ask replacing the queued one, a retarget
dropping the old answer."""
from __future__ import annotations

import time
from typing import Any

from helab.utils import folder_info
from helab.utils.folder_info import Memory, Reads, Session, build

NOW = time.time()
PATH = "/data/run/x"
ROOT = ("/data/run", "uuid-1", "run")


def part(status: str = "found", error: str = "") -> dict[str, str]:
    return {"status": status, "error": error}


def answer(**changes: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "folder_info", "path": PATH, "key": "root://uuid-1/x", "root_state": "rooted", "layout": 4,
        "read_at": NOW - 5, "store": "s", "parts": {name: part() for name in (
            "raw", "layers", "views", "seed", "results", "prefs", "convert_prefs", "choices", "constants", "history",
            "summary", "listing", "converted")},
        "raw": {"shots": 120, "bytes": 18_000_000, "first": 1, "last": 120, "saved_first": NOW - 3600,
                "saved_last": NOW - 60, "last_used": NOW - 60, "seen_at": NOW - 100, "only_copy": 0,
                "only_copy_bytes": 0, "gone_first": None, "gone_last": None},
        "layers": [{"layer": "helab:abc", "tags": ["m19v1"], "shots": 120, "first": 1, "last": 120, "rows": 9000,
                    "bytes": 9_000_000, "precision": "g8", "saved_at": NOW - 60, "last_used": NOW - 60,
                    "seen_at": NOW - 100, "gone_at": None, "group": "rebuildable"}],
        "layers_more": 0, "views": [{"source": "", "tag": "m19v1", "last_used": NOW - 60}], "views_more": 0,
        "seed_bytes": 0, "results": {"count": 0, "bytes": 0, "rows": [], "more": 0},
        "prefs": None, "convert_prefs": None, "choices": None, "constants": None, "history": None, "summary": None,
        "listing_at": NOW - 100, "converted": []}
    event.update(changes)
    return event


def memory(**changes: Any) -> Memory:
    values: dict[str, Any] = {"path": PATH, "root": ROOT, "txy_list": "m19v1 › External", "policy": "Raw + what you load",
                              "flags": {"no_cache": False, "no_auto_load": False}}
    values.update(changes)
    return Memory(**values)


def section(info: folder_info.Info, ident: str) -> folder_info.Section:
    return next(section for section in info.sections if section.id == ident)


def texts(info: folder_info.Info, ident: str) -> list[str]:
    return [row.text for row in section(info, ident).rows]


def test_the_sections_come_in_order_with_the_folders_existing_actions() -> None:
    info = build(answer(), memory(), NOW)
    assert [section.id for section in info.sections] == [
        "session", "store", "results", "flags", "choices", "constants", "scan", "converted"]
    assert info.title == f"Folder info — {PATH}"
    actions = {section.id: [action.id for action in section.actions] for section in info.sections}
    assert actions == {"session": [], "store": ["clear_data", "settings_cache"],
                       "results": ["settings_roots", "settings_cache"],
                       "flags": ["flag_no_cache", "flag_no_auto_load", "flag_write_beside"],
                       "choices": ["txy_choose", "policy_choose"], "constants": ["constants_edit"],
                       "scan": ["scan_refresh"], "converted": ["convert", "settings_cache"]}
    assert [action.id for action in info.header_actions] == ["settings_roots", "refresh", "copy"]
    assert info.header[1].text == "⚓ run · /data/run" and info.header[2].text.startswith("As of ")


def test_the_disk_cache_lines_name_raw_pulses_layers_and_loads() -> None:
    lines = texts(build(answer(), memory(), NOW), "store")
    assert lines[0].startswith("Raw pulses: 120 shots (d1–d120) · 18.0 MB · saved ")
    assert lines[1] == "TXY m19v1: 120 shots · 9.0 MB · rebuildable from raw pulses"
    assert lines[2] == "Loads saved: priority modes · m19v1"


def test_only_copies_are_named_with_when_helab_last_looked() -> None:
    looked = NOW - 7200
    raw = {**answer()["raw"], "only_copy": 12, "only_copy_bytes": 1_800_000, "gone_first": looked, "gone_last": looked}
    layers = [*answer()["layers"], {**answer()["layers"][0], "layer": "matlab", "tags": [], "group": "only",
                                    "gone_at": looked - 10}]
    store = section(build(answer(raw=raw, layers=layers, listing_at=looked - 50), memory(), NOW), "store")
    first = store.rows[0]
    assert first.warn and first.text.startswith("⚠ Only copy: 12 shots' raw pulses (1.8 MB) and 1 TXY layer · HeLab "
                                                "last looked ")
    assert folder_info.when(looked, NOW) in first.text and "2h ago" in first.tooltip
    assert "the source files are gone" in first.tooltip
    assert store.more == "All 5 lines ›" and store.detail is not None and len(store.rows) == folder_info.SHOWN - 1
    assert any(cells[0].startswith("TXY External (MATLAB's TXY): 120 shots") and cells[0].endswith("only copy")
               for cells, _ in store.detail.rows)


def test_nothing_saved_only_from_a_read_that_worked() -> None:
    empty = answer(raw={**answer()["raw"], "shots": 0}, layers=[], views=[],
                   parts={**answer()["parts"], "raw": part("missing"), "layers": part("missing"),
                          "views": part("missing")})
    assert texts(build(empty, memory(), NOW), "store") == ["Nothing cached for this folder"]
    failed = build(None, memory(), NOW, error="Disk cache could not be read: disk I/O error")
    for ident in ("store", "results", "converted"):
        assert texts(failed, ident) == [folder_info.NOT_READ]
        assert section(failed, ident).rows[0].warn
    assert any("Couldn't read the disk cache: Disk cache could not be read" in row.text and row.warn
               for row in failed.header)
    every = " ".join(row.text for section in failed.sections for row in section.rows)
    assert "Nothing cached" not in every and "No saved results" not in every and "None recorded" not in every
    assert texts(build(None, memory(), NOW, reading=True), "store") == [folder_info.READING]


def test_a_failed_read_keeps_the_last_good_lines_marked_stale() -> None:
    info = build(answer(), memory(), NOW, error="timed out")
    assert section(info, "store").stale and not section(info, "session").stale
    assert texts(info, "store")[0].startswith("Raw pulses") and "Couldn't read" in info.header[-1].text


def test_a_part_that_failed_says_so_and_the_rest_shows() -> None:
    event = answer(parts={**answer()["parts"], "layers": part("error", "Disk cache could not be read: bad")},
                   layers=[])
    lines = texts(build(event, memory(), NOW), "store")
    assert lines[0] == "Couldn't read layers: Disk cache could not be read: bad" and lines[1].startswith("Raw pulses")
    results = build(answer(parts={**answer()["parts"], "results": part("error", "x")}), memory(), NOW)
    assert texts(results, "results") == ["Couldn't read saved results: x"]


def test_ram_only_offers_place_root_and_needs_a_root_for_the_flags() -> None:
    event = answer(root_state="no_root", key="", parts={name: part("skipped") for name in answer()["parts"]})
    info = build(event, memory(root=None, no_root="no .helab-root found here or above"), NOW)
    assert info.header[1].text == "RAM only: no .helab-root here or above" and info.header[1].warn
    assert [action.id for action in info.header_actions][0] == "place_root"
    assert texts(info, "store") == [folder_info.RAM_ONLY_ROW] and texts(info, "results") == [folder_info.RAM_ONLY_ROW]
    flags = section(info, "flags")
    assert not any(action.enabled for action in flags.actions)
    assert not section(info, "store").actions[0].enabled and section(info, "store").actions[1].enabled


def test_store_v3_shows_store_v4_only() -> None:
    parts = {**answer()["parts"], **{name: part("skipped", "store-v3") for name in ("raw", "layers", "views", "seed",
                                                                                     "results")}}
    info = build(answer(layout=3, parts=parts), memory(store_v4=False), NOW)
    assert texts(info, "store") == [folder_info.STORE_V4_ONLY] and texts(info, "results") == [folder_info.STORE_V4_ONLY]
    assert not any(action.enabled for action in section(info, "choices").actions)


def result(index: int, **changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"result_id": f"r{index}", "analysis_id": "tests.corr", "version": "3", "file_name": "corr.py",
                           "action": "Plot", "settings": f"bins={index}", "settings_full": f"bins={index}",
                           "bytes": 1_000_000, "computed_at": NOW - 600, "saved_at": NOW - 600, "last_used": NOW - index,
                           "damaged": False}
    row.update(changes)
    return row


def test_saved_results_show_a_few_lines_and_open_the_rest_to_the_side() -> None:
    rows = [result(index) for index in range(5)] + [result(9, damaged=True, settings="", analysis_id="tests.gone")]
    event = answer(results={"count": 206, "bytes": 206_000_000, "rows": rows, "more": 200})
    info = build(event, memory(script_names={"tests.corr": "Correlations"}), NOW)
    results = section(info, "results")
    assert len(results.rows) == folder_info.SHOWN - 1 and results.more == "All 206 saved results ›"
    assert results.rows[0].text == "206 saved results · 206 MB"
    assert results.rows[1].text.startswith("Correlations v3 · Plot · bins=0 · used ")
    assert results.detail is not None and len(results.detail.rows) == 7
    assert results.detail.columns == ("Script", "Action", "Settings", "Computed", "Used", "Size")
    damaged = results.detail.rows[5]
    assert damaged[0][0] == "tests.gone v3" and damaged[0][2] == "record unreadable"
    assert results.detail.rows[6][0][0] == "and 200 more not shown"
    few = build(answer(results={"count": 1, "bytes": 1, "rows": [result(1)], "more": 0}), memory(), NOW)
    assert section(few, "results").detail is None and len(section(few, "results").rows) == 2


def test_flags_and_choices_are_memorys_with_the_stores_difference_named() -> None:
    event = answer(prefs={"no_cache": True, "no_auto_load": False, "set_at": 1.0},
                   convert_prefs={"write_beside": True, "set_at": 1.0},
                   choices={"policy": "raw", "source": "helab-only", "tag": "m19v1", "policy_set_at": NOW - 60,
                            "source_set_at": NOW - 60})
    info = build(event, memory(flags={"no_cache": False, "no_auto_load": False}, write_beside=True, txy_own=True,
                               policy_own=False), NOW)
    flags = texts(info, "flags")
    assert flags == ["Don't cache: off (not saved yet)", "Don't auto-load: off", "Write TXY beside: on"]
    assert section(info, "flags").rows[0].warn and section(info, "flags").actions[2].checked is True
    choices = section(info, "choices")
    assert choices.rows[0].text == "TXY: m19v1 › External (this folder's own)"
    assert choices.rows[1].text == "Cache policy: Raw + what you load (Settings')"
    assert "Saved for this folder" in choices.rows[0].tooltip


def test_constants_say_where_each_is_set_and_when_only_this_session() -> None:
    info = build(answer(constants={"values": {"fall_distance": 0.848}, "set_at": NOW - 60}),
                 memory(constants={"fall_distance": (0.848, PATH), "g": (9.8, "/data/run")},
                        constants_note="no .helab-root found here or above"), NOW)
    lines = texts(info, "constants")
    assert lines[0] == "Fall distance h: 0.848 m (this folder)"
    assert lines[1] == "Gravitational acceleration g: 9.8 m/s² (from run)"
    assert lines[2] == "This session only: no .helab-root found here or above"
    assert "Saved for this folder" in section(info, "constants").rows[0].tooltip
    assert texts(build(answer(), memory(), NOW), "constants") == ["None set here or above: the lab's values"]


def test_scan_history_names_failures_newest_first() -> None:
    failures = [{"operation_id": f"o{index}", "revision": index, "failed_at": NOW - 1000 + index, "attempts": 1,
                 "reason": f"timed out {index}", "kind": "error"} for index in range(4)]
    history = {"revision": 4, "blocked": True, "failures": failures, "last_success_at": None}
    info = build(answer(history=history, summary={"status": "ok", "raw_count": 3, "txy_count": 2,
                                                  "scanned_at": NOW - 2000}), memory(), NOW)
    scan = section(info, "scan")
    assert scan.rows[0].text.startswith("Last basic scan: ok · 3 raw, 2 TXY")
    assert scan.rows[1].text == "4 failed status checks · automatic checks skipped" and scan.rows[1].warn
    assert scan.rows[2].text.endswith("timed out 3") and scan.more and scan.detail is not None
    assert scan.detail.rows[-1][0][0].startswith("Last listed: ")
    newer = dict(history, revision=9, blocked=False, failures=failures[:1], last_success_at=NOW - 10)
    assert texts(build(answer(history=history), memory(history=newer), NOW), "scan")[0].startswith(
        "Last folder status check that worked")


def test_converted_txy_by_base_and_an_index_that_cant_be_read() -> None:
    converted = [{"base": "cache", "folder": "/c/converted-txy/abc", "status": "found", "error": "", "last_used": NOW,
                  "tags": [{"tag": "m19v1", "profile": "matlab-2019", "version": 1, "output": "beside", "shots": 3,
                            "bytes": 3000, "newest": NOW - 5},
                           {"tag": "m19v1", "profile": "matlab-2019", "version": 1, "output": "cache", "shots": 2,
                            "bytes": 2_000_000, "newest": NOW - 5}]},
                 {"base": "temp", "folder": "/t/converted-txy/abc", "status": "error",
                  "error": "HeLab's TXY index here can't be read (damaged)", "last_used": None, "tags": []}]
    lines = texts(build(answer(converted=converted), memory(), NOW), "converted")
    assert lines == ["Beside the raw files: m19v1 · 3 shots · 3.0 kB (as recorded)",
                     "Cache folder: m19v1 · 2 shots · 2.0 MB",
                     "Temp folder: HeLab's TXY index here can't be read (damaged)"]
    assert texts(build(answer(), memory(), NOW), "converted") == ["None recorded"]
    unavailable = build(answer(), memory(convert_unavailable="working offline"), NOW)
    assert not section(unavailable, "converted").actions[0].enabled


def test_this_session_and_live() -> None:
    session = Session(loaded_shots=120, ram_bytes=2 * 1024**3, source="m19v1 › External", newest_shot=120,
                      newest_at=NOW - 3, live="Tab 1", auto_convert=True, plots=("A", "B", "C", "D"))
    info = build(answer(), memory(session=session, subtree={"status": "something", "derived_at": NOW - 9}), NOW)
    lines = texts(info, "session")
    assert lines[0] == "Loaded: 120 shots · 2.0 GiB in RAM · m19v1 › External"
    assert lines[1] == "Live: on in Tab 1 · Auto-convert on" and lines[2] == "Plots: A, B, C and 1 more"
    assert lines[3].startswith("Newest shot: 120 · written ") and lines[4].startswith("Subfolders: some have data")
    assert info.live and "Live: refreshes by itself" in info.header[2].text


def test_copy_as_text_has_every_line() -> None:
    rows = [result(index) for index in range(6)]
    info = build(answer(results={"count": 6, "bytes": 6, "rows": rows, "more": 0}), memory(), NOW)
    text = folder_info.as_text(info)
    assert text.startswith(f"Folder info — {PATH}\n⚓ run") and "Saved plot results" in text
    assert all(f"bins={index}" in text for index in range(6))


def test_reads_keep_one_in_flight_and_drop_a_retargeted_answer() -> None:
    reads = Reads()
    assert reads.ask("/a")
    reads.started("o1")
    assert not reads.ask("/a") and not reads.ask("/a") and reads.queued  # (One queued, however often asked.)
    assert reads.answered("o1", "/a")
    assert reads.ended("o1") and not reads.in_flight  # (The queued one goes now.)
    reads.started("o2")
    assert not reads.ask("/b")  # Retargeted while o2 reads /a.
    assert not reads.answered("o2", "/a") and not reads.answered("o2", "/b")
    assert reads.ended("o2")
    reads.started("o3")
    assert reads.answered("o3", "/b") and not reads.answered("o1", "/b")
    assert not reads.ended("other") and not reads.ended("o3") and not reads.in_flight
    reads.started("")  # (Couldn't be queued.)
    assert not reads.in_flight and reads.ask("/b")
