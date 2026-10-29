# HANDOFF.md — Warden: RIVALS Public FFA Session Runner

> Working name is **Warden** (it keeps watch over your session). Rename freely.

---

## 0. How to work on this (read first, Claude Code)

> **Since 2026-10-29 the repo uses the stage harness in `CLAUDE.md` and `PRINCIPLES.md`.** Phases 0–9
> below are finished history. New work is the **Stages** list at the end of section 10: one prompt =
> one stage, each ending with a smoke check, `python scripts/smoke.py`, the verifier, a PROGRESS.md
> entry, commit and push. Where the bullets below disagree with `CLAUDE.md`, `CLAUDE.md` wins.

- Build in the **phases in section 10**, in order. Each phase has a Definition of Done (DoD).
- Keep a `PROGRESS.md` at the repo root: current phase, what's done, decisions made, known issues, exact next step. Update it at the end of every phase and before any long pause. Commit after each phase.
- **If your context gets cleared/compacted:** re-read `HANDOFF.md` and `PROGRESS.md`, then continue from the first unchecked DoD item. Don't redo finished phases.
- **Don't stop to ask questions.** Pick sensible defaults, write them into `PROGRESS.md` under "Decisions", and keep going. Section 12 lists the things I'll confirm later.
- Default to **offline tests** (synthetic frames + recorded frame replay). Only drive the real Roblox client when I explicitly start a live test.

> **User override (2026-10-01):** stop at the end of **every** phase for the user to review before starting the next one.

---

## 1. Clean-room rules (non-negotiable)

This spec describes the *behavior* of a commercial macro (Nova Macro) so we can build our own. We are building an **independent implementation**, not a copy.

- Do **not** download, decompile, open, or reference Nova Macro's executable, bytecode, assets, icons, or text. Don't search for its source.
- Use an **original** name, branding, color palette, icons, layout details, UI copy, and log/event messages. Don't imitate its look.
- Icons: draw simple ones yourself or use an open-licensed set (e.g. Lucide, MIT) and include its LICENSE file.
- **No licensing, trial, or DRM system.** This is a personal tool.

---

## 2. Goal

Fully unattended grinding of RIVALS playtime contracts (first target: **Glass Wrap, 24h**) in **public FFA matches**. It must:

- Join public FFA from the lobby, verify the loadout, and stay alive in the match.
- Handle deaths, match end/rotation, mid-game join prompts, server shutdowns, disconnects, Roblox crashes, and Roblox updates — and get back into public FFA without me touching anything.
- Show clearly how long I've been AFK (this session and all-time) and how close I am to the contract target.
- Be customizable from a GUI with no code edits.

**Important:** the contract only counts in **public** servers. Default launch mode is `public`. A `share_link` mode exists as an option but is **off by default**, and the README must warn it may not count toward contracts.

---

## 3. Tech stack

- Python 3.12 (64-bit), Windows 10/11; macOS 13+ as a DMG built by GitHub Actions (`warden-mac-handoff.md`)
- **GUI:** PySide6
- **Capture & vision:** `mss`, `opencv-python`, `numpy`; `pytesseract` optional (OCR features degrade gracefully if Tesseract isn't installed)
- **Input:** own `ctypes` wrapper around `SendInput` (scan-code keys, relative mouse moves, clicks) as primary; `pydirectinput` then `pynput` as fallbacks
- **Windows/process:** `ctypes`/`pywin32` (enumerate windows, class names, foreground, DPI), `psutil`
- **Hotkeys:** `pynput` global listener
- **Config:** `pyyaml` + `pydantic` (validated schema, helpful errors)
- **Integrations:** `requests` (Discord webhook), `discord.py` (optional bot), `fastapi` + `uvicorn` (optional LAN dashboard), `winotify` or similar (toasts)
- **Tests:** `pytest`
- **Packaging:** PyInstaller, one-folder build

---

## 4. Architecture

### 4.1 Layout

```
warden/
  __main__.py                # entry: python -m warden
  core/
    state_machine.py         # states, transitions, timeouts, fallbacks
    tick.py                  # main loop: capture → detect → decide → act
    events.py                # event bus (GUI, log, Discord, LAN all subscribe)
    session.py               # timers, counters, uptime, incidents
    persistence.py           # atomic state.json, session history
    watchdog.py
  platform/
    window.py                # find real Roblox client, focus + confirm, client rect
    input.py                 # SendInput wrapper + fallback chain
    dpi.py                   # per-monitor DPI awareness, scaling report
    power.py                 # sleep prevention
    process.py               # graceful close → terminate Roblox
  vision/
    capture.py               # mss grab of client area only
    color.py                 # HSV blob finder
    templates.py             # multi-scale template match
    ocr.py                   # optional
    detectors.py             # high-level detectors (see 5.2)
  flows/
    lobby.py                 # Play → mode list → FFA
    loadout.py               # loadout transaction
    respawn.py
    recovery.py
  behaviors/
    idle.py  patrol.py  fire.py  abilities.py  humanize.py
  integrations/
    discord_webhook.py  discord_bot.py  lan_dashboard.py  toast.py
  gui/
    main_window.py  mini_overlay.py  summary_dialog.py
    pages/ home.py loadout.py settings.py calibration.py history.py diagnostics.py
    theme.py
  tools/
    recorder.py  replay.py  diagnostics_cli.py
config/
  default.yaml
  presets/ default.yaml glass_wrap.yaml random.yaml
fixtures/frames/             # recorded + synthetic frames for tests
tests/
```

### 4.2 Main loop

Tick every ~250 ms (configurable): capture the Roblox client area → run only the detectors relevant to the current state (plus always-on ones: disconnect, respawn) → state machine decides → flow issues actions. Every decision and transition is emitted on the event bus with a level (`info` / `success` / `warn` / `error` / `debug`) and detector confidence.

**Input gate:** no key or click is ever sent unless the Roblox client is confirmed foreground. If focus can't be confirmed, skip that action, log it, refocus, retry next tick.

---

## 5. Detection

### 5.1 Approach: color first, templates second, OCR third

RIVALS' important buttons and the health bar are strongly colored, so the primary detector is **HSV color blobs**, not icon templates. This survives small UI changes far better.

Every detector is defined in config with:

- **ROI** as fractions of the client area (e.g. `[0.30, 0.70, 0.70, 0.98]` = x1, y1, x2, y2)
- **HSV range(s)**
- **min/max area** as a fraction of the client area, and an **aspect-ratio** range
- optional **template** fallback (multi-scale 0.75–1.25×) and optional **OCR** text check
- **confirm_frames**: how many consecutive ticks it must be seen before it counts

All of this is editable in the Calibration page (section 7.4).

### 5.2 Detectors needed

| Detector | What it finds | Primary method |
|---|---|---|
| `lobby_play` | Green Play button in the lobby | Color blob, lower screen ROI; fallback to a looser "lower green" range |
| `mode_list` | Game-mode list is open | Template/layout |
| `ffa_tile` | The FFA entry in the mode list | Template + OCR "FFA" |
| `health_bar` | Green health bar = alive in match | Color blob |
| `respawn_prompt` | Death/respawn screen | Template + color |
| `weapon_picker` | Loadout/weapon picker open | Template anchor |
| `switch_weapons` | Post-respawn "switch weapons" window | Template/color |
| `midgame_join` | "Join this game" prompt | Green blob + OCR |
| `match_end` | Results / vote / scoreboard screens | Template + OCR |
| `disconnect_modal` | Roblox disconnect / error dialog | Dimmed background + centered dialog + button pair + OCR error code |
| `roblox_updating` | Roblox updater window | Window title/class |
| `frozen` | Frame not changing | Perceptual hash unchanged ≥ 30 s while in match |

---

## 6. Behavior spec (the features to reproduce)

### 6.1 States

| State | Entered when | Action | Timeout / fallback |
|---|---|---|---|
| `IDLE` | App open, not running | — | — |
| `LAUNCHING` | Start or recovery | Open launch target (6.6) | 90 s → `RECOVERING` |
| `LOADING` | Client window exists | Wait | 120 s → `RECOVERING` |
| `LOBBY` | `lobby_play` confirmed | Click Play (verified click) | 30 s → retry, then `RECOVERING` |
| `MODE_SELECT` | `mode_list` visible | Scroll list to bottom (**wheel only**, no drag), find `ffa_tile`, click, verify transition | 60 s → back to `LOBBY`. **Abort the search early** if the weapon picker, health bar, or respawn prompt appears — we're already in. |
| `MIDGAME_JOIN` | `midgame_join` seen | Click with verification | 15 s → `MODE_SELECT` |
| `LOADOUT` | Picker visible, or reapply due | Loadout transaction (6.3) | 45 s → abort, retry at next safe window |
| `IN_MATCH` | `health_bar` confirmed | Behavior profile, abilities, anti-idle | — |
| `DEAD` | `respawn_prompt` | Respawn (6.4) | 20 s → `UNKNOWN` |
| `MATCH_END` | `match_end` | Click through to continue / back to modes | 60 s → `LOBBY` |
| `DISCONNECTED` | `disconnect_modal` confirmed (6.5) | Recovery | — |
| `RECOVERING` | Any recovery trigger | Recovery flow (6.5) | Backoff, forever until stopped |
| `UNKNOWN` | Nothing matched for 45 s | Save frame to unknown gallery → press Escape → recheck → `RECOVERING` | — |
| `PAUSED` / `STOPPED` | User | No input | — |

### 6.2 Reliable input

- **Click sequence:** move to target → small relative-motion "jiggle" (Roblox can ignore clicks with no prior mouse movement) → press/release via `SendInput` → recapture after ~400 ms → if the target is still there, one more deliberate click → if still there, refocus the client and click once more → then give up and log.
- **Fallback chain** if a click/key method fails: `SendInput` → `pydirectinput` → `pynput`. Log which one worked at `debug` level.
- **Keys** as hardware scan codes (DirectInput-style), with randomized hold durations.
- **Finding the client:** process `RobloxPlayerBeta.exe` + its top-level window. **Never** target a browser tab with "Roblox" in its title — exclude browser window classes (e.g. `Chrome_WidgetWin_1`, `MozillaWindowClass`).
- **Coordinates:** always fractions of the client area; process is per-monitor-DPI-aware so 100/125/150% scaling and 1080p/1440p all work.
- **Emergency stop:** mouse held in the top-left 5×5 px corner for 0.3 s, or the stop hotkey.
- **Don't cover the game:** on Start, the main window minimizes or moves off the Roblox client rect. The optional mini overlay (8.12) docks outside it.

### 6.3 Loadout (transactional, verified)

- Four slots: **Primary, Secondary, Melee, Utility**. A preset names a weapon per slot; each weapon has a template image captured in Calibration.
- Open the picker with the configured key (default **M** — verify).
- **Transaction:** begin → for each slot: select the slot category → locate the weapon tile by template → click → verify the slot now shows that weapon → next slot. Commit only on **4/4 verified**.
- **Never guess a grid position.** If a weapon tile isn't found, scroll/search inside the picker up to N times; if still not found, fail that slot, log it, and continue.
- **Abort** mid-transaction if a death/respawn prompt appears, the picker disappears, or a disconnect is detected. Discard partial state; retry at the next safe window.
- Count **Loadout fixes** = slots that needed correcting.
- On any verification failure, save a diagnostic crop to `diagnostics/loadout/<timestamp>_<slot>.png`.
- **Reapply** after respawns, during the post-respawn switch-weapons window (the safe window).
- **Quick presets:** `Default`, `Glass Wrap`, `Random` (random pick per slot from my owned-weapons list each match). Plus user-created presets.

### 6.4 Respawn

On `respawn_prompt`: press **Space** → if still visible after ~1.5 s, press Space once more → watch ~6 s for the switch-weapons window → run the reapply loadout step if due → back to `IN_MATCH`. Count **Respawns**.

### 6.5 Disconnect & recovery

- **Confirm before acting:** a disconnect candidate must be seen in ≥ 3 captures over ≥ 1.5 s, with modal context (dimmed background, centered dialog, a two-button pair). If it vanishes, reset the candidate. This avoids false positives from brief overlays.
- **Prefer Leave over Reconnect/Retry** — the in-game reconnect button is unreliable. Identify which button is which via relative position + color + OCR; make the choice configurable.
- **Recovery sequence:**
  1. Click Leave → wait 10 s.
  2. If a Roblox client is still running: graceful close (`WM_CLOSE`), then terminate after 10 s. Confirm it's gone.
  3. Open the launch target (6.6) → wait for the client window (≤ 90 s) → `LOBBY` → `MODE_SELECT` → FFA.
  4. Success = **two independent confirmations** that we're in a match (e.g. health bar seen twice, ≥ 5 s apart).
  5. Up to **3 attempts** of steps 2–4.
  6. **Browser fallback:** open the RIVALS game page in the default browser, find that browser window, find its green Play button, click, then step 4.
  7. If all fail: exponential backoff 30 s → 10 min cap, retry forever until stopped. Discord/toast alert after 3 failed cycles.
- **Other recovery triggers:** Roblox process gone, `frozen` while in match, Roblox updater window, error codes read by OCR (277, 279, 267, 268, 529 …).
- Track per incident: cause, start/end time, attempts, method that worked, time lost. Count **Reconnects**.

### 6.6 Launch targets

| Mode | Target | Default |
|---|---|---|
| `public` | `roblox://experiences/start?placeId=<PLACE_ID>` | **On.** Place ID default `17625359962` — verify against the game's roblox.com URL |
| `share_link` | Roblox share-link deep link with my code | Off. README warns contracts may not count |
| browser fallback | `https://www.roblox.com/games/<PLACE_ID>` | Used by 6.5 step 6 |

### 6.7 In-match behavior

Pluggable profiles, all with humanized timing (8.10):

- `idle_nudge` — minimal movement + occasional look-around to beat the idle kick
- `patrol` — WASD pattern with jitter
- `fire_loop` — fire the configured slot every N s at a configured aim offset
- `hide_spot` — walk a recorded key path after spawn, then `idle_nudge`

**Abilities:** optional list of keys + intervals (default ability key **F** — verify), only sent in `IN_MATCH` with confirmed focus.

**Idle-kick defense:** if Roblox's idle warning appears (OCR), immediately move and act.

---

## 7. GUI

Pages in a left sidebar: **Home, Loadout, Settings, Calibration, History, Diagnostics.**

### 7.1 Home (dashboard)

- Start / Pause / Stop, status chip (Ready / Running / Queueing / In match / Recovering / Paused)
- Big **session timer** (HH:MM:SS) and **total AFK time across all sessions**
- **Contract progress bar:** credited hours / target, ETA, % — shows whether the value is *estimated* or *OCR-verified* (8.1)
- Counters: **Respawns · Reconnects · Re-queues · Loadout fixes · Time lost**, plus in-match uptime %
- Automation toggles: Auto reconnect · Respawn recovery · Auto re-queue · Abilities · Anti-idle
- Active loadout card: 4 slots, each with a verified tick
- Quick preset buttons
- Live thumbnail of the Roblox window (~1 fps)
- Event log with level filter and a "verbose" toggle that shows low-level detection/retry messages

### 7.2 Loadout

Per-slot weapon picker from the captured template library, preset create/rename/delete, **Verify now** button showing per-slot confidence.

### 7.3 Settings

Launch mode + place ID / share code, hotkeys (rebindable; defaults F6 start, F7 pause, F8 stop, F9 screenshot), behavior profile, timings + jitter, target hours + auto-stop options, scheduler, integrations, always-on-top, log verbosity, observe-only mode.

### 7.4 Calibration wizard

Steps through each screen the detectors need (lobby, mode list, FFA tile, in match, death, picker, switch weapons, results, disconnect). For each: capture a region as a template, click/drag to sample an HSV range, adjust ROI, and see a **live detection overlay** with boxes + confidence. Includes a "test click" button and a coordinate picker that outputs client-area fractions.

### 7.5 History

Past sessions table (start, duration, in-match %, counters, incidents) and a **timeline chart** of states over time.

### 7.6 Diagnostics

DPI/scaling, Roblox window found + class, focus test, capture FPS, per-detector hit rates, Tesseract available, webhook reachable.

### 7.7 End-of-session summary dialog

Duration, in-match time and %, counters, longest uninterrupted stretch, list of incidents with causes.

### 7.8 Visual identity (original)

Graphite background (`#121417`), raised cards (`#1B1E23`), off-white text, single **amber** accent (`#F2A93B`), success green and error red for states only. Segoe UI Variable with sensible fallbacks. Rounded cards are fine; keep the look our own.

---

## 8. Extras (beyond the reference app)

1. **Contract progress verification** — opportunistically OCR the real contract progress when safely in the lobby (e.g. during recovery) and correct the estimate. Otherwise estimate from time in public match; make the estimate rule configurable.
2. **Discord webhook** — status embed every N min (screenshot, state, timers, counters, hours remaining) + instant alerts (disconnect, recovery result, unknown screen, milestone every 4 h, target reached).
3. **Discord bot (optional)** — `/status`, `/screenshot`, `/pause`, `/resume`, `/stop`, restricted to my Discord user ID.
4. **Phone dashboard on LAN (optional)** — small web page showing live stats + thumbnail, with pause/stop behind a PIN. Off by default, binds to the local network only.
5. **Sleep prevention** — `SetThreadExecutionState` during sessions so Windows doesn't sleep or blank the screen; restored on stop.
6. **Observe-only mode** — runs all detectors and the state machine and logs what it *would* do, but sends no input. For safe testing and calibration.
7. **Frame recorder + replay harness** — record captures (~2 fps) with detector outputs; replay runs the full state machine offline against a recording. Used heavily in tests.
8. **Unknown-screen gallery** — every unknown frame saved with timestamp; one click turns a region of it into a new template.
9. **Scheduler** — stop at target hours, stop at a clock time, run only inside time windows, optional PC sleep/shutdown after stop with a 60 s cancelable countdown.
10. **Humanization** — Gaussian jitter on every timing, randomized look-arounds, occasional micro-pauses. No fixed intervals anywhere in the codebase.
11. **Contract queue** — chain presets (Glass Wrap → next contract), each with its own target hours.
12. **Mini overlay** — compact always-on-top strip (timer, state, counters) that docks outside the Roblox window.
13. **Windows toast notifications** for incidents and milestones.
14. **Watchdog** — main-loop heartbeat; restart the worker if it stalls 60 s; alert.

---

## 9. Persistence

All under `%LOCALAPPDATA%\Warden\`:

- `config.yaml`, `presets/*.yaml`
- `state.json` — cumulative AFK time per contract, all-time counters, target progress. Written **atomically** (temp file + rename) every 30 s and on every event.
- `sessions/<timestamp>.json` — per-session summary + incidents
- `logs/` — rotating per session
- `diagnostics/`, `unknown/`, `recordings/`

If the app or PC crashes, totals survive. On next launch, Home offers **Resume last session**.

### Example `config/presets/glass_wrap.yaml`

```yaml
name: Glass Wrap
contract:
  label: Glass Wrap
  target_hours: 24
  auto_stop_at_target: true
launch:
  mode: public              # public | share_link
  place_id: 17625359962     # verify from the game's roblox.com URL
  share_code: ""
loadout:                    # placeholders — I'll confirm
  primary: Grenade Launcher
  secondary: Handgun
  melee: Fists
  utility: Grenade
behavior:
  profile: idle_nudge
  anti_idle_seconds: 75
  jitter_pct: 15
abilities:
  enabled: false
  keys: [{ key: F, every_seconds: 20 }]
keys:
  respawn: SPACE
  loadout: M
```

---

## 10. Phases and Definitions of Done

### Phase 0 — Scaffold
- [ ] Repo, `requirements.txt` / `pyproject.toml`, pydantic config schema, logging, event bus, `PROGRESS.md`
- [ ] `python -m warden` opens an empty themed window
- [ ] Default config loads and validates; invalid config shows a readable error
- [ ] `pytest` runs green

### Phase 1 — Platform & vision core
- [ ] Window finder returns the real client and ignores browser tabs (unit-tested with mocked window lists)
- [ ] Focus-confirm gate blocks input when Roblox isn't foreground
- [ ] DPI-aware client-area capture; fraction ↔ pixel conversion tested at 100/125/150% scaling
- [ ] HSV blob detector + multi-scale template matcher, tested on synthetic frames (generated green rectangles, scaled templates)
- [ ] Input wrapper with fallback chain and jiggle-then-click; emergency stop works
- [ ] Observe-only mode and frame recorder work; `tools/diagnostics_cli.py` prints window/DPI/capture info

### Phase 2 — State machine, lobby, FFA, respawn, match end
- [ ] All states in 6.1 implemented with timeouts and fallbacks
- [ ] Replay tests over synthetic frame sequences cover every transition, including early-abort of the FFA search and the mid-game join prompt
- [ ] Respawn double-press logic tested; Respawns counter increments

### Phase 3 — Loadout transactions
- [ ] 4/4 verified commit path
- [ ] Single-slot mismatch → corrected → Loadout fixes +1
- [ ] Abort on death mid-transaction, retried at next safe window
- [ ] Missing weapon tile never triggers a guessed click; diagnostic crop saved

### Phase 4 — Recovery
- [ ] One-frame modal flash does **not** trigger recovery
- [ ] Leave preferred over Reconnect; 3 attempts then browser fallback; then backoff
- [ ] Frozen-frame, process-gone, and updater triggers tested
- [ ] Incidents recorded with cause, attempts, method, time lost
- [ ] (Live, when I start it) killing `RobloxPlayerBeta.exe` mid-match → back in public FFA with verified loadout, no input from me

### Phase 5 — GUI
- [ ] All pages in section 7, dashboard updates live from the event bus
- [ ] Presets switch from Home and persist
- [ ] Hotkeys work while Roblox is focused
- [ ] App never overlaps the Roblox client during a session
- [ ] Summary dialog on stop

### Phase 6 — Persistence, tracking, scheduler
- [ ] Kill the app mid-session → relaunch → totals intact, Resume offered
- [ ] Stop-at-target works (test with a 0.01 h target)
- [ ] Scheduler windows and stop-at-time work; shutdown countdown is cancelable

### Phase 7 — Integrations
- [ ] Discord webhook embed with screenshot on interval + alerts
- [ ] Optional bot commands restricted to my user ID
- [ ] LAN dashboard reachable from my phone, PIN-gated controls, off by default
- [ ] Toasts and sleep prevention working

### Phase 8 — Calibration, unknown gallery, diagnostics, extras
- [ ] Calibration wizard can capture a template, sample an HSV range, and show live detections in under a minute per screen
- [ ] Unknown gallery → "make template" flow
- [ ] Diagnostics page complete; contract OCR verification and contract queue working

### Phase 9 — Packaging & docs
- [ ] PyInstaller one-folder build runs on a clean Windows machine
- [ ] README: install, Tesseract (optional), first-run calibration walkthrough, public vs share-link note, Discord setup, troubleshooting, and a clear note that automating play is against Roblox's rules and can get the account banned — test on an alt
- [ ] No gameplay-specific values hardcoded anywhere; everything lives in config/presets

### Stages (one prompt each; tick here and in PROGRESS.md "Stages")

IDs: `M` Mac, `W` Windows/both, `L` live test, `H` harness, `B-NNN` bug, `R-n` refactor.
**(needs the user)** = can't finish without them. **[design]** = approved note in `docs/design/` first.

- [x] **M0-M4** — Mac port code and DMG release workflow. Ref: `warden-mac-handoff.md` §7 Phases 0–4.
- [x] **H0** — Stage harness (CLAUDE.md, PRINCIPLES.md, smoke, hooks, verifier) and DMG as the only Mac launch path. Ref: user request 2026-10-29.
- [ ] **M4U** — **(needs the user)** First Mac CI run. The user pushes `main` and creates the pre-release tag `v0.0.1-mactest`; Claude fixes whatever the "Mac release" log shows until the run is green and both DMGs are on the pre-release. Ref: `warden-mac-handoff.md` §5, §7 Phase 4.
- [ ] **B-001** — Mac CI crashes on Qt teardown after the Mac port tests pass (no DMG). Ref: `docs/bugs/BUG-001-mac-ci-qt-teardown-crash.md`, M4U.
- [ ] **M5a** — **(needs the user)** Real-Mac checklist steps 1–4 (install from DMG, permissions, Roblox window found, capture has no title bar and right colors). Ref: `warden-mac-handoff.md` §7 Phase 5.
- [ ] **M5b** — **(needs the user)** Real-Mac checklist steps 5–10 (clicks land, loadout, hotkeys, reconnect, stop, stays awake). Ref: same.
- [ ] **M5c** — Fix what M5a/M5b found (one `B-NNN` stage per bug), then the user tags the first normal release `v0.2.0`. Ref: same, §8 risks.
- [ ] **W1** — **[design]** Corner emergency stop: `CornerWatch` exists but nothing starts it on either OS, while the README describes it. Wire it in (both OSes) or take it out of the README. Ref: §6.2, Phase 1 DoD "emergency stop works".
- [ ] **L1** — **(needs the user)** Windows live recovery test on an alt account: kill `RobloxPlayerBeta.exe` mid-match, Warden gets back into public FFA with the loadout verified. Ref: Phase 4 last DoD item.

---

## 11. Testing rules

- Every detector and flow has offline tests using synthetic frames or recordings in `fixtures/frames/`.
- Live tests only when I explicitly start one, preferably on an alt account.
- Every test and smoke run is observe-only: `scripts/smoke.py` sets `WARDEN_FORCE_OBSERVE_ONLY=1`
  (no real clicks or keys, whatever config says) and a temp `WARDEN_HOME`. Tests never write into the
  repo's `config/` or `templates/`.
- OS APIs (Win32, Quartz, AppKit, IOKit) are tested through fakes. Real-Mac behavior is only proven by
  the M5 checklist on a personally owned Mac.
- Every stage adds a permanent check in `smoke_checks/`; the smoke suite re-runs all of them.
- When a live run hits something unexpected, save the recording and add it as a regression fixture.

---

## 12. Things I'll confirm later (use the defaults, don't block)

- Glass Wrap preset weapons (placeholders in section 9)
- RIVALS keybinds: respawn = Space, loadout = M, ability = F
- RIVALS place ID
- Whether lobby time counts toward the contract (affects the progress estimate)
