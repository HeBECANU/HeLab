# Run sheet: the switch-on build (Q50.18)

This is the check Tony runs before store-v4 is switched on in the v0.0.8 PR: M44.1 and M47.1 on the Mac, then
M47.2 (with Q51.1's extra listing) and M42.1 on a lab PC. It takes about 15 minutes.

- **Build:** `agent/v4-switch-on` at `23134c0` (dev/v0.0.8 `162342d` merged in). On this branch store-v4 is on by
  default, so nothing needs switching on.
- **Folders:** every command below runs HeLab with its own app folder, cache folder, temp folder and settings
  file, all under one `HeLab-check` folder. Your real cache, settings and app folder aren't opened. Deleting
  `HeLab-check` afterwards removes the whole test.

## (a) Mac

### Set up (once)

```bash
mkdir -p ~/HeLab-check/data && cd ~/HeLab-check
git clone --depth 1 --branch agent/v4-switch-on https://github.com/TonyXTYan/HeLab.git src
cd src && uv venv --seed --python 3.13 venv && source venv/bin/activate && uv pip install -r requirements.lock -e .
```

Copy a few shots into `~/HeLab-check/data/run1`: raw `d*.txt` with their `d_txy_forc*.txt`, from any run folder or
`~/HeLab-samples/txy-v1`. Delete two of the copied `d_txy_forc*.txt`, so those two shots are raw only.

### Every terminal that runs HeLab

```bash
cd ~/HeLab-check/src && source venv/bin/activate
export HELAB_APP_DIR_OVERRIDE=~/HeLab-check/app HELAB_DIR_CACHES_OVERRIDE=~/HeLab-check/caches
export HELAB_DIR_TEMPS_OVERRIDE=~/HeLab-check/temps HELAB_TEST_SETTINGS_FILE=~/HeLab-check/settings.ini
echo "$HELAB_DIR_CACHES_OVERRIDE"   # must print ~/HeLab-check/caches (expanded) before you start helab
```

This HeLab has its own running lock, so it can run beside your usual one.

### M44.1: caching v2's dialogs

1. Make an older cache to be asked about. Run `printf '[General]\nstore_v4=false\n' > ~/HeLab-check/settings.ini`,
   then `helab`. This writes store-v3 in the test cache, as 0.0.7 would.
2. In that run, right-click `run1` › Place .helab-root here…, load the folder, then quit.
3. Turn the switch back on with `sed -i '' '/^store_v4=/d' ~/HeLab-check/settings.ini`, then `helab`.
4. "An older disk cache" appears once, with its size. Choose Keep using it.
5. Quit and start again: it isn't asked a second time.
6. Settings › Cache: check the "HeLab's cached raw pulses" row and the "Older cache (store-v3)" row and their buttons.
   Open each Clear… and cancel it.
7. Make an only copy: delete one `d*.txt` from `run1` and reselect the folder. Its cached raw pulses are now the
   only copy.
8. Make room's text: in Settings › Cache, set the disk budget just below what's used and save. "Lower the disk
   cache budget?" uses Make room's text, and names the raw pulses and the only copy it would remove. Cancel it.
9. Make room on a load: run `cp -R ~/HeLab-check/data/run1 ~/HeLab-check/data/run2`. Lower the budget to a little
   under what's used and accept (temp data only). Then load `run2`: Make room asks, naming what it would remove.
10. Amber line: append a line to another raw file (`echo >> ~/HeLab-check/data/run1/d3.txt`), wait 5 s and
    reselect the folder. Folder details' Problems line is amber, for a raw file changed since it was cached.

### M47.1: stage 2's controls

1. Settings › Cache's TXY data row: shots, folders, size, tags and only copies, and its Clear…, cancelled.
2. The Cache policy combo: Raw + what you load, Raw only, TXY only.
3. Clear all… and the purge: both name TXY data and HeLab's cached raw pulses. Cancel both.
4. The purge rows per kind, and "Everything not used, checked or shown in the last N days": Remove… asks, naming
   each part with its size. Cancel it.
5. Lowering the budget below usage: the question comes from its plan (M44.1 step 8).
6. Make room names TXY layers by group (M44.1 step 9).
7. Right-click `run1` › "TXY for this folder…" and "Cache policy for this folder…" are there.
8. Both are disabled on a folder without a data root, for example `~/HeLab-check/data`.
9. Folder details' TXY line names the folder's choices.
10. "Cache policy for this folder…" › TXY only asks, with the size, to remove HeLab's cached raw pulses, saying
    "Your d files aren't touched". Answer No: nothing is removed.
11. The two shots without a TXY: the row tooltip and Folder details say "2 converted when loaded".
12. A plot on one of those two shots: its TXY line says "converted from raw".

## (b) Lab PC (Windows)

### Set up (once, PowerShell)

```powershell
mkdir $env:LOCALAPPDATA\HeLab-check; cd $env:LOCALAPPDATA\HeLab-check
git clone --depth 1 --branch agent/v4-switch-on https://github.com/TonyXTYan/HeLab.git src
cd src; uv venv --seed --python 3.13 venv; venv\Scripts\activate; uv pip install -r requirements.lock -e .
```

### Every PowerShell window that runs HeLab

```powershell
cd $env:LOCALAPPDATA\HeLab-check\src; venv\Scripts\activate
$env:HELAB_APP_DIR_OVERRIDE = "$env:LOCALAPPDATA\HeLab-check\app"
$env:HELAB_DIR_CACHES_OVERRIDE = "$env:LOCALAPPDATA\HeLab-check\caches"
$env:HELAB_DIR_TEMPS_OVERRIDE = "$env:LOCALAPPDATA\HeLab-check\temps"
$env:HELAB_TEST_SETTINGS_FILE = "$env:LOCALAPPDATA\HeLab-check\settings.ini"
```

**Folders used.** Run this way, it doesn't use the PC's real HeLab folders:
- the app folder, cache, temp and settings are all under `%LOCALAPPDATA%\HeLab-check`;
- the lab's usual HeLab, its store-v3 and its registry settings stay as they are;
- what it reads from the share is the data and its existing `.helab-root` markers, read only.

The settings start fresh, at HeLab's defaults. Set again anything the timing depends on, such as the converter
profile. For fair timings, quit the lab's usual HeLab first.

**Run without these four lines, and it uses the real folders:**
- `%LOCALAPPDATA%\HeLab` and the PC's real settings and cache folder;
- it must be the only HeLab running there;
- it makes `store-v4` beside the existing `store-v3`, and never writes store-v3;
- it asks "An older disk cache" once. Keep using it, or Ignore it, are both safe. Clear it… removes store-v3.

That is acceptable:
- the older HeLab keeps working from its untouched store-v3;
- if store-v4 misbehaves, V-2's hidden fallback (`store_v4=false` in the settings) takes this build back to
  store-v3;
- on your word, the cache rebuilds in minutes.

But it leaves a store-v4 in the lab's cache folder that the older HeLab doesn't count or clear. The isolated
folders avoid that, so use them unless you want the real setup tested.

### M47.2 + Q51.1: a load from the raw layer on the share

1. Run `helab` with the four lines set, then Help › Record I/O trace (this session).
2. Pick a share folder with a large shot (tens of MB raw). It needs its `.helab-root` above it; if it has none,
   placing one writes to the share.
3. Load it once (HeLab priority, the default) and note Folder details' load time. This first load reads it over
   the share.
4. Q51.1: once loaded, the background raw fill lists the folder once more. In Folder details' activity it shows as
   the raw fill.
5. Its time is in the trace: Help › Show I/O trace folder, then in the newest helper file find the line with
   `"reason": "raw fill: listing"`. Its `seconds` and `entries` are the listing's time and size.
6. During and just after that fill: note whether browsing other folders, or the next load, is slower. If it is,
   Q51.1 (c) follows (the load hands the fill its listing).
7. Wait until the fill finishes: Settings › Cache's "HeLab's cached raw pulses" row includes the folder.
8. Right-click the folder › "TXY for this folder…" › another profile, one this folder never loaded with. Load it
   and note the load time: this load converts from the raw layer, with no reads of the shots over the share.
9. Compare the times from steps 3 and 8, per shot, for the large shot. On an M4 the raw step took 0.48 s for a
   3.25 MB shot, against 0.004 s to parse its text locally. Expect the raw layer to pay off only on a slow share.
   Above about 30 MB a shot may pass the first file timeout.

### M42.1: the raw layer's codec on the lab PC

On a copy of the sample set, in the same window, with the four lines set, and `--root` pointing at the copy:

```powershell
Measure-Command { python dev\txy\check_samples.py --root C:\path\to\txy-v1-copy --backend numpy | Out-Default }
Measure-Command { python dev\txy\check_samples.py --root C:\path\to\txy-v1-copy --backend numpy --via-layer | Out-Default }
```

- Both runs must show every shot identical.
- The script prints no times, so `Measure-Command` gives each run's total.
- The second run's extra time, divided by the copy's raw `d*.txt` megabytes, is the codec's MB/s on this PC.
  zstd 9 gave 16 MB/s per M4 Max thread, and an estimated 4–5 MB/s here.
- If it's too slow for a folder's background fill, M42.1 says zstd 5.
- It is in memory and read only: nothing is written beside the samples, and its scratch goes under `src\.ai\temp\txy\`.
