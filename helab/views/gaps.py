"""Gaps HeLab's Fusion style doesn't give by itself (Tony, 2026-11-04: names ran into their values).

Fusion puts no space between a label and the widget beside it, so "Presets2 script presets" and
"TXY:[As the folder's tab]" ran together. Rows add ``LABEL_GAP`` after a name; the Cache tab's rows
use ``COLUMN_GAP`` between a name, its value and its buttons.
"""
from __future__ import annotations

LABEL_GAP = 6  # px after a row's name ("TXY:", "Preset:", "Group:")
COLUMN_GAP = 10  # px between a row's name, its value and its buttons
ROW_SPACING = 2  # px between rows that are not in one grid
# Space either side of a list's cells, so resized-to-contents columns don't run together
# ("built in default", "test_settings0 In use"). Set on the view (``QTreeView`` style sheet).
CELL_PADDING_STYLE = "QTreeView::item { padding: 0px 4px; }"
