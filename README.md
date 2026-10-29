# Warden

Warden watches a RIVALS session for you: it joins public FFA matches, keeps your
loadout correct, handles deaths and disconnects, and tracks how close you are to
a playtime contract — fully unattended, with a GUI to control and watch it.

> **⚠️ Automating gameplay is against Roblox's Terms of Use and can get your account
> banned or terminated.** This is a personal automation tool, built for one account at
> a time. **Test it on an alt account first**, not your main, before trusting it with
> an account you care about. You are using this entirely at your own risk.

This is an independent, clean-room implementation — it does not use, reference, or
include any code, assets, or branding from any other macro. See [HANDOFF.md](HANDOFF.md)
section 1 for the clean-room rules this project follows.

---

## Install

**Requirements:** Windows 10/11 or macOS 13+ (Mac users: see **Mac** below for the no-Terminal download), Python 3.12+ (built and tested on
3.12/3.14), a 64-bit Python install. Everything in this README applies to both —
the only differences are the shell commands below and where things like logs and
config end up on disk, covered in the **Mac** section further down.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m warden
```

On a Mac, don't use these commands: download the **DMG** instead (see **Mac** below).
It's a normal Mac app, so there's no Python, no Terminal and no setup script.

Or run it as a packaged build (no Python install needed) — see **Packaging** below.

On first run, Warden copies its default settings into `config.yaml` and
`presets\*.yaml` under its data folder — `%LOCALAPPDATA%\Warden` on Windows,
`~/Library/Application Support/Warden` on macOS (every other `%LOCALAPPDATA%\Warden`
path in this README has a matching folder in that same macOS location). Edit those
(or use the Settings/Loadout pages) — the files in this repo's `config/` folder are
only the shipped defaults and are never modified by the running app.

### Mac (download, no Terminal needed)

Works on personally owned Macs running macOS 13 Ventura or newer.

1. Download from this repo's **Releases** page: `Warden-mac-arm64.dmg` for Apple
   Silicon Macs (M1 or newer), or `Warden-mac-x86_64.dmg` for older Intel Macs if one
   is offered. To check which you have, open the Apple menu → **About This Mac** and
   look at **Chip** (Apple M-something = Apple Silicon; Intel = Intel).
2. Open the DMG and drag **Warden** into **Applications**.
3. The first time you open it, macOS may say it can't verify the app (Warden isn't
   notarized by Apple). Open **System Settings → Privacy & Security**, scroll down,
   and click **Open Anyway**. (On some macOS versions, right-click → **Open** also works.)
4. Follow Warden's **Mac setup** screen to allow **Accessibility** (clicks and keys),
   **Screen Recording** (seeing the game) and **Input Monitoring** (hotkeys), and
   reopen Warden when it asks.
5. **School and work Macs** usually block this kind of app through device management
   and **aren't supported**. Warden doesn't try to get around that.

Mac notes:

- **Hotkeys:** Mac keyboards need Fn for F6–F9, so a new Mac install starts with
  **Ctrl+Shift+S** (start), **Ctrl+Shift+P** (pause), **Ctrl+Shift+X** (stop) and
  **Ctrl+Shift+K** (screenshot). Change them on the Settings page.
- **OCR is off on Mac** (installing Tesseract needs Terminal). The few features that
  use it (idle-warning text, disconnect error codes, contract progress verification)
  just stay off; everything else works.
- **Updates may ask for permissions again.** macOS ties these permissions to the app's
  signature, and each build has a new (ad-hoc) one. If Warden stops seeing or clicking
  after an update, open the Mac setup page and allow them again.
- **Windowed vs. fullscreen Roblox:** Warden trims the title bar off a windowed Roblox
  window automatically (`mac.title_bar_pt` in config.yaml, default 28). If clicks
  land slightly off, play RIVALS in **fullscreen**.
- **The DMG is the only supported way to run Warden on a Mac.** The old
  `.command` launchers are gone. Developers can still run from source with the
  commands above (`python3` instead of `python`), but permissions then belong to
  Terminal, not Warden.app.
- Everything else (calibration, presets, Discord/LAN integrations, troubleshooting)
  works the same as on Windows; swap in `~/Library/Application Support/Warden`
  wherever this README says `%LOCALAPPDATA%\Warden`.

### Optional: Tesseract OCR

A few detectors (idle warnings, disconnect error codes, contract progress
verification) use OCR, which is **optional** — everything else works without it,
and those specific features just stay off until it's installed.

1. Install Tesseract: <https://github.com/UB-Mannheim/tesseract/wiki> (Windows installer).
2. Warden looks for it on `PATH`, or at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
3. Check the **Diagnostics** page — it reports whether Tesseract was found.

### Optional: integrations

Discord webhook/bot, the LAN phone dashboard, and desktop toast notifications are all
optional and off by default (toasts are on by default). Toasts use `winotify` on
Windows and the built-in `osascript`/Notification Center on macOS (nothing extra to
install there). The other packages (`requests`, `discord.py`, `fastapi`, `uvicorn`)
are in `requirements.txt`'s `integrations` extra — install them only if you want
those features:

```bash
pip install -e ".[integrations]"
```

Enabling an integration whose package isn't installed just logs a warning and leaves
that one feature off — it never crashes the app.

---

## Quick start (no setup)

1. Open RIVALS (windowed or fullscreen, any resolution).
2. Open Warden and press **Start**.
3. In your **first** match, pick your weapons yourself when the weapon picker shows
   up - Warden watches and remembers them. From then on it picks them for you.

That's it. Warden ships with the screens it needs to recognise (Play button, game-mode
menu, Free For All, health bar, weapon picker, respawn button) already set up, and
they scale to your resolution. Calibration is only for fixing something that isn't
being recognised (e.g. after a big RIVALS UI update).

The Home page tracks a "Recent sessions" chart of in-match minutes per session, and
the History page keeps a full table of every past session (duration, in-match time,
incidents) — both read from the same session records Warden has always saved, so
there's nothing to turn on.

## First run: Calibration (optional)

**Quick version (recommended):** open RIVALS, then in Warden go to **Calibration** and
click **▶ Auto-capture screens**. A small panel appears over the top-right of Roblox and
walks you through each screen (lobby, mode menu with FFA, in a match, weapon picker, ...),
taking each screenshot by itself after a short countdown - just go to that screen in the
game. Afterwards, click each screen in the **Setup checklist**, drag **one small box**
around what it describes (the hint above the picture says what), and press
**✓ Save this screen**. It turns green when Warden can see it. Don't box the whole
screen - Warden refuses boxes that cover most of it.

The health bar ships pre-calibrated from a real RIVALS screenshot.

**Weapons:** click **🎯 Learn my loadout**, open the weapon picker in RIVALS (start of an
FFA match or the shooting range) and pick your weapons yourself like normal - Warden
watches your clicks and learns each one. After that it picks them for you every match.

**Moving/shooting:** Settings → Behavior → Profile. `fight` walks around and shoots,
`patrol` only walks, `fire_loop` stands and shoots, `idle_nudge` barely moves.

The detailed manual steps below still work if you prefer them.

Warden's detectors (what counts as "the Play button", "the health bar", "a weapon
tile", etc.) ship as **uncalibrated placeholders** — they're reasonable guesses at
screen layout and color, not tuned to your actual screen, resolution, or scaling.
**Run Calibration before your first real session.**

1. Launch RIVALS into the game yourself (Warden won't drive the Calibration page's
   detection — just captures what's on screen).
2. Open Warden → **Calibration** → **Detector wizard** tab.
3. Pick a screen from the dropdown (`lobby_play`, `mode_list`, `ffa_tile`,
   `health_bar`, `respawn_prompt`, `weapon_picker`, `switch_weapons`, `match_end`,
   `disconnect_modal`, `contract_progress`, ...).
4. Click **Capture live frame** (grabs the current Roblox window) — or **Load
   image…** to calibrate from a saved screenshot instead.
5. Drag a box over the thing that identifies this screen (the Play button, the
   health bar, etc.).
6. Click **Sample HSV from selection** (for color-based detectors like buttons and
   health bars) and/or **Save selection as template** (for icon/layout-based
   detectors), then **Set as detector ROI** to narrow where it looks.
7. Click **Run detection** to see the live hit/confidence result against your
   current capture.

Repeat for each screen — each one is a couple of clicks once you've got the hang of
it. You don't need to press Start to calibrate: **Capture live frame** grabs the
Roblox window directly (Warden minimizes itself for a moment so it isn't in the
shot). Saving a template for a color-based detector such as `lobby_play` switches
that detector to template matching automatically.

**The minimum to reach an FFA match:** `lobby_play`, `ffa_tile` (or `mode_list`) and
`health_bar`. Pressing Start with any of those missing shows a "Calibration needed"
prompt listing exactly what's missing. Captured templates are saved under
`%LOCALAPPDATA%\Warden\templates\`, so they survive rebuilding the .exe. The **Unknown gallery** tab (second tab) lists every screen Warden didn't
recognize during a real run; pick one, drag a region, and turn it into a new
template the same way.

The **Loadout** page's weapon templates work the same way: each weapon needs its
own captured template image before Warden can select it in the weapon picker. Until
a weapon's template exists, Warden will never guess a click — it just logs that slot
as failed and moves on (see HANDOFF.md §6.3).

---

## Launch mode: public vs. share link

**The contract only counts in public servers.** Warden's default launch mode is
`public` (joins via `roblox://experiences/start?placeId=...`). A `share_link` mode
exists in Settings for joining a specific server by share code, but **it is off by
default and may not count toward contract playtime** — only use it if you've
confirmed that for yourself. Check the place ID in Settings matches the game's
actual `roblox.com` URL before a long unattended run.

---

## Discord setup (optional)

**Webhook** (status updates + alerts):
1. In your Discord server: *Server Settings → Integrations → Webhooks → New Webhook*,
   copy its URL.
2. Warden → Settings → paste the URL into **Webhook URL**, check **Discord webhook
   enabled**.
3. You'll get a status embed every `interval_min` minutes, plus instant alerts on
   disconnect, recovery result, an unrecognized screen, playtime milestones, and
   reaching the contract target.

**Bot** (optional, `/status /pause /resume /stop /screenshot` from Discord):
1. Create an application + bot at <https://discord.com/developers/applications>,
   copy its token, invite it to your server.
2. Find your own Discord user ID (enable Developer Mode, right-click your name →
   Copy User ID).
3. Put the token and your user ID into `discord_bot` in `config.yaml` (not yet on
   the Settings page — edit the YAML directly for now) and set `enabled: true`.
   Commands from anyone else are rejected.

**LAN dashboard** (optional, a small phone-reachable status page): enable it in
Settings, set a PIN (one is generated and logged if you leave it blank — check the
log file for it). It only ever binds to your local network, never the public
internet, and read/write are separated: status is viewable without the PIN, but
pause/resume/stop require it.

---

## Troubleshooting

- **Open the Diagnostics page first.** It reports DPI/scaling, whether the real
  Roblox client window was found (and its window class — this matters if a browser
  tab is being confused for the client), a focus test, capture FPS, and whether
  Tesseract is available.
- **Nothing seems to click/detect correctly:** almost always means Calibration
  hasn't been run yet for your screen — see above.
- **Warden won't send any input:** check Settings → **Observe-only mode** isn't
  checked (it's a deliberate safe-testing switch that logs what Warden *would* do
  without touching the mouse/keyboard), and that the Roblox window is actually
  focused — Warden's input gate refuses to act otherwise.
- **A config file won't load:** Warden's error messages point at the exact setting
  and problem (e.g. `detectors.lobby_play.roi: x1 (0.7) must be less than x2
  (0.3)`). Fix the named file, or delete it to restore the shipped default (it gets
  re-seeded on the next launch).
- **Roblox keeps rejoining / refreshing without ever opening FFA:** fixed on
  2026-10-01. Starting with Roblox already open now takes over that client instead
  of re-launching it, and a screen Warden can't recognize is retried in place
  (Escape → lobby → Play again) instead of closing and relaunching the game. If it
  still can't get past a step after a few retries and two relaunches, Warden
  **pauses itself** and the event log names the screen that needs calibrating —
  calibrate it, then press Resume.
- **Window too small / text cut off:** the window scales its text and spacing down
  with its size, rows of buttons wrap, side-by-side cards stack, and anything that
  still doesn't fit scrolls.
- **Recovery keeps failing / can't get back into a match:** the Leave/Reconnect
  button positions (`recovery_ui` in config.yaml) are uncalibrated placeholders too
  — these aren't on the Calibration wizard yet; for now, adjust them directly in
  `%LOCALAPPDATA%\Warden\config.yaml`.
- **Logs:** `%LOCALAPPDATA%\Warden\logs\` (rotating, one file per run, last 30 kept).
  Diagnostic crops (failed loadout verification, unrecognized screens) are under
  `%LOCALAPPDATA%\Warden\diagnostics\` and `...\unknown\`.
- **Something looks stuck mid-session:** the emergency stop is holding the mouse in
  the screen's top-left 5×5px corner for 0.3s, or the configured stop hotkey
  (default **F8**; **Ctrl+Shift+X** on a Mac).
- **On macOS, nothing seems to happen at all:** this is almost always the Screen
  Recording / Accessibility permissions — open the **Mac setup** page. The
  Diagnostics page's new "macOS permissions" section repeats this reminder whenever
  it can't find the Roblox window.

---

## Packaging (build your own .exe / .app)

**Mac builds are made by GitHub, not by hand:** pushing a version tag (for example
`v0.2.0`) runs `.github/workflows/mac-release.yml` on GitHub's macOS machines, which
tests, builds `Warden.app`, wraps it in `Warden-mac-<arch>.dmg`, self-checks it, and
attaches it to that tag's GitHub Release. A tag with a dash (`v0.0.1-mactest`) makes
a pre-release. The Windows build below is separate and unchanged.

```bash
pip install -e ".[dev]"
pyinstaller warden.spec --clean
```

On Windows this produces a one-folder build at `dist\Warden\Warden.exe` — copy the
whole `Warden\` folder wherever you like; it carries its own `config\` defaults and
doesn't need Python installed on the target machine. The Mac app can't be built
from Windows (PyInstaller only builds for the OS it runs on), which is why GitHub
builds it, as described above. Nothing gameplay-specific
is hardcoded anywhere in the Python source — every detector range, ROI, keybind,
place ID, and loadout lives in `config\default.yaml` / `config\presets\*.yaml`,
which this build step copies in as the shipped defaults (never overwritten on an
existing install).

---

## Project layout

See [HANDOFF.md](HANDOFF.md) for the full architecture and build phases, and
[PROGRESS.md](PROGRESS.md) for what's been built, decisions made along the way, and
known gaps.
