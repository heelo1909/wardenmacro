# PROGRESS.md

## Current phase

**Phase 4 — Recovery: COMPLETE.**
Running autonomously through all phases per HANDOFF.md section 0's original
instruction (user said "continue all phases without me", away at squash),
stopping only for a live-Roblox-test DoD item or a genuine blocker.
Next: Phase 5 — GUI.
The first genuinely live-only DoD item is in this phase ("killing
RobloxPlayerBeta.exe mid-match -> back in public FFA, no input from user") -
marked not-done below since it needs the real game; everything else in
Phase 4 is built and tested offline.

## Phase checklist

### Phase 0 — Scaffold
- [x] Repo, `requirements.txt` / `pyproject.toml`, pydantic config schema, logging, event bus, `PROGRESS.md`
- [x] `python -m warden` opens an empty themed window
- [x] Default config loads and validates; invalid config shows a readable error
- [x] `pytest` runs green (21 tests)

### Phase 1 — Platform & vision core
- [x] Window finder ignores browser tabs (mocked window lists) — `warden/platform/window.py`
- [x] Focus-confirm gate — `FocusGate` in same file
- [x] DPI-aware capture; fraction ↔ pixel tested at 100/125/150% — `warden/geometry.py`, `warden/platform/dpi.py`
- [x] HSV blob detector + multi-scale template matcher on synthetic frames — `warden/vision/color.py`, `warden/vision/templates.py`
- [x] Input wrapper, fallback chain, jiggle-then-click, emergency stop — `warden/platform/input.py`
- [x] Observe-only mode, frame recorder, `tools/diagnostics_cli.py` — `warden/tools/recorder.py`, `warden/tools/diagnostics_cli.py`
- [x] `pytest` runs green (87 tests)

### Phase 2 — State machine, lobby, FFA, respawn, match end
- [x] All 15 states in §6.1 implemented with timeouts and fallbacks — `warden/core/state_machine.py`
- [x] Replay tests over synthetic frame sequences cover every transition, incl. early-abort of FFA search + mid-game join — `tests/test_state_machine.py` (71 cases), `warden/tools/replay.py` + `tests/test_replay.py`
- [x] Respawn double-press logic tested; Respawns counter increments — `warden/flows/respawn.py`, `tests/test_flows_respawn.py`
- [x] Bonus: wired Phase 1 + Phase 2 into a real drivable loop — `warden/core/tick.py` (`LiveActions` + `TickLoop`), runs safely with no Roblox present
- [x] `pytest` runs green (156 tests)

### Phase 3 — Loadout transactions
- [x] 4/4 verified commit path — `warden/flows/loadout.py` (`LoadoutTransaction`), `tests/test_flows_loadout.py` (13 cases)
- [x] Single-slot mismatch → corrected → Loadout fixes +1 — `LoadoutResult.fixes`
- [x] Abort on death mid-transaction, retried at next safe window — already handled by `_handle_loadout` in Phase 2 (`run_loadout()` is a single idempotent step the state machine can abandon any tick; already-equipped slots are skipped on retry, so nothing is redone)
- [x] Missing weapon tile never triggers a guessed click; diagnostic crop saved — `diagnostics/loadout/<timestamp>_<slot>.png`
- [x] Wired into `LiveActions.run_loadout`/`reapply_loadout_if_due` in `core/tick.py` — two `TemplateLibrary` instances (repo-root for detector anchor templates, `weapon_templates_dir` for per-weapon templates)
- [x] `pytest` runs green (169 tests)

### Phase 4 — Recovery
- [x] One-frame modal flash does **not** trigger recovery — `_StreakConfirmer` (Phase 2) + regression test
- [x] Leave preferred over Reconnect; 3 attempts then browser fallback; then backoff — `warden/flows/recovery.py` (`RecoverySequence`)
- [x] Frozen-frame, process-gone, and updater triggers tested — Phase 2 global interrupts, re-verified with the fixed confirmers
- [x] Incidents recorded with cause, attempts, method, time lost — `on_incident`/`RecoveryStats` + `TickLoop`'s `time_lost_s` bookkeeping
- [ ] **(Live — needs the user)** killing `RobloxPlayerBeta.exe` mid-match → back in public FFA with verified loadout, no input from user. Can't be done offline; see "Live test needed" below.
- [x] `pytest` runs green (182 tests)

### Phase 5 — GUI
- [ ] All pages in section 7, dashboard updates live from the event bus
- [ ] Presets switch from Home and persist
- [ ] Hotkeys work while Roblox is focused
- [ ] App never overlaps the Roblox client during a session
- [ ] Summary dialog on stop

---

## Live test needed (stopping point for Phase 4's last item)

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

## What exists

- `warden/config/schema.py` — `AppConfig` (config.yaml) + `Preset` (presets/*.yaml). `extra="forbid"` so YAML typos are errors.
- `warden/config/loader.py` — YAML load, `ConfigError` with one readable line per problem (`detectors.lobby_play.roi: x1 (0.7) must be less than x2 (0.3)`), atomic save, first-run seeding into `%LOCALAPPDATA%\Warden\`.
- `warden/core/events.py` — thread-safe `EventBus` (levels debug/info/success/warn/error, topic-prefix filters, history ring, subscriber isolation).
- `warden/core/logs.py` — rotating per-run log file in `%LOCALAPPDATA%\Warden\logs\`, bus→log bridge, keeps last 30 logs.
- `warden/gui/theme.py`, `warden/gui/main_window.py` — themed sidebar shell with 6 placeholder pages.
- `config/default.yaml`, `config/presets/{default,glass_wrap,random}.yaml`.
- `python -m warden --check-config [PATH]` validates and exits (0 ok / 2 invalid).

## Decisions

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

## Known issues

- None yet. GUI smoke test runs offscreen (`QT_QPA_PLATFORM=offscreen`).

## Exact next step

Start Phase 5: the GUI pages in HANDOFF §7 (`gui/pages/{home,loadout,settings,
calibration,history,diagnostics}.py`), wired to `core/tick.py`'s `TickLoop` and the
event bus (which already carries every state transition, detection, incident, and
`loadout`/`recovery` event from Phases 2-4). Home's counters (Respawns, Reconnects,
Re-queues, Loadout fixes) read straight off `StateMachine.counters`; the session
timer and contract-progress estimate are new (Phase 6 persistence will make them
durable across restarts, but Home can show a live in-memory version now). Hotkeys
(`platform/hotkeys.py`, built in Phase 1 but not yet wired to anything) bind
Start/Pause/Stop/Screenshot to `TickLoop.start/pause/resume/stop`. Keep the main
window off the Roblox client rect on Start (HANDOFF §6.2).
