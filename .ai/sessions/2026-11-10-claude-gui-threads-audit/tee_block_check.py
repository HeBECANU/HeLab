"""GT audit: does a log line on the GUI thread wait when the console tee's file write is slow?

Run as ``python .ai/sessions/2026-11-10-claude-gui-threads-audit/tee_block_check.py OUT_DIR [SECONDS]``. It
starts ``ConsoleTee`` in this process (only ``helab.utils.console_tee``, standard library, is imported), makes
its file write take SECONDS (default 3) once, then logs 2,000 lines of 100 bytes to stderr through a
``StreamHandler`` as ``coloredlogs`` does in the app, timing the slowest call. It prints the result on the
original stderr (fd kept before the tee).
"""
from __future__ import annotations

import logging
import os
import sys
import time

from helab.utils import console_tee


def main() -> int:
    out = sys.argv[1]
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    report = os.fdopen(os.dup(2), "w", buffering=1)
    tee = console_tee.ConsoleTee(os.path.join(out, "console-check.txt"))
    tee.start()
    real_write = tee.write
    slowed = [False]

    def slow_write(chunk: bytes) -> None:
        if not slowed[0]:
            slowed[0] = True
            time.sleep(delay)  # A file write held up (a busy disk, an antivirus scan of the file).
        real_write(chunk)

    tee.write = slow_write  # type: ignore[method-assign]
    handler = logging.StreamHandler(sys.stderr)
    logger = logging.getLogger("gt")
    logger.addHandler(handler)
    logger.propagate = False
    worst, at = 0.0, -1
    start = time.monotonic()
    for i in range(2000):
        t = time.monotonic()
        logger.warning("x" * 99)
        took = time.monotonic() - t
        if took > worst:
            worst, at = took, i
    total = time.monotonic() - start
    tee.stop()
    print(f"file write held {delay:.1f} s: slowest log call {worst:.3f} s (line {at}, after {at * 100:,} bytes); "
          f"2,000 lines in {total:.3f} s", file=report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
