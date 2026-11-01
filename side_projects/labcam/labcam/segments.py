"""A small 7-segment display (dark segments on a light LCD), read segment by segment rather than by OCR.

The box goes tightly around the digits (four corners, so a display seen at an angle is straightened); the
digits are taken as `digits` equal cells across it (or `cells`, [start, end] fractions of the width, when the
decimal point leaves a gap), leaning right by `slant` (the top's shift, as a fraction of a cell's width). In
each cell the seven segments' places are sampled; a segment is on when it's darker than halfway between the
box's light (90th percentile) and dark (10th). The pattern gives the digit, or "?" for no known digit.

Like the wavemeter, every digit position is voted over the last `vote_s` seconds of checks: a position counts
only checks that read a digit there, its winner needs `agree` of those votes, and how sure (confidence) is the
weakest position's share times the fraction of checks that read a digit at all — so frames it can't read lower
the confidence without voting.

`point`: digits before the decimal point (default 1: "0.08"). The value's sign isn't read; `offset` is the
value, so the lock sign `<name>:middle` holds while it's within `tolerance` (e.g. 0.3) of zero.
"""

from __future__ import annotations

import collections
import threading
import time

import cv2
import numpy as np

from .config import Instrument
from .detectors import Detector, Image, Reading

# Segment places in a cell, (across, down) as fractions: a top, b upper right, c lower right, d bottom,
# e lower left, f upper left, g middle.
PLACES = {"a": (0.5, 0.06), "b": (0.9, 0.27), "c": (0.9, 0.73), "d": (0.5, 0.94), "e": (0.1, 0.73),
          "f": (0.1, 0.27), "g": (0.5, 0.5)}
DIGITS = {"abcdef": "0", "bc": "1", "abdeg": "2", "abcdg": "3", "bcfg": "4", "acdfg": "5", "acdefg": "6",
          "cdefg": "6", "abc": "7", "abcf": "7", "abcdefg": "8", "abcdfg": "9", "abcfg": "9", "ef": "1"}


def read_cells(grey: np.ndarray, cells: list[tuple[float, float]], slant: float) -> tuple[str, float]:
    """The digits read from a straightened grey image, "?" where a cell's pattern is no digit; and the contrast
    (light minus dark), which is small when there are no digits to see."""
    h, w = grey.shape
    light, dark = float(np.percentile(grey, 90)), float(np.percentile(grey, 10))
    contrast = light - dark
    halfway = dark + contrast / 2
    r = max(1, int(round(min(h, w) * 0.03)))
    out = []
    dark_mask = grey < halfway
    for start, end in cells:
        # The digit's own extent in its cell (the box needn't be tight): rows and columns with dark pixels.
        c0, c1 = int(start * w), max(int(start * w) + 1, int(end * w))
        cell = dark_mask[:, c0:c1]
        rows = np.flatnonzero(cell.mean(axis=1) > 0.1)
        cols = np.flatnonzero(cell.mean(axis=0) > 0.15)
        if len(rows) < h * 0.3 or len(cols) < 2:
            out.append("?")
            continue
        top, bottom = float(rows[0]), float(rows[-1] + 1)
        left, right = c0 + float(cols[0]), c0 + float(cols[-1] + 1)
        if right - left < 0.4 * (c1 - c0):  # only a narrow upright stroke: a "1" (its two right segments)
            out.append("1" if bottom - top > 0.6 * h else "?")
            continue
        dh, dw = bottom - top, right - left
        on = ""
        for name, (u, v) in PLACES.items():
            # Slant: the top leans right by `slant` of the width; the extent's left and right include it.
            lean = slant * dw
            x = left + lean / 2 + (u - 0.5) * (dw - lean) + (dw - lean) / 2 + lean * (0.5 - v)
            y = top + v * dh
            x0, x1 = int(max(0, x - r)), int(min(w, x + r + 1))
            y0, y1 = int(max(0, y - r)), int(min(h, y + r + 1))
            if x1 > x0 and y1 > y0 and float(grey[y0:y1, x0:x1].mean()) < halfway:
                on += name
        out.append(DIGITS.get("".join(sorted(on)), "?"))
    return "".join(out), contrast


class SevenSegment(Detector):
    oversample = 8.0

    def __init__(self, inst: Instrument) -> None:
        super().__init__(inst)
        n = int(inst.option("digits", 3))
        given = inst.options.get("cells")
        self.cells = [(float(a), float(b)) for a, b in given] if isinstance(given, list) else \
            [(k / n, (k + 1) / n) for k in range(n)]
        self.frames: collections.deque[tuple[float, str]] = collections.deque()
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.frames.clear()

    def update(self, roi: Image) -> Reading:
        grey = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
        read, contrast = read_cells(grey, self.cells, self.inst.option("slant", 0.15))
        if contrast < self.inst.option("contrast", 20.0):
            read = "?" * len(self.cells)  # nothing like digits: an unreadable check
        now = time.time()
        with self._lock:
            self.frames.append((now, read))
            while self.frames and now - self.frames[0][0] > self.inst.option("vote_s", 5.0):
                self.frames.popleft()
            reads = [r for _, r in self.frames]
        return tally(self.inst, read, reads, contrast)


def tally(inst: Instrument, read: str, reads: list[str], contrast: float) -> Reading:
    """The vote over `reads` (each a digit string, "?" where unread), as a Reading."""
    positions = len(reads[-1]) if reads else 0
    shown, shares, readable = "", [], []
    for p in range(positions):
        votes = [r[p] for r in reads if len(r) > p and r[p] != "?"]
        readable.append(len(votes) / len(reads))
        if not votes:
            shown += "?"
            shares.append(0.0)
            continue
        digit, count = collections.Counter(votes).most_common(1)[0]
        share = count / len(votes)
        shares.append(share)
        shown += digit if share >= inst.option("agree", 0.6) and len(votes) / len(reads) >= 0.3 else "?"
    point = int(inst.option("point", 1))
    text = shown[:point] + "." + shown[point:] if 0 < point < len(shown) else shown
    confidence = min((s * f for s, f in zip(shares, readable)), default=0.0)
    values: dict[str, float | str | None] = {
        "shown": text, "this_check": read, "per_digit": " ".join(f"{s:.0%}" for s in shares),
        "readable": " ".join(f"{f:.0%}" for f in readable), "checks": len(reads), "contrast": round(contrast, 1),
    }
    if not positions or shown.startswith("?"):
        return Reading("unknown", text or "unreadable", values, round(confidence, 2),
                       "some digits unsure or unread" if positions else "no checks yet")
    # An unsure later digit needn't matter: 0.0? is within ±0.3 whatever it is. Decided when the lowest and
    # highest values it could be fall on the same side; how sure then counts only the digits it rests on.
    low, high = float(text.replace("?", "0")), float(text.replace("?", "9"))
    tolerance = inst.option("tolerance", 0.3)
    if (abs(low) <= tolerance) != (abs(high) <= tolerance):
        return Reading("unknown", text, values, round(confidence, 2), f"unsure digits decide whether it's within ±{tolerance:g}")
    if "?" in shown:
        sure = [s * f for s, f, d in zip(shares, readable, shown) if d != "?"]
        confidence = min(sure, default=0.0)
    else:
        values["value"] = low
    values["offset"] = (low + high) / 2
    within = abs(low) <= tolerance
    return Reading("ok" if within else "off", f"{text} ({'within' if within else 'beyond'} ±{tolerance:g})",
                   values, round(confidence, 2), "an unsure last digit, but it can't change that" if "?" in shown else "")
