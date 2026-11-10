"""GT audit: does ``quit_watch.exit_soon`` still end the process when stderr takes nothing?

Run as ``python .ai/sessions/2026-11-10-claude-gui-threads-audit/quit_watch_check.py``. A child process points
fd 2 at a pipe nobody reads and fills it (a console paused by a selection, as it is after ``ConsoleTee.stop``
points fd 2 back at the terminal), logs to stderr as ``coloredlogs`` does, starts ``exit_soon(7, 0.2)``, and then
keeps its main thread busy for 5 s (a lingering teardown). The parent reports how long the child took and its
exit code: 7 within ~0.2 s means the watch ended it; anything later means the watch was stuck in its log call.
A control run drains the pipe.
``helab.views.quit_watch`` is standard library only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

CHILD = r"""
import fcntl, logging, os, sys, time
BLOCKED = sys.argv[1] == "blocked"
read, write = os.pipe()
os.dup2(write, 2)
flags = fcntl.fcntl(2, fcntl.F_GETFL)
fcntl.fcntl(2, fcntl.F_SETFL, flags | os.O_NONBLOCK)
try:
    while BLOCKED:
        os.write(2, b"x" * 4096)
except BlockingIOError:
    pass
if not BLOCKED:
    import threading
    threading.Thread(target=lambda: [os.read(read, 65536) for _ in iter(int, 1)], daemon=True).start()
fcntl.fcntl(2, fcntl.F_SETFL, flags)  # (Blocking again, as a console's handle is.)
logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))
from helab.views import quit_watch
quit_watch.exit_soon(7, 0.2)
time.sleep(5)
"""


def main() -> int:
    for mode in ("drained", "blocked"):
        start = time.monotonic()
        try:
            code: object = subprocess.run([sys.executable, "-c", CHILD, mode], cwd=os.getcwd(), timeout=20).returncode
        except subprocess.TimeoutExpired:
            code = "none: still running after 20 s, killed"
        print(f"stderr {mode}: child ended after {time.monotonic() - start:.2f} s, exit code {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
