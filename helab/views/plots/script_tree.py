"""The Scripts panel (``TreePanelWidget``): HeLab's bundled analyses and loaded scripts by
group, with each script's run buttons; it opens each new plot's dock in the plot area."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING, Union

from PyQt6 import sip
from PyQt6.QtCore import QFileSystemWatcher, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget)

from helab.analysis.dataset_view import DatasetView
from helab.analysis.presets import SavedPlot, ScriptRef, waiting_view
from helab.analysis.runner import AnalysisRunner, get_analysis_runner
from helab.scripts import dld, standard
from helab.scripts.base import DatasetAnalysis, ScriptMetadata
from helab.scripts.scripts_manager import LoadError, ScriptsManager, Stamp
from helab.utils.accessible import id_part, identify
from helab.utils.colours import AMBER
from helab.utils.settings_defaults import SCRIPT_AUTO_RELOAD_SETTING, SCRIPT_FOLDERS_SETTING, read_setting
from helab.utils.settings_store import app_settings
from helab.views.plots.dock import AnalysisDock, DockTabCloser
from helab.views.plots.instance import AnalysisInstance, LinkedAnalysisInstance
if TYPE_CHECKING:
    from helab.views.plots.arrangement import FolderWait
    from helab.views.plots.workspace import PlotWorkspace

# ``_add_dock``'s default: tab the new plot with the shown one (``tab_target``).
AUTO = "auto"
# Auto-reload: a change starts this wait (ms) before the folder's files are compared, so an editor's save
# (often a temporary file, then a rename) has finished.
SETTLE_MS = 750


def read_script_folders() -> List[str]:
    """The remembered script folders (``script_folders``: a JSON list of paths); unreadable: none."""
    text = read_setting(app_settings(), SCRIPT_FOLDERS_SETTING, typed=True)
    if not text:
        return []
    try:
        folders = json.loads(text)
    except ValueError:
        logging.warning("Remembered script folders unreadable (%r): none restored", text)
        return []
    return [folder for folder in folders if isinstance(folder, str) and folder] if isinstance(folders, list) else []


class TreePanelWidget(QWidget):
    """The Scripts panel: a group selector, Load Scripts… and the selected group's scripts, each
    with up to two run buttons (its first actions).

    Groups are each script's metadata group: HeLab's bundled analyses ("Basic plots v1",
    ``helab.scripts.standard.group``; "DLD Front Panel Port", ``helab.scripts.dld.group``) and
    those of scripts loaded from a folder (``ScriptsManager``).

    ``plotsChanged`` says when a plot opened or closed (the plots to reopen at start are recorded
    then, helab/views/plots/arrangement.py).

    **Live scripts:** the folders added with Load Scripts… are remembered (``script_folders``) and
    loaded again at start, before plots reopen; Load Scripts…'s menu removes one from the list and
    turns on reloading when a script is saved (``script_auto_reload``, off by default: only then a
    ``QFileSystemWatcher`` watches the script folders and their helper modules, never a data
    folder). **Reload** loads the folders again with their helper modules (``ScriptsManager``); a
    reload waits until no run of those folders' scripts is queued or computing (their plots are held
    and their runs cancelled first), then each open plot of them takes the new code
    (``AnalysisInstance.adopt_script``) or, its script gone or failing, keeps its old code and says
    so (``keep_script``). Files that didn't load are listed at the tree's end, whatever the group,
    with their traceback in the tooltip and, on a double-click, a details window.
    """

    plotsChanged = pyqtSignal()

    def __init__(self, workspace: Optional[PlotWorkspace] = None,
                 parent: Any = None) -> None:
        super().__init__(parent)

        self.workspace = workspace  # The plot area new plots open in.
        self.script_manager = ScriptsManager()
        
        self.groups: List[str] = []  # As the group selector lists them.

        # Analysis instance tracking
        self._instance_counter = 0
        self._analysis_instances: Dict[str, LinkedAnalysisInstance] = {}

        # Layout for the right-bottom panel
        self.panel_layout_right_bottom = QVBoxLayout(self)
        self.panel_layout_right_bottom.setContentsMargins(0, 0, 0, 0)

        # Add controls at the top
        controls_layout = QHBoxLayout()
        
        # Add group selector
        self.group_selector = identify(QComboBox(), "script_group", "Script group",
                                       "Choose which group's scripts are listed")
        self.group_selector.currentTextChanged.connect(self._on_group_changed)
        controls_layout.addWidget(QLabel("Group:"))
        controls_layout.addWidget(self.group_selector)

        # Add script directory button; its menu: the remembered folders and auto-reload.
        self.load_dir_button = identify(QToolButton(), "load_scripts", "Load Scripts...",
                                        "Load analysis scripts from a folder; the menu lists the folders loaded")
        self.load_dir_button.setText("Load Scripts...")
        self.load_dir_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.load_dir_button.clicked.connect(self._on_load_directory)
        self.folders_menu = QMenu(self.load_dir_button)
        self.folders_menu.aboutToShow.connect(self._fill_folders_menu)
        self.load_dir_button.setMenu(self.folders_menu)
        self.auto_reload_action = QAction("Reload when a script is saved", self)
        self.auto_reload_action.setCheckable(True)
        self.auto_reload_action.setToolTip("Watch the script folders (only those) and reload one when a script or "
                                           "helper module in it is saved")
        self.auto_reload_action.toggled.connect(self.set_auto_reload)
        controls_layout.addWidget(self.load_dir_button)
        self.reload_button = identify(QPushButton("Reload"), "reload_scripts", "Reload scripts",
                                      "Import the loaded folders' scripts and their helper modules again; open "
                                      "plots of them rerun on the new code")
        self.reload_button.clicked.connect(self.reload_scripts)
        controls_layout.addWidget(self.reload_button)
        # The row shrinks with the panel, never sets its width (Q33.2; on Windows it held the settings panel at
        # ~548 px): the combo to a few characters, the button to its text.
        self.group_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.group_selector.setMinimumContentsLength(4)
        for button in (self.load_dir_button, self.reload_button):
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 8)

        controls_layout.addStretch()
        self.panel_layout_right_bottom.addLayout(controls_layout)

        # Tree list widget
        self.tree_widget = identify(QTreeWidget(), "scripts", "Scripts", "The group's scripts and their run buttons")
        self.tree_widget.setHeaderLabels(["Script", "Run", "Run"])
        self.tree_widget.setColumnCount(3)
        header = self.tree_widget.header()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setStretchLastSection(False)
            self.tree_widget.setColumnWidth(1, 100)
            self.tree_widget.setColumnWidth(2, 100)

        # Add tree widget to the layout
        self.panel_layout_right_bottom.addWidget(self.tree_widget)

        # Live scripts: what each folder's files were when last loaded (auto-reload compares), the
        # folders waiting to reload (until their runs end), and the watcher (only while auto-reload is on).
        self._stamps: Dict[str, Stamp] = {}
        self._pending: Set[str] = set()
        self._waiting_on: List[AnalysisRunner] = []
        self._watcher: Optional[QFileSystemWatcher] = None
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._check_changes)
        self._details: Optional[QMessageBox] = None
        self.tree_widget.itemDoubleClicked.connect(self._show_error_details)

        # HeLab's bundled analyses, then the user's remembered folders (before plots reopen)
        self._load_default_scripts()
        self._restore_folders()

        logging.info(f"TreePanelWidget initialized. {type(self.parent()) = }")

    def _load_default_scripts(self) -> None:
        """Register HeLab's bundled analyses (``helab.scripts.standard``, then the DLD front panel port, ``helab.scripts.dld``) and show the first group."""
        for module in (*standard.MODULES, *dld.MODULES):
            try:
                self.script_manager.load_module(module)
            except Exception as e:
                logging.error(f"Error loading bundled analyses from {module.__name__}: {e}")
        self._update_groups()
        if self.group_selector.count() > 0:
            self.group_selector.setCurrentIndex(0)

    def _on_load_directory(self) -> None:
        """Handle loading a new script directory selected by the user.
        
        This method:
        1. Opens a file dialog for directory selection
        2. Loads Python script files from the selected directory
        3. Updates available groups in the UI
        4. Reloads the current group if one is selected
        
        Error handling:
        - Logs any errors that occur during script loading
        - Maintains UI state even if script loading fails
        """
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Script Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if dir_path:
            self.add_folder(dir_path)

    # Live scripts: the user's folders

    def _restore_folders(self) -> None:
        """Load the remembered folders (a missing one is listed with "folder not found"), and start
        watching them if auto-reload is on."""
        for folder in read_script_folders():
            self._load_folder(folder)
        self._refresh()
        auto = bool(read_setting(app_settings(), SCRIPT_AUTO_RELOAD_SETTING, typed=True))
        self.auto_reload_action.blockSignals(True)
        self.auto_reload_action.setChecked(auto)
        self.auto_reload_action.blockSignals(False)
        self._watch(auto)

    def _load_folder(self, folder: str) -> bool:
        try:
            loaded = self.script_manager.add_folder(folder)
        except Exception:  # (Never expected: the manager keeps each file's failure. It stays listed.)
            logging.exception("Error loading scripts from %s", folder)
            return False
        self._stamps[ScriptsManager.normal(folder)] = self._stamp_of(folder)
        return loaded

    def _stamp_of(self, folder: str) -> Stamp:
        manager = self.script_manager
        return manager.stamp(manager.watched_files(folder))

    def add_folder(self, folder: str) -> None:
        """Load Scripts…: a new folder is loaded and remembered; one loaded already reloads (its plots
        take the new code)."""
        folder = ScriptsManager.normal(folder)
        if any(os.path.normcase(known) == os.path.normcase(folder) for known in self.script_manager.folders()):
            self.reload_scripts([folder])
            return
        self._load_folder(folder)
        self._save_folders()
        self._refresh()
        self._sync_watch()
        self._say_errors(folder)

    def remove_folder(self, folder: str) -> None:
        """Remove from the list: its scripts go from the panel (its files stay); its open plots keep
        the code they have and say so."""
        folder = ScriptsManager.normal(folder)
        for instance in self._plots_of({folder}):
            instance.keep_script("its folder was removed from the Scripts list")
        self._pending.discard(folder)
        self.script_manager.remove_folder(folder)
        self._stamps.pop(folder, None)
        self._save_folders()
        self._refresh()
        self._sync_watch()

    def _save_folders(self) -> None:
        app_settings().setValue(SCRIPT_FOLDERS_SETTING, json.dumps(self.script_manager.folders()))

    def _fill_folders_menu(self) -> None:
        menu = self.folders_menu
        menu.clear()
        folders = self.script_manager.folders()
        if folders:
            menu.addSection("Script folders")
        for folder in folders:
            sub = menu.addMenu(folder)
            assert sub is not None
            reload = sub.addAction("Reload")
            remove = sub.addAction("Remove from the list")
            assert reload is not None and remove is not None
            reload.setData(folder)
            remove.setData(folder)
            reload.triggered.connect(self._reload_chosen)
            remove.triggered.connect(self._remove_chosen)
        if not folders:
            none = menu.addAction("No script folders loaded")
            assert none is not None
            none.setEnabled(False)
        menu.addSeparator()
        menu.addAction(self.auto_reload_action)

    @pyqtSlot()
    def _reload_chosen(self) -> None:
        action = self.sender()
        if isinstance(action, QAction) and isinstance(action.data(), str):
            self.reload_scripts([action.data()])

    @pyqtSlot()
    def _remove_chosen(self) -> None:
        action = self.sender()
        if isinstance(action, QAction) and isinstance(action.data(), str):
            self.remove_folder(action.data())

    # Live scripts: reloading

    def _plots_of(self, folders: Set[str]) -> List[AnalysisInstance]:
        """The open plots whose script was loaded from one of ``folders``."""
        keys = {os.path.normcase(folder) for folder in folders}
        manager = self.script_manager
        return [instance for instance in self.instances()
                if os.path.normcase(manager.folder_of(instance.metadata.script_id)
                                    or manager.class_folder(type(instance.script))) in keys]

    def reload_scripts(self, folders: Optional[List[str]] = None) -> None:
        """Reload ``folders`` (default: every loaded one). Their plots are held and their runs cancelled;
        the reload itself waits until no run of those folders' scripts is queued or computing (a
        ``compute`` on the worker thread is never under a reload), then runs (``_try_reload``)."""
        chosen = self.script_manager.folders() if folders is None else [ScriptsManager.normal(f) for f in folders]
        if not chosen:
            return
        self._pending.update(chosen)
        for instance in self._plots_of(set(chosen)):
            instance.hold_for_reload()
        self._try_reload()

    def _runners(self) -> List[AnalysisRunner]:
        runners = [get_analysis_runner()]
        for instance in self.instances():
            if instance.runner not in runners:
                runners.append(instance.runner)
        return runners

    def _busy(self, folders: Set[str]) -> int:
        """Runs of ``folders``' scripts queued or computing, on any runner the plots use."""
        keys = {os.path.normcase(folder) for folder in folders}
        manager = self.script_manager
        return sum(1 for runner in self._runners() for script in runner.in_flight()
                   if os.path.normcase(manager.class_folder(type(script))) in keys)

    def _try_reload(self) -> None:
        if not self._pending:
            return
        busy = self._busy(self._pending)
        if busy:
            for runner in self._runners():
                if runner not in self._waiting_on:
                    runner.finished.connect(self._run_ended)
                    self._waiting_on.append(runner)
            self.reload_button.setText("Reload (waiting)")
            self.reload_button.setToolTip(f"The reload waits for {busy:,} run{'' if busy == 1 else 's'} of these "
                                          "scripts to end (cancelled)")
            return
        self._stop_waiting()
        folders, self._pending = set(self._pending), set()
        for folder in sorted(folders):
            self._load_folder(folder)
        self._refresh()
        self._sync_watch()
        adopted, kept = self._adopt(folders)
        self.plotsChanged.emit()  # (Their records name the new code.)
        errors = [error for error in self.script_manager.errors()
                  if any(self._in_folder(error.path, folder) for folder in folders)]
        parts = [f"Reloaded {len(folders):,} script folder{'' if len(folders) == 1 else 's'}"]
        if adopted:
            parts.append(f"{adopted:,} plot{'' if adopted == 1 else 's'} rerun")
        if kept:
            parts.append(f"⚠ {kept:,} plot{'' if kept == 1 else 's'} kept the old code")
        if errors:
            parts.append(f"⚠ {len(errors):,} file{'' if len(errors) == 1 else 's'} didn't load (listed in Scripts)")
        if self.workspace is not None:
            self.workspace.notice(" · ".join(parts))

    @staticmethod
    def _in_folder(path: str, folder: str) -> bool:
        return os.path.normcase(path) == os.path.normcase(folder) or \
            os.path.normcase(os.path.dirname(path)) == os.path.normcase(folder)

    @pyqtSlot(object)
    def _run_ended(self, _result: object) -> None:
        if self._pending:
            self._try_reload()

    def _stop_waiting(self) -> None:
        for runner in self._waiting_on:
            try:
                runner.finished.disconnect(self._run_ended)
            except TypeError:
                pass
        self._waiting_on.clear()
        self.reload_button.setText("Reload")
        self.reload_button.setToolTip("Import the loaded folders' scripts and their helper modules again; open "
                                      "plots of them rerun on the new code")

    def _adopt(self, folders: Set[str]) -> Tuple[int, int]:
        """Each open plot of ``folders`` takes its script's new code, or keeps its old one and says why:
        (plots that took it, plots that kept theirs)."""
        adopted = kept = 0
        manager = self.script_manager
        for instance in self._plots_of(folders):
            found = self._reloaded(instance)
            if isinstance(found, str):
                instance.keep_script(found)
                kept += 1
            elif instance.adopt_script(*found):
                instance.code_loaded_at = manager.loaded_at(found[0].script_id)
                adopted += 1
            else:
                kept += 1
        return adopted, kept

    def _reloaded(self, instance: AnalysisInstance) -> Union[Tuple[ScriptMetadata, DatasetAnalysis], str]:
        """The reloaded script of ``instance`` (its file's class of the same analysis id, else another
        of its folder's), a new instance of it, or why there is none."""
        manager = self.script_manager
        old = instance.metadata
        folder = manager.folder_of(old.script_id) or manager.class_folder(type(instance.script))
        file = old.script_id.rpartition("::")[0]
        failed = next((error for error in manager.errors() if os.path.normcase(error.path) == os.path.normcase(file)
                       or os.path.normcase(error.path) == os.path.normcase(folder)), None)
        candidates = [metadata for script_id in manager.script_ids(folder)
                      if (metadata := manager.get_script_metadata(script_id)) is not None
                      and metadata.identity().analysis_id == old.identity().analysis_id]
        candidates.sort(key=lambda metadata: metadata.script_id != old.script_id)
        if not candidates:
            return failed.message if failed is not None else "its class is gone from its folder"
        metadata = candidates[0]
        script_class = manager.get_script(metadata.script_id)
        try:
            script = script_class() if script_class is not None else None
            actions = script.get_actions() if script is not None else []
        except Exception as error:
            logging.exception("%s could not be made", metadata.name)
            return f"{type(error).__name__}: {error}"
        if not isinstance(script, DatasetAnalysis):
            return "its script no longer plots a folder's data"
        if instance.action not in actions:
            return f"its script has no “{instance.action}” now"
        return metadata, script

    # Live scripts: auto-reload

    def set_auto_reload(self, on: bool) -> None:
        """Reload when a script is saved: saved (``script_auto_reload``), and the watcher made or dropped."""
        app_settings().setValue(SCRIPT_AUTO_RELOAD_SETTING, bool(on))
        if self.auto_reload_action.isChecked() != on:
            self.auto_reload_action.blockSignals(True)
            self.auto_reload_action.setChecked(on)
            self.auto_reload_action.blockSignals(False)
        self._watch(on)

    def _watch(self, on: bool) -> None:
        if not on:
            self._settle.stop()
            if self._watcher is not None:
                self._watcher.deleteLater()
                self._watcher = None
            return
        if self._watcher is None:
            self._watcher = QFileSystemWatcher(self)
            self._watcher.directoryChanged.connect(self._changed)
            self._watcher.fileChanged.connect(self._changed)
        self._sync_watch()

    def watched(self) -> List[str]:
        """What the watcher watches now (none while auto-reload is off)."""
        watcher = self._watcher
        return sorted([*watcher.directories(), *watcher.files()]) if watcher is not None else []

    def _sync_watch(self) -> None:
        """Watch exactly the script folders that are there and their watched files (an editor that saves by
        replacing a file ends the watch on it: it is added again here, after each change)."""
        watcher = self._watcher
        if watcher is None:
            return
        manager = self.script_manager
        wanted: Set[str] = set()
        for folder in manager.folders():
            if os.path.isdir(folder):
                wanted.add(folder)
                wanted.update(os.path.dirname(file) for file in manager.watched_files(folder))
                wanted.update(manager.watched_files(folder))
        now = set(watcher.directories()) | set(watcher.files())
        if gone := sorted(now - wanted):
            watcher.removePaths(gone)
        if new := sorted(wanted - now):
            watcher.addPaths(new)

    @pyqtSlot(str)
    def _changed(self, _path: str) -> None:
        self._settle.start()  # (Restarted by each event: compared once they stop.)

    def _check_changes(self) -> None:
        """After the settle wait: reload each folder whose ``.py`` files or helper modules changed (added,
        removed, resized or modified), only those."""
        self._sync_watch()
        changed = [folder for folder in self.script_manager.folders()
                   if self._stamp_of(folder) != self._stamps.get(folder)]
        if changed:
            self.reload_scripts(changed)

    # Live scripts: load errors

    def _say_errors(self, folder: str) -> None:
        errors = [error for error in self.script_manager.errors() if self._in_folder(error.path, folder)]
        if errors and self.workspace is not None:
            self.workspace.notice(f"⚠ {len(errors):,} script file{'' if len(errors) == 1 else 's'} didn't load "
                                  "(listed in Scripts)")

    def _refresh(self) -> None:
        """The groups and the shown group's scripts again (after a load), and the load errors."""
        self._update_groups()
        if self.group_selector.currentText():
            self._load_current_group()
        else:
            self._show_errors()
        self.reload_button.setEnabled(bool(self.script_manager.folders()))

    def _show_errors(self) -> None:
        """``⚠ N script files didn't load`` at the tree's end, one line per file, its traceback in the tooltip."""
        errors = self.script_manager.errors()
        if not errors:
            return
        count = len(errors)
        top = QTreeWidgetItem(self.tree_widget, [f"⚠ {count:,} script file{'' if count == 1 else 's'} didn't load"])
        top.setFirstColumnSpanned(True)
        amber = QBrush(QColor(AMBER))
        top.setForeground(0, amber)
        top.setToolTip(0, "Fix them and Reload; double-click one for its traceback")
        for error in errors:
            item = QTreeWidgetItem(top, [error.line()])
            item.setFirstColumnSpanned(True)
            item.setForeground(0, amber)
            item.setToolTip(0, f"{error.path}\n\n{error.details or error.message}")
            item.setData(0, Qt.ItemDataRole.UserRole, error.path)
        top.setExpanded(True)

    def error_items(self) -> List[QTreeWidgetItem]:
        """The load errors' lines in the tree (none when all loaded)."""
        for index in range(self.tree_widget.topLevelItemCount()):
            top = self.tree_widget.topLevelItem(index)
            if top is not None and top.text(0).startswith("⚠ ") and "didn't load" in top.text(0):
                return [child for row in range(top.childCount()) if (child := top.child(row)) is not None]
        return []

    def _show_error_details(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        error = next((error for error in self.script_manager.errors() if error.path == path), None)
        if not isinstance(path, str) or error is None:
            return
        self.show_error_details(error)

    def show_error_details(self, error: LoadError) -> QMessageBox:
        """A details window for one load error (non-modal; one at a time): its line and its traceback."""
        if self._details is not None and not sip.isdeleted(self._details):
            self._details.close()
        box = QMessageBox(QMessageBox.Icon.Warning, "Script didn't load", error.line(),
                          QMessageBox.StandardButton.Close, self)
        identify(box, "script_error_details", "Script didn't load")
        box.setInformativeText(error.path)
        box.setDetailedText(error.details or error.message)
        box.setModal(False)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.show()
        self._details = box
        return box

    def _update_groups(self) -> None:
        """Update the group selector with available groups.
        
        This method manages the UI state when groups are added or removed:
        1. Preserves the current selection if possible
        2. Updates the dropdown with all available groups
        3. Attempts to restore the previous selection
        4. Falls back to first item if previous selection is gone
        5. Clears the tree widget if no groups are available
        
        This provides a smooth transition when the available groups change,
        maintaining user selection when possible while ensuring the UI
        stays in a valid state.
        """
        current = self.group_selector.currentText()
        groups = self.script_manager.get_groups()
        self.groups = list(groups)  # Known before the selector lists them (it selects one at once).
        self.group_selector.clear()
        if groups:
            self.group_selector.addItems(groups)
            
            # Try to restore previous selection
            index = self.group_selector.findText(current)
            if index >= 0:
                self.group_selector.setCurrentIndex(index)
            else:
                self.group_selector.setCurrentIndex(0)
        else:
            self.tree_widget.clear()
            self._show_errors()

    def _on_group_changed(self, group_name: str) -> None:
        """The selector chose another group: list its scripts."""
        if group_name:
            if group_name in self.groups:
                self._load_current_group()
            else:
                logging.error(f"Unknown group: {group_name}")

    def _load_current_group(self) -> None:
        """Load the currently selected group's scripts into the tree widget.
        
        1. Loads script metadata from ScriptsManager
        2. Creates script class instances
        3. Sets up action buttons for each script
        4. Handles errors by displaying them in red
        
        The loaded scripts appear as child items under their group in the tree,
        with up to two action buttons for each script.
        """
        group_name = self.group_selector.currentText()
        if not group_name or group_name not in self.groups:
            return

        self.tree_widget.clear()
        group_item = QTreeWidgetItem(self.tree_widget, [group_name])
        group_item.setFirstColumnSpanned(True)

        for metadata in self.script_manager.get_scripts_in_group(group_name):
            script_class = self.script_manager.get_script(metadata.script_id)
            if script_class:
                try:
                    script = script_class()
                    actions = script.get_actions()

                    item = QTreeWidgetItem(group_item, [metadata.name])
                    item.setToolTip(0, f"{metadata.description}\n{metadata.identity().text()}")
                    for column, action in enumerate(actions[:2], start=1):
                        button = self.create_button(action, self._action_callback(metadata, script, action))
                        # "Plot Counts per shot", its ID from the script's analysis ID (not its name).
                        identify(button, f"run_{id_part(metadata.identity().analysis_id)}_{id_part(action)}",
                                 f"{action} {metadata.name}", f"Run {metadata.name} on this tab's loaded data")
                        self.tree_widget.setItemWidget(item, column, button)
                except Exception as e:
                    logging.error(f"Error loading script {metadata.name}: {e}")
                    error_item = QTreeWidgetItem(group_item, [f"{metadata.name} (Error)"])
                    error_item.setForeground(0, Qt.GlobalColor.red)
                    error_item.setToolTip(0, f"{type(e).__name__}: {e}")

        group_item.setExpanded(True)
        self._show_errors()

    def _action_callback(self, metadata: ScriptMetadata, script: Any, action: str) -> Callable[[], None]:
        if isinstance(script, DatasetAnalysis):
            def run() -> None:
                self.run_analysis(metadata, script, action)
            return run
        return lambda: script.execute_action(action)

    def run_analysis(self, metadata: ScriptMetadata, script: DatasetAnalysis,
                     action: str) -> Optional[AnalysisInstance]:
        """Run ``action`` on the current tab's shown dataset, in a new plot dock."""
        plots = self.workspace
        view = plots.current_dataset_view() if plots is not None else None
        if plots is None or not isinstance(view, DatasetView):
            if plots is not None:
                plots.notice(f"{metadata.name}: load a folder's data first")
            return None
        self._instance_counter += 1
        instance_id = f"{self._instance_counter}"
        try:
            instance = AnalysisInstance(metadata, script, action, view, instance_id, plots)
        except Exception as error:
            # The script's live_policy() or constant_keys() failing (in this Qt slot it would abort the app).
            logging.exception("%s could not open its plot", metadata.name)
            plots.notice(f"{metadata.name} failed: {error}")
            return None
        instance.code_loaded_at = self.script_manager.loaded_at(metadata.script_id)
        self._analysis_instances[instance_id] = instance
        instance.start()
        self._add_dock(instance)
        return instance

    def instances(self) -> List[AnalysisInstance]:
        """The open plots (of dataset analyses), as opened."""
        return [instance for instance in self._analysis_instances.values()
                if isinstance(instance, AnalysisInstance) and not instance.is_closed]

    def find_script(self, ref: ScriptRef) -> Union[Tuple[ScriptMetadata, DatasetAnalysis], str]:
        """The loaded script ``ref`` names (by its analysis id) with its action, a new instance of
        it, or why there is none (for the user: "its script isn't loaded …")."""
        for group in self.script_manager.get_groups():
            for metadata in self.script_manager.get_scripts_in_group(group):
                if metadata.identity().analysis_id != ref.analysis_id:
                    continue
                script_class = self.script_manager.get_script(metadata.script_id)
                try:
                    script = script_class() if script_class is not None else None
                    actions = script.get_actions() if script is not None else []
                except Exception as error:
                    logging.exception("%s could not be made", metadata.name)
                    return f"its script failed: {error}"
                if not isinstance(script, DatasetAnalysis):
                    return "its script no longer plots a folder's data"
                if ref.action not in actions:
                    return f"its script has no “{ref.action}” now"
                return metadata, script
        return "its script isn't loaded (Load Scripts… its folder, then open it again)"

    def reopen_plot(self, saved: SavedPlot, wait: FolderWait, *, keep_id: bool = False,
                    place: bool = True) -> Union[AnalysisInstance, str]:
        """Open ``saved`` again (at start, or from an arrangement preset): a plot of its script with
        its saved settings, waiting for its folder's data (``wait``) instead of running. Its number
        is its saved one if ``keep_id`` and free. Not ``place``: its dock isn't added to the plot
        area yet (the caller places it, ``place_dock``). The plot, or why it couldn't open."""
        plots = self.workspace
        if plots is None:
            return "no plot area"
        found = self.find_script(saved.script)
        if isinstance(found, str):
            return found
        metadata, script = found
        if keep_id and saved.instance_id.isdecimal() and saved.instance_id not in self._analysis_instances:
            instance_id = saved.instance_id
            self._instance_counter = max(self._instance_counter, int(instance_id))
        else:
            self._instance_counter += 1
            instance_id = f"{self._instance_counter}"
        try:
            instance = AnalysisInstance(metadata, script, saved.script.action,
                                        waiting_view(saved.path, saved.root_key), instance_id, plots)
        except Exception as error:
            logging.exception("%s could not open its plot", metadata.name)
            return f"it failed: {error}"
        instance.code_loaded_at = self.script_manager.loaded_at(metadata.script_id)
        self._analysis_instances[instance_id] = instance
        instance.start(saved, wait)
        if instance.open_error:
            # Without its settings page it would be recorded with none: it couldn't reopen (kept).
            del self._analysis_instances[instance_id]
            instance.close()
            return f"it failed: {instance.open_error}"
        if place:
            self._add_dock(instance)
        return instance

    def place_dock(self, instance: LinkedAnalysisInstance, tab_with: Optional[QDockWidget]) -> None:
        """Add a reopened plot's dock to the plot area: tabbed with ``tab_with``, else on its own."""
        self._add_dock(instance, tab_with)

    def _add_dock(self, instance: LinkedAnalysisInstance, tab_with: Union[Optional[QDockWidget], str] = AUTO) -> None:
        plots, dock = self.workspace, instance.dock_widget
        if plots is None or not isinstance(dock, AnalysisDock):
            return
        instance.ended.connect(self._forget_instance)
        settings = plots.panel_right_top_plot_settings
        area = plots.middle_mainwindow
        settings.follow(area)
        closer = area.findChild(DockTabCloser) or DockTabCloser(area)
        target = (self.tab_target(area, plots.dock_widgets, settings.current_plot()) if tab_with == AUTO
                  else tab_with if isinstance(tab_with, QDockWidget) else None)
        area.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        # In a shown area Qt hides the new dock and shows it later, and it won't tab a plot
        # opened meanwhile with a hidden one: show it now.
        dock.show()
        if target is not None:
            # Plots share the area as tabs; the new one comes to the front.
            area.tabifyDockWidget(target, dock)
            dock.raise_()
        closer.watch(dock)
        plots.dock_widgets.append(dock)
        plots.update_placeholder_visibility()
        self.plotsChanged.emit()

    @staticmethod
    def tab_target(area: QMainWindow, open_docks: List[QDockWidget],
                   shown: Optional[QDockWidget]) -> Optional[QDockWidget]:
        """The open plot a new plot is tabbed with in ``area``: the plot whose settings show
        (``shown``) if it is docked there, else the newest docked one. Docked means in the
        area and not floating; a plot behind another tab counts, and whether docks are
        visible yet doesn't matter (``addDockWidget`` shows a dock later, and the area may not
        be shown). Never a floating plot (Qt would put the new one in its old place, beside
        some other plot), nor a hidden plot on its own (unticked in the area's menu: the new
        one would sit alone in its place); a hidden plot in a tab group still stands for that
        group. Closed plots aren't open. None: the new plot docks on its own (no plot open,
        or all floating or hidden)."""
        docked = [dock for dock in open_docks if not sip.isdeleted(dock) and not dock.isFloating()
                  and area.dockWidgetArea(dock) != Qt.DockWidgetArea.NoDockWidgetArea
                  and (not dock.isHidden() or area.tabifiedDockWidgets(dock))]
        if shown in docked:
            return shown
        return docked[-1] if docked else None

    @pyqtSlot(str)
    def _forget_instance(self, instance_id: str) -> None:
        if self._analysis_instances.pop(instance_id, None) is not None:
            self.plotsChanged.emit()

    def create_button(self, label: str, callback: Callable[..., Any]) -> QPushButton:
        """Create a standardized action button for script items.
        
        Creates a QPushButton with consistent styling and behavior:
        - Fixed maximum width for visual consistency
        - Connected callback for action handling
        - Standard appearance across all script items
        
        Args:
            label: Text to display on the button
            callback: Function to call when button is clicked
            
        Returns:
            QPushButton: Configured button ready to be added to the UI
        """
        button = QPushButton(label)
        button.setMaximumWidth(100)
        button.clicked.connect(callback)
        return button

