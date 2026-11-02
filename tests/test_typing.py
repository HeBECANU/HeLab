import os
import subprocess

import pytest

# The checkout's root, where the type checkers run (their own subprocess's working folder, not this
# process's: these tests run first, and the tests after them run where pytest started).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each runs a whole type checker: pyright on helab took 58-73 s on macOS and Windows CI and 115-142 s on a
# slow macOS runner (caching-v2 CI 41389534725, job 125097691928: CI's --timeout=120 killed it five times),
# so CI's per-test 120 s is too little for them.
TYPE_CHECK_SECONDS = 300
pytestmark = pytest.mark.timeout(TYPE_CHECK_SECONDS)


def cache(name: str) -> list[str]:
    """Each mypy run's own cache folder: these run at once, on separate xdist workers, and mypy runs
    sharing one SQLite cache crashed ("database is locked" setting its journal mode)."""
    return ['--cache-dir', os.path.join('.mypy_cache', 'test_typing', name)]


def test_mypy_helab_soft() -> None:
    result = subprocess.run(['mypy', 'helab', *cache('helab')], capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "mypy type check failed"

def test_mypy_helab_strict() -> None:
    result = subprocess.run(['mypy', 'helab', '--strict', *cache('helab-strict')],
                            capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "mypy type check on helab failed"

def test_mypy_helab_tests_soft() -> None:
    result = subprocess.run(['mypy', 'tests', *cache('tests')], capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "mypy type check on tests failed"

def test_mypy_helab_tests_strict() -> None:
    result = subprocess.run(['mypy', 'tests', '--strict', *cache('tests-strict')],
                            capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "mypy type check on tests failed"


def test_pyright_helab() -> None:
    result = subprocess.run(['pyright', 'helab'], capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "pyright type check on helab failed"


def test_pyright_tests() -> None:
    result = subprocess.run(['pyright', 'tests'], capture_output=True, text=True, cwd=ROOT)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, "pyright type check on tests failed"


def test_the_type_checks_get_more_time_than_cis_per_test_timeout() -> None:
    """Every test here keeps its own timeout over CI's ``--timeout=120`` (a whole type checker each)."""
    assert pytestmark.name == "timeout" and pytestmark.args == (TYPE_CHECK_SECONDS,) and TYPE_CHECK_SECONDS >= 300


if __name__ == "__main__":
    test_mypy_helab_soft()
    test_mypy_helab_strict()
    test_mypy_helab_tests_soft()
    test_mypy_helab_tests_strict()

    test_pyright_helab()
    test_pyright_tests()
