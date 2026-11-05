"""The Folder info window (Q64.1–Q64.10): everything HeLab holds and knows about one folder, read only.

One window, retargeted on each open (``show_folder``), its folder's path in the title. Its content is
``helab.utils.folder_info``'s model, from one helper read (``FolderCache.folder_info``, the local lane: the store and
HeLab's converted-TXY index, never the folder) and memory (``FolderInfoSources.memory``). Each section's buttons call
the folder's existing actions through its tab, which ask as they do elsewhere; the window itself changes nothing. It
reads on open, on Refresh and after an action started here; while Live watches the folder, its This session lines
follow each check that brings shots and it reads again after each Live save, with at most one read in flight
(``folder_info.Reads``). Long sections open their full list in a detail pane to the right, widening the window; the
sections scroll, so it is never taller than its screen. Rendering reads memory only.
"""
from __future__ import annotations

import os
import time
import weakref
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QGuiApplication, QHideEvent, QShowEvent
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QSplitter, QToolButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from helab.utils import folder_cache as folder_cache_module
from helab.utils import folder_info, txy_sources
from helab.utils.accessible import identify
from helab.utils.colours import AMBER
from helab.utils.folder_cache import FolderCache
from helab.utils.folder_info import Action, Info, Memory, Reads, Row, Section, Session
from helab.utils.settings_defaults import FOLDER_INFO_SIZE_SETTING, read_setting
from helab.utils.settings_store import app_settings
from helab.views.ActivityWindow import parse_size, session_of, watching
from helab.views.ElidedLabel import ElidedLabel
from helab.views.gaps import CELL_PADDING_STYLE, COLUMN_GAP, LABEL_GAP

if TYPE_CHECKING:
    from helab.views.FolderExplorer import FolderExplorer

DEFAULT_SIZE = (620, 560)
MIN_SIZE = (420, 240)
# A read after an action started here waits for the folder's next change this long (a dialog left open).
ARM_SECONDS = 600.0
# Coalescing: a read after a change, and This session's lines during Live.
READ_DELAY_MS = 300
MEMORY_DELAY_MS = 500
# Actions whose buttons sit on the data root's header line.
ROOT_ACTIONS = ("place_root", "review_root", "settings_roots")


class FolderInfoSources:
    """What the window reads and calls in the app: the folder cache, the tabs (their text and explorer), the current
    tab, the plots open on a folder, the loaded scripts' names by analysis ID, and the main window's Settings and
    Review…. ``memory`` gathers the model's ``Memory`` from them, memory only."""

    def __init__(self, cache: FolderCache, tabs: Callable[[], list[tuple[str, FolderExplorer]]],
                 current: Callable[[], Optional[FolderExplorer]],
                 plots_on: Callable[[str], tuple[str, ...]] = lambda path: (),
                 script_names: Callable[[], Mapping[str, str]] = dict,
                 open_settings: Callable[[str], None] = lambda tab: None,
                 review_root: Callable[[str], None] = lambda location: None) -> None:
        self.cache = cache
        self.tabs = tabs
        self.current = current
        self.plots_on = plots_on
        self.script_names = script_names
        self.open_settings = open_settings
        self.review_root = review_root

    def memory(self, path: str, explorer: Optional[FolderExplorer]) -> Memory:
        from helab.views.CacheTab import POLICY_LABELS
        from helab.utils.folder_cache import OFFLINE_TOOLTIP
        from helab.utils.store_v4 import DIRNAME as STORE_V4_DIRNAME
        cache = self.cache
        options = folder_cache_module.store_options()
        pending = cache.pending_root(path)
        choices = cache.folder_choices.get(path) or {}
        policy = str(choices.get("policy") or options.get("policy") or "")
        history = cache.scan_history(path)
        refresh = OFFLINE_TOOLTIP if cache.offline else ""
        if explorer is not None and not refresh and explorer.model.refresh_pending(path):
            refresh = "This folder is being listed again now"
        return Memory(
            path=path, cache_on=bool(options),
            store_v4=os.path.basename(str(options.get("directory") or "")) == STORE_V4_DIRNAME,
            offline=cache.offline, root=cache.root_of(path), no_root=cache.no_root(path),
            pending_root=str(pending["path"]) if pending is not None else "",
            flags=cache.folder_prefs(path), write_beside=cache.write_beside(path),
            txy_list=txy_sources.summary(cache.folder_list(path), cache.convert_profile_tag()),
            txy_own=bool(choices.get("source")),
            policy=dict(POLICY_LABELS).get(policy, policy).removesuffix(" (default)"),
            policy_own=bool(choices.get("policy")), constants=cache.inherited_constants(path),
            constants_note=cache.constants_session_only(path),
            history=dict(history) if int(history.get("revision") or 0) else None, subtree=cache.subtree(path),
            session=self.session(path), refresh_unavailable=refresh,
            convert_unavailable=(explorer.converter.convert_unavailable(path) if explorer is not None
                                 else "open the folder in a tab first"),
            place_root=(explorer.place_root_state(path) if explorer is not None
                        else (False, "Open the folder in a tab first")),
            script_names=self.script_names())

    def session(self, path: str) -> Session:
        """This session's state of ``path``: its data in RAM, Live in any tab, the plots open on it."""
        cache = self.cache
        dataset = cache.latest_dataset(path)
        live, converting = "", path in cache.auto_convert
        for text, explorer in self.tabs():
            if not explorer.closed and watching(explorer, path):
                live = text or "a tab"
                found = session_of(explorer, path)
                converting = converting or (found is not None and found.convert is not None)
        waiting = cache.cache_status(path).error if path in cache.pending_saves else ""
        if dataset is None:
            return Session(live=live, auto_convert=converting, plots=self.plots_on(path), waiting=waiting)
        shots = sorted(dataset.data)
        newest = shots[-1] if shots else None
        written = None
        for entry in dataset.metadata.get("raw_times") or dataset.metadata.get("fingerprint") or ():
            if newest is not None and int(entry[0]) == newest:
                written = float(entry[-1]) / 1e9
        return Session(loaded_shots=len(shots), ram_bytes=sum(int(array.nbytes) for array in dataset.data.values()),
                       source=txy_sources.summary(cache.folder_list(path), cache.convert_profile_tag()),
                       newest_shot=newest, newest_at=written, live=live, auto_convert=converting,
                       plots=self.plots_on(path), waiting=waiting)


class FolderInfoWindow(QWidget):
    """File › Folder info…, right-click › Folder info… and Folder details' link: one window, the folder it was last
    opened for."""

    def __init__(self, sources: FolderInfoSources, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.sources = sources
        self.cache = sources.cache
        self.path = ""
        self.reads = Reads()
        self.answer: Optional[Mapping[str, Any]] = None  # The last read that worked, of ``path``.
        self.error = ""
        self.info: Optional[Info] = None
        self._explorer: Optional[weakref.ref[FolderExplorer]] = None
        self._answered: set[str] = set()
        self._armed_until = 0.0
        self._detail = ""  # The section shown in the detail pane ("" closed).
        self._pane_width = 0
        self._connected = False
        self._fitted = False
        identify(self, "folder_info_window", "Folder info")
        self.setWindowTitle("Folder info")
        self.resize(*parse_size(read_setting(app_settings(), FOLDER_INFO_SIZE_SETTING), DEFAULT_SIZE))
        self.resize(max(MIN_SIZE[0], self.width()), max(MIN_SIZE[1], self.height()))
        self.outer = outer = QVBoxLayout(self)
        outer.setContentsMargins(LABEL_GAP, 0, LABEL_GAP, 0)
        outer.setSpacing(0)
        self.header = QWidget()
        outer.addWidget(self.header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.sections_area = QScrollArea()
        self.sections_area.setWidgetResizable(True)
        self.sections_area.setFrameShape(QFrame.Shape.NoFrame)
        self.sections_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        identify(self.sections_area, "folder_info_sections", "Folder info sections")
        self.splitter.addWidget(self.sections_area)
        self.pane = QWidget()
        pane = QVBoxLayout(self.pane)
        pane.setContentsMargins(LABEL_GAP, 0, 0, 0)
        pane.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(COLUMN_GAP)
        self.pane_title = QLabel()
        self.pane_title.setFont(self._bold())
        top.addWidget(self.pane_title, 1)
        self.pane_close = identify(QToolButton(), "folder_info_detail_close", "Close the list")
        self.pane_close.setText("×")
        self.pane_close.setAutoRaise(True)
        self.pane_close.setToolTip("Close this list (the window narrows again)")
        self.pane_close.clicked.connect(self.close_detail)
        top.addWidget(self.pane_close)
        pane.addLayout(top)
        self.tree = identify(QTreeWidget(), "folder_info_detail", "Folder info list")
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet(CELL_PADDING_STYLE)
        pane.addWidget(self.tree)
        self.splitter.addWidget(self.pane)
        self.pane.hide()
        outer.addWidget(self.splitter, 1)
        self._read_timer = QTimer(self)
        self._read_timer.setSingleShot(True)
        self._read_timer.setInterval(READ_DELAY_MS)
        self._read_timer.timeout.connect(self.refresh)
        self._memory_timer = QTimer(self)
        self._memory_timer.setSingleShot(True)
        self._memory_timer.setInterval(MEMORY_DELAY_MS)
        self._memory_timer.timeout.connect(self.rebuild)
        self.cache.folderInfoRead.connect(self._on_read)
        self.cache.cacheAdminDone.connect(self._on_admin_done)

    @staticmethod
    def _bold() -> QFont:
        font = QFont()
        font.setBold(True)
        return font

    # Opening and reading

    def show_folder(self, path: str, explorer: Optional[FolderExplorer] = None) -> None:
        """Show ``path`` (from its tab ``explorer``, through which its actions go), read it, and raise the window."""
        if path != self.path:
            self.path, self.answer, self.error = path, None, ""
            self._armed_until = 0.0
            self.close_detail()
        self._explorer = weakref.ref(explorer) if explorer is not None else None
        self.setWindowTitle(f"Folder info — {path}")
        self.setWindowFilePath(path)
        self.request_read()
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def explorer(self) -> Optional[FolderExplorer]:
        """The tab it was opened from, else the current tab (its actions go through it)."""
        explorer = self._explorer() if self._explorer is not None else None
        if explorer is None or explorer.closed:
            explorer = self.sources.current()
        return explorer if explorer is not None and not explorer.closed else None

    def request_read(self) -> None:
        """Read the folder: now, or after the read in flight (one queued at most)."""
        if not self.path:
            return
        if self.reads.ask(self.path):
            self._submit()
        self.rebuild()

    @pyqtSlot()
    def refresh(self) -> None:
        self.request_read()

    def _submit(self) -> None:
        owner = self.cache.folder_info(self.path)
        self.reads.started(owner)
        if not owner:
            self.error = ("the disk cache is off this session" if not folder_cache_module.store_options()
                          else "the read couldn't be queued (the I/O queue is full or HeLab is quitting)")

    @pyqtSlot(str, object)
    def _on_read(self, owner: str, event: object) -> None:
        if isinstance(event, dict) and self.reads.answered(owner, str(event.get("path") or "")):
            self.answer, self.error = event, ""
            self._answered.add(owner)

    @pyqtSlot(str, str, str)
    def _on_admin_done(self, owner: str, action: str, message: str) -> None:
        if action != "folder_info":
            self._changed()
            return
        if owner != self.reads.owner:
            return
        answered = owner in self._answered
        self._answered.discard(owner)
        if not answered and self.reads.asked_for == self.path:
            self.error = message or "the read ended without an answer"
        if self.reads.ended(owner):
            self._submit()
        self.rebuild()

    # What makes it read by itself

    def arm(self) -> None:
        """An action started here: read after the folder's next change (``ARM_SECONDS`` at most)."""
        self._armed_until = time.monotonic() + ARM_SECONDS

    def live(self) -> bool:
        """Whether Live watches the folder in a tab."""
        return bool(self.path) and any(not explorer.closed and watching(explorer, self.path)
                                       for _, explorer in self.sources.tabs())

    def _changed(self, path: str | None = None) -> None:
        """A change of the folder (or of the cache, ``path`` None) after an action started here: read, coalesced."""
        if (self._armed_until and time.monotonic() < self._armed_until and self.isVisible()
                and (path is None or path == self.path)):
            self._armed_until = 0.0
            self._read_timer.start()

    @pyqtSlot(str)
    def _folder_changed(self, path: str) -> None:
        self._changed(path)

    @pyqtSlot(object, object)
    def _removed(self, paths: object, kinds: object) -> None:
        self._changed()

    @pyqtSlot(str)
    def _dataset_changed(self, path: str) -> None:
        """A Live check brought shots (or a load ended): This session's lines, while Live watches the folder."""
        if path == self.path and self.live():
            self._memory_timer.start()

    @pyqtSlot()
    def live_changed(self) -> None:
        """A tab's Live started or stopped (``FolderExplorer.liveChanged``): the header and This session say so. Its
        last save, on stop, reads again through ``saveEnded``."""
        if self.isVisible() and self.path:
            self._memory_timer.start()

    @pyqtSlot(str, str)
    def _save_ended(self, path: str, outcome: str) -> None:
        """A save of the folder ended: while Live watches it, read (Live saves every N shots and on stop)."""
        if path != self.path:
            return
        if outcome in ("saved", "superseded") and self.live():
            self.request_read()
        else:
            self._changed(path)

    def _signals(self) -> list[tuple[Any, Any]]:
        cache = self.cache
        return [(cache.folderPrefsChanged, self._folder_changed), (cache.constantsChanged, self._folder_changed),
                (cache.dataRootsChanged, self._folder_changed), (cache.scanHistoryChanged, self._folder_changed),
                (cache.diskCacheChanged, self._folder_changed), (cache.cacheRemoved, self._removed),
                (cache.datasetChanged, self._dataset_changed), (cache.saveEnded, self._save_ended)]

    def _connect(self) -> None:
        if not self._connected:
            for signal, slot in self._signals():
                signal.connect(slot)
            self._connected = True

    def _disconnect(self) -> None:
        if self._connected:
            for signal, slot in self._signals():
                signal.disconnect(slot)
            self._connected = False

    # Actions: the folder's existing ones, through its tab

    def act(self, ident: str, checked: bool = False) -> None:
        """Run the action ``ident`` names (``folder_info.Action.id``) for the window's folder."""
        path, explorer = self.path, self.explorer()
        if ident == "refresh":
            self.request_read()
            return
        if ident == "copy":
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None and self.info is not None:
                clipboard.setText(folder_info.as_text(self.info))
            return
        self.arm()
        if ident == "settings_cache":
            self.sources.open_settings("Cache")
        elif ident == "settings_roots":
            self.sources.open_settings("Data roots")
        elif ident == "review_root" and (pending := self.cache.pending_root(path)) is not None:
            self.sources.review_root(str(pending["location"]))
        elif explorer is None:
            self._armed_until = 0.0
        elif ident == "place_root":
            explorer.place_root(path)
        elif ident == "clear_data":
            explorer.clear_data_cache(path)
        elif ident in ("flag_no_cache", "flag_no_auto_load"):
            explorer.set_folder_flag(path, ident.removeprefix("flag_"), checked)
        elif ident == "flag_write_beside":
            explorer.live_control.set_write_beside(path, checked)
        elif ident == "txy_choose":
            explorer.choose_folder_txy(path)
        elif ident == "policy_choose":
            explorer.choose_folder_policy(path)
        elif ident == "constants_edit":
            explorer.show_folder_constants(path)
        elif ident == "scan_refresh":
            explorer.refresh_folder(path)
        elif ident == "convert":
            explorer.converter.ask_convert(path)
        if not self.isHidden():
            self.rebuild()  # (A toggle a dialog declined shows its state again.)

    @pyqtSlot(bool)
    def _clicked(self, checked: bool = False) -> None:
        button = self.sender()
        ident = str(button.property("action")) if button is not None else ""
        if ident:
            self.act(ident, checked)

    @pyqtSlot()
    def _more_clicked(self) -> None:
        button = self.sender()
        if button is not None:
            self.open_detail(str(button.property("section")))

    # Rendering (memory only)

    def rebuild(self) -> None:
        if not self.path:
            return
        memory = self.sources.memory(self.path, self.explorer())
        self.info = folder_info.build(self.answer, memory, time.time(), error=self.error,
                                      reading=self.reads.in_flight)
        self._paint(self.info)

    def _row(self, row: Row, ident: str, stale: bool = False,
             mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight) -> ElidedLabel:
        label = identify(ElidedLabel(row.text, mode=mode), ident)
        label.setToolTip(row.tooltip or row.text)
        if row.warn:
            label.setStyleSheet(f"color: {AMBER};")
        label.setEnabled(not stale)
        return label

    def _button(self, action: Action, ident: str) -> QToolButton:
        # (Tool buttons: a title line keeps a label's height, no padding around the blocks.)
        button = identify(QToolButton(), ident, action.label)
        button.setText(action.label)
        button.setAutoRaise(True)
        button.setProperty("action", action.id)
        button.setToolTip(action.tooltip)
        button.setEnabled(action.enabled)
        if action.checked is not None:
            button.setCheckable(True)
            button.setChecked(action.checked)
        button.clicked.connect(self._clicked)
        return button

    def _line(self, widgets: list[QWidget], stretch_first: bool = True) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(COLUMN_GAP)
        for index, widget in enumerate(widgets):
            line.addWidget(widget, 1 if index == 0 and stretch_first else 0)
        return line

    def _paint(self, info: Info) -> None:
        self.setWindowTitle(info.title)
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        root_actions = [action for action in info.header_actions if action.id in ROOT_ACTIONS]
        other = [action for action in info.header_actions if action.id not in ROOT_ACTIONS]
        for index, row in enumerate(info.header):
            label = self._row(row, f"folder_info_header_{index}",
                              mode=Qt.TextElideMode.ElideMiddle if index == 0 else Qt.TextElideMode.ElideRight)
            widgets: list[QWidget] = [label]
            if index == 1:
                widgets += [self._button(action, f"folder_info_{action.id}") for action in root_actions]
            if row.text.startswith(("As of", "Not read yet")):
                widgets += [self._button(action, f"folder_info_{action.id}") for action in other]
            header_layout.addLayout(self._line(widgets))
        self.outer.replaceWidget(self.header, header)
        self._retire(self.header)
        self.header = header
        header.show()
        bar = self.sections_area.verticalScrollBar()
        position = bar.value() if bar is not None else 0
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for section in info.sections:
            self._section(layout, section)
        layout.addStretch(1)
        old = self.sections_area.takeWidget()
        self.sections_area.setWidget(body)
        if old is not None:
            self._retire(old)
        bar = self.sections_area.verticalScrollBar()
        if bar is not None:
            bar.setValue(position)
        if self._detail:
            self._fill_detail()

    @staticmethod
    def _retire(widget: QWidget) -> None:
        """A replaced part: out of the window at once (its IDs are the new part's now), deleted later (a button of
        it may be the one whose click rebuilt the window)."""
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def _section(self, layout: QVBoxLayout, section: Section) -> None:
        title = identify(QLabel(section.title), f"folder_info_{section.id}_title")
        title.setFont(self._bold())
        buttons: list[QWidget] = [self._button(action, f"folder_info_{section.id}_{action.id}")
                                  for action in section.actions]
        layout.addLayout(self._line([title, *buttons]))
        for index, row in enumerate(section.rows):
            line = self._row(row, f"folder_info_{section.id}_row_{index}", section.stale)
            line.setContentsMargins(LABEL_GAP * 2, 0, 0, 0)
            layout.addWidget(line)
        if section.more:
            more = identify(QToolButton(), f"folder_info_{section.id}_more", section.more)
            more.setText(section.more)
            more.setAutoRaise(True)
            more.setProperty("section", section.id)
            more.setToolTip("Open the full list beside the window (the window widens)")
            more.clicked.connect(self._more_clicked)
            link = QHBoxLayout()
            link.setContentsMargins(LABEL_GAP * 2, 0, 0, 0)
            link.addWidget(more)
            link.addStretch(1)
            layout.addLayout(link)

    # The detail pane: the window grows sideways, not tall (Q64.7)

    def open_detail(self, section_id: str) -> None:
        """Show ``section_id``'s full list to the right, widening the window by the pane's width (up to the screen's)."""
        self._detail = section_id
        if not self._fill_detail():
            return
        if self.pane.isHidden():
            left = self.sections_area.width()
            self._pane_width = max(360, self.fontMetrics().averageCharWidth() * 60)
            width, x = self.width() + self._pane_width, self.x()
            screen = self.screen()
            if screen is not None:
                room = screen.availableGeometry()
                width = min(width, room.width())
                if x + width > room.right():
                    x = max(room.left(), room.right() - width)
            self.pane.show()
            self.setGeometry(x, self.y(), width, self.height())
            self.splitter.setSizes([max(MIN_SIZE[0] // 2, min(left, width - self._pane_width)), self._pane_width])

    def _fill_detail(self) -> bool:
        section = next((section for section in (self.info.sections if self.info else ()) if section.id == self._detail),
                       None)
        if section is None or section.detail is None:
            self.close_detail()
            return False
        detail = section.detail
        self.pane_title.setText(detail.title)
        self.tree.clear()
        self.tree.setColumnCount(len(detail.columns))
        self.tree.setHeaderLabels(list(detail.columns))
        for cells, tooltip in detail.rows:
            item = QTreeWidgetItem(list(cells))
            for column in range(len(cells)):
                item.setToolTip(column, tooltip or cells[column])
            self.tree.addTopLevelItem(item)
        return True

    @pyqtSlot()
    def close_detail(self) -> None:
        """Close the detail pane and give its width back."""
        self._detail = ""
        if not self.pane.isHidden():
            width = max(MIN_SIZE[0], self.width() - self.pane.width())
            self.pane.hide()
            self.resize(width, self.height())

    # The window

    def fit_screen(self) -> None:
        """At most the screen's available size (a size saved on a larger monitor), at least ``MIN_SIZE``."""
        screen = (self.parentWidget() or self).screen()
        if screen is None:
            return
        room = screen.availableGeometry()
        width, height = min(self.width(), room.width()), min(self.height(), room.height())
        if (width, height) != (self.width(), self.height()):
            self.resize(max(MIN_SIZE[0], width), max(MIN_SIZE[1], height))

    def showEvent(self, a0: Optional[QShowEvent]) -> None:
        super().showEvent(a0)
        if not self._fitted:
            self._fitted = True
            self.fit_screen()
        self._connect()

    def hideEvent(self, a0: Optional[QHideEvent]) -> None:
        super().hideEvent(a0)
        self._disconnect()
        self._read_timer.stop()
        self._memory_timer.stop()
        width = self.width() - (self.pane.width() if not self.pane.isHidden() else 0)
        app_settings().setValue(FOLDER_INFO_SIZE_SETTING, f"{max(MIN_SIZE[0], width)},{self.height()}")
