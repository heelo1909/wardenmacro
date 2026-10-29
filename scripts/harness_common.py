"""Shared helpers for the stage harness (smoke runner, Stop hook, progress view).

Standard library only, so the hooks run with any Python 3. Part of the harness:
protected by the PreToolUse hook; change it only with the user's OK.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMOKE_DIR = ROOT / ".smoke"
LAST_RUN = SMOKE_DIR / "last-run.json"

# Files that don't count as "code" for the smoke-freshness check: notes, logs and
# the files smoke itself writes. Everything else git would track does count.
NON_CODE_SUFFIXES = (".md",)
NON_CODE_PREFIXES = (".smoke/", "docs/")

PROTECTED = (
    ".claude/",
    "scripts/smoke.py",
    "scripts/progress_view.py",
    "scripts/harness_common.py",
    "scripts/known_env_failures.json",
)


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def is_code_path(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel.startswith(NON_CODE_PREFIXES) or "__pycache__/" in rel or rel.endswith(".pyc"):
        return False
    return not rel.endswith(NON_CODE_SUFFIXES)


def code_files() -> list[str]:
    """Every file git tracks or would track (untracked but not ignored), code only, sorted."""
    out = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    names = sorted({n for n in out.stdout.split("\0") if n})
    return [n for n in names if is_code_path(n) and (ROOT / n).is_file()]


def code_fingerprint() -> str:
    """Content hash of all code files. Changes whenever any code changes, on any OS."""
    h = hashlib.sha256()
    for rel in code_files():
        h.update(rel.replace("\\", "/").encode())
        h.update(b"\0")
        h.update((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()


def load_last_run() -> dict | None:
    try:
        return json.loads(LAST_RUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def repo_relative(path: str, root: Path = ROOT) -> str | None:
    """``path`` (absolute or relative to the repo) as a repo-relative posix path,
    or None if it's outside the repo."""
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        rel = p.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return rel.as_posix()


def is_protected(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return any(rel == p or rel.startswith(p) for p in PROTECTED)
