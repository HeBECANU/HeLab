"""Settings › General's update rows, one line each: "Check for updates at start (once a day)", and "Updates
from:" with the repo, the mode (Q65.3: the branch HeLab runs from, or releases) and "Include pre-releases".

A compiled build shows releases only (the mode disabled, its tooltip says why); a checkout off a branch can't
pick the branch mode. Saved only with Settings' Save, like the other rows.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QWidget

from helab.build_info import BuildInfo
from helab.updates import settings as update_settings
from helab.updates.github import REPOSITORIES
from helab.updates.versions import BRANCH, RELEASES
from helab.utils.accessible import identify
from helab.views.gaps import LABEL_GAP


class UpdateSettingsRows:
    def __init__(self, build: BuildInfo, form: QFormLayout, parent: QWidget | None = None) -> None:
        self.build = build
        source, branch = update_settings.is_source(build), update_settings.on_branch(build)
        self.check_at_start = identify(
            QCheckBox("Check for updates at start (once a day)", parent), "updates_check_at_start", "",
            "Ask GitHub for a newer HeLab when it starts, at most once a day")
        self.check_at_start.setToolTip(
            "At most once a day, 30 s after HeLab starts, ask GitHub whether a newer HeLab is available; a newer "
            "one shows in the status bar and the Help menu. Nothing is downloaded or changed. Off, only Help › "
            "Check for Updates… asks.")
        self.repository = identify(QComboBox(parent), "updates_repository", "Updates repository")
        self.repository.addItem(f"Default ({update_settings.default_repository(build)})", "")
        for name in REPOSITORIES:
            self.repository.addItem(name, name)
        self.repository.setToolTip("The GitHub repository whose releases (or branch) HeLab updates from")
        self.mode = identify(QComboBox(parent), "updates_mode", "Update from")
        if source and branch:
            self.mode.addItem(f"The branch HeLab runs from ({build.branch})", BRANCH)
        self.mode.addItem("Releases", RELEASES)
        if not source:
            self.mode.setEnabled(False)
            self.mode.setToolTip("A compiled HeLab only checks releases; download them from the release page")
        elif not branch:
            self.mode.setToolTip("This checkout isn't on a branch (it is on a release tag): it updates tag to tag")
        else:
            self.mode.setToolTip(
                "The branch: fast-forward only, to the newest commit whose CI passed on macOS, Windows and Ubuntu. "
                "Releases: from release tag to release tag (the checkout leaves the branch).")
        self.prereleases = identify(QCheckBox("Include pre-releases", parent), "updates_prereleases", "",
                                    "Offer alpha, beta and release-candidate versions too")
        row = QHBoxLayout()
        row.setSpacing(LABEL_GAP)
        row.addWidget(self.repository)
        row.addWidget(self.mode)
        row.addWidget(self.prereleases)
        row.addStretch(1)
        form.addRow(self.check_at_start)
        form.addRow("Updates from:", row)

    def load(self, settings: QSettings) -> None:
        chosen = update_settings.read(settings, self.build)
        self.check_at_start.setChecked(chosen.check_at_start)
        self.repository.setCurrentIndex(max(0, self.repository.findData(chosen.chosen_repository)))
        self.mode.setCurrentIndex(max(0, self.mode.findData(chosen.mode)))
        self.prereleases.setChecked(chosen.prereleases)

    def save(self, settings: QSettings) -> None:
        mode = str(self.mode.currentData() or "")
        # The default mode is saved as "" so it keeps following what the checkout is on.
        saved = "" if mode == update_settings.default_mode(self.build) else mode
        update_settings.write(settings, check_at_start=self.check_at_start.isChecked(),
                              repository=str(self.repository.currentData() or ""),
                              mode=saved if self.mode.isEnabled() else "", prereleases=self.prereleases.isChecked())
