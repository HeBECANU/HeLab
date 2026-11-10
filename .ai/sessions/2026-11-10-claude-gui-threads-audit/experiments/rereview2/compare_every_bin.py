"""Compare two ``test_every_bin_same.py`` outputs: ``python compare_every_bin.py BEFORE.npz AFTER.npz``. Prints each
key that differs (or is in one only) and a count; exit 1 if any differs."""
from __future__ import annotations

import sys

import numpy as np


def main() -> int:
    before, after = (np.load(path, allow_pickle=True) for path in sys.argv[1:3])  # (Our own files.)
    keys = sorted(set(before.files) | set(after.files))
    differ = []
    for key in keys:
        if key not in before.files or key not in after.files:
            differ.append(f"{key}: only {'after' if key in after.files else 'before'}")
        elif not np.array_equal(before[key], after[key]):
            differ.append(f"{key}: differs")
    for line in differ:
        print(line)
    print(f"{len(keys)} arrays compared, {len(differ)} differ")
    return 1 if differ else 0


if __name__ == "__main__":
    raise SystemExit(main())
