"""GitHub's side of the update check: the requests, their replies trimmed and parsed, the CI rule, and the
ETag cache. Pure: no Qt, no network. ``check`` is the whole check as a generator: it yields each
``Request`` and is sent back a ``Fetched``, so the Qt transport (``helab.updates.check``) and the tests'
fake one drive the same code.

Only GETs to ``API`` (a constant), without a token: drafts stay invisible, and GitHub allows 60 requests
an hour per address, of which a 304 (the ETag matched) costs none.
"""
from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, cast

from helab.build_info import BuildInfo
from helab.updates.versions import (
    BRANCH, BranchFacts, Commit, Facts, Release, newer_releases, parse_version)

API = "https://api.github.com"
# The known repos (no free-text repo: a typo or a stranger's fork can never become the update source).
REPOSITORIES = ("HeBECANU/HeLab", "TonyXTYan/HeLab")
DEFAULT_REPOSITORY = REPOSITORIES[0]
OSES = ("macos", "windows", "ubuntu")
# CI's required jobs, per OS: "<os> + py3.13 / Tests (1/3)", "… / Converter backends", "… / Build".
CI_PYTHON = "py3.13"
CI_APP = "github-actions"
# How many of a branch's newer commits a check looks at for green CI, newest first.
MAX_CI_LOOKUPS = 5
# How many newer releases a check tries for one on main.
MAX_MAIN_LOOKUPS = 3
TIMEOUT_MS = 10_000  # Qt's transfer timeout: time without progress.

JsonTrim = Callable[[Any], Any]


@dataclass(frozen=True)
class Request:
    path: str  # After ``API``, with its query.
    trim: JsonTrim  # What of the reply is kept (and cached).

    @property
    def url(self) -> str:
        return API + self.path


@dataclass(frozen=True)
class Fetched:
    status: int  # HTTP status (304 already replaced by the cached 200); 0 when it never arrived
    data: Any = None  # The trimmed reply, for a 200
    error: str = ""  # Why it failed, in words

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error


class CheckFailed(Exception):
    """The check couldn't finish; its message says why, for the manual check's window."""


def headers(version: str) -> dict[str, str]:
    """Every request's headers: nothing identifies the PC or its user."""
    return {"User-Agent": f"HeLab/{version}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def failure(status: int, reply_headers: dict[str, str], network_error: str, now: float) -> str:
    """A failed request in words; "" when it didn't fail (200 or 304)."""
    if network_error and status == 0:
        return f"Couldn't reach GitHub ({network_error})."
    lowered = {key.lower(): value for key, value in reply_headers.items()}
    if status in (403, 429) and lowered.get("x-ratelimit-remaining") == "0":
        try:
            wait = max(0, int(float(lowered.get("x-ratelimit-reset", "0")) - now))
            when = f" for about {max(1, round(wait / 60))} min"
        except ValueError:
            when = ""
        return (f"GitHub's limit of 60 requests an hour from this network is used up{when}. "
                "HeLab checks again later.")
    if status in (200, 304):
        return ""
    return f"GitHub answered {status}."


# -- Trimming and parsing (what's kept of each reply is all HeLab reads) ---------------------------------

def _text(item: dict[str, Any], key: str, limit: int = 0) -> str:
    value = item.get(key)
    text = value if isinstance(value, str) else ""
    return text[:limit] if limit else text


def _items(data: Any, key: str = "") -> list[dict[str, Any]]:
    value = data.get(key) if key and isinstance(data, dict) else data
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def trim_releases(data: Any) -> Any:
    kept = []
    for item in _items(data):
        if item.get("draft") is True:
            continue  # (Never listed without a token; dropped anyway.)
        assets = [[_text(a, "name"), _text(a, "browser_download_url")] for a in _items(item, "assets")]
        kept.append({"tag_name": _text(item, "tag_name"), "name": _text(item, "name", 200),
                     "prerelease": item.get("prerelease") is True, "published_at": _text(item, "published_at"),
                     "html_url": _text(item, "html_url"), "body": _text(item, "body", 20_000), "assets": assets})
    return kept


def parse_releases(data: Any) -> tuple[Release, ...]:
    releases = []
    for item in _items(data):
        tag = _text(item, "tag_name")
        version = parse_version(tag)
        if version is None or item.get("draft") is True:
            continue
        assets = tuple((str(a[0]), str(a[1])) for a in item.get("assets") or () if isinstance(a, list) and len(a) == 2)
        releases.append(Release(tag, str(version), item.get("prerelease") is True or version.is_prerelease,
                                _text(item, "published_at"), _text(item, "html_url"), _text(item, "body"),
                                _text(item, "name"), assets))
    return tuple(releases)


def trim_refs(data: Any) -> Any:
    kept = []
    for item in _items(data):
        target = item.get("object")
        if isinstance(target, dict):
            kept.append({"ref": _text(item, "ref"), "type": _text(target, "type"), "sha": _text(target, "sha")})
    return kept


def parse_refs(data: Any) -> dict[str, tuple[str, str]]:
    """``refs/tags/<tag>`` → (object type, sha): "commit" for a lightweight tag, "tag" for an annotated one."""
    return {_text(item, "ref").removeprefix("refs/tags/"): (_text(item, "type"), _text(item, "sha"))
            for item in _items(data) if _text(item, "ref").startswith("refs/tags/")}


def trim_tag(data: Any) -> Any:
    target = data.get("object") if isinstance(data, dict) else None
    return {"type": _text(target, "type"), "sha": _text(target, "sha")} if isinstance(target, dict) else {}


def _commit(item: dict[str, Any]) -> dict[str, Any]:
    inner = item.get("commit")
    inner = inner if isinstance(inner, dict) else {}
    committer = inner.get("committer")
    message = _text(inner, "message").split("\n", 1)[0][:200]
    return {"sha": _text(item, "sha"), "subject": message,
            "date": _text(committer, "date") if isinstance(committer, dict) else "", "html_url": _text(item, "html_url"),
            "parents": [_text(parent, "sha") for parent in _items(item, "parents")]}


def trim_compare(data: Any) -> Any:
    if not isinstance(data, dict):
        return {}
    return {"status": _text(data, "status"), "ahead_by": data.get("ahead_by") if isinstance(data.get("ahead_by"), int) else 0,
            "commits": [_commit(item) for item in _items(data, "commits")]}


def parse_compare(data: Any) -> tuple[str, tuple[Commit, ...]]:
    """The compare's status and its commits newest first (GitHub lists them oldest first)."""
    if not isinstance(data, dict):
        return "", ()
    commits = [Commit(_text(c, "sha"), _text(c, "subject"), _text(c, "date"), _text(c, "html_url"))
               for c in _items(data, "commits") if _text(c, "sha")]
    return _text(data, "status"), tuple(reversed(commits))


def branch_line(data: Any, base: str) -> tuple[tuple[Commit, ...], bool]:
    """The branch's own newer commits, newest first: its first-parent chain from the tip, down to ``base`` (the
    running commit), keeping only commits that contain ``base`` (a fast-forward from it). Never a commit merged
    in from another branch: those are the branch's state only through the merge. And whether the chain may go on
    past what GitHub listed (a compare lists at most 250 commits, the newest, so the "+N" is then a floor)."""
    if not isinstance(data, dict):
        return (), False
    items = [item for item in _items(data, "commits") if _text(item, "sha")]
    ahead_by = data.get("ahead_by")
    more = isinstance(ahead_by, int) and ahead_by > len(items)
    listed = {_text(item, "sha"): item for item in items}
    if not listed:
        return (), more

    def parents(sha: str) -> list[str]:
        found = listed[sha].get("parents")
        return [str(parent) for parent in found if isinstance(parent, str)] if isinstance(found, list) else []

    # A listed commit contains base when a parent is base, or a listed parent contains it. A parent not listed is
    # an ancestor of base (the compare lists what base lacks), unless the list was cut short: then unknown, and
    # taken as containing it (the updater checks the ancestry again before it moves anything).
    contains: dict[str, bool] = {}
    for start in listed:
        stack = [start]
        while stack:
            sha = stack[-1]
            if sha in contains:
                stack.pop()
                continue
            waiting = [parent for parent in parents(sha) if parent in listed and parent not in contains]
            if waiting:
                stack.extend(waiting)
                continue
            stack.pop()
            contains[sha] = any(parent == base or (contains[parent] if parent in listed else more)
                                for parent in parents(sha))
    children = {parent for sha in listed for parent in parents(sha)}
    tips = [sha for sha in listed if sha not in children]
    sha = tips[0] if len(tips) == 1 else _text(items[-1], "sha")  # (GitHub lists the head last.)
    line: list[Commit] = []
    while sha in listed and contains.get(sha) and len(line) < len(listed):
        item = listed[sha]
        line.append(Commit(sha, _text(item, "subject"), _text(item, "date"), _text(item, "html_url")))
        first = parents(sha)
        sha = first[0] if first else ""
    return tuple(line), more and sha not in (base, "")


def trim_check_runs(data: Any) -> Any:
    kept = []
    for item in _items(data, "check_runs"):
        app = item.get("app")
        kept.append({"id": item.get("id") if isinstance(item.get("id"), int) else 0, "name": _text(item, "name"),
                     "status": _text(item, "status"), "conclusion": _text(item, "conclusion"),
                     "app": _text(app, "slug") if isinstance(app, dict) else ""})
    total = data.get("total_count") if isinstance(data, dict) else 0
    return {"total_count": total if isinstance(total, int) else 0, "check_runs": kept}


def ci_state(data: Any) -> tuple[str, str]:
    """One commit's CI from its check runs: ("green", "") when it passed on all three OSes, else
    ("pending", why) or ("red", why).

    Only GitHub Actions' runs count (another app can't post a fake success). For each OS, the Python 3.13
    jobs (``<os> + py3.13 / …``) must include a Tests job and the Build job, and each of those names must
    have succeeded: of a name's runs (a re-run, or a push's and a pull request's run of one commit) the
    newest that isn't skipped counts, and a name that was only skipped or cancelled is not green. Other
    jobs (Docs, compatibility, the release job) don't count. The number of test groups isn't fixed, so a
    CI that grows a group still passes."""
    runs = [run for run in _items(data, "check_runs") if run.get("app") == CI_APP]
    if isinstance(data, dict) and isinstance(data.get("total_count"), int) and data["total_count"] > len(
            _items(data, "check_runs")):
        return "pending", "more check runs than one page lists"
    pending: list[str] = []
    red: list[str] = []
    for os_name in OSES:
        prefix = f"{os_name} + {CI_PYTHON} / "
        names: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            name = _text(run, "name")
            if name.startswith(prefix):
                names.setdefault(name[len(prefix):], []).append(run)
        if not any(job.startswith("Tests") for job in names) or "Build" not in names:
            pending.append(f"{os_name}: no Tests or Build job yet")
            continue
        for job, found in sorted(names.items()):
            ran = sorted((run for run in found if run.get("conclusion") != "skipped"),
                         key=lambda run: int(run.get("id") or 0))
            if not ran:
                red.append(f"{os_name} {job}: skipped")
                continue
            newest = ran[-1]
            if newest.get("status") != "completed":
                pending.append(f"{os_name} {job}: {_text(newest, 'status') or 'not started'}")
            elif newest.get("conclusion") != "success":
                red.append(f"{os_name} {job}: {_text(newest, 'conclusion') or 'no result'}")
    if red:
        return "red", "; ".join(red)
    if pending:
        return "pending", "; ".join(pending)
    return "green", ""


# -- The check ------------------------------------------------------------------------------------------

def releases_request(repo: str) -> Request:
    return Request(f"/repos/{repo}/releases?per_page=100", trim_releases)


def tags_request(repo: str) -> Request:
    return Request(f"/repos/{repo}/git/matching-refs/tags/v", trim_refs)


def tag_request(repo: str, sha: str) -> Request:
    return Request(f"/repos/{repo}/git/tags/{sha}", trim_tag)


def compare_request(repo: str, base: str, head: str) -> Request:
    return Request(f"/repos/{repo}/compare/{base}...{head}", trim_compare)


def check_runs_request(repo: str, sha: str) -> Request:
    return Request(f"/repos/{repo}/commits/{sha}/check-runs?per_page=100", trim_check_runs)


Check = Generator[Request, Fetched, Facts]


def _need(fetched: Fetched) -> Any:
    if not fetched.ok:
        raise CheckFailed(fetched.error or f"GitHub answered {fetched.status}.")
    return fetched.data


def check(repo: str, commit: str, version: str, mode: str, branch: str, prereleases: bool) -> Check:
    """One check of ``repo`` for a run of ``commit`` (``version``): its releases and their tags, which of
    the newer ones is on main, and in branch mode ``branch``'s own newer commits (its first-parent line) and the
    newest green one."""
    releases = parse_releases(_need((yield releases_request(repo))))
    refs = parse_refs(_need((yield tags_request(repo))))
    tags: dict[str, str] = {}
    annotated = 0
    for release in releases:
        kind, sha = refs.get(release.tag, ("", ""))
        if kind == "commit":
            tags[release.tag] = sha
        elif kind == "tag" and annotated < 10:  # (Older releases' annotated tags; cached for good.)
            annotated += 1
            fetched = yield tag_request(repo, sha)
            if fetched.ok and fetched.data.get("type") == "commit":
                tags[release.tag] = fetched.data["sha"]
    facts = Facts(repo, releases, tuple(tags.items()))
    on_main: list[str] = []
    off_main: list[str] = []
    build = BuildInfo(version=version, commit=commit)
    for release in newer_releases(build, facts, prereleases)[:MAX_MAIN_LOOKUPS]:
        tag_commit = tags.get(release.tag)
        if not tag_commit:
            continue
        fetched = yield compare_request(repo, tag_commit, "main")
        state = parse_compare(_need(fetched))[0] if fetched.status != 404 else "missing"
        # (base...head: "ahead" or "identical" when main contains the tag's commit.)
        (on_main if state in ("ahead", "identical") else off_main).append(release.tag)
        if on_main:
            break
    branch_facts = None
    if mode == BRANCH and branch and commit != "unknown":
        fetched = yield compare_request(repo, commit, branch)
        if fetched.status == 404:
            branch_facts = BranchFacts(branch, "missing")
        else:
            data = _need(fetched)
            state = parse_compare(data)[0]
            candidates, more = branch_line(data, commit)
            ci: list[tuple[str, str]] = []
            target = None
            if state == "ahead":
                for candidate in candidates[:MAX_CI_LOOKUPS]:
                    found, why = ci_state(_need((yield check_runs_request(repo, candidate.sha))))
                    ci.append((candidate.sha, found if not why else f"{found}: {why}"))
                    if found == "green":
                        target = candidate
                        break
            branch_facts = BranchFacts(branch, state, candidates, tuple(ci), target, more)
    return Facts(repo, releases, tuple(tags.items()), tuple(off_main), tuple(on_main), branch_facts)


def drive(steps: Check, fetch: Callable[[Request], Fetched]) -> Facts:
    """Run a check to its end with a synchronous ``fetch`` (the cache replay, the tests)."""
    try:
        request = next(steps)
        while True:
            request = steps.send(fetch(request))
    except StopIteration as done:
        return cast(Facts, done.value)


# -- The ETag cache --------------------------------------------------------------------------------------

class EtagCache:
    """Each URL's last ETag and trimmed reply, in ``<app folder>/updates/github-cache.json``. A missing or
    malformed file is an empty cache; writes are a temporary file, then a rename."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                self.entries = {url: entry for url, entry in loaded["entries"].items()
                                if isinstance(entry, dict) and isinstance(entry.get("etag"), str)}
        except (OSError, ValueError):
            pass

    def etag(self, url: str) -> str:
        entry = self.entries.get(url)
        return str(entry["etag"]) if entry else ""

    def data(self, url: str) -> Any:
        entry = self.entries.get(url)
        return entry.get("data") if entry else None

    def has(self, url: str) -> bool:
        return url in self.entries

    def put(self, url: str, etag: str, data: Any) -> None:
        if etag:
            self.entries[url] = {"etag": etag, "data": data}
        else:
            self.entries.pop(url, None)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps({"entries": self.entries}), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass  # (A cache that can't be written only costs requests.)

    def replay(self, request: Request) -> Fetched:
        """The cached reply, for the status at startup without the network."""
        if self.has(request.url):
            return Fetched(200, self.data(request.url))
        return Fetched(0, None, "not checked yet")

    def answer(self, request: Request, status: int, etag: str, body: bytes, error: str) -> Fetched:
        """A reply to ``request`` as the check sees it: a 304 is the cached reply; a 200 is parsed, trimmed
        and cached with its ETag."""
        if error:
            return Fetched(status, None, error)
        if status == 304 and self.has(request.url):
            return Fetched(200, self.data(request.url))
        if status != 200:
            return Fetched(status, None, "" if status == 404 else f"GitHub answered {status}.")
        try:
            data = request.trim(json.loads(body.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return Fetched(status, None, "GitHub's reply couldn't be read.")
        self.put(request.url, etag, data)
        return Fetched(200, data)
