"""The Folder info window's model (Q64.1–Q64.10): one folder's state as sections of one-line rows, from one helper read
(``cache_admin`` "folder_info", ``helab.io_ops.folder_info``) and the app's memory.

``build`` turns the read's event and a ``Memory`` (what the window gathered from ``FolderCache`` and the tab, memory
only) into an ``Info``: a header, then the sections, each with its actions (the folder's existing ones, by ID: the
window calls them) and, when long, a detail list for the side pane. The read is the truth for what HeLab holds; memory
for what applies now. No part says nothing is saved unless the read found none; a failed read says so. ``Reads`` keeps
at most one read in flight. Qt-free (``PURE`` in ``tests/test_headless_imports.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
import os
from typing import Any, Collection, Mapping, Sequence

from helab.analysis.physics import CONSTANTS
from helab.utils.number_format import byte_size
from helab.utils.time_format import relative_age

# A list section shows this many rows; a longer one shows one fewer and a link to its detail pane.
SHOWN = 4
ONLY_COPY_TOOLTIP = ("Only copy: the source files are gone. HeLab keeps these in its disk cache, but the folder's "
                     "files for them weren't there when HeLab last listed the folder{looked}. HeLab learns a file is "
                     "gone only when it lists the folder; if the files are back, Retry / Refresh lists it again and "
                     "clears this.")
NOT_READ = "Not read: see above"
READING = "Reading…"
STORE_V4_ONLY = "Shown for store-v4 only"
NEEDS_ROOT = "Needs a .helab-root at or above this folder"
RAM_ONLY_ROW = "RAM only: no .helab-root here or above, so nothing is cached for this folder"
_TITLES = {constant.key: (constant.title, constant.unit) for constant in CONSTANTS}
_OUTPUTS = {"cache": "Cache folder", "temp": "Temp folder", "beside": "Beside the raw files"}
_GROUPS = {"rebuildable": "rebuildable from raw pulses", "seen": "its sources were there at the last listing",
           "only": "only copy"}


@dataclass(frozen=True)
class Row:
    """One line; its detail in the tooltip; ``warn`` shows it amber."""
    text: str
    tooltip: str = ""
    warn: bool = False


@dataclass(frozen=True)
class Action:
    """A button on a section's title line: ``id`` names the folder's existing action the window calls; ``checked``
    for a toggle (None: a plain button)."""
    id: str
    label: str
    tooltip: str = ""
    enabled: bool = True
    checked: bool | None = None


@dataclass(frozen=True)
class Detail:
    """A section's full list for the side pane: its columns and rows (cells, tooltip)."""
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[tuple[str, ...], str], ...]


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    rows: tuple[Row, ...]
    actions: tuple[Action, ...] = ()
    detail: Detail | None = None
    more: str = ""  # The link row's text to the detail pane ("" without one).
    stale: bool = False  # From the last good read while the latest failed.


@dataclass(frozen=True)
class Info:
    path: str
    title: str
    header: tuple[Row, ...]
    header_actions: tuple[Action, ...]
    sections: tuple[Section, ...]
    live: bool


# The per-folder Clears (Q~6 and Q64.6 b, Tony 2026-11-05): an action ID's part, each asked first from the last read.
CLEARS = {"clear_raw": "raw", "clear_results": "results", "clear_converted": "converted"}
_CLEARED = {"raw": "this folder's cached raw pulses", "results": "this folder's saved results",
            "converted": "this folder's converted TXY"}
READ_FIRST = "Read this folder's disk cache first (Refresh)"
UNVERIFIED = "Not now: this drive isn't verified yet this session"
REMOVING = "Removing…"


@dataclass(frozen=True)
class Question:
    """A Clear's question: its title, text and buttons; ``warn`` when it names only copies."""
    title: str
    text: str
    accept: str
    reject: str = "Keep them"
    warn: bool = False


@dataclass(frozen=True)
class Session:
    """This session's state of the folder, from memory: the data loaded (None: not loaded), its RAM and TXY source,
    the newest shot and when its file was written, Live (its tab's name, "" off) and Auto-convert, the plots open on
    it, and a save waiting for the user's answer."""
    loaded_shots: int | None = None
    ram_bytes: int = 0
    source: str = ""
    newest_shot: int | None = None
    newest_at: float | None = None
    live: str = ""
    auto_convert: bool = False
    plots: tuple[str, ...] = ()
    waiting: str = ""


@dataclass(frozen=True)
class Memory:
    """What the window gathers from memory for ``build`` (no disk): the cache's state, the data root, the folder's
    flags and choices as HeLab applies them now, the constants in effect (each with the folder that sets it), the
    session's scan history and the subfolders' derived status, This session, why some actions aren't available now,
    and the loaded scripts' names by analysis ID."""
    path: str
    cache_on: bool = True
    store_v4: bool = True
    offline: bool = False
    root: tuple[str, str, str] | None = None  # (folder, uuid, label)
    no_root: str | None = None
    pending_root: str = ""  # A location waiting for Same folder or Copy.
    flags: Mapping[str, bool] = field(default_factory=dict)
    write_beside: bool = False
    txy_list: str = ""
    txy_own: bool = False
    policy: str = ""
    policy_own: bool = False
    policy_id: str = ""  # The policy in effect as saved ("raw+used", "raw", "txy"; "" not known).
    constants: Mapping[str, tuple[float, str]] = field(default_factory=dict)
    constants_note: str = ""
    history: Mapping[str, Any] | None = None
    subtree: Mapping[str, Any] | None = None
    session: Session = field(default_factory=Session)
    convert_unavailable: str = ""
    refresh_unavailable: str = ""
    place_root: tuple[bool, str] = (True, "")
    script_names: Mapping[str, str] = field(default_factory=dict)


# Times outside these (s since the epoch: 1980 to 9999) are no real record's: "unknown". Windows' local time refuses
# some of them outright (``OSError``), so the window never formats one.
EARLIEST, LATEST = 315_532_800.0, 253_402_300_799.0


def local_time(seconds: float | None) -> datetime | None:
    """``seconds`` as local time, or None when it can't be one (missing, out of range, or refused by the OS)."""
    if seconds is None or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not (
            EARLIEST <= seconds <= LATEST):
        return None
    try:
        return datetime.fromtimestamp(seconds).astimezone()
    except (OSError, OverflowError, ValueError):
        return None


def when(seconds: float | None, now: float) -> str:
    """A time as the window shows it: "14:02:31" today, "5 Nov 14:02" this year, else "5 Nov 2025"; "unknown" for
    one that can't be a real time (never raises)."""
    moment, today = local_time(seconds), local_time(now)
    if moment is None:
        return "unknown"
    if today is None:
        return f"{moment.day} {moment:%b %Y %H:%M}"
    if moment.date() == today.date():
        return moment.strftime("%H:%M:%S")
    if moment.year == today.year:
        return f"{moment.day} {moment:%b %H:%M}"
    return f"{moment.day} {moment:%b %Y}"


def ago(seconds: float | None, now: float) -> str:
    """``when`` and how long ago: "5 Nov 14:02, 2h ago"; "unknown" for a time ``when`` can't show."""
    if seconds is None or local_time(seconds) is None:
        return "unknown"
    return f"{when(seconds, now)}, {relative_age(max(0.0, now - seconds))}"


def size(value: int | float) -> str:
    return byte_size(int(value), "disk")


def name_of(path: str) -> str:
    return os.path.basename(path.rstrip("/\\")) or path


def layer_name(layer: Mapping[str, Any]) -> str:
    """A TXY layer as users know it: MATLAB's ("External"), or HeLab's by its profile's tags."""
    if layer["layer"] == "matlab":
        return "External (MATLAB's TXY)"
    tags = ", ".join(layer.get("tags") or ())
    return tags or f"HeLab profile {str(layer['layer']).partition(':')[2][:8]}"


def view_name(view: Mapping[str, Any]) -> str:
    source, tag = str(view["source"]), str(view["tag"])
    if not source:
        return f"priority modes · {tag}" if tag else "priority modes"
    return f"{source} · {tag}" if tag else source


def _shots(first: Any, last: Any) -> str:
    return "" if first is None else f" (d{first}–d{last})" if first != last else f" (d{first})"


def _part(event: Mapping[str, Any] | None, name: str) -> str:
    if event is None:
        return "unread"
    return str(((event.get("parts") or {}).get(name) or {}).get("status") or "missing")


def _part_error(event: Mapping[str, Any], name: str) -> str:
    return str(((event.get("parts") or {}).get(name) or {}).get("error") or "")


def _listed(rows: Sequence[Row], detail: Detail | None, noun: str) -> tuple[tuple[Row, ...], str]:
    """At most ``SHOWN`` rows; a longer list shows one fewer and names its detail pane."""
    if len(rows) <= SHOWN or detail is None:
        return tuple(rows), ""
    return tuple(rows[:SHOWN - 1]), f"All {len(detail.rows):,} {noun} ›"


def _unread(event: Mapping[str, Any] | None, error: str, reading: bool) -> Row | None:
    """The row a store section shows before any read worked (None once one did)."""
    if event is not None:
        return None
    return Row(NOT_READ, error, warn=True) if error else Row(READING)


def build(event: Mapping[str, Any] | None, memory: Memory, now: float, *, error: str = "",
          reading: bool = False, clearing: Collection[str] = (), notice: Row | None = None) -> Info:
    """The window's content: ``event`` the last read that worked for this folder (None before one), ``error`` why the
    latest failed ("" if it didn't), ``reading`` a read in flight, ``clearing`` the Clears running (``CLEARS``' parts),
    ``notice`` the header's line for the last one (``cleared``, ``not_cleared``)."""
    stale = bool(error) and event is not None
    usable = None if error else event  # (A Clear asks from a read that is current, never a stale one.)
    sections: tuple[Section, ...] = (
        _session(memory, now),
        _store(event, memory, now, error, reading, _clear_action(usable, "raw", memory, clearing)),
        _results(event, memory, now, error, reading, _clear_action(usable, "results", memory, clearing)),
        _flags(event, memory),
        _choices(event, memory, now),
        _constants(event, memory, now),
        _scan(event, memory, now, error, reading),
        _converted(event, memory, now, error, reading, _clear_action(usable, "converted", memory, clearing)),
    )
    if stale:
        sections = tuple(Section(section.id, section.title, section.rows, section.actions, section.detail, section.more,
                                 stale=section.id not in ("session",)) for section in sections)
    header, actions = _header(event, memory, now, error, reading)
    if notice is not None:
        header = (*header, notice)
    return Info(memory.path, f"Folder info — {memory.path}", header, actions, sections, bool(memory.session.live))


def _header(event: Mapping[str, Any] | None, memory: Memory, now: float, error: str,
            reading: bool) -> tuple[tuple[Row, ...], tuple[Action, ...]]:
    rows = [Row(memory.path, memory.path)]
    actions: list[Action] = []
    key = str((event or {}).get("key") or "")
    if not memory.cache_on:
        rows.append(Row("Disk cache off this session: RAM only", "HeLab keeps nothing on disk this session."))
    elif memory.pending_root:
        rows.append(Row("⚓ Waiting for Same folder or Copy", f"This .helab-root is also at another location: "
                                                             f"answer Review… first.\n\n{memory.pending_root}",
                        warn=True))
        actions.append(Action("review_root", "Review…", "Same folder or a copy of it?"))
    elif memory.root is not None:
        folder, identifier, label = memory.root
        rows.append(Row(f"⚓ {label or name_of(folder)} · {folder}",
                        f"Disk cache on, using the data root at {folder} (“{label or name_of(folder)}”, {identifier})."
                        + (f"\nThis folder's key: {key}" if key else "")))
        actions.append(Action("settings_roots", "Settings › Data roots…", "This data root in Settings › Data roots: "
                                                                          "its identity, and Clear cached data there"))
    elif memory.no_root is not None or (event or {}).get("root_state") == "no_root":
        rows.append(Row("RAM only: no .helab-root here or above",
                        f"Nothing is cached on disk for this folder: {memory.no_root or 'no data root'}.", warn=True))
    elif (event or {}).get("root_state") == "unverified":
        rows.append(Row("Drive not verified yet this session", "HeLab shows a drive's cache once it has checked the "
                                                               "drive is the one it cached; Refresh after that."))
    else:
        rows.append(Row("Data root: not known yet", "HeLab learns it when a helper lists or reads the folder."))
    if not memory.pending_root and memory.root is None:
        enabled, tooltip = memory.place_root
        actions.append(Action("place_root", "Place .helab-root here…", tooltip, enabled))
    as_of = (f"As of {when(float(event['read_at']), now)}" if event is not None else "Not read yet")
    if reading:
        as_of += " · reading…"
    if memory.session.live:
        as_of += " · Live: refreshes by itself"
    rows.append(Row(as_of, "When HeLab last read this folder's disk cache. "
                    + ("While Live watches the folder, the window refreshes after each Live save and its This session "
                       "lines with each check that brings shots." if memory.session.live else
                       "It reads again on Refresh and after an action started here.")
                    + " Raw pulses are filled after a save, so they show at the next read."))
    if error:
        rows.append(Row(f"Couldn't read the disk cache: {error}",
                        "The lines below are from the last read that worked, if any; nothing here means nothing is "
                        "saved.", warn=True))
    actions += [Action("refresh", "Refresh", "Read this folder's disk cache again"),
                Action("copy", "Copy as text", "Copy everything shown here as text")]
    return tuple(rows), tuple(actions)


def _session(memory: Memory, now: float) -> Section:
    session = memory.session
    rows: list[Row] = []
    if session.loaded_shots is None:
        rows.append(Row("Not loaded", "This folder's data isn't in RAM this session."))
    else:
        text = f"Loaded: {session.loaded_shots:,} shots · {byte_size(session.ram_bytes, 'ram')} in RAM"
        rows.append(Row(text + (f" · {session.source}" if session.source else ""), "This session's data of the folder"
                        + (f", read as {session.source}" if session.source else "") + "."))
    if session.live:
        rows.append(Row(f"Live: on in {session.live}" + (" · Auto-convert on" if session.auto_convert else ""),
                        "Live watches this folder."))
    else:
        rows.append(Row("Live: off" + (" · Auto-convert armed" if session.auto_convert else "")))
    if session.plots:
        shown = ", ".join(session.plots[:3]) + (f" and {len(session.plots) - 3} more" if len(session.plots) > 3 else "")
        rows.append(Row(f"Plots: {shown}", "\n".join(session.plots)))
    if session.newest_shot is not None:
        rows.append(Row(f"Newest shot: {session.newest_shot:,}"
                        + (f" · written {when(session.newest_at, now)}" if session.newest_at else ""),
                        "The highest shot number in the data loaded, and when its file was last written."))
    if session.waiting:
        rows.append(Row(session.waiting, "The disk cache asks before this save.", warn=True))
    subtree = memory.subtree
    if subtree:
        status = "some have data" if subtree.get("status") == "something" else "none have data"
        rows.append(Row(f"Subfolders: {status} (as of {when(float(subtree.get('derived_at') or 0), now)})",
                        "From this folder's listed subfolders' statuses, never their own subfolders."))
    return Section("session", "This session", tuple(rows))


def _store(event: Mapping[str, Any] | None, memory: Memory, now: float, error: str, reading: bool,
           clear: Action) -> Section:
    rooted = memory.root is not None and not memory.pending_root
    actions = (Action("clear_data", "Clear loaded data cache",
                      "Remove this folder's cached data, TXY layers and raw pulses whose files are there (only copies "
                      "stay), as the right-click's Clear loaded data cache does" if rooted else NEEDS_ROOT, rooted),
               clear,
               Action("settings_cache", "Settings › Cache…", "Clear cached data, analysis and converted TXY of every "
                                                             "folder, by kind"))
    unread = _unread(event, error, reading)
    if unread is not None:
        return Section("store", "Disk cache", (unread,), actions)
    assert event is not None
    if event.get("root_state") == "no_root" or not memory.cache_on:
        return Section("store", "Disk cache", (Row(RAM_ONLY_ROW),), actions)
    if event.get("root_state") == "unverified":
        return Section("store", "Disk cache", (Row("Not read: this drive isn't verified yet this session"),), actions)
    if _part(event, "raw") == "skipped":
        return Section("store", "Disk cache", (Row(STORE_V4_ONLY, "The disk cache is the older store-v3 this "
                                                                  "session."),), actions)
    rows: list[Row] = []
    raw = event.get("raw") or {}
    layers = list(event.get("layers") or ())
    only_layers = [layer for layer in layers if layer["group"] == "only"]
    if int(raw.get("only_copy") or 0) or only_layers:
        looked = max([float(raw.get("gone_last") or 0)] + [float(layer["gone_at"] or 0) for layer in only_layers]
                     + [float(event.get("listing_at") or 0)])
        parts = []
        if raw.get("only_copy"):
            parts.append(f"{int(raw['only_copy']):,} shots' raw pulses ({size(raw['only_copy_bytes'])})")
        if only_layers:
            parts.append(f"{len(only_layers)} TXY layer{'s' if len(only_layers) > 1 else ''}")
        rows.append(Row(f"⚠ Only copy: {' and '.join(parts)} · HeLab last looked {when(looked, now)}",
                        ONLY_COPY_TOOLTIP.format(looked=f" ({ago(looked, now)})" if looked else ""), warn=True))
    for name in ("raw", "layers", "views", "seed"):
        if _part(event, name) == "error":
            rows.append(Row(f"Couldn't read {name.replace('seed', 'older data')}: {_part_error(event, name)}",
                            "This part only; the rest was read.", warn=True))
    if int(raw.get("shots") or 0):
        saved = (f" · saved {when(raw.get('saved_first'), now)}" if raw.get("saved_first") == raw.get("saved_last")
                 else f" · saved {when(raw.get('saved_first'), now)}–{when(raw.get('saved_last'), now)}")
        rows.append(Row(f"Raw pulses: {int(raw['shots']):,} shots{_shots(raw.get('first'), raw.get('last'))} · "
                        f"{size(raw['bytes'])}{saved}",
                        f"HeLab's copy of the folder's raw files (d<N>.txt), from which it converts again.\n"
                        f"Last used {ago(raw.get('last_used'), now)}; last seen by a listing "
                        f"{ago(raw.get('seen_at'), now)}." + (f"\nCache policy: {memory.policy}." if memory.policy
                                                              else "")))
    for layer in layers:
        group = str(layer["group"])
        rows.append(Row(f"TXY {layer_name(layer)}: {int(layer['shots']):,} shots · {size(layer['bytes'])}"
                        + (" · rebuildable from raw pulses" if group == "rebuildable" else
                           " · only copy" if group == "only" else f" · last used {when(layer['last_used'], now)}"),
                        f"Layer {layer['layer']}{_shots(layer.get('first'), layer.get('last'))}, "
                        f"{int(layer['rows']):,} hits, {layer['precision']}; tags {', '.join(layer['tags']) or 'none'}."
                        f"\nSaved {ago(layer['saved_at'], now)}; last used {ago(layer['last_used'], now)}."
                        f"\n{_GROUPS.get(group, group).capitalize()}.", warn=group == "only"))
    if event.get("layers_more"):
        rows.append(Row(f"and {int(event['layers_more']):,} more TXY layers"))
    views = list(event.get("views") or ())
    if views:
        rows.append(Row("Loads saved: " + "; ".join(view_name(view) for view in views),
                        "\n".join(f"{view_name(view)}: last used {ago(view['last_used'], now)}" for view in views)))
    if int(event.get("seed_bytes") or 0):
        rows.append(Row(f"Older dataset (before TXY layers): {size(event['seed_bytes'])}",
                        "A dataset saved before TXY layers; the next load writes its layers."))
    if not rows:
        rows.append(Row("Nothing cached for this folder", "The disk cache holds no raw pulses, TXY layers or loads of "
                                                          "this folder."))
    detail = Detail("Disk cache", ("Line",), tuple(((row.text,), row.tooltip) for row in rows))
    shown, more = _listed(rows, detail, "lines")
    return Section("store", "Disk cache", shown, actions, detail if more else None, more)


def _results(event: Mapping[str, Any] | None, memory: Memory, now: float, error: str, reading: bool,
             clear: Action) -> Section:
    rooted = memory.root is not None
    actions = (clear,
               Action("settings_roots", "Settings › Data roots…", "Clear cached analysis of this data root"
                      if rooted else NEEDS_ROOT, rooted))  # (Every folder's: Disk cache's Settings › Cache….)
    unread = _unread(event, error, reading)
    if unread is not None:
        return Section("results", "Saved plot results", (unread,), actions)
    assert event is not None
    status = _part(event, "results")
    if status == "skipped":
        text = RAM_ONLY_ROW if event.get("root_state") == "no_root" else (
            "Not read: this drive isn't verified yet this session" if event.get("root_state") == "unverified"
            else STORE_V4_ONLY)
        return Section("results", "Saved plot results", (Row(text),), actions)
    if status == "error":
        return Section("results", "Saved plot results", (Row(f"Couldn't read saved results: "
                                                              f"{_part_error(event, 'results')}", warn=True),), actions)
    results = event.get("results") or {}
    if not int(results.get("count") or 0):
        return Section("results", "Saved plot results", (Row("No saved results for this folder"),), actions)
    names = memory.script_names
    entries: list[tuple[tuple[str, ...], str]] = []
    lines: list[Row] = []
    for row in results.get("rows") or ():
        script = names.get(str(row["analysis_id"])) or str(row["analysis_id"])
        script += f" v{row['version']}" if row.get("version") else ""
        settings = "record unreadable" if row.get("damaged") else (row.get("settings") or "default settings")
        tooltip = (f"{script} · {row['action']}\n" + ("Its record can't be read." if row.get("damaged") else
                                                      str(row.get("settings_full") or "Default settings"))
                   + f"\n\nScript file: {row.get('file_name') or 'unknown'}\nComputed {ago(row['computed_at'], now)}; "
                     f"saved {ago(row['saved_at'], now)}; last used {ago(row['last_used'], now)}; {size(row['bytes'])}.")
        lines.append(Row(f"{script} · {row['action']} · {settings} · used {when(row['last_used'], now)} · "
                         f"{size(row['bytes'])}", tooltip, warn=bool(row.get("damaged"))))
        entries.append(((script, str(row["action"]), settings, when(row["computed_at"], now),
                         when(row["last_used"], now), size(row["bytes"])), tooltip))
    if results.get("more"):
        entries.append(((f"and {int(results['more']):,} more not shown", "", "", "", "", ""), ""))
    total = Row(f"{int(results['count']):,} saved results · {size(results['bytes'])}",
                "Plots of this folder with the same data and settings show them without computing again.")
    detail = Detail("Saved plot results", ("Script", "Action", "Settings", "Computed", "Used", "Size"), tuple(entries))
    if len(lines) + 1 <= SHOWN:
        return Section("results", "Saved plot results", (total, *lines), actions)
    return Section("results", "Saved plot results", (total, *lines[:SHOWN - 2]), actions, detail,
                   f"All {int(results['count']):,} saved results ›")


def _flags(event: Mapping[str, Any] | None, memory: Memory) -> Section:
    rooted = memory.root is not None and not memory.pending_root
    saved = (event or {}).get("prefs") or {}
    beside = (event or {}).get("convert_prefs") or {}
    rows = []
    for key, label, on, stored in (
            ("no_cache", "Don't cache", bool(memory.flags.get("no_cache")), saved.get("no_cache")),
            ("no_auto_load", "Don't auto-load", bool(memory.flags.get("no_auto_load")), saved.get("no_auto_load")),
            ("write_beside", "Write TXY beside", memory.write_beside, beside.get("write_beside"))):
        differs = event is not None and _part(event, "prefs" if key != "write_beside" else "convert_prefs") in (
            "found", "missing") and bool(stored) != on
        rows.append(Row(f"{label}: {'on' if on else 'off'}" + (" (not saved yet)" if differs else ""),
                        "This folder only, never its subfolders." + (
                            f"\nThe disk cache says {'on' if stored else 'off'}." if differs else ""), warn=differs))
    rows[:0] = _saved_errors(event, (("prefs", "flags"), ("convert_prefs", "Write TXY beside flag")))
    tip = "This folder only, never its subfolders" if rooted else NEEDS_ROOT
    actions = (Action("flag_no_cache", "Don't cache", tip, rooted, bool(memory.flags.get("no_cache"))),
               Action("flag_no_auto_load", "Don't auto-load", tip, rooted, bool(memory.flags.get("no_auto_load"))),
               Action("flag_write_beside", "Write TXY beside",
                      "Write HeLab's TXY beside the raw files in this folder (asked first)" if rooted else NEEDS_ROOT,
                      rooted, memory.write_beside))
    return Section("flags", "Flags", tuple(rows), actions)


def _saved_errors(event: Mapping[str, Any] | None, parts: Sequence[tuple[str, str]]) -> list[Row]:
    """A warning line for each of ``parts`` (part, what it holds) the read couldn't read (FI-7): the section's lines are
    what HeLab applies now; the saved row is unknown, never "none"."""
    if event is None:
        return []
    return [Row(f"Couldn't read the saved {what}: {_part_error(event, name)}",
                "The lines here are what HeLab applies this session; what the disk cache holds for this folder "
                "couldn't be read, so whether they are saved is unknown.", warn=True)
            for name, what in parts if _part(event, name) == "error"]


def _whose(own: bool) -> str:
    return "this folder's own" if own else "Settings'"


def _choices(event: Mapping[str, Any] | None, memory: Memory, now: float) -> Section:
    enabled = memory.root is not None and memory.store_v4 and not memory.pending_root
    saved = (event or {}).get("choices") or {}
    rows: tuple[Row, ...] = (
            Row(f"TXY: {memory.txy_list} ({_whose(memory.txy_own)})" if memory.txy_list else "TXY: unknown",
                "Which TXY this folder's tab and Live load." + (
                    f"\nSaved for this folder {ago(saved.get('source_set_at'), now)}." if saved.get("source") else "")),
            Row(f"Cache policy: {memory.policy} ({_whose(memory.policy_own)})" if memory.policy else "Cache policy: unknown",
                "What this folder's saves keep in the disk cache." + (
                    f"\nSaved for this folder {ago(saved.get('policy_set_at'), now)}." if saved.get("policy") else "")))
    rows = (*_saved_errors(event, (("choices", "TXY list and cache policy"),)), *rows)
    tip = "" if enabled else NEEDS_ROOT if memory.store_v4 else STORE_V4_ONLY
    actions = (Action("txy_choose", "TXY for this folder…", tip or "Which TXY this folder's tab and Live load",
                      enabled),
               Action("policy_choose", "Cache policy for this folder…",
                      tip or "What this folder's saves keep in the disk cache", enabled))
    return Section("choices", "TXY list and cache policy", rows, actions)


def _constant(key: str, value: float) -> tuple[str, str]:
    title, unit = _TITLES.get(key, (key, ""))
    return title, f"{value:.6g}" + (f" {unit}" if unit else "")


def _constants(event: Mapping[str, Any] | None, memory: Memory, now: float) -> Section:
    rows: list[Row] = []
    for key, (value, folder) in sorted(memory.constants.items()):
        title, text = _constant(key, value)
        where = "this folder" if folder == memory.path else f"from {name_of(folder)}"
        rows.append(Row(f"{title}: {text} ({where})", f"Set at {folder}; it applies to its subfolders that don't set "
                                                      "their own."))
    if not rows:
        rows.append(Row("None set here or above: the lab's values", "Right-click › Folder constants… sets values for "
                                                                    "a folder and its subfolders."))
    if memory.constants_note:
        rows.append(Row(f"This session only: {memory.constants_note}", "These values aren't saved.", warn=True))
    saved = (event or {}).get("constants") or {}
    if saved.get("values"):
        own = ", ".join(f"{_constant(key, float(value))[0]} {_constant(key, float(value))[1]}"
                        for key, value in sorted(saved["values"].items()))
        rows[0] = Row(rows[0].text, f"{rows[0].tooltip}\n\nSaved for this folder ({ago(saved.get('set_at'), now)}): "
                                    f"{own}", rows[0].warn)
    rows[:0] = _saved_errors(event, (("constants", "constants"),))
    detail = Detail("Constants", ("Constant",), tuple(((row.text,), row.tooltip) for row in rows))
    shown, more = _listed(rows, detail, "constants")
    return Section("constants", "Constants", shown, (Action("constants_edit", "Folder constants…",
                                                            "Fall distance, fall time and trap frequencies for this "
                                                            "folder and its subfolders"),),
                   detail if more else None, more)


def _scan(event: Mapping[str, Any] | None, memory: Memory, now: float, error: str, reading: bool) -> Section:
    action = (Action("scan_refresh", "Retry / Refresh", memory.refresh_unavailable or
                     "List this folder again and check its status", not memory.refresh_unavailable),)
    saved = (event or {}).get("history")
    history = saved
    if memory.history and (not isinstance(saved, Mapping) or int(memory.history.get("revision") or 0)
                           > int(saved.get("revision") or 0)):
        history = memory.history
    rows: list[Row] = []
    failures = list((history or {}).get("failures") or ())
    if history and failures:
        blocked = bool(history.get("blocked"))
        rows.append(Row(f"{len(failures)} failed status check{'s' if len(failures) > 1 else ''}"
                        + (" · automatic checks skipped" if blocked else " · a later check worked"),
                        "Automatic folder status checks are skipped until a successful manual scan." if blocked else
                        "Previous scan failures; a later scan succeeded.", warn=blocked))
        for failure in reversed(failures):
            rows.append(Row(f"{when(float(failure['failed_at']), now)} · {failure['reason']}",
                            f"Failed {ago(float(failure['failed_at']), now)}"
                            + (f" after {failure['attempts']} attempts" if int(failure.get("attempts") or 1) > 1 else "")))
    if history and history.get("last_success_at"):
        rows.insert(0, Row(f"Last folder status check that worked: {when(float(history['last_success_at']), now)}"))
    summary = (event or {}).get("summary")
    if summary:
        rows.insert(0, Row(f"Last basic scan: {summary.get('status')} · {int(summary.get('raw_count') or 0):,} raw, "
                           f"{int(summary.get('txy_count') or 0):,} TXY · {when(summary.get('scanned_at'), now)}",
                           "The folder's last status check, as the disk cache keeps it."))
    if event is not None and event.get("listing_at"):
        rows.append(Row(f"Last listed: {when(float(event['listing_at']), now)}",
                        "When HeLab last listed this folder completely (its saved listing)."))
    if not rows:
        unread = _unread(event, error, reading)
        rows.append(unread if unread is not None else Row("No status checks saved", "No failures saved either."))
    if event is not None and _part(event, "history") == "error":
        rows.insert(0, Row(f"Couldn't read the saved history: {_part_error(event, 'history')}", warn=True))
    detail = Detail("Scan history", ("Line",), tuple(((row.text,), row.tooltip) for row in rows))
    shown, more = _listed(rows, detail, "lines")
    return Section("scan", "Scan history", shown, action, detail if more else None, more)


def _converted(event: Mapping[str, Any] | None, memory: Memory, now: float, error: str, reading: bool,
               clear: Action) -> Section:
    actions = (Action("convert", "Convert this folder…", f"Not now: {memory.convert_unavailable}"
                      if memory.convert_unavailable else "Convert this folder's raw files to HeLab's TXY",
                      not memory.convert_unavailable),
               clear)  # (Every folder's: Disk cache's Settings › Cache….)
    unread = _unread(event, error, reading)
    if unread is not None:
        return Section("converted", "HeLab's converted TXY", (unread,), actions)
    assert event is not None
    rows: list[Row] = []
    for base in event.get("converted") or ():
        if base["status"] == "error":
            rows.append(Row(f"{_OUTPUTS.get(str(base['base']), base['base'])}: {base['error']}", base["folder"],
                            warn=True))
        for tag in base.get("tags") or ():
            only = int(tag.get("only_copy") or 0)
            rows.append(Row(f"{_OUTPUTS.get(str(tag['output']), tag['output'])}: {tag['tag']} · "
                            f"{int(tag['shots']):,} shots · {size(tag['bytes'])}"
                            + (" (as recorded)" if tag["output"] == "beside" else "")
                            + (f" · ⚠ {only:,} only copies" if only else ""),
                            f"Profile {tag['profile']} v{tag['version']}; newest converted {ago(tag['newest'], now)}; "
                            f"folder last used {ago(base.get('last_used'), now)}.\nAs HeLab's index records them in "
                            f"{base['folder']}."
                            + (f"\n{only:,} of them ({size(tag.get('only_copy_bytes') or 0)}) are the only copy of "
                               "that TXY: their d files were gone when HeLab last looked." if only else ""),
                            warn=bool(only)))
    if not rows:
        rows.append(Row("None recorded", "HeLab's index has no TXY it converted from this folder."))
    detail = Detail("HeLab's converted TXY", ("Line",), tuple(((row.text,), row.tooltip) for row in rows))
    shown, more = _listed(rows, detail, "lines")
    return Section("converted", "HeLab's converted TXY", shown, actions, detail if more else None, more)


def _converted_totals(event: Mapping[str, Any]) -> dict[str, Any]:
    """What a Clear of the folder's converted TXY removes, as the read's index rows say: HeLab's folders' TXY only
    (never beside ones): shots, bytes, the bases holding them, and the only copies among them."""
    totals: dict[str, Any] = {"shots": 0, "bytes": 0, "bases": [], "only_copy": 0, "only_copy_bytes": 0}
    for base in event.get("converted") or ():
        tags = [tag for tag in base.get("tags") or () if tag["output"] != "beside"]
        if tags and str(base["base"]) not in totals["bases"]:
            totals["bases"].append(str(base["base"]))
        for tag in tags:
            totals["shots"] += int(tag["shots"])
            totals["bytes"] += int(tag["bytes"])
            totals["only_copy"] += int(tag.get("only_copy") or 0)
            totals["only_copy_bytes"] += int(tag.get("only_copy_bytes") or 0)
    return totals


def _clear_action(event: Mapping[str, Any] | None, part: str, memory: Memory, clearing: Collection[str]) -> Action:
    """A per-folder Clear's button: enabled when the current read found something of ``part`` to remove; asks first."""
    ident = next(ident for ident, name in CLEARS.items() if name == part)
    label = {"raw": "Clear raw pulses…", "results": "Clear this folder's saved results…",
             "converted": "Clear this folder's converted TXY…"}[part]
    rooted = memory.root is not None and not memory.pending_root
    if part in clearing:
        return Action(ident, label, REMOVING, False)
    if part != "converted" and not rooted:
        return Action(ident, label, NEEDS_ROOT, False)
    if event is None:
        return Action(ident, label, READ_FIRST, False)
    if event.get("root_state") == "unverified":
        return Action(ident, label, UNVERIFIED, False)  # (Its Clear would be refused: never the wrong folder's.)
    if part == "raw":
        if _part(event, "raw") == "skipped":
            return Action(ident, label, STORE_V4_ONLY, False)
        raw = event.get("raw") or {}
        if not int(raw.get("shots") or 0):
            return Action(ident, label, "No raw pulses cached for this folder", False)
        return Action(ident, label, f"Remove HeLab's cached raw pulses of this folder ({size(raw['bytes'])}), after "
                                    "asking; your d files aren't touched")
    if part == "results":
        results = event.get("results") or {}
        if not int(results.get("count") or 0):
            return Action(ident, label, "No saved results for this folder", False)
        return Action(ident, label, f"Remove this folder's {int(results['count']):,} saved results "
                                    f"({size(results.get('bytes') or 0)}), after asking")
    totals = _converted_totals(event)
    if not totals["shots"]:
        return Action(ident, label, "No converted TXY of this folder in HeLab's cache or temp folder", False)
    return Action(ident, label, f"Remove HeLab's converted TXY of this folder ({size(totals['bytes'])}), after asking; "
                                "never TXY written beside the raw files")


def clear_question(event: Mapping[str, Any] | None, ident: str, path: str, now: float,
                   memory: Memory | None = None) -> Question | None:
    """The question a per-folder Clear (``ident``, one of ``CLEARS``) asks, naming the sizes and counts the last read
    (``event``) found and the only copies among them, and for raw pulses whether they come back (``memory``: the
    folder's flags and policy now); None when there is nothing to ask about."""
    part = CLEARS.get(ident)
    if event is None or part is None:
        return None
    name = name_of(path)
    if part == "raw":
        raw = event.get("raw") or {}
        if not int(raw.get("shots") or 0):
            return None
        only = int(raw.get("only_copy") or 0)
        # S4~1's question and only-copy paragraph (Tony's wording, 2026-11-02), for this folder (Q~6 (a)).
        text = (f"Remove HeLab's cached raw pulses of {name} ({size(raw['bytes'])})? Your d files aren't touched. "
                + _raw_again(memory)
                + (f"\n\n{only:,} of them are the only copy: their raw files are gone from the folder, so they can't "
                   "be read again." if only else ""))
        return Question("Clear raw pulses of this folder", text, "Remove cached raw pulses", warn=bool(only))
    if part == "results":
        results = event.get("results") or {}
        count = int(results.get("count") or 0)
        if not count:
            return None
        text = (f"Remove the {count:,} saved plot result{'' if count == 1 else 's'} of {name} "
                f"({size(results.get('bytes') or 0)})? Plots compute them again when they need them. Plots open on it "
                "keep what they show; its cached data, flags and other folders' results stay.")
        return Question("Clear this folder's saved results", text, "Remove saved results")
    totals = _converted_totals(event)
    if not totals["shots"]:
        return None
    places = {"cache": "HeLab's cache folder", "temp": "HeLab's temp folder"}
    where = " and ".join(places.get(str(base), str(base)) for base in totals["bases"])
    only = int(totals["only_copy"])
    raw = event.get("raw") or {}
    looked = raw.get("gone_last")
    known = ("HeLab knows a d file is gone only for shots whose raw pulses it cached, as of its last look at the "
             "folder.")
    text = (f"Remove HeLab's converted TXY of {name}: {totals['shots']:,} shots ({size(totals['bytes'])}) in {where}? "
            "Your d files aren't touched, nor TXY written beside them; shots are converted again when converting is on."
            + (f"\n\n{only:,} of them ({size(totals['only_copy_bytes'])}) are the only copy of that TXY: their d files "
               f"were gone when HeLab last looked ({when(looked, now) if looked else 'unknown'}), so they can't be "
               f"converted from them again. {known}" if only else f"\n\nNone of them is known to be the only copy. "
                                                                  f"{known}"))
    return Question("Clear this folder's converted TXY", text, "Remove converted TXY", warn=bool(only))


def _raw_again(memory: Memory | None) -> str:
    """Whether a folder's cleared raw pulses are cached again (FI-4, CoCo's wording): from its d files at its next
    load, unless Don't cache or a TXY only policy stops that."""
    if memory is not None and memory.flags.get("no_cache"):
        return "They aren't cached again: this folder is set to Don't cache."
    if memory is not None and memory.policy_id == "txy":
        return "They aren't cached again: this folder's cache policy is TXY only."
    return "They're cached again the next time this folder loads."


def cleared(ident: str, now: float) -> Row:
    """The header's line once a per-folder Clear worked."""
    return Row(f"Removed {_CLEARED.get(CLEARS.get(ident, ''), 'it')} · {when(now, now)}",
               "Removed after you confirmed; the lines below are read again and show what is left.")


def not_cleared(ident: str, message: str) -> Row:
    """The header's line when a per-folder Clear was refused or failed: why."""
    return Row(f"Couldn't remove {_CLEARED.get(CLEARS.get(ident, ''), 'it')}: {message}",
               "The lines below are read again and show what the disk cache holds now.", warn=True)


def as_text(info: Info) -> str:
    """Everything shown, as text (Copy as text): the header, then each section with all its lines."""
    lines = [info.title, *(row.text for row in info.header[1:])]
    for section in info.sections:
        lines += ["", section.title]
        if section.detail is not None:
            lines += ["  " + " · ".join(cell for cell in cells if cell) for cells, _ in section.detail.rows]
        else:
            lines += [f"  {row.text}" for row in section.rows]
    return "\n".join(lines)


class Reads:
    """At most one read in flight (Q64.4): asking while one runs queues one more (a newer ask replaces it); retargeting
    drops the old folder's answer. The window calls ``ask``, then ``started`` with the owner it submitted under (""
    when it couldn't be queued); ``answered`` says whether an answer applies; ``ended`` whether to submit the queued
    one now."""

    def __init__(self) -> None:
        self.target = ""
        self.owner = ""
        self.asked_for = ""
        self.queued = False

    @property
    def in_flight(self) -> bool:
        return bool(self.owner)

    def ask(self, path: str) -> bool:
        """Read ``path`` (the window's folder now): True to submit now, False when queued behind the running one."""
        self.target = path
        if self.owner:
            self.queued = True
            return False
        return True

    def started(self, owner: str) -> None:
        self.owner, self.asked_for, self.queued = owner, self.target, False

    def answered(self, owner: str, path: str) -> bool:
        """Whether this answer is the running read's, for the folder shown now."""
        return bool(owner) and owner == self.owner and path == self.target == self.asked_for

    def ended(self, owner: str) -> bool:
        """The running read ended (answered or not): True to submit the queued one now."""
        if not owner or owner != self.owner:
            return False
        self.owner = ""
        queued, self.queued = self.queued, False
        return queued
