"""Tiny helpers for smoke checks. Each check is a standalone script that exits non-zero on failure.

Rules: fakes only. No Roblox, no real window, no real input, no real data folder
(scripts/smoke.py sets WARDEN_HOME to a temp folder and WARDEN_FORCE_OBSERVE_ONLY=1).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))
        _failures.append(name)


def run(main) -> None:
    """Run ``main()``; exit 1 if it raised or any check failed."""
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    sys.exit(1 if _failures else 0)
