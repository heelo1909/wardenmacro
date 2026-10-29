---
description: Fix a bug the user reported (evidence first, red test, fix, smoke)
---
Bug: $ARGUMENTS

Follow CLAUDE.md "Fixing bugs the user reports":
0. Next free number → `docs/bugs/BUG-NNN-<short-name>.md` from `docs/bugs/TEMPLATE.md`, with the user's
   exact words. Add a stage `B-NNN` to HANDOFF.md §10 and PROGRESS.md "Stages".
1. Evidence before any fix: the session log in the data folder's `logs/`, `diagnostics/unknown/` frames,
   the session summary, or a failing test. Write down what the evidence shows in the bug file.
2. Red regression test (test-writer subagent if useful).
3. Fix until green. Smallest change that fixes the cause, not the symptom.
4. Permanent smoke check `smoke_checks/b_NNN_<name>.py`, then `python scripts/smoke.py` → `SMOKE: PASS`.
5. Verifier subagent with `B-NNN`.
6. PROGRESS.md: root cause under Decisions and the stage-log entry. If it can only be confirmed live,
   say so and add it to "Live tests needed". Commit `B-NNN: <what>`, push, hand back.
