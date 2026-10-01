# PROGRESS.md

## Current phase

**Phase 1 — Platform & vision core: COMPLETE.**
User approved Phase 0, then said "continue all phases without me" (away at squash) —
now running autonomously through all phases per HANDOFF.md section 0's original
instruction, stopping only for a live-Roblox-test DoD item or a genuine blocker.
Next: Phase 2 — State machine, lobby, FFA, respawn, match end.

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
- [ ] All states in §6.1 implemented with timeouts and fallbacks
- [ ] Replay tests over synthetic frame sequences cover every transition, incl. early-abort of FFA search + mid-game join
- [ ] Respawn double-press logic tested; Respawns counter increments

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

Start Phase 2: `warden/core/state_machine.py` (states from §6.1 with timeouts/fallbacks),
`warden/flows/lobby.py`, `warden/flows/respawn.py`, and `warden/tools/replay.py` (offline
replay harness over recorded/synthetic frame sequences) + its tests.
