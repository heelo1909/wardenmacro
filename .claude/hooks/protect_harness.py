"""PreToolUse hook: block edits to the harness itself.

Protected: .claude/, scripts/smoke.py, scripts/progress_view.py, scripts/harness_common.py,
scripts/known_env_failures.json. If one of them really needs to change, tell the user
what and why; they edit it (or approve it) themselves.

Covers Edit/Write/MultiEdit/NotebookEdit by path, and Bash commands that look like they
write, move or delete a protected path. Exit code 2 = blocked (stderr goes back to Claude).
Standard library only. Part of the harness (protected).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import harness_common as hc  # noqa: E402

_WRITE_VERBS = re.compile(r"(\brm\b|\bmv\b|\bcp\b|\bdel\b|\btee\b|sed\s+-i|\btruncate\b|Set-Content|"
                          r"Out-File|Remove-Item|Move-Item|Copy-Item|\bgit\s+(checkout|restore|rm|mv)\b|"
                          r"write_text|write_bytes|open\([^)]*['\"][wa])")
_REDIRECT = re.compile(r">>?\s*['\"]?([^\s;|&'\"]+)")
_MESSAGE = ("Blocked: {path} is part of the stage harness (CLAUDE.md). Don't change it to get a stage "
            "through. If it really needs changing, stop and tell the user exactly what and why.")


def blocked_path(payload: dict) -> str | None:
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input") or {}
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        rel = hc.repo_relative(path) if path else None
        if rel and hc.is_protected(rel):
            return rel
        return None
    if tool == "Bash":
        cmd = (inp.get("command") or "").replace("\\", "/")
        for target in _REDIRECT.findall(cmd):
            rel = hc.repo_relative(target)
            if rel and hc.is_protected(rel):
                return rel
        if _WRITE_VERBS.search(cmd):
            for p in hc.PROTECTED:
                if p in cmd:
                    return p
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    path = blocked_path(payload)
    if path:
        print(_MESSAGE.format(path=path), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
