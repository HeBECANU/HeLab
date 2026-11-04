"""The command line's help is public text: ``helab convert --help`` and ``helab cache --help`` (and its
subcommands') name no person and carry no internal item IDs, whatever the modules' docstrings say."""
from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from helab import cache_cli, convert_cli

# A dated attribution, "(Name, 2026-10-31)" or "Name, 2026-10-31:"; a planning item's ID (Q38.1, A44.2, S3~6).
ATTRIBUTION = re.compile(r"\b[A-Z][a-z]+,? \d{4}-\d{2}-\d{2}")
ITEM_ID = re.compile(r"\b[QAMS]\d+(?:\.\d+|~\d+)\b")


def _help(run: Callable[[list[str]], object], argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exit_info:
        run(argv)
    assert exit_info.value.code == 0
    text = capsys.readouterr().out
    assert text.strip()
    return text


@pytest.mark.parametrize("argv", [["--help"], ["dump", "--help"], ["export", "--help"]])
def test_cache_help_names_no_one(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    text = _help(cache_cli.main, argv, capsys)
    assert not ATTRIBUTION.search(text) and not ITEM_ID.search(text), text
    if argv == ["--help"]:
        assert cache_cli.DESCRIPTION.split()[0] in text


def test_convert_help_names_no_one(capsys: pytest.CaptureFixture[str]) -> None:
    text = _help(convert_cli._arguments, ["--help"], capsys)
    assert not ATTRIBUTION.search(text) and not ITEM_ID.search(text), text


def test_the_checks_catch_what_they_look_for() -> None:
    assert ATTRIBUTION.search("read only (Someone, 2026-10-31).")
    assert ITEM_ID.search("refused (Q38.1)") and ITEM_ID.search("S3~6") and not ITEM_ID.search("m19v1")
