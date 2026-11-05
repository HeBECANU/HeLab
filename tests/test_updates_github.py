"""The update check's pure core (``helab.updates.versions``, ``helab.updates.github``): the version status, the
channels, the CI rule, the ETag cache and the whole check driven by fake GitHub replies. No network."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from helab.build_info import BuildInfo
from helab.updates import github
from helab.updates.github import EtagCache, Fetched, Request, check, ci_state, drive
from helab.updates.versions import (
    BRANCH, DEVELOPMENT, PRE_RELEASE, RELEASE, RELEASES, UNCHECKED, Facts, Release, status)

REPO = "TonyXTYan/HeLab"
C_OLD, C_REL, C_PRE, C_NEW = "a" * 40, "b" * 40, "c" * 40, "d" * 40
JOBS = ("Tests (1/3)", "Tests (2/3)", "Tests (3/3)", "Converter backends", "Build")


def release(tag: str, *, pre: bool = False, draft: bool = False, notes: str = "") -> dict[str, Any]:
    return {"tag_name": tag, "name": f"Automated Release {tag}", "prerelease": pre, "draft": draft,
            "published_at": "2026-11-01T00:00:00Z", "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
            "body": notes, "assets": [{"name": "HeLab-macos.zip", "browser_download_url": "https://x/mac.zip"},
                                      {"name": "HeLab-windows.zip", "browser_download_url": "https://x/win.zip"}]}


def ref(tag: str, sha: str, kind: str = "commit") -> dict[str, Any]:
    return {"ref": f"refs/tags/{tag}", "object": {"type": kind, "sha": sha}}


def runs(conclusions: dict[str, str] | None = None, *, oses: tuple[str, ...] = github.OSES, app: str = "github-actions",
         status: str = "completed", extra: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A commit's check runs as GitHub lists them: every required job per OS (success unless
    ``conclusions`` says otherwise, keyed "<os> <job>"), and the skipped compatibility jobs."""
    found: list[dict[str, Any]] = []
    for number, os_name in enumerate(oses):
        for index, job in enumerate(JOBS):
            conclusion = (conclusions or {}).get(f"{os_name} {job}", "success")
            found.append({"id": 100 + 10 * number + index, "name": f"{os_name} + py3.13 / {job}", "status": status,
                          "conclusion": conclusion if status == "completed" else None, "app": {"slug": app}})
        found.append({"id": 900 + number, "name": f"{os_name} + py3.12 / Tests", "status": "completed",
                      "conclusion": "skipped", "app": {"slug": "github-actions"}})
    found += extra or []
    return {"total_count": len(found), "check_runs": found}


def compare(state: str, shas: list[str]) -> dict[str, Any]:
    """GitHub lists a compare's commits oldest first."""
    return {"status": state, "ahead_by": len(shas), "commits": [
        {"sha": sha, "html_url": f"https://github.com/{REPO}/commit/{sha}",
         "commit": {"message": f"Commit {sha[:3]}\n\nbody", "committer": {"date": "2026-11-05T01:00:00Z"}}}
        for sha in shas]}


class Feed:
    """GitHub's replies by path; every request made is recorded."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.asked: list[str] = []

    def __call__(self, request: Request) -> Fetched:
        self.asked.append(request.path)
        for path, reply in self.replies.items():
            if request.path == path or request.path.startswith(path + "?"):
                if isinstance(reply, int):
                    return Fetched(reply, None, "" if reply == 404 else f"GitHub answered {reply}.")
                return Fetched(200, request.trim(json.loads(json.dumps(reply))))
        return Fetched(404, None, "")


def feed(*, releases: list[dict[str, Any]] | None = None, extra: dict[str, Any] | None = None) -> Feed:
    replies: dict[str, Any] = {
        f"/repos/{REPO}/releases": releases if releases is not None else [
            release("v0.0.9", notes="New things"), release("v0.0.9a1", pre=True), release("v0.0.8a1")],
        f"/repos/{REPO}/git/matching-refs/tags/v": [ref("v0.0.9", C_NEW), ref("v0.0.9a1", C_PRE),
                                                     ref("v0.0.8a1", C_REL)],
        f"/repos/{REPO}/compare/{C_NEW}...main": compare("ahead", [C_OLD]),
        f"/repos/{REPO}/compare/{C_PRE}...main": compare("identical", []),
    }
    replies.update(extra or {})
    return Feed(replies)


def run(build: BuildInfo, source: Feed, mode: str = RELEASES, prereleases: bool = False) -> Facts:
    return drive(check(REPO, build.commit, build.version, mode, build.branch, prereleases), source)


# -- Status ---------------------------------------------------------------------------------------------

def test_a_release_commit_is_release_and_is_offered_the_newer_stable_one() -> None:
    build = BuildInfo(version="0.0.8", commit=C_REL, branch="detached", dirty=False)
    facts = run(build, feed(releases=[release("v0.0.9"), release("v0.0.8")], extra={
        f"/repos/{REPO}/git/matching-refs/tags/v": [ref("v0.0.9", C_NEW), ref("v0.0.8", C_REL)]}))
    found = status(build, facts, RELEASES, prereleases=False)
    assert (found.kind, found.text) == (RELEASE, "Release 0.0.8")
    assert found.offer is not None and found.offer.label == "0.0.9" and found.offer.commit is not None
    assert found.offer.commit.sha == C_NEW
    assert found.available


def test_source_and_frozen_runs_of_one_commit_get_the_same_status() -> None:
    source = BuildInfo(version="0.0.8a1", commit=C_REL, branch="detached", dirty=False)
    frozen = BuildInfo(version="0.0.8a1", commit=C_REL, branch="main", dirty=False, built_at="2026-11-01T00:00:00+00:00")
    facts = run(source, feed())
    assert status(source, facts, RELEASES, False) == status(frozen, facts, RELEASES, False)


def test_a_pre_release_is_pre_release_and_pre_releases_only_when_opted_in() -> None:
    build = BuildInfo(version="0.0.9a1", commit=C_PRE, dirty=False)
    source = feed(releases=[release("v0.0.9b1", pre=True), release("v0.0.9a1", pre=True), release("v0.0.8a1")],
                  extra={f"/repos/{REPO}/git/matching-refs/tags/v": [ref("v0.0.9b1", C_NEW), ref("v0.0.9a1", C_PRE)]})
    found = status(build, run(build, source), RELEASES, prereleases=False)
    assert found.kind == PRE_RELEASE and found.offer is None
    found = status(build, run(build, source, prereleases=True), RELEASES, prereleases=True)
    assert found.offer is not None and found.offer.label == "0.0.9b1"


def test_a_version_number_that_is_a_pre_release_counts_as_one_even_unmarked() -> None:
    build = BuildInfo(version="0.0.8a1", commit=C_REL, dirty=False)
    assert status(build, run(build, feed()), RELEASES, False).kind == PRE_RELEASE
    # (v0.0.8a1 was published as a full GitHub release: by its version it is still a pre-release.)
    build = BuildInfo(version="0.0.7", commit=C_OLD, dirty=False)
    source = feed(releases=[release("v0.0.8a1")], extra={
        f"/repos/{REPO}/compare/{C_REL}...main": compare("identical", [])})
    assert status(build, run(build, source), RELEASES, False).offer is None
    offer = status(build, run(build, source, prereleases=True), RELEASES, True).offer
    assert offer is not None and offer.label == "0.0.8a1"


def test_a_dirty_tree_or_a_branch_commit_is_a_development_version() -> None:
    dirty = BuildInfo(version="0.0.8a1", commit=C_REL, dirty=True)
    assert status(dirty, run(dirty, feed()), RELEASES, False).text == "Development version (based on 0.0.8a1)"
    ahead = BuildInfo(version="0.0.8a1", commit=C_OLD, branch="dev/v0.0.9", dirty=False)
    found = status(ahead, run(ahead, feed()), RELEASES, False)
    assert found.kind == DEVELOPMENT and found.offer is not None and found.offer.label == "0.0.9"


def test_a_development_version_is_offered_only_releases_newer_than_its_own_version() -> None:
    build = BuildInfo(version="0.0.9", commit=C_OLD, branch="dev/v0.0.10", dirty=False)
    assert status(build, run(build, feed()), RELEASES, True).offer is None


def test_before_any_check_the_status_comes_from_the_build_alone() -> None:
    assert status(BuildInfo(version="0.0.8a1", commit=C_OLD), None, BRANCH, False).kind == DEVELOPMENT
    frozen = BuildInfo(version="0.0.8a1", commit=C_OLD, built_at="2026-11-01T00:00:00+00:00")
    assert status(frozen, None, RELEASES, False).text == "0.0.8a1 (not checked yet)"
    assert status(frozen, None, RELEASES, False).kind == UNCHECKED


def test_drafts_never_show() -> None:
    build = BuildInfo(version="0.0.8a1", commit=C_REL, dirty=False)
    source = feed(releases=[release("v0.0.9", draft=True), release("v0.0.8a1")])
    facts = run(build, source)
    assert [r.tag for r in facts.releases] == ["v0.0.8a1"]
    assert status(build, facts, RELEASES, True).offer is None


def test_a_release_whose_tag_is_not_on_main_is_not_offered_and_the_next_is() -> None:
    build = BuildInfo(version="0.0.8a1", commit=C_REL, dirty=False)
    source = feed(extra={f"/repos/{REPO}/compare/{C_NEW}...main": compare("diverged", [C_OLD])})
    facts = run(build, source, prereleases=True)
    assert facts.off_main == ("v0.0.9",)
    offer = status(build, facts, RELEASES, True).offer
    assert offer is not None and offer.label == "0.0.9a1"


def test_skip_this_version_marks_the_offer_skipped_and_a_newer_one_is_offered_again() -> None:
    build = BuildInfo(version="0.0.8a1", commit=C_REL, dirty=False)
    facts = run(build, feed())
    assert status(build, facts, RELEASES, False, skipped="0.0.9").skipped
    assert not status(build, facts, RELEASES, False, skipped="0.0.9").available
    assert status(build, facts, RELEASES, False, skipped="0.0.8").available


def test_annotated_tags_are_resolved_to_their_commit() -> None:
    build = BuildInfo(version="0.0.2", commit=C_OLD, dirty=False)
    source = feed(releases=[release("v0.0.3b")], extra={
        f"/repos/{REPO}/git/matching-refs/tags/v": [ref("v0.0.3b", "e" * 40, "tag")],
        f"/repos/{REPO}/git/tags/{'e' * 40}": {"object": {"type": "commit", "sha": C_REL}},
        f"/repos/{REPO}/compare/{C_REL}...main": compare("ahead", [])})
    facts = run(build, source, prereleases=True)
    assert facts.tag_commit("v0.0.3b") == C_REL


def test_the_platform_asset_is_found_by_os() -> None:
    found = github.parse_releases(github.trim_releases([release("v0.0.9")]))[0]
    assert found.asset_for("darwin") == "https://x/mac.zip"
    assert found.asset_for("win32") == "https://x/win.zip"
    assert found.asset_for("linux") == ""


# -- Branch mode ----------------------------------------------------------------------------------------

def branch_feed(state: str, newer: list[str], ci: dict[str, dict[str, Any]]) -> Feed:
    extra: dict[str, Any] = {f"/repos/{REPO}/compare/{C_OLD}...dev/v0.0.9": compare(state, newer)}
    extra.update({f"/repos/{REPO}/commits/{sha}/check-runs": reply for sha, reply in ci.items()})
    return feed(extra=extra)


def branch_build() -> BuildInfo:
    return BuildInfo(version="0.0.8a1", commit=C_OLD, branch="dev/v0.0.9", dirty=False)


def test_branch_mode_moves_to_the_newest_green_commit_past_a_red_newer_one() -> None:
    first, second, third = "1" * 40, "2" * 40, "3" * 40
    source = branch_feed("ahead", [first, second, third],
                         {third: runs({"windows Tests (2/3)": "failure"}), second: runs()})
    facts = run(branch_build(), source, BRANCH)
    found = status(branch_build(), facts, BRANCH, False)
    assert found.offer is not None and found.offer.commit is not None
    assert found.offer.commit.sha == second and found.offer.label == "dev/v0.0.9 +2" and found.offer.ahead == 2
    assert facts.branch is not None and facts.branch.ci_of(third).startswith("red")
    assert f"/repos/{REPO}/commits/{first}/check-runs?per_page=100" not in source.asked  # (Stops at the green one.)


@pytest.mark.parametrize("state, note", [("identical", "Up to date"), ("diverged", "fast-forward"),
                                         ("behind", "fast-forward")])
def test_branch_mode_offers_nothing_when_up_to_date_or_not_a_fast_forward(state: str, note: str) -> None:
    facts = run(branch_build(), branch_feed(state, [], {}), BRANCH)
    found = status(branch_build(), facts, BRANCH, False)
    assert found.offer is None and note in " ".join(found.notes)


def test_branch_mode_with_no_green_commit_offers_nothing_and_says_why() -> None:
    newest = "4" * 40
    facts = run(branch_build(), branch_feed("ahead", [newest], {newest: runs(status="in_progress")}), BRANCH)
    found = status(branch_build(), facts, BRANCH, False)
    assert found.offer is None and "none of them" in found.notes[0]


def test_a_branch_or_commit_github_doesnt_have_is_missing_not_a_failure() -> None:
    facts = run(branch_build(), feed(), BRANCH)  # (No compare reply: 404.)
    assert facts.branch is not None and facts.branch.state == "missing"


def test_branch_mode_looks_at_no_more_than_five_commits() -> None:
    newer = [f"{n}" * 40 for n in range(1, 9)]
    source = branch_feed("ahead", newer, {sha: runs(status="queued") for sha in newer})
    run(branch_build(), source, BRANCH)
    assert sum("/check-runs" in path for path in source.asked) == github.MAX_CI_LOOKUPS


# -- The CI rule ----------------------------------------------------------------------------------------

def test_ci_is_green_when_every_required_job_passed_on_all_three_oses() -> None:
    assert ci_state(github.trim_check_runs(runs())) == ("green", "")


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out", "skipped", "action_required"])
def test_any_required_job_that_didnt_succeed_is_not_green(conclusion: str) -> None:
    state, why = ci_state(github.trim_check_runs(runs({"ubuntu Build": conclusion})))
    assert state == "red" and "ubuntu Build" in why


def test_an_os_without_its_jobs_is_not_green() -> None:
    state, why = ci_state(github.trim_check_runs(runs(oses=("macos", "windows"))))
    assert state == "pending" and "ubuntu" in why


def test_unfinished_jobs_are_pending() -> None:
    assert ci_state(github.trim_check_runs(runs(status="in_progress")))[0] == "pending"


def test_another_apps_success_doesnt_count() -> None:
    assert ci_state(github.trim_check_runs(runs(app="someone-else")))[0] == "pending"


def test_a_rerun_that_passed_counts_and_a_newer_cancelled_one_doesnt() -> None:
    rerun = {"id": 5000, "name": "macos + py3.13 / Tests (2/3)", "status": "completed", "conclusion": "success",
             "app": {"slug": "github-actions"}}
    assert ci_state(github.trim_check_runs(runs({"macos Tests (2/3)": "failure"}, extra=[rerun])))[0] == "green"
    cancelled = dict(rerun, conclusion="cancelled")
    assert ci_state(github.trim_check_runs(runs(extra=[cancelled])))[0] == "red"


def test_a_skipped_push_run_beside_a_passed_pull_request_run_is_green() -> None:
    # (A push to a branch with an open PR runs only the detection job: its required jobs are skipped.)
    skipped = [{"id": 1 + n, "name": f"{os_name} + py3.13 / {job}", "status": "completed", "conclusion": "skipped",
                "app": {"slug": "github-actions"}} for n, (os_name, job) in
               enumerate((o, j) for o in github.OSES for j in JOBS)]
    assert ci_state(github.trim_check_runs(runs(extra=skipped)))[0] == "green"
    only_skipped = {"total_count": len(skipped), "check_runs": skipped}
    assert ci_state(github.trim_check_runs(only_skipped))[0] == "red"


def test_a_fourth_test_group_still_passes() -> None:
    more = [{"id": 7000 + n, "name": f"{os_name} + py3.13 / Tests (4/4)", "status": "completed", "conclusion": "success",
             "app": {"slug": "github-actions"}} for n, os_name in enumerate(github.OSES)]
    assert ci_state(github.trim_check_runs(runs(extra=more)))[0] == "green"


def test_other_jobs_dont_count() -> None:
    docs = {"id": 8000, "name": "Docs", "status": "completed", "conclusion": "failure", "app": {"slug": "github-actions"}}
    assert ci_state(github.trim_check_runs(runs(extra=[docs])))[0] == "green"


def test_more_runs_than_one_page_is_pending() -> None:
    found = github.trim_check_runs(runs())
    found["total_count"] = 500
    assert ci_state(found)[0] == "pending"


# -- Requests, failures and the ETag cache ---------------------------------------------------------------

def test_requests_go_to_api_github_com_with_helabs_user_agent_only() -> None:
    assert github.releases_request(REPO).url.startswith("https://api.github.com/repos/")
    sent = github.headers("0.0.8a1")
    assert sent["User-Agent"] == "HeLab/0.0.8a1"
    assert set(sent) == {"User-Agent", "Accept", "X-GitHub-Api-Version"}


def test_failures_in_words() -> None:
    assert "Couldn't reach GitHub" in github.failure(0, {}, "Host not found", 0)
    limit = github.failure(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1200"}, "", 0)
    assert "60 requests an hour" in limit and "20 min" in limit
    assert github.failure(500, {}, "", 0) == "GitHub answered 500."
    assert github.failure(304, {}, "", 0) == ""


def test_a_failed_request_fails_the_check_with_its_reason() -> None:
    build = BuildInfo(version="0.0.8a1", commit=C_REL)
    with pytest.raises(github.CheckFailed, match="500"):
        run(build, feed(extra={f"/repos/{REPO}/releases": 500}))


def test_the_etag_cache_reuses_a_304_and_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "updates" / "github-cache.json"
    cache = EtagCache(path)
    request = github.releases_request(REPO)
    body = json.dumps([release("v0.0.9")]).encode()
    first = cache.answer(request, 200, 'W/"abc"', body, "")
    assert first.ok and cache.etag(request.url) == 'W/"abc"'
    cache.save()
    again = EtagCache(path)
    assert again.etag(request.url) == 'W/"abc"'
    reused = again.answer(request, 304, "", b"", "")
    assert reused.ok and reused.data == first.data
    assert again.replay(request).data == first.data


def test_a_malformed_cache_file_is_an_empty_cache(tmp_path: Path) -> None:
    path = tmp_path / "github-cache.json"
    path.write_text("{not json", encoding="utf-8")
    cache = EtagCache(path)
    assert cache.entries == {} and not cache.replay(github.releases_request(REPO)).ok


def test_an_unreadable_reply_is_a_failure_not_a_crash(tmp_path: Path) -> None:
    cache = EtagCache(tmp_path / "c.json")
    assert not cache.answer(github.releases_request(REPO), 200, "", b"\xff<html>", "").ok


def test_only_the_trimmed_reply_is_kept() -> None:
    kept = github.trim_check_runs(runs())
    assert set(kept["check_runs"][0]) == {"id", "name", "status", "conclusion", "app"}
    notes = github.trim_releases([release("v1", notes="x" * 50_000)])
    assert len(notes[0]["body"]) == 20_000


def test_a_release_with_a_tag_that_isnt_pep_440_is_ignored() -> None:
    assert github.parse_releases(github.trim_releases([release("CI-CD-everything-passed"), release("v.0.0.1i")])) == ()
    assert isinstance(github.parse_releases(github.trim_releases([release("v0.0.9")]))[0], Release)
