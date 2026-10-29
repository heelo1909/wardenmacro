---
description: Write a one-page design note for a [design] stage
---
Feature: $ARGUMENTS

Create `docs/design/<short-name>.md` from `docs/design/TEMPLATE.md` (one page): the requirement it traces
to, the approach, the OS APIs involved, what stays the same on the other OS, how it's tested offline,
what can only be checked live, and risks. Set `Status: draft`. Log a decision in PROGRESS.md and stop:
the user changes it to `approved` before any code for that stage is written.
