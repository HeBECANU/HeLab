"""The manual site's versions (Q56.3): the mike commands that publish one release's manual, run by
``.github/workflows/docs-site.yml`` when a release is published.

- Every release is a version of its own (``0.0.8``, ``0.0.8a1``), listed in the version menu.
- ``latest``: the newest stable (final) release. It is the site's front page.
- ``pre-release``: the newest alpha, beta or release candidate (PEP 440's pre-releases), while it is newer than
  every stable release: a stable release newer than its target removes the alias (``mike delete`` of the alias
  only, Q58.3 (b), Tony 2026-11-03), and the next pre-release brings it back. Removed rather than pointed at
  ``latest``, which would label the stable release a pre-release too.
- Until there is a stable release, the front page is a short page (``no-stable.html``, mike's ``set-default``
  template) naming the newest pre-release as the latest download, "Latest: 0.0.8a1 (alpha)", linked to its
  manual (``pre-release``). A pre-release published as a full GitHub release (v0.0.8a1, A59.2 (b)) is still a
  pre-release here: the site goes by the version number.
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
import tempfile
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


KINDS = {"a": "alpha", "b": "beta", "rc": "release candidate"}


def newest_pre_release(version: str, deployed: Sequence[dict[str, Any]]) -> Version | None:
    """The newest pre-release once ``version`` is deployed beside ``deployed``, while there is no stable
    release (None once there is one: the front page is then ``latest``)."""
    new = Version(version)
    every = [*_versions(deployed, new), new]
    return None if any(not item.is_prerelease for item in every) else max(every)


def latest_label(version: Version) -> str:
    """How the front page names a pre-release: ``0.0.8a1 (alpha)``, ``0.0.9rc1 (release candidate)``."""
    kind = KINDS.get(version.pre[0], "pre-release") if version.pre else "development version"
    return f"{version} ({kind})"


def no_stable_page(newest: Version, template: str = NO_STABLE_TEMPLATE) -> str:
    """The front page's template with the newest pre-release filled in; mike then fills in ``{{href}}``."""
    with open(template, encoding="utf-8") as stream:
        return stream.read().replace("{{latest}}", latest_label(newest))


def plan(version: str, deployed: Sequence[dict[str, Any]], page: str = NO_STABLE_TEMPLATE) -> List[List[str]]:
    """The mike commands that publish ``version`` (a PEP 440 version, no ``v``) beside ``deployed`` (``mike
    list --json``): its deploy, with ``latest`` or ``pre-release`` when it is the newest of its kind (a
    pre-release also newer than every stable release); for a stable release newer than ``pre-release``'s
    target, that alias's removal; then the front page: ``latest`` once a stable release exists, else ``page``
    (``no_stable_page``'s, written by ``main``) linking to ``pre-release``."""
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
        commands.append(["mike", "set-default", "--push", "--template", page, PRE_RELEASE_ALIAS])
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
    with tempfile.TemporaryDirectory() as folder:
        page = os.path.join(folder, "no-stable.html")
        newest = newest_pre_release(argv[0], deployed)
        if newest is not None:
            with open(page, "w", encoding="utf-8") as stream:
                stream.write(no_stable_page(newest))
            print(f"Front page: Latest: {latest_label(newest)}", flush=True)
        for command in plan(argv[0], deployed, page):
            print(" ".join(command), flush=True)
            if len(argv) == 1:
                subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
