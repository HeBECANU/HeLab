"""Summarise ``stall_probe``'s output: GUI-thread stalls by the HeLab code that held them.

``python .ai/sessions/2026-11-10-claude-gui-threads-audit/aggregate.py DIR [MIN_SECONDS]`` prints, for each
place (the topmost HeLab frame's file:line and function), how many stalls, the longest, and the tests, then
one sample stack per place.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from typing import Any


def short(path: str) -> str:
    return path.split(f"{os.sep}helab{os.sep}", 1)[-1] if f"{os.sep}helab{os.sep}" in path else path


def main() -> int:
    folder = sys.argv[1]
    least = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    places: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name in glob.glob(os.path.join(folder, "stalls-*.jsonl")):
        with open(name, encoding="utf-8") as handle:
            for line in handle:
                stall = json.loads(line)
                if stall.get("seconds", 0) < least or not stall["samples"]:
                    continue
                top = stall["samples"][-1]["top"] or ["?", 0, "?"]
                places[f"{short(top[0])}:{top[1]} {top[2]}"].append(stall)
    ranked = sorted(places.items(), key=lambda item: -max(s["seconds"] for s in item[1]))
    for place, stalls in ranked:
        longest = max(stalls, key=lambda s: s["seconds"])
        tests = sorted({s["test"].split("::")[0] for s in stalls})
        print(f"{longest['seconds']:7.2f} s max  x{len(stalls):<3} {place}   [{', '.join(tests[:4])}"
              f"{' …' if len(tests) > 4 else ''}]")
    print()
    for place, stalls in ranked:
        longest = max(stalls, key=lambda s: s["seconds"])
        print(f"== {place} ({longest['seconds']:.2f} s, {longest['test']})")
        for frame in longest["samples"][-1]["stack"][-14:]:
            print("   " + frame[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
