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

from helab.utils import activity
from helab.utils.activity import About, Action, Progress, Route, Snapshot, Task
from helab.utils.folder_cache import FolderCache, SharedJob
from helab.utils.io_service import IORequest, IOService
from helab.utils.time_format import clock

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
            if owner.explorer is not None and owner.explorer.live_control.session(path) is not None:
                return live_id(owner.explorer, path)
        return ""

    @staticmethod
    def _conversion_parent(found: Sequence[Owner], path: str) -> str:
        for owner in found:
            if owner.explorer is not None and path in owner.explorer.converter.conversions:
                return conversion_id(owner.explorer, path)
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
        tasks = []
        for folder, state, started in scripts.probe_activity():
            text = {"importing": "test-importing", "starting": "starting its test import",
                    "stopping": "stopping (killed)", "queued": "queued"}[state]
            tasks.append(Task(f"probe:{folder}", "scripts", "Test-import scripts", folder, "",
                              "queued" if state == "queued" else "stopping" if state == "stopping" else "running",
                              text, None, None if started is None else max(0.0, now - started), None,
                              (f"Test import of the script folder {folder} in a separate process",
                               "Its own time limits end it (Q49.3 (b))"), frozenset({"log"}),
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
