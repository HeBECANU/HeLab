"""``--test-group N/M`` (``tests/conftest.py``): CI runs the suite in three groups per OS (Q16.2), and
every test must be in exactly one of them, or a test would run twice or never on CI."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from conftest import ALL_TESTS, SLOW_FIRST_MODULES, group_numbers, group_option

ROOT = Path(__file__).resolve().parents[1]

PROBE = "\n".join(f"def test_{index}():\n    pass\n" for index in range(40))
SLOW = "\n".join(f"def test_slow_{index}():\n    pass\n" for index in range(5))


def is_slow(nodeid: str) -> bool:
    return nodeid.split("::")[0].rsplit("/", 1)[-1] in SLOW_FIRST_MODULES


@pytest.mark.parametrize("groups", [2, 3])
def test_the_whole_collection_splits_into_groups_of_about_equal_size(request: pytest.FixtureRequest,
                                                                     groups: int) -> None:
    """This run's own collection (every test, before a group's selection): each test is in one of the groups,
    their sizes are close, and each has its share of the slow-first tests. Three for CI's required jobs, two
    for its compatibility jobs (``CI_GROUPS``)."""
    everything = request.config.stash[ALL_TESTS]
    assert len(everything) == len(set(everything)) > 0
    numbers = group_numbers(everything, groups)
    assert set(numbers) <= set(range(1, groups + 1))
    if len(everything) >= 1000:  # (the full suite, not a file or two run alone)
        sizes = Counter(numbers)
        assert max(sizes.values()) - min(sizes.values()) < 0.05 * len(everything), sizes
    slow = Counter(number for nodeid, number in zip(everything, numbers) if is_slow(nodeid))
    shares = [slow.get(n, 0) for n in range(1, groups + 1)]
    assert max(shares) - min(shares) <= 1, slow
    group = group_option(request.config.getoption("test_group"))
    if group is not None and group[1] == groups:  # (CI's run of one group: it runs only that group's tests)
        mine = {nodeid for nodeid, number in zip(everything, numbers) if number == group[0]}
        assert {item.nodeid for item in request.session.items} <= mine


# The groups CI's test jobs run: (required 3.13 jobs, compatibility jobs).
CI_GROUPS = (3, 2)


def test_ci_runs_three_groups_for_the_required_jobs_and_two_for_compatibility() -> None:
    """With two groups Windows' required jobs took 20.3 and 21.1 min of pytest (Ground CI 41476107464) against
    a 30-min limit, and the suite grows: three now, on every OS. The compatibility jobs (PRs only) keep two."""
    workflow = (ROOT / ".github" / "workflows" / "ci-test.yml").read_text(encoding="utf-8")
    [matrix] = re.findall(r"group: \$\{\{ fromJSON\(inputs\.experimental && '(\[.*?\])' \|\| '(\[.*?\])'\) \}\}", workflow)
    compatibility, required = (json.loads(text) for text in matrix)
    assert required == [f"{n}/{CI_GROUPS[0]}" for n in range(1, CI_GROUPS[0] + 1)]
    assert compatibility == [f"{n}/{CI_GROUPS[1]}" for n in range(1, CI_GROUPS[1] + 1)]
    assert '--test-group "${{ matrix.group }}"' in workflow


def test_a_tests_group_depends_on_its_node_id_only() -> None:
    nodeids = [f"tests/test_x.py::test_{index}" for index in range(200)]
    for groups in (1, 2, 3):
        numbers = group_numbers(nodeids, groups)
        assert set(numbers) == set(range(1, groups + 1))
        assert group_numbers(list(reversed(nodeids)), groups) == list(reversed(numbers))
        assert group_numbers(nodeids[50:], groups) == numbers[50:]


def test_the_slow_first_tests_are_dealt_out_in_turn() -> None:
    [module] = SLOW_FIRST_MODULES  # (the rule holds for any; the test reads one)
    nodeids = ["tests/test_a.py::test_one", *(f"tests/{module}::test_{index}" for index in range(5))]
    assert group_numbers(nodeids, 2)[1:] == [1, 2, 1, 2, 1]
    assert group_numbers(nodeids, 3)[1:] == [1, 2, 3, 1, 2]


@pytest.mark.parametrize("text", ["0/2", "3/2", "1", "a/b", "1/0", ""])
def test_a_bad_group_is_a_usage_error(text: str) -> None:
    with pytest.raises(pytest.UsageError, match="--test-group"):
        group_option(text)


def test_a_group_is_read_as_n_of_m() -> None:
    assert group_option(None) is None
    assert group_option("1/2") == (1, 2) and group_option(" 2 / 2 ") == (2, 2)


def nested_collect(tmp_path: Path, *options: str) -> subprocess.CompletedProcess[str]:
    """A collection of the probe tests of its own, with this conftest as its plugin (as in
    test_convert_required_backends)."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = {name: value for name, value in os.environ.items()
           if not name.startswith(("COV_CORE_", "PYTEST_XDIST_"))}  # (no coverage or xdist of the outer run)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "tests")])
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "conftest", "-p", "no:cacheprovider",
                           "-p", "no:xdist", "-p", "no:randomly", "--collect-only", "-q", *options],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def collected(done: subprocess.CompletedProcess[str]) -> list[str]:
    assert done.returncode == 0, done.stdout + done.stderr
    return [line for line in done.stdout.splitlines() if "::" in line]


def test_the_groups_of_a_run_cover_its_tests_once_each(tmp_path: Path) -> None:
    [module] = SLOW_FIRST_MODULES
    (tmp_path / "test_probe.py").write_text(PROBE, encoding="utf-8")
    (tmp_path / module).write_text(SLOW, encoding="utf-8")
    everything = collected(nested_collect(tmp_path))
    one = collected(nested_collect(tmp_path, "--test-group", "1/2"))
    two = collected(nested_collect(tmp_path, "--test-group", "2/2"))
    assert len(everything) == 45 and sorted(one + two) == sorted(everything) and one and two
    assert not set(one) & set(two)
    # Each group runs its slow-first tests first (3 and 2 of the 5).
    assert [nodeid.startswith(module) for nodeid in one[:3]] == [True] * 3
    assert [nodeid.startswith(module) for nodeid in two[:2]] == [True] * 2


def test_a_bad_group_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "test_probe.py").write_text(PROBE, encoding="utf-8")
    done = nested_collect(tmp_path, "--test-group", "3/2")
    assert done.returncode == pytest.ExitCode.USAGE_ERROR, done.stdout + done.stderr
    assert "--test-group takes N/M" in done.stdout + done.stderr


def test_ci_ends_pytest_itself_before_a_test_jobs_limit() -> None:
    """A~4 of Quick Fixes 9: a test job the runner cancels at its limit keeps no summary, rerun reasons or junit.xml
    (Ubuntu CI 41468043383), so pytest's --session-timeout ends it first: with room left in the job for the test
    running then (its tries) and the steps after."""
    workflow = (ROOT / ".github" / "workflows" / "ci-test.yml").read_text(encoding="utf-8")
    [(windows_job, other_job)] = re.findall(r"timeout-minutes: \$\{\{ inputs\.os == 'windows' && (\d+) \|\| (\d+) \}\}",
                                            workflow.split("name: Tests", 1)[1])
    [(windows_pytest, other_pytest)] = re.findall(r"--session-timeout=\$\{\{ inputs\.os == 'windows' && (\d+) \|\| (\d+) \}\}",
                                                  workflow)
    for job, pytest_seconds in ((windows_job, windows_pytest), (other_job, other_pytest)):
        assert int(pytest_seconds) <= int(job) * 60 - 8 * 60, (job, pytest_seconds)  # (8 min for the rest.)
