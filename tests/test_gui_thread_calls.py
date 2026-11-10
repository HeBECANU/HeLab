"""Guard (1) of the GUI-thread audit: no new call that can block in HeLab's GUI modules without saying why.

An AST scan of ``helab/views`` and ``helab/models`` (code the GUI thread runs: slots, timers, ``render``,
``data()``) for calls that wait, list or copy folders, start processes, open sockets or databases, read mount
tables, import code chosen at run time, run a nested event loop or open a native file dialog, and HeLab's own
utilities that do those (``DENIED``). Each hit must be in ``tests/data/gui_thread_allowed.txt`` as
``module:function:call  # reason``; an entry that no longer matches fails too, so the list stays true.
Direct calls only: a utility two calls down isn't seen unless it is in ``DENIED``. Not scanned: ``open``,
``os.stat`` and the like, too common for HeLab's own small local files (the audit's inventory lists them).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("helab/views", "helab/models")
ALLOWED = ROOT / "tests" / "data" / "gui_thread_allowed.txt"

# Calls by their dotted name as written.
CALLS = {
    "time.sleep", "subprocess.run", "subprocess.Popen", "subprocess.check_output", "subprocess.call",
    "subprocess.check_call", "os.listdir", "os.scandir", "os.walk", "glob.glob", "glob.iglob", "shutil.rmtree",
    "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.move", "sqlite3.connect",
    "socket.socket", "socket.create_connection", "urllib.request.urlopen", "psutil.disk_partitions",
    "importlib.import_module", "importlib.reload", "QEventLoop", "os.path.realpath", "faulthandler.dump_traceback",
    "QFileDialog.getExistingDirectory", "QFileDialog.getOpenFileName", "QFileDialog.getOpenFileNames",
    "QFileDialog.getSaveFileName",
}
# Calls by their last name, on any receiver.
METHODS = {"waitForFinished", "waitForStarted", "waitForReadyRead", "waitForBytesWritten", "communicate",
           "exec_module", "processEvents", "iterdir", "rglob", "sync"}
# HeLab's own utilities that read mount tables or files (by their last name).
DENIED = {"current_mounts", "mount_table", "share_of", "cache_location_problem", "file_hash"}


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def hits() -> set[str]:
    """Every scanned call as ``module:function:call``."""
    found: set[str] = set()
    for folder in SCANNED:
        for path in sorted((ROOT / folder).rglob("*.py")):
            module = path.relative_to(ROOT).as_posix()

            def visit(node: ast.AST, where: str) -> None:
                for child in ast.iter_child_nodes(node):
                    inner = where
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        inner = f"{where}.{child.name}" if where else child.name
                    if isinstance(child, ast.Call):
                        name = dotted(child.func)
                        last = name.rsplit(".", 1)[-1]
                        if name in CALLS or last in METHODS or last in DENIED:
                            found.add(f"{module}:{inner or '<module>'}:{name}")
                    visit(child, inner)
            visit(ast.parse(path.read_text(encoding="utf-8")), "")
    return found


def allowed() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in ALLOWED.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        entry, _, reason = line.partition("#")
        assert reason.strip(), f"no reason given: {line}"
        entries[entry.strip()] = reason.strip()
    return entries


def test_every_blocking_call_in_gui_modules_is_allowed_with_a_reason() -> None:
    found, listed = hits(), allowed()
    new = sorted(found - listed.keys())
    assert not new, ("Calls that can block on the GUI thread, not in tests/data/gui_thread_allowed.txt (move them "
                     "to a helper or the worker, or list them with why they can't block):\n" + "\n".join(new))
    gone = sorted(listed.keys() - found)
    assert not gone, "Allowed calls no longer made (remove them from the list):\n" + "\n".join(gone)


def test_the_scan_finds_what_it_looks_for() -> None:
    """(A seeded case each: the scan itself works.)"""
    tree = ast.parse("def f():\n    os.listdir(x)\n    proc.waitForFinished()\n    cache_location.share_of(p)\n")
    calls = [dotted(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert calls == ["os.listdir", "proc.waitForFinished", "cache_location.share_of"]
    assert {call for call in calls if call in CALLS or call.rsplit(".", 1)[-1] in METHODS | DENIED} == set(calls)
