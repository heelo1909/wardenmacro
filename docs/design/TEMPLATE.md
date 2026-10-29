# Design: <feature>

- **Status:** draft   <!-- the user changes this to: approved -->
- **Stage:** <id>
- **Traces to:** HANDOFF.md §x.y / warden-mac-handoff.md §n / BUG-NNN

## Problem
One paragraph: what's missing or broken, for whom.

## Approach
What changes, in which modules. Which platform seam it sits behind.

## OS APIs
Each call, what it needs (permissions), what happens when it's missing (degrade, don't crash).

## The other OS
What stays exactly the same on Windows (or Mac), and how that's checked.

## Testing
Offline: fakes, synthetic or recorded frames, smoke check name.
Live only (needs the user): the exact steps.

## Risks
