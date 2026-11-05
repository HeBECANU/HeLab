"""The manual's Basic Plots page: a placeholder in angle brackets outside code (``<folder>``) is passed through
as an HTML element, which the browser drops ("Data source:  · rev N"), and ``mkdocs build --strict`` doesn't
catch it; placeholders go in backticks."""
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "docs" / "how-to" / "basic-plots.md"


def test_no_bare_angle_bracket_placeholder() -> None:
    text = re.sub(r"```.*?```", "", PAGE.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    assert not re.findall(r"<[A-Za-z][^>\n]*>", text)
