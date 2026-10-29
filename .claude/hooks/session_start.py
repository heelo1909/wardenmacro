"""SessionStart hook: print the time and the next stage (stdout is added to Claude's context).
Standard library only. Part of the harness (protected).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import harness_common as hc  # noqa: E402
import progress_view as pv  # noqa: E402


def main() -> int:
    now = datetime.now().astimezone()
    lines = [f"Session start: {now.strftime('%Y-%m-%d %H:%M %Z')} (one prompt = one stage, ~30 min)."]
    progress = ROOT / "PROGRESS.md"
    if progress.exists():
        text = progress.read_text(encoding="utf-8")
        status = pv.current_status(text)
        nxt = status.get("Next stage") or (lambda s: f"{s.id} {s.title}" if s else "none")(pv.next_stage(text))
        lines.append(f"Next stage: {nxt}")
        if status.get("Waiting on the user"):
            lines.append(f"Waiting on the user: {status['Waiting on the user']}")
    last = hc.load_last_run()
    if last:
        fresh = last.get("code_fingerprint") == hc.code_fingerprint()
        lines.append(f"Last smoke: {last.get('result')} at {last.get('finished_at')}"
                     f" ({'matches current code' if fresh else 'code changed since'}).")
    else:
        lines.append("Last smoke: none recorded.")
    lines.append("Read CLAUDE.md first.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
