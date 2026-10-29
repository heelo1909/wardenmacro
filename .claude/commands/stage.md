---
description: Do the next stage (same as "continue")
---
Run the next stage, following CLAUDE.md exactly:

1. `date`. Read the "Current status" block in PROGRESS.md, PRINCIPLES.md, HANDOFF.md §0–3, and the next
   stage's entry in HANDOFF.md §10 with everything it links to. $ARGUMENTS
2. If the stage is tagged [design] and its note in docs/design/ isn't `approved`, write or finish the
   note, log the stage as PARTIAL ("waiting for design approval"), and stop.
3. If the stage is (needs the user), do the prep that doesn't need them, then hand back the user's
   steps in plain words (no Terminal on a Mac) and stop.
4. Otherwise: tests first (use the test-writer subagent for anything non-trivial), then code, then a
   permanent smoke check in smoke_checks/, then `python scripts/smoke.py` until `SMOKE: PASS`.
5. Run the verifier subagent with the stage ID; fix and re-run (max 2 rounds).
6. Update PROGRESS.md (Current status, Stage log entry with Smoke test / Verifier lines, tick the stage
   in both lists) and HANDOFF.md §10, commit `<id>: <what> (<ref>)`, push, hand back in 8 lines or fewer.
