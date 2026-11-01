"""The wavemeter's display: wavelength (nm) or frequency (GHz), and power, read by OCR.

The reader is RapidOCR (PaddleOCR's recognition model on ONNX Runtime, about 5 ms a read) when installed, else
Tesseract. The display is small in the frame (digits about 13 px tall, bold, slanted, blurred into each other):
on 16 frames of 2026-11-01, Tesseract read the power's digits from none of them, RapidOCR from about half, and
Tesseract confuses 8, 6, 5, 3 and 2 and drops the decimal point. So:
- each field is its own instrument (`field` "main" for the wavelength or frequency, "power" for the power),
  whose four corners follow the text; the engine cuts it out straightened and 3x oversampled;
- each frame is read several ways (RapidOCR: the colours at 3x, 4x and 6x and the cleaned-up green at 4x;
  Tesseract: two enlargements, three small turns around `tilt`), and only the digits are kept: the decimal point goes where the display's format puts it (`format`, e.g. "####.###");
- every digit position is voted on over those reads and the last `vote_s` seconds of frames (default 10). A
  position whose winner has less than `agree` of the votes shows as "?", and the reading is then `unknown`, not
  a guess. Reads without the format's digits don't vote, but count against how sure: confidence is the weakest
  position's share times the fraction of reads that were readable.
"""

from __future__ import annotations

import collections
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np


from .config import Instrument
from .detectors import Detector, Image, Reading, duration

log = logging.getLogger("labcam.wavemeter")

def _find_tesseract() -> str | None:
    """`LABCAM_TESSERACT`, else on PATH, else Windows' usual install folders."""
    named = os.environ.get("LABCAM_TESSERACT")
    if named:
        return named if Path(named).is_file() else None
    found = shutil.which("tesseract")
    if found:
        return found
    for folder in (os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "") + "\\Programs"):
        candidate = Path(folder) / "Tesseract-OCR" / "tesseract.exe"
        if folder and candidate.is_file():
            return str(candidate)
    return None


TESSERACT = _find_tesseract()


def _rapid() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped,import-not-found,unused-ignore]
    except ImportError:
        return None
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    return RapidOCR()


RAPID = _rapid()
READER = "RapidOCR" if RAPID is not None else (f"Tesseract ({TESSERACT})" if TESSERACT else None)
_rapid_lock = threading.Lock()  # one recognition at a time per model (ONNX Runtime uses several cores itself)


def rapid_read(image: Image) -> str:
    with _rapid_lock:
        result, _ = RAPID(image, use_det=False, use_cls=False, use_rec=True)
    return str(result[0][0]) if result else ""

# Formats by unit: # is a digit. The unit decides between them where the OCR caught it (G, H or z → GHz).
FORMATS = {"nm": "####.###", "GHz": "######.##", "power": "###.##"}


def digits_for(text: str, fmt: str) -> str | None:
    """The digit string of `text` if it has exactly as many digits as `fmt`."""
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) == fmt.count("#") else None


def with_point(digits: str, fmt: str) -> str:
    """Digits (or "?") placed into `fmt`."""
    out, i = [], 0
    for ch in fmt:
        if ch == "#":
            out.append(digits[i])
            i += 1
        else:
            out.append(ch)
    return "".join(out)


def prepare(roi: Image, scale: float, angle: float) -> Image:
    """Green display text on dark glass → dark text on white, enlarged and turned by `angle` degrees."""
    green = roi[:, :, 1].astype(np.float32)
    big = cv2.resize(green, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if angle:
        turn = cv2.getRotationMatrix2D((big.shape[1] / 2, big.shape[0] / 2), angle, 1.0)
        big = cv2.warpAffine(big, turn, (big.shape[1], big.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    span = max(float(big.max() - big.min()), 1e-6)
    norm = (255 - (big - big.min()) * (255 / span)).astype(np.uint8)
    return cv2.copyMakeBorder(norm, 20, 20, 20, 20, cv2.BORDER_REPLICATE)


def ocr(image: Image, allowed: str) -> str:
    if TESSERACT is None:
        return ""
    ok, png = cv2.imencode(".png", image)
    if not ok:
        return ""
    result = subprocess.run(
        [TESSERACT, "stdin", "stdout", "--psm", "7", "-c", f"tessedit_char_whitelist={allowed}"],
        input=png.tobytes(),
        capture_output=True,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},  # one core per read: reads run side by side instead
        timeout=10,
    )
    return " ".join(result.stdout.decode("utf-8", "replace").split())


def vote(reads: list[str]) -> tuple[str, list[float]]:
    """Per position, the most common digit and its share of the votes."""
    winners, shares = [], []
    for position in zip(*reads):
        digit, count = collections.Counter(position).most_common(1)[0]
        winners.append(digit)
        shares.append(count / len(reads))
    return "".join(winners), shares


class Wavemeter(Detector):
    oversample = 3.0

    def __init__(self, inst: Instrument) -> None:
        super().__init__(inst)
        self.power = inst.options.get("field", "main") == "power"
        # (time, unit, readable reads, all reads) per frame read, over the last `vote_s` seconds.
        self.frames: collections.deque[tuple[float, str, list[str], int]] = collections.deque()
        self._lock = threading.Lock()  # frames are read in parallel when reading every check
        self.last: tuple[float, str] | None = None  # (time, text) of the last vote with readable reads

    def reset(self) -> None:
        with self._lock:
            self.frames.clear()

    def _unit(self, texts: list[str]) -> str:
        if self.power:
            return str(self.inst.options.get("unit", "µW"))
        return "GHz" if re.search(r"[GHz]", "".join(texts)) else "nm"

    def update(self, roi: Image) -> Reading:
        if READER is None:
            return Reading("unknown", "no OCR", note="install rapidocr-onnxruntime (or tesseract) to read the wavemeter")
        tilt = self.inst.option("tilt", 0.0)
        if RAPID is not None:
            # roi is 3x the camera's pixels: as it is, 4x and 6x in colour, and the green cleaned up at 4x.
            def bordered(image: Image) -> Image:
                return cv2.copyMakeBorder(image, 16, 16, 16, 16, cv2.BORDER_REPLICATE)
            variants = [bordered(roi), bordered(cv2.resize(roi, None, fx=4 / 3, fy=4 / 3, interpolation=cv2.INTER_CUBIC)),
                        bordered(cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)),
                        cv2.cvtColor(prepare(roi, 4 / 3, tilt), cv2.COLOR_GRAY2BGR)]
            texts = [rapid_read(v) for v in variants]
        else:
            allowed = "0123456789.uWmn" if self.power else "0123456789.nmGHz"
            # roi is already 3x; 4/3 and 8/3 make 4x and 8x of the camera's pixels.
            texts = [ocr(prepare(roi, s, tilt + a), allowed) for s in (4 / 3, 8 / 3) for a in (-1.5, 0.0, 1.5)]
        unit = self._unit(texts)
        fmt = str(self.inst.options.get("format", FORMATS["power" if self.power else unit]))
        reads = [d for d in (digits_for(t, fmt) for t in texts) if d is not None]
        log.debug("%s OCR %s -> %s", self.inst.name, texts, reads)
        raw = " | ".join(texts)
        now = time.time()
        with self._lock:
            self.frames.append((now, unit, reads, len(texts)))
            while self.frames and now - self.frames[0][0] > self.inst.option("vote_s", 10.0):
                self.frames.popleft()
            frames = list(self.frames)
        # Votes from the recent frames read in the same unit as the newest readable one.
        current = next((u for _, u, rs, _ in reversed(frames) if rs), unit)
        fmt = str(self.inst.options.get("format", FORMATS["power" if self.power else current]))
        pool = [r for _, u, rs, _ in frames if u == current for r in rs if len(r) == fmt.count("#")]
        tried = sum(n for _, _, _, n in frames)
        readable = len(pool) / tried if tried else 0.0
        if not pool:
            if self.last is not None:  # the last value read, marked as old: not a reading now, not saved
                at, text = self.last
                return Reading("unknown", f"{text} (read {duration(now - at)} ago)", {"raw": raw, "readable": f"0% of {tried}"},
                               0.0, f"no read in the last {self.inst.option('vote_s', 10.0):g} s had the {fmt} format")
            return Reading("unknown", "unreadable", {"raw": raw}, 0.0, f"no read had the {fmt} format")
        winner, shares = vote(pool)
        agree = self.inst.option("agree", 0.6)
        shown = with_point("".join(d if s >= agree else "?" for d, s in zip(winner, shares)), fmt)
        values: dict[str, float | str | None] = {
            "shown": shown,
            "per_digit": " ".join(f"{s:.0%}" for s in shares),
            "reads": len(pool),
            "readable": f"{readable:.0%} of {tried}",
            "raw": raw,
        }
        if "?" not in shown:
            key = "power" if self.power else ("frequency" if current == "GHz" else "wavelength")
            values[key] = float(shown)
        status = "ok" if "?" not in shown and reads else "unknown"
        self.last = (now, f"{shown} {current}")
        note = ""
        if "?" in shown:
            note = "some digits unsure: the reads disagree"
        elif not reads:
            note = "this frame unreadable; showing the recent vote"
        return Reading(status, f"{shown} {current}", values, round(min(shares) * readable, 2), note)
