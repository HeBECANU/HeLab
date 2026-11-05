# Text-length audit (LR-3's app half, 2026-11-05, Mendy on Ground)

Tony (live run, LR-3): "automatic audits that every text's length is reasonable at various sizes". CoCo's
brief: extend Side's UI audit (`.ai/sessions/2026-11-04-claude-ui-audit/`) to the whole app at several window
sizes and panel widths, with long folder names and long values where text comes from data. Plot settings
(Input, the TXY note, the status lines and their tooltips) and the Scripts panel are the Basic plots v2
floor's, so they are left out here.

## The script

`text_audit.py` keeps Side's four checks (squeezed, label cut, touching, outside window) and adds:

- **elided:** an `ElidedLabel`/`ElidedButton` showing less than its text, and whether its tooltip has the rest;
- **button / check / combo text cut:** a button, check box, radio button or combo narrower than its text;
- **cells cut:** item-view cells narrower than their text, and how many have no tooltip with the whole text;
- **tooltip wide / tall:** a plain-text tooltip line wider than 800 px (Qt doesn't wrap plain text until it
  is wider than the screen), or one over 30 lines;
- **wraps tall:** a word-wrapped label whose text takes more than 4 lines at its width;
- **window larger than asked / opens large / window minimum width / panel width not taken:** a window
  that contents hold larger than the size asked for, opens over 1400×900, or a main-window splitter that
  can't give the left panel the width asked for.

Cases (long data: a folder three levels deep under 72-, 85- and 85-character names, `LONG_PARTS`):

- Settings, every tab, at 880×620, 800×500 and 700×450;
- the main window empty, then with the long-named folder loaded, at 1440×860, 1100×700 and 900×600 with the
  left panel asked for 250, 420 and 700 px; then with a Live session set by hand (no checks run) for the
  status bar's Live phrase;
- every dialog in `tests/test_accessible_names.py`'s `DIALOGS`, given the long path, as opened and at 640×420;
- the message boxes of its `ASKS`.

Run it as Side's (a real display: offscreen the font and tab titles differ, and it found 600 items there
against 440 on screen):

```bash
cp .ai/sessions/2026-11-05-claude-text-length-audit/text_audit.py tests/test_zz_text_audit_tmp.py
HELAB_SHOW_GUI=1 pytest -q -p no:randomly tests/test_zz_text_audit_tmp.py   # about 8 min on screen
rm tests/test_zz_text_audit_tmp.py
```

It writes `.ai/temp/text-audit/findings.{json,txt}` and a screenshot per case. Look at the screenshots too.

## Findings

See `findings.md` (sent to CoCo and Side before any fix).
