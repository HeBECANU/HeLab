"""Check a built manual loads no script from elsewhere: every ``<script src>`` of every page is a file of the
site, so the copy bundled in HeLab (``HELAB_DOCS_OFFLINE=true``) works, search included, from ``file://``
without a network. Run by the Docs job (``.github/workflows/dev-cicd.yml``) on the offline build.

    python docs/publish/check_offline.py SITE_DIR      # exit 1, naming each page and script, if any is external

Stylesheets and fonts from elsewhere (Google Fonts) aren't counted: without a network the pages fall back to
the system's fonts and still work. Standard library only.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

# A source that leaves the site: a scheme (http:, https:; data: is kept, below) or a protocol-relative //host.
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag == "script":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source.strip())


def external_scripts(site: Path) -> List[Tuple[str, str]]:
    """Each (page, script source) in ``site`` that isn't a file of the site."""
    found = []
    for page in sorted(site.rglob("*.html")):
        parser = _Scripts()
        parser.feed(page.read_text(encoding="utf-8", errors="replace"))
        found += [(page.relative_to(site).as_posix(), source) for source in parser.sources
                  if EXTERNAL.match(source) and not source.lower().startswith("data:")]
    return found


def main(argv: List[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        sys.stderr.write("usage: python docs/publish/check_offline.py SITE_DIR\n")
        return 2
    site = Path(argv[0])
    pages = list(site.rglob("*.html"))
    found = external_scripts(site)
    for page, source in found:
        print(f"{page}: loads {source}")
    if found:
        print(f"{len(found)} external script{'' if len(found) == 1 else 's'} in {site}: the bundled manual "
              "would need a network", file=sys.stderr)
        return 1
    print(f"{len(pages)} pages, every script a file of the site")
    return 0 if pages else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
