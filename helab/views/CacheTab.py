"""Settings → Cache: what the disk cache holds, clearing and purging it, and both budgets.

The GUI never opens the store: the numbers come from a ``cache_admin inventory`` helper job
(``FolderCache.cache_admin``), and every Clear or Remove is another such job. Memory numbers
come from ``FolderCache``. See roadmaps/cache-storage-and-settings.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
import re
import time
from typing import Any, Callable, Mapping

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QValidator
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from helab.analysis.budget_core import RELEASE_SHARE
from helab.utils.accessible import identify, identify_buttons
from helab.utils.cache_store import KINDS, purge_estimate, results_purge_estimate, trim_estimate
from helab.utils.constants import (
    DISK_BUDGET_SETTING, LIVE_AUTOSAVE_SETTING, PLOT_AUTO_RELOAD_SETTING, MAX_LIVE_AUTOSAVE, MIN_DISK_BUDGET, RAM_BUDGET_SETTING, RAM_STEPS,
    read_disk_budget, cache_dir_refused, read_live_autosave, read_plot_auto_reload, read_ram_budget_steps, ram_step_bytes, ram_step_range,
    total_ram,
)
from helab.utils import file_manager, folder_cache
from helab.utils.folder_cache import FolderCache
from helab.utils.number_format import byte_size, byte_unit
from helab.utils.settings_defaults import CACHE_POLICY_SETTING, RESULT_REUSE_SETTING, read_setting
from helab.utils.time_format import relative_age
from helab.views.ElidedLabel import ElidedLabel
from helab.views.gaps import COLUMN_GAP, ROW_SPACING

DAY = 86400.0
# The narrowest a purge row's name gets before it wraps, in characters.
PURGE_NAME_CHARS = 28
DEFAULT_PURGE_DAYS = 90
# The rows of the disk cache, by record kind: label and button.
# The cache policy's choices (caching v2, Q45.1), in the words S~6 proposed (Tony to confirm).
POLICY_LABELS = (("raw+used", "Raw + what you load (default)"), ("raw", "Raw only, convert on load"),
                 ("txy", "TXY only (no raw)"))


def remove_raw_following_text(following: Mapping[str, Any]) -> str:
    """S4~1's question for Settings' policy (Tony's wording, 2026-11-02): every folder that follows it now keeps
    no raw pulses; remove HeLab's cached copy of theirs? ``following``: the inventory's ``raw.following``, what
    ``remove_raw_following`` removes (S4-1)."""
    only = int(following.get("only_copy") or 0)
    folders = int(following.get("folders") or 0)
    return ("Folders that follow this setting keep no raw pulses from now on. Also remove HeLab's cached copy of "
            f"their raw pulses ({plural(folders, 'folder')}, {byte_size(int(following.get('bytes') or 0), 'disk')})? "
            "Your d files aren't touched. Folders with their own cache policy keep theirs."
            + (f"\n\nRaw pulses of {plural(only, 'shot')} are the only copy: their raw files are gone from their "
               "folders, so they can't be read again." if only else ""))


# What Settings says when it couldn't offer that (S4-3: busy, or the cache not checked yet).
RAW_KEPT_MESSAGE = "Cached raw pulses kept: Clear raw pulses removes them"


def _only_copies(txy: Mapping[str, Any] | None, raw: Mapping[str, Any] | None) -> str:
    """The sentence a question that removes store-v4's TXY data or raw pulses (Clear, Clear all) gives their only
    copies (Q22.6, C2-9: never removed unnamed), or "" when there are none."""
    parts: list[str] = []
    folders = int((txy or {}).get("only_copy_folders") or 0)
    if folders:
        parts.append(f"TXY data of {folders} folder{'' if folders == 1 else 's'}")
    shots = int((raw or {}).get("only_copy") or 0)
    if shots:
        parts.append(f"HeLab's cached raw pulses of {shots} shot{'' if shots == 1 else 's'}")
    if not parts:
        return ""
    return (f"Some of it is the only copy ({' and '.join(parts)}): their files are gone from their folders, so "
            "it can't be read again.")


# The purges by age (A47.4), as their controls' accessible names say them.
PURGE_NAMES = {"datasets": "cached data", "txy": "TXY data", "raw": "HeLab's cached raw pulses",
               "records": "folder records", "results": "cached analysis", "all": "everything"}
# What a purge of TXY data or raw pulses leaves, for its question (Tony, 2026-11-02: name the raw pulses as
# HeLab's cached copy, and say the d files aren't touched).
PURGE_TEXT = {
    "txy": "Loaded data stays open; the next load of each folder caches its TXY again. TXY files are never touched.",
    "raw": "Your d files aren't touched: their pulses are cached again from them after the next load of each folder.",
}
ONLY_COPIES_STAY = "Only copies stay (Make room names them)."


@dataclass(frozen=True)
class Everything:
    """What Remove everything old takes by one cutoff, by part (A47.4)."""
    datasets: dict[str, int]
    txy: dict[str, int] | None
    raw: dict[str, int] | None
    records: int
    record_kinds: dict[str, int]
    results: dict[str, int]

    @property
    def bytes(self) -> int:
        return (self.datasets["bytes"] + (self.txy or {}).get("bytes", 0) + (self.raw or {}).get("bytes", 0)
                + self.results["bytes"])

    @property
    def any(self) -> bool:
        return bool(self.datasets["datasets"] or (self.txy or {}).get("txy_folders") or
                    (self.raw or {}).get("raw_folders") or self.records or self.results["results"])


def everything(inventory: Mapping[str, Any], cutoff: float, include_failures: bool) -> Everything:
    """Each part of Remove everything old, from the same estimates as each part's own purge."""
    v4 = "txy" in inventory["ages"]
    records = purge_estimate(inventory, cutoff, datasets=False, include_failures=include_failures)
    return Everything(
        datasets=purge_estimate(inventory, cutoff, datasets=True, kinds=("datasets",)),
        txy=purge_estimate(inventory, cutoff, datasets=True, kinds=("txy",)) if v4 else None,
        raw=purge_estimate(inventory, cutoff, datasets=True, kinds=("raw",)) if v4 else None,
        records=sum(records.values()), record_kinds=records,
        results=results_purge_estimate(inventory, cutoff))


def everything_text(inventory: Mapping[str, Any], cutoff: float, days: int, include_failures: bool) -> str:
    """Remove everything old's question: every part with its size (CoCo: cached analysis named as the user's
    results; scan failures only with the box), and what stays."""
    parts = everything(inventory, cutoff, include_failures)
    lines = [f"• cached data for {plural(parts.datasets['datasets'], 'folder')} "
             f"({byte_size(parts.datasets['bytes'], 'disk')})"]
    if parts.txy is not None:
        lines.append(f"• TXY data for {plural(parts.txy.get('txy_folders', 0), 'folder')} "
                     f"({byte_size(parts.txy['bytes'], 'disk')})")
    if parts.raw is not None:
        lines.append(f"• HeLab's cached raw pulses for {plural(parts.raw.get('raw_folders', 0), 'folder')} "
                     f"({byte_size(parts.raw['bytes'], 'disk')}); your d files aren't touched")
    lines.append(f"• {plural(parts.records, 'folder record')} not checked since: summaries, subfolder status, "
                 "listings and scan histories" + ("" if include_failures else " (scan failures are kept)"))
    lines.append(f"• cached analysis: {plural(parts.results['results'], 'saved result')} of your plots "
                 f"({byte_size(parts.results['bytes'], 'disk')}) not shown since")
    stays = ("Automatic checks will try folders whose scan failed again." if include_failures else
             "Automatic checks still skip folders whose scan failed.")
    return (f"Removes everything not used, checked or shown in the last {plural(days, 'day')} "
            f"({byte_size(parts.bytes, 'disk')}):\n" + "\n".join(lines) + "\n\n"
            f"Loaded data and plots shown now stay open. {stays} Raw files and TXY files are never touched."
            + (f" {ONLY_COPIES_STAY}" if parts.txy is not None else "") + " Presets are kept.")


KIND_ROWS = {"datasets": ("Cached data", "Clear…"), "summaries": ("Folder summaries", "Clear…"),
             "histories": ("Scan failures", "Forget…"), "subtrees": ("Subfolder status", "Clear…"),
             "listings": ("Folder listings", "Clear…")}
# What a Clear of each kind loses and keeps, for its confirmation.
CLEAR_TEXT = {
    "datasets": "Loaded data stays open; the next load of each folder reads its TXY files again.",
    "summaries": "Folders show their counts and status again after their next check.",
    "histories": "Automatic checks will try these folders again.",
    "subtrees": "Each folder's status from its subfolders is derived again when it is listed.",
    "listings": "Browsing offline can't show these folders' subfolders until they are listed again.",
}
# Saved analysis results (result caching R2): apart from the kinds above (Clear all keeps them).
RESULTS_LABEL = "Cached analysis"
RESULTS_TEXT = ("Plots shown now stay as they are; the next run of each plot computes again. Cached data, "
                "folder records and exported files are kept.")
# HeLab's converted TXY (Q27.5): where they are, and what each folder holds (the row's tooltip).
CONVERTED_TIP = ("TXY files HeLab converted from raw files, in the cache and temp folders' converted-txy folders, "
                 "with HeLab's index of what made them. They don't count toward the budget, and nothing removes "
                 "them but this Clear, which keeps the index (counted here; a Clear gives back the space of the "
                 "rows it removes) and the records of TXY written beside the raw files (those TXY aren't here).")
CONVERTED_BASES = {"cache": "Cache folder", "temp": "Temp folder"}


def converted_used(usage: dict[str, Any]) -> str:
    """`` · last used 2h ago`` once a conversion or load has used one of the folders, else ""."""
    last_used = usage.get("last_used")
    return f" · last used {relative_age(time.time() - float(last_used))}" if last_used else ""


def read_result_reuse(settings: QSettings) -> bool:
    return bool(read_setting(settings, RESULT_REUSE_SETTING, typed=True))


def plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


class RamBudgetSpinBox(QSpinBox):
    """The RAM budget in steps of 1/128 of RAM, shown as e.g. "16.0 GiB (1/8 of 128 GiB)".
    A typed size in GiB snaps to the nearest step."""

    def __init__(self, total: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.total = total
        self.step = ram_step_bytes(total)
        self.setRange(*ram_step_range(total))

    def textFromValue(self, v: int) -> str:
        share = Fraction(v, RAM_STEPS)
        return f"{byte_size(v * self.step, 'ram')} ({share.numerator}/{share.denominator} of {byte_size(self.total, 'ram')})"

    def valueFromText(self, text: str | None) -> int:
        match = re.match(r"\s*(\d*\.?\d+)", text or "")
        if match is None:
            return self.value()
        return max(self.minimum(), min(self.maximum(), round(float(match.group(1)) * byte_unit(3, "ram")[0] / self.step)))

    def validate(self, input: str | None, pos: int) -> tuple[QValidator.State, str, int]:
        text = input or ""
        state = (QValidator.State.Acceptable if re.match(r"\s*\d*\.?\d+", text)
                 else QValidator.State.Intermediate)
        return state, text, pos


class CacheTab(QWidget):
    """Rows of the disk cache by kind, purges by age, and the disk and RAM budgets.

    Buttons are disabled while a job runs and until the inventory arrives. Every Clear
    or Remove asks first, saying what is lost and what stays (``confirm``, replaceable
    in tests). The budgets are saved with the Settings dialog (``save``).
    """

    # The store recorded a changed disk budget (True), or couldn't (False): Settings saves only then.
    budgetApplied = pyqtSignal(bool)

    def __init__(self, cache: FolderCache | None, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.settings = settings
        self.enabled = bool(cache is not None and folder_cache.store_options())
        self.inventory: dict[str, Any] | None = None
        self._inventory_owner = ""
        self._job = ""
        self._job_label = ""
        self._budget_job = ""
        # The disk budget the store has recorded (``apply_budget``): the only one Save writes.
        self._acknowledged: int | None = None
        self._applying_budget = 0
        # The budget job found more cached than the lowered budget allows (its usage).
        self._too_full: int | None = None
        # store-v4: lowering the budget asks from the helper's plan (``trim`` ``plan_only``, S2-1): the budget
        # being planned for, and the plan when it came.
        self._planning: int | None = None
        self._trim_plan: dict[str, Any] | None = None
        self.message = ""
        self.confirm: Callable[[str, str, str], bool] = self._confirm

        # The rows scroll when the Settings window is shorter than they are, so a short window never squeezes
        # them (buttons and the policy box cut off, Tony 2026-11-04).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.scroll_area.setWidget(content)
        viewport = self.scroll_area.viewport()
        if viewport is not None:
            viewport.setAutoFillBackground(False)
        content.setAutoFillBackground(False)
        outer.addWidget(self.scroll_area)
        layout = QVBoxLayout(content)
        layout.setSpacing(ROW_SPACING)
        layout.addWidget(self._heading("Disk cache"))
        location = self._row()
        # Elided in the middle (the full path in its tooltip), so a long path never widens the tab past the window.
        self.location_label = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.location_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.addWidget(self.location_label, 1)
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(lambda: file_manager.show(str(folder_cache.store_options().get("directory", ""))))
        location.addWidget(self.open_button)
        self.show_location(refresh=False)
        layout.addLayout(location)
        if cache_dir_refused():
            refused = QLabel(cache_dir_refused())
            refused.setWordWrap(True)
            layout.addWidget(refused)

        usage = self._row()
        self.usage_label = QLabel("Checking…")
        usage.addWidget(self.usage_label)
        self.usage_bar = QProgressBar()
        self.usage_bar.setRange(0, 1000)
        self.usage_bar.setTextVisible(False)
        self.usage_bar.setMaximumHeight(self.usage_label.fontMetrics().height())
        usage.addWidget(self.usage_bar, 1)
        usage.addWidget(QLabel("Budget"))
        # In the OS's disk units, GB or GiB on Windows (Q26.1), typed in steps of half a unit.
        self.disk_unit, unit = byte_unit(3, "disk")
        self._shown_budget = (-1.0, 0)  # (``show_disk_budget``)
        self.disk_budget = QDoubleSpinBox()
        self.disk_budget.setRange(MIN_DISK_BUDGET / self.disk_unit, 1 << 20)
        self.disk_budget.setDecimals(1)
        self.disk_budget.setSingleStep(0.5)
        self.disk_budget.setSuffix(f" {unit}")
        self.show_disk_budget(read_disk_budget(settings))
        self.disk_budget.valueChanged.connect(self._snap_disk_budget)
        self.disk_budget.setToolTip(
            "Counts live data: cached datasets, cached analysis and the records database. Removed files waiting out their "
            "10-minute grace period don't count. Nothing is removed to make room without asking. At 80%, "
            "automatic loads of folders without cached data pause.")
        usage.addWidget(self.disk_budget)
        layout.addLayout(usage)

        grid = QGridLayout()
        grid.setVerticalSpacing(0)
        grid.setHorizontalSpacing(COLUMN_GAP)
        grid.setColumnStretch(1, 1)
        self.kind_labels: dict[str, QLabel] = {}
        self.kind_buttons: dict[str, QPushButton] = {}
        for row, (kind, (label, button_text)) in enumerate(KIND_ROWS.items()):
            grid.addWidget(QLabel(label), row, 0)
            self.kind_labels[kind] = QLabel("Checking…")
            grid.addWidget(self.kind_labels[kind], row, 1)
            button = QPushButton(button_text)
            button.clicked.connect(lambda checked=False, k=kind: self.clear([k]))
            self.kind_buttons[kind] = button
            grid.addWidget(button, row, 2)
        self.kind_labels["listings"].setToolTip(
            "Each listed folder's subfolder names and counts (below data roots), for browsing cached folders "
            "when their drive or share isn't there.")
        # Saved analysis results (R2): their own Clear, not part of Clear all.
        row = len(KIND_ROWS)
        grid.addWidget(QLabel(RESULTS_LABEL), row, 0)
        self.results_label = QLabel("Checking…")
        self.results_label.setToolTip("Results of costly plots (Correlations, Release time…), reused when a plot "
                                      "runs again with the same data, script and settings. They count toward the "
                                      "budget; Clear all keeps them.")
        grid.addWidget(self.results_label, row, 1)
        self.results_button = QPushButton("Clear…")
        self.results_button.clicked.connect(self.clear_results)
        grid.addWidget(self.results_button, row, 2)
        # Caching v2 (store-v4, the switch on): raw pulses, and an older HeLab's store-v3 beside it.
        self.raw_name = QLabel("Raw pulses")
        self.raw_label = QLabel("")
        self.raw_label.setToolTip("Each raw file's pulses, kept so any converter profile can make its TXY without "
                                  "reading the folder again. Filled in the background after a folder's data is "
                                  "cached. Only copies: raw files gone from their folders since.")
        self.raw_button = QPushButton("Clear…")
        self.raw_button.clicked.connect(self.clear_raw)
        grid.addWidget(self.raw_name, row + 1, 0)
        grid.addWidget(self.raw_label, row + 1, 1)
        grid.addWidget(self.raw_button, row + 1, 2)
        # Caching v2 stage 2: TXY data in layers (MATLAB's, and one per HeLab profile), and what new saves keep.
        self.txy_name = QLabel("TXY data")
        self.txy_label = QLabel("")
        self.txy_label.setToolTip("Each folder's cached TXY: External (MATLAB converter), and HeLab's of each "
                                  "converter profile used, each shot kept once whichever TXY source a tab or plot shows. Only copies: their TXY "
                                  "files are gone from their folders since.")
        self.txy_button = QPushButton("Clear…")
        self.txy_button.clicked.connect(self.clear_txy)
        grid.addWidget(self.txy_name, row + 2, 0)
        grid.addWidget(self.txy_label, row + 2, 1)
        grid.addWidget(self.txy_button, row + 2, 2)
        self.policy_name = QLabel("Cache policy")
        self.policy_combo = QComboBox()
        for data, text in POLICY_LABELS:
            self.policy_combo.addItem(text, data)
        self.policy_combo.setCurrentIndex(max(0, self.policy_combo.findData(
            str(read_setting(settings, CACHE_POLICY_SETTING, typed=True)))))
        self.policy_combo.setToolTip("What new saves keep, for every folder that hasn't its own choice. Raw + what you "
                                     "load: raw pulses and each TXY a tab or plot uses. Raw only: TXY are made from "
                                     "the raw pulses on each load. TXY only: no raw pulses (archives without raw "
                                     "files). Changing it removes nothing.")
        grid.addWidget(self.policy_name, row + 3, 0)
        grid.addWidget(self.policy_combo, row + 3, 1, 1, 2)
        layout.addLayout(grid)
        legacy = self._row()
        self.legacy_name = QLabel("Older cache (store-v3)")
        legacy.addWidget(self.legacy_name)
        self.legacy_label = QLabel("")
        self.legacy_label.setToolTip("An older HeLab's disk cache in this cache folder. Kept: HeLab reads its records "
                                     "and saved analysis where the new cache has none, and it counts toward the "
                                     "budget. Ignored: left on disk, unused.")
        legacy.addWidget(self.legacy_label, 1)
        self.legacy_choice_button = QPushButton("Ignore it")
        self.legacy_choice_button.clicked.connect(self.toggle_legacy)
        legacy.addWidget(self.legacy_choice_button)
        self.legacy_clear_button = QPushButton("Clear…")
        self.legacy_clear_button.clicked.connect(self.clear_legacy)
        legacy.addWidget(self.legacy_clear_button)
        layout.addLayout(legacy)
        self.result_reuse = QCheckBox("Reuse saved analysis results")
        self.result_reuse.setChecked(read_result_reuse(settings))
        self.result_reuse.setToolTip(
            "On: a costly plot (Correlations, Release time) shows its result saved for the same data, script and "
            "settings at once instead of computing it again, and saves new ones; its source line says so. Off: "
            "plots compute every run and save nothing (saved results stay until cleared).")

        # One row: the reuse switch, when the inventory was checked, Refresh and Clear all.
        footer = self._row()
        footer.addWidget(self.result_reuse)
        self.checked_label = QLabel("Checking…")
        footer.addWidget(self.checked_label, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        footer.addWidget(self.refresh_button)
        self.clear_all_button = QPushButton("Clear all…")
        self.clear_all_button.clicked.connect(lambda: self.clear(list(KINDS)))
        footer.addWidget(self.clear_all_button)
        layout.addLayout(footer)

        # The user's choices (S10): not part of Clear all, never removed to make room.
        prefs = self._row()
        prefs.addWidget(QLabel("Folder preferences"))
        self.prefs_label = QLabel("Checking…")
        self.prefs_label.setToolTip("Folders you chose not to cache, not to auto-load, or to have HeLab's converted "
                                    "TXY written beside their raw files (right-click a folder). Clear all and purges "
                                    "keep them.")
        prefs.addWidget(self.prefs_label, 1)
        self.prefs_button = QPushButton("Clear…")
        self.prefs_button.clicked.connect(self.clear_prefs)
        prefs.addWidget(self.prefs_button)
        layout.addLayout(prefs)

        # HeLab's own TXY under the cache and temp folders (converted-txy/, Q27.5): not in the store, outside
        # the budget, removed only by this Clear (Q12.3), through a helper and each folder's index.
        converted = self._row()
        converted.addWidget(QLabel("HeLab's converted TXY"))
        self.converted_label = QLabel("Checking…")
        self.converted_label.setToolTip(CONVERTED_TIP)
        converted.addWidget(self.converted_label, 1)
        self.converted_button = QPushButton("Clear…")
        self.converted_button.clicked.connect(self.clear_converted)
        converted.addWidget(self.converted_button)
        layout.addLayout(converted)

        # Presets (helab/views/PresetsInspector.py): the user's too, kept by Clear all and purges.
        presets = self._row()
        presets.addWidget(QLabel("Presets"))
        self.presets_label = QLabel()
        self.presets_label.setWordWrap(True)  # (Unwrapped, its summary held the tab past 800 px on Windows.)
        presets.addWidget(self.presets_label, 1)
        self.presets_button = QPushButton("Presets…")
        self.presets_button.setToolTip("The saved presets of plots and of folders with their plots: their values, "
                                       "whether they fit the installed scripts; rename, duplicate or delete one")
        self.presets_button.clicked.connect(self.show_presets)
        presets.addWidget(self.presets_button)
        layout.addLayout(presets)
        from helab.views.PresetsInspector import show_summary
        self.presets_store = show_summary(self.presets_label, cache)
        self.presets_window: QWidget | None = None

        # Live (roadmaps/live-monitoring.md): new shots wait in RAM, then the folder is saved.
        live = self._row()
        live.addWidget(QLabel("Live: save to the disk cache every"))
        self.live_autosave = QSpinBox()
        self.live_autosave.setRange(1, MAX_LIVE_AUTOSAVE)
        self.live_autosave.setSuffix(" new shots")
        self.live_autosave.setValue(read_live_autosave(settings))
        self.live_autosave.setToolTip(
            "While Live watches a folder, new shots stay in RAM; once this many wait, the folder's cached data "
            "is rewritten in the background (one save at a time), and again when Live stops. A crash or Quit "
            "now loses at most these: the next check reads them from the folder again.")
        live.addWidget(self.live_autosave)
        live.addStretch(1)
        layout.addLayout(live)

        layout.addWidget(self._heading("Remove old entries"))
        purges = QGridLayout()
        purges.setVerticalSpacing(0)
        purges.setHorizontalSpacing(COLUMN_GAP)
        purges.setColumnStretch(0, 3)  # (Names take most of the spare width, so they wrap only when it runs out.)
        purges.setColumnStretch(2, 1)
        # One row per purge by age (A47.4): store-v4 adds TXY data and raw pulses; Everything takes them all.
        self.purge_rows: dict[str, tuple[QLabel, QSpinBox, QLabel, QPushButton]] = {}
        for row, (kind, text, slot) in enumerate((
                ("datasets", "Cached data not used in the last", self.purge_datasets),
                ("txy", "TXY data not used in the last", self.purge_txy),
                ("raw", "HeLab's cached raw pulses not used in the last", self.purge_raw),
                ("records", "Folder records not checked in the last", self.purge_records),
                ("results", "Cached analysis not shown in the last", self.purge_results),
                ("all", "Everything not used, checked or shown in the last", self.purge_all))):
            name, days, estimate, button = QLabel(text), self._days(), QLabel(""), QPushButton("Remove…")
            # A narrow window wraps the longest names instead of widening the tab (Windows: past 800 px).
            name.setWordWrap(True)
            name.setMinimumWidth(name.fontMetrics().horizontalAdvance("x" * PURGE_NAME_CHARS))
            button.clicked.connect(slot)
            self.purge_rows[kind] = (name, days, estimate, button)
            for column, widget in enumerate((name, days, estimate, button)):
                purges.addWidget(widget, row, column)
        _, self.dataset_days, self.dataset_estimate, self.purge_datasets_button = self.purge_rows["datasets"]
        _, self.txy_days, self.txy_estimate, self.purge_txy_button = self.purge_rows["txy"]
        _, self.raw_days, self.raw_estimate, self.purge_raw_button = self.purge_rows["raw"]
        _, self.record_days, self.record_estimate, self.purge_records_button = self.purge_rows["records"]
        _, self.result_days, self.result_estimate, self.purge_results_button = self.purge_rows["results"]
        _, self.all_days, self.all_estimate, self.purge_all_button = self.purge_rows["all"]
        for kind in ("txy", "raw"):
            for widget in self.purge_rows[kind]:
                widget.setVisible(False)  # (store-v4 only: shown with its inventory.)
        layout.addLayout(purges)
        # The box and its note apart, the note wrapping: as one check box's text it held the tab at 900 px on
        # Windows, past Settings' 800 px (CI 41785919415).
        failures_row = self._row()
        self.include_failures = QCheckBox("Include scan failures")
        self.include_failures.toggled.connect(self._show_estimates)
        failures_row.addWidget(self.include_failures)
        failures_note = QLabel("(automatic checks will try those folders again)")
        failures_note.setWordWrap(True)
        failures_note.setBuddy(self.include_failures)
        failures_row.addWidget(failures_note, 1)
        layout.addLayout(failures_row)

        layout.addWidget(self._heading("Memory"))
        memory = self._row()
        memory.addWidget(QLabel("RAM budget"))
        self.ram_budget = RamBudgetSpinBox(total_ram())
        self.ram_budget.setValue(read_ram_budget_steps(settings, self.ram_budget.total))
        self.ram_budget.setToolTip(
            "Loaded folders not shown in a tab are dropped from RAM, least recently used first, until the rest "
            "fit. Plots count too: from 50 % the status bar says so, at 75 % a window lists the biggest plots and "
            f"folders, and above {RELEASE_SHARE:.0%} plots not viewed lately are released (each keeps a picture). "
            "Folders shown in tabs and the shown, running or Live plots are never dropped, so HeLab can use "
            "more than this.")
        memory.addWidget(self.ram_budget)
        self.memory_label = QLabel("")
        memory.addWidget(self.memory_label, 1)
        layout.addLayout(memory)
        self.plot_auto_reload = QCheckBox("Reload a released plot when it is shown again")
        self.plot_auto_reload.setChecked(read_plot_auto_reload(settings))
        self.plot_auto_reload.setToolTip(
            "A plot released to free RAM keeps a picture of itself. On: showing it again (its tab, its window or "
            "its settings) draws it again from RAM or the disk cache, never from its folder. Off: only its "
            "Reload button does.")
        layout.addWidget(self.plot_auto_reload)
        layout.addStretch(1)

        self._identify()
        if cache is not None:
            cache.cacheAdminResult.connect(self._on_result)
            cache.cacheAdminDone.connect(self._on_done)
        self.show_memory()
        self._update()
        self.refresh()

    @staticmethod
    def _row() -> QHBoxLayout:
        """A row of the tab: a name, its value and its buttons, ``COLUMN_GAP`` apart."""
        row = QHBoxLayout()
        row.setSpacing(COLUMN_GAP)
        return row

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _identify(self) -> None:
        """The tab's controls' IDs and names (helab/utils/accessible.py)."""
        identify(self.open_button, "cache_open", "Open cache folder")
        identify(self.disk_budget, "disk_budget", "Disk budget")
        for kind, button in self.kind_buttons.items():
            identify(button, f"cache_clear_{kind}", f"{button.text().rstrip('…')} {KIND_ROWS[kind][0].lower()}…")
        identify(self.results_button, "cache_clear_results", f"Clear {RESULTS_LABEL.lower()}…")
        identify(self.raw_button, "cache_clear_raw", "Clear raw pulses…")
        identify(self.txy_button, "cache_clear_txy", "Clear TXY data…")
        identify(self.policy_combo, "cache_policy", "Cache policy")
        identify(self.legacy_choice_button, "cache_legacy_choice", "Keep using or ignore the older cache")
        identify(self.legacy_clear_button, "cache_clear_legacy", "Clear the older cache…")
        identify(self.result_reuse, "result_reuse")
        identify(self.refresh_button, "cache_refresh", "Refresh cache sizes")
        identify(self.clear_all_button, "cache_clear_all")
        identify(self.prefs_button, "cache_clear_preferences", "Clear folder preferences…")
        identify(self.converted_button, "cache_clear_converted", "Clear HeLab's converted TXY…")
        identify(self.presets_button, "cache_presets")
        identify(self.live_autosave, "live_autosave", "Live: save to the disk cache every")
        for kind, what in PURGE_NAMES.items():
            _, days, _, button = self.purge_rows[kind]
            identify(days, f"purge_{kind}_days", f"Remove {what} older than")
            identify(button, f"purge_{kind}", f"Remove old {what}…")
        identify(self.include_failures, "purge_include_failures",
                 "Include scan failures (automatic checks will try those folders again)")
        identify(self.ram_budget, "ram_budget_setting", "RAM budget")
        identify(self.plot_auto_reload, "plot_auto_reload")

    def _days(self) -> QSpinBox:
        days = QSpinBox()
        days.setRange(1, 3650)
        days.setValue(DEFAULT_PURGE_DAYS)
        days.setSuffix(" days")
        days.valueChanged.connect(self._show_estimates)
        return days

    def show_location(self, *, refresh: bool = True) -> None:
        """Where the disk cache is now (it can move while Settings is open)."""
        root = str(folder_cache.store_options().get("directory", ""))
        self.location_label.setText(root or "Off for this session")
        self.location_label.setToolTip("\n".join(filter(None, (
            root, cache_dir_refused(), "Move it with Change… on the General tab."))))
        self.open_button.setEnabled(bool(root))
        if refresh:
            self.refresh()

    def detach(self) -> None:
        """Stop listening to the cache (the dialog is closing)."""
        if self.cache is not None:
            self.cache.cacheAdminResult.disconnect(self._on_result)
            self.cache.cacheAdminDone.disconnect(self._on_done)
            self.cache = None

    def _confirm(self, title: str, text: str, verb: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Warning, title, text, parent=self)
        accept = box.addButton(verb, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        identify_buttons(box, "cache_confirm")
        box.exec()
        return box.clickedButton() is accept

    @property
    def busy(self) -> bool:
        return bool(self._job or self._budget_job)

    @property
    def applying(self) -> bool:
        """A changed disk budget is on its way to the store; Settings hasn't saved it yet."""
        return bool(self._budget_job)

    def refresh(self) -> None:
        """Ask a helper for the inventory; the tab shows Checking… until it arrives."""
        if self.cache is None or not self.enabled or self._inventory_owner:
            return
        self._inventory_owner = self.cache.cache_admin("inventory")
        if not self._inventory_owner:
            self.message = "Disk cache queue full — Refresh to try again"
        self._update()

    def _run(self, label: str, action: str, **params: Any) -> None:
        if self.cache is None:
            return
        self._job = self.cache.cache_admin(action, **params)
        self._job_label = label
        self.message = "" if self._job else "Disk cache queue full — try again"
        self._update()

    def _on_result(self, action: str, event: dict[str, Any]) -> None:
        if action == "trim" and self._planning is not None and event.get("kind") == "admin_result" and "items" in event:
            self._trim_plan = event  # (What lowering the budget would remove, only copies named.)
        if (action == "budget" and self._budget_job and event.get("kind") == "admin_result"
                and event.get("recorded") is False):
            self._too_full = int(event.get("usage") or 0)  # The data cached by now doesn't fit.
        if action == "inventory" and event.get("kind") == "inventory":
            self.inventory = event["inventory"]
            self._update()

    def _on_done(self, owner: str, action: str, message: str) -> None:
        if owner == self._inventory_owner:
            self._inventory_owner = ""
            if message:
                self.message = f"Could not read the disk cache: {message}"
        elif owner == self._budget_job and self._planning is not None:
            # store-v4: the plan came; ask from it, and lower the budget removing exactly what it named (S2-1).
            self._budget_job = ""
            budget, plan, self._planning, self._trim_plan = self._planning, self._trim_plan, None, None
            if not message and plan is not None and self._ask_trim(budget, None, None, plan.get("room")):
                self._send_budget("trim", budget, plan=list(plan["items"]))
                if self._budget_job:
                    return
            elif message:
                self.message = f"Changing the disk budget failed: {message} — nothing saved"
            else:
                self.message = "Budget not lowered — nothing saved"
            self.budgetApplied.emit(False)
            self.refresh()
        elif owner == self._budget_job:
            self._budget_job = ""
            too_full, self._too_full = self._too_full, None
            if not message and too_full is not None:
                # More was cached since the tab looked: it needs a trim, so ask now.
                self.message = ""
                if self._ask_trim(self._applying_budget, None, too_full):
                    self._send_budget("trim", self._applying_budget)
                    if self._budget_job:
                        return
                else:
                    self.message = "Budget not lowered — nothing saved"
                self.budgetApplied.emit(False)
            elif message:
                # It may have been recorded before failing: the budget in effect is set again.
                if self.cache is not None:
                    self.cache.restore_budget()
                self.message = f"Changing the disk budget failed: {message} — nothing saved"
                self.budgetApplied.emit(False)
            else:
                self._acknowledged = self._applying_budget
                self.message = ""
                self.budgetApplied.emit(True)
            self.refresh()
        elif owner == self._job:
            self._job = ""
            self.message = f"{self._job_label} failed: {message}" if message else ""
            self.refresh()  # Show what is left.
        else:
            return
        self._update()

    def show_presets(self) -> None:
        """Presets…: the presets window (one at a time)."""
        from helab.views.PresetsInspector import open_inspector
        self.presets_window = open_inspector(self.presets_store, self, self.presets_window)

    def clear_prefs(self) -> None:
        inventory = self.inventory
        if inventory is None or self.busy:
            return
        prefs = inventory.get("prefs") or {}
        if not self.confirm("Clear folder preferences?",
                            f"Forgets your choices: {plural(int(prefs.get('no_cache', 0)), 'folder')} not cached, "
                            f"{plural(int(prefs.get('no_auto_load', 0)), 'folder')} not auto-loaded and "
                            f"{plural(int(prefs.get('write_beside', 0)), 'folder')} with HeLab's TXY written beside "
                            "their raw files. Those folders are cached and auto-loaded again, and HeLab's TXY of them "
                            "go to the cache or temp folder. Cached data, and TXY already written, are kept.", "Clear"):
            return
        self._run("Clear folder preferences", "clear_prefs")

    def clear_converted(self) -> None:
        """Clear HeLab's converted TXY under the cache and temp folders (asks first)."""
        inventory = self.inventory
        if inventory is None or self.busy:
            return
        converted = inventory.get("converted_txy") or {"files": 0, "bytes": 0}
        files, size = int(converted["files"]), byte_size(int(converted.get("clearable_bytes") or 0), "disk")
        # (No TXY left, only old builds' records or a damaged index set aside: say those.)
        what = (f"{plural(files, 'TXY file')} HeLab converted, with their records ({size})" if files
                else f"what is left of HeLab's converted TXY: old records and damaged indexes ({size})")
        if not self.confirm("Clear HeLab's converted TXY?",
                            f"Removes {what}, from the cache and temp folders; HeLab's index of what made them "
                            "stays. Raw files, External TXY (MATLAB converter) and HeLab's TXY written beside raw files "
                            "are kept. Data loaded stays open; plots on HeLab's TXY keep what they show, and shots are converted "
                            "again when converting is on.", "Clear"):
            return
        self._run("Clear HeLab's converted TXY", "clear_converted_txy")

    def clear(self, kinds: list[str]) -> None:
        inventory = self.inventory
        if inventory is None or self.busy:
            return
        if set(kinds) >= set(KINDS):
            raw = inventory.get("raw")
            txy = inventory.get("txy")
            title = "Clear the disk cache?"
            text = (f"Removes everything in the disk cache: cached data for "
                    f"{plural(inventory['datasets']['count'], 'folder')} ({byte_size(inventory['datasets']['bytes'], 'disk')}),"
                    + (f" TXY data for {plural(int(txy['folders']), 'folder')} ({byte_size(int(txy['bytes']), 'disk')}),"
                       if txy else "")
                    + (f" HeLab's cached raw pulses for {plural(int(raw['folders']), 'folder')} "
                       f"({byte_size(int(raw['bytes']), 'disk')}; your d files aren't touched)," if raw else "")
                    + " folder summaries, scan failures, subfolder status and folder listings.\n\n"
                    "Loaded data stays open. Automatic checks will try failed folders again. Cached analysis "
                    "stays (its own Clear).")
            only = _only_copies(txy, raw)
            if only:
                text += f"\n\n{only}"
            verb, label = "Clear all", "Clear all"
            # (store-v4: its raw pulses and TXY data too.)
            kinds = [*KINDS, *(["raw"] if raw is not None else []), *(["txy"] if txy is not None else [])]
        else:
            kind = kinds[0]
            name = KIND_ROWS[kind][0]
            count = (inventory["histories"]["blocked"] if kind == "histories"
                     else (inventory.get(kind) or {"count": 0})["count"])
            size = f" ({byte_size(inventory['datasets']['bytes'], 'disk')})" if kind == "datasets" else ""
            verb = "Forget" if kind == "histories" else "Clear"
            title = f"{verb} {name.lower()}?"
            text = f"{verb}s {name.lower()} for {plural(count, 'folder')}{size}.\n\n{CLEAR_TEXT[kind]}"
            label = f"{verb} {name.lower()}"
        if self.confirm(title, text, verb):
            self._run(label, "clear", kinds=list(kinds))

    def clear_raw(self) -> None:
        """Clear raw pulses (store-v4): every folder's, only copies included, after asking."""
        inventory = self.inventory
        raw = (inventory or {}).get("raw")
        if inventory is None or self.busy or not raw:
            return
        only = int(raw.get("only_copy") or 0)
        text = (f"Removes HeLab's cached raw pulses of {plural(int(raw['folders']), 'folder')} "
                f"({byte_size(int(raw['bytes']), 'disk')}). Your d files aren't touched: their pulses are cached "
                "again from them after the next load of each folder."
                + (f"\n\n{plural(only, 'shot')} are the only copy: their raw files are gone from their folders, so "
                   "these can't be read again." if only else ""))
        if self.confirm("Clear HeLab's cached raw pulses?", text, "Clear"):
            self._run("Clear raw pulses", "clear_raw")

    def clear_txy(self) -> None:
        """Clear TXY data (store-v4): every folder's layers, only copies included, after asking."""
        inventory = self.inventory
        txy = (inventory or {}).get("txy")
        if inventory is None or self.busy or not txy:
            return
        only = _only_copies(txy, None)
        text = (f"Removes the cached TXY data of {plural(int(txy['folders']), 'folder')} "
                f"({byte_size(int(txy['bytes']), 'disk')}). It is cached again at the next load of each folder."
                + (f"\n\n{only}" if only else ""))
        if self.confirm("Clear TXY data?", text, "Clear"):
            self._run("Clear TXY data", "clear_txy")

    def toggle_legacy(self) -> None:
        """Keep using the older store-v3, or ignore it (store-v4)."""
        legacy = (self.inventory or {}).get("legacy") or {}
        if self.busy or not legacy.get("present"):
            return
        choice = "keep" if legacy.get("choice") == "ignore" else "ignore"
        self._run("Keep using the older cache" if choice == "keep" else "Ignore the older cache", "legacy_choice",
                  choice=choice)

    def clear_legacy(self) -> None:
        """The Older cache row's Clear… (as Make room's Clear old stores…, Q28.5): store-v3 goes, after asking with its size, while no other HeLab runs."""
        from helab.utils.cache_locks import other_instances
        from helab.utils.constants import app_folder
        from helab.views.CacheDialogs import legacy_clear_text, legacy_clearable
        legacy = (self.inventory or {}).get("legacy") or {}
        if self.busy or not legacy_clearable(legacy):
            return
        if other_instances(app_folder()):
            self.message = "A HeLab converter (helab convert) is running. Stop it before clearing the older cache."
            self._update()
            return
        if self.confirm("Clear the older cache?", legacy_clear_text(legacy), "Remove"):
            self._run("Clear the older cache", "clear_legacy")

    def clear_results(self) -> None:
        """Clear cached analysis: every saved result, nothing else (asks first)."""
        inventory = self.inventory
        if inventory is None or self.busy:
            return
        results = inventory.get("results") or {"count": 0, "bytes": 0}
        if self.confirm("Clear cached analysis?",
                        f"Removes {plural(int(results['count']), 'saved result')} ({byte_size(int(results['bytes']), 'disk')})"
                        f".\n\n{RESULTS_TEXT}", "Clear"):
            self._run("Clear cached analysis", "clear_results")

    def purge_results(self) -> None:
        if self.inventory is None or self.busy:
            return
        days = self.result_days.value()
        cutoff = time.time() - days * DAY
        estimate = results_purge_estimate(self.inventory, cutoff)
        if self.confirm("Remove old cached analysis?",
                        f"Removes {plural(estimate['results'], 'saved result')} ({byte_size(estimate['bytes'], 'disk')}) "
                        f"not shown in the last {plural(days, 'day')}.\n\n{RESULTS_TEXT}", "Remove"):
            self._run("Remove old cached analysis", "purge", what="results", cutoff=cutoff)

    def _purge_cutoff(self, days: QSpinBox) -> tuple[int, float] | None:
        """A purge's days and cutoff, or None while there is nothing to ask from (no inventory, or busy)."""
        if self.inventory is None or self.busy:
            return None
        return days.value(), time.time() - days.value() * DAY

    def purge_datasets(self) -> None:
        if (asked := self._purge_cutoff(self.dataset_days)) is None or self.inventory is None:
            return
        days, cutoff = asked
        estimate = purge_estimate(self.inventory, cutoff, datasets=True, kinds=("datasets",))
        if self.confirm("Remove old cached data?",
                        f"Removes cached data for {plural(estimate['datasets'], 'folder')} "
                        f"({byte_size(estimate['bytes'], 'disk')}) not used in the last {plural(days, 'day')}.\n\n"
                        f"{CLEAR_TEXT['datasets']} TXY files are never touched.", "Remove"):
            self._run("Remove old cached data", "purge", what="datasets", cutoff=cutoff)

    def purge_txy(self) -> None:
        """Remove TXY data (store-v4's layers and their views) not used since the cutoff; only copies stay."""
        if (asked := self._purge_cutoff(self.txy_days)) is None or self.inventory is None:
            return
        days, cutoff = asked
        estimate = purge_estimate(self.inventory, cutoff, datasets=True, kinds=("txy",))
        if self.confirm("Remove old TXY data?",
                        f"Removes the cached TXY data of {plural(estimate.get('txy_folders', 0), 'folder')} "
                        f"({byte_size(estimate['bytes'], 'disk')}) not used in the last {plural(days, 'day')}.\n\n"
                        f"{PURGE_TEXT['txy']} {ONLY_COPIES_STAY}", "Remove"):
            self._run("Remove old TXY data", "purge", what="txy", cutoff=cutoff)

    def purge_raw(self) -> None:
        """Remove HeLab's cached raw pulses (store-v4's raw layers) not used since the cutoff; only copies stay."""
        if (asked := self._purge_cutoff(self.raw_days)) is None or self.inventory is None:
            return
        days, cutoff = asked
        estimate = purge_estimate(self.inventory, cutoff, datasets=True, kinds=("raw",))
        if self.confirm("Remove old cached raw pulses?",
                        f"Removes HeLab's cached raw pulses of {plural(estimate.get('raw_folders', 0), 'folder')} "
                        f"({byte_size(estimate['bytes'], 'disk')}) not used in the last {plural(days, 'day')}.\n\n"
                        f"{PURGE_TEXT['raw']} {ONLY_COPIES_STAY}", "Remove"):
            self._run("Remove old cached raw pulses", "purge", what="raw", cutoff=cutoff)

    def purge_all(self) -> None:
        """Everything by age (A47.4): every kind of cached data, folder records (scan failures only with the box)
        and cached analysis, each part named with its size; only copies stay."""
        if (asked := self._purge_cutoff(self.all_days)) is None or self.inventory is None:
            return
        days, cutoff = asked
        failures = self.include_failures.isChecked()
        if self.confirm("Remove everything old?", everything_text(self.inventory, cutoff, days, failures), "Remove"):
            self._run("Remove everything old", "purge", what="all", cutoff=cutoff, include_failures=failures)

    def purge_records(self) -> None:
        if self.inventory is None or self.busy:
            return
        days = self.record_days.value()
        cutoff = time.time() - days * DAY
        failures = self.include_failures.isChecked()
        estimate = purge_estimate(self.inventory, cutoff, datasets=False, include_failures=failures)
        stays = ("Automatic checks will try folders whose scan failed again." if failures else
                 "Scan failures are kept, so automatic checks still skip those folders.")
        if self.confirm("Remove old folder records?",
                        f"Removes {plural(sum(estimate.values()), 'folder record')} not checked in the last "
                        f"{plural(days, 'day')}: summaries, subfolder status, listings and scan histories.\n\n"
                        f"Cached data stays. {stays}", "Remove"):
            self._run("Remove old folder records", "purge", what="records", cutoff=cutoff,
                      include_failures=failures)

    def show_memory(self) -> None:
        if self.cache is None:
            self.memory_label.setText("")
            return
        count, total, shown = self.cache.memory_usage()
        plots = self.cache.plot_bytes()
        self.memory_label.setText(f"In use: {plural(count, 'folder')} · {byte_size(total, 'ram')} "
                                  f"({byte_size(shown, 'ram')} shown in tabs)"
                                  + (f" · plots {byte_size(plots, 'ram')} more" if plots else ""))

    def _show_estimates(self) -> None:
        inventory = self.inventory
        if inventory is None:
            for _, _, label, button in self.purge_rows.values():
                label.setText("")
                label.setToolTip("")
                button.setEnabled(False)
            return
        now = time.time()
        v4 = "txy" in inventory["ages"]
        for kind in ("txy", "raw"):
            for widget in self.purge_rows[kind]:
                widget.setVisible(v4)
        writable = not inventory.get("read_only") and not self.busy
        for kind, folders in (("datasets", "datasets"), ("txy", "txy_folders"), ("raw", "raw_folders")):
            _, days, label, button = self.purge_rows[kind]
            found = purge_estimate(inventory, now - days.value() * DAY, datasets=True, kinds=(kind,))
            label.setText(f"— frees ~{byte_size(found['bytes'], 'disk')} ({plural(found.get(folders, 0), 'folder')})")
            button.setEnabled(writable and found.get(folders, 0) > 0)
        records = purge_estimate(inventory, now - self.record_days.value() * DAY, datasets=False,
                                 include_failures=self.include_failures.isChecked())
        self.record_estimate.setText(f"— {plural(sum(records.values()), 'record')}")
        self.record_estimate.setToolTip(f"{plural(records['summaries'], 'folder summary')} · "
                                        f"{plural(records['subtrees'], 'subfolder status')} · "
                                        f"{plural(records['listings'], 'folder listing')} · "
                                        f"{plural(records['histories'], 'scan history')}")
        results = results_purge_estimate(inventory, now - self.result_days.value() * DAY)
        self.result_estimate.setText(f"— frees ~{byte_size(results['bytes'], 'disk')} "
                                     f"({plural(results['results'], 'result')})")
        parts = everything(inventory, now - self.all_days.value() * DAY, self.include_failures.isChecked())
        self.all_estimate.setText(f"— frees ~{byte_size(parts.bytes, 'disk')}"
                                  + (f" (+{plural(parts.records, 'record')})" if parts.records else ""))
        self.all_estimate.setToolTip(everything_text(inventory, now - self.all_days.value() * DAY,
                                                     self.all_days.value(), self.include_failures.isChecked()))
        self.purge_all_button.setEnabled(writable and parts.any)
        self.purge_records_button.setEnabled(writable and sum(records.values()) > 0)
        self.purge_results_button.setEnabled(writable and results["results"] > 0)

    def _update(self) -> None:
        inventory = self.inventory
        writable = inventory is not None and not inventory.get("read_only") and not self.busy
        for button in (*self.kind_buttons.values(), self.clear_all_button):
            button.setEnabled(writable)
        self.prefs_button.setEnabled(False)
        self.converted_button.setEnabled(False)
        self.results_button.setEnabled(False)
        self.refresh_button.setEnabled(self.enabled and not self.busy and not self._inventory_owner)
        self.disk_budget.setEnabled(not self.applying)
        status = ("Off for this session" if not folder_cache.store_options() else
                  "Changing the disk budget…" if self._budget_job else f"{self._job_label}…" if self.busy else "Checking…" if self._inventory_owner and inventory is None
                  else "")
        if inventory is None:
            for widget in (self.raw_name, self.raw_label, self.raw_button, self.txy_name, self.txy_label,
                           self.txy_button, self.policy_name, self.policy_combo, self.legacy_name, self.legacy_label,
                           self.legacy_choice_button, self.legacy_clear_button):
                widget.setVisible(False)
            for label in (*self.kind_labels.values(), self.prefs_label, self.results_label, self.converted_label):
                label.setText(status or "Not checked")
            self.usage_label.setText(status or "Not checked")
            self.checked_label.setText(self.message or status)
            self._show_estimates()
            return
        budget = int(folder_cache.store_options().get("budget") or read_disk_budget(self.settings))
        usage = int(inventory["usage"])
        extras = []
        if inventory["retired"]["bytes"]:
            extras.append(f"freeing {byte_size(inventory['retired']['bytes'], 'disk')}")
        if inventory["pending"]:
            extras.append(f"{plural(len(inventory['pending']), 'save')} waiting for your answer")
        if inventory.get("read_only"):
            extras.append("read only: written by a newer HeLab")
        self.usage_label.setText(" · ".join([f"{byte_size(usage, 'disk')} of {byte_size(budget, 'disk')} budget", *extras]))
        self.usage_label.setToolTip("Freeing: removed cached data waiting out its 10-minute grace period; it "
                                    "doesn't count toward the budget." if inventory["retired"]["bytes"] else "")
        self.usage_bar.setValue(min(1000, round(1000 * usage / budget)) if budget else 0)
        datasets = inventory["datasets"]
        text = f"{plural(datasets['count'], 'folder')} · {byte_size(datasets['bytes'], 'disk')}"
        last_used = datasets.get("last_used")
        if isinstance(last_used, (int, float)):
            text += f" · last used {relative_age(time.time() - last_used)}"
            self.kind_labels["datasets"].setToolTip(
                f"Last used: {datetime.fromtimestamp(last_used):%Y-%m-%d %H:%M}\n"
                f"About {byte_size(datasets.get('ram_bytes', 0), 'ram')} in RAM when loaded")
        self.kind_labels["datasets"].setText(text)
        self.kind_labels["summaries"].setText(plural(inventory["summaries"]["count"], "folder"))
        histories = inventory["histories"]
        self.kind_labels["histories"].setText(f"{plural(histories['blocked'], 'folder')} skip automatic checks")
        self.kind_labels["histories"].setToolTip(f"{plural(histories['count'], 'folder')} with a scan history")
        self.kind_labels["subtrees"].setText(plural(inventory["subtrees"]["count"], "folder"))
        self.kind_labels["listings"].setText(plural((inventory.get("listings") or {"count": 0})["count"], "folder"))
        results = inventory.get("results") or {"count": 0, "bytes": 0, "last_used": None}
        text = f"{plural(int(results['count']), 'result')} · {byte_size(int(results['bytes']), 'disk')}"
        if isinstance(results.get("last_used"), (int, float)):
            text += f" · last shown {relative_age(time.time() - results['last_used'])}"
        self.results_label.setText(text)
        self.results_button.setEnabled(writable and bool(results["count"]))
        prefs = {"no_cache": 0, "no_auto_load": 0, "write_beside": 0, **(inventory.get("prefs") or {})}
        self.prefs_label.setText(f"{plural(prefs['no_cache'], 'folder')} not cached · "
                                 f"{plural(prefs['no_auto_load'], 'folder')} not auto-loaded" + (
                                     f" · {plural(prefs['write_beside'], 'folder')} with HeLab's TXY beside"
                                     if prefs["write_beside"] else ""))
        self.prefs_button.setEnabled(writable and bool(prefs["no_cache"] or prefs["no_auto_load"]
                                                       or prefs["write_beside"]))
        converted: dict[str, Any] = inventory.get("converted_txy") or {"files": 0, "bytes": 0}
        self.converted_label.setText(f"{plural(int(converted['files']), 'file')} · "
                                     f"{byte_size(int(converted['bytes']), 'disk')}" + converted_used(converted))
        self.converted_label.setToolTip("\n".join((CONVERTED_TIP, "", *(
            f"{CONVERTED_BASES.get(name, name)}: {plural(int(base['files']), 'file')} in "
            f"{plural(int(base['folders']), 'folder')} · {byte_size(int(base['bytes']), 'disk')}{converted_used(base)}"
            + (f" · a newer HeLab's index, {byte_size(int(base['newer']), 'disk')}, which Clear leaves"
               if base.get("newer") else "")
            for name, base in (converted.get("bases") or {}).items()))))
        # (Only when Clear would remove something: never the index itself, which the bytes include.)
        self.converted_button.setEnabled(writable and bool(converted.get("clearable")))
        self._show_v4_rows(inventory, writable)
        checked = f"Checked {datetime.fromtimestamp(inventory['checked_at']):%H:%M}"
        self.checked_label.setText(" · ".join(filter(None, (status or checked, self.message))))
        self._show_estimates()

    def _show_v4_rows(self, inventory: dict[str, Any], writable: bool) -> None:
        """Caching v2's rows, shown only with store-v4: raw pulses, TXY data and the policy, and the older store-v3
        when there is one."""
        txy = inventory.get("txy")
        for widget in (self.txy_name, self.txy_label, self.txy_button, self.policy_name, self.policy_combo):
            widget.setVisible(txy is not None)
        if txy is not None:
            tags = ", ".join(sorted(txy.get("tags") or ()))
            text = f"{plural(int(txy['shots']), 'shot')} in {plural(int(txy['folders']), 'folder')} · " \
                   f"{byte_size(int(txy['bytes']), 'disk')}" + (f" · {tags}" if tags else "")
            if txy.get("only_copy"):
                text += f" · {int(txy['only_copy']):,} only copies"
            self.txy_label.setText(text)
            self.txy_button.setEnabled(writable and bool(txy["layers"]))
        raw = inventory.get("raw")
        for widget in (self.raw_name, self.raw_label, self.raw_button):
            widget.setVisible(raw is not None)
        if raw is not None:
            text = f"{plural(int(raw['count']), 'shot')} in {plural(int(raw['folders']), 'folder')} · " \
                   f"{byte_size(int(raw['bytes']), 'disk')}"
            if raw.get("only_copy"):
                text += f" · {int(raw['only_copy']):,} only copies"
            self.raw_label.setText(text)
            self.raw_button.setEnabled(writable and bool(raw["count"]))
        from helab.views.CacheDialogs import legacy_clearable, legacy_text
        legacy = inventory.get("legacy") or {}
        present = bool(legacy.get("present"))
        for widget in (self.legacy_name, self.legacy_label, self.legacy_clear_button):
            widget.setVisible(legacy_clearable(legacy))  # (Or only what a Clear cut short left, C3-4.)
        self.legacy_choice_button.setVisible(present)
        if legacy_clearable(legacy):
            self.legacy_label.setText(legacy_text(legacy))
            self.legacy_clear_button.setEnabled(writable)
        if present:
            self.legacy_choice_button.setText("Keep using it" if legacy.get("choice") == "ignore" else "Ignore it")
            self.legacy_choice_button.setEnabled(writable)

    def focus_purge(self) -> None:
        """Opened from the 80% warning: start at Remove old entries."""
        self.dataset_days.setFocus()
        self.dataset_days.selectAll()

    def show_disk_budget(self, budget: int) -> None:
        """Shows ``budget`` bytes. Left as shown, it stays those bytes: a budget saved in the other
        units (8 GB on Windows shows 7.5 GiB) isn't rewritten."""
        self._shown_budget = (-1.0, budget)  # (No snap: it shows the stored bytes.)
        self.disk_budget.setValue(budget / self.disk_unit)
        self._shown_budget = (self.disk_budget.value(), budget)

    def _snap_disk_budget(self, value: float) -> None:
        """Moved off a stored budget that isn't on the half-unit grid (most GB budgets on Windows),
        the box goes to the grid at once, so the value shown is the value saved."""
        if self._shown_budget[0] >= 0 and value != self._shown_budget[0] and value * 2 != round(value * 2):
            self.disk_budget.setValue(round(value * 2) / 2)

    def disk_budget_bytes(self) -> int:
        shown, budget = self._shown_budget
        if self.disk_budget.value() == shown:
            return budget
        return max(MIN_DISK_BUDGET, round(self.disk_budget.value() * 2) * self.disk_unit // 2)

    def apply_budget(self) -> bool | None:
        """Before Settings writes anything, the store records a changed disk budget: from then
        on, loads already running save within it too. Lowering it below current use asks first,
        and the same job removes the least recently used cached data until the rest fits.

        True: nothing to wait for. None: wait for ``budgetApplied``. False: declined, or the job
        couldn't be queued; nothing is saved.
        """
        budget = self.disk_budget_bytes()
        # Compared with the budget in effect (the store's), not the saved setting, which
        # "Reset all settings…" may already have changed.
        saved = int(folder_cache.store_options().get("budget") or read_disk_budget(self.settings))
        if self.applying:
            return False
        if budget == saved or not self.enabled or self.cache is None:
            self._acknowledged = budget  # Unchanged, or no store to tell.
            return True
        inventory = self.inventory
        trim = budget < saved and (inventory is None or int(inventory["usage"]) > budget)
        if trim and inventory is not None and "txy" in inventory:
            # store-v4: what lowering it removes comes from the helper's plan (layers, raw pulses and only copies,
            # named); the question is asked when it comes (``_on_done``).
            self._planning = budget
            self._send_budget("trim", budget, plan_only=True)
            if not self._budget_job:
                self._planning = None
            return None if self._budget_job else False
        if trim and not self._ask_trim(budget, inventory, None):
            return False
        # Lowering it without a trim: the helper checks it still fits (more may be cached by now).
        self._send_budget("trim" if trim else "budget", budget, fit=budget < saved and not trim)
        return None if self._budget_job else False

    def _ask_trim(self, budget: int, inventory: dict[str, Any] | None, usage: int | None,
                  room: dict[str, Any] | None = None) -> bool:
        if room is not None:
            from helab.views.CacheDialogs import room_text
            removes = room_text(room, "Lowering the budget")
        elif inventory is not None:
            estimate = trim_estimate(inventory, budget)
            removes = (f"Removes cached data for up to {plural(estimate['datasets'], 'folder')} "
                       f"({byte_size(estimate['bytes'], 'disk')}), least recently used first.")
        else:
            removes = "Removes the least recently used cached data until the rest fits."
        uses = f"now uses {byte_size(usage, 'disk')}, more than" if usage is not None else "uses more than"
        return self.confirm("Lower the disk cache budget?",
                            f"The disk cache {uses} {byte_size(budget, 'disk')}. {removes}\n\n{CLEAR_TEXT['datasets']}",
                            "Lower budget")

    def _send_budget(self, action: str, budget: int, *, fit: bool = False, plan_only: bool = False,
                     plan: list[str] | None = None) -> None:
        assert self.cache is not None
        self._applying_budget = budget
        params: dict[str, Any] = {"budget": budget, "budget_set_at": time.time()}
        if fit:
            params["fit"] = True
        if plan_only:
            params["plan_only"] = True
        if plan is not None:
            params["plan"] = plan
        self._budget_job = self.cache.cache_admin(action, **params)
        self.message = "" if self._budget_job else "Disk cache queue full — nothing saved. Save again to retry."
        self._update()

    def save(self, settings: QSettings) -> None:
        """Save both budgets (after :meth:`apply_budget`), how often Live saves, and the cache policy."""
        policy = str(self.policy_combo.currentData() or "")
        if policy:
            before = folder_cache.cache_policy()
            settings.setValue(CACHE_POLICY_SETTING, policy)
            folder_cache.set_cache_policy(policy)  # (Sent with the next store-v4 request.)
            raw = (self.inventory or {}).get("raw")
            following = (raw or {}).get("following") or {}
            if policy == "txy" and before != "txy":
                # S4~1 (Tony, 2026-11-02): nothing is removed unasked; offer the raw pulses of the folders that
                # follow this setting (those with their own policy keep theirs), sized as the removal (S4-1).
                if self.inventory is None or self.busy:
                    # S4-3, S4R-1: not offered now; said, not skipped silently. Settings closes as it saves, so
                    # the main window's status bar says it (in the app, not the desktop), and this tab too.
                    self.message = RAW_KEPT_MESSAGE
                    self._update()
                    from helab.utils import events
                    events.notify(events.RAW_KEPT, RAW_KEPT_MESSAGE, status=True)
                elif int(following.get("count") or 0) and self.confirm(
                        "TXY only", remove_raw_following_text(following), "Remove"):
                    self._run("Remove cached raw pulses", "clear_raw", following=True)
        # Never a value the store hasn't recorded (e.g. edited while it was recording another).
        settings.setValue(DISK_BUDGET_SETTING,
                          self._acknowledged if self._acknowledged is not None else read_disk_budget(settings))
        settings.setValue(RAM_BUDGET_SETTING, self.ram_budget.value())
        settings.setValue(PLOT_AUTO_RELOAD_SETTING, self.plot_auto_reload.isChecked())
        settings.setValue(RESULT_REUSE_SETTING, self.result_reuse.isChecked())
        if self.cache is not None:
            self.cache.set_result_reuse(self.result_reuse.isChecked())  # (The folder rows' badge.)
        settings.setValue(LIVE_AUTOSAVE_SETTING, self.live_autosave.value())

