"""Repro of the Ground CI rerun (41463943327, job 125340069131): copy into tests/ and run with pytest.

Cause: the reload-waits test waited for ``runner.in_flight()``, which counts a job from when it is queued,
not from when its ``compute`` starts. On a busy runner the job was still queued when ``reload_scripts``
cancelled it; the worker then ended it at once without computing, so ``in_flight()`` was empty at the test's
next checks (``"Reload (waiting)"``, or line 206's ``len(in_flight()) == 1``). With the worker reaching the
job only after the cancel (``late`` waiting for ``cancel_event``), the old test fails every time on
``assert 'Reload' == 'Reload (waiting)'``. The fixed tests wait for the compute's own ``STARTED`` event; as
saved here, ``late`` only delays each job (a busy runner) and both fixed tests pass."""
import time
from typing import Any

import pytest

from helab.analysis import runner_core
from test_live_scripts import *  # noqa: F401,F403
from test_live_scripts import test_a_reload_waits_for_a_run_of_its_scripts_on_the_worker_thread as original
from test_live_scripts import test_removing_the_folder_a_reload_waits_for_ends_the_wait as original_l2


@pytest.fixture(autouse=True)
def late_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    run = runner_core.AnalysisQueue._run

    def late(self: Any, script: Any, context: Any, *args: Any) -> None:
        # The worker reaches the job only once it was cancelled (a busy runner), then ends it at once.
        time.sleep(0.3)  # (A busy runner: the job starts late.)
        run(self, script, context, *args)

    cancel = runner_core.AnalysisQueue.cancel

    def cancel_then_yield(self: Any, job_id: str) -> None:
        cancel(self, job_id)
        time.sleep(0.2)  # (The GUI thread is slow to go on: the worker ends the job meanwhile.)

    monkeypatch.setattr(runner_core.AnalysisQueue, "cancel", cancel_then_yield)

    monkeypatch.setattr(runner_core.AnalysisQueue, "_run", late)


def test_repro(qtbot, cache, windows, tmp_path) -> None:  # type: ignore[no-untyped-def]
    original(qtbot, cache, windows, tmp_path)


def test_repro_l2(qtbot, cache, windows, tmp_path) -> None:  # type: ignore[no-untyped-def]
    original_l2(qtbot, cache, windows, tmp_path)
