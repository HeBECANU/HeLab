"""Results being delivered on the GUI thread, and running code outside them.

IOService's timer (``IOService._tick``) hands every helper's events to their slots, and AnalysisRunner hands
each job's end to its receivers. Both run inside ``delivering(...)``. A modal box or menu (``exec()``) opened
there runs a nested event loop *inside* the delivery: Qt never fires a timer again while its slot runs, so
every helper's events, slots and timeouts would stop until the box is answered (GT-1).

Code reached from a delivery that may open one goes through ``outside(fn)``: ``fn`` runs now when nothing is
being delivered (a click, or a test calling a slot directly), else from the event loop as soon as the delivery
has returned. ``tests/conftest.py`` fails any ``exec()`` of a dialog, box or menu made while ``current()`` is set.
"""
from __future__ import annotations

import contextlib
from typing import Callable, Iterator

from PyQt6.QtCore import QTimer

# (GUI thread only.) What is being delivered now, innermost last: "io" or "analysis".
_delivering: list[str] = []


@contextlib.contextmanager
def delivering(source: str) -> Iterator[None]:
    """Mark the code inside as delivering ``source``'s results."""
    _delivering.append(source)
    try:
        yield
    finally:
        _delivering.pop()


def current() -> str | None:
    """What is being delivered now, or None."""
    return _delivering[-1] if _delivering else None


def outside(fn: Callable[[], object]) -> None:
    """Run ``fn`` now unless a result is being delivered; then, once that delivery has returned.

    ``fn`` checks for itself that what it needs still exists (a closed window, a cancelled request)."""
    if _delivering:
        QTimer.singleShot(0, fn)
    else:
        fn()


__all__ = ["current", "delivering", "outside"]
