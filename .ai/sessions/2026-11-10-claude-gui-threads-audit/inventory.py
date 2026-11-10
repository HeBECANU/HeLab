"""Static inventory of calls that can block, in ``helab/``, with the function that holds each (GT audit, step 1).

Run from the checkout's root: ``python .ai/sessions/2026-11-10-claude-gui-threads-audit/inventory.py [--all]``.
It prints one tab-separated row per hit: category, module:line, enclosing function, the call as written.
Modules that only run in a helper or a headless process (``HELPER_ONLY``) are left out unless ``--all``.
Reachability from the GUI thread is traced by hand from this list (see audit.md): an AST can't tell which
thread runs a function.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path("helab")
# Run only in a helper process, the headless converter, ``helab cache``, a script probe or release tooling.
HELPER_ONLY = ("helab/io_helper.py", "helab/io_ops/", "helab/convert_cli.py", "helab/cache_cli.py",
               "helab/release.py", "helab/release_draft.py", "helab/scripts/probe.py", "helab/updates/updater.py",
               "helab/scripts/legacy_plotly/", "helab/convert/backends/", "helab/dependency_snapshot.py")

# Call names (the last attribute, or ``module.attr``) and their category.
EXACT = {
    # waits
    "time.sleep": "wait", "sleep": "wait", "select.select": "wait",
    "subprocess.run": "wait", "subprocess.check_output": "wait", "subprocess.check_call": "wait",
    "subprocess.call": "wait", "subprocess.Popen": "proc", "os.waitpid": "wait",
    # file-system I/O
    "open": "io", "io.open": "io", "os.listdir": "io", "os.scandir": "io", "os.walk": "io", "os.stat": "io",
    "os.lstat": "io", "os.path.exists": "io", "os.path.isfile": "io", "os.path.isdir": "io",
    "os.path.islink": "io", "os.path.ismount": "io", "os.path.getsize": "io", "os.path.getmtime": "io",
    "os.path.realpath": "io", "os.path.samefile": "io", "os.path.lexists": "io", "os.makedirs": "io",
    "os.mkdir": "io", "os.remove": "io", "os.unlink": "io", "os.replace": "io", "os.rename": "io",
    "os.rmdir": "io", "os.access": "io", "os.statvfs": "io", "os.utime": "io", "os.fsync": "io",
    "os.open": "io", "os.read": "io", "os.write": "io", "glob.glob": "io", "glob.iglob": "io",
    "shutil.rmtree": "io", "shutil.copy": "io", "shutil.copy2": "io", "shutil.copyfile": "io",
    "shutil.copytree": "io", "shutil.move": "io", "shutil.disk_usage": "io", "shutil.which": "io",
    "tempfile.mkdtemp": "io", "tempfile.mkstemp": "io", "tempfile.NamedTemporaryFile": "io",
    "tempfile.TemporaryFile": "io", "tempfile.TemporaryDirectory": "io",
    "json.load": "io", "json.dump": "io", "np.load": "io", "np.save": "io", "np.savez": "io",
    "np.loadtxt": "io", "np.genfromtxt": "io", "numpy.load": "io",
    "sqlite3.connect": "io", "psutil.disk_partitions": "io", "psutil.disk_usage": "io",
    # network
    "urllib.request.urlopen": "net", "urlopen": "net", "socket.socket": "net", "socket.create_connection": "net",
    "http.client.HTTPSConnection": "net", "requests.get": "net",
    # imports of code chosen at run time
    "importlib.import_module": "import", "importlib.reload": "import", "spec.loader.exec_module": "import",
    "runpy.run_path": "import",
    # nested event loops
    "QApplication.processEvents": "loop", "QCoreApplication.processEvents": "loop",
    # output that may block
    "print": "out", "faulthandler.dump_traceback": "out",
}
# Method names (any receiver) and their category; noisy, so each is kept to names that rarely mean anything else.
METHODS = {
    "join": "wait?", "wait": "wait", "acquire": "wait?", "communicate": "wait", "result": "wait?",
    "get": None, "put": None,  # (only when the receiver's name says queue)
    "exec": "loop", "exec_": "loop", "processEvents": "loop",
    "sync": "settings", "exists": "io?", "is_dir": "io?", "is_file": "io?", "resolve": "io?", "stat": "io?",
    "read_text": "io", "read_bytes": "io", "write_text": "io", "write_bytes": "io", "iterdir": "io",
    "rglob": "io", "mkdir": "io?", "unlink": "io?", "touch": "io", "samefile": "io",
    "flush": "out?", "dump_traceback_later": "out",
    "setValue": "settings?", "remove": None,
}
QUEUEISH = ("queue", "_q", "chunks", "inbox", "outbox")


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func) + "()"
    return ""


class Finder(ast.NodeVisitor):
    def __init__(self, module: str, source: str) -> None:
        self.module, self.source = module, source
        self.stack: list[str] = []
        self.rows: list[tuple[str, str, int, str, str]] = []

    def where(self) -> str:
        return ".".join(self.stack) or "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def add(self, category: str, node: ast.AST) -> None:
        text = (ast.get_source_segment(self.source, node) or "").splitlines()[0][:110]
        self.rows.append((category, self.module, getattr(node, "lineno", 0), self.where(), text))

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            name = dotted(item.context_expr).lower()
            if "lock" in name or "mutex" in name or "condition" in name:
                self.add("lock", item.context_expr)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "BlockingQueuedConnection":
            self.add("blocking-signal", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted(node.func)
        category = EXACT.get(name)
        if category is None and "." in name:
            tail = name.rsplit(".", 1)[1]
            receiver = name.rsplit(".", 1)[0].lower()
            if tail in ("get", "put"):
                if any(word in receiver for word in QUEUEISH) and not any(
                        k.arg in ("block", "timeout") or isinstance(k.value, ast.Constant) and k.value.value is False
                        for k in node.keywords) and not tail.endswith("nowait"):
                    category = "wait"
            elif tail == "QEventLoop" or name.endswith("QEventLoop"):
                category = "loop"
            elif tail in METHODS and METHODS[tail] is not None:
                category = METHODS[tail]
            elif name.startswith(("subprocess.", "shutil.", "sqlite3.", "socket.", "urllib.", "http.")):
                category = "io"
        if name in ("QEventLoop",):
            category = "loop"
        if category:
            self.add(category, node)
        self.generic_visit(node)


def main(all_modules: bool) -> int:
    rows = []
    for path in sorted(ROOT.rglob("*.py")):
        module = path.as_posix()
        if not all_modules and module.startswith(HELPER_ONLY):
            continue
        source = path.read_text(encoding="utf-8")
        finder = Finder(module, source)
        finder.visit(ast.parse(source))
        rows.extend(finder.rows)
    for category, module, line, where, text in rows:
        print(f"{category}\t{module}:{line}\t{where}\t{text}")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[0]] = counts.get(row[0], 0) + 1
    print("# " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--all" in sys.argv))
