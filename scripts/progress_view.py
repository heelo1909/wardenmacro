"""Read the harness sections of PROGRESS.md.

    python scripts/progress_view.py        # current status, next stage, stage checklist

Relies on these exact headings in PROGRESS.md (keep them as they are):
    ## Current status      bullet lines, one of them "- **Next stage:** <id> ..."
    ## Stages              "- [x] <id> ..." / "- [ ] <id> ..."
    ## Stage log           "### <id> ..." entries, newest first, each with
                           "- Smoke test: ..." and "- Verifier: ..." lines

Used by the SessionStart and Stop hooks and by scripts/smoke.py (STATUS.md).
Standard library only. Part of the harness (protected).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "PROGRESS.md"

_STAGE_RE = re.compile(r"^- \[( |x|X)\] \*{0,2}([A-Z][A-Za-z0-9.\-]*)\*{0,2}\s*[—:-]?\s*(.*)$")


@dataclass
class Stage:
    done: bool
    id: str
    title: str


def section(text: str, heading: str) -> str:
    """Body of the level-2 section called ``heading`` ('' if missing)."""
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == heading
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def current_status(text: str) -> dict[str, str]:
    """'- **Key:** value' bullets of "Current status" as {key: value}."""
    out: dict[str, str] = {}
    for line in section(text, "Current status").splitlines():
        m = re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def stages(text: str) -> list[Stage]:
    out = []
    for line in section(text, "Stages").splitlines():
        m = _STAGE_RE.match(line.strip())
        if m:
            out.append(Stage(m.group(1).lower() == "x", m.group(2), m.group(3).strip()))
    return out


def next_stage(text: str) -> Stage | None:
    return next((s for s in stages(text) if not s.done), None)


def log_entries(text: str) -> list[str]:
    """Stage-log entries ('### ...' blocks), newest first, excluding the template."""
    body = section(text, "Stage log")
    entries, cur = [], None
    for line in body.splitlines():
        if line.startswith("### "):
            if cur is not None:
                entries.append("\n".join(cur))
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        entries.append("\n".join(cur))
    return [e for e in entries if not e.lower().startswith("### template")]


def entry_field(entry: str, name: str) -> str | None:
    m = re.search(rf"^- {re.escape(name)}:\s*(.+)$", entry, re.MULTILINE)
    return m.group(1).strip() if m else None


def summary(text: str) -> str:
    status = current_status(text)
    lines = ["Warden progress"]
    for key, value in status.items():
        lines.append(f"  {key}: {value}")
    nxt = next_stage(text)
    lines.append(f"  Next unchecked stage: {nxt.id} {nxt.title}" if nxt else "  All stages checked.")
    done = sum(s.done for s in stages(text))
    lines.append(f"  Stages: {done}/{len(stages(text))} done")
    return "\n".join(lines)


def main() -> int:
    if not PROGRESS.exists():
        print("PROGRESS.md not found", file=sys.stderr)
        return 1
    text = PROGRESS.read_text(encoding="utf-8")
    print(summary(text))
    for s in stages(text):
        print(f"  [{'x' if s.done else ' '}] {s.id} {s.title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
