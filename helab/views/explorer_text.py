"""Wording shared by the folder explorer (``FolderExplorer``), its Live controller
(``helab/views/explorer_live.py``) and the panels that describe a tab's loads."""
from __future__ import annotations

import re

from helab.utils.number_format import byte_size

# A zero-width space: where Qt may break a line in a word-wrapped label.
BREAK = "\u200b"


def breakable(text: str, longest: int = 24) -> str:
    """``text`` with a break opportunity (a zero-width space) between the characters of each word longer
    than ``longest``: a word-wrapped label then breaks a long folder name across lines instead of widening
    its window (LR-3)."""
    return re.sub(rf"\S{{{longest + 1},}}", lambda match: BREAK.join(match.group()), text)


def middle(name: str, limit: int = 40) -> str:
    """``name`` shortened to ``limit`` characters with "…" in the middle, its start and end kept (a long
    folder name in a one-line phrase, whose counts after it must stay in view: LR-3)."""
    if len(name) <= limit:
        return name
    head = (limit - 1) * 3 // 5
    return f"{name[:head]}…{name[len(name) - (limit - 1 - head):]}"


def plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


def large_text(estimate: int, refused: bool) -> str:
    """How the summary line, Folder details and the status bar name a large folder."""
    if refused:
        return f"Too large to load · ~{byte_size(estimate, 'ram')} in RAM, over 30% of RAM"
    return f"Large folder · ~{byte_size(estimate, 'ram')} in RAM"
