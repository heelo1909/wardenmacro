# PROGRESS.md

## Current phase

**Phase 0 — Scaffold: COMPLETE, awaiting user review.**
Next: Phase 1 — Platform & vision core (only after user sign-off; user asked to stop at every phase).

## Phase checklist

### Phase 0 — Scaffold
- [x] Repo, `requirements.txt` / `pyproject.toml`, pydantic config schema, logging, event bus, `PROGRESS.md`
- [x] `python -m warden` opens an empty themed window
- [x] Default config loads and validates; invalid config shows a readable error
- [x] `pytest` runs green (21 tests)

### Phase 1 — Platform & vision core
- [ ] Window finder ignores browser tabs (mocked window lists)
- [ ] Focus-confirm gate
- [ ] DPI-aware capture; fraction ↔ pixel at 100/125/150%
- [ ] HSV blob detector + multi-scale template matcher on synthetic frames
- [ ] Input wrapper, fallback chain, jiggle-then-click, emergency stop
- [ ] Observe-only mode, frame recorder, `tools/diagnostics_cli.py`

## What exists

- `warden/config/schema.py` — `AppConfig` (config.yaml) + `Preset` (presets/*.yaml). `extra="forbid"` so YAML typos are errors.
- `warden/config/loader.py` — YAML load, `ConfigError` with one readable line per problem (`detectors.lobby_play.roi: x1 (0.7) must be less than x2 (0.3)`), atomic save, first-run seeding into `%LOCALAPPDATA%\Warden\`.
- `warden/core/events.py` — thread-safe `EventBus` (levels debug/info/success/warn/error, topic-prefix filters, history ring, subscriber isolation).
- `warden/core/logs.py` — rotating per-run log file in `%LOCALAPPDATA%\Warden\logs\`, bus→log bridge, keeps last 30 logs.
- `warden/gui/theme.py`, `warden/gui/main_window.py` — themed sidebar shell with 6 placeholder pages.
- `config/default.yaml`, `config/presets/{default,glass_wrap,random}.yaml`.
- `python -m warden --check-config [PATH]` validates and exits (0 ok / 2 invalid).

## Decisions

1. **Python 3.14** (only version installed; 3.12 not present). All deps install and run on it. `requires-python >= 3.12`.
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

Wait for user sign-off on Phase 0, then start Phase 1 with `warden/platform/window.py` (window enumeration + browser-class exclusion, mocked tests first).
