# PRINCIPLES.md (Warden)

How work happens on this repo. Short on purpose; `CLAUDE.md` has the per-prompt checklist.

## 1. Order of work
**Requirement → (design note) → tests → code → smoke → verifier → log → commit.**
- Every stage starts from a requirement: a `HANDOFF.md` section, a `warden-mac-handoff.md` step,
  or a bug report in `docs/bugs/`.
- Stages tagged **[design]** (new subsystem, new OS API, anything touching input or recovery
  behavior) get a one-page note in `docs/design/` first, from `docs/design/TEMPLATE.md`. Code waits
  until its `Status:` line says `approved` (the user approves; a stage may write the note and stop).
  Small stages skip the note.
- Tests come before or with the code, never after the fact. Prefer a red test first.

## 2. What "done" means
A stage is done only when: its DoD items are met, a permanent smoke check exists for it,
`python scripts/smoke.py` prints `SMOKE: PASS`, the verifier says PASS, `PROGRESS.md` is updated,
and the work is committed and pushed. Anything less is PARTIAL or FAILED, and is logged as such.

## 3. Offline first
- Detectors and flows are tested on synthetic frames or recorded frames (`fixtures/frames/`).
- OS APIs (Win32, Quartz, AppKit, IOKit) are tested through fakes shaped like the real API.
- Live Roblox runs and real-Mac checks are **(needs the user)** stages. Offline green never
  proves a live behavior; say so and list it under "Live tests needed".

## 4. Hard limits
1. Never commit with failing tests. The only allowed failures are the environment-only ones in
   `scripts/known_env_failures.json`, for the OS listed there. The list may shrink, never grow,
   unless the user agrees.
2. Never change Windows behavior in a Mac stage (and the reverse).
3. Never mix a feature and a refactor in one stage (`R-n` stages for refactors).
4. Every change traces to a requirement; commit messages carry the stage ID and the reference.
5. Tests never send real input, never touch a real Roblox window, never write to the repo's
   `config/` or `templates/`, and never use the real data folder.
6. Nothing that works around Roblox's anti-cheat, Gatekeeper, macOS privacy permissions, or
   device management. No credentials in the repo or in CI logs.
7. Never edit the harness (`.claude/`, `scripts/smoke.py`, `scripts/progress_view.py`, `scripts/harness_common.py`,
   `scripts/known_env_failures.json`) to get a stage through. Ask the user.

## 5. Quality gates
- New code has tests; every new public function or class has at least one.
- `python -m warden --selftest` passes.
- The Mac release workflow stays green on tag pushes (Mac stages check it).
- Logs and UI text are original (HANDOFF §1).
