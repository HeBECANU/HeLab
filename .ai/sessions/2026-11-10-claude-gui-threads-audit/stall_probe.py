"""A pytest plugin for the GT audit: the GUI thread's stack whenever its event loop misses beats.

Load it with ``PYTHONPATH=.ai/sessions/2026-11-10-claude-gui-threads-audit pytest -p stall_probe ...`` and set
``GT_STALL_DIR`` to a folder for its output (one ``stalls-<worker>.jsonl`` per xdist worker). It changes nothing
in HeLab: a ``QTimer`` on the GUI thread beats every ``BEAT`` s once a ``QApplication`` exists, and a watching
thread samples the main thread's Python stack (``sys._current_frames``) when no beat came for ``STALL`` s.

A stall counts only when the event loop was running under the stalled code: some frame below the topmost
``helab`` frame is on a line that turns the event loop (``processEvents``, ``qWait``, ``waitUntil``, ``exec(``,
a ``qtbot.wait*``...), so test code calling HeLab directly is not counted. ``aggregate.py`` summarises.
"""
from __future__ import annotations

import json
import re
import linecache
import os
import sys
import threading
import time
from typing import Any

import pytest

BEAT = 0.05
STALL = float(os.environ.get("GT_STALL_SECONDS", "0.3"))
# A line that turns the event loop, in a test, HeLab or pytest-qt (never pytest's own or another library's frames).
LOOP_LINE = re.compile(r"\b(processEvents|qWait|waitUntil|waitSignals?|waitExposed|waitActive|waitCallback|"
                       r"sendPostedEvents)\b|\.exec_?\(|\bqtbot\.wait\(|self\._loop\.exec|loop\.exec")
LOOP_FILES = (f"{os.sep}tests{os.sep}", f"{os.sep}helab{os.sep}", f"{os.sep}pytestqt{os.sep}")
# In-process helper code a test runs on the GUI thread is the test's, not the GUI process's.
NOT_GUI = (f"{os.sep}helab{os.sep}io_ops{os.sep}", f"{os.sep}helab{os.sep}io_helper.py")

_state: dict[str, Any] = {"beat": time.monotonic(), "timer": None, "test": "", "stall": None}
_lock = threading.Lock()


def _out() -> Any:
    folder = os.environ.get("GT_STALL_DIR")
    if not folder:
        return None
    os.makedirs(folder, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return open(os.path.join(folder, f"stalls-{worker}.jsonl"), "a", encoding="utf-8", buffering=1)


_file = None


def _frames(frame: Any) -> list[tuple[str, int, str, str]]:
    stack = []
    while frame is not None:
        code = frame.f_code
        stack.append((code.co_filename, frame.f_lineno, code.co_qualname if hasattr(code, "co_qualname") else
                      code.co_name, linecache.getline(code.co_filename, frame.f_lineno).strip()))
        frame = frame.f_back
    stack.reverse()  # outermost first
    return stack


def _helab(filename: str) -> bool:
    return f"{os.sep}helab{os.sep}" in filename and f"{os.sep}tests{os.sep}" not in filename


def _in_loop(stack: list[tuple[str, int, str, str]]) -> tuple[bool, int]:
    """Whether the topmost helab frame runs under an event loop; that frame's index."""
    top = max((i for i, f in enumerate(stack) if _helab(f[0])), default=-1)
    if top < 0:
        return False, -1
    first = min(i for i, f in enumerate(stack) if _helab(f[0]))
    # A loop turned anywhere below the topmost helab frame (a test's wait, or HeLab's own nested exec).
    if any(part in stack[top][0] for part in NOT_GUI):
        return False, top
    for i in range(top - 1, -1, -1):
        if any(part in stack[i][0] for part in LOOP_FILES) and LOOP_LINE.search(stack[i][3]):
            # The code it dispatched into must be HeLab's (the first frame above the loop that is).
            return any(_helab(f[0]) and not any(p in f[0] for p in NOT_GUI) for f in stack[i + 1:]), top
    return False, top if first >= 0 else -1


def _watch() -> None:
    main = threading.main_thread().ident
    while True:
        time.sleep(BEAT / 2)
        now = time.monotonic()
        late = now - _state["beat"]
        with _lock:
            stall = _state["stall"]
            if late < STALL:
                if stall is not None:
                    if stall["counted"] and _file is not None:
                        stall["seconds"] = round(stall["last"] - stall["start"], 3)
                        _file.write(json.dumps(stall) + "\n")
                    _state["stall"] = None
                continue
            frame = sys._current_frames().get(main)
            if frame is None:
                continue
            stack = _frames(frame)
            looping, top = _in_loop(stack)
            if stall is None:
                # ``start``: when the event loop was first seen running under HeLab code in this stall (a test's
                # own work before it, with no loop running, isn't counted), less the STALL it took to notice
                # when that was at once.
                stall = _state["stall"] = {"test": _state["test"], "start": now - STALL if looping else None,
                                           "last": now, "counted": looping, "samples": []}
            elif looping and stall["start"] is None:
                stall["start"] = now
            stall["last"] = now
            stall["counted"] = stall["counted"] or looping
            if looping and len(stall["samples"]) < 6 and (not stall["samples"] or now - stall["samples"][-1]["at"] > 0.5):
                inner = [f for f in stack if _helab(f[0]) or "site-packages" in f[0] or "lib/python" in f[0]]
                stall["samples"].append({"at": now, "top": stack[top][:3] if top >= 0 else None,
                                         "stack": [f"{f[0].split(os.sep + 'helab' + os.sep, 1)[-1]}:{f[1]} {f[2]}: {f[3]}"
                                                   for f in stack[-25:]], "inner": len(inner)})


def _beat() -> None:
    _state["beat"] = time.monotonic()


def pytest_configure(config: pytest.Config) -> None:
    global _file
    _file = _out()
    threading.Thread(target=_watch, daemon=True, name="gt-stall-probe").start()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Any:
    _state["test"] = item.nodeid
    if _state["timer"] is None:
        try:
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None:
                timer = QTimer()
                timer.timeout.connect(_beat)
                timer.start(int(BEAT * 1000))
                _state["timer"] = timer
        except Exception:
            pass
    _state["beat"] = time.monotonic()
    yield
    _state["beat"] = time.monotonic()
    with _lock:
        stall = _state["stall"]
        if stall is not None and stall["counted"] and _file is not None:
            stall["seconds"] = round(stall["last"] - stall["start"], 3)
            stall["ended_with_test"] = True
            _file.write(json.dumps(stall) + "\n")
        _state["stall"] = None  # (Test teardown isn't counted.)
