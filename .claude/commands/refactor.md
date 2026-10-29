---
description: A behavior-preserving refactor as its own R-n stage
---
Refactor: $ARGUMENTS

1. Add stage `R-<n>` (next free number) to HANDOFF.md §10 and PROGRESS.md "Stages" with one line on
   what changes and why. No feature changes in this stage, and no behavior change on either OS.
2. Before touching code, run `python scripts/smoke.py` and note the pytest count. It must already pass.
3. Refactor in small steps, re-running the affected tests as you go.
4. Same pytest count, same results, `SMOKE: PASS`. Add a smoke check only if the refactor creates a new
   seam worth guarding.
5. Verifier subagent with the stage ID, PROGRESS.md entry, commit `R-<n>: <what>`, push, hand back.
