"""The Activity window (Q62.1–Q62.5): every task HeLab runs, its state, and what can be done to it.

``ActivitySources`` reads each owner's memory (IOService and FolderCache, each tab's Live and
conversions, the analysis runner, the script folders' test imports, the cache-folder move) and builds an
``activity.Snapshot`` with the pure rules of ``helab.utils.activity``. Nothing here reads a disk or
submits I/O while building or rendering; actions call each owner's own path.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional, Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QHideEvent, QMouseEvent, QShowEvent
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from helab.utils import activity
from helab.utils.accessible import identify
from helab.utils.activity import About, Action, Progress, Route, Snapshot, Task
from helab.utils.colours import AMBER
from helab.utils.folder_cache import FolderCache, SharedJob
from helab.utils.io_service import IORequest, IOService
from helab.utils.settings_defaults import ACTIVITY_SIZE_SETTING, read_setting
from helab.utils.settings_store import app_settings
from helab.utils.time_format import clock
from helab.views.ElidedLabel import ElidedLabel
from helab.views.gaps import CELL_PADDING_STYLE, COLUMN_GAP, LABEL_GAP, ROW_SPACING

if TYPE_CHECKING:
    from helab.analysis.runner import AnalysisRunner
    from helab.views.CacheMover import CacheMover
    from helab.views.explorer_live import LiveSession
    from helab.views.FolderExplorer import FolderExplorer
    from helab.views.plots.script_tree import TreePanelWidget

# Why a background request is paused, by who holds it.
PAUSED_BY_YOU = "by you (Activity: Resume background I/O)"
PAUSED_MISMATCH = "cached data doesn't match several folders (see the status bar's ⚠)"
PAUSED_FOREGROUND = "while the current tab browses or loads"
HELD_MOVE = "the disk cache is being moved"


def _name(path: str) -> str:
    return os.path.basename(path.rstrip("/\\")) or path


def same(one: str, other: str) -> bool:
    """Whether two owners' paths name one folder (``FolderCache.key``: lexical, no disk)."""
    return bool(one) and bool(other) and FolderCache.key(one) == FolderCache.key(other)


def session_of(explorer: FolderExplorer, path: str) -> Optional[LiveSession]:
    """The tab's Live session of ``path``, its paths compared as folders."""
    return next((session for session in explorer.live_control.sessions() if same(session.path, path)), None)


def watching(explorer: FolderExplorer, path: str) -> bool:
    """Live on for ``path`` in this tab (``LiveController.watching``, its paths compared as folders)."""
    live = explorer.live_control.live
    return live is not None and same(live.path, path)


@dataclass(frozen=True)
class Owner:
    """Whom an I/O owner works for: a tab (its text and explorer) and in what role, or a plot."""
    tab: str
    role: str  # select (the tab's own), background, live, live_save, convert, plot
    explorer: Optional[FolderExplorer] = None
    plot: str = ""  # A plot's instance id.


class ActivitySources:
    """Builds the Activity snapshot from the app's owners, memory only. ``tabs`` gives the folder tabs
    (their text and explorer), ``runners`` the analysis runners, ``plots`` each open plot's title by its
    instance id, ``scripts`` the Scripts panel (probes, reloads), ``mover`` the cache-folder move."""

    def __init__(self, service: IOService, cache: FolderCache,
                 tabs: Callable[[], Sequence[tuple[str, FolderExplorer]]] = lambda: (),
                 runners: Callable[[], Sequence[AnalysisRunner]] = lambda: (),
                 plots: Callable[[], dict[str, str]] = lambda: {},
                 scripts: Callable[[], Optional[TreePanelWidget]] = lambda: None,
                 mover: Optional[Callable[[], Optional[CacheMover]]] = None) -> None:
        self.service = service
        self.cache = cache
        self.tabs = tabs
        self.runners = runners
        self.plots = plots
        self.scripts = scripts
        self.mover: Callable[[], Optional[CacheMover]] = mover or self._cache_mover
        self._owners: dict[str, Owner] = {}
        self._plots: dict[str, str] = {}

    def _cache_mover(self) -> Optional[CacheMover]:
        from helab.views.CacheMover import CacheMover
        mover = self.cache.cache_mover
        return mover if isinstance(mover, CacheMover) else None

    # Owners

    def _index_owners(self) -> None:
        owners: dict[str, Owner] = {}
        for text, explorer in self.tabs():
            for role, owner in (("select", explorer.model.owner), ("background", explorer.bg_owner),
                                ("live", explorer.live_owner), ("live_save", explorer.live_save_owner),
                                ("convert", explorer.converter.owner)):
                owners[owner] = Owner(text, role, explorer)
        self._owners = owners
        self._plots = dict(self.plots())

    def owner(self, owner: str) -> Optional[Owner]:
        """Whom an I/O owner (a subscriber, or a request's own owner) works for, if known now."""
        if owner in self._owners:
            return self._owners[owner]
        if owner.startswith("plot-txy:"):
            plot = owner.split(":")[1]
            return Owner(self._plots.get(plot, f"plot {plot}"), "plot", plot=plot)
        if owner in self._plots:
            return Owner(self._plots[owner], "plot", plot=owner)
        return None

    def plot_title(self, plot: str) -> str:
        return self._plots.get(plot, "")

    def subscribers(self, request: IORequest) -> list[str]:
        """The owners a helper's request works for: a shared job's subscribers, else its own owner."""
        job = self.cache.job_of(request.owner)
        if job is not None:
            return list(dict.fromkeys(subscriber.owner for subscriber in job.subscribers.values()))
        return [request.owner]

    def tab_text(self, owners: Iterable[str]) -> str:
        names = [found.tab for owner in owners if (found := self.owner(owner)) is not None]
        return ", ".join(dict.fromkeys(names))

    # I/O

    def about(self, request: IORequest) -> About:
        """What a helper's request is, from its owners' memory."""
        service, cache = self.service, self.cache
        job = cache.job_of(request.owner)
        admin = cache.admin_action(request.owner)
        finishing = service.finishing(request) or cache.finishing_of(request.owner) is not None
        payload = request.payload if job is None else {**request.payload, "save": job.saves() or request.payload.get(
            "save"), "live": job.live or request.payload.get("live")}
        group = activity.group_of(request.operation, payload, finishing=finishing, admin=admin)
        owners = self.subscribers(request)
        found = [owner for name in owners if (owner := self.owner(name)) is not None]
        title = service.label(request) + (f": {admin.replace('_', ' ')}" if admin else "")
        actions: set[Action] = set()
        parent = ""
        if any(owner.explorer is not None or owner.plot for owner in found):
            actions.add("show")
        roles = {owner.role for owner in found}
        mover = self.mover()
        if activity.is_live_check(request) or (job is not None and job.live):
            actions.add("stop_live")
            parent = self._live_parent(found, request.path)
        elif group == "saves":
            parent = self._live_parent(found, request.path) if "live_save" in roles else ""
        elif request.operation == "convert":
            actions.add("cancel")
            parent = self._live_parent(found, request.path) if "live" in roles else self._conversion_parent(
                found, request.path)
        elif request.operation == "raw_fill" or cache.raw_filling(request.owner):
            actions.add("cancel")
        elif request.operation == "cache_move":
            if mover is not None and request.owner == mover.owner:
                parent = "move"
                if mover.busy:
                    actions.add("cancel")
        elif group == "loads" and found and not request.completed:
            actions.add("cancel")
        progress: Optional[Progress] = None
        elapsed = left = stalled = None
        file = ""
        if job is not None:
            progress, file = self._job_progress(job), job.current_file
            if request.operation == "load" and not job.live and job.clock.elapsed():
                elapsed, left = job.clock.elapsed(), job.clock.remaining()
                stalled = job.clock.stalled_for() or None
        notes: list[str] = []
        if job is not None and len(found) > 1:
            notes.append("Shared by: " + ", ".join(dict.fromkeys(owner.tab for owner in found)))
        if job is not None and request.operation == "load":
            _, note = cache.load_note(request)
            if note:
                notes.append(note)
        return About(title, group, self.tab_text(owners), progress, elapsed, left, stalled, file, tuple(notes),
                     frozenset(actions), Route("io", request.owner, request.operation, request.path), parent,
                     writing=not request.completed or cache.writing_disk_cache(request.owner))

    @staticmethod
    def _job_progress(job: SharedJob) -> Optional[Progress]:
        progress = job.progress or {}
        total, checked = progress.get("total_files"), progress.get("checked_files")
        if not isinstance(total, int) or not isinstance(checked, int):
            return None
        read, total_bytes = progress.get("read_bytes"), progress.get("total_read_bytes")
        return Progress(checked, total, read if isinstance(read, int) else None,
                        total_bytes if isinstance(total_bytes, int) else None)

    @staticmethod
    def _live_parent(found: Sequence[Owner], path: str) -> str:
        for owner in found:
            if owner.explorer is not None and (session := session_of(owner.explorer, path)) is not None:
                return live_id(owner.explorer, session.path)
        return ""

    @staticmethod
    def _conversion_parent(found: Sequence[Owner], path: str) -> str:
        for owner in found:
            if owner.explorer is None:
                continue
            folder = next((known for known in owner.explorer.converter.conversions if same(known, path)), None)
            if folder is not None:
                return conversion_id(owner.explorer, folder)
        return ""

    def why_paused(self, request: IORequest) -> str:
        service = self.service
        if service.user_held(request):
            return PAUSED_BY_YOU
        if service.held_by_mismatch(request):
            return PAUSED_MISMATCH
        return PAUSED_FOREGROUND

    def why_held(self, request: IORequest) -> str:
        service = self.service
        if service.cache_hold and service.uses_cache(request):
            return HELD_MOVE
        if service.held_by_mismatch(request):
            return PAUSED_MISMATCH
        if service.user_held(request):
            return "background I/O paused by you"
        return ""

    def io_tasks(self, now: float) -> list[Task]:
        service = self.service
        return activity.io_tasks(service.active, service.pending, service.retired, self.about, now,
                                 why_paused=self.why_paused, why_held=self.why_held, pid=_pid,
                                 attempts=len(service.TIMEOUTS))

    def waiting_saves(self) -> list[Task]:
        """Saves quitting waits for that no helper runs yet: one waiting for the folder's previous save or
        a load of it, and writes held for the store's identity check (``FolderCache.quit_entries``)."""
        tasks = []
        for entry in self.cache.quit_entries():
            if entry.state not in ("waiting", "held"):
                continue
            text = ("waits for the folder's previous save or load" if entry.state == "waiting"
                    else "held: the disk cache's identity is being checked")
            tasks.append(Task(f"save:{entry.kind}:{entry.path}", "saves", entry.kind.capitalize(), entry.path, "",
                              "queued", text, details=(f"{entry.kind.capitalize()} · {entry.path}", text,
                                                       "Quitting waits for it"),
                              actions=frozenset({"log"}), route=Route("save", path=entry.path)))
        return tasks

    # Live, conversions and questions (per tab)

    def tab_tasks(self, now: float) -> list[Task]:
        tasks: list[Task] = []
        wall = time.time()
        for text, explorer in self.tabs():
            control = explorer.live_control
            for session in control.sessions():
                tasks.append(self._live_task(text, explorer, session, wall, now))
                if session.convert is not None:
                    tasks.append(self._auto_convert_task(text, explorer, session))
            if control.box is not None:
                tasks.append(_question_task(text, explorer, control.box, "live"))
            for path, conversion in explorer.converter.conversions.items():
                if conversion.finished and not conversion.error:
                    continue
                tasks.append(self._conversion_task(text, explorer, path, conversion, wall))
            if explorer.converter.box is not None:
                tasks.append(_question_task(text, explorer, explorer.converter.box, "convert"))
        return tasks

    @staticmethod
    def _live_task(tab: str, explorer: FolderExplorer, session: LiveSession, wall: float, now: float) -> Task:
        control = explorer.live_control
        line, tooltip, _ = control.live_line(session)
        actions: set[Action] = {"show", "log"}
        state: activity.State
        if session.on and session.error:
            state, text = "failed", f"stopped: {session.error}"
            actions |= {"retry", "stop_live"}
        elif session.on:
            actions.add("stop_live")
            if session.request == "check":
                state, text = "running", "reading new shots" if session.reading else "checking for new shots"
            elif session.request == "save":
                state, text = "running", "saving new shots"
            elif session.unsettled:
                state, text = "settling", f"waiting for {session.unsettled:,} file{'' if session.unsettled == 1 else 's'} to settle"
            else:
                state, text = "waiting", f"next check in {clock(max(0.0, session.next_at - now))}"
        else:
            state, text = "running", "saving new shots (Live is off)"
        details = (f"Live · {session.path}", f"Tab: {tab}",
                   "Started " + time.strftime("%H:%M:%S", time.localtime(session.started_at)),
                   f"Checks: {session.checks:,} · new shots: {session.new:,} · not yet saved: {len(session.unsaved):,}",
                   line, *[part for part in tooltip.splitlines() if part])
        return Task(live_id(explorer, session.path), "live", "Live", session.path, tab, state, text, None,
                    max(0.0, wall - session.started_at), None, tuple(details), frozenset(actions),
                    Route("live", explorer.live_owner, path=session.path))

    @staticmethod
    def _auto_convert_task(tab: str, explorer: FolderExplorer, session: LiveSession) -> Task:
        convert = session.convert
        assert convert is not None
        text, lines, _ = explorer.live_control.convert_line(session)
        state: activity.State
        actions: set[Action] = {"show", "log", "cancel"}
        if convert.error:
            state, status = "failed", f"stopped: {convert.error}"
            actions.add("retry")
        elif convert.request:
            state, status = "running", (f"converting {convert.done:,} of {convert.todo:,}" if convert.todo
                                        else "converting")
        elif convert.waiting:
            state, status = "settling", f"waiting for {len(convert.waiting):,} raw file{'' if len(convert.waiting) == 1 else 's'} to settle"
        else:
            state, status = "waiting", f"converted {convert.converted:,} · converts with each check"
        progress = Progress(convert.done, convert.todo, noun="shot") if convert.request and convert.todo else None
        return Task(f"autoconvert:{explorer.live_owner}:{session.path}", "live", "Auto-convert", session.path, tab,
                    state, status, progress, max(0.0, time.time() - convert.started_at), None,
                    tuple(line for line in (f"Auto-convert · {session.path}", text, *lines) if line),
                    frozenset(actions), Route("autoconvert", explorer.live_owner, path=session.path),
                    live_id(explorer, session.path))

    @staticmethod
    def _conversion_task(tab: str, explorer: FolderExplorer, path: str, conversion: Any, wall: float) -> Task:
        row = explorer.converter.row(path)
        text, tooltip = row if row is not None else ("", "")
        actions: set[Action] = {"show", "log"}
        state: activity.State
        if conversion.error:
            state, status = "failed", f"stopped: {conversion.error}"
            actions.add("retry")
        elif conversion.flag:
            state, status = "waiting", "saving the folder's beside setting"
        elif conversion.request:
            state, status = "running", "converting"
            actions.add("cancel")
        elif conversion.waiting:
            state, status = "settling", f"waiting for {conversion.waiting:,} file{'' if conversion.waiting == 1 else 's'} to settle"
        else:
            state, status = "waiting", "next pass shortly"
        progress = Progress(conversion.done, conversion.todo, noun="shot") if conversion.request and conversion.todo else None
        return Task(conversion_id(explorer, path), "convert", "Convert raw files to TXY", path, tab, state, status,
                    progress, max(0.0, wall - conversion.started_at), None,
                    tuple(line for line in (text, *tooltip.splitlines()) if line), frozenset(actions),
                    Route("conversion", explorer.converter.owner, "convert", path))

    # Analysis, scripts and the cache move

    def analysis_tasks(self, now: float) -> list[Task]:
        tasks: list[Task] = []
        seen: set[int] = set()
        for runner in self.runners():
            if id(runner) in seen:
                continue
            seen.add(id(runner))
            tasks += activity.analysis_tasks(runner.jobs(), now, tab=self.plot_title)
        return tasks

    def script_tasks(self, now: float) -> list[Task]:
        scripts = self.scripts()
        if scripts is None:
            return []
        start, imports = scripts.probe_limits()
        limits = f"Its own time limits end it ({start:g} s to start, {imports:g} s to import)"
        tasks = []
        for folder, state, started in scripts.probe_activity():
            text = {"importing": "test-importing", "starting": "starting its test import",
                    "stopping": "stopping (killed)", "queued": "queued"}[state]
            tasks.append(Task(f"probe:{folder}", "scripts", "Test-import scripts", folder, "",
                              "queued" if state == "queued" else "stopping" if state == "stopping" else "running",
                              text, None, None if started is None else max(0.0, now - started), None,
                              (f"Test import of the script folder {folder} in a separate process",
                               limits), frozenset({"log"}),
                              Route("probe", path=folder)))
        folders, runs = scripts.reload_waiting()
        if folders:
            text = (f"waits for {runs:,} run{'' if runs == 1 else 's'} to end" if runs
                    else "waits for the test imports")
            tasks.append(Task("reload", "scripts", "Reload scripts", ", ".join(folders), "", "waiting", text,
                              details=("Reload of " + ", ".join(folders), text), actions=frozenset({"log"}),
                              route=Route("reload")))
        return tasks

    def move_task(self) -> list[Task]:
        mover = self.mover()
        if mover is None or not mover.running:
            return []
        state: activity.State = "running"
        text = (f"moving to {mover.target}" if mover.moving and not mover.switched_folder
                else "switched; removing the old folder" if mover.switched_folder else f"checking {mover.target}")
        actions: set[Action] = {"log", "cancel"} if mover.busy else {"log"}
        return [Task("move", "upkeep", "Move disk cache", mover.source, "", state, text,
                     details=(f"Moving the disk cache from {mover.source} to {mover.target}",
                              f"Method: {mover.method or 'not chosen yet'}", text),
                     actions=frozenset(actions), route=Route("move", mover.owner))]

    # The snapshot

    def snapshot(self, now: Optional[float] = None) -> Snapshot:
        """Everything running, queued or waiting now (memory only)."""
        now = time.monotonic() if now is None else now
        self._index_owners()
        service = self.service
        tasks = [*self.io_tasks(now), *self.waiting_saves(), *self.tab_tasks(now), *self.analysis_tasks(now),
                 *self.script_tasks(now), *self.move_task()]
        known = {task.id for task in tasks}
        # (A child whose parent row isn't listed is shown at the top of its group.)
        tasks = [task if not task.parent or task.parent in known else _orphan(task) for task in tasks]
        running = len(service.running_requests())
        paused = sum(r.paused and not r.completed for r in service.active)
        queued = len(service.pending) - len(service.held_requests())
        counts = activity.Counts(running, paused, queued, len(service.retired), service.activity_counts())
        return Snapshot(activity.ordered(tasks), counts, service.user_hold, now)


def unique(items: Iterable[Any]) -> list[Any]:
    """``items`` without repeats, by identity, in order."""
    seen: set[int] = set()
    kept = []
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            kept.append(item)
    return kept


def _orphan(task: Task) -> Task:
    from dataclasses import replace
    return replace(task, parent="")


def _pid(request: IORequest) -> Optional[int]:
    process = request.process
    return None if process is None else int(process.pid)


def live_id(explorer: FolderExplorer, path: str) -> str:
    return f"live:{explorer.live_owner}:{path}"


def conversion_id(explorer: FolderExplorer, path: str) -> str:
    return f"conversion:{explorer.converter.owner}:{path}"


def _question_task(tab: str, explorer: FolderExplorer, box: Any, kind: str) -> Task:
    title = box.windowTitle() or "Converter question"
    text = box.text() or ""
    return Task(f"question:{kind}:{explorer.model.owner}", "convert", f"Question: {title}", "", tab, "waiting",
                "waiting for your answer", details=(title, *[line for line in text.splitlines() if line],
                                                    "Nothing converts there until it is answered"),
                actions=frozenset({"answer", "show"}), route=Route("question", explorer.model.owner, kind))


# The window

def parse_size(text: object, default: tuple[int, int] = (1080, 440)) -> tuple[int, int]:
    """``"W,H"`` as (width, height), at least ``MIN_SIZE``; the default when it can't be read."""
    try:
        width, height = (int(part) for part in str(text).split(","))
    except (TypeError, ValueError):
        return default
    if width <= 0 or height <= 0:
        return default
    return max(MIN_SIZE[0], width), max(MIN_SIZE[1], height)


MIN_SIZE = (400, 200)
# Listings and scans: their Retry is the tree's right-click Retry (``FolderExplorer.refresh_folder``).
LISTINGS = frozenset({"list", "details", "scan", "resolve"})
NOW_COLUMNS = ("Task", "Tab", "Folder", "State", "Progress", "Elapsed", "Left")
HISTORY_COLUMNS = ("Ended", "Task", "Tab", "Folder", "Outcome", "Took")
# IOService events that change what the list shows at once (progress waits for the 1 s tick).
REFRESH_KINDS = frozenset({"queued", "started", "paused", "resumed", "done", "error", "cancelled", "loaded"})
# Why each action can't be used on the selected row (its tooltip).
ACTION_TIPS: dict[str, tuple[str, str]] = {
    "cancel": ("Cancel", "Stop the selected task, as its own Cancel does; it shows stopping until its process exits. "
                         "A tab's selected load stops as the toolbar's Cancel stops it, with that tab's other "
                         "background loads"),
    "retry": ("Retry", "Run the failed task again, as its own Retry does"),
    "show": ("Show in tab", "Show the selected task's folder in its tab, or its plot"),
    "stop_live": ("Stop Live", "Turn Live off for the selected folder; its new shots are saved as always"),
    "log": ("Open log", "Open this session's log file"),
    "answer": ("Answer", "Show the converter's question waiting for your answer"),
}
NOT_FOR = {
    "cancel": "Not for this task: saves, cache upkeep and test imports end by themselves (Live: Stop Live)",
    "retry": "Only a failed task, whose owner can run it again now",
    "show": "This task isn't for a tab or a plot",
    "stop_live": "Only Live",
}


class ActivityActions:
    """What the window's buttons do, each through its owner's own path."""

    def __init__(self, sources: ActivitySources, show_tab: Callable[[FolderExplorer, str], None] = lambda e, p: None,
                 show_plot: Callable[[str], bool] = lambda plot: False, open_log: Callable[[], None] = lambda: None,
                 run_plot: Callable[[str], bool] = lambda plot: False,
                 reload_scripts: Callable[[list[str]], None] = lambda folders: None) -> None:
        self.sources = sources
        self.show_tab = show_tab
        self.show_plot = show_plot
        self.open_log = open_log
        self.run_plot = run_plot
        self.reload_scripts = reload_scripts

    def _owners(self, route: Route, owners: Sequence[str] = ()) -> list[str]:
        """Whom a route's task works for: a helper's subscribers while it runs, else those it recorded
        (a finished task's ``owners``), else its own owner."""
        if route.kind == "io":
            request = self._request(route)
            if request is not None:
                return self.sources.subscribers(request)
        return list(owners) or [route.owner]

    def _explorer(self, route: Route, owners: Sequence[str] = ()) -> Optional[FolderExplorer]:
        """The tab a route's owner (or, for a helper's request, one of its subscribers) belongs to."""
        for name in self._owners(route, owners):
            owner = self.sources.owner(name)
            if owner is not None and owner.explorer is not None:
                return owner.explorer
        return None

    def _request(self, route: Route) -> Optional[IORequest]:
        service = self.sources.service
        return next((r for r in (*service.active, *service.pending, *service.retired)
                     if (r.owner, r.operation, r.path) == (route.owner, route.operation, route.path)), None)

    def _plot(self, route: Route, owners: Sequence[str] = ()) -> str:
        if route.kind == "analysis":
            return route.owner
        for name in self._owners(route, owners):
            owner = self.sources.owner(name)
            if owner is not None and owner.plot:
                return owner.plot
        return ""

    def show(self, route: Route, folder: str, owners: Sequence[str] = ()) -> bool:
        """Show the task's folder in its tab (``FolderExplorer.reveal``), or its plot."""
        plot = self._plot(route, owners)
        if plot:
            return self.show_plot(plot)
        explorer = self._explorer(route, owners)
        if explorer is None:
            return False
        self.show_tab(explorer, route.path or folder)
        return True

    def show_target(self, route: Route, owners: Sequence[str] = ()) -> bool:
        """Whether Show in tab has somewhere to go for ``route``: a tab or a plot that is open now."""
        plot = self._plot(route, owners)
        return bool(self.sources.plot_title(plot)) if plot else self._explorer(route, owners) is not None

    def _tab(self, owner: str) -> Optional[FolderExplorer]:
        found = self.sources.owner(owner)
        return None if found is None else found.explorer

    def _tab_of(self, owners: Iterable[str], roles: Iterable[str] = ("select", "background")) -> Optional[FolderExplorer]:
        roles = set(roles)
        for name in owners:
            found = self.sources.owner(name)
            if found is not None and found.explorer is not None and found.role in roles:
                return found.explorer
        return None

    # Cancel (Q62.3): each through its owner's own path; a helper then shows "stopping" until its exit.

    def cancel(self, task: Task, *, queued_only: bool = False) -> bool:
        """Cancel ``task`` as its owner's own Cancel does; whether anything was asked to stop. A tab's selected
        load goes through the tab's Cancel (``cancel_loading``, the toolbar's), which also stops that tab's
        background loads; ``queued_only`` (Cancel all queued) leaves it, so nothing running is stopped."""
        route, cache = task.route, self.sources.cache
        if route.kind == "analysis":
            for runner in unique(self.sources.runners()):
                runner.cancel(route.job)
            return True
        if route.kind == "move":
            return self._cancel_move()
        if route.kind == "autoconvert":
            explorer = self._tab(route.owner)
            if explorer is None or not watching(explorer, route.path):
                return False
            explorer.live_control.set_auto_convert(False)  # (Its own toggle: one pass cancelled would only restart.)
            return True
        if route.kind == "conversion":
            cache.cancel(route.owner, "convert", route.path)  # (As ExplorerConverter.close does.)
            return True
        if route.kind != "io":
            return False
        request = self._request(route)
        if request is None:
            return False
        if request.operation == "raw_fill" or cache.raw_filling(request.owner):
            cache.cancel_raw_fill(request.path)
            return True
        if request.operation == "cache_move":
            return self._cancel_move()
        asked = False
        for name in self.sources.subscribers(request):
            found = self.sources.owner(name)
            if found is None:
                continue
            explorer = found.explorer
            if found.role == "live" and request.operation == "convert" and explorer is not None:
                if watching(explorer, request.path):
                    explorer.live_control.set_auto_convert(False)
                else:
                    cache.cancel(name, "convert", request.path)
            elif found.role == "select" and request.operation in ("load", "cached") and explorer is not None:
                if queued_only:
                    continue  # (Its tab's Cancel would stop the tab's running background loads too: AW-3.)
                explorer.cancel_loading()  # (The toolbar's Cancel: the tab says "Cancelled — Retry".)
                if self._subscribed(request, name):
                    cache.cancel(name, request.operation, request.path)
            elif found.role in ("select", "background", "convert", "plot"):
                cache.cancel(name, request.operation, request.path)
            else:
                continue
            asked = True
        return asked

    def _subscribed(self, request: IORequest, owner: str) -> bool:
        job = self.sources.cache.job_of(request.owner)
        return job is not None and any(subscriber.owner == owner for subscriber in job.subscribers.values())

    def _cancel_move(self) -> bool:
        mover = self.sources.mover()
        if mover is None or not mover.busy:
            return False
        mover.cancel()  # (Until the copy is verified; a rename can't be.)
        return True

    def cancel_queued(self, snapshot: Snapshot) -> int:
        """Cancel every queued task that can be cancelled, each through its own path; how many. Never a running
        one: a tab's selected load is left to its tab's Cancel (``cancel``'s ``queued_only``)."""
        count = 0
        for task in snapshot.tasks:
            if task.state == "queued" and "cancel" in task.actions and self.cancel(task, queued_only=True):
                count += 1
        return count

    # Retry: a failed task, through its owner; never beside the attempt it replaces.

    def retry_refusal(self, route: Route, outcome: Optional[str] = None, owners: Sequence[str] = ()) -> str:
        """Why ``route``'s task can't be retried now ("" when it can)."""
        if outcome == "ok":
            return "Only a failed or cancelled task"
        operation = {"live": "load", "autoconvert": "convert", "conversion": "convert"}.get(route.kind, route.operation)
        if route.path and operation and self.sources.service.unexited(operation, route.path):
            return "The previous attempt is still stopping: Retry once its process has exited"
        if route.kind in ("live", "autoconvert"):
            explorer = self._tab(route.owner)
            if explorer is None:
                return "Its tab is closed"
            session = explorer.live_control.live
            if session is None or not same(session.path, route.path):
                return "Live is off there: turn it on in its tab"
            if route.kind == "live" and not session.error:
                return "Live isn't stopped by an error"
            if route.kind == "autoconvert" and not (session.convert is not None and session.convert.error):
                return "Auto-convert isn't stopped by an error"
            return ""
        if route.kind == "conversion":
            explorer = self._tab(route.owner)
            if explorer is None:
                return "Its tab is closed"
            conversion = next((known for folder, known in explorer.converter.conversions.items()
                               if same(folder, route.path)), None)
            return "" if conversion is not None and conversion.error else "This conversion isn't stopped now"
        if route.kind == "analysis":
            if not route.owner or not self.sources.plot_title(route.owner):
                return "Its plot is closed"
            if any(job.owner == route.owner for runner in unique(self.sources.runners()) for job in runner.jobs()):
                return "The plot is running"
            return ""
        if route.kind == "probe":
            return ""
        if route.kind == "io":
            explorer = self._tab_of(owners)
            if explorer is None:
                return "Its owner tries again by itself, or its tab is closed"
            if route.operation in LISTINGS:
                return ""
            if route.operation in ("load", "cached"):
                return ("" if same(explorer.selected_path_globally, route.path)
                        else "Select the folder in its tab to load it again (Show in tab)")
            return "Its owner tries again by itself"
        return NOT_FOR["retry"]

    def retry(self, route: Route, folder: str, owners: Sequence[str] = ()) -> bool:
        """Retry through the owner's own Retry; whether it was asked."""
        if self.retry_refusal(route, None, owners):
            return False
        if route.kind in ("live", "autoconvert"):
            explorer = self._tab(route.owner)
            if explorer is not None:
                explorer.resume_live()  # (The Live line's Retry.)
            return explorer is not None
        if route.kind == "conversion":
            explorer = self._tab(route.owner)
            folder = next((known for known in explorer.converter.conversions if same(known, route.path)),
                          route.path) if explorer is not None else route.path
            if explorer is not None:
                explorer.converter.clicked(folder)  # (The Convert row's click.)
            return explorer is not None
        if route.kind == "analysis":
            return self.run_plot(route.owner)
        if route.kind == "probe":
            self.reload_scripts([route.path])
            return True
        explorer = self._tab_of(owners)
        if explorer is None:
            return False
        if route.operation in LISTINGS:
            explorer.refresh_folder(route.path)  # (Right-click Retry.)
        else:
            explorer.retry()  # (The tab's Retry, for its selected folder.)
        return True

    def stop_live(self, route: Route) -> bool:
        """Turn Live off for the task's folder (the toolbar's Live; its new shots are saved)."""
        explorer = self._explorer(route) if route.kind == "io" else self._tab(route.owner)
        if explorer is None or not watching(explorer, route.path):
            return False
        explorer.stop_live()
        return True

    def answer(self, route: Route) -> bool:
        explorer = self._explorer(route) if route.kind != "question" else next(
            (owner.explorer for owner in [self.sources.owner(route.owner)] if owner is not None), None)
        if explorer is None:
            return False
        box = explorer.live_control.box if route.operation == "live" else explorer.converter.box
        if box is None:
            return False
        box.show()
        box.raise_()
        box.activateWindow()
        return True


class ClickOpens(QObject):
    """Calls ``opened`` when its watched widget is clicked (the status bar's message opens Activity)."""

    def __init__(self, opened: Callable[[], None], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.opened = opened

    def eventFilter(self, a0: Optional[QObject], a1: Optional[QEvent]) -> bool:
        if (a1 is not None and a1.type() == QEvent.Type.MouseButtonRelease and isinstance(a1, QMouseEvent)
                and a1.button() == Qt.MouseButton.LeftButton):
            self.opened()
        return False


class ActivityWindow(QWidget):
    """Activity (Q62.1): every task HeLab runs, grouped by kind, with its state, progress and time, this
    session's history, and a details pane. Not modal; one per main window. Closed, it does nothing: no
    timer and no signal connection; shown, it refreshes on its owners' signals (at most every
    ``REFRESH_MS``) and every ``TICK_MS`` for times and progress."""
    REFRESH_MS = 200
    TICK_MS = 1000

    def __init__(self, sources: ActivitySources, actions: Optional[ActivityActions] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.sources = sources
        self.handler = actions or ActivityActions(sources)
        self.snapshot = Snapshot()
        self.refreshes = 0
        self.setWindowTitle("Activity")
        identify(self, "activity_window", "Activity", "Every task HeLab runs, and this session's history")
        self._items: dict[str, QTreeWidgetItem] = {}
        self._groups: dict[str, QTreeWidgetItem] = {}
        self._shape: dict[str, list[str]] = {}  # (Each parent's children's ids as last shown; "" the top level.)
        self._collapsed: set[str] = set()
        self._history: dict[str, activity.Finished] = {}  # (By ``Finished.key``.)
        self._history_version = -1
        self._connected: list[tuple[Any, Callable[..., None]]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(LABEL_GAP, ROW_SPACING, LABEL_GAP, LABEL_GAP)
        layout.setSpacing(ROW_SPACING)
        row = QHBoxLayout()
        row.setSpacing(LABEL_GAP)
        self.buttons: dict[str, QPushButton] = {}
        for action, (text, tip) in ACTION_TIPS.items():
            if action == "answer":
                continue
            button = identify(QPushButton(text), f"activity_{action}", text, tip)
            button.setToolTip(tip)
            button.setAutoDefault(False)
            button.clicked.connect(getattr(self, f"_on_{action}"))
            self.buttons[action] = button
            row.addWidget(button)
        row.addSpacing(COLUMN_GAP)
        self.pause_button = identify(QPushButton("Pause background I/O"), "activity_pause", "Pause background I/O",
                                     "Pause background loads, scans and conversions, and start none, until Resume")
        self.pause_button.setCheckable(True)
        self.pause_button.setAutoDefault(False)
        self.pause_button.setToolTip("Pause background loads, scans and conversions, and start none, until "
                                     "Resume. The current tab, saves, Live and the local disk cache go on.")
        self.pause_button.clicked.connect(self._on_pause)
        row.addWidget(self.pause_button)
        self.cancel_queued_button = identify(QPushButton("Cancel all queued"), "activity_cancel_queued",
                                             "Cancel all queued", "Cancel every queued task that can be cancelled")
        self.cancel_queued_button.setToolTip("Cancel every queued task that can be cancelled, each as its own "
                                             "Cancel does. Nothing running stops: a tab's selected load is "
                                             "left to that tab's Cancel. Saves stay queued.")
        self.cancel_queued_button.setAutoDefault(False)
        self.cancel_queued_button.clicked.connect(self._on_cancel_queued)
        row.addWidget(self.cancel_queued_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.summary = identify(ElidedLabel("Ready"), "activity_summary", "Activity summary")
        layout.addWidget(self.summary)
        self.now = self._tree("activity_now", "Running and queued tasks", NOW_COLUMNS)
        self.now.itemCollapsed.connect(self._item_collapsed)
        self.now.itemExpanded.connect(self._item_expanded)
        self.history = self._tree("activity_history", "This session's finished tasks", HISTORY_COLUMNS)
        self.tabs = identify(QTabWidget(), "activity_tabs", "Activity lists")
        self.tabs.addTab(self.now, "Now")
        self.tabs.addTab(self.history, "History")
        if (bar := self.tabs.tabBar()) is not None:
            identify(bar, "activity_tab_bar", "Now or History")
        self.tabs.currentChanged.connect(self._selection_changed)
        self.details = identify(QPlainTextEdit(), "activity_details", "Task details",
                                "What the selected task is, where it is, and for a failure its error and log lines")
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a task to see its details")
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(self.REFRESH_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(self.TICK_MS)
        self._tick.timeout.connect(self.refresh)
        self.resize(*parse_size(read_setting(app_settings(), ACTIVITY_SIZE_SETTING)))
        self._fitted = False  # (Fitted to its screen when it first shows: AW-9.)
        self._update_buttons()

    def _tree(self, ident: str, name: str, columns: Sequence[str]) -> QTreeWidget:
        tree = identify(QTreeWidget(), ident, name)
        tree.setColumnCount(len(columns))
        tree.setHeaderLabels(list(columns))
        tree.setUniformRowHeights(True)
        tree.setStyleSheet(CELL_PADDING_STYLE)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.currentItemChanged.connect(self._selection_changed)
        return tree

    # Showing and hiding: nothing runs while hidden

    def show_window(self) -> None:
        """Window › Activity and the status bar's click: show it, raised."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

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
        self.refresh()
        self._tick.start()

    def hideEvent(self, a0: Optional[QHideEvent]) -> None:
        super().hideEvent(a0)
        self._tick.stop()
        self._refresh_timer.stop()
        self._disconnect()
        size = self.size()
        app_settings().setValue(ACTIVITY_SIZE_SETTING, f"{size.width()},{size.height()}")

    @property
    def watching(self) -> bool:
        """Whether it is connected to its owners' signals (only while shown)."""
        return bool(self._connected)

    def _connect(self) -> None:
        if self._connected:
            return
        sources = self.sources
        pairs: list[tuple[Any, Callable[..., None]]] = [
            (sources.service.activityChanged, self.request_refresh), (sources.service.resultReady, self._io_event),
            (sources.cache.quitSavesChanged, self.request_refresh)]
        for runner in unique(sources.runners()):
            pairs.append((runner.finished, self._run_ended))
        for signal, slot in pairs:
            signal.connect(slot)
        self._connected = pairs
        activity.HISTORY.listeners.append(self.request_refresh)

    def _disconnect(self) -> None:
        for signal, slot in self._connected:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass  # (Its sender has gone.)
        self._connected = []
        if self.request_refresh in activity.HISTORY.listeners:
            activity.HISTORY.listeners.remove(self.request_refresh)

    # Refreshing

    @pyqtSlot()
    def request_refresh(self) -> None:
        """A refresh soon: requests within ``REFRESH_MS`` share one."""
        if self.isVisible() and not self._refresh_timer.isActive():
            self._refresh_timer.start()

    @pyqtSlot(object, object)
    def _io_event(self, _request: object, event: object) -> None:
        if isinstance(event, dict) and event.get("kind") in REFRESH_KINDS:
            self.request_refresh()

    @pyqtSlot(object)
    def _run_ended(self, _result: object) -> None:
        self.request_refresh()

    @pyqtSlot()
    def refresh(self) -> None:
        """Build the snapshot from memory and show it (rows updated in place, the selection kept)."""
        self.refreshes += 1
        self.snapshot = self.sources.snapshot()
        self._render_now()
        if activity.HISTORY.version != self._history_version:
            self._render_history()
        counts = self.snapshot.counts
        groups = {task.group for task in self.snapshot.tasks}
        self.summary.setText(f"{counts.text} · {len(self.snapshot.tasks):,} task"
                             f"{'' if len(self.snapshot.tasks) == 1 else 's'} listed"
                             + (f" · history {len(activity.HISTORY):,}" if len(activity.HISTORY) else ""))
        self.summary.setToolTip("I/O: " + counts.text + "\nGroups: " + (", ".join(
            activity.GROUP_TITLES[group] for group, _ in activity.GROUPS if group in groups) or "none"))
        self.pause_button.blockSignals(True)
        self.pause_button.setChecked(self.snapshot.user_paused)
        self.pause_button.blockSignals(False)
        self.pause_button.setText("Resume background I/O" if self.snapshot.user_paused else "Pause background I/O")
        self._selection_changed()

    def _render_now(self) -> None:
        """Show the snapshot in the Now tree: rows filled in place and, when any row's place changed (a task
        moved to another group or parent, a group or parent left), every item detached from its old parent
        before it is attached again, so no item is deleted with a parent that leaves (AW-1). Items taken
        out are held until the render ends; the tree's signals are restored whatever happens."""
        tree = self.now
        selected = self._selected_id()
        held: list[QTreeWidgetItem] = []  # (Taken out of the tree: alive until the render ends.)
        tree.blockSignals(True)
        try:
            self._place_rows(tree, held)
            if selected is not None and selected in self._items:
                tree.setCurrentItem(self._items[selected])
        finally:
            tree.blockSignals(False)
            held.clear()
        for column in range(1, len(NOW_COLUMNS)):
            tree.resizeColumnToContents(column)

    def _item(self, task: Task) -> QTreeWidgetItem:
        """The task's row, filled: the one shown before, or a new one if it has gone (a stale wrapper)."""
        item = self._items.get(task.id)
        if item is not None:
            try:
                item.setData(0, Qt.ItemDataRole.UserRole, task.id)
                self._fill(item, task)
                return item
            except RuntimeError:  # (Its C++ item was deleted: never reused.)
                self._items.pop(task.id, None)
        item = QTreeWidgetItem()
        item.setData(0, Qt.ItemDataRole.UserRole, task.id)
        self._fill(item, task)
        return item

    def _place_rows(self, tree: QTreeWidget, held: list[QTreeWidgetItem]) -> None:
        wanted: dict[str, QTreeWidgetItem] = {}
        children: dict[str, list[str]] = {}
        tops: dict[str, list[str]] = {}  # (By group.)
        known = {task.id for task in self.snapshot.tasks}
        for task in self.snapshot.tasks:
            wanted[task.id] = self._item(task)
            if task.parent and task.parent in known:
                children.setdefault(task.parent, []).append(task.id)
            else:
                tops.setdefault(task.group, []).append(task.id)

        def shown(task_id: str) -> int:
            return 1 + sum(shown(child) for child in children.get(task_id, []))
        groups: dict[str, QTreeWidgetItem] = {}  # (By group, in GROUPS' order.)
        for group, _title in activity.GROUPS:
            if group not in tops:
                continue
            item = self._groups.get(group) or QTreeWidgetItem()
            # (Counts the rows shown under it, children included, wherever their own group is: AW-13.)
            item.setText(0, activity.group_heading(group, sum(shown(top) for top in tops[group])))
            item.setData(0, Qt.ItemDataRole.UserRole, f"group:{group}")
            groups[group] = item
        shape = {"": [f"group:{group}" for group in groups],
                 **{f"group:{group}": list(ids) for group, ids in tops.items()},
                 **{task_id: list(ids) for task_id, ids in children.items()}}
        replaced = any(item is not self._items.get(task_id) for task_id, item in wanted.items()) or any(
            item is not self._groups.get(group) for group, item in groups.items())
        if shape != self._shape or replaced:
            # Detach everything first (children from their parents, then the top level), so each item is
            # parentless when it is placed again and none goes with a parent that is dropped.
            for item in (*self._items.values(), *self._groups.values()):
                try:
                    held.extend(item.takeChildren())
                except RuntimeError:
                    pass
            root = tree.invisibleRootItem()
            assert root is not None
            held.extend(root.takeChildren())
            root.addChildren([groups[name] for name in groups])
            for name, item in groups.items():
                item.addChildren([wanted[task_id] for task_id in tops[name]])
            for task_id, ids in children.items():
                wanted[task_id].addChildren([wanted[child] for child in ids])
            self._shape = shape
        for name, item in groups.items():
            item.setFirstColumnSpanned(True)
            item.setExpanded(f"group:{name}" not in self._collapsed)
        for task_id in children:
            wanted[task_id].setExpanded(task_id not in self._collapsed)
        self._items, self._groups = wanted, groups

    @staticmethod
    def _fill(item: QTreeWidgetItem, task: Task) -> None:
        texts = (task.title, task.tab, _name(task.folder) if task.folder else "", task.state_text,
                 task.progress.text() if task.progress is not None else "",
                 "" if task.elapsed is None else clock(task.elapsed),
                 "" if task.left is None else f"~{clock(task.left)}")
        tooltip = "\n".join(task.details)
        for column, text in enumerate(texts):
            if item.text(column) != text:
                item.setText(column, text)
            item.setToolTip(column, task.folder if column == 2 and task.folder else tooltip)
        brush = QBrush(QColor(AMBER)) if task.state in ("failed", "stalled") else QBrush()
        item.setForeground(3, brush)

    def _render_history(self) -> None:
        """Show the history, newest first: new entries put on top and dropped ones taken off the bottom, the
        rest left as they are (their scroll position and selection with them; AW-10). Each row's tooltip is
        the entry's own lines; the session's log lines are read only for the details pane."""
        self._history_version = activity.HISTORY.version
        entries = activity.HISTORY.entries()
        self._history = {entry.key: entry for entry in entries}
        tree = self.history
        tree.blockSignals(True)
        try:
            items = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
            shown = [str(item.data(0, Qt.ItemDataRole.UserRole)) for item in items if item is not None]
            keys = [entry.key for entry in entries]
            if shown and shown[0] in self._history:
                for index in reversed(range(len(shown))):
                    if shown[index] not in self._history:
                        tree.takeTopLevelItem(index)  # (Dropped from the history's oldest end.)
                fresh = entries[:keys.index(shown[0])]
            else:
                tree.clear()  # (First, or the history was cleared.)
                fresh = entries
            tree.insertTopLevelItems(0, [self._history_item(entry) for entry in fresh])
        finally:
            tree.blockSignals(False)
        if fresh:
            for column in range(len(HISTORY_COLUMNS)):
                tree.resizeColumnToContents(column)

    def _history_item(self, entry: activity.Finished) -> QTreeWidgetItem:
        took = "" if entry.started is None else clock(max(0.0, entry.ended - entry.started))
        item = QTreeWidgetItem([time.strftime("%H:%M:%S", time.localtime(entry.ended)), entry.title,
                                self.sources.tab_text(entry.owners), _name(entry.folder) if entry.folder else "",
                                activity.outcome_text(entry), took])
        item.setData(0, Qt.ItemDataRole.UserRole, entry.key)
        item.setToolTip(3, entry.folder)
        tooltip = "\n".join(self._history_details(entry, log=False))
        for column in (0, 1, 2, 4, 5):
            item.setToolTip(column, tooltip)
        if entry.outcome != "ok":
            item.setForeground(4, QBrush(QColor(AMBER)))
        return item

    def _history_details(self, entry: activity.Finished, *, log: bool = True) -> list[str]:
        took = "" if entry.started is None else f" · took {clock(max(0.0, entry.ended - entry.started))}"
        lines = [entry.title, f"Folder: {entry.folder}" if entry.folder else "",
                 f"For: {tab}" if (tab := self.sources.tab_text(entry.owners)) else "",
                 "Ended " + time.strftime("%H:%M:%S", time.localtime(entry.ended)) + took,
                 f"Outcome: {activity.outcome_text(entry)}",
                 f"Attempts: {entry.attempts}" if entry.attempts > 1 else "", *entry.details]
        lines = [line for line in lines if line]
        if log and entry.outcome != "ok":
            found = activity.LOG_LINES_HANDLER.about(entry.folder, entry.started, entry.ended)
            if found:
                lines += ["", "Log:", *found]
        return lines

    # Selection, details and buttons

    def _selected_id(self) -> Optional[str]:
        item = self.now.currentItem()
        value = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        return str(value) if value is not None else None

    def selected_task(self) -> Optional[Task]:
        if self.tabs.currentWidget() is not self.now:
            return None
        chosen = self._selected_id()
        return None if chosen is None else self.snapshot.by_id().get(chosen)

    def selected_entry(self) -> Optional[activity.Finished]:
        if self.tabs.currentWidget() is not self.history:
            return None
        item = self.history.currentItem()
        if item is None:
            return None
        return self._history.get(str(item.data(0, Qt.ItemDataRole.UserRole)))

    def _selection_changed(self, *_: object) -> None:
        task, entry = self.selected_task(), self.selected_entry()
        if task is not None:
            text = "\n".join(task.details)
            if task.state == "failed":
                log = activity.LOG_LINES_HANDLER.about(task.folder)
                if log:
                    text += "\n\nLog:\n" + "\n".join(log)
        elif entry is not None:
            text = "\n".join(self._history_details(entry))
        else:
            text = ""
        if self.details.toPlainText() != text:
            self.details.setPlainText(text)
        self._update_buttons()

    def available(self) -> dict[str, str]:
        """Each action's state for the selected row: "" if it can be used, else why not."""
        task, entry = self.selected_task(), self.selected_entry()
        result: dict[str, str] = {}
        for action in self.buttons:
            if action == "log":
                result[action] = ""
            elif task is not None:
                result[action] = ("" if action in task.actions else NOT_FOR.get(action, "Not for this task"))
                if action == "retry" and not result[action]:
                    result[action] = self.handler.retry_refusal(task.route)
            elif entry is not None:
                result[action] = self._entry_action(entry, action)
            else:
                result[action] = "Select a task first"
        return result

    def _entry_action(self, entry: activity.Finished, action: str) -> str:
        if action == "show":
            return "" if self.handler.show_target(entry.route, entry.owners) else NOT_FOR["show"]
        if action == "retry":
            return self.handler.retry_refusal(entry.route, entry.outcome, entry.owners)
        return "Not for a finished task"

    def _update_buttons(self) -> None:
        for action, why in self.available().items():
            button = self.buttons[action]
            button.setEnabled(not why)
            button.setToolTip(ACTION_TIPS[action][1] if not why else why)
        queued = [task for task in self.snapshot.tasks if task.state == "queued" and "cancel" in task.actions]
        self.cancel_queued_button.setEnabled(bool(queued))

    @pyqtSlot(QTreeWidgetItem)
    def _item_collapsed(self, item: QTreeWidgetItem) -> None:
        self._collapsed.add(str(item.data(0, Qt.ItemDataRole.UserRole)))

    @pyqtSlot(QTreeWidgetItem)
    def _item_expanded(self, item: QTreeWidgetItem) -> None:
        self._collapsed.discard(str(item.data(0, Qt.ItemDataRole.UserRole)))

    # The buttons

    def _route(self) -> tuple[Optional[Route], str, tuple[str, ...]]:
        task, entry = self.selected_task(), self.selected_entry()
        if task is not None:
            return task.route, task.folder, ()
        if entry is not None:
            return entry.route, entry.folder, entry.owners
        return None, "", ()

    @pyqtSlot()
    def _on_show(self) -> None:
        route, folder, owners = self._route()
        if route is not None:
            if route.kind == "question":
                self.handler.answer(route)
            else:
                self.handler.show(route, folder, owners)

    @pyqtSlot()
    def _on_log(self) -> None:
        self.handler.open_log()

    @pyqtSlot()
    def _on_cancel(self) -> None:
        task = self.selected_task()
        if task is not None and "cancel" in task.actions:
            self.handler.cancel(task)
            self.request_refresh()

    @pyqtSlot()
    def _on_retry(self) -> None:
        task, entry = self.selected_task(), self.selected_entry()
        if task is not None and "retry" in task.actions:
            self.handler.retry(task.route, task.folder)
        elif entry is not None and not self.handler.retry_refusal(entry.route, entry.outcome, entry.owners):
            self.handler.retry(entry.route, entry.folder, entry.owners)
        self.request_refresh()

    @pyqtSlot()
    def _on_stop_live(self) -> None:
        task = self.selected_task()
        if task is not None and "stop_live" in task.actions:
            self.handler.stop_live(task.route)
            self.request_refresh()

    @pyqtSlot(bool)
    def _on_pause(self, on: bool) -> None:
        self.sources.service.set_user_hold(on)
        self.refresh()

    @pyqtSlot()
    def _on_cancel_queued(self) -> None:
        self.handler.cancel_queued(self.snapshot)
        self.request_refresh()
