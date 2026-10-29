"""Stop hook: Claude may only stop when the stage's work is really closed out.

Checks (CLAUDE.md "Every stage ends with..." steps 2, 4, 5):
  1. nothing uncommitted (git status clean)
  2. nothing unpushed (HEAD is on the upstream branch)
  3. PROGRESS.md was updated in or after the latest commit that changed code, and its newest
     stage-log entry has filled-in "Smoke test:" and "Verifier:" lines
  4. .smoke/last-run.json says PASS (a full run, not --quick) for exactly the current code

If something fails, Claude is sent back with the reason. To avoid an endless loop, after
3 blocks in a row it lets Claude stop but says loudly that the gate is still failing.
Standard library only. Part of the harness (protected).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import harness_common as hc  # noqa: E402
import progress_view as pv  # noqa: E402

MAX_BLOCKS = 3
COUNTER = hc.SMOKE_DIR / "gate-blocks.txt"


def problems() -> list[str]:
    out: list[str] = []
    if hc.git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return ["not a git repository"]

    dirty = [line for line in hc.git("status", "--porcelain").stdout.splitlines()
             if line[3:].strip() != ".smoke/gate-blocks.txt"]
    if dirty:
        out.append(f"{len(dirty)} uncommitted change(s): commit them (git add -A; git commit -m \"<id>: ...\").")

    upstream = hc.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode != 0:
        out.append("this branch has no upstream: push it (git push -u origin <branch>).")
    else:
        ahead = hc.git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
        if ahead and ahead != "0":
            out.append(f"{ahead} commit(s) not pushed: run git push.")

    # PROGRESS.md must be updated in or after the latest commit that touched code.
    log = hc.git("log", "--format=%H", "--name-only", "-n", "200").stdout
    last_code = last_progress = None
    commit = None
    for line in log.splitlines():
        line = line.strip()
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            commit = line
            continue
        if not line or commit is None:
            continue
        if last_progress is None and line == "PROGRESS.md":
            last_progress = commit
        if last_code is None and hc.is_code_path(line):
            last_code = commit
    if last_code and last_progress:
        if hc.git("merge-base", "--is-ancestor", last_code, last_progress).returncode != 0:
            out.append("the latest code commit has no PROGRESS.md update with or after it: add the stage-log entry.")
    elif last_code and not last_progress:
        out.append("PROGRESS.md has never been committed alongside the code.")

    progress = ROOT / "PROGRESS.md"
    text = progress.read_text(encoding="utf-8") if progress.exists() else ""
    entries = pv.log_entries(text)
    if not entries:
        out.append("PROGRESS.md 'Stage log' has no entries.")
    else:
        newest = entries[0]
        for field in ("Smoke test", "Verifier"):
            value = pv.entry_field(newest, field)
            if not value or value.strip("_ .-").lower() in ("", "tbd", "todo", "pending"):
                out.append(f"newest stage-log entry is missing a filled-in '{field}:' line.")
    if not pv.current_status(text).get("Next stage"):
        out.append("PROGRESS.md 'Current status' has no '- **Next stage:**' line.")

    last = hc.load_last_run()
    if last is None:
        out.append("no smoke run recorded: run python scripts/smoke.py.")
    else:
        if last.get("quick"):
            out.append("the last smoke run was --quick: run the full python scripts/smoke.py.")
        if last.get("result") != "PASS":
            out.append("the last smoke run FAILED: fix it and run python scripts/smoke.py again.")
        if last.get("code_fingerprint") != hc.code_fingerprint():
            out.append("code changed since the last smoke run: run python scripts/smoke.py again (then commit .smoke/ and STATUS.md).")
    return out


def _read_counter() -> int:
    try:
        return int(COUNTER.read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def _write_counter(n: int) -> None:
    try:
        hc.SMOKE_DIR.mkdir(exist_ok=True)
        if n:
            COUNTER.write_text(str(n))
        elif COUNTER.exists():
            COUNTER.unlink()
    except OSError:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    found = problems()
    if not found:
        _write_counter(0)
        return 0
    blocks = _read_counter() + 1
    if payload.get("stop_hook_active") and blocks > MAX_BLOCKS:
        _write_counter(0)
        print("STAGE GATE STILL FAILING after %d tries - stopping anyway. Tell the user:\n- %s"
              % (MAX_BLOCKS, "\n- ".join(found)), file=sys.stderr)
        return 0
    _write_counter(blocks)
    reason = "Stage gate (CLAUDE.md, end-of-stage steps) isn't satisfied yet:\n- " + "\n- ".join(found)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
