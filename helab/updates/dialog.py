"""The update window (Help › Check for Updates…, the status-bar mark, Help's "is available" entry): the status,
what was found (a release's notes, or a branch's newer commits with their CI), links, and per run Download
(a compiled build) or Update and restart (a source checkout, ``helab.updates.launch``), Skip this version.

Modeless and one per main window; it reads the check's memory only and never waits.
"""
from __future__ import annotations

from collections.abc import Callable
import html
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from typing import Any

from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from helab.updates import settings as update_settings
from helab.updates.check import UpdateCheck
from helab.updates.versions import BranchFacts, Offer
from helab.utils.accessible import identify


def offer_html(offer: Offer, branch: BranchFacts | None) -> str:
    """What was found, as HTML for the browser: a release's notes (Markdown shown as text), or the branch's
    newer commits, newest first, each with its CI where it was looked at."""
    if offer.release is not None:
        release = offer.release
        head = f"<p><b>HeLab {html.escape(release.version)}</b>"
        if release.published_at:
            head += f", published {html.escape(release.published_at[:10])}"
        if release.html_url:
            head += f" · <a href='{html.escape(release.html_url)}'>release page</a>"
        return head + "</p><pre style='white-space: pre-wrap'>" + html.escape(release.notes or "(no notes)") + "</pre>"
    target = offer.commit.short if offer.commit is not None else ""
    text = (f"<p><b>{html.escape(offer.label)}</b>: moves to {html.escape(target)}, the newest commit whose CI "
            "passed on macOS, Windows and Ubuntu.</p>")
    if branch is None:
        return text
    items = []
    for commit in branch.candidates:
        ci = branch.ci_of(commit.sha)
        items.append(f"<li>{html.escape(commit.short)} {html.escape(commit.subject)} ({html.escape(commit.date[:10])})"
                     + (f" · CI {html.escape(ci)}" if ci else "") + "</li>")
    return text + "<ul>" + "".join(items) + "</ul>"


# Update and restart's call: (the offer, stash local changes first, confirmed after the dry run).
UpdateCall = Callable[[Offer, bool, bool], None]


class UpdateWindow(QDialog):
    """``update`` is called by Update and restart (a source checkout; None: not offered): first unconfirmed, for
    the updater's dry run, whose result ``show_plan`` shows; then, if nothing refused, confirmed ("Quit and
    update")."""

    def __init__(self, check: UpdateCheck, parent: QWidget | None = None, *, update: UpdateCall | None = None) -> None:
        super().__init__(parent)
        self.check = check
        self.update_action = update
        self.planned: dict[str, Any] | None = None  # The dry run's result for ``planned_for``
        self.planned_for = ""
        self.planning = False
        self.setWindowTitle("HeLab updates")
        self.setModal(False)
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        self.status_label = identify(QLabel(), "update_status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.details = identify(QTextBrowser(), "update_details", "What's new")
        self.details.setOpenExternalLinks(True)
        layout.addWidget(self.details, 1)
        self.plan_label = identify(QLabel(), "update_plan")
        self.plan_label.setWordWrap(True)
        self.plan_label.hide()
        layout.addWidget(self.plan_label)
        self.stash_box = identify(QCheckBox("Stash my changes first (git stash; never deleted)"), "update_stash", "",
                                  "Put this checkout's changes in a git stash before updating")
        self.stash_box.hide()
        self.stash_box.toggled.connect(self._stash_toggled)
        layout.addWidget(self.stash_box)
        buttons = QHBoxLayout()
        self.check_button = identify(QPushButton("Check again"), "update_check_again",
                                     description="Ask GitHub again now")
        self.download_button = identify(QPushButton("Download…"), "update_download",
                                        description="Open this OS's download in your web browser")
        self.update_button = identify(QPushButton("Update and restart…"), "update_and_restart",
                                      description="Update this checkout, then quit HeLab and start it again")
        self.skip_button = identify(QPushButton("Skip this version"), "update_skip",
                                    description="Don't remind me of this version at start")
        self.close_button = identify(QPushButton("Close"), "update_close")
        for button in (self.check_button, self.download_button, self.update_button, self.skip_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.check_button.clicked.connect(self._check_again)
        self.download_button.clicked.connect(self._download)
        self.update_button.clicked.connect(self._update)
        self.skip_button.clicked.connect(self._skip)
        self.close_button.clicked.connect(self.close)
        check.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        check = self.check
        found = check.status
        chosen = check.settings()
        source = update_settings.is_source(check.build)
        lines = [f"<b>{html.escape(found.text)}</b> · updates from "
                 f"{html.escape(update_settings.mode_words(check.build, chosen))}"]
        if check.running:
            lines.append("Checking GitHub…")
        elif check.error:
            lines.append(html.escape(check.error))
        elif check.last_check() is None:
            lines.append("Not checked yet.")
        else:
            lines.append(f"Last checked {html.escape(check.last_check_words())}.")
        offer = found.offer
        if offer is None and not check.running and not check.error and check.facts is not None:
            lines.append(html.escape(" ".join(found.notes) or "HeLab is up to date."))
        self.status_label.setText("<br>".join(lines))
        if offer is not None:
            self.details.setHtml(offer_html(offer, check.facts.branch if check.facts is not None else None))
        else:
            self.details.setHtml("")
        self.check_button.setEnabled(not check.running)
        release = offer.release if offer is not None else None
        self.download_button.setVisible(not source and offer is not None)
        self.download_button.setEnabled(release is not None)
        self.update_button.setVisible(source and offer is not None)
        if offer is None or offer.key != self.planned_for:
            self._forget_plan()
        ready = self.planned is not None and bool(self.planned.get("ok"))
        self.update_button.setText("Quit and update" if ready else "Update and restart…")
        self.update_button.setEnabled(self.update_action is not None and not check.running and not self.planning
                                      and (self.planned is None or ready))
        self.skip_button.setVisible(offer is not None)
        self.skip_button.setText("Don't skip" if found.skipped else "Skip this version")

    def _check_again(self) -> None:
        self.check.start(manual=True)

    def _download(self) -> None:
        offer = self.check.status.offer
        if offer is None or offer.release is None:
            return
        url = offer.release.asset_for(sys.platform) or offer.release.html_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _update(self) -> None:
        offer = self.check.status.offer
        if offer is None or self.update_action is None:
            return
        confirmed = self.planned is not None and bool(self.planned.get("ok")) and self.planned_for == offer.key
        if not confirmed:
            self.planning, self.planned_for = True, offer.key
            self.show_plan("Checking this checkout and fetching the update…")
            self.refresh()
        self.update_action(offer, self.stash_box.isChecked(), confirmed)

    def _stash_toggled(self) -> None:
        """A new choice needs a new dry run."""
        self._forget_plan(keep_stash=True)
        self.refresh()

    def _forget_plan(self, keep_stash: bool = False) -> None:
        if self.planned is None and not self.planning:
            return
        self.planned, self.planning = None, False
        self.show_plan("")
        if not keep_stash:
            self.stash_box.setChecked(False)
            self.stash_box.hide()

    def plan_ready(self, result: dict[str, Any], note: str = "") -> None:
        """The dry run's result: what will happen (and ``note``: what quitting does), or why it can't."""
        self.planning = False
        self.planned = result
        refusals = [str(r) for r in result.get("refusals") or []]
        steps = [str(s) for s in result.get("steps") or []]
        if refusals:
            text = "Can't update: " + " ".join(refusals)
            self.stash_box.setVisible(bool(result.get("stashable")) or self.stash_box.isChecked())
        else:
            text = "Update and restart will: " + "; ".join([*steps, "quit HeLab and start it again"]) + "."
            if note:
                text += " " + note
        self.show_plan(text)
        self.refresh()

    def _skip(self) -> None:
        found = self.check.status
        if found.offer is None:
            return
        if found.skipped:
            self.check.unskip()
        else:
            self.check.skip(found.offer.key)

    def show_plan(self, text: str) -> None:
        """The updater's dry run: what will happen, or why it can't (``helab.updates.launch``)."""
        self.plan_label.setText(text)
        self.plan_label.setVisible(bool(text))
