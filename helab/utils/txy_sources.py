"""Which TXY a dataset is made of (Q6.6, Q18.2): MATLAB's ``d_txy_forc<N>.txt``, HeLab's
``d_txy_helab_<tag>_<N>.txt``, or both, per shot.

A load is asked for one **source** (mode), and for HeLab's TXY of one profile, chosen by its tag
(``profile_tag``, Q18.4; the conversion profile's unless a plot picks another):

- ``helab-priority`` (the default for tabs and Live, the ``txy_source`` setting): HeLab's TXY where
  they exist, MATLAB's for the rest;
- ``matlab-priority`` (the default before Q18.2): MATLAB's TXY, HeLab's filling the shots MATLAB lacks;
- ``helab-only`` and ``matlab-only`` (for comparing, a plot on each): one kind each.

Each shot then has an **origin**: ``""`` for MATLAB's, ``helab:<profile hash>`` for HeLab's (only a
TXY that is current is used, so the hash is the profile it was made with). A dataset records its source
and its shots' origins (``TXY_FIELD`` in its metadata); views, results and saved-result keys carry the
origins, so data of one kind of TXY is never taken for another's. The two priority modes share the
identity "" (``identity_source``): they differ only on shots both kinds have, which their origins tell
apart; so data of MATLAB's TXY alone keeps the identity it had before HeLab converted anything, under
either default, and existing caches and saved results stay valid. A view still records its choice
(``DatasetView.txy_choice``), so a plot on one choice never takes another's data as its own.

Data saved before Q18.2 says ``matlab`` or ``helab`` (``LEGACY``): read as the priority modes.

**Priority lists** (Q53.2): a choice is an ordered list of entries, each ``External`` (MATLAB's TXY,
Q53.1's label), a HeLab profile's tag, or ``Conversion`` (the profile HeLab converts with, resolved to
its tag when a load is asked for); each shot takes the first entry with a usable TXY. The four modes are
lists (``list_of``: HeLab priority is ``[Conversion, External]``, or ``[<tag>, External]`` with a tag),
and a list that is one of them (``mode_of``) is saved, sent and identified as that mode, so everything
saved before keeps its meaning and identity. Any other list (always two HeLab entries or more, so its
text has a ``>``) is its own source: its text (``list_text``, e.g. ``m23v1>m19v1>External``) is its
source, choice and identity. Lists are compared resolved (``resolve``).

Standard library only: helpers import it.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence

# The two kinds of TXY a shot comes from (``choose``).
MATLAB = "matlab"
HELAB = "helab"
# The sources (modes).
HELAB_PRIORITY = "helab-priority"
MATLAB_PRIORITY = "matlab-priority"
HELAB_ONLY = "helab-only"
MATLAB_ONLY = "matlab-only"
SOURCES = (HELAB_PRIORITY, MATLAB_PRIORITY, HELAB_ONLY, MATLAB_ONLY)
# The tabs' and Live's when the setting says nothing valid (Tony, Q18.2).
DEFAULT_SOURCE = HELAB_PRIORITY
# Data that names no source (made before Q6.6): MATLAB's alone, as MATLAB priority reads it.
UNNAMED_SOURCE = MATLAB_PRIORITY
LEGACY = {MATLAB: MATLAB_PRIORITY, HELAB: HELAB_PRIORITY}
# A load's payload field (the app's options for finding HeLab's TXY) and a dataset's metadata field
# (what it is made of), both ``txy``.
TXY_FIELD = "txy"
HELAB_ORIGIN = "helab:"
# The source and profile tag of a dataset's choice, as one text (``choice_text``).
_CHOICE_SEPARATOR = "@"

# What the UI calls MATLAB's ``d_txy_forc<N>.txt`` (Q53.1: the label only; files, tags and HeLab's
# ``matlab-2019``/``matlab-2023-lab-edit`` profiles keep their names), in full and in short.
EXTERNAL_LABEL = "External (MATLAB converter)"
EXTERNAL_SHORT = "External"
LABELS = {
    HELAB_PRIORITY: f"HeLab's where made, {EXTERNAL_SHORT} for the rest",
    MATLAB_PRIORITY: f"{EXTERNAL_LABEL}, HeLab's for shots it lacks",
    HELAB_ONLY: "HeLab's only",
    MATLAB_ONLY: f"{EXTERNAL_LABEL} only",
}
SHORT = {HELAB_PRIORITY: "HeLab priority", MATLAB_PRIORITY: f"{EXTERNAL_SHORT} priority", HELAB_ONLY: "HeLab only",
         MATLAB_ONLY: f"{EXTERNAL_SHORT} only"}

# Priority lists (Q53.2): the entries' tokens. A tag is lowercase (``profile.NAME_TAG``), so these never are.
EXTERNAL = "External"
CONVERSION = "Conversion"
LIST_SEPARATOR = ">"
_TAG = re.compile(r"[a-z][a-z0-9]{1,32}\Z", re.ASCII)
Entries = tuple[str, ...]


def is_entry(token: Any) -> bool:
    """``External``, ``Conversion`` or a profile tag."""
    return isinstance(token, str) and (token in (EXTERNAL, CONVERSION) or _TAG.match(token) is not None)


def list_of(source: str, tag: str = "") -> Entries:
    """A mode (``SOURCES``) as a list; its HeLab entry ``tag`` ("": the conversion profile's)."""
    helab = tag or CONVERSION
    return {HELAB_PRIORITY: (helab, EXTERNAL), MATLAB_PRIORITY: (EXTERNAL, helab), HELAB_ONLY: (helab,),
            MATLAB_ONLY: (EXTERNAL,)}[source]


def parse_list(value: Any, tag: str = "") -> Entries | None:
    """A saved or sent choice as a list: a mode (an old name too) with its HeLab entry ``tag`` ("": the
    conversion profile's), a mode and its tag as one text (``helab-priority@m23v1``, ``choice_text``'s form),
    or a list text of two entries or more; None if it names none of them (a lone word, repeated or unknown
    entries)."""
    mode = normal_source(value)
    if mode is not None:
        return list_of(mode, tag)
    if not isinstance(value, str) or not value:
        return None
    if _CHOICE_SEPARATOR in value:
        named, _, given = value.partition(_CHOICE_SEPARATOR)
        mode = normal_source(named)
        return list_of(mode, given) if mode is not None and _TAG.match(given) else None
    entries = tuple(value.split(LIST_SEPARATOR))
    if len(entries) < 2:
        return None
    if len(set(entries)) != len(entries) or not all(is_entry(token) for token in entries):
        return None
    return entries


def list_text(entries: Sequence[str]) -> str:
    return LIST_SEPARATOR.join(entries)


def mode_of(entries: Sequence[str]) -> tuple[str, str] | None:
    """The mode a list is, with its HeLab entry (a tag or ``Conversion``; "" for MATLAB only); None for a list
    that is none of them (two HeLab entries or more)."""
    entries = tuple(entries)
    helab = [token for token in entries if token != EXTERNAL]
    if not entries or len(helab) > 1 or len(set(entries)) != len(entries):
        return None
    if not helab:
        return MATLAB_ONLY, ""
    shapes = {(helab[0],): HELAB_ONLY, (helab[0], EXTERNAL): HELAB_PRIORITY, (EXTERNAL, helab[0]): MATLAB_PRIORITY}
    return shapes[entries], helab[0]


def resolve(entries: Sequence[str], conversion_tag: str) -> Entries:
    """``Conversion`` as the conversion profile's tag, and each entry once (the first kept)."""
    return tuple(dict.fromkeys(conversion_tag if token == CONVERSION else token for token in entries))


def setting_text(entries: Sequence[str]) -> str:
    """A list as the ``txy_source`` setting holds it (no tag of its own: a mode follows the conversion
    profile): the mode when the list is one whose HeLab entry is ``Conversion`` (or none), the mode and its
    tag (``helab-only@m23v1``) when it names another, else its text."""
    mode = mode_of(entries)
    if mode is None:
        return list_text(entries)
    return mode[0] if mode[1] in ("", CONVERSION) else f"{mode[0]}{_CHOICE_SEPARATOR}{mode[1]}"


def folder_row(entries: Sequence[str]) -> tuple[str, str]:
    """A list as store-v4's ``txy_source_prefs`` holds it (``source``, ``tag``; tag "" the conversion
    profile's): a mode and its tag when it is one, else its text and no tag."""
    mode = mode_of(entries)
    if mode is not None:
        return mode[0], "" if mode[1] == CONVERSION else mode[1]
    return list_text(entries), ""


def source_text(value: Any) -> str | None:
    """A source as saved or sent: a mode (an old name too) or another list's text; None if it names neither.
    (A list that is a mode is sent and saved as the mode, with its tag apart.)"""
    mode = normal_source(value)
    if mode is not None:
        return mode
    entries = parse_list(value)
    return list_text(entries) if entries is not None and mode_of(entries) is None else None


def is_list(source: str) -> bool:
    """A source that is a list's text, not a mode."""
    return normal_source(source) is None and source_text(source) is not None


def entries_of(source: str, tag: str = "") -> Entries:
    """A source's entries (a mode's HeLab entry ``tag``, "" the conversion profile's); a source that names
    none: MATLAB's alone, as data that names none (``UNNAMED_SOURCE``)."""
    return parse_list(source, tag) or list_of(UNNAMED_SOURCE, tag)


def short_entry(token: str, conversion_tag: str = "") -> str:
    """An entry as a summary names it: "External", "m23v1", "Conversion (m19v1)"."""
    if token == EXTERNAL:
        return EXTERNAL_SHORT
    if token == CONVERSION:
        return f"Conversion ({conversion_tag})" if conversion_tag else "Conversion"
    return token


def summary(entries: Sequence[str], conversion_tag: str = "") -> str:
    """A list in short: "m23v1 › m19v1 › External"."""
    return " › ".join(short_entry(token, conversion_tag) for token in entries)


def normal_source(value: Any) -> str | None:
    """A source as saved or sent (an old name too), or None if it names none."""
    if not isinstance(value, str):
        return None
    value = LEGACY.get(value, value)
    return value if value in SOURCES else None


def requested_source(value: Any) -> str:
    """The source a load, Live check or save asks for (a mode, or a list's text, Q53.2): the default when it
    names none (``ValueError`` for one that isn't a source)."""
    if value is None or value == "":
        return DEFAULT_SOURCE
    found = source_text(value)
    if found is None:
        raise ValueError(f"Unknown TXY source {value!r} (have {', '.join(SOURCES)}, or a list of entries "
                         f"joined by {LIST_SEPARATOR!r})")
    return found


def choice_tag(source: str, tag: str) -> str:
    """The profile tag a choice depends on: none for MATLAB's alone, nor for a list (its text names its
    tags)."""
    return "" if source == MATLAB_ONLY or is_list(source) else tag


def helab_origin(profile_hash: str) -> str:
    return HELAB_ORIGIN + profile_hash


def is_helab(origin: str) -> bool:
    return origin.startswith(HELAB_ORIGIN)


def wants_helab(source: str) -> bool:
    return source != MATLAB_ONLY


# Caching v2 stage 3 (store-v4): whether HeLab priority converts a raw file on read over a MATLAB TXY that is
# there (Q50.1 = Q~16). Off, the safe default (CoCo, 2026-11-03): a shot whose raw file can't be converted now
# (still settling, damaged) keeps MATLAB's TXY. On, HeLab's conversion wins, with no fallback yet (Q50.1 (b)).
CONVERT_OVER_MATLAB = False


def converts_over_matlab(source: str) -> bool:
    """Whether a load of ``source`` converts on read the shots MATLAB's TXY has too: HeLab only always, HeLab
    priority only with ``CONVERT_OVER_MATLAB``, MATLAB priority and MATLAB only never (Q50.1); a list
    (Q~1, generalising Q50.1 (a)) when External isn't in it, or comes after a HeLab entry with the flag."""
    normal = normal_source(source)
    if normal is None and is_list(source):
        entries = entries_of(source)
        return EXTERNAL not in entries or CONVERT_OVER_MATLAB and entries[0] != EXTERNAL
    return normal == HELAB_ONLY or normal == HELAB_PRIORITY and CONVERT_OVER_MATLAB


def choose(source: str, matlab: bool, helab: bool, held: str | None = None) -> str | None:
    """Which kind a shot's TXY is taken from, ``"matlab"`` or ``"helab"`` (None: neither is there).
    ``held``: the origin the caller already holds the shot from (Live), kept while that kind is
    still there, so a MATLAB TXY appearing for a shot HeLab filled doesn't stop Live."""
    source = normal_source(source) or source
    if held is not None and source in (MATLAB_PRIORITY, HELAB_PRIORITY):
        if is_helab(held) and helab:
            return HELAB
        if not is_helab(held) and matlab:
            return MATLAB
    order = {MATLAB_PRIORITY: (MATLAB, HELAB), HELAB_PRIORITY: (HELAB, MATLAB), MATLAB_ONLY: (MATLAB,),
             HELAB_ONLY: (HELAB,)}[source]
    for kind in order:
        if (matlab if kind == MATLAB else helab):
            return kind
    return None


def origins_of(metadata: Mapping[str, Any]) -> dict[int, str]:
    """A dataset's shots that aren't MATLAB's, with their origin, from its metadata."""
    record = metadata.get(TXY_FIELD)
    origins = record.get("origins") if isinstance(record, Mapping) else None
    found: dict[int, str] = {}
    if isinstance(origins, Mapping):
        for shot, origin in origins.items():
            try:
                found[int(shot)] = str(origin)
            except (TypeError, ValueError):
                continue
    return found


def empty_helab_shots(metadata: Mapping[str, Any], data: Mapping[int, Any]) -> list[int]:
    """Shots read from HeLab's TXY that hold no hits (a 0-byte TXY: its conversion found none, A17.1), from
    the data in RAM (``len`` of each shot's array)."""
    return sorted(shot for shot, origin in origins_of(metadata).items()
                  if is_helab(origin) and shot in data and len(data[shot]) == 0)


def source_of(metadata: Mapping[str, Any]) -> str:
    """A dataset's source; data that names none (made before Q6.6) is MATLAB's alone."""
    record = metadata.get(TXY_FIELD)
    return source_text(record.get("source") if isinstance(record, Mapping) else None) or UNNAMED_SOURCE


def tag_of(metadata: Mapping[str, Any]) -> str:
    """The profile tag a dataset's HeLab TXY were asked for ("" for MATLAB's alone, or data made before
    Q18.4)."""
    record = metadata.get(TXY_FIELD)
    tag = record.get("profile_tag") if isinstance(record, Mapping) else None
    return choice_tag(source_of(metadata), tag if isinstance(tag, str) else "")


def metadata_choice(metadata: Mapping[str, Any]) -> str:
    """A dataset's choice (``choice_text``) from its metadata; "" when it names none (made before Q6.6:
    MATLAB's alone)."""
    if not isinstance(metadata.get(TXY_FIELD), Mapping):
        return ""
    return choice_text(source_of(metadata), tag_of(metadata))


def same_choice(one: str, other: str) -> bool:
    """Two datasets' choices could hold each other's data: equal, or one naming none (MATLAB's alone, made
    before Q6.6) and the other a priority source's (which reads MATLAB's alone alike)."""
    if one == other:
        return True
    if one and other:
        return False
    return source_of_choice(one or other) in (HELAB_PRIORITY, MATLAB_PRIORITY)


def source_of_choice(choice: str) -> str:
    """The source of a choice text ("": MATLAB's alone, as data that names none)."""
    return source_text(choice.split(_CHOICE_SEPARATOR, 1)[0]) or UNNAMED_SOURCE


def choice_text(source: str, tag: str) -> str:
    """A source and profile tag as one text (``helab-only@p22v1``; a MATLAB-only choice has no tag)."""
    tag = choice_tag(source, tag)
    return f"{source}{_CHOICE_SEPARATOR}{tag}" if tag else source


def identity_source(source: str) -> str:
    """The source as a view's identity names it: "" for the two priority modes (their shots' origins
    tell their data apart), so MATLAB's TXY alone keep the identity (and saved results) they had under
    either default; else the mode's name, or a list's text (Q53.2: a list is its own identity)."""
    return "" if source in (HELAB_PRIORITY, MATLAB_PRIORITY) else source


def profiles_of(metadata: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Profile hash → {name, version, calibrated} of the HeLab TXY in a dataset."""
    record = metadata.get(TXY_FIELD)
    profiles = record.get("profiles") if isinstance(record, Mapping) else None
    return {str(key): dict(value) for key, value in profiles.items() if isinstance(value, Mapping)} \
        if isinstance(profiles, Mapping) else {}


def on_read_of(metadata: Mapping[str, Any]) -> set[int]:
    """The HeLab shots of a dataset made from their raw files when read (caching v2 stage 3, S3~6)."""
    record = metadata.get(TXY_FIELD)
    shots = record.get("on_read") if isinstance(record, Mapping) else None
    return {int(shot) for shot in shots if isinstance(shot, int)} if isinstance(shots, list) else set()


def describe(source: str, origins: Mapping[int, str], profiles: Mapping[str, Mapping[str, Any]],
             shots: int, on_read: int = 0) -> str:
    """``TXY: External`` / ``TXY: HeLab's (matlab-2019 v1) for 3 of 10 shots, External for the rest``; with
    ``on_read`` of the HeLab shots made from their raw files when read, "converted from raw" (S3~6)."""
    count = len(origins)
    names = sorted({_profile_text(origin[len(HELAB_ORIGIN):], profiles) for origin in origins.values()})
    helab = f"HeLab's ({', '.join(names)})" if names else "HeLab's"
    if not count:
        return ("TXY: none of HeLab's (no current HeLab TXY)" if EXTERNAL not in entries_of(source)
                else f"TXY: {EXTERNAL_SHORT}")
    from_raw = ("" if not on_read else ", converted from raw" if on_read >= count
                else f" ({on_read:,} converted from raw)")
    if count >= shots:
        return f"TXY: {helab}{from_raw}"
    return f"TXY: {helab} for {count:,} of {shots:,} shots{from_raw}, {EXTERNAL_SHORT} for the rest"


def _profile_text(profile_hash: str, profiles: Mapping[str, Mapping[str, Any]]) -> str:
    profile = profiles.get(profile_hash)
    if not profile:
        return f"profile {profile_hash[:8]}"
    names = profile.get("names")
    if isinstance(names, list) and len(names) > 1:
        return " / ".join(str(name) for name in names)  # Profiles of one output: their TXY are alike.
    return f"{profile.get('name', '?')} v{profile.get('version', '?')}"


def with_list(txy: Mapping[str, Any], entries: Sequence[str],
              profiles: Callable[[str], dict[str, Any] | None]) -> dict[str, Any]:
    """A load's TXY options for a list (Q53.2). ``txy`` holds the conversion profile's ``profile_hash``,
    ``profile_tag`` and ``profile`` (``Conversion``'s); ``profiles``: tag → those fields of another profile
    (None for one it doesn't know). A list that is a mode is sent as the mode, as before: its HeLab entry's
    profile (a tag it doesn't know keeps the profile asked for). Any other list: its text as ``source`` and
    ``entries``, each ``{"external": True}`` or ``{"tag", "profile_hash", "profile"}`` (a tag it doesn't know
    with hash "", whose TXY in HeLab's folders are taken whatever made them, as a load of no profile does).
    ``txy``'s ``conversion`` (FolderCache sends it), when there, is ``Conversion``'s instead: a helper applying a
    folder's row over options already resolved."""
    conversion = txy.get("conversion")
    if isinstance(conversion, Mapping) and conversion.get("profile_tag"):
        txy = {**txy, **{key: conversion[key] for key in ("profile_hash", "profile_tag", "profile") if key in conversion}}
    conversion_tag = str(txy.get("profile_tag") or "")
    resolved = resolve(entries, conversion_tag) if conversion_tag else tuple(entries)
    found = {key: value for key, value in txy.items() if key != "entries"}
    mode = mode_of(resolved)
    if mode is not None:
        found["source"] = mode[0]
        tag = mode[1]
        if tag and tag not in (CONVERSION, conversion_tag) and (profile := profiles(tag)) is not None:
            found.update(profile)
        return found
    items: list[dict[str, Any]] = []
    for token in resolved:
        if token == EXTERNAL:
            items.append({"external": True})
            continue
        if token in (CONVERSION, conversion_tag):
            profile = {"profile_hash": txy.get("profile_hash"), "profile": txy.get("profile")}
        else:
            profile = profiles(token) or {}
        given = profile.get("profile")
        items.append({"tag": conversion_tag if token == CONVERSION else token,
                      "profile_hash": str(profile.get("profile_hash") or ""),
                      "profile": dict(given) if isinstance(given, Mapping) else {"name": token}})
    return {**found, "source": list_text(resolved), "entries": items}


def payload_entries(txy: Mapping[str, Any]) -> list[dict[str, Any]]:
    """A load's entries in order (``with_list``'s form): a mode's from its ``source`` and its one profile
    (``profile_hash``, ``profile_tag``, ``profile``); a list's from its ``entries`` (an entry whose tag the
    text doesn't name, or missing, from the text: hash "")."""
    source = requested_source(txy.get("source"))
    mode = normal_source(source)
    if mode is not None:
        helab: dict[str, Any] = {"tag": str(txy.get("profile_tag") or ""),
                                 "profile_hash": str(txy.get("profile_hash") or ""),
                                 "profile": txy.get("profile") if isinstance(txy.get("profile"), Mapping) else {}}
        return [{"external": True} if token == EXTERNAL else dict(helab) for token in list_of(mode)]
    given = {str(item.get("tag")): item for item in txy.get("entries") or () if isinstance(item, Mapping)}
    found: list[dict[str, Any]] = []
    for token in entries_of(source):
        if token == EXTERNAL:
            found.append({"external": True})
            continue
        item = given.get(token) or {}
        profile = item.get("profile")
        found.append({"tag": token, "profile_hash": str(item.get("profile_hash") or ""),
                      "profile": dict(profile) if isinstance(profile, Mapping) else {"name": token}})
    return found


def with_choices(txy: Mapping[str, Any], choices: Mapping[str, Any],
                 profiles: Callable[[str], dict[str, Any] | None]) -> dict[str, Any]:
    """The tab's TXY options with the folder's own choice (caching v2 stage 2, Q45.2): its ``source``, and its
    ``tag``'s profile (``profiles``: tag → ``profile_hash``, ``profile_tag``, ``profile``; None for one it
    doesn't know, which keeps the profile asked for); "" follows the global one; a list's text (Q53.2) is that
    list (``with_list``). Only the tab's own loads (``tab``) follow it: a plot's choice is its own."""
    entries = parse_list(choices.get("source"), str(choices.get("tag") or ""))
    if entries is None or not txy.get("tab", True):
        return dict(txy)
    return with_list(txy, entries, profiles)
