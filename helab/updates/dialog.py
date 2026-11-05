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
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

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


class UpdateWindow(QDialog):
    """``update`` is called by Update and restart (a source checkout; None: not offered)."""

    def __init__(self, check: UpdateCheck, parent: QWidget | None = None, *,
                 update: Callable[[Offer], None] | None = None) -> None:
        super().__init__(parent)
        self.check = check
        self.update_action = update
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
        self.update_button.setEnabled(self.update_action is not None and not check.running)
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
        if offer is not None and self.update_action is not None:
            self.update_action(offer)

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
