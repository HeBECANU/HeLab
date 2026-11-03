"""The manual site's versions (Q56.3): the mike commands that publish one release's manual, run by
``.github/workflows/docs-site.yml`` when a release is published.

- Every release is a version of its own (``0.0.8``, ``0.0.8a1``), listed in the version menu.
- ``latest``: the newest stable (final) release. It is the site's front page.
- ``pre-release``: the newest alpha, beta or release candidate (PEP 440's pre-releases), while it is newer than
  every stable release: a stable release newer than its target removes the alias (``mike delete`` of the alias
  only, Q~3 (b), Tony 2026-11-03), and the next pre-release brings it back. Removed rather than pointed at
  ``latest``, which would label the stable release a pre-release too.
- Until there is a stable release, the front page is a short "No stable release yet" page
  (``no-stable.html``, mike's ``set-default`` template) linking to the newest pre-release.
- No development channel: a development manual is built locally (the README's User manual section).

An older release published after a newer one gets its version, but moves no alias back.

    python docs/publish/site_versions.py VERSION            # deploy VERSION and push (in CI)
    python docs/publish/site_versions.py VERSION --dry-run  # print the mike commands only

Reads what is deployed with ``mike list --json``. Standard library and ``packaging`` only (it comes with
the docs tools); it isn't one of the manual's pages (``mkdocs.yml`` excludes ``publish/``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, List, Sequence

from packaging.version import InvalidVersion, Version

STABLE_ALIAS = "latest"
PRE_RELEASE_ALIAS = "pre-release"
NO_STABLE_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-stable.html")


def _versions(deployed: Sequence[dict[str, Any]], other_than: Version) -> List[Version]:
    found = []
    for entry in deployed:
        try:
            version = Version(str(entry.get("version", "")))
        except InvalidVersion:
            continue  # (Not one of these releases' versions: left alone.)
        if version != other_than:
            found.append(version)
    return found


def _alias_target(deployed: Sequence[dict[str, Any]], alias: str) -> Version | None:
    """The version ``alias`` names in ``deployed`` (None: no such alias, or not a version)."""
    for entry in deployed:
        if alias in (entry.get("aliases") or []):
            try:
                return Version(str(entry.get("version", "")))
            except InvalidVersion:
                return None
    return None


def plan(version: str, deployed: Sequence[dict[str, Any]]) -> List[List[str]]:
    """The mike commands that publish ``version`` (a PEP 440 version, no ``v``) beside ``deployed`` (``mike
    list --json``): its deploy, with ``latest`` or ``pre-release`` when it is the newest of its kind (a
    pre-release also newer than every stable release); for a stable release newer than ``pre-release``'s
    target, that alias's removal; then the front page: ``latest`` once a stable release exists, else the "No
    stable release yet" page."""
    new = Version(version)
    others = _versions(deployed, new)
    stable = [other for other in others if not other.is_prerelease]
    if new.is_prerelease:
        newest = all(new > other for other in others)  # (Newer than every pre-release and stable release.)
        aliases = [PRE_RELEASE_ALIAS] if newest else []
    else:
        aliases = [STABLE_ALIAS] if all(new > other for other in stable) else []
    commands = [["mike", "deploy", "--push", "--update-aliases", version, *aliases]]
    target = _alias_target(deployed, PRE_RELEASE_ALIAS)
    if not new.is_prerelease and target is not None and new > target:
        commands.append(["mike", "delete", "--push", PRE_RELEASE_ALIAS])
    if stable or not new.is_prerelease:
        commands.append(["mike", "set-default", "--push", STABLE_ALIAS])
    else:
        commands.append(["mike", "set-default", "--push", "--template", NO_STABLE_TEMPLATE, PRE_RELEASE_ALIAS])
    return commands


def main(argv: List[str]) -> int:
    if not argv or len(argv) > 2 or len(argv) == 2 and argv[1] != "--dry-run":
        sys.stderr.write("usage: python docs/publish/site_versions.py VERSION [--dry-run]\n")
        return 2
    listed = subprocess.run(["mike", "list", "--json"], capture_output=True, text=True)
    if listed.returncode != 0:
        # (Without a gh-pages branch mike lists [] and succeeds: a failure is a real one, and planning as if
        # nothing were deployed could show "No stable release yet" over a stable release.)
        sys.stderr.write(f"mike list failed ({listed.returncode}): {listed.stderr.strip()}\n")
        return 1
    deployed = json.loads(listed.stdout) if listed.stdout.strip() else []
    for command in plan(argv[0], deployed):
        print(" ".join(command), flush=True)
        if len(argv) == 1:
            subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
