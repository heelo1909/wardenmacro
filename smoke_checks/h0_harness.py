"""H0: the stage harness itself is wired up (PROGRESS headings parse, hooks exist, gate logic runs)."""

import json

from _util import ROOT, check, run


def main():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import harness_common as hc
    import progress_view as pv

    text = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")
    check("PROGRESS has a Next stage", bool(pv.current_status(text).get("Next stage")))
    stages = pv.stages(text)
    check("PROGRESS lists stages", len(stages) >= 2)
    entries = pv.log_entries(text)
    check("stage log has entries", bool(entries))
    if entries:
        check("newest entry has Smoke test line", pv.entry_field(entries[0], "Smoke test") is not None)
        check("newest entry has Verifier line", pv.entry_field(entries[0], "Verifier") is not None)

    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = settings.get("hooks", {})
    for event, script in (("Stop", "stage_gate.py"), ("PreToolUse", "protect_harness.py"),
                          ("SessionStart", "session_start.py")):
        cmds = [h["command"] for group in hooks.get(event, []) for h in group.get("hooks", [])]
        check(f"{event} hook runs {script}", any(script in c for c in cmds))
        check(f"{script} exists", (ROOT / ".claude" / "hooks" / script).is_file())
    for agent in ("verifier", "test-writer"):
        check(f"agent {agent}", (ROOT / ".claude" / "agents" / f"{agent}.md").is_file())

    known = json.loads((ROOT / "scripts" / "known_env_failures.json").read_text(encoding="utf-8"))
    check("no Windows test is allowed to fail", known.get("win32") == [])
    check("protected list covers smoke.py", hc.is_protected("scripts/smoke.py"))
    check("code fingerprint is stable", hc.code_fingerprint() == hc.code_fingerprint())


run(main)
