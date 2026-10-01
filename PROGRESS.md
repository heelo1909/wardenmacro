# PROGRESS.md

## Current phase

**Phase 8 — Calibration, unknown gallery, diagnostics, extras: COMPLETE.**
Running autonomously through all phases per HANDOFF.md section 0's original
instruction (user said "continue all phases without me", away at squash),
stopping only for a live-Roblox-test DoD item or a genuine blocker.
Next: Phase 9 — Packaging & docs (the last one).

**⚠️ Incident during Phase 5 (2026-10-01), already handled - see "Decisions"
#29/#30 and `warden-testing-safety` memory:** a manual GUI smoke test briefly
ran the real tick loop while the user's actual Roblox client happened to be
open and focused. A read-only screenshot right after showed the lobby
untouched; flagged to the user via SendUserFile + a message. Fixed the root
cause (test isolation forcing `observe_only`) and separately found/reverted
two test files that were accidentally writing to the real checked-in
`config/` instead of a temp copy - also fixed. No repeat since.

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
- [x] All pages in section 7, dashboard updates live from the event bus — `warden/gui/pages/{home,loadout,settings,calibration,history,diagnostics}.py`, `warden/gui/bridge.py` (thread-safe EventBus→Qt signal bridge)
- [x] Presets switch from Home and persist — `AppContext.set_active_preset`/`create_preset`/`delete_preset`
- [x] Hotkeys work while Roblox is focused — `platform/hotkeys.py` (built Phase 1) now wired to Start/Pause/Stop/Screenshot in `MainWindow._setup_hotkeys`; pynput's global hook isn't scoped to a specific app, so it fires regardless of focus (matches intent)
- [x] App never overlaps the Roblox client during a session — `MainWindow._start()` minimizes on Start per `gui.minimize_on_start`
- [x] Summary dialog on stop — `warden/gui/summary_dialog.py`
- [x] Bonus: mini overlay (extras §8.12) — `warden/gui/mini_overlay.py`
- [x] `pytest` runs green (203 tests)

### Phase 6 — Persistence, tracking, scheduler
- [x] Kill the app mid-session → relaunch → totals intact, Resume offered — `warden/core/persistence.py` (atomic `state.json`, per-preset `ContractProgress`, all-time counters), Home page's resume banner
- [x] Stop-at-target works (test with a 0.01 h target) — `warden/core/scheduler.py` (`Scheduler.check`), `TickLoop._scheduled_stop` (never joins its own thread), tested exactly with a 0.01h target
- [x] Scheduler windows and stop-at-time work; shutdown countdown is cancelable — `in_any_window` (handles midnight wraparound), `ShutdownCountdown`
- [x] `pytest` runs green (239 tests)

### Phase 7 — Integrations
- [x] Discord webhook embed on interval + alerts — `warden/integrations/discord_webhook.py` (`DiscordWebhook`); screenshot-in-embed not yet attached (see Decisions #39), everything else works
- [x] Optional bot commands restricted to the user's Discord user ID — `warden/integrations/discord_bot.py` (`BotCommands` fully tested; `DiscordBotRunner`'s `discord.py` glue is thin and untested - needs a real gateway connection)
- [x] LAN dashboard reachable from a phone, PIN-gated controls, off by default — `warden/integrations/lan_dashboard.py` (FastAPI app tested via `TestClient`; auto-generates a PIN if left blank rather than ever running unprotected)
- [x] Toasts and sleep prevention working — `warden/integrations/toast.py`, `warden/platform/power.py` (`SleepGuard`, wired into `TickLoop.start/stop`)
- [x] `pytest` runs green (299 tests)

### Phase 8 — Calibration, unknown gallery, diagnostics, extras
- [x] Calibration wizard can capture a template, sample an HSV range, and show live detections in under a minute per screen — `warden/gui/pages/calibration.py` (real wizard, not the Phase 5 stub): capture live or load an image, drag a selection (`gui/widgets.py`'s `ImageCanvas`), save as template / sample HSV / set ROI / run detection, each one or two clicks
- [x] Unknown gallery → "make template" flow — second tab on the same page, lists `diagnostics/unknown/*.png`, drag a region, pick a detector name, save
- [x] Diagnostics page complete (Phase 5); contract OCR verification and contract queue working — `warden/flows/calibration.py` (`parse_contract_hours`), `core/persistence.py` (`verify_contract_hours`), `core/tick.py` (`_maybe_verify_contract`, opportunistic while safely in LOBBY); `gui/context.py` (`advance_contract_queue`), `core/tick.py` emits `schedule.target_reached`, `MainWindow` advances and restarts
- [x] `pytest` runs green (341 tests)

### Phase 9 — Packaging & docs
- [ ] PyInstaller one-folder build runs on a clean Windows machine
- [ ] README: install, Tesseract (optional), first-run calibration walkthrough, public vs share-link note, Discord setup, troubleshooting, and a clear note that automating play is against Roblox's rules and can get the account banned — test on an alt
- [ ] No gameplay-specific values hardcoded anywhere; everything lives in config/presets

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

- GUI smoke tests run offscreen (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`).
- Session timer / in-match-% / contract progress on Home are in-memory only (reset on app
  restart) - durable, cross-restart versions are Phase 6's job (`state.json`).
- History page only shows the current session's live transitions, not past sessions (needs
  Phase 6's `sessions/<timestamp>.json`). Calibration page lists missing templates but isn't
  the real capture/sample/live-overlay wizard yet (Phase 8).
- Settings page's hotkey fields are free-text key names, not an actual "press a key to bind"
  capture widget - functional but not polished; fine to revisit as a later nicety.

## Exact next step

Start Phase 9 (the last one): packaging and docs.
1. PyInstaller one-folder build (`pyproject.toml`'s `dev` extra already includes `pyinstaller`) -
   write a `.spec` (or a plain `pyinstaller` invocation) that bundles `warden/`, `config/`
   (defaults), and any Lucide/MIT icon assets used; verify it runs on a clean checkout (no `.venv`
   dev dependencies beyond what's declared) - this is the one DoD item that benefits from an
   actual clean-machine test, though not a *live Roblox* one, so it doesn't need to wait for the
   user.
2. README.md: install steps, optional Tesseract setup (OCR features degrade gracefully without
   it - already true in `vision/ocr.py`), a first-run Calibration walkthrough (screenshot or
   plain steps using the Phase 8 wizard), the public-vs-share_link warning (already in HANDOFF
   §2/§6.6 and the Settings page - make sure the README repeats it prominently), Discord webhook/
   bot setup steps, troubleshooting (Diagnostics page, common config errors), and the required
   note that automating play is against Roblox's rules and can get the account banned - test on
   an alt (HANDOFF §9's exact wording).
3. Final sweep for hardcoded gameplay-specific values - everything should already live in
   `config/default.yaml` or `config/presets/*.yaml` (placeholders throughout, never baked into
   Python code), but worth one pass over `warden/` to confirm nothing slipped through.
4. Clean-room check (HANDOFF §1): re-read the whole codebase's naming, log messages, and the
   Lucide icon licensing note once real icons are chosen for packaging.
