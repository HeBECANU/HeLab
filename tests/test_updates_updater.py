"""The updater script (``helab/updates/updater.py``), run as a subprocess on every OS against temporary repos: a bare
repo as "the remote", a clone as "the checkout", both under ``tmp_path``. The clone's remote URL is
``https://github.com/HeBECANU/HeLab``, rewritten to the bare repo by the clone's own ``url.<bare>.insteadOf``, so
the updater's matching by URL runs as it would; ``GIT_ALLOW_PROTOCOL=file`` and an empty global config make sure
nothing leaves the machine. Never this checkout, never Tony's remotes.

A fake ``uv`` (a Python script) builds a real ``venv`` that imports the temporary checkout's stub ``helab`` and a
stub ``PyQt6``, and fails on demand; a fake HeLab records each start and writes the started mark, or exits, as told.
"""
from __future__ import annotations

from collections.abc import Iterator
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
import venv as venv_module

import pytest

from helab.utils.cache_locks import FileLock

UPDATER = Path(__file__).resolve().parents[1] / "helab" / "updates" / "updater.py"
REPO_URL = "https://github.com/HeBECANU/HeLab"
MINOR = f"{sys.version_info[0]}.{sys.version_info[1]}"

FAKE_UV = r'''
import json, os, sys, venv
from pathlib import Path
log = Path(os.environ["FAKE_UV_LOG"])
with log.open("a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if Path(os.environ["FAKE_UV_FAIL"]).exists():
    print("fake uv: failing as asked", file=sys.stderr)
    raise SystemExit(1)
if sys.argv[1] == "venv":
    venv.EnvBuilder(with_pip=False, symlinks=sys.platform != "win32").create(sys.argv[-1])
    raise SystemExit(0)
# pip install --python <venv python> -r <lock> -e <checkout>: the checkout and a stub PyQt6 on its path.
python = Path(sys.argv[sys.argv.index("--python") + 1])
checkout = sys.argv[sys.argv.index("-e") + 1]
root = python.parent.parent
site = next(root.rglob("site-packages"))
(site / "helab-checkout.pth").write_text(checkout + "\n" + os.environ["FAKE_UV_STUBS"] + "\n")
(root / "marker.txt").write_text(Path(checkout, "requirements.lock").read_text())
'''

FAKE_HELAB = r'''
import json, os, sys, time
from pathlib import Path
base = Path(sys.argv[1])
token = os.environ.get("HELAB_UPDATE_TOKEN", "")
checkout = Path.cwd()
version = (checkout / "helab" / "_version.py").read_text().split('"')[1]
with (base / "launches.jsonl").open("a") as f:
    f.write(json.dumps({"token": token, "version": version, "python": sys.executable}) + "\n")
behaviour = (base / "behaviour").read_text().strip() if (base / "behaviour").exists() else "ok"
if token and behaviour == "crash-new":
    raise SystemExit(3)
if token and behaviour == "hang":
    time.sleep(30)
if token:
    (Path(os.environ["FAKE_APP_DIR"]) / "updates" / f"started-{token}").write_text("")
'''


def _git(cwd: Path, *arguments: str, env: dict[str, str]) -> str:
    done = subprocess.run(["git", *arguments], cwd=cwd, env=env, capture_output=True, text=True)
    assert done.returncode == 0, (arguments, done.stderr)
    return done.stdout.strip()


class Lab:
    """The temporary world: remote, checkout, venv, app folder, tools."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.remote = base / "remote.git"
        self.seed = base / "seed"
        self.checkout = base / "checkout"
        self.app_dir = base / "app"
        self.stubs = base / "stubs"
        (self.stubs / "PyQt6").mkdir(parents=True)
        (self.stubs / "PyQt6" / "__init__.py").write_text("")
        (self.stubs / "PyQt6" / "QtCore.py").write_text("")
        (base / "gitconfig").write_text("")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("SSH_", "GIT_")) and key != "HELAB_UPDATE_TOKEN"}
        self.env.update(GIT_CONFIG_GLOBAL=str(base / "gitconfig"), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                        GIT_ALLOW_PROTOCOL="file", GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
                        HELAB_UPDATER_TEST_ROOT=str(base), HELAB_UPDATER_TEST_ELEVATED="0",
                        FAKE_UV_LOG=str(base / "uv.log"), FAKE_UV_FAIL=str(base / "uv-fail"),
                        FAKE_UV_STUBS=str(self.stubs), FAKE_APP_DIR=str(self.app_dir))
        self.env.pop("PYTHONPATH", None)
        assert os.environ.get("HELAB_TEST_SOURCE_GUARD")  # (conftest: the updater's own guard is on.)
        for script, text in (("fake_uv.py", FAKE_UV), ("fake_helab.py", FAKE_HELAB)):
            (base / script).write_text(text)
        self.git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.git(base, "init", "-q", "-b", "main", str(self.seed))
        self.commit("0.0.1", lock="a")
        self.git(self.seed, "tag", "v0.0.1")
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.git(self.seed, "push", "-q", "origin", "main", "v0.0.1")
        self.git(base, "clone", "-q", str(self.remote), str(self.checkout))
        self.git(self.checkout, "config", "remote.origin.url", REPO_URL)
        self.git(self.checkout, "config", f"url.{self.remote.as_posix()}.insteadOf", REPO_URL)
        self.venv = self.checkout / "venv"
        self.make_venv(self.venv, "old")
        (self.app_dir / "updates").mkdir(parents=True)

    def git(self, cwd: Path, *arguments: str) -> str:
        return _git(cwd, *arguments, env=self.env)

    def commit(self, version: str, *, lock: str | None = None, files: dict[str, str] | None = None,
               where: Path | None = None) -> str:
        repo = where or self.seed
        (repo / "helab").mkdir(exist_ok=True)
        (repo / "helab" / "__init__.py").write_text("")
        (repo / "helab" / "_version.py").write_text(f'__version__ = "{version}"\n')
        (repo / "helab" / "build_info.py").write_text("")
        (repo / "helab" / "utils").mkdir(exist_ok=True)
        (repo / "helab" / "utils" / "__init__.py").write_text("")
        (repo / "helab" / "utils" / "settings_defaults.py").write_text("")
        (repo / ".gitignore").write_text("venv\nvenv.*\n")
        if lock is not None:
            (repo / "requirements.lock").write_text(
                f"# uv pip compile requirements.txt --universal --python-version {MINOR} -o requirements.lock\n{lock}\n")
        for name, text in (files or {}).items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text)
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", f"Version {version}")
        return self.git(repo, "rev-parse", "HEAD")

    def publish(self, version: str, *, tag: bool = False, **kwargs: Any) -> str:
        sha = self.commit(version, **kwargs)
        self.git(self.seed, "push", "-q", "origin", "main")
        if tag:
            self.git(self.seed, "tag", f"v{version}")
            self.git(self.seed, "push", "-q", "origin", f"v{version}")
        return sha

    def make_venv(self, folder: Path, marker: str) -> None:
        venv_module.EnvBuilder(with_pip=False, symlinks=sys.platform != "win32").create(folder)
        (folder / "marker.txt").write_text(marker)

    def head(self) -> str:
        return self.git(self.checkout, "rev-parse", "HEAD")

    def version(self) -> str:
        return (self.checkout / "helab" / "_version.py").read_text().split('"')[1]

    def request(self, **overrides: Any) -> Path:
        token = overrides.pop("token", os.urandom(8).hex())
        data: dict[str, Any] = {
            "token": token, "action": "update", "checkout": str(self.checkout), "venv": str(self.venv),
            "app_dir": str(self.app_dir), "pid": overrides.pop("pid", os.getpid()), "mode": "releases",
            "repository": "HeBECANU/HeLab", "branch": "main", "tag": "", "target": "", "stash": False,
            "git": ["git"], "uv": [sys.executable, str(self.base / "fake_uv.py")], "python": sys.executable,
            "relaunch": [sys.executable, str(self.base / "fake_helab.py"), str(self.base)],
            "timeouts": {"helab": 20, "others": 10, "started": 20}}
        data.update(overrides)
        path = self.app_dir / "updates" / f"request-{token}.json"
        path.write_text(json.dumps(data))
        return path

    def script(self) -> Path:
        copy = self.app_dir / "updates" / "updater-test.py"  # (Run outside the checkout, as HeLab does.)
        shutil.copyfile(UPDATER, copy)
        return copy

    def dry_run(self, **overrides: Any) -> dict[str, Any]:
        done = subprocess.run([sys.executable, str(self.script()), str(self.request(**overrides)), "--check"],
                              env=overrides.pop("env", None) or self.env, capture_output=True, text=True,
                              timeout=120, cwd=self.app_dir)
        assert done.returncode == 0, done.stderr
        result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
        return result

    def start(self, helab: subprocess.Popen[bytes] | None = None, env: dict[str, str] | None = None,
              **overrides: Any) -> subprocess.Popen[str]:
        """The real run, for a stand-in HeLab process (one that exits at once unless given)."""
        process = helab or subprocess.Popen([sys.executable, "-c", "pass"])
        if helab is None:
            process.wait()
        path = self.request(pid=overrides.pop("pid", process.pid), **overrides)
        return subprocess.Popen([sys.executable, str(self.script()), str(path)], env=env or self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.app_dir)

    def run(self, **overrides: Any) -> dict[str, Any]:
        updater = self.start(**overrides)
        _, err = updater.communicate(timeout=240)
        return self.last(err)

    def last(self, err: str = "") -> dict[str, Any]:
        data = json.loads((self.app_dir / "updates" / "last.json").read_text())
        assert isinstance(data, dict), err
        log = Path(str(data.get("log", "")))
        data["_log"] = log.read_text() if log.is_file() else ""
        return data

    def launches(self, count: int = 0) -> list[dict[str, Any]]:
        """Each start of the fake HeLab; waits (up to 20 s) for ``count`` of them: a start without a token is
        detached, and the updater doesn't wait for it."""
        path = self.base / "launches.jsonl"
        deadline = time.monotonic() + 20
        while True:
            found = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
            if len(found) >= count or time.monotonic() > deadline:
                return found
            time.sleep(0.1)

    def uv_calls(self) -> list[list[str]]:
        path = self.base / "uv.log"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def why(last: dict[str, Any]) -> str:
    """An assertion's message: the outcome and reason first (pytest keeps only a message's first lines)."""
    return f"{last.get('outcome')}: {last.get('reason')}\n{last.get('_log', '')}"


@pytest.fixture
def lab(tmp_path: Path) -> Iterator[Lab]:
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    yield Lab(tmp_path)


def detach_at_tag(lab: Lab) -> None:
    lab.git(lab.checkout, "checkout", "-q", "--detach", "v0.0.1")


# -- Releases ------------------------------------------------------------------------------------------

def test_releases_mode_checks_out_the_tag_and_restarts_into_it(lab: Lab) -> None:
    detach_at_tag(lab)
    target = lab.publish("0.0.2", tag=True)
    plan = lab.dry_run(tag="v0.0.2", target=target)
    assert plan["ok"] and plan["target"] == target and not plan["rebuild"]
    assert lab.head() != target  # (The dry run changes nothing but the fetch.)
    last = lab.run(tag="v0.0.2", target=target)
    assert last["outcome"] == "updated", why(last)
    assert lab.head() == target and lab.version() == "0.0.2"
    assert (lab.venv / "marker.txt").read_text() == "old"  # (The lock didn't change: the venv is reused.)
    assert lab.uv_calls() == []
    launches = lab.launches()
    assert len(launches) == 1 and launches[0]["token"] and launches[0]["version"] == "0.0.2"
    previous = json.loads((lab.app_dir / "updates" / "previous.json").read_text())
    assert previous["to"] == target and previous["rebuilt"] is False


def test_a_tag_not_on_main_is_refused(lab: Lab) -> None:
    detach_at_tag(lab)
    lab.git(lab.seed, "checkout", "-q", "-b", "side")
    side = lab.commit("0.0.3")
    lab.git(lab.seed, "tag", "v0.0.3")
    lab.git(lab.seed, "push", "-q", "origin", "side", "v0.0.3")
    plan = lab.dry_run(tag="v0.0.3", target=side)
    assert not plan["ok"] and "isn't on HeBECANU/HeLab's main" in " ".join(plan["refusals"])


def test_a_moved_tag_is_refused(lab: Lab) -> None:
    detach_at_tag(lab)
    first = lab.publish("0.0.2", tag=True)
    lab.dry_run(tag="v0.0.2", target=first)  # (The checkout now has v0.0.2.)
    second = lab.publish("0.0.2-moved")
    lab.git(lab.seed, "tag", "-f", "v0.0.2", second)
    lab.git(lab.seed, "push", "-q", "-f", "origin", "v0.0.2")
    plan = lab.dry_run(tag="v0.0.2", target=second)
    assert not plan["ok"] and "the tag moved" in " ".join(plan["refusals"])


def test_a_target_other_than_the_one_checked_is_refused(lab: Lab) -> None:
    detach_at_tag(lab)
    lab.publish("0.0.2", tag=True)
    plan = lab.dry_run(tag="v0.0.2", target="f" * 40)
    assert not plan["ok"] and "not the fffffff the check found" in " ".join(plan["refusals"])


# -- Branch ---------------------------------------------------------------------------------------------

def test_branch_mode_fast_forwards_to_the_checked_commit_not_past_it(lab: Lab) -> None:
    green = lab.publish("0.0.2")
    lab.publish("0.0.3")  # (Newer, not green: not the target.)
    last = lab.run(mode="branch", branch="main", target=green)
    assert last["outcome"] == "updated", why(last)
    assert lab.head() == green and lab.git(lab.checkout, "symbolic-ref", "--short", "HEAD") == "main"


def test_branch_mode_refuses_a_detached_checkout_another_branch_or_a_diverged_one(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    detach_at_tag(lab)
    assert "isn't on a branch" in " ".join(lab.dry_run(mode="branch", branch="main", target=target)["refusals"])
    lab.git(lab.checkout, "checkout", "-q", "-b", "mine")
    assert "on mine, not main" in " ".join(lab.dry_run(mode="branch", branch="main", target=target)["refusals"])
    lab.git(lab.checkout, "checkout", "-q", "main")
    lab.commit("0.0.1-local", where=lab.checkout)
    refusals = " ".join(lab.dry_run(mode="branch", branch="main", target=target)["refusals"])
    assert "can't fast-forward" in refusals


def test_a_commit_not_on_the_branch_is_refused(lab: Lab) -> None:
    lab.publish("0.0.2")
    refusals = " ".join(lab.dry_run(mode="branch", branch="main", target="e" * 40)["refusals"])
    assert "isn't on HeBECANU/HeLab's main" in refusals


# -- Refusals -------------------------------------------------------------------------------------------

def test_local_changes_are_refused_unless_stashed_and_the_stash_is_kept(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    (lab.checkout / "helab" / "build_info.py").write_text("# mine\n")
    plan = lab.dry_run(mode="branch", branch="main", target=target)
    assert not plan["ok"] and plan["stashable"] and "has changes (helab/build_info.py)" in plan["refusals"][0]
    last = lab.run(mode="branch", branch="main", target=target, stash=True)
    assert last["outcome"] == "updated", why(last)
    assert lab.head() == target
    stashes = lab.git(lab.checkout, "stash", "list")
    assert "HeLab update" in stashes and last["stash"].startswith("HeLab update")


def test_untracked_files_the_update_would_overwrite_are_named(lab: Lab) -> None:
    target = lab.publish("0.0.2", files={"helab/new_module.py": "x = 1\n"})
    (lab.checkout / "helab" / "new_module.py").write_text("mine\n")
    refusals = " ".join(lab.dry_run(mode="branch", branch="main", target=target)["refusals"])
    assert "untracked: helab/new_module.py" in refusals


def test_a_different_python_minor_version_is_refused(lab: Lab) -> None:
    (lab.seed / "requirements.lock").write_text("# uv pip compile --python-version 3.99 -o requirements.lock\n")
    target = lab.publish("0.0.2")
    refusals = " ".join(lab.dry_run(mode="branch", branch="main", target=target)["refusals"])
    assert "needs Python 3.99" in refusals


def test_missing_git_or_uv_is_refused(lab: Lab) -> None:
    same_lock = lab.publish("0.0.2")
    missing = str(lab.base / "no-such-tool")
    assert "git isn't installed" in " ".join(lab.dry_run(git=[missing], mode="branch", target=same_lock)["refusals"])
    # uv is needed only to rebuild the venv.
    assert lab.dry_run(uv=[missing], mode="branch", branch="main", target=same_lock)["refusals"] == []
    new_lock = lab.publish("0.0.3", lock="b")
    refusals = " ".join(lab.dry_run(uv=[missing], mode="branch", branch="main", target=new_lock)["refusals"])
    assert "uv isn't installed" in refusals


def test_an_ssh_or_elevated_session_is_refused(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    ssh = dict(lab.env, SSH_CONNECTION="10.0.0.1 50000 10.0.0.2 22")
    plan = lab.dry_run(mode="branch", branch="main", target=target, env=ssh)
    assert "SSH session" in " ".join(plan["refusals"])
    elevated = dict(lab.env, HELAB_UPDATER_TEST_ELEVATED="1")
    plan = lab.dry_run(mode="branch", branch="main", target=target, env=elevated)
    assert "administrator rights" in " ".join(plan["refusals"])


def test_another_helab_or_a_cache_move_is_refused(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    other = FileLock(str(lab.app_dir / "instances" / "99999.lock"))
    assert other.try_lock()
    try:
        plan = lab.dry_run(mode="branch", branch="main", target=target)
        assert "another HeLab (a helab convert, process 99999)" in " ".join(plan["refusals"])
    finally:
        other.unlock()
    own = FileLock(str(lab.app_dir / "instances" / f"{os.getpid()}.lock"))
    move = FileLock(str(lab.app_dir / "move.lock"))
    assert own.try_lock() and move.try_lock()
    try:
        plan = lab.dry_run(mode="branch", branch="main", target=target)  # (Its own instance lock is fine.)
        assert plan["refusals"] == ["Not while a cache move's helper is still running."]
    finally:
        own.unlock()
        move.unlock()


def test_the_test_guard_refuses_folders_outside_the_tests_root(lab: Lab, tmp_path_factory: pytest.TempPathFactory) -> None:
    target = lab.publish("0.0.2")
    elsewhere = dict(lab.env, HELAB_UPDATER_TEST_ROOT=str(tmp_path_factory.mktemp("elsewhere")))
    plan = lab.dry_run(mode="branch", branch="main", target=target, env=elsewhere)
    assert "Under tests, the updater only works below" in " ".join(plan["refusals"])


def test_a_refusal_after_helab_quit_changes_nothing_and_starts_the_old_one(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    (lab.checkout / "helab" / "build_info.py").write_text("# mine\n")
    before = lab.head()
    last = lab.run(mode="branch", branch="main", target=target)
    assert last["outcome"] == "refused" and "has changes" in last["reason"]
    assert lab.head() == before and (lab.checkout / "helab" / "build_info.py").read_text() == "# mine\n"
    assert [launch["token"] for launch in lab.launches(1)] == [""]  # (The old one, without a token.)


# -- Waiting --------------------------------------------------------------------------------------------

def test_the_updater_waits_for_helab_and_its_helpers_before_changing_a_file(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    helab = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    python = lab.venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    helper = None
    try:
        updater = lab.start(helab=helab, mode="branch", branch="main", target=target)
        ready = list((lab.app_dir / "updates").glob("ready-*"))
        deadline = time.monotonic() + 30
        while not ready and time.monotonic() < deadline:
            time.sleep(0.1)
            ready = list((lab.app_dir / "updates").glob("ready-*"))
        assert ready, "the updater never said it was ready"
        # A helper from the venv, its command naming HeLab's helper.
        helper = subprocess.Popen([str(python), "-c", "import time; time.sleep(60)", "--helab-io-helper"],
                                  env={k: v for k, v in lab.env.items() if k != "PYTHONHOME"})
        time.sleep(1.0)
        assert lab.head() != target and updater.poll() is None
        helab.kill()
        helab.wait()
        time.sleep(2.0)
        assert lab.head() != target and updater.poll() is None, "it changed files while a helper ran"
        helper.kill()
        helper.wait()
        updater.communicate(timeout=120)
        assert lab.last()["outcome"] == "updated" and lab.head() == target
    finally:
        for process in (helab, helper):
            if process is not None and process.poll() is None:
                process.kill()


def test_helab_that_never_quits_leaves_everything_as_it_was(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    helab = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        last = lab.start(helab=helab, mode="branch", branch="main", target=target,
                         timeouts={"helab": 1, "others": 1, "started": 5})
        last.communicate(timeout=60)
        assert lab.last()["outcome"] == "refused" and "didn't quit" in lab.last()["reason"]
        assert lab.head() != target
    finally:
        helab.kill()


# -- The venv -------------------------------------------------------------------------------------------

def test_the_venv_is_rebuilt_beside_the_old_one_only_when_the_lock_changed(lab: Lab) -> None:
    target = lab.publish("0.0.2", lock="b")
    assert lab.dry_run(mode="branch", branch="main", target=target)["rebuild"]
    last = lab.run(mode="branch", branch="main", target=target)
    assert last["outcome"] == "updated", why(last)
    assert "b" in (lab.venv / "marker.txt").read_text()  # (Built from the new lock.)
    assert (lab.base / "checkout" / "venv.previous" / "marker.txt").read_text() == "old"
    calls = lab.uv_calls()
    assert calls[0][:2] == ["venv", "--relocatable"] and calls[1][:2] == ["pip", "install"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_venv_symlink_stays_a_symlink(lab: Lab) -> None:
    real = lab.checkout / "venv.nosync"
    shutil.rmtree(lab.venv)
    lab.make_venv(real, "old")
    lab.venv.symlink_to("venv.nosync")
    target = lab.publish("0.0.2", lock="b")
    last = lab.run(mode="branch", branch="main", target=target)
    assert last["outcome"] == "updated", why(last)
    assert lab.venv.is_symlink() and os.readlink(lab.venv) == "venv.nosync"
    assert "b" in (real / "marker.txt").read_text()
    assert (lab.checkout / "venv.nosync.previous" / "marker.txt").read_text() == "old"


def test_a_failed_venv_build_leaves_the_previous_version(lab: Lab) -> None:
    before = lab.head()
    target = lab.publish("0.0.2", lock="b")
    (lab.base / "uv-fail").write_text("")
    last = lab.run(mode="branch", branch="main", target=target)
    assert last["outcome"] == "failed" and "Building the new venv failed" in last["reason"]
    assert lab.head() == before and (lab.venv / "marker.txt").read_text() == "old"
    assert not (lab.checkout / "venv.new").exists() and not (lab.checkout / "venv.previous").exists()
    assert [launch["version"] for launch in lab.launches(1)] == ["0.0.1"]
    assert not (lab.app_dir / "updates" / "previous.json").exists()


# -- Started, rolled back, restored ---------------------------------------------------------------------

def test_a_new_version_that_exits_before_starting_is_rolled_back(lab: Lab) -> None:
    before = lab.head()
    target = lab.publish("0.0.2", lock="b")
    (lab.base / "behaviour").write_text("crash-new")
    last = lab.run(mode="branch", branch="main", target=target)
    assert last["outcome"] == "rolled back", why(last)
    assert lab.head() == before and (lab.venv / "marker.txt").read_text() == "old"
    assert [(bool(launch["token"]), launch["version"]) for launch in lab.launches(2)] == [(True, "0.0.2"),
                                                                                         (False, "0.0.1")]


def test_a_slow_new_version_is_never_killed(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    (lab.base / "behaviour").write_text("hang")
    last = lab.run(mode="branch", branch="main", target=target, timeouts={"helab": 20, "others": 10, "started": 2})
    assert last["outcome"] == "unconfirmed" and lab.head() == target


def test_restore_brings_back_the_previous_commit_and_venv(lab: Lab) -> None:
    before = lab.head()
    target = lab.publish("0.0.2", lock="b")
    assert lab.run(mode="branch", branch="main", target=target)["outcome"] == "updated"
    plan = lab.dry_run(action="restore", mode="branch", branch="main")
    assert plan["ok"] and plan["target"] == before and plan["rebuild"]
    last = lab.run(action="restore", mode="branch", branch="main")
    assert last["outcome"] == "restored", why(last)
    assert lab.head() == before and lab.git(lab.checkout, "symbolic-ref", "--short", "HEAD") == "main"
    assert (lab.venv / "marker.txt").read_text() == "old"
    assert "b" in (lab.checkout / "venv.previous" / "marker.txt").read_text()
    # (Restore again undoes it.)
    assert lab.run(action="restore", mode="branch", branch="main")["outcome"] == "restored"
    assert lab.head() == target and "b" in (lab.venv / "marker.txt").read_text()


def test_restore_refuses_when_the_checkout_moved_since(lab: Lab) -> None:
    target = lab.publish("0.0.2")
    assert lab.run(mode="branch", branch="main", target=target)["outcome"] == "updated"
    lab.commit("0.0.2-local", where=lab.checkout)
    assert "moved since the update" in " ".join(lab.dry_run(action="restore")["refusals"])


def test_a_second_update_deletes_only_the_venv_before_the_previous_one(lab: Lab) -> None:
    first = lab.publish("0.0.2", lock="b")
    earlier = lab.run(mode="branch", branch="main", target=first)
    assert earlier["outcome"] == "updated", why(earlier)
    second = lab.publish("0.0.3", lock="c")
    last = lab.run(mode="branch", branch="main", target=second)
    assert last["outcome"] == "updated", why(last)
    assert "c" in (lab.venv / "marker.txt").read_text()
    assert "b" in (lab.checkout / "venv.previous" / "marker.txt").read_text()
    assert not list(lab.checkout.glob("venv.previous-*"))  # (Q~8 (a): the one before that is gone.)
    assert "Deleted the older venv" in last["_log"]


def test_the_updater_imports_only_the_standard_library() -> None:
    """It runs as a lone copy with the base Python: nothing from HeLab or the venv."""
    import ast
    tree = ast.parse(UPDATER.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.level == 0}
    assert imported and imported <= set(sys.stdlib_module_names) | {"__future__"}, imported - set(sys.stdlib_module_names)
