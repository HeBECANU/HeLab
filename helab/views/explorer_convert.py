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
the folder's flag on). ``ExplorerConverter`` then runs the folder's conversions (``FolderCache.convert``
with the destination chosen, owner ``<tab>:convert``, the background lane): the first only records, as
every conversion's first does, so passes follow a check interval apart while files wait to settle (at
most ``MAX_PASSES``); then the folder is listed and loaded again, so HeLab's new TXY show.

**A beside write that can't be made safely** (Q38.1, Tony 2026-11-02): the helper's ``beside_refused``
(no hard links and no rename that refuses an existing name), then the run fails as before; HeLab asks
(``ask_after_refusal``): Retry, write to HeLab's cache or temp folder instead (that conversion, Live's
auto-convert or this one, for the rest of the session; the folder's flag stays), or not now. Never a
silent refusal nor a silent fallback.

Every question is a non-modal ``QMessageBox`` (``open``) but the beside confirmation, which answers a
click: none waits on a helper. Each button has an ID (``<prefix>_<choice>``).
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
import time
from typing import TYPE_CHECKING, Any, Callable
import weakref

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QPushButton, QWidget

from helab.utils import cache_location
from helab.utils.accessible import identify
from helab.utils.folder_cache import FolderCache
from helab.views.explorer_text import plural

if TYPE_CHECKING:
    from helab.utils.io_service import IORequest
    from helab.views.FolderExplorer import FolderExplorer

# Folders whose TXY the user agreed this session to write beside the raw files on a share (FolderCache keys).
beside_confirmed: set[str] = set()
# A one-off conversion's passes at most: a folder still being written after these is Live's to follow.
MAX_PASSES = 6
# What each destination is called in the questions and the Convert row.
WHERE = {"cache": "HeLab's cache folder", "temp": "HeLab's temp folder", "beside": "beside the raw files"}
# A shot_waiting reason that settles by itself (written just now, or changed between two looks).
SETTLING = ("settling", "changed", "")


def share_to_confirm(path: str) -> str:
    """The share holding ``path`` while writing beside there isn't confirmed this session, else ""."""
    if FolderCache.key(path) in beside_confirmed:
        return ""
    return cache_location.share_of(path)


def confirm_share(path: str) -> None:
    beside_confirmed.add(FolderCache.key(path))


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


def offer_conversion(parent: QWidget, path: str, share: str, answer: Callable[[str], None]) -> QMessageBox:
    """Folder details' offer for a share folder without TXY: ``cache`` (recommended), ``temp``, ``beside``
    (confirmed next) or ``cancel``."""
    return question(
        parent, "convert_offer", "Convert this folder's raw files",
        f"{_name(path)} has raw files but no TXY of any kind, and it is on the network share {share}.",
        "HeLab's converter should run on the computer that owns the data (the acquisition PC), where the raw "
        "files are local. Here HeLab can convert them into its cache folder on this computer (recommended) or "
        "its temp folder, writing nothing to the share; converting beside the raw files on the share asks "
        f"first.\n\n{path}",
        [("cache", "Convert to HeLab's cache (recommended)", QMessageBox.ButtonRole.AcceptRole),
         ("temp", "Convert to HeLab's temp folder", QMessageBox.ButtonRole.ActionRole),
         ("beside", "Convert beside on the share…", QMessageBox.ButtonRole.ActionRole),
         ("cancel", "Cancel", QMessageBox.ButtonRole.RejectRole)],
        "cache", "cancel", answer)


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
            if conversion.error:
                text = f"Conversion stopped: {conversion.error}"
            elif not conversion.finished:
                text = (f"Converting to {where}… {conversion.done:,} of {conversion.todo:,}" if conversion.todo
                        else f"Converting to {where}…")
            else:
                parts = [f"{conversion.converted:,} converted to {where}"]
                if conversion.waiting:
                    parts.append(f"{conversion.waiting:,} still being written")
                if conversion.stuck:
                    parts.append(f"{conversion.stuck:,} not convertible")
                text = " · ".join(parts)
            lines = [f"Converting {path}'s raw files from Folder details, since "
                     f"{time.strftime('%H:%M:%S', time.localtime(conversion.started_at))}, to {where}"
                     + (f" ({conversion.fallback})" if conversion.fallback else ""),
                     f"Passes: {conversion.passes:,} (the first only records each file; a file converts once "
                     "unchanged between two passes, a check interval apart)"]
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
                self.start(path, conversion.destination)
            return
        if conversion is not None and not conversion.finished:
            return
        share = self.offered(path) or cache_location.share_of(path)
        if share:
            self.box = offer_conversion(self.explorer, path, share, lambda choice: self._offer_answered(path, choice))

    def _offer_answered(self, path: str, choice: str) -> None:
        self.box = None
        if choice == "beside":
            share = cache_location.share_of(path)
            if not confirm_beside_on_share(self.explorer, path, share):
                return
            self.explorer.model.cache.set_write_beside(path, True)
        if choice in WHERE:
            self.start(path, choice)

    def _refusal_answered(self, path: str, choice: str) -> None:
        self.box = None
        conversion = self.conversions.get(path)
        if conversion is None:
            return
        if choice in ("retry", "cache", "temp"):
            self.start(path, conversion.destination if choice == "retry" else choice)

    def start(self, path: str, destination: str) -> bool:
        """Convert ``path``'s raw files to ``destination`` (``cache``, ``temp`` or ``beside``): passes until
        nothing settles, then the folder is listed and loaded again. Whether its first pass was queued."""
        conversion = self.conversions[path] = FolderConversion(path, destination, time.time())
        logging.info("Converting %s to %s (Folder details)", path, WHERE.get(destination, destination))
        return self._pass(conversion)

    def _pass(self, conversion: FolderConversion) -> bool:
        beside = conversion.destination == "beside"
        cache = self.explorer.model.cache
        if not cache.convert(self.owner, conversion.path, destination=None if beside else conversion.destination,
                             beside=None if beside else False):
            conversion.error = "the conversion couldn't be queued"
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
        if conversion.converted:
            explorer = self.explorer
            explorer.refresh_folder(conversion.path)
            if conversion.path == explorer.selected_path_globally:
                explorer.queue_load(conversion.path)

    def close(self) -> None:
        self._timer.stop()
        for conversion in self.conversions.values():
            if conversion.request:
                self.explorer.model.cache.cancel(self.owner, "convert", conversion.path)
        if self.box is not None:
            self.box.close()
