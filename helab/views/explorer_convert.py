"""Converting raw files outside Live, and the converter's questions (A39.5, Q38.1; Converter UX floor).

**Shares** (A39.5, Q39.2): writing TXY beside the raw files of a folder on a network share
(``cache_location.share_of``: lexical and the OS's mount table, never a stat of the folder) asks first,
once per folder this session (``beside_confirmed``): turning on the folder's beside setting
(``confirm_beside_on_share``, modal: the user's own action), and Live's auto-convert when that folder's
flag is on (``ask_live_beside_on_share``, which ``explorer_live`` opens). The flag stays the persistent
record; the session memory only spares a second question.

**Folder details' offer** (A39.5): a folder on a share with raw files and no TXY of any kind, not
converted by Live, shows a Convert row; clicking it asks (``offer_conversion``): HeLab's cache folder
(recommended), its temp folder, or beside on the share (behind ``confirm_beside_on_share``, which turns
the folder's flag on, offered only where the Live menu offers that setting: ``beside_unavailable``). A beside
conversion starts once the store says the folder's flag is on (``folderPrefsChanged``); a flag that can't be
saved stops it, said in the row. ``ExplorerConverter`` then runs the folder's conversions (``FolderCache.convert``
with the destination chosen, owner ``<tab>:convert``, the background lane): the first only records, as
every conversion's first does, so passes follow a check interval apart while files wait to settle (at
most ``MAX_PASSES``); then the folder is listed and loaded again, so HeLab's new TXY show.

**A beside write that can't be made safely** (Q38.1, Tony 2026-11-02): the helper's ``beside_refused``
(no hard links and no rename that refuses an existing name), then the run fails as before; HeLab asks
(``ask_after_refusal``): Retry, write to HeLab's cache or temp folder instead (the folder's, for the rest of
the session: ``instead``, which Live's auto-convert and Folder details' conversions both follow; the folder's
flag stays), or not now. Never a silent refusal nor a silent fallback. Live's "Convert to HeLab's cache
instead" on a share is kept the same way.

**Convert this folder…** (Q~4, Tony 2026-11-03: right-click, and File › Convert This Folder… for the tab's
selected folder): ``ConvertFolderDialog`` picks any profile (built-in or user, by its tag; the folder's
Auto-convert profile first) and where HeLab's TXY go (HeLab's cache, its temp folder, or beside the raw files);
``ExplorerConverter.ask_convert`` then runs it as Folder details' conversions run (``start`` with the profile):
beside asks first on a share (``confirm_beside_on_share``) and needs the folder's beside setting, which it turns
on as Folder details' offer does; the folder only, never its subfolders; the helper writes
``d_txy_helab_<tag>_<N>.txt`` by its rules (a temporary name, then a rename; never over an existing TXY).
Not while Live's Auto-convert converts that folder (one conversion per folder: its menu's Convert with… instead).

**A read stopped early** (A37.1, Q48.1, Q48.2; A58.2 for Folder details): a raw file whose read stopped at a
line textscan can't read converts (the hits before it); ``note_read_stop`` logs it and sends a system
notification once per file (its name, size and mtime) whichever conversion made it, Live's auto-convert or
Folder details', and ``read_stops_text`` names it: one by name, several counted.

Every question is a non-modal ``QMessageBox`` (``open``) but the beside confirmation, which answers a
click: none waits on a helper. Each button has an ID (``<prefix>_<choice>``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import os
import time
from typing import TYPE_CHECKING, Any, Callable
import weakref

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox,
                             QPushButton, QRadioButton, QVBoxLayout, QWidget)

from helab.convert.profile import DetectorProfile, file_tag
from helab.convert.raw import ReadStop
from helab.utils import activity, cache_location, events, folder_cache
from helab.utils.accessible import identify, identify_buttons
from helab.utils.folder_cache import FolderCache
from helab.views.explorer_text import plural

if TYPE_CHECKING:
    from helab.utils.io_service import IORequest
    from helab.views.FolderExplorer import FolderExplorer

# Folders whose TXY the user agreed this session to write beside the raw files on a share (FolderCache keys).
beside_confirmed: set[str] = set()
# HeLab's folder (``cache`` or ``temp``) instead of beside the raw files, by folder (FolderCache keys), for the
# session: the user's answer after a refused beside write (Q38.1) or to Live's share question (A39.5). Live's
# auto-convert and Folder details' conversions both follow it; choosing beside again in Folder details clears it.
instead: dict[str, str] = {}
# A one-off conversion's passes at most: a folder still being written after these is Live's to follow.
MAX_PASSES = 6
# What each destination is called in the questions and the Convert row.
WHERE = {"cache": "HeLab's cache folder", "temp": "HeLab's temp folder", "beside": "beside the raw files"}
# A shot_waiting reason that settles by itself (written just now, or changed between two looks).
SETTLING = ("settling", "changed", "")
# How a conversion's line names raw files whose read stopped early (A37.1): one by name, several counted. Folder
# details colours its Auto-convert row amber on either.
READ_STOPPED = ("read stopped at line", "reads stopped early")


def note_read_stop(path: str, event: dict[str, Any], by: str) -> ReadStop:
    """A ``shot_converted`` whose raw file's read stopped early (A37.1), by Live's auto-convert or Folder details'
    conversion (``by``, for the log): logged, and a system notification once per file (its name, size and mtime)
    this session, as a damaged one's (Q48.2), since its TXY lacks the hits after that line."""
    stop = ReadStop.of(event["read_stop"])
    raw_name = str(event["raw_name"])
    logging.warning("%s: %s in %s: %s", by, raw_name, path, stop.detail())
    events.notify(events.READ_STOPPED_RAW, f"{raw_name} in {_name(path)}: {stop.detail()}. Later shots go on.",
                  title="HeLab: raw file read stopped early",
                  key=(events.READ_STOPPED_RAW, path, raw_name, int(event["raw_size"]), int(event["raw_mtime_ns"])),
                  desktop=True, path=path, shot=int(event["shot"]), line=stop.line, source="convert")
    return stop


def read_stops_text(stopped: dict[str, ReadStop]) -> tuple[str, str]:
    """Raw files whose read stopped early (by name): a conversion line's part (one by name, several counted) and
    its tooltip line ("" for none)."""
    if not stopped:
        return "", ""
    if len(stopped) == 1:
        name, stop = next(iter(stopped.items()))
        part = f"{name} {stop.summary()}"
    else:
        part = f"{len(stopped):,} {READ_STOPPED[1]}"
    return part, (f"Read stopped early ({len(stopped):,}): " + "; ".join(
        f"{name}: {stop.detail()}" for name, stop in sorted(stopped.items())[:8]) + (" …" if len(stopped) > 8 else ""))


def share_to_confirm(path: str) -> str:
    """The share holding ``path`` while writing beside there isn't confirmed this session, else ""."""
    if FolderCache.key(path) in beside_confirmed:
        return ""
    return cache_location.share_of(path)


def confirm_share(path: str) -> None:
    beside_confirmed.add(FolderCache.key(path))


def instead_of_beside(path: str) -> str | None:
    """HeLab's folder the user chose this session instead of beside the raw files of ``path``, or None."""
    return instead.get(FolderCache.key(path))


def write_instead(path: str, destination: str) -> None:
    instead[FolderCache.key(path)] = destination


def beside_unavailable(cache: FolderCache, path: str) -> str:
    """Why the folder's beside setting can't be saved now ("" when it can): it needs the disk cache and a
    confirmed data root (the setting is saved with the root). The Live menu and Folder details' offer ask
    this alike."""
    if not folder_cache.store_options():
        return "the disk cache is off for this session"
    if cache.no_root(path) is not None:
        return "no .helab-root found here or above (the choice is saved with the folder's data root)"
    if cache.pending_root(path) is not None:
        return "its .helab-root isn't confirmed yet (Review…)"
    return ""


def _name(path: str) -> str:
    return os.path.basename(path.rstrip("/\\")) or path


def question(parent: QWidget, prefix: str, title: str, text: str, informative: str,
             choices: list[tuple[str, str, QMessageBox.ButtonRole]], default: str, escape: str,
             answer: Callable[[str], None]) -> QMessageBox:
    """A non-modal question (``open``): ``answer`` gets the choice clicked, or ``escape`` when closed."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setInformativeText(informative)
    buttons: dict[str, QPushButton] = {}
    for key, label, role in choices:
        button = box.addButton(label, role)
        assert button is not None
        buttons[key] = identify(button, f"{prefix}_{key}")
    box.setDefaultButton(buttons[default])
    box.setEscapeButton(buttons[escape])

    def finished(_result: int) -> None:
        clicked = box.clickedButton()
        box.deleteLater()
        answer(next((key for key, button in buttons.items() if button is clicked), escape))
    box.finished.connect(finished)
    box.open()
    return box


def confirm_beside_on_share(parent: QWidget, path: str, share: str) -> bool:
    """The user turns on writing beside the raw files of a folder on a share: the share's warning, asked
    on that click (modal; nothing waits on a helper). Yes confirms the folder for this session too."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Write TXY beside the raw files on a share?")
    box.setText(cache_location.share_warning(_name(path), share))
    box.setInformativeText("Saved for this folder: Live's auto-convert writes beside the raw files too. HeLab writes "
                           f"nothing else there and never replaces or removes a file there.\n\n{path}")
    beside = box.addButton("Write beside on the share", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    assert beside is not None and cancel is not None
    identify(beside, "share_beside_confirm_beside")
    identify(cancel, "share_beside_confirm_cancel")
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    if box.clickedButton() is not beside:
        return False
    confirm_share(path)
    return True


def ask_live_beside_on_share(parent: QWidget, path: str, share: str, answer: Callable[[str], None]) -> QMessageBox:
    """Live's auto-convert would write beside the raw files on a share (the folder's flag is on): ``beside``
    (confirmed for the session), ``cache`` (HeLab's cache folder for this session's auto-convert) or
    ``off`` (auto-convert off, the default on closing)."""
    return question(
        parent, "live_share", "Auto-convert beside the raw files on a share?",
        cache_location.share_warning(_name(path), share),
        "This folder is set to get HeLab's TXY beside its raw files (Auto-convert › Write TXY beside the raw "
        f"files in this folder…). Asked once per folder this session.\n\n{path}",
        [("beside", "Convert beside on the share", QMessageBox.ButtonRole.AcceptRole),
         ("cache", "Convert to HeLab's cache instead (recommended)", QMessageBox.ButtonRole.ActionRole),
         ("off", "Turn auto-convert off", QMessageBox.ButtonRole.RejectRole)],
        "cache", "off", answer)


def ask_after_refusal(parent: QWidget, path: str, message: str, answer: Callable[[str], None]) -> QMessageBox:
    """Q38.1: a beside write refused (no safe rename on that file system): ``retry``, ``cache`` or ``temp``
    (HeLab's folder on this computer instead, for this session), or ``later`` (stopped, Retry stays)."""
    return question(
        parent, "beside_refused", "TXY not written beside the raw files",
        f"{_name(path)}: {message.rstrip('.')}.",
        "HeLab never risks replacing a file in a source folder. Retry (after the share is fixed or remounted), or "
        "write this folder's TXY to HeLab's cache or temp folder on this computer instead, for this session; the "
        f"folder's beside setting stays as it is.\n\n{path}",
        [("retry", "Retry", QMessageBox.ButtonRole.AcceptRole),
         ("cache", "Write to HeLab's cache folder instead", QMessageBox.ButtonRole.ActionRole),
         ("temp", "Write to HeLab's temp folder instead", QMessageBox.ButtonRole.ActionRole),
         ("later", "Not now", QMessageBox.ButtonRole.RejectRole)],
        "cache", "later", answer)


def offer_conversion(parent: QWidget, path: str, share: str, answer: Callable[[str], None],
                     beside_why: str = "") -> QMessageBox:
    """Folder details' offer for a share folder without TXY: ``cache`` (recommended), ``temp``, ``beside``
    (confirmed next; disabled with ``beside_why`` when the folder's beside setting can't be saved) or
    ``cancel``."""
    box = question(
        parent, "convert_offer", "Convert this folder's raw files",
        f"{_name(path)} has raw files but no TXY of any kind, and it is on the network share {share}.",
        "HeLab's converter should run on the computer that owns the data (the acquisition PC), where the raw "
        "files are local. Here HeLab can convert them into its cache folder on this computer (recommended) or "
        "its temp folder, writing nothing to the share; converting beside the raw files on the share asks "
        f"first." + (f" Converting beside them isn't available here: {beside_why}." if beside_why else "")
        + f"\n\n{path}",
        [("cache", "Convert to HeLab's cache (recommended)", QMessageBox.ButtonRole.AcceptRole),
         ("temp", "Convert to HeLab's temp folder", QMessageBox.ButtonRole.ActionRole),
         ("beside", "Convert beside on the share…", QMessageBox.ButtonRole.ActionRole),
         ("cancel", "Cancel", QMessageBox.ButtonRole.RejectRole)],
        "cache", "cancel", answer)
    beside = box.findChild(QPushButton, "convert_offer_beside")
    if beside is not None and beside_why:
        beside.setEnabled(False)
        beside.setToolTip(f"Not available: {beside_why}")
    return box


class ConvertFolderDialog(QDialog):
    """Convert this folder… (Q~4): the profile (every known one, by tag) and where HeLab's TXY go. Non-modal:
    ``answer`` gets the profile and the destination, or (None, "cancel")."""

    def __init__(self, parent: QWidget | None, path: str, profiles: dict[str, DetectorProfile], tag: str,
                 destination: str, beside_why: str, answer: Callable[[DetectorProfile | None, str], None]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Convert this folder")
        self.profiles = profiles
        self._answer = answer
        layout = QVBoxLayout(self)
        intro = QLabel(f"Convert {_name(path)}'s raw files (d<N>.txt) to HeLab's TXY, this folder only (not its "
                       "subfolders). Shots already converted with the profile are skipped; HeLab never replaces "
                       "a TXY file.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.profile_combo = identify(QComboBox(), "convert_folder_profile", "Profile",
                                      "The detector profile the raw files are converted with (its tag names the "
                                      "TXY files)")
        for item_tag, profile in profiles.items():
            self.profile_combo.addItem(f"{profile.name} ({item_tag})", item_tag)
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(tag)))
        form.addRow("Profile", self.profile_combo)
        layout.addLayout(form)
        self.group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for name, text in (("cache", "HeLab's cache folder"), ("temp", "HeLab's temp folder"),
                           ("beside", "Beside the raw files, in this folder")):
            radio = identify(QRadioButton(text), f"convert_folder_{name}", f"Convert to {text}")
            self.group.addButton(radio)
            self.radios[name] = radio
            layout.addWidget(radio)
        beside = self.radios["beside"]
        beside.setToolTip(f"Not available: {beside_why}" if beside_why else
                          "d_txy_helab_<tag>_<N>.txt beside the raw files; turns the folder's beside setting on "
                          "(on a network share HeLab asks first)")
        beside.setEnabled(not beside_why)
        self.radios[destination if destination in self.radios and (destination != "beside" or not beside_why)
                    else "cache"].setChecked(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        identify_buttons(self.buttons, "convert_folder")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.finished.connect(self._finished)

    def chosen(self) -> tuple[DetectorProfile | None, str]:
        tag = str(self.profile_combo.currentData() or "")
        where = next((name for name, radio in self.radios.items() if radio.isChecked()), "cache")
        return self.profiles.get(tag), where

    def _finished(self, result: int) -> None:
        self._answer(*(self.chosen() if result == int(QDialog.DialogCode.Accepted) else (None, "cancel")))
        self.deleteLater()


@dataclass(eq=False)
class FolderConversion:
    """A folder's conversion from Folder details (not Live's): its passes and what they found."""
    path: str
    destination: str  # cache, temp or beside
    started_at: float  # Wall time.
    passes: int = 0
    request: bool = False
    todo: int = 0
    done: int = 0
    converted: int = 0
    waiting: int = 0  # Settling at the last pass.
    stuck: int = 0  # Waiting for more than settling (no final newline, …) or unconvertible.
    output: str = ""  # Where the last plan wrote, and why not where asked.
    fallback: str = ""
    refused: str = ""  # A beside write refused (Q38.1), until answered.
    error: str = ""
    finished: bool = False
    flag: bool = False  # Beside: waiting for the store to say the folder's flag is on.
    profile: DetectorProfile | None = None  # Convert this folder… 's (Q~4); None: Settings' conversion profile.
    # Raw files converted whose read stopped early (A37.1, A58.2), by name.
    stopped: dict[str, ReadStop] = field(default_factory=dict)


class ExplorerConverter:
    """One tab's conversions from Folder details, and its open converter question (``box``)."""

    def __init__(self, explorer: FolderExplorer) -> None:
        self._explorer = weakref.ref(explorer)  # (The tab owns this; no cycle.)
        self.owner = f"{explorer.model.owner}:convert"
        self.conversions: dict[str, FolderConversion] = {}
        self.box: QMessageBox | None = None
        self._timer = QTimer(explorer)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._next_passes)
        cache = explorer.model.cache
        self._cache = cache
        cache.folderPrefsChanged.connect(self._flag_changed)
        cache.cacheAdminResult.connect(self._admin_result)

    @property
    def explorer(self) -> FolderExplorer:
        explorer = self._explorer()
        assert explorer is not None
        return explorer

    def offered(self, path: str) -> str:
        """The share of a folder Folder details offers to convert (raw files, no TXY of any kind, on a share,
        not converted by Live), else "". Memory only (the listing's counts) and the cached mount table."""
        explorer = self.explorer
        node = explorer.model.nodes.get(path)
        if node is None or not node.raw_count or node.txy_count or explorer.live_control.auto_converting(path):
            return ""
        files = (explorer.model.cache.scan_summaries.get(path) or {}).get("files") or {}
        if (files.get("helab_txy") or {}).get("count"):
            return ""
        dataset = explorer.displayed_dataset
        if dataset is not None and dataset.path == path and dataset.data:
            return ""
        return cache_location.share_of(path)

    def row(self, path: str) -> tuple[str, str] | None:
        """Folder details' Convert row: this tab's conversion of ``path``, or the offer; None for neither."""
        conversion = self.conversions.get(path)
        if conversion is not None:
            where = WHERE.get(conversion.output or conversion.destination, conversion.destination)
            stop_part, stop_line = read_stops_text(conversion.stopped)
            if conversion.error:
                text = f"Conversion stopped: {conversion.error}"
            elif conversion.flag:
                text = "Saving the folder's beside setting, then converting beside the raw files…"
            elif not conversion.finished:
                text = (f"Converting to {where}… {conversion.done:,} of {conversion.todo:,}" if conversion.todo
                        else f"Converting to {where}…") + (f" · {stop_part}" if stop_part else "")
            else:
                parts = [f"{conversion.converted:,} converted to {where}"]
                if conversion.waiting:
                    parts.append(f"{conversion.waiting:,} still being written")
                if conversion.stuck:
                    parts.append(f"{conversion.stuck:,} not convertible")
                if stop_part:
                    parts.append(stop_part)
                text = " · ".join(parts)
            with_profile = f" with {file_tag(conversion.profile)}" if conversion.profile is not None else ""
            lines = [f"Converting {path}'s raw files{with_profile}, since "
                     f"{time.strftime('%H:%M:%S', time.localtime(conversion.started_at))}, to {where}"
                     + (f" ({conversion.fallback})" if conversion.fallback else ""),
                     f"Passes: {conversion.passes:,} (the first only records each file; a file converts once "
                     "unchanged between two passes, a check interval apart)"]
            if stop_line:
                lines.append(stop_line)
            if conversion.finished and conversion.waiting:
                lines.append(f"{plural(conversion.waiting, 'raw file')} still being written after {MAX_PASSES} "
                             "passes: Live's auto-convert converts them as they settle.")
            if conversion.error:
                lines.append("Click to choose what to do." if conversion.refused else "Click to try again.")
            return text, "\n".join(lines)
        share = self.offered(path)
        if not share:
            return None
        return ("No TXY · on a share · Convert…",
                f"{cache_location.share_warning(_name(path), share)}\n\nClick to convert: to HeLab's cache "
                "(recommended), its temp folder, or beside the raw files on the share (asks first).")

    def clicked(self, path: str) -> None:
        """The Convert row was clicked: the offer, or the stopped conversion's question."""
        if self.box is not None:
            self.box.raise_()
            return
        conversion = self.conversions.get(path)
        if conversion is not None and conversion.error:
            if conversion.refused:
                self.box = ask_after_refusal(self.explorer, path, conversion.refused,
                                             lambda choice: self._refusal_answered(path, choice))
            else:
                self.start(path, conversion.destination, conversion.profile)
            return
        if conversion is not None and not conversion.finished:
            return
        share = self.offered(path) or cache_location.share_of(path)
        if share:
            self.box = offer_conversion(self.explorer, path, share, lambda choice: self._offer_answered(path, choice),
                                        beside_unavailable(self.explorer.model.cache, path))

    def _offer_answered(self, path: str, choice: str) -> None:
        self.box = None
        if choice == "beside":
            if why := beside_unavailable(self.explorer.model.cache, path):
                logging.info("Converting %s beside the raw files isn't available: %s", path, why)
                return
            share = cache_location.share_of(path)
            if not confirm_beside_on_share(self.explorer, path, share):
                return
        if choice in WHERE:
            self.start(path, choice)

    def _refusal_answered(self, path: str, choice: str) -> None:
        self.box = None
        conversion = self.conversions.get(path)
        if conversion is None:
            return
        if choice in ("cache", "temp"):
            write_instead(path, choice)  # (The folder's for the session: Live's auto-convert follows it too.)
        if choice in ("retry", "cache", "temp"):
            self.start(path, conversion.destination if choice == "retry" else choice, conversion.profile)

    def convert_unavailable(self, path: str) -> str:
        """Why Convert this folder… can't run now ("" when it can): Live converts it, or a conversion of it from
        here is running."""
        if self.box is not None:
            return "a converter question is open: answer it first"  # (Never a silent refusal, TP-9.)
        if self.explorer.live_control.auto_converting(path):
            return "Live's Auto-convert converts this folder (its menu: Convert with…)"
        conversion = self.conversions.get(path)
        if conversion is not None and not conversion.finished and not conversion.error:
            return "this folder is being converted (Folder details)"
        if other := self.explorer.model.cache.converting_with(path):
            return f"a conversion of this folder with {other} is running"  # (Another tab's, or Live's: TP-5.)
        return ""

    def ask_convert(self, path: str) -> ConvertFolderDialog | None:
        """Right-click › Convert this folder… (Q~4): the dialog, then the conversion as chosen."""
        if why := self.convert_unavailable(path):
            logging.info("Convert this folder… not now for %s: %s", path, why)  # (The items say why, disabled.)
            return None
        from helab.utils.constants import read_convert_output
        from helab.utils.settings_store import app_settings
        from helab.views.plots.txy_source import known_profiles
        cache = self.explorer.model.cache
        profiles: dict[str, DetectorProfile] = {}
        for profile in known_profiles().values():
            profiles.setdefault(file_tag(profile), profile)
        default = cache.auto_convert_profile(path)
        profiles.setdefault(file_tag(default), default)
        destination = "beside" if cache.write_beside(path) else read_convert_output(app_settings())
        dialog = ConvertFolderDialog(self.explorer, path, profiles, file_tag(default), destination,
                                     beside_unavailable(cache, path),
                                     lambda profile, where: self._convert_answered(path, profile, where))
        dialog.open()
        return dialog

    def _convert_answered(self, path: str, profile: DetectorProfile | None, where: str) -> None:
        if profile is None or where not in WHERE:
            return
        if where == "beside":
            if why := beside_unavailable(self.explorer.model.cache, path):
                # (It changed while the dialog was open: said, never a silent refusal, TP-9.)
                logging.info("Converting %s beside the raw files isn't available: %s", path, why)
                self.box = question(self.explorer, "convert_folder_beside", "Convert this folder",
                                    f"{_name(path)} can't be converted beside its raw files now.",
                                    f"Not available: {why}. Nothing was converted; Convert this folder… again to "
                                    f"choose HeLab's cache or temp folder.\n\n{path}",
                                    [("ok", "OK", QMessageBox.ButtonRole.AcceptRole)], "ok", "ok",
                                    self._beside_said)
                return
            share = share_to_confirm(path)
            if share and not confirm_beside_on_share(self.explorer, path, share):
                return
        self.start(path, where, profile)

    def _beside_said(self, _choice: str) -> None:
        self.box = None

    def start(self, path: str, destination: str, profile: DetectorProfile | None = None) -> bool:
        """Convert ``path``'s raw files to ``destination`` (``cache``, ``temp`` or ``beside``) with ``profile``
        (None: Settings' conversion profile): passes until nothing settles, then the folder is listed and loaded
        again. Whether its first pass was queued."""
        conversion = self.conversions[path] = FolderConversion(path, destination, time.time(), profile=profile)
        logging.info("Converting %s to %s (Folder details)", path, WHERE.get(destination, destination))
        cache = self.explorer.model.cache
        if destination == "beside":
            instead.pop(FolderCache.key(path), None)  # (Beside, chosen again: no longer instead.)
            if not cache.write_beside(path):
                # The folder's flag first: the helper writes beside only while the store's flag is on.
                if not cache.set_write_beside(path, True):
                    conversion.error = "the folder's beside setting couldn't be saved (HeLab's work queue is full)"
                    self.explorer.loadStateChanged.emit()
                    return False
                conversion.flag = True
                self.explorer.loadStateChanged.emit()
                return True
        return self._pass(conversion)

    def _flag_changed(self, path: str) -> None:
        """A folder's flags as the store said: a beside conversion waiting for its flag starts."""
        for conversion in self.conversions.values():
            if (conversion.flag and FolderCache.key(conversion.path) == path
                    and self.explorer.model.cache.write_beside(conversion.path)):
                conversion.flag = False
                self._pass(conversion)

    def _admin_result(self, action: str, event: object) -> None:
        """The folder's beside flag couldn't be saved: the conversions waiting for it stop, saying so."""
        if action != "convert_prefs" or not isinstance(event, dict) or event.get("kind") not in ("error", "cancelled"):
            return
        for conversion in self.conversions.values():
            if conversion.flag:
                conversion.flag = False
                conversion.error = ("the folder's beside setting couldn't be saved: "
                                    + str(event.get("message") or "cancelled"))
                logging.warning("Converting %s stopped: %s", conversion.path, conversion.error)
                self._report(conversion, "failed")
        self.explorer.loadStateChanged.emit()

    def _pass(self, conversion: FolderConversion) -> bool:
        beside = conversion.destination == "beside"
        cache = self.explorer.model.cache
        if not cache.convert(self.owner, conversion.path, destination=None if beside else conversion.destination,
                             beside=beside, profile_used=conversion.profile):
            other = cache.converting_with(conversion.path)
            conversion.error = (f"a conversion of this folder with {other} is running; try again when it ends"
                                if other else "the conversion couldn't be queued")
            self.explorer.loadStateChanged.emit()
            return False
        conversion.request, conversion.todo, conversion.done = True, 0, 0
        self.explorer.loadStateChanged.emit()
        return True

    def _next_passes(self) -> None:
        for conversion in self.conversions.values():
            if conversion.request or conversion.finished or conversion.error or conversion.passes == 0:
                continue
            self._pass(conversion)

    def event(self, request: IORequest, event: dict[str, Any]) -> None:
        """A conversion's events (owner ``self.owner``)."""
        conversion = self.conversions.get(request.path)
        if conversion is None or not conversion.request or request.operation != "convert":
            return
        kind = event["kind"]
        if kind == "convert_plan":
            conversion.todo, conversion.done = int(event["todo"]), 0
            conversion.output, conversion.fallback = str(event["output"]), str(event.get("fallback") or "")
        elif kind == "convert_progress":
            conversion.done, conversion.todo = int(event["done"]), int(event["todo"])
        elif kind == "shot_converted":
            conversion.converted += 1
            if event.get("read_stop"):
                conversion.stopped[str(event["raw_name"])] = note_read_stop(conversion.path, event, "Converting")
            else:
                conversion.stopped.pop(str(event["raw_name"]), None)  # (Converted again, read to its end.)
        elif kind == "beside_refused":
            conversion.refused = str(event["message"])
        elif kind == "convert_summary":
            waiting = [entry for entry in event["waiting"] if len(entry) < 5 or entry[3] in SETTLING]
            conversion.waiting = len(waiting)
            conversion.stuck = len(event["waiting"]) - len(waiting) + len(event["unconvertible"])
        elif kind in ("done", "error", "cancelled", "offline"):
            conversion.request = False
            conversion.passes += kind == "done"
            if kind == "done":
                self._passed(conversion)
            else:
                conversion.error = ("not while working offline" if kind == "offline" else "cancelled"
                                    if kind == "cancelled" else
                                    str(event.get("message") or "the conversion failed").removesuffix(" — Retry"))
                logging.warning("Converting %s stopped: %s", conversion.path, conversion.error)
                self._report(conversion, "cancelled" if kind == "cancelled" else "failed")
                if conversion.refused and self.box is None:
                    self.box = ask_after_refusal(self.explorer, conversion.path, conversion.refused,
                                                 lambda choice: self._refusal_answered(conversion.path, choice))
        else:
            return
        self.explorer._update_activity()
        self.explorer.loadStateChanged.emit()

    def _passed(self, conversion: FolderConversion) -> None:
        if conversion.passes == 1 or conversion.waiting and conversion.passes < MAX_PASSES:
            # (The first pass records; files written just now wait a check interval.)
            self._timer.start(max(0, math.ceil(self.explorer.model.cache.live_interval * 1000)))
            return
        conversion.finished = True
        logging.info("Converted %s: %d to %s", conversion.path, conversion.converted,
                     WHERE.get(conversion.output, conversion.output))
        self._report(conversion, "ok")
        if conversion.converted:
            explorer = self.explorer
            explorer.refresh_folder(conversion.path)
            if conversion.path == explorer.selected_path_globally:
                explorer.queue_load(conversion.path)

    def _report(self, conversion: FolderConversion, outcome: activity.Outcome) -> None:
        """A conversion's end in the session's history (the Activity window, Q62.4)."""
        where = WHERE.get(conversion.output or conversion.destination, conversion.destination)
        activity.record(activity.Finished(
            f"conversion:{self.owner}:{conversion.path}:{conversion.started_at}", "convert", "Convert raw files to TXY",
            conversion.path, time.time(), outcome, conversion.error, conversion.started_at, (self.owner,),
            route=activity.Route("conversion", self.owner, "convert", conversion.path),
            details=(f"{conversion.converted:,} converted to {where} in {conversion.passes:,} passes",)))

    def close(self) -> None:
        self._timer.stop()
        try:
            self._cache.folderPrefsChanged.disconnect(self._flag_changed)
            self._cache.cacheAdminResult.disconnect(self._admin_result)
        except TypeError:
            pass  # (Closed before.)
        for conversion in self.conversions.values():
            if conversion.request:
                self.explorer.model.cache.cancel(self.owner, "convert", conversion.path)
        if self.box is not None:
            self.box.close()
