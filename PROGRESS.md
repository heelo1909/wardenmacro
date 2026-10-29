# PROGRESS.md

Read only "Current status" at the start of a prompt (CLAUDE.md). Keep these headings exactly as they are:
`scripts/progress_view.py` and the Stop hook read them.

## Current status
- **Next stage:** B-002 — make the 13 Windows-only tests skip/fake on a Mac so smoke can pass on a Mac
- **Last stage:** B-001 — Mac CI crash on Qt teardown — PARTIAL 2026-10-29
- **Smoke:** see STATUS.md (generated)
- **Waiting on the user:** nothing (v0.1.1 release build running)
- **Live tests needed:** M5a, M5b (real Mac), L1 (Windows recovery)

## Stages
Mirror of HANDOFF.md §10 "Stages". Tick in both places.

- [x] M0-M4 — Mac port code and DMG release workflow
- [x] H0 — Stage harness and DMG-only Mac launch
- [ ] M4U — First Mac CI run (needs the user)
- [ ] B-001 — Mac CI crashes on Qt teardown after tests pass
- [ ] B-002 — 13 Windows-only tests fail on a Mac (test_power, test_window, test_hotkeys, 2 GUI build tests)
- [ ] M5a — Real-Mac checklist steps 1–4 (needs the user)
- [ ] M5b — Real-Mac checklist steps 5–10 (needs the user)
- [ ] M5c — Fix M5 findings, release v0.2.0
- [ ] W1 — Corner emergency stop [design]
- [ ] L1 — Windows live recovery test (needs the user)

## Stage log
Newest first. Copy the template for each stage.

### Template
- Date: YYYY-MM-DD HH:MM–HH:MM
- Status: DONE | PARTIAL (what's left) | FAILED
- Ref: HANDOFF §… / warden-mac-handoff §… / BUG-NNN
- Built:
- Smoke check added: smoke_checks/<file>.py
- Smoke test: PASS (N checks, pytest X passed / Y known env-only failures on <os>)
- Verifier: PASS | FAIL → fixed → PASS (rounds: n)
- Decisions:
- Needs the user:

### B-001 — Mac CI crashes on Qt teardown after tests pass
- Date: 2026-10-29 12:59–13:12
- Status: PARTIAL (left: local smoke blocked by missing `httpx2`; then verifier, merge `b-001-qt-teardown` into `main`, re-tag)
- Ref: BUG-001, HANDOFF §10 M4U, warden-mac-handoff §7 Phase 4
- Built: `tests/qt_teardown.py` (`shutdown_qt_app`), `pytest_sessionfinish` in `tests/conftest.py`, regression test `tests/test_qt_teardown.py`. Build-only CI run 40917054897 on the branch: both arm64 and x86_64 green, both DMGs built.
- Smoke check added: smoke_checks/b_001_qt_teardown.py
- Smoke test: FAIL (all 10 checks ok; pytest collection error in tests/test_integrations_lan_dashboard.py: latest starlette's TestClient needs `httpx2`, not installed in the new local `.venv`; installing it was not permitted this session)
- Verifier: not run (smoke not passing)
- Decisions: B1
- Needs the user: none
- Update 13:30: `httpx2` installed (user OK). Smoke still FAIL: 13 Windows-only tests fail on a Mac, the same 13 fail on `main` without this change (not caused by B-001). User chose to release first ("just launch the dmg first the smoke tests can wait"): merged to `main` and tagged `v0.1.1`. Decision B2.

### H0 — Stage harness and DMG-only Mac launch
- Date: 2026-10-29 11:33–12:50 (Cowork session, Linux sandbox)
- Status: DONE
- Ref: user request 2026-10-29 ("make it run with the DMG"; adapt the CLAUDE.md harness)
- Built: removed `Run Warden (Mac).command` and `Rebuild Warden.app (Mac).command`; README now sends Mac users to the DMG only. Added CLAUDE.md, PRINCIPLES.md, HANDOFF §0/§10 Stages/§11, this file's harness sections, `scripts/smoke.py`, `scripts/progress_view.py`, `scripts/harness_common.py`, `scripts/known_env_failures.json`, `smoke_checks/` (8 checks), `.claude/` (Stop/PreToolUse/SessionStart hooks, verifier and test-writer agents, /stage /bugfix /refactor /design /retro), `docs/bugs/TEMPLATE.md`, `docs/design/TEMPLATE.md`, `tests/test_harness.py`. Safety net: `WARDEN_FORCE_OBSERVE_ONLY=1` forces observe-only in `TickLoop`.
- Smoke check added: smoke_checks/h0_harness.py, h0_dmg_only.py, h0_observe_only_env.py (plus m2_/m3_/m4_/w_ checks covering the Mac port)
- Smoke test: PASS (8 smoke checks, selftest, pytest 530 tests: 490 passed / 40 known env-only failures on linux, 0 unexpected)
- Verifier: PASS (round 1; 2 nits: CRLF line endings lost in tests/test_tick.py, fixed; HANDOFF §3 stack line is M0-M4 scope, kept)
- Decisions: H1–H6 below.
- Needs the user: M4U (push + tag). Claude Code's hooks call `python`; if `python` isn't on PATH in Git Bash, the hooks fail open with an error, so install it from python.org or the Microsoft Store first.

### M0-M4 — Mac port code and DMG release workflow
- Date: 2026-10-29 (Cowork session, before the harness)
- Status: DONE (code); first CI run is M4U
- Ref: warden-mac-handoff.md §7 Phases 0–4
- Built: Quartz input + key map, Retina helpers, title-bar trim, Mac setup screen, Mac defaults, `--selftest`, `.app` spec, DMG script, `mac-release.yml`; fixed `TickLoop` hardcoding `Win32Windows()`. Details under History → "Mac port".
- Smoke check added: (harness didn't exist yet; covered by H0's m2_/m3_/m4_/w_ checks)
- Smoke test: n/a then; pytest 515 tests, same 40 Linux env-only failures as before
- Verifier: n/a (pre-harness)
- Needs the user: M4U

## Live tests needed
- **M5a / M5b:** the real-Mac checklist (warden-mac-handoff.md §7 Phase 5), personally owned Mac, alt account.
- **L1:** Windows: kill `RobloxPlayerBeta.exe` mid-match → back in public FFA with the loadout verified.
- Map-vote detector seen in a real session (from the 2026-10-03 round).
- **B-001:** green "Mac release" run on the release tag (CI only).

## Decisions
- **B2 (2026-10-29):** User override: merge B-001 and release `v0.1.1` with local Mac smoke failing on 13 pre-existing Windows-only tests (CI's required Mac tests are green). Fixing those is B-002. `known_env_failures.json` was not touched.
- **B1 (2026-10-29):** Mac CI crash (BUG-001) fixed in the test harness, not the app: pytest now closes/deletes leftover widgets and calls `QApplication.shutdown()` at session end. Root cause: Python's interpreter shutdown destroyed the `QApplication` before leftover widgets; macOS 15 runners crash on that ("shared QObject was deleted directly", bus error/segfault). Only confirmable on GitHub's runners: branch run 40917054897 green.
- **H1 (2026-10-29):** The DMG is the only supported way to run Warden on a Mac. The `.command` launchers were removed: they needed Python and opened Terminal, which the user can't use. Developers can still run from source by hand.
- **H2:** Single component, so `smoke_checks/` lives at the repo root (the harness template had one per component).
- **H3:** Smoke runs the whole pytest suite. The only allowed failures are the 40 Linux-sandbox ones (no Win32, no X display) in `scripts/known_env_failures.json`; Windows and Mac lists are empty, so on the user's PC every test must pass.
- **H4:** "Smoke newer than the last code change" is checked by a content hash of all code files (`harness_common.code_fingerprint`), not timestamps, so it works across machines. `.smoke/last-run.json` and `STATUS.md` are committed; `.smoke/gate-blocks.txt` is ignored.
- **H5:** The Stop hook lets Claude stop after 3 blocks in a row (printing why) so it can't loop forever.
- **H6:** `WARDEN_FORCE_OBSERVE_ONLY=1` (set by smoke) forces observe-only input in `TickLoop`; it does not change launch/kill/power actions, which tests already fake.
- Earlier decisions (1–48, Mac port) are under History.

## History (before the stage harness)

### Current phase

**Mac port (warden-mac-handoff.md): Phases 0-4 built (2026-10-29), waiting on the
Phase 4 user test** - push, tag `v0.0.1-mactest`, confirm the workflow is green and both
DMGs are on the pre-release. Details: "Mac port" section below.

**Phase 9 — Packaging & docs: COMPLETE. All 10 phases (0–9) are now built.**

Ran autonomously through every phase per HANDOFF.md section 0's original
instruction (user said "continue all phases without me", away at squash),
stopping only for genuinely live-Roblox-test DoD items. There is exactly
**one remaining stop point**, flagged below and in Phase 4's section: the
live kill-Roblox-mid-match test, which needs the user and the real game.
Calibration (Phase 8) needs to run against the user's own screen before
that live test will mean anything - the detector/loadout/recovery-UI values
shipped are uncalibrated placeholders everywhere, by design (see Decisions).

**⚠️ Incident during Phase 5 (2026-10-01), already handled - see "Decisions"
##29/#30 and `warden-testing-safety` memory:** a manual GUI smoke test briefly
ran the real tick loop while the user's actual Roblox client happened to be
open and focused. A read-only screenshot right after showed the lobby
untouched; flagged to the user via SendUserFile + a message. Fixed the root
cause (test isolation forcing `observe_only`) and separately found/reverted
two test files that were accidentally writing to the real checked-in
`config/` instead of a temp copy - also fixed. No repeat since.

### Phase checklist

#### Phase 0 — Scaffold
- [x] Repo, `requirements.txt` / `pyproject.toml`, pydantic config schema, logging, event bus, `PROGRESS.md`
- [x] `python -m warden` opens an empty themed window
- [x] Default config loads and validates; invalid config shows a readable error
- [x] `pytest` runs green (21 tests)

#### Phase 1 — Platform & vision core
- [x] Window finder ignores browser tabs (mocked window lists) — `warden/platform/window.py`
- [x] Focus-confirm gate — `FocusGate` in same file
- [x] DPI-aware capture; fraction ↔ pixel tested at 100/125/150% — `warden/geometry.py`, `warden/platform/dpi.py`
- [x] HSV blob detector + multi-scale template matcher on synthetic frames — `warden/vision/color.py`, `warden/vision/templates.py`
- [x] Input wrapper, fallback chain, jiggle-then-click, emergency stop — `warden/platform/input.py`
- [x] Observe-only mode, frame recorder, `tools/diagnostics_cli.py` — `warden/tools/recorder.py`, `warden/tools/diagnostics_cli.py`
- [x] `pytest` runs green (87 tests)

#### Phase 2 — State machine, lobby, FFA, respawn, match end
- [x] All 15 states in §6.1 implemented with timeouts and fallbacks — `warden/core/state_machine.py`
- [x] Replay tests over synthetic frame sequences cover every transition, incl. early-abort of FFA search + mid-game join — `tests/test_state_machine.py` (71 cases), `warden/tools/replay.py` + `tests/test_replay.py`
- [x] Respawn double-press logic tested; Respawns counter increments — `warden/flows/respawn.py`, `tests/test_flows_respawn.py`
- [x] Bonus: wired Phase 1 + Phase 2 into a real drivable loop — `warden/core/tick.py` (`LiveActions` + `TickLoop`), runs safely with no Roblox present
- [x] `pytest` runs green (156 tests)

#### Phase 3 — Loadout transactions
- [x] 4/4 verified commit path — `warden/flows/loadout.py` (`LoadoutTransaction`), `tests/test_flows_loadout.py` (13 cases)
- [x] Single-slot mismatch → corrected → Loadout fixes +1 — `LoadoutResult.fixes`
- [x] Abort on death mid-transaction, retried at next safe window — already handled by `_handle_loadout` in Phase 2 (`run_loadout()` is a single idempotent step the state machine can abandon any tick; already-equipped slots are skipped on retry, so nothing is redone)
- [x] Missing weapon tile never triggers a guessed click; diagnostic crop saved — `diagnostics/loadout/<timestamp>_<slot>.png`
- [x] Wired into `LiveActions.run_loadout`/`reapply_loadout_if_due` in `core/tick.py` — two `TemplateLibrary` instances (repo-root for detector anchor templates, `weapon_templates_dir` for per-weapon templates)
- [x] `pytest` runs green (169 tests)

#### Phase 4 — Recovery
- [x] One-frame modal flash does **not** trigger recovery — `_StreakConfirmer` (Phase 2) + regression test
- [x] Leave preferred over Reconnect; 3 attempts then browser fallback; then backoff — `warden/flows/recovery.py` (`RecoverySequence`)
- [x] Frozen-frame, process-gone, and updater triggers tested — Phase 2 global interrupts, re-verified with the fixed confirmers
- [x] Incidents recorded with cause, attempts, method, time lost — `on_incident`/`RecoveryStats` + `TickLoop`'s `time_lost_s` bookkeeping
- [ ] **(Live — needs the user)** killing `RobloxPlayerBeta.exe` mid-match → back in public FFA with verified loadout, no input from user. Can't be done offline; see "Live test needed" below.
- [x] `pytest` runs green (182 tests)

#### Phase 5 — GUI
- [x] All pages in section 7, dashboard updates live from the event bus — `warden/gui/pages/{home,loadout,settings,calibration,history,diagnostics}.py`, `warden/gui/bridge.py` (thread-safe EventBus→Qt signal bridge)
- [x] Presets switch from Home and persist — `AppContext.set_active_preset`/`create_preset`/`delete_preset`
- [x] Hotkeys work while Roblox is focused — `platform/hotkeys.py` (built Phase 1) now wired to Start/Pause/Stop/Screenshot in `MainWindow._setup_hotkeys`; pynput's global hook isn't scoped to a specific app, so it fires regardless of focus (matches intent)
- [x] App never overlaps the Roblox client during a session — `MainWindow._start()` minimizes on Start per `gui.minimize_on_start`
- [x] Summary dialog on stop — `warden/gui/summary_dialog.py`
- [x] Bonus: mini overlay (extras §8.12) — `warden/gui/mini_overlay.py`
- [x] `pytest` runs green (203 tests)

#### Phase 6 — Persistence, tracking, scheduler
- [x] Kill the app mid-session → relaunch → totals intact, Resume offered — `warden/core/persistence.py` (atomic `state.json`, per-preset `ContractProgress`, all-time counters), Home page's resume banner
- [x] Stop-at-target works (test with a 0.01 h target) — `warden/core/scheduler.py` (`Scheduler.check`), `TickLoop._scheduled_stop` (never joins its own thread), tested exactly with a 0.01h target
- [x] Scheduler windows and stop-at-time work; shutdown countdown is cancelable — `in_any_window` (handles midnight wraparound), `ShutdownCountdown`
- [x] `pytest` runs green (239 tests)

#### Phase 7 — Integrations
- [x] Discord webhook embed on interval + alerts — `warden/integrations/discord_webhook.py` (`DiscordWebhook`); screenshot-in-embed not yet attached (see Decisions #39), everything else works
- [x] Optional bot commands restricted to the user's Discord user ID — `warden/integrations/discord_bot.py` (`BotCommands` fully tested; `DiscordBotRunner`'s `discord.py` glue is thin and untested - needs a real gateway connection)
- [x] LAN dashboard reachable from a phone, PIN-gated controls, off by default — `warden/integrations/lan_dashboard.py` (FastAPI app tested via `TestClient`; auto-generates a PIN if left blank rather than ever running unprotected)
- [x] Toasts and sleep prevention working — `warden/integrations/toast.py`, `warden/platform/power.py` (`SleepGuard`, wired into `TickLoop.start/stop`)
- [x] `pytest` runs green (299 tests)

#### Phase 8 — Calibration, unknown gallery, diagnostics, extras
- [x] Calibration wizard can capture a template, sample an HSV range, and show live detections in under a minute per screen — `warden/gui/pages/calibration.py` (real wizard, not the Phase 5 stub): capture live or load an image, drag a selection (`gui/widgets.py`'s `ImageCanvas`), save as template / sample HSV / set ROI / run detection, each one or two clicks
- [x] Unknown gallery → "make template" flow — second tab on the same page, lists `diagnostics/unknown/*.png`, drag a region, pick a detector name, save
- [x] Diagnostics page complete (Phase 5); contract OCR verification and contract queue working — `warden/flows/calibration.py` (`parse_contract_hours`), `core/persistence.py` (`verify_contract_hours`), `core/tick.py` (`_maybe_verify_contract`, opportunistic while safely in LOBBY); `gui/context.py` (`advance_contract_queue`), `core/tick.py` emits `schedule.target_reached`, `MainWindow` advances and restarts
- [x] `pytest` runs green (341 tests)

#### Phase 9 — Packaging & docs
- [x] PyInstaller one-folder build runs — `warden.spec`, `scripts/run_warden.py`. Built and verified on **this** machine (launched the packaged `dist\Warden\Warden.exe`, confirmed the GUI renders correctly, confirmed `--check-config` works); "a clean Windows machine" specifically isn't something I can verify without one - see Decisions #46
- [x] README: install, Tesseract (optional), first-run Calibration walkthrough, public vs share_link warning, Discord webhook/bot/LAN dashboard setup, troubleshooting, the required Roblox ToS/ban/alt-account warning — `README.md`
- [x] No gameplay-specific values hardcoded anywhere — swept `warden/*.py` for weapon names, the game name as a value (vs. docstrings), and numeric gameplay constants; the only one found is `place_id`'s schema default (17625359962), which is HANDOFF §6.6's own documented default and is override-able per-preset, not a hidden hardcoded value
- [x] `pytest` runs green (341 tests) - unchanged this phase (README/spec/packaging don't touch test-covered code)

---

### Post-Phase-9 fixes (user testing, 2026-10-01)

User tried it for real and reported two things, both now fixed and committed:

1. **Calibration preview showed only a cropped corner of the capture**, not the whole
   screen. Root cause: `ImageCanvas` called `QLabel.setPixmap()` without scaling, so Qt
   rendered the capture at native resolution clipped to the small preview widget. Fixed
   by having `ImageCanvas` do its own `paintEvent` drawing (scaled, aspect-preserved)
   instead of relying on QLabel's default pixmap rendering. Verified offscreen with a
   bordered test frame (commit `1eb4add`).
2. **No way to actually capture a weapon's template through the GUI.** The Calibration
   wizard only ever saved *detector* anchor templates (`lobby_play`, `mode_list`, etc.)
   - there was no path to create the `templates/weapons/<slot>/<name>.png` files the real
   loadout transaction looks for, so a preset's loadout (e.g. "Grenade Launcher") could
   never actually be fulfilled no matter what was calibrated. Added a **Weapon templates**
   tab (pick slot + weapon name, capture, drag-select, save) using the same path
   convention `flows/loadout.py` reads from (commit `d1cda95`).

These explain exactly what the user hit: it relaunched Roblox fine (that part needs no
calibration) but never clicked Play/FFA (lobby_play/mode_list/ffa_tile detectors are
still uncalibrated placeholders - expected until Calibration is actually run) and never
selected Grenade Launcher (impossible before the weapon-template gap was fixed - now
possible). **User still needs to actually run Calibration for lobby_play, mode_list,
ffa_tile, health_bar, respawn_prompt, weapon_picker, and now a weapon template for each
loadout slot** - nothing was pre-calibrated on their machine; that was never in scope for
an autonomous build (it inherently requires their own screen).

335 tests passing, 0 failures/errors - confirmed via JUnit XML output
(`--junit-xml`), not dot-counting: pytest's terminal summary line wasn't
reliably showing up in this environment's captured output on every run this
session, so test counts quoted earlier in this file (e.g. "341" at the end of
Phase 9) were dot-count estimates and may be slightly off from the true count.

### Post-Phase-9 fixes, round 2 (user testing, 2026-10-01 evening)

User reported: (a) Warden "keeps rejoining and refreshing the game without ever
opening an FFA and selecting the right weapons", (b) the UI gets cramped and cuts
off text on a small monitor. No `templates/` existed anywhere (repo, `dist`), so
every template detector was permanently blind - that plus the bugs below made the
relaunch loop inevitable.

Root causes and fixes (regression tests: `tests/test_stuck_loop_regressions.py`):
1. **Start always opened `roblox://experiences/start`**, even with Roblox already
   open - Roblox then leaves and rejoins. `StateMachine.start(attach=True)` now takes
   over a running client (goes to LOADING); `TickLoop.start()` checks first.
2. **Every recognition timeout = full relaunch.** LOADING/LOBBY/MODE_SELECT/
   MATCH_END timeouts and UNKNOWN all went to RECOVERING (close + relaunch). Now a
   healthy client gets a *soft reset* (Escape -> LOBBY -> Play) up to
   `recovery.max_soft_resets` (4); then at most `recovery.max_stuck_relaunches` (2)
   relaunches; then Warden **pauses** and emits `session.stuck` naming the step it
   couldn't pass. Hard recovery is still immediate for real failures (process gone,
   disconnect modal, frozen frame, updater, launch timeout, loading with no window).
3. **Play and FFA were clicked once.** Play is re-clicked every
   `timings.lobby_click_interval_s` (4s); the FFA tile every
   `timings.ffa_click_interval_s` (2.5s) while still visible. `ffa_tile` seen in the
   lobby (or mode list / weapon picker / respawn on load) is accepted directly.
4. **Recovery clicked the "Leave" placeholder spot for every cause** - a stray click
   into the lobby. Now only for an actual disconnect; the real cause is passed
   through (`_recovery_cause`) instead of the hardcoded "retry".
5. **Loadout read the screen before the game redrew** (verify ran on the frame
   captured before the click) and the post-respawn reapply loop re-read one stale
   frame 500 times. Loadout now grabs fresh frames, waits `timings.ui_settle_s`
   (0.6s) after each click, and gives verification 3 looks.
6. **Calibration's "Capture live frame" required a running session** - i.e. running
   the very loop that relaunches the game. It now grabs the Roblox window directly.
   Saving a template for a color detector switches it to template matching.
7. **Preflight:** Start shows a "Calibration needed" dialog listing missing
   critical templates (`flows/calibration.py: calibration_gaps`), with Open
   Calibration / Start anyway / Cancel. Unattended contract-queue restarts never
   prompt. Tests auto-answer via `MainWindow._ask_calibration` (conftest).
8. Templates now live in `%LOCALAPPDATA%\Warden\templates` (`paths.templates_home`)
   with the repo/install folder as a read-only fallback, so they survive a rebuild.
9. Global hotkeys were calling Qt widgets from pynput's thread; now marshalled
   through a queued Qt signal. Home's contract progress bar no longer overwrites the
   banked total with session-only hours.

**UI scaling:** `theme.stylesheet(scale)` scales every font size and spacing;
`MainWindow` picks scale from window size (0.72-1.2, 0.04 steps, debounced), opens
at min(design size, 90% of screen), min size 560x400, wraps every page in a scroll
area. New `widgets.FlowLayout`/`flow()`, `ResponsiveRow` (stacks cards when narrow),
`ResponsiveGrid` (counter tiles reflow 6 -> 3x2 -> 2x3). Checked by rendering
offscreen at 600x420, 760x480, 1120x740.

Tests: 353 collected; all pass except 10 that need real Windows APIs (power,
hotkeys, capture) when run in the Linux sandbox - the same set that failed there
before these changes. **Needs a re-run on Windows** and a **PyInstaller rebuild**
(`dist\Warden` is still the old build). Live Roblox verification not possible from
this session (no desktop control) - next real run should start with Calibration.

### Zero-setup round (2026-10-02)

User: "people will think it's too hard to set up - how do I do it without taking
pictures for calibration". Now nothing needs calibrating:
- Every screen on the lobby -> FFA -> match path ships as a template cut from real
  RIVALS frames: lobby_play (Play button), mode_list (menu's red X), ffa_tile ("Free For
  All" title), weapon_picker (the white "current slot" square - visible even when the
  list is scrolled, unlike the "Random" row), respawn_prompt ("Respawn" text), plus the
  colour-based health bar. Verified on every saved frame: hits >=0.97, misses <=0.65.
- `TemplateSpec.ref_height` (shipped = 1440): templates are scaled by
  frame_height/ref_height before matching, so 1080p/1440p/4K all work. Verified on the
  1080p clip and on 1440p frames downscaled to 1080p.
- **Weapons learn themselves**: `SequentialLoadoutTransaction(learn_missing=True)` picks
  the weapons it knows and, for one it doesn't, waits for the player's own click in the
  list (pynput listener + rolling frame buffer in `LiveActions`), saves that row as the
  template, and picks it automatically from then on. Missing weapons are now an "info"
  note, not a Start warning.
- User's local copies of the screen templates removed (backed up) so the shipped ones
  are used; their junk full-screen Assault_Rifle template removed (backed up).

### Clip review (2026-10-02, 18:31 run)

User clip + log: Warden sat in LOADING ~60s in the lobby doing nothing, then only got
going because the uncalibrated `midgame_join` green-button guess fired on the Play
button. Root causes, all fixed and verified against frames from the clip:
- **lobby_play template included the 3D world around the button** (scored 0.72 < 0.78
  as the camera moved). New `flows/calibration.py: tighten_to_button` shrinks a box to
  the solid button inside it on Save; user's template tightened -> 0.97-0.99.
- **mode_list was never calibrated**, so after Play nothing moved to MODE_SELECT.
  Template = RIVALS' red close (X) button on the mode menu, ROI top-right, thr 0.9
  (0.99 on menu frames, <=0.65 elsewhere).
- **ffa_tile template was cut from the wrong screen** (0.67 on the real menu). Now the
  "Free For All" title (0.995 vs <=0.34 elsewhere).
- Mode-menu scrolling used the mode_list box centre (now the X button) -> scroll at
  screen centre instead. `midgame_join` disabled by default. Stronger refocus
  (AttachThreadInput fallback) for "Roblox is not the foreground window".
- These three templates now **ship in the repo** (`templates/`, bundled by warden.spec)
  and default.yaml uses them, so a fresh install works without calibrating them.

### Weapons + movement round (2026-10-02 evening)

User: queueing into FFA works now, but "it doesn't select Grenade Launcher" and "it
doesn't move or shoot anything". Their latest frames (diagnostics/loadout 18:09-18:11)
showed RIVALS' picker: a vertical list of weapon *names* per slot, walked in order
primary -> secondary -> melee -> utility (clicking a weapon advances; the active slot's
square stays centred at the top). No tabs - the "tabs" loadout model could never work.

- **In-match behavior (HANDOFF 6.7) was never implemented** - `IN_MATCH` did nothing.
  New `behaviors/profiles.py: InMatchBehavior` with `idle_nudge`, `patrol`, `fire_loop`,
  new `fight` (walk + shoot), `hide_spot`; abilities; immediate nudge on idle warning.
  Non-blocking walking (key down now, key up on a later tick). State machine hooks:
  `enter_match` / `in_match_tick` / `leave_match` (keys always released on leaving
  IN_MATCH and on Stop). `InputController.fire()` clicks without moving the cursor.
  `GameKeys` gained `slot_keys` (1-4), `move` (WASD), `jump`. Settings: profile hint +
  "Shoot every (s)". Glass Wrap preset now `fight`, shoot every 4s.
- **Sequential picker:** `LoadoutUI.mode: sequential` + `list_roi`;
  `flows/loadout.py: SequentialLoadoutTransaction` (scroll to top, find the name, click,
  verify the list moved on; stops cleanly if a slot can't be picked).
- **Learn my loadout** (`gui/loadout_teacher.py`): on-top panel; user picks their weapons
  in-game normally; a pynput click listener + rolling window capture crops the clicked
  row (`learn_row_template`) as that slot's template. Buttons on Calibration's checklist
  and Weapon templates tab.
- Bug: after a failed transaction, `run_loadout` reset and re-ran it every tick
  (re-clicking the picker). Now one transaction per LOADOUT visit (`begin_loadout`).
- User's own files: `loadout_ui.mode: sequential`, profile `fight`; Grenade Launcher
  (primary) and Grenade (utility) templates pre-made from their frames (cross-match
  scores 0.96 vs <=0.62 for other rows). Secondary/melee still need Learn my loadout.

### Calibration UX round (2026-10-02)

User: "I did it, it just said warning, doesn't work" + "make it take the screenshots
automatically". Their `%LOCALAPPDATA%\Warden` showed: no detector template ever saved;
one weapon template that was the *whole screen* (2502x1440); the "warning" was the
Start-time Calibration-needed dialog (mode_list/ffa_tile missing). Their real frames
also showed RIVALS' health bar is bottom-left (default ROI was bottom-centre) and that
Warden's own window covering the game was being captured as an "unknown screen".

- `vision/capture.py: WindowCapturer` - PrintWindow(PW_CLIENTONLY|PW_RENDERFULLCONTENT)
  capture of the Roblox window itself, screen-grab fallback per frame. Used by the tick
  loop and calibration, so overlapping windows never end up in frames. **Untested on
  real Windows** (sandbox is Linux) - verify on first run; fallback keeps old behavior.
- `gui/guided_capture.py: GuidedCapture` - always-on-top step panel, auto-captures each
  screen after an 8s countdown (Capture now / +10s / Skip / Done), saves to
  `%LOCALAPPDATA%\Warden\calibration\<screen>.png`.
- Calibration page: Setup checklist (○ not captured / ● captured / ✓ done), per-screen
  hint, one-click **Save this screen** (`flows/calibration.py: quick_calibrate` - color
  learning for health_bar, image template + padded ROI for everything else, then an
  immediate test), auto-advance to the next unfinished screen, giant-box guard
  (`selection_problem`, >35% of screen refused) also on weapon templates.
- health_bar pre-calibrated (default.yaml + the user's config.yaml, backup kept in the
  session outputs): ROI [0,0.84,0.31,1], HSV [40,150,170]-[66,255,255]. Hits on their
  in-game frame, not on the Warden-covered frame.
- Open question for the user: how FFA is entered in RIVALS (the lobby shows a
  "To Duels" button and in-world queue pads, not a Play -> mode list flow), and the
  lobby also shows a health bar - so health_bar alone can't tell lobby from match.

### Graph + UI polish + macOS round (2026-10-02)

User: "make there have a graph for the warden main page, and also make sure that the
ui and ux are great... and that its mac compatable, u can make 2 versions if its not
possible to make it mac compatible." One codebase, platform-dispatched at runtime,
rather than two forks - the pieces that touch the OS were already isolated behind
small backend classes/functions, which made this additive rather than a rewrite.

**Session-history graph:**
- `gui/widgets.py: SessionHistoryChart` - hand-drawn (QPainter, like the existing
  `_ProgressBar`/`ImageCanvas`) amber bar chart of in-match minutes per session, reading
  the per-session summaries (`sessions/<timestamp>.json`) `PersistenceManager` already
  wrote every session - no new tracking needed, this data just wasn't surfaced anywhere.
- Home page: new "Recent sessions" card (last 12), refreshed on load and whenever a
  session ends (`MainWindow._refresh_history_views`, called from both `_stop()` and the
  contract-queue auto-advance path - both write a new session file).
- History page was previously a stub ("full history arrives with Phase 6" - Phase 6
  shipped long ago, the page just never got updated): now shows the same chart (last 24)
  plus a sortable-by-recency table of every past session, and refreshes when its nav
  button is clicked. The live current-session timeline table stays, now with an
  empty-state placeholder row instead of a blank table before the first transition.

**UI/UX pass** (subagent-audited, then fixed):
- `QDialog`/`QMessageBox` had no background rule in `theme.stylesheet()`, so every
  dialog (session summary, calibration-needed prompt, preset rename/delete) rendered
  with the OS's native light background next to Warden's dark chrome. Added one.
- `StatusChip`'s "warn" and "accent" tones were the identical color - Paused/Recovering
  looked the same as ordinary Queueing. Warn is now a red-tinted amber.
- `MiniOverlay` never applied the shared stylesheet, so its timer/counts labels had no
  color at all (invisible or OS-default); `dock_outside()` also positioned it using a
  raw physical-pixel rect with no `devicePixelRatioF()` correction, unlike every other
  overlay panel - wrong at any display scaling above 100%, Retina included. Fixed both.
- `CalibrationPage` had no `apply_scale` (unlike every other page), so its two preview
  canvases stayed fixed at 300px tall and forced a scrollbar on a small window instead
  of shrinking with it.
- Font stack was Windows-only (`Segoe UI Variable...`); added macOS system-font
  fallbacks. Diagnostics' log output was hardcoded to `Consolas` (Windows-only
  monospace font); added a cross-platform stack (new `theme.MONOSPACE_STACK`).

**macOS compatibility:**
- The Win32-specific pieces were already behind small seams (`WindowBackend` protocol
  in `platform/window.py`, a swappable `Capturer` protocol in `vision/capture.py`,
  `InputController`'s fallback chain already ending in cross-platform `pynput`) - adding
  a second OS meant filling in the macOS side of those seams, not restructuring.
  `platform/window.py: make_window_backend()` is the one new dispatch point (replaces
  every direct `Win32Windows()` call); `WindowBackend`'s pure logic (`pick_client`,
  `FocusGate`, the state machine, ...) is unchanged and OS-agnostic either way.
- `platform/window_mac.py: MacWindows` (new) - window enumeration/focus via Quartz's
  `CGWindowListCopyWindowInfo` + AppKit's `NSRunningApplication`. Known caveat (can't
  verify without a Mac): Quartz reports a window's full frame including its title bar,
  where Win32's `GetClientRect` (what the rest of Warden assumes) is content-only -
  documented in the module and the README; playing RIVALS fullscreen avoids it entirely.
- `vision/capture.py: WindowCapturer._quartz_capture` - the macOS equivalent of the
  existing `PrintWindow` path: `CGWindowListCreateImage` rasterizes by window id, so
  anything on top of Roblox (Warden itself included) still doesn't end up in the frame.
  Byte-layout logic (`_cgimage_to_bgr`) is split out as a pure function so it's unit
  tested against a fake image object without pyobjc installed.
- Input needed **no new code**: `platform/input.py` already tries SendInput, then
  pydirectinput, then `pynput` per key/click, and both Windows-only methods already
  self-disqualify (`sys.platform` guards) - macOS just falls through to `pynput`, which
  already works there. Same story for global hotkeys (`platform/hotkeys.py`, already
  pure `pynput`).
- `platform/power.py: SleepGuard` - added a macOS path using `caffeinate` (ships with
  the OS; held open for the session's duration, terminated on `release()`, same
  "sticky until cleared" shape as `SetThreadExecutionState`). `core/scheduler.py:
  power_action` - added `pmset sleepnow` / `osascript ... shut down` for the
  post-session sleep/shutdown action.
- `integrations/toast.py` - added `_MacNotification` (shells out to `osascript
  display notification`, ships with the OS, no package needed) alongside the existing
  `winotify` path.
- `paths.py: data_home()` - macOS now gets `~/Library/Application Support/Warden`
  instead of silently falling into the Windows `AppData\Local` branch (which doesn't
  exist on Mac - this was a real bug, not just a missing feature, that nobody had hit
  yet since Warden had never run on Mac before).
- `platform/process.py` - `_startfile` uses `open` (macOS) instead of `os.startfile`
  (Windows-only); `RobloxProcess.pids()` matches `robloxplayer` (macOS process name) or
  `robloxplayerbeta.exe` (Windows) via `window.client_process_names()`.
- Packaging: `warden.spec` now branches on `sys.platform` - same Analysis/hidden-imports
  setup, but wraps the build in a `BUNDLE()` for a real `Warden.app` on macOS instead of
  a bare folder. PyInstaller can't cross-compile (a `.app` has to be built *on* a Mac),
  so also added `Run Warden (Mac).command` / `Rebuild Warden.app (Mac).command` -
  double-click launchers that bootstrap their own `.venv` on first run, so running from
  source needs no terminal commands either.
- Tests: new `tests/test_mac_platform.py` fakes just enough of Quartz/AppKit/`caffeinate`/
  `osascript` (shaped like the real documented APIs) to exercise `MacWindows`, the CGImage
  byte-layout conversion, `SleepGuard`, `power_action`, and the toast/process/paths
  branches on this Linux dev sandbox - the same "test the logic, not the OS" approach
  already used for `test_power.py`'s Win32 mocking. **None of this has run on real macOS
  hardware** - there isn't one in this environment, the same gap the Windows-only pieces
  already had until the user ran them for real. First real Mac run is the actual test;
  the README's new "macOS notes" section covers the Screen Recording/Accessibility
  permissions it'll need.

Full suite: same 40 pre-existing failures as before this round (all either need a real
Windows/macOS OS call or a real X display for `pynput` - this dev sandbox is plain
Linux with neither), zero new ones; 47 new tests added (`tests/test_mac_platform.py`
plus additions to `test_window.py`/`test_gui_pages.py`/`test_main_window_session.py`),
all passing.

### Speed, FFA stuck-loop, and pause/resume round (2026-10-03)

User, after running the previous round for real: weapon picking was "extremely slow",
FFA mode-select "keeps trying to scroll down... gets in a loop", and (reported mid-round,
after the first three fixes shipped) resuming from a pause made it "click the leave
button... leave and keep pressing W". All three diagnosed from the user's own session
logs and saved `unknown/` screenshots rather than guessed at.

**Weapon-pick speed** (`flows/loadout.py`, `config/schema.py`):
- `SequentialLoadoutTransaction` always scrolled a slot's list all the way back to the
  top before searching for the weapon, even when it was already on screen - paying for a
  scroll-to-top plus a `ui_settle_s` wait on every single slot regardless. Added a "peek"
  stage: one match attempt against the current (unscrolled) frame before committing to
  the top-reset; skips the reset entirely in the common case (`_try_click_match`, shared
  with the existing "search" stage).
- `ui_settle_s` (wait after every loadout click/scroll before re-reading the screen)
  default cut 0.6s -> 0.35s - the user's own log showed this fixed wait, not detection,
  was the dominant per-slot cost even when no scrolling was needed at all.
- Not a skins problem as the user suspected (confirmed: still slow with the skin off) -
  this was fixed per-step padding baked into every pick, skin or not.

**FFA mode-select stuck-scroll loop** (`platform/input.py`, `flows/lobby.py`):
- `InputController._allowed()` called `gate.refocus()` on a focus-blocked action but
  discarded the result and dropped the action anyway - even when the refocus (Alt-tap
  + `AttachThreadInput` fallback, `platform/window.py: Win32Windows.focus()`) succeeded
  within its own poll. A successful refocus now sends the action in the same call
  instead of making the caller wait a full extra retry cycle.
- `ModeSelectSearch.tick()` (`flows/lobby.py`) called `scroll_mode_list()`/`click_ffa()`
  and ignored the return value, so a focus-blocked scroll consumed the same finite
  12-attempt budget as a real one - a run of bad focus luck burned the whole budget doing
  nothing, then MODE_SELECT went quiet for up to a minute waiting on the state timeout.
  Both actions now return `bool`; a block retries on a short cooldown instead of
  spending part of the real budget.

**Post-loadout flourish** (`behaviors/humanize.py`, `core/tick.py`): user asked for some
randomized screen movement/fire/jump right after picking weapons so the handoff doesn't
look like a bot going still - explicitly asked to keep this one simple rather than a
full humanization engine. `post_loadout_flourish()`: 2-4 small randomized look nudges,
then a ~50% chance of a brief fire and a ~35% chance of a jump, built from the existing
`Humanizer` primitives and the existing (already focus/e-stop/observe-only-safe) input
methods - no new input primitives. Gated by `automation.post_loadout_flourish` (default
on).

**Pause/resume false-stuck bug** (`core/state_machine.py`), found from a live user report
mid-round: `resume()` refreshed `_entered_at` (via `_go()`) but not `_last_seen`, the
clock behind the global "nothing recognized in `unknown_after` seconds -> stuck" safety
net. `tick()` is a full no-op while paused, so `_last_seen` never advances either, but
real time keeps passing - pausing for longer than `unknown_after` (45s default) made the
very next tick after resuming see the gap and treat it as instant proof the screen was
stuck, escalating (escape -> soft-reset -> relaunch) over nothing. `resume()` now
refreshes `_last_seen` too. Matches the user's "paused it, came back, it clicked leave
and left" report; a disconnect-modal detector false-positive on the FFA map-vote screen
(visible in a saved `unknown/` screenshot - a "Gamemode: Free For All" map picker with no
detector of its own) is suspected as a possible compounding factor but unconfirmed -
flagged in Known Issues below.

**Process notes:**
- This round's project folder was disconnected from the Cowork session partway through;
  the fixes were built and fully tested against a sandbox copy and handed over as a zip
  once the user reconnected the folder (now at `Roblox/Warden` instead of the previous
  `Roblox/Astral macro`).
- Briefly wrote a new `post_loadout_flourish` key into the user's *live* `config.yaml`
  before the matching code had actually landed there - the still-old Warden correctly
  refused to start, reporting it as an unrecognized setting. Reverted immediately once
  reported. Lesson: don't write a new config key into a live config until the code that
  understands it is actually in place, even when the schema change is already written
  and tested elsewhere.
- Secondary (`Handgun`) and melee (`Fists`) aren't bugged - this user's install has
  simply never had them picked once yet (`templates/weapons/` only has `primary/
  Grenade_Launcher.png` and `utility/Grenade.png`). `SequentialLoadoutTransaction`'s
  "zero setup" design (`learn_missing=True`) waits indefinitely on an unlearned slot
  for the player's own click rather than failing - correct behavior, but easy to mistake
  for a hang if you don't know to look for the `calibration.missing` log lines that
  explain it.

Full suite: same 40 pre-existing failures as every round (a real Windows/macOS API or a
real X display is needed, this dev sandbox has neither), zero new ones; 10 new tests
added across `test_input.py`, `test_flows_lobby.py`, `test_humanize.py`, and
`test_stuck_loop_regressions.py`, all passing. Verified identically in both the sandbox
copy and this real project folder after delivery.

### Map-vote detector + further loadout speed, round 3 (2026-10-03)

User reviewed a recorded clip from the round above: the stuck-scroll loop fix held up
("the looping works, everything is good except for those") and mouse movement reads as
smooth/human. Three things remained: FFA still "needed help" choosing/starting at launch,
"trying to join" instead clicked leave and needed a manual join again, and weapon
selection was "a little bit slow" beyond the round-2 fix. Explicit instruction: fix only
these three, get it to a shippable "first prototype" state, before anything else
(including the licensing/distribution write-up requested separately).

**FFA map-vote screen - the actual root cause of both "needed help" reports**
(`flows/calibration.py`, `config/schema.py`, `config/default.yaml`, `core/state_machine.py`,
`core/tick.py`, `tools/replay.py`): a saved `unknown/` screenshot from the user's session
showed RIVALS drops onto a map-vote screen (countdown timer + a row of map tiles, one
always labeled "Random") right after picking FFA - a screen Warden had no detector for at
all. With nothing recognized, it just sat there until the `mode_select` timeout gave up
and soft-reset (escape back to the lobby), which is exactly what the user described as
"it clicked leave and left" and "needed help to click join again." The first "needed help
choosing FFA" report is suspected to be the same mechanism one layer up (a long enough
stall anywhere in mode-select reads the same way from the user's seat), though this part
is circumstantial rather than directly confirmed in the logs.

Fix: new `map_vote` detector (template match against the "Random" tile's shuffle-arrow
icon, cropped and verified from the user's own captured frame - scored 0.9999 against
`match_template()` before being committed), wired through the full stack the same way
`ffa_tile` is - `DETECTOR_NAMES`, `Signals.map_vote`, `GameActions.click_map_vote()`,
a new `_handle_mode_select()` branch that clicks "Random" and treats the screen as
recognized (so it can never itself cause an `unknown_after` stuck-escalation or hit the
`mode_select` soft-reset timeout), the calibration page's guide list, and replay-tool
signal playback. Caveat, stated plainly: this is seeded from one real frame and has not
been verified against a live game session in this environment (no real Roblox access in
this sandbox) - if it stops matching after a resolution change or RIVALS UI update,
recalibrate it from the Calibration page the same way any other detector gets fixed.

**Further loadout speed** (`flows/loadout.py`, `config/schema.py`): primary now picks
almost instantly after round 2's "peek" stage, but the user's own fresh log showed
secondary/melee/utility each still taking a consistent ~2.7s between clicks - more than
`ui_settle_s` alone explains. Added per-slot diagnostic logging (pick duration, verify-check
count, scroll count) to `SequentialLoadoutTransaction` so the next real session's log says
definitively whether this is verify-retry cycling or game-side animation/network latency,
and took one more incremental `ui_settle_s` trim (0.35s -> 0.25s) as a safe next step while
that diagnosis is pending - not claiming this alone fully closes the gap the user flagged.

Full suite: same 40 pre-existing environment-only failures as every prior round, zero new
ones; 4 new tests added to `test_stuck_loop_regressions.py` covering the map-vote click,
its cooldown, that it can't cause a false stuck-escalation, and that the cooldown resets
on each fresh mode-select entry - all passing (69/69 across the touched files). Live
`config.yaml`'s `detectors.map_vote` block was added only after this was confirmed, to
avoid repeating the earlier "unknown setting" startup-crash mistake.

**Known caveat carried forward:** the map-vote fix is the best explanation the evidence
supports, not a live-confirmed one - flag this to the user explicitly and ask for one more
recorded session to confirm before calling FFA fully done.

### GUI redesign (silver/white) + gradients + weapon dropdowns + Fusion fix, round 4 (2026-10-03)

Separate thread from the three bug fixes above: user asked for a full GUI redesign inspired
by a competitor's ("Nova") dashboard - new nav/look, silver/white minimalist theme (an
explicit override of a suggested purple/dark default), then a follow-up pass adding subtle
"futuristic" gradients while keeping the minimalist feel, and replacing the Loadout page's
free-text weapon slots with per-slot dropdowns covering every real RIVALS weapon (transcribed
directly from the user's own 4 in-game weapon-select screenshots - 49 weapons across
Primary/Secondary/Melee/Utility, including locked ones - after an initial web-sourced draft
turned out unreliable and was fully discarded). `theme.py` retheme, `GRADIENT_*` constants,
and `loadout.py`'s `QComboBox` pickers (with "✓ learned" suffixes and a text-lookup fix for
`currentData()` going stale under `setEditText()`) all verified via offscreen screenshots and
a new/updated `test_gui_pages.py` test - 393 passed, same 40-failure baseline, at the time.

**User then reported "there are no gradients in sight" on the real Windows app**, despite
screenshots here showing them correctly. Root cause: Qt defaults to each OS's *native* widget
style (`windowsvista` on Windows, `macos` on Mac), which paints some widgets - QPushButton
especially - with the OS's own theming engine and can silently ignore custom QSS
backgrounds/gradients on them. This sandbox's offscreen platform doesn't use native OS chrome,
so every screenshot taken here looked right regardless of this bug - it was invisible from
this side. Confirmed via a full-codebase grep that no `app.setStyle(...)` call existed
anywhere. Fix: `app.setStyle("Fusion")` added in `warden/__main__.py` right after
`QApplication` construction - Fusion is Qt's own cross-platform style and renders the
stylesheet identically on Windows, Mac, and Linux, which also directly covers this round's
"make sure on Windows AND Mac" requirement. Re-verified: offscreen screenshots unchanged/correct
with `app.style().objectName()` confirmed as `"fusion"`, full suite still 40/40 baseline,
zero regressions.

**Why gradients - and the round-3 FFA/speed fixes - may still look "not there" live:**
`Run Warden.bat` runs straight from source (always current, just needs the app fully quit and
relaunched to pick up new code - it will not hot-reload into an already-running process).
`Rebuild Warden.exe.bat`'s output (`dist\Warden\Warden.exe`), if that's what's actually being
launched day-to-day, does **not** update on its own - it's a frozen snapshot and needs that
rebuild script re-run after every code change, including this entire GUI-redesign round and
round 3's map-vote/loadout-speed fixes. This is the leading explanation for the gradients
report and worth ruling out for the "FFA still needs help" report too, before concluding the
map-vote detector itself is failing live.

**Not done this round (needs fresh data first):** no further `ui_settle_s` trim - round 3's
per-slot diagnostic logging was added specifically to capture real pick-duration/verify-count
data from the *next* live session, and that log hasn't come back yet. Trimming further without
it risks shaving timing margins that are actually load-bearing for verification reliability.
Similarly, no further change to the `map_vote` detector itself - no fresh log or screenshot of
the current "needs help" moment has been reviewed, and round 3 already flagged this fix as
unconfirmed against live play pending exactly that.

**User confirmed the Fusion fix worked** ("yep it does") and asked to drop the FFA/speed
threads for now rather than keep chasing them without fresh data - both left as-is, not
reopened without a new log/screenshot from a live session.

### Phase 1 licensing - "Ship it" (2026-10-03)

User circled back to the Licensing & Distribution Proposal doc (built earlier, left pending
approval) and asked how to actually do it - read as the green light the doc was waiting on.
Built the doc's own recommended starting point: a Gumroad storefront-key check.

**`warden/flows/license.py`** (new): `verify_and_activate()` posts to Gumroad's free
`/v2/licenses/verify` API (real call isolated behind an injectable `verifier`, same pattern as
`discord_webhook.py`'s `poster`, so tests never touch the network) - tries the pass product's
permalink first, falls through to lifetime's if the key belongs to the other one, and accepts
only `uses_count == 1` (Gumroad's own counter, incremented on that one call) - anything higher
means the key already activated somewhere, which is also what happens if the same pass key is
re-entered after it expires, since a pass is single-use by design. `has_access()` is the
every-other-launch path: purely local, no network call - lifetime passes through once
confirmed, pass checks a locally-stored activation timestamp against `pass_hours`. State
(key, tier, activated-at, device-confirmed) persists to `license.yaml` under the data home via
the existing `save_model()` atomic-write helper; a missing or corrupt file just means
unactivated rather than crashing startup.

**`config/schema.py` + `config/default.yaml`**: new `LicenseConfig` (`enabled`, two Gumroad
permalinks, `pass_hours`) on `AppConfig.license` - `enabled: false` by default, on purpose, so
this repo's own dev copy (and anyone building Warden from source) is never gated. Only a
config built for paying customers should flip it on.

**`warden/__main__.py`**: `_ensure_licensed()` runs right after config loads and before the
main window opens - a no-op when `license.enabled` is false, otherwise checks local state first
and only prompts (`QInputDialog`, looped until a valid key or a cancel) when that fails; a
cancelled prompt exits cleanly (code 3) rather than opening the app unlicensed.

**`tests/test_license.py`** (new, 14 tests): fresh-key activation for both tiers, lifetime vs.
pass falling through correctly, a reused/already-active key refused, a network failure
reported rather than raised, disabled licensing always granting access, pass-tier expiry at the
`pass_hours` boundary, and state-file round-trip/corruption handling. Full suite: same 40
pre-existing environment-only failures as every prior round, zero new ones, 14 added and
passing.

**`sales-bot/README.md`**: new step 4 ("Turn on Warden's own license check") - the permalink is
just the last part of the same purchase link already copied in step 2, goes into the
distributed build's `config.yaml` under `license:`, with an explicit warning to leave it
`false` in this repo's own working copy.

**Still manual, by hand, not by Claude** (per the proposal's own risk section and this
engagement's standing policy on credentials/accounts): creating the two actual Gumroad products
and turning on their per-sale unique keys, and re-running `Rebuild Warden.exe.bat` once real
permalinks are filled in so a distributed build actually contains this gate. The proposal doc
itself was updated in place to reflect Phase 1 being built, rather than left saying "pending
approval."

### Mac port (warden-mac-handoff.md): Phases 0-4 built, 2026-10-29

Built in a Cowork session (Linux sandbox, no Mac, no push access), so the work stops
at Phase 4's user step: **push the code and a test tag, then check the workflow.**
Phase 5 (real-Mac test) is untouched.

#### Phase 0: inventory (every Windows-only call, and where macOS stands)

| File:line | Windows-only call | macOS status |
|---|---|---|
| platform/input.py:71-139 | `SendInputMethod` (ctypes `user32.SendInput`, scan codes) | **New:** `platform/input_mac.py` `QuartzMethod` (CGEvent) + `MAC_KEYCODES`; tried first on darwin via `effective_order()` |
| platform/input.py:145-170 | `pydirectinput` | Windows-only, self-disqualifies; pynput stays the Mac fallback |
| platform/window.py:137-280 | `Win32Windows` (EnumWindows, GetClientRect, GetForegroundWindow, SetForegroundWindow + Alt-tap + AttachThreadInput, PostMessage WM_CLOSE) | `platform/window_mac.py` `MacWindows` (existed). **New:** title bar trimmed in windowed mode, display list + Retina scale |
| core/tick.py:338 | **`Win32Windows()` hardcoded in `TickLoop`** | **Bug, fixed:** now `make_window_backend()`. Before this, Start raised OSError on any Mac |
| platform/dpi.py:21-120 | DPI awareness, GetDpiForWindow, EnumDisplayMonitors | Returns "n/a"/1.0 off Windows (unchanged). Mac scale lives in **new** `platform/retina.py` |
| vision/capture.py:69-140 | `PrintWindow` + GDI | `_quartz_capture` (existed). **New:** clips to the content rect; screen-fallback frames also scaled to points |
| platform/power.py:39,71 | `SetThreadExecutionState` | `caffeinate` (existed) |
| core/scheduler.py:129 | `powrprof.SetSuspendState` / `shutdown` | `pmset sleepnow` / osascript (existed) |
| platform/process.py:52 | `os.startfile` | `open` (existed); process `robloxplayer` (existed, unverified) |
| integrations/toast.py:42 | `winotify` | osascript notification (existed) |
| paths.py:34 | `%LOCALAPPDATA%` | `~/Library/Application Support/Warden` (existed) |
| vision/ocr.py:17-18 | Tesseract `C:\Program Files\...` paths | **New:** OCR off by default on Mac (`mac.ocr`) |
| platform/hotkeys.py | pynput `GlobalHotKeys`, F6-F9 | **New:** Mac uses a key-code matcher (`ComboMatcher`) and Ctrl+Shift letter defaults |
| platform/window.py:37 | updater names `robloxplayerlauncher.exe` / `robloxplayerinstaller.exe` | **Gap:** no Mac updater name known; verify in Phase 5 |
| warden.spec | `.exe` one-folder | `BUNDLE()` existed. **New:** icon, `com.heelo1909.warden`, version, plist |

**Interface decision:** the handoff proposed a new `platform/` interface. The repo already
had the seams it describes (`WindowBackend` + `make_window_backend()`, the `InputMethod`
fallback chain, the swappable `Capturer`, `SleepGuard`, `power_action`). Phase 1 therefore
moved nothing; it routed the one place that bypassed a seam (`TickLoop`) through it.
Windows code paths are byte-for-byte the same apart from that line, which still returns
`Win32Windows()` on Windows.

#### Phase 1: platform interface (no Windows behavior change)
- `core/tick.py`: `make_window_backend()` instead of `Win32Windows()`.
- Proof: the full suite has the same 40 environment-only failures as before
  (Linux sandbox: no Win32, no X display for pynput) and **no new ones**. With a fake
  window backend + fake input method injected, all 58 TickLoop/MainWindow/GUI tests
  that normally need Windows pass here too.

#### Phase 2: Mac backend
- `platform/input_mac.py`: `QuartzMethod` (move/drag with delta fields for camera look,
  left/right/middle buttons, keys with held-modifier flags, wheel) and `MAC_KEYCODES`
  (every key in `SCAN_CODES`, unique codes). `InputConfig.methods` accepts `"quartz"`.
- `platform/retina.py`: backing scale, pixel <-> point, display lookup, fullscreen
  detection, title-bar trim. Decision: **frames on Mac are always in points** (Retina
  captures are scaled down), so click math is 1:1 with the window rect. Templates already
  rescale by frame height (`ref_height`), so detection is resolution-independent.
- `platform/window_mac.py`: `displays()`; windowed Roblox gets `mac.title_bar_pt` (28)
  trimmed; fullscreen untouched; unknown display list = nothing trimmed (old behavior).
- `vision/capture.py`: Quartz capture passes the content rect, so the title bar is never
  in the frame; `to_point_size()` used by both capture paths.

#### Phase 3: Mac setup screen and defaults
- `platform/permissions_mac.py`: Accessibility (`AXIsProcessTrusted`, prompt via
  `AXIsProcessTrustedWithOptions`), Screen Recording (`CGPreflightScreenCaptureAccess` /
  `CGRequestScreenCaptureAccess`), Input Monitoring (`IOHIDCheckAccess` /
  `IOHIDRequestAccess`) through ctypes, plus System Settings deep links and
  `relaunch_command()`. Read-only checks; nothing is changed on the user's behalf.
- `gui/pages/mac_setup.py`: one row per permission (one-sentence reason, green tick when
  allowed, Open System Settings, written steps if the link fails), Check again, Reopen
  Warden (shown after Screen Recording is opened/granted, since macOS re-reads it only on
  launch), 2 s auto-recheck. `MainWindow` adds the page on darwin only and opens on it
  while anything is missing (`mac.show_setup_on_launch`).
- First run on a Mac (`config/loader.py`): hotkeys Ctrl+Shift+S/P/X/K, input
  `[quartz, pynput]`, `estimate.ocr_verify: false`. Windows seeding is still a plain copy.
- `platform/macos.py: configure()` applies `mac.title_bar_pt` / `mac.ocr` at startup;
  no-op elsewhere. New `mac:` config section (defaults only, `default.yaml` unchanged).
- Screenshot: not possible here (no Mac); the page is covered by offscreen Qt tests.

#### Phase 4: packaging and CI
- `warden --selftest` (`tools/selftest.py`): imports, bundled config + presets validate,
  templates present, first-run seed in a temp folder; on Mac also Quartz/AppKit, the
  three permission checks (read-only) and `QuartzMethod` construction. Exit 0/1.
- `warden.spec`: `com.heelo1909.warden`, version from `warden/__init__.py`,
  `assets/warden.icns` (original placeholder icon), `LSMinimumSystemVersion` 13.0,
  `NSAppleEventsUsageDescription`. Windows branch untouched (still `icon=None`).
- `scripts/mac/build_dmg.sh`: verify/ad-hoc sign, `hdiutil create -volname "Warden"
  -srcfolder <staging> -ov -format UDZO`, Applications link, `hdiutil verify`, sha256.
- `.github/workflows/mac-release.yml`: on `v*` tags (and manual runs), `macos-15`
  (arm64) + `macos-15-intel` (best-effort), Python 3.12, Mac tests (blocking), full
  suite (report only), selftest from source, PyInstaller, arch check, selftest of the
  built app, DMG, selftest from inside the mounted DMG, then a release job that creates
  the release (pre-release if the tag has a dash) and uploads the DMGs with the built-in
  `GITHUB_TOKEN`. No other secrets.
- Tests: `tests/test_mac_port.py`, 68 tests, all passing here. Suite: 515 tests, same 40
  environment-only failures as before.

#### Known issues / risks for Phase 5
- **Corner emergency stop isn't wired on either OS.** `CornerWatch` exists in
  `platform/input.py` but nothing starts it, even though the README describes it. The
  stop hotkey works. Not changed here (it would change Windows behavior); decide first.
- `CGWindowListCreateImage` is marked obsolete in the macOS 15 SDK. It still exists at
  runtime and `mss` uses it too, but there are reports of macOS 26 returning only the
  desktop. If captures come back blank on a real Mac, the fix is ScreenCaptureKit.
- Hotkeys on Mac are new code (`ComboMatcher`); verify they fire with Roblox focused.
- Roblox's Mac process name (`RobloxPlayer`) and updater name are unverified.
- Title bar height (28 pt) is the standard macOS value; adjust `mac.title_bar_pt` if
  clicks are off by a strip in windowed mode.
- Qt needs macOS 13+ in current releases, hence the 13.0 minimum.
- Full-suite tests that assume Windows process names will fail on the Mac runner (report
  only); the Mac-specific tests block the build.
- Every update has a new ad-hoc signature, so macOS may ask for the permissions again.
- The Windows `.bat` launchers had been deleted in the uncommitted working tree; they were
  restored from git (`Run Warden.bat`, `Rebuild Warden.exe.bat`). Delete them again if that
  was intended.

### ALL PHASES COMPLETE (0 through 9)

What's left, for the user:
1. **Run Calibration** (Phase 8's wizard) against your own screen - every detector
   ROI/HSV range, loadout-picker layout, and recovery button position shipped as an
   uncalibrated placeholder, by design (see Decisions throughout). Nothing will
   reliably detect or click anything real until this is done.
2. **The one live test that was never run** (flagged under Phase 4, still true):
   killing `RobloxPlayerBeta.exe` mid-match and confirming Warden recovers back into
   public FFA unattended. Do this on an alt account per the README's warning.
3. Discord/LAN dashboard setup, if wanted - both optional, both off by default,
   both documented in the README.

---

### Live test needed (stopping point for Phase 4's last item)

Everything in Phase 4 is built and covered by offline tests (`tests/test_flows_recovery.py`,
`tests/test_recovery_integration.py`), **except** the one DoD item that can only be verified
with the real game running, per HANDOFF §11 ("Live tests only when I explicitly start one,
preferably on an alt account"). I did not run this — it needs you.

**What to run, when you're ready (preferably on an alt account):**
1. Launch RIVALS into a public FFA match through Warden (once the GUI exists in Phase 5) or
   drive `warden.core.tick.TickLoop` directly against a real Roblox session.
2. While in a match, kill `RobloxPlayerBeta.exe` from Task Manager.
3. Expected: Warden detects the process is gone → `RECOVERING` → closes any remnants → relaunches
   → walks back through `LOBBY → MODE_SELECT → FFA` → loadout reapplies → `IN_MATCH`, all without
   you touching the keyboard or mouse.

Known gap going into this: `recovery_ui.leave_pos`/`reconnect_pos` and all the detector
ROIs/colors in `config/default.yaml` are **uncalibrated placeholders** (Phase 8 Calibration
hasn't been built yet) — a live run this early will very likely fail to find the real buttons.
I'm continuing through Phases 5-9 regardless (GUI, persistence, integrations, calibration,
packaging) since most of that doesn't need a live Roblox client either, and Calibration
(Phase 8) is what makes a real live run meaningful. Flagging this now rather than waiting,
since you may want to try it earlier.

### What exists

- `warden/config/schema.py` — `AppConfig` (config.yaml) + `Preset` (presets/*.yaml). `extra="forbid"` so YAML typos are errors.
- `warden/config/loader.py` — YAML load, `ConfigError` with one readable line per problem (`detectors.lobby_play.roi: x1 (0.7) must be less than x2 (0.3)`), atomic save, first-run seeding into `%LOCALAPPDATA%\Warden\`.
- `warden/core/events.py` — thread-safe `EventBus` (levels debug/info/success/warn/error, topic-prefix filters, history ring, subscriber isolation).
- `warden/core/logs.py` — rotating per-run log file in `%LOCALAPPDATA%\Warden\logs\`, bus→log bridge, keeps last 30 logs.
- `warden/gui/theme.py`, `warden/gui/main_window.py` — themed sidebar shell with 6 placeholder pages.
- `config/default.yaml`, `config/presets/{default,glass_wrap,random}.yaml`.
- `python -m warden --check-config [PATH]` validates and exits (0 ok / 2 invalid).

### Decisions

1. **Python 3.14** (only version installed; 3.12 not present). All deps install and run on it. `requires-python >= 3.12`. **User confirmed 2026-10-01: stay on newest (3.14).**
12. **2026-10-01:** user said "continue all of the stages and phases without me" — building straight through per HANDOFF §0's original instruction (stop only at a live-test DoD item, real credentials needed, or a genuine blocker). Per-phase sign-off is no longer required.
13. `pydirectinput`/`pywin32` added as real (optional) deps now that Phase 1 uses them; fallback chain in `InputController` already tolerates either being absent.
14. `warden/geometry.py` holds `Rect` (shared by platform + vision) — not in HANDOFF's layout but needed as a common module both depend on.
15. Frozen-frame detector uses a mean-threshold perceptual hash; flat/solid-colour frames are a degenerate case for it (every pixel equals the mean), which only matters for synthetic test frames, not real captures.
16. **State machine design (Phase 2):** a state's own handler only runs starting the tick *after* some other handler transitioned into it (transitions and the new state's first action are never in the same tick) — matches how LOBBY's "click once on entry" and DEAD's first respawn press behave, and is exercised directly by the tests rather than worked around.
17. UNKNOWN and DISCONNECTED are one-tick waypoints, not stable states: UNKNOWN always auto-advances to RECOVERING on the next tick (after saving the frame + pressing Escape), DISCONNECTED auto-advances to RECOVERING the same tick it's confirmed. Both still appear in the transition log for GUI/History visibility.
18. `RECOVERING`'s default behavior (`NullActions.handle_recovering` / `FakeActions` in tests) is to **stay in RECOVERING** (keep retrying) rather than guess a next state — Phase 4 provides the real backoff/leave/relaunch/browser-fallback sequence that decides when to hand off to LAUNCHING.
19. `warden/core/tick.py` wires Phase 1 (window/input/vision) + Phase 2 (state machine) into a real loop (`TickLoop` + `LiveActions`). `run_loadout`/`reapply_loadout_if_due`/`handle_recovering` are clearly-logged stand-ins (accept current equipment / no reapply / simple close-and-relaunch) until Phases 3 and 4 replace them — no other code needs to change when they do, since they're just `GameActions` methods.
20. Replay/state-machine tests jump a fresh `StateMachine` directly into the state under test (bypassing `_go`'s entry side effects, which are already at their reset position on a fresh machine) rather than re-deriving the full LAUNCHING→LOADING→LOBBY boot sequence for every single transition test. One true end-to-end boot test (`test_full_happy_path_launch_to_in_match`) covers the real sequence.
21. **Loadout transaction (Phase 3)** is a step-wise sub-flow (like `RespawnFlow`/`ModeSelectSearch`): `run_loadout()` does one small step per call (check already-equipped → click tab → search/scroll → click tile → verify) and is called once per tick while `weapon_picker` is visible, so it's naturally interruptible by the state machine's own abort checks rather than blocking through a multi-second transaction. A slot already showing the target weapon is never re-clicked (cheap to call repeatedly / on retry).
22. Weapon templates live under `<weapon_templates_dir>/<slot>/<sanitized weapon name>.png` (`weapon_template_path()` in `flows/loadout.py`), in a **separate** `TemplateLibrary` from the one detector anchor templates use (whose paths like `templates/mode_list.png` are relative to the repo root, not the weapons subfolder) — `core/tick.py` builds both.
23. `loadout_ui` config section (tab position, grid/verify ROIs per slot) is uncalibrated placeholders, same as the detectors — real values come from the Calibration wizard (Phase 8).
24. **Recovery (Phase 4)** is a step-wise flow like the others (`RecoverySequence` in `flows/recovery.py`): steps 1-3 of §6.5 (Leave → wait → close if still running → relaunch) are its job; step 4 ("two independent confirmations we're in a match") was already built in Phase 2 (`StateMachine`'s `_GapConfirmer`) and stays there — the flow only ever has to hand off to `State.LAUNCHING` once a relaunch is kicked off, and the ordinary LAUNCHING→LOADING→LOBBY→MODE_SELECT→FFA path (also already built) covers the rest. Attempt count and backoff cycles persist **across separate RECOVERING re-entries within the same ongoing incident** (e.g. LAUNCHING times out again) and reset only when `on_recovered()` fires (state machine reaches IN_MATCH, by any path).
25. **Bug fixed in Phase 2's global interrupts** while building Phase 4: the `roblox_updating` and `disconnect_modal` checks re-fired every single tick the underlying signal stayed true, re-entering RECOVERING (and re-emitting incidents) forever and starving the actual RECOVERING-handling branch below them of ever running. Fixed by guarding both to only fire when not already RECOVERING/DISCONNECTED, and by resetting the disconnect streak confirmer whenever IN_MATCH is reached (by any path) so a stale mid-count streak from a resolved incident can't instantly re-trigger on a future single frame. Caught by `tests/test_recovery_integration.py`, a true end-to-end test (StateMachine + a real RecoverySequence, not mocked) — worth keeping this kind of test per phase going forward, not just unit tests against mocked collaborators.
26. Added `GameActions.on_recovered()` (no-op in `NullActions`) so "the incident is over" is a first-class notification from the state machine itself (fired from `_go` on reaching IN_MATCH) rather than something `TickLoop` had to infer by watching transitions from outside — `LiveActions.on_recovered` calls `self.recovery.full_reset()`.
27. `recovery_ui` config (leave/reconnect button positions) is another uncalibrated placeholder pair, same pattern as `loadout_ui`/detectors.
28. **GUI (Phase 5)** uses a thread-safe `BusBridge` (Qt signal wrapping every `EventBus` event) since `TickLoop` fires events from its own background thread, never the GUI thread. One shared mutable `AppContext` (config + bus + lazily-(re)built `TickLoop`) is passed to every page; `ensure_tick_loop()` rebuilds it fresh on every Start so Settings changes take effect without restarting the app. `History` and `Calibration` are intentionally partial for this phase (full cross-session history needs Phase 6 persistence; the full calibration wizard is Phase 8) - each explains what's missing and does something useful in the meantime (live session timeline; a checklist of templates still needed).
29. **Safety incident during Phase 5, corrected (see `warden-testing-safety` memory):** a manual smoke test briefly ran the real tick loop while the user's actual Roblox client was open and focused on this machine - `observe_only` defaults to `false` (correctly, for the shipped product) and the focus gate only blocks input when Roblox *isn't* foreground, which it was. A read-only screenshot immediately after showed the lobby untouched; flagged to the user. Every test that builds a real `TickLoop` now forces `observe_only = True` (the one exception being a test that proves the focus-gate-blocks path specifically, which is safe without it because `FocusGate.set_target()` is never called there, so `hwnd` stays 0 and `is_focused()` is unconditionally False). Going forward: no more ad-hoc live smoke tests of `TickLoop.start()`/`MainWindow._start()` - rely on the offline pytest suite.
30. **Separately found while adding GUI tests:** two test files (`test_gui_pages.py`, `test_gui_smoke.py`) were writing settings changes back into the real checked-in `config/default.yaml` and `config/presets/random.yaml` instead of a temp copy, because `AppContext.save_*()` writes to whatever `app_path`/`preset_path` point at, and those tests pointed straight at `bundled_config`. Reverted the accidental changes (`git checkout -- config/`) and fixed both tests to copy `config/` into `tmp_path` first. Worth remembering for any future test that builds an `AppContext` from `bundled_config`.
31. **Persistence (Phase 6)** tracks only a *delta* since the last flush (`PersistenceManager._apply_delta`), not an absolute snapshot - `maybe_flush`/`end_session` can be called as often as convenient (every 30s per `timings.state_save_s`, or on-demand) without ever double-counting. `TickLoop._bookkeep()` is deliberately split out of `tick_once()` so Phase 6 logic (credited-time tracking, flush, scheduler check) is testable without a real capture/detect pipeline - tests drive it directly with a `result_state` and `now`, no Roblox or even a real window needed.
32. **`_scheduled_stop` vs `stop()`:** a scheduler-triggered stop happens *from inside the tick thread itself* (called from `_bookkeep()`, called from `tick_once()`, called from the thread `start()` spawns) - it must never call `self._thread.join()` (a thread joining itself deadlocks). Only the externally-called `stop()` joins the thread; both funnel into the same `_finalize_session()` for persistence, guarded by `_session_active` so it's safe to call either one first.
33. **`estimate.count_lobby_time`** (HANDOFF §12, "unconfirmed whether lobby time counts toward the contract") governs what counts as credited time: off (default) = only `IN_MATCH`; on = any state except `IDLE`/`PAUSED`/`STOPPED`/`LAUNCHING` (waiting for the client to even open never counts, regardless of the toggle).
34. Home's "Resume last session" banner is informational, not a distinct code path - the banked hours for a preset are already safe (persisted per-preset in `state.json` regardless of how the last session ended), so its "Resume" button is just the ordinary Start button under a different label. It shows only when `last_session_incomplete` is true *and* matches the currently active preset.
35. Scheduler `windows` (time-of-day run windows) are YAML/Settings-file-editable only for now - no dedicated add/remove list widget on the Settings page. The underlying logic (`in_any_window`, including midnight wraparound) is built and tested; a GUI list editor is a small, low-risk addition if wanted later.
36. Installed the optional `integrations` extra for real (`fastapi`, `uvicorn`, `discord.py`, `winotify`, `requests`, plus `httpx` for FastAPI's `TestClient`) so Phase 7 could be built and tested properly rather than left as an untestable stub - already listed in `pyproject.toml`'s `integrations` extra, nothing new to add there.
37. **Integrations architecture:** each one takes an injectable collaborator (`DiscordWebhook.poster`, `ToastNotifier.backend_factory`) so nothing in the test suite ever makes a real HTTP call, shows a real toast, or needs a real Discord/fastapi dependency to exercise the logic - only `warden/integrations/lan_dashboard.py`'s `create_app()` is tested via FastAPI's `TestClient` (no real socket). Every integration is gated by its own `enabled` flag (off by default except toasts) and degrades to a safe no-op if its optional dependency isn't installed (checked when `TickLoop` constructs it, not deferred to first use, so a missing `fastapi`/`discord.py` never crashes startup - just logs a warning and leaves that one integration off).
38. **LAN dashboard safety:** `LanDashboardServer.__init__` refuses (raises `ValueError`, caught by `TickLoop`) to bind anywhere that isn't a private/loopback address (`is_lan_only_bind`), and `ensure_pin()` auto-generates a 6-digit PIN rather than ever running the control endpoints (`/api/pause`, `/api/resume`, `/api/stop`) unprotected - `/api/status` alone is readable without a PIN (matches "live stats + thumbnail" being the point of a phone dashboard).
39. **Known gap:** the webhook's periodic status embed doesn't attach a screenshot yet (`DiscordWebhookConfig.include_screenshot` exists in the schema but isn't read) - `TickLoop` has the last captured frame available (`self.actions.detections.get("_last_frame")`) and `discord_webhook.py`'s `_send`/`_default_poster` would need a multipart upload path (`requests`' `files=` parameter) instead of the current pure-JSON POST. Small, well-scoped follow-up; flagging rather than rushing it in.
40. Discord bot command dispatch (`BotCommands`) is fully tested; the `discord.py` client/slash-command glue around it (`DiscordBotRunner.build_client`/`run`) is deliberately thin and untested, since exercising it needs a real bot token and gateway connection - not something to fake convincingly, and the actual decision logic it delegates to is where the real risk of bugs lives anyway.
41. **Calibration (Phase 8)** backend logic lives in `flows/calibration.py` (pure, Qt-free: ROI/HSV helpers, unknown-gallery template-making, contract-hours text parsing) with a thin GUI page on top, same split as every other flow. `gui/widgets.py`'s `ImageCanvas` tracks the drag-selection in *original frame pixels* (not display pixels), so it stays correct regardless of how the captured frame is scaled to fit the widget.
42. **Contract OCR verification** overwrites (not adds to) the banked total for that preset the moment a parseable readout is seen while safely in LOBBY (`PersistenceManager.verify_contract_hours`) - the game's own counter is taken as authoritative over the estimate. It resets both `PersistenceManager`'s internal delta baseline and `TickLoop._in_match_seconds` to 0 together (the docstring on `verify_contract_hours` spells out why both must move together, or the next flush would re-add the pre-verification session time on top).
43. **Contract queue** ownership split: `TickLoop` only knows its own single preset, so it just emits `schedule.target_reached` (distinct from the generic `schedule.stop`) when the stop reason is specifically target-reached - not for a clock-time or run-window stop. `AppContext.advance_contract_queue()` (new) decides whether to actually continue, and `MainWindow._handle_target_reached` restarts the session for the next preset if so, cancelling the just-started shutdown/sleep countdown (`TickLoop.cancel_shutdown_countdown()`) since the point of a queue is to keep going, not power off.
44. A GUI test crashed the test process **silently** (no Python traceback, just a bare process exit) the first time `ImageCanvas` (a `QWidget` subclass) was instantiated in a test that didn't request the module-scoped `qapp` fixture - constructing any `QWidget` before a `QApplication` exists is a native-level crash in Qt, not a catchable Python exception. Every GUI test file already threads a `qapp` fixture through for this reason; the lesson is to double check *every* test that touches a widget requests it, not just the file's "main" ones.
45. **Another real-file-write incident, same family as Phase 5's (see `warden-testing-safety` memory):** `CalibrationPage`'s template-saving paths use `TemplateLibrary(paths.repo_root())` - correct for the real app (templates should live alongside the installed code), but `paths.repo_root()` is **not** affected by the `WARDEN_HOME` env var or a temp config copy, so a GUI test exercising a save path would write into the actual checked-in `templates/` folder. Found a stray `templates/lobby_play.png` had been created this way; deleted it (confirmed via `git status` it was newly added, not prior content) and fixed the root cause: `CalibrationPage.__init__` now takes an injectable `templates_root` parameter (defaults to `paths.repo_root()` for real use), and every calibration GUI test passes `templates_root=tmp_path`. General lesson carried forward: any path built from `paths.repo_root()` (as opposed to `paths.data_home()`, which `WARDEN_HOME` already isolates) needs its own explicit test-isolation story - check for this pattern before writing tests for anything new that touches the repo's own `templates/`/`config/` folders.
46. **Packaging (Phase 9):** `warden.spec` builds a one-folder PyInstaller app from `scripts/run_warden.py` (a one-line entry point - PyInstaller needs an actual script file, `python -m warden` doesn't translate directly). Hidden imports listed explicitly for `discord`/`fastapi`/`uvicorn`/`winotify`/`pydirectinput`/`pytesseract`/`pywin32`, since Phase 7's integrations import them lazily inside functions (gracefully, when enabled) rather than at module load time, so PyInstaller's static analysis can't find them on its own. Built and ran it for real on this machine (`pyinstaller warden.spec --clean`, then launched `dist\Warden\Warden.exe`, confirmed the GUI renders and `--check-config` works) - "runs on a **clean** Windows machine" specifically can't be verified without one; the build and a same-machine run are the closest offline proxy. No icon set yet (`icon=None` in the spec) - HANDOFF §1 calls for an original or Lucide/MIT icon with its LICENSE file once one is chosen; left as a deliberate gap rather than picking something without the user's input.
47. **README.md** covers install, optional Tesseract, the Calibration walkthrough, the public-vs-share_link warning, Discord webhook/bot/LAN dashboard setup, troubleshooting, and the required Roblox ToS/ban/alt-account warning (HANDOFF §9's exact ask). The Discord bot's token/allowed-user-id aren't yet exposed on the Settings page (Decision #35's `discord_bot` fields) - the README says to edit `config.yaml` directly for now; a small, low-risk Settings addition if wanted later, same category as the scheduler-windows gap.
48. Final sweep for hardcoded gameplay-specific values (the last Phase 9 DoD item): nothing found beyond `AppConfig`'s `place_id` schema default, which is HANDOFF §6.6's own documented default value and is override-able per-preset - not a value hidden from configuration, just a sensible fallback for an omitted field, same as any other schema default in the codebase.
2. Virtualenv at `.venv/` (git-ignored). Run with `.venv\Scripts\python -m warden`.
3. Config split: **app config** (machine settings, detectors) vs **preset** (per-contract). Effective config = app + `active_preset`. Matches the preset example in HANDOFF §9.
4. Config module lives at `warden/config/` (not in HANDOFF's layout; needed somewhere).
5. `WARDEN_HOME` env var overrides the data folder; tests always use a temp dir.
6. Added a `SUCCESS` level (25) between INFO and WARN to match the bus levels.
7. Detector HSV/ROI defaults are **uncalibrated placeholders**; templates referenced (`templates/*.png`) don't exist until Calibration (Phase 8). Added an `idle_warning` detector for §6.7 idle-kick defense.
8. Hue ranges may wrap (lower H > upper H) for red-ish colours; S/V must be ordered.
9. `Random` preset uses `loadout.random: true` + `owned_weapons` pool in config.yaml.
10. `estimate.count_lobby_time: false` by default (unconfirmed, HANDOFF §12).
11. Invalid config at GUI start → modal error with the same readable text, exit code 2.

### Known issues

- GUI smoke tests run offscreen (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`).
- Session timer / in-match-% / contract progress on Home are in-memory only (reset on app
  restart) - durable, cross-restart versions are Phase 6's job (`state.json`).
- ~~History page only shows the current session's live transitions, not past sessions~~
  fixed in the Graph + UI polish + macOS round - it now reads `sessions/<timestamp>.json`
  directly. ~~Calibration page lists missing templates but isn't the real capture/
  sample/live-overlay wizard yet~~ - also done (see the Calibration UX round); this
  whole bullet was stale, left over from Phase 5 and never updated.
- Settings page's hotkey fields are free-text key names, not an actual "press a key to bind"
  capture widget - functional but not polished; fine to revisit as a later nicety.
- **macOS support is new and unverified on real hardware** (this dev environment has no
  Mac) - the window/capture/input/power/notification backends are built against
  documented Quartz/AppKit/`caffeinate`/`osascript` behavior and covered by tests that
  fake those APIs, but the first real run on an actual Mac is the real test. Most likely
  rough edges: the window-bounds-includes-title-bar caveat (`platform/window_mac.py`'s
  docstring), and whatever System Settings permission prompts actually look like in
  practice.
- ~~No detector for RIVALS' FFA map-vote screen~~ fixed in the map-vote detector round
  (round 3, 2026-10-03) - a `map_vote` detector now clicks "Random" and the screen counts
  as recognized. **Not yet live-verified** (seeded from one captured frame, no real Roblox
  access in this dev sandbox) - watch the next real session's log to confirm it actually
  matches in play, and recalibrate from the Calibration page if it doesn't.

### Exact next step

**Mac port:** the user pushes this code and the tag `v0.0.1-mactest`, then checks the
Actions run and the Releases page (Phase 4 user test in warden-mac-handoff.md). On a
green run, Phase 5: the real-Mac checklist on a personally owned Mac.

Windows (unchanged from before):

**None - all 10 phases are built.** The only things left are the two user-facing items
listed just above ("ALL PHASES COMPLETE"): run Calibration against your own screen, then
try the one live test (killing Roblox mid-match) on an alt account. If picking this back
up after a context reset with nothing further requested, there's nothing to build -
re-read this file to get oriented, then wait for direction.
