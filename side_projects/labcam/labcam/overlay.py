"""Draws each instrument's region, reading and marks on the frame."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .config import Corners
from .detectors import Image, Reading

# BGR
COLOURS = {"ok": (80, 200, 80), "off": (40, 160, 255), "unknown": (170, 170, 170)}
MARK = (255, 0, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass
class Item:
    label: str
    kind: str
    corners: Corners  # in the frame
    reading: Reading
    marks: list[tuple[Any, ...]]  # in the frame
    label_dx: int = 0  # moves the label sideways (px), off something it would hide


def _p(point: tuple[float, float]) -> tuple[int, int]:
    return int(round(point[0])), int(round(point[1]))


def _poly(points: Corners) -> Any:
    return np.array([_p(p) for p in points], np.int32)


@dataclass
class Style:
    font: float = 0.45  # text scale
    line: int = 1  # boxes' line width, px (marks one more)


def _label(image: Image, text: str, x: int, y: int, colour: tuple[int, int, int],
           taken: list[tuple[int, int, int, int]] | None = None, style: Style = Style()) -> None:
    """A label with its baseline at y; moved down past labels already in `taken`."""
    weight = max(1, round(style.font * 2.2))
    (w, h), base = cv2.getTextSize(text, FONT, style.font, weight)
    x = min(max(0, x), image.shape[1] - w - 6)
    y = min(max(h + 4, y), image.shape[0] - 2)
    if taken is not None:
        while any(x < tx + tw and tx < x + w + 6 and y - h - 4 < ty + th and ty < y + base for tx, ty, tw, th in taken):
            y += h + 6
        taken.append((x, y - h - 4, w + 6, h + base + 4))
    cv2.rectangle(image, (x, y - h - 4), (x + w + 6, y + base - 2), (0, 0, 0), -1)
    cv2.putText(image, text, (x + 3, y - 3), FONT, style.font, colour, weight, cv2.LINE_AA)


def _dashed(image: Image, a: tuple[float, float], b: tuple[float, float], colour: tuple[int, int, int],
            width: int = 1) -> None:
    length = max(1.0, float(np.hypot(b[0] - a[0], b[1] - a[1])))
    for start in np.arange(0, length, 6):
        t0, t1 = start / length, min(1.0, (start + 3) / length)
        p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        cv2.line(image, _p(p0), _p(p1), colour, width)


OPACITY = 0.75


def draw(frame: Image, items: list[Item], header: str, style: Style = Style()) -> Image:
    """Everything drawn at OPACITY over the frame, so what's under a label or a box still shows a little."""
    out = frame.copy()
    taken: list[tuple[int, int, int, int]] = []
    for item in items:
        colour = COLOURS.get(item.reading.status, COLOURS["unknown"])
        if item.kind != "motion":
            cv2.polylines(out, [_poly(item.corners)], True, colour, style.line, cv2.LINE_AA)
        for mark in item.marks:
            shape = mark[0]
            if shape in ("line", "loop"):
                cv2.polylines(out, [_poly(mark[1])], shape == "loop", MARK if shape == "line" else colour, style.line + 1, cv2.LINE_AA)
            elif shape == "dash":
                _dashed(out, mark[1][0], mark[1][1], colour, style.line)
            elif shape == "circle":
                cv2.circle(out, _p(mark[1]), int(mark[2]), MARK, style.line + 1, cv2.LINE_AA)
            elif shape == "point":
                cv2.circle(out, _p(mark[1]), 1, (255, 255, 0), -1)
        text = f"{item.label}: {item.reading.text}"
        if item.kind == "motion":
            _label(out, text, 8, out.shape[0] - 10, colour, style=style)
        else:
            xs = [p[0] for p in item.corners]
            ys = [p[1] for p in item.corners]
            top = min(ys)
            below = int(max(ys) + 12 + 10 * style.font / 0.45)
            _label(out, text, int(min(xs)) + item.label_dx, below if top < 30 else int(top - 4), colour, taken, style)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _label(out, f"{header}  {stamp}" if header else stamp, out.shape[1] - int(330 * style.font / 0.45), out.shape[0] - 10,
           (255, 255, 255), style=style)
    return cv2.addWeighted(out, OPACITY, frame, 1 - OPACITY, 0)
