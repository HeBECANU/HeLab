"""The Activity window's model (Q62.1–Q62.5): what HeLab is doing, as plain data, without Qt.

``Task`` is one row of the window's Now list, ``Snapshot`` all of them at one moment, ``Finished`` one
entry of this session's history (``HISTORY``, the last ``HISTORY_SIZE``, newest first). The rules that
decide a task's state, its group and whether a finished one is kept are pure functions here; the window
(``helab.views.ActivityWindow``) reads each owner's memory, calls them, and renders the result. Nothing
here reads a disk or submits I/O.

Requests are read through ``RequestLike`` (the fields of ``helab.utils.io_service.IORequest`` used here),
so this module never imports Qt (``tests/test_headless_imports.py``'s ``PURE``).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import logging
import re
import threading
import time
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Protocol, Sequence, TYPE_CHECKING, TypeVar

from helab.utils.load_clock import LoadClock
from helab.utils.time_format import clock

if TYPE_CHECKING:
    from helab.analysis.runner_core import RunInfo

Group = Literal["loads", "saves", "live", "convert", "upkeep", "analysis", "scripts", "other"]
State = Literal["running", "queued", "paused", "stopping", "settling", "stalled", "waiting", "failed"]
Action = Literal["cancel", "retry", "show", "stop_live", "log", "answer"]
Outcome = Literal["ok", "failed", "cancelled"]

# The Now list's groups, in order, with their headings (Q62.2).
GROUPS: tuple[tuple[Group, str], ...] = (
    ("loads", "Loads and scans"), ("saves", "Saves"), ("live", "Live"), ("convert", "Conversions"),
    ("upkeep", "Cache upkeep"), ("analysis", "Analysis"), ("scripts", "Scripts"), ("other", "Other"))
GROUP_TITLES: dict[str, str] = dict(GROUPS)

# A running task with no progress this long says "no progress for M:SS" (a load's ``LoadClock`` rule).
STALL_SECONDS = LoadClock.STALL_SECONDS

HISTORY_SIZE = 200  # Q62.4: this session's last 200 finished tasks.
LOG_LINES = 500  # Warnings kept in memory for the details pane (``LogLines``).

# Operations by group (``group_of``); a load's own payload refines it (a save, a Live check).
LOAD_OPERATIONS = frozenset({"load", "cached", "list", "resolve", "details", "scan", "saved_list", "icons", "drives"})
SAVE_OPERATIONS = frozenset({"result_save", "scan_history", "subtree_save", "marker_save", "root_create",
                             "root_reassign", "root_remove"})
UPKEEP_OPERATIONS = frozenset({"raw_fill", "cache_admin", "cache_move", "invalidate", "volumes_verify",
                               "roots_verify", "trace_check"})
ANALYSIS_OPERATIONS = frozenset({"result_find"})
# ``cache_admin`` actions that write what the user keeps (flags, constants, presets, choices, last uses):
# a save, not upkeep.
ADMIN_SAVES = frozenset({"folder_prefs", "convert_prefs", "folder_constants", "presets", "folder_choice",
                         "mark_used", "adopt_result"})
# Successful requests the history leaves out (Q~2): frequent small work that would push everything else
# out of the last 200 (a folder's details scan and cached read come with each folder browsed into). A
# conversion's passes too: Live's auto-convert runs one with each check, and the Live session or the GUI
# conversion is the entry (AW-2). Failures and cancellations of anything are always kept.
NOT_KEPT_WHEN_OK = frozenset({"list", "resolve", "saved_list", "details", "cached", "icons", "subtree_save",
                              "volumes_verify", "roots_verify", "drives", "trace_check", "convert"})


@dataclass(frozen=True)
class Progress:
    """How far a task is: files done of total, bytes read of total (None: not known)."""
    done: Optional[int] = None
    total: Optional[int] = None
    read_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    noun: str = "file"

    @property
    def fraction(self) -> Optional[float]:
        if self.total_bytes:
            return min(1.0, (self.read_bytes or 0) / self.total_bytes)
        if self.total:
            return min(1.0, (self.done or 0) / self.total)
        return None

    def text(self) -> str:
        """``123 of 579 files · 21 %``; "" when nothing is known."""
        if self.total is None or self.done is None:
            return ""
        if not self.total:
            return f"no {self.noun}s"
        fraction = self.fraction
        return (f"{self.done:,} of {self.total:,} {self.noun}{'' if self.total == 1 else 's'}"
                + ("" if fraction is None else f" · {fraction:.0%}"))


@dataclass(frozen=True)
class Route:
    """What the window needs to reach a task's owner (its kind and keys); plain data."""
    kind: str = "none"  # io, live, conversion, question, analysis, probe, reload, move, save
    owner: str = ""
    operation: str = ""
    path: str = ""
    job: str = ""  # An analysis job's id.


@dataclass(frozen=True)
class Task:
    """One row of the Now list. ``details`` are the details pane's lines; ``actions`` what may be done
    to it now; ``parent`` the row it sits under (a Live session's check, save and conversion)."""
    id: str
    group: Group
    title: str
    folder: str
    tab: str
    state: State
    state_text: str
    progress: Optional[Progress] = None
    elapsed: Optional[float] = None
    left: Optional[float] = None
    details: tuple[str, ...] = ()
    actions: frozenset[Action] = frozenset()
    route: Route = Route()
    parent: str = ""


@dataclass(frozen=True)
class Counts:
    """The status bar's app-wide counts (``IOService.activity_counts``), so both say the same."""
    running: int = 0
    paused: int = 0
    queued: int = 0
    stopping: int = 0
    text: str = "Ready"


@dataclass(frozen=True)
class Snapshot:
    tasks: tuple[Task, ...] = ()
    counts: Counts = Counts()
    user_paused: bool = False
    taken_at: float = 0.0

    def by_id(self) -> dict[str, Task]:
        return {task.id: task for task in self.tasks}


@dataclass(frozen=True)
class Finished:
    """One entry of the session's history: a task that ended (``outcome``), with what the window needs
    to show it and retry it (``route``). Times are wall-clock seconds; ``owners`` are the I/O owners
    (tabs, plots) it worked for, named when shown."""
    id: str
    group: Group
    title: str
    folder: str
    ended: float
    outcome: Outcome
    message: str = ""
    started: Optional[float] = None
    owners: tuple[str, ...] = ()
    attempts: int = 1
    route: Route = Route()
    details: tuple[str, ...] = ()
    seq: int = 0  # Its place in the session's history (``History.add``), so ``key`` is unique (AW-10).

    @property
    def failed(self) -> bool:
        return self.outcome == "failed"

    @property
    def key(self) -> str:
        """Unique among the session's entries: two Live sessions of a folder share their ``id``."""
        return f"{self.id}#{self.seq}"


class History:
    """This session's finished tasks, the last ``size`` (the oldest dropped: a session-only list). Added
    to on the GUI thread only: every reporter runs there (the analysis runner reports from a slot that Qt
    calls on it), and ``listeners`` (the open window) are called there."""

    def __init__(self, size: int = HISTORY_SIZE) -> None:
        self._entries: deque[Finished] = deque(maxlen=size)
        self.listeners: list[Callable[[], None]] = []
        self.version = 0  # Counts changes, so a view redraws only after one.
        self._serial = 0  # The next entry's ``seq``.

    def add(self, entry: Finished) -> None:
        assert threading.current_thread() is threading.main_thread(), "History.add off the GUI thread"
        self._serial += 1
        self._entries.append(replace(entry, seq=self._serial))
        self.version += 1
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:  # (A view never breaks the owner reporting its task's end: AW-6.)
                logging.exception("Activity history listener")

    def entries(self) -> list[Finished]:
        """Newest first."""
        return list(reversed(self._entries))

    def clear(self) -> None:
        self._entries.clear()
        self.listeners.clear()
        self.version += 1

    def __len__(self) -> int:
        return len(self._entries)


HISTORY = History()


def record(entry: Finished) -> None:
    """Report a finished task (GUI thread): one call by each owner when its task ends."""
    HISTORY.add(entry)


class LogLines(logging.Handler):
    """The session's last ``LOG_LINES`` warnings and errors, in memory, for the details pane: ``about``
    gives those naming a folder within a time span. Added to the root logger by the main window, removed
    when it closes."""

    def __init__(self, size: int = LOG_LINES) -> None:
        super().__init__(logging.WARNING)
        self._lines: deque[tuple[float, str]] = deque(maxlen=size)
        self._guard = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = f"{time.strftime('%H:%M:%S', time.localtime(record.created))} {record.levelname} {record.getMessage()}"
        except Exception:  # (A record whose arguments don't format: its template.)
            line = f"{record.levelname} {record.msg}"
        with self._guard:
            self._lines.append((record.created, line.splitlines()[0] if line else line))

    def about(self, folder: str, since: Optional[float] = None, until: Optional[float] = None,
              limit: int = 20) -> list[str]:
        """The lines that name ``folder`` (wall-clock ``since``…``until``, a minute either side), oldest first."""
        if not folder:
            return []
        start = -float("inf") if since is None else since - 60.0
        end = float("inf") if until is None else until + 60.0
        # (The folder itself or a path inside it: not a longer name that starts with it, run10 for run1: AW-12.)
        named = re.compile(re.escape(folder.rstrip("/\\")) + r"(?![\w\-])")
        with self._guard:
            lines = [line for at, line in self._lines if start <= at <= end and named.search(line)]
        return lines[-limit:]

    def clear(self) -> None:
        with self._guard:
            self._lines.clear()


LOG_LINES_HANDLER = LogLines()


def install_log_lines() -> LogLines:
    """Add ``LOG_LINES_HANDLER`` to the root logger (once)."""
    root = logging.getLogger()
    if LOG_LINES_HANDLER not in root.handlers:
        root.addHandler(LOG_LINES_HANDLER)
    return LOG_LINES_HANDLER


def remove_log_lines() -> None:
    logging.getLogger().removeHandler(LOG_LINES_HANDLER)


class RequestLike(Protocol):
    """The fields of an I/O request (``IORequest``) the Activity model reads."""
    owner: str
    generation: int
    path: str
    operation: str
    payload: dict[str, Any]
    timeout: float
    started: float
    last_activity: float
    current_file: Optional[str]
    attempt: int
    completed: bool
    paused: bool
    lane: str
    retirement_reason: str
    retired_at: Optional[float]
    last_event: str
    queued_at: float


Request = TypeVar("Request", bound=RequestLike)


def key(request: RequestLike) -> tuple[str, int, str, str]:
    """A request's identity (``IOService._key``): a retry and the attempt it replaces share it."""
    return request.owner, request.generation, request.path, request.operation


def request_id(request: RequestLike) -> str:
    return "io:" + ":".join(str(part) for part in key(request))


def is_save(request: RequestLike) -> bool:
    """A load that saves data shown in RAM (``FolderCache.save``: Live's autosaves and stop-saves)."""
    return request.operation == "load" and bool(request.payload.get("save"))


def is_live_check(request: RequestLike) -> bool:
    return request.operation == "load" and bool(request.payload.get("live"))


def group_of(operation: str, payload: Mapping[str, Any], *, finishing: bool = False, admin: str = "") -> Group:
    """Which group an I/O request is listed under (Q62.2)."""
    if operation == "load":
        if payload.get("live"):
            return "live"
        return "saves" if payload.get("save") or finishing else "loads"
    if operation == "convert":
        return "convert"
    if operation == "cache_admin":
        return "saves" if admin in ADMIN_SAVES else "upkeep"
    for group, operations in (("loads", LOAD_OPERATIONS), ("saves", SAVE_OPERATIONS),
                              ("upkeep", UPKEEP_OPERATIONS), ("analysis", ANALYSIS_OPERATIONS)):
        if operation in operations:
            return group  # type: ignore[return-value]
    return "other"


def kept_in_history(operation: str, payload: Mapping[str, Any], outcome: Outcome) -> bool:
    """Whether a finished request goes in the history (Q~2): every failure and cancellation; successes
    but Live checks (the Live session is the entry) and frequent small work (``NOT_KEPT_WHEN_OK``)."""
    if outcome != "ok":
        return True
    if operation == "load" and payload.get("live"):
        return False
    return operation not in NOT_KEPT_WHEN_OK


def wall(monotonic_at: float, now_monotonic: Optional[float] = None, now_wall: Optional[float] = None) -> float:
    """A ``time.monotonic()`` instant as wall-clock seconds."""
    now_monotonic = time.monotonic() if now_monotonic is None else now_monotonic
    now_wall = time.time() if now_wall is None else now_wall
    return now_wall - (now_monotonic - monotonic_at)


def finished_request(request: RequestLike, outcome: Outcome, message: str, *, label: str,
                     owners: Sequence[str], admin: str = "", finishing: bool = False) -> Finished:
    """A history entry for an I/O request that ended (``IOService``'s report)."""
    started = wall(request.started) if request.started else None
    return Finished(request_id(request), group_of(request.operation, request.payload, finishing=finishing,
                                                  admin=admin),
                    label + (f": {admin}" if admin else ""), request.path, time.time(), outcome,
                    message.removesuffix(" — Retry"), started, tuple(owners), request.attempt,
                    Route("io", request.owner, request.operation, request.path))


def stopping_text(request: RequestLike, now: float) -> str:
    age = None if request.retired_at is None else max(0.0, now - request.retired_at)
    why = request.retirement_reason or "cancelled"
    return f"stopping ({clock(age)})" if age is not None else "stopping" + ("" if why == "cancelled" else f": {why}")


@dataclass(frozen=True)
class About:
    """What a request's owner says about it, from memory (the window's sources fill it): its title,
    group, tab(s), progress and time, the file it is on, extra detail lines, what may be done to it and
    how to reach its owner."""
    title: str
    group: Group
    tab: str = ""
    progress: Optional[Progress] = None
    elapsed: Optional[float] = None
    left: Optional[float] = None
    stalled: Optional[float] = None  # A load clock's ``stalled_for`` (None: use the request's last event).
    file: str = ""
    notes: tuple[str, ...] = ()
    actions: frozenset[Action] = frozenset()
    route: Route = Route()
    parent: str = ""
    writing: bool = True  # A finished load: whether it is writing the disk cache now.


LANES = {"foreground": "current tab", "background": "background", "local": "local disk cache"}


def request_state(where: str, request: RequestLike, now: float, *, why_paused: str = "", why_held: str = "",
                  blocked: bool = False, position: int = 0, stalled: Optional[float] = None,
                  writing: bool = True) -> tuple[State, str]:
    """A request's state and its text: ``where`` is the IOService list it is in (active, pending,
    retired). ``why_paused`` / ``why_held``: why it is paused or held while queued; ``blocked``: a retry
    waiting for the attempt it replaces; ``position``: its place among queued requests (1: next)."""
    if where == "retired":
        return "stopping", stopping_text(request, now)
    if where == "pending":
        if blocked:
            return "queued", "waits for the previous attempt to stop"
        if why_held:
            return "queued", f"held: {why_held}"
        return "queued", f"queued ({ordinal(position)})" if position else "queued"
    if request.paused:
        return "paused", f"paused: {why_paused}" if why_paused else "paused"
    if request.completed:
        return "running", "saving its cached data" if writing else "finishing"
    quiet = stalled if stalled is not None else now - request.last_activity
    if quiet >= STALL_SECONDS:
        return "stalled", f"no progress for {clock(quiet)}"
    return "running", "running"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def request_details(request: RequestLike, about: About, where: str, now: float, *, pid: Optional[int] = None,
                    waiting: Optional[RequestLike] = None, attempts: int = 1) -> tuple[str, ...]:
    """The details pane's lines for a request (memory only)."""
    lines = [f"{about.title} · {request.operation}" + (f" · attempt {request.attempt}" if request.attempt > 1 else ""),
             f"Folder: {request.path}" if request.path else ""]
    if about.tab:
        lines.append(f"For: {about.tab}")
    if where == "pending":
        lines.append(f"Queued {clock(now - request.queued_at)} ago")
    else:
        lines.append(f"Lane: {LANES.get(request.lane, request.lane or 'not started')}")
        lines.append(f"Helper process: {pid}" if pid else "Helper process: starting")
        if request.started:
            lines.append("Started: " + time.strftime("%H:%M:%S", time.localtime(wall(request.started, now))))
        lines.append(f"Last heard from {clock(max(0.0, now - request.last_activity))} ago"
                     + (f" ({request.last_event})" if request.last_event else ""))
    if about.file or request.current_file:
        lines.append(f"File: {about.file or request.current_file}")
    if about.progress is not None and about.progress.text():
        lines.append(f"Progress: {about.progress.text()}")
    if where == "retired":
        lines.append(f"Stopping: {request.retirement_reason or 'cancelled'} · its slot stays taken until its "
                     "process has exited")
        if waiting is not None:
            lines.append(f"Attempt {waiting.attempt} of {attempts} starts when it exits"
                         if waiting.attempt > request.attempt else "Asked for again: starts when it exits")
    lines.extend(about.notes)
    return tuple(line for line in lines if line)


def io_tasks(active: Iterable[Request], pending: Iterable[Request], retired: Iterable[Request],
             about: Callable[[Request], About], now: float, *,
             why_paused: Callable[[Request], str] = lambda request: "",
             why_held: Callable[[Request], str] = lambda request: "",
             pid: Callable[[Request], Optional[int]] = lambda request: None,
             attempts: int = 1) -> list[Task]:
    """The rows for IOService's requests: running and paused, then stopping, then queued (dispatch
    order). A retry held until the attempt it replaces exits is shown once, on that attempt's row."""
    retired = list(retired)
    retired_keys = {key(request) for request in retired}
    pending = list(pending)
    waiting = {key(request): request for request in pending if key(request) in retired_keys}
    tasks: list[Task] = []
    position = 0
    for where, requests in (("active", list(active)), ("retired", retired), ("pending", pending)):
        for request in requests:
            if where == "pending" and key(request) in retired_keys:
                continue  # (Shown on the stopping attempt's row.)
            if where == "pending":
                position += 1
            told = about(request)
            state, text = request_state(where, request, now, why_paused=why_paused(request),
                                        why_held=why_held(request) if where == "pending" else "",
                                        position=position, stalled=told.stalled, writing=told.writing)
            actions: set[Action] = {*told.actions, "log"}
            if where == "retired":
                actions.discard("cancel")
            elapsed = told.elapsed if told.elapsed is not None else (
                None if where == "pending" or not request.started else now - request.started)
            tasks.append(Task(request_id(request), told.group, told.title, request.path, told.tab, state, text,
                              told.progress, elapsed, None if state == "stalled" else told.left,
                              request_details(request, told, where, now, pid=pid(request),
                                              waiting=waiting.get(key(request)), attempts=attempts),
                              frozenset(actions), told.route, told.parent))
    return tasks


def ordered(tasks: Iterable[Task]) -> tuple[Task, ...]:
    """Tasks in group order (``GROUPS``), each group's in the order given; children after their parent."""
    rank = {group: index for index, (group, _) in enumerate(GROUPS)}
    return tuple(sorted(tasks, key=lambda task: rank.get(task.group, len(rank))))


def group_heading(group: str, count: int) -> str:
    return f"{GROUP_TITLES.get(group, group)} ({count:,})"


def outcome_text(entry: Finished) -> str:
    return {"ok": "done", "failed": "✕ failed", "cancelled": "cancelled"}[entry.outcome] + (
        f": {entry.message}" if entry.message and entry.outcome != "ok" else "")


def analysis_tasks(jobs: Iterable[RunInfo], now: float, *, tab: Callable[[str], str] = lambda owner: "",
                   parent: str = "") -> list[Task]:
    """The rows for the analysis runner's jobs (``AnalysisQueue.jobs``): queued, running, stopping (its
    cancel asked, ``compute`` not yet returned)."""
    tasks = []
    position = 0
    for job in jobs:
        if job.state == "queued":
            position += 1
            text = f"queued ({ordinal(position)})"
        else:
            text = "stopping" if job.state == "stopping" else "computing"
        state: State = "queued" if job.state == "queued" else "stopping" if job.state == "stopping" else "running"
        elapsed = None if job.started_at is None else max(0.0, now - job.started_at)
        where = tab(job.owner)
        details = (f"{job.analysis} · {job.action}" + (" · following Live" if job.live else ""),
                   f"Plot: {where}" if where else "", f"Job {job.job_id} on the analysis worker",
                   "Queued " + time.strftime("%H:%M:%S", time.localtime(job.queued_wall)),
                   "" if job.started_wall is None else
                   "Started " + time.strftime("%H:%M:%S", time.localtime(job.started_wall)))
        actions: set[Action] = {"log", "show"} if where else {"log"}
        if job.state != "stopping":
            actions.add("cancel")
        tasks.append(Task(f"analysis:{job.job_id}", "analysis", f"{job.analysis}: {job.action}", "", where, state,
                          text, None, elapsed, None, tuple(line for line in details if line), frozenset(actions),
                          Route("analysis", job.owner, job=job.job_id), parent))
    return tasks

