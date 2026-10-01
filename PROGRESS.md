# PROGRESS.md

## Current phase

**Phase 2 — State machine, lobby, FFA, respawn, match end: COMPLETE.**
Running autonomously through all phases per HANDOFF.md section 0's original
instruction (user said "continue all phases without me", away at squash),
stopping only for a live-Roblox-test DoD item or a genuine blocker.
Next: Phase 3 — Loadout transactions.

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
- [ ] 4/4 verified commit path
- [ ] Single-slot mismatch → corrected → Loadout fixes +1
- [ ] Abort on death mid-transaction, retried at next safe window
- [ ] Missing weapon tile never triggers a guessed click; diagnostic crop saved

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

Start Phase 3: `warden/flows/loadout.py` — the verified 4-slot loadout transaction
(HANDOFF §6.3). Needs: per-slot weapon template matching inside the picker, open
picker → select slot → locate tile → click → verify slot shows it → next slot,
commit only on 4/4 verified, abort on death/picker-closed/disconnect, scroll/search
inside the picker before giving up on a slot (never guess a grid position), save a
diagnostic crop to `diagnostics/loadout/<timestamp>_<slot>.png` on any verification
failure, and a `loadout_fixes` counter for corrected slots. Then wire it into
`LiveActions.run_loadout`/`reapply_loadout_if_due` in `warden/core/tick.py`,
replacing the Phase 2 stand-ins (no change needed to `state_machine.py` itself).
