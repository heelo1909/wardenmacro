"""Tests for the stage harness: PROGRESS parsing, the harness-protection hook, the Stop-hook
gate (run for real against a throwaway git repo), and the observe-only safety switch.
Don't weaken these to get a stage through (CLAUDE.md)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import harness_common as hc  # noqa: E402
import progress_view as pv  # noqa: E402

SAMPLE = """# PROGRESS.md

## Current status
- **Next stage:** M5a — real Mac part 1 (needs the user)
- **Last stage:** M4U — DONE

## Stages
- [x] M4U — First Mac CI run
- [ ] M5a — Real-Mac checklist steps 1–4
- [ ] B-001 — Hotkeys ignored

## Stage log
### Template
- Smoke test: PASS
- Verifier: PASS

### M4U — First Mac CI run
- Smoke test: PASS (9 checks)
- Verifier: PASS

### M0-M4 — older
- Smoke test: n/a

## Decisions
- something
"""


# =================================================================== progress_view


def test_current_status_and_stages():
    assert pv.current_status(SAMPLE)["Next stage"].startswith("M5a")
    ids = [(s.id, s.done) for s in pv.stages(SAMPLE)]
    assert ids == [("M4U", True), ("M5a", False), ("B-001", False)]
    assert pv.next_stage(SAMPLE).id == "M5a"


def test_log_entries_skip_template_and_read_fields():
    entries = pv.log_entries(SAMPLE)
    assert entries[0].startswith("### M4U")
    assert pv.entry_field(entries[0], "Smoke test") == "PASS (9 checks)"
    assert pv.entry_field(entries[1], "Verifier") is None


def test_real_progress_file_parses():
    text = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")
    assert pv.current_status(text).get("Next stage")
    assert pv.stages(text) and pv.log_entries(text)


# =================================================================== protection hook


def test_is_protected():
    for path in (".claude/settings.json", ".claude/hooks/stage_gate.py", "scripts/smoke.py",
                 "./scripts/progress_view.py", "scripts\\known_env_failures.json"):
        assert hc.is_protected(path), path
    for path in ("scripts/mac/build_dmg.sh", "warden/core/tick.py", "smoke_checks/h0_harness.py", "CLAUDE.md"):
        assert not hc.is_protected(path), path


def test_protect_hook_blocks_edits_and_writes_but_not_reads():
    import protect_harness as ph

    assert ph.blocked_path({"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "scripts" / "smoke.py")}})
    assert ph.blocked_path({"tool_name": "Write", "tool_input": {"file_path": ".claude/hooks/stage_gate.py"}})
    assert not ph.blocked_path({"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "warden" / "paths.py")}})
    assert ph.blocked_path({"tool_name": "Bash", "tool_input": {"command": "echo x > scripts/smoke.py"}})
    assert ph.blocked_path({"tool_name": "Bash", "tool_input": {"command": "rm -rf .claude/hooks"}})
    assert ph.blocked_path({"tool_name": "Bash", "tool_input": {"command": "sed -i s/a/b/ scripts/known_env_failures.json"}})
    assert not ph.blocked_path({"tool_name": "Bash", "tool_input": {"command": "python scripts/smoke.py > out.txt 2>&1"}})
    assert not ph.blocked_path({"tool_name": "Bash", "tool_input": {"command": "cat .claude/settings.json"}})
    assert not ph.blocked_path({"tool_name": "Read", "tool_input": {"file_path": "scripts/smoke.py"}})


def test_protect_hook_exit_code_2_when_blocked():
    proc = subprocess.run([sys.executable, str(ROOT / ".claude" / "hooks" / "protect_harness.py")],
                          input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "scripts/smoke.py"}}),
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 2 and "harness" in proc.stderr


def test_known_failures_never_include_windows():
    known = json.loads((ROOT / "scripts" / "known_env_failures.json").read_text(encoding="utf-8"))
    assert known["win32"] == []


# =================================================================== Stop-hook gate on a throwaway repo


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def gate_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    (repo / "scripts").mkdir(parents=True)
    (repo / ".claude" / "hooks").mkdir(parents=True)
    for name in ("harness_common.py", "progress_view.py"):
        shutil.copy(ROOT / "scripts" / name, repo / "scripts" / name)
    shutil.copy(ROOT / ".claude" / "hooks" / "stage_gate.py", repo / ".claude" / "hooks" / "stage_gate.py")
    (repo / ".gitignore").write_text(".smoke/gate-blocks.txt\n__pycache__/\n")
    (repo / "app.py").write_text("print('v1')\n")
    (repo / "PROGRESS.md").write_text(SAMPLE, encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(remote))

    def record_smoke(result="PASS", quick=False):
        code = ("import sys, json; sys.path.insert(0, 'scripts'); import harness_common as hc; "
                "hc.SMOKE_DIR.mkdir(exist_ok=True); "
                f"hc.LAST_RUN.write_text(json.dumps({{'result': '{result}', 'quick': {quick}, "
                "'code_fingerprint': hc.code_fingerprint()}))")
        subprocess.run([sys.executable, "-c", code], cwd=repo, check=True)

    def commit_and_push(msg="S: x"):
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", msg)
        _git(repo, "push", "-q", "-u", "origin", "main")

    def gate(payload=None):
        proc = subprocess.run([sys.executable, str(repo / ".claude" / "hooks" / "stage_gate.py")],
                              input=json.dumps(payload or {}), capture_output=True, text=True, cwd=repo)
        out = proc.stdout.strip()
        return json.loads(out) if out else None

    record_smoke()
    commit_and_push()
    return repo, record_smoke, commit_and_push, gate


def test_gate_passes_when_everything_is_closed_out(gate_repo):
    _repo, _smoke, _commit, gate = gate_repo
    assert gate() is None


def test_gate_blocks_uncommitted_and_stale_smoke(gate_repo):
    repo, _smoke, _commit, gate = gate_repo
    (repo / "app.py").write_text("print('v2')\n")
    verdict = gate()
    assert verdict["decision"] == "block"
    assert "uncommitted" in verdict["reason"] and "code changed since the last smoke run" in verdict["reason"]


def test_gate_blocks_unpushed_commit(gate_repo):
    repo, smoke, _commit, gate = gate_repo
    (repo / "app.py").write_text("print('v2')\n")
    (repo / "PROGRESS.md").write_text(SAMPLE + "\n", encoding="utf-8")
    smoke()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "S: v2")
    verdict = gate()
    assert "not pushed" in verdict["reason"]


def test_gate_requires_progress_with_the_code(gate_repo):
    repo, smoke, commit, gate = gate_repo
    (repo / "app.py").write_text("print('v3')\n")
    smoke()
    commit("S: code only")
    verdict = gate()
    assert "PROGRESS.md" in verdict["reason"]


def test_gate_rejects_failed_or_quick_smoke(gate_repo):
    repo, smoke, commit, gate = gate_repo
    smoke(result="FAIL", quick=True)
    commit("S: smoke record")
    reason = gate()["reason"]
    assert "FAILED" in reason and "--quick" in reason


def test_gate_requires_filled_smoke_and_verifier_lines(gate_repo):
    repo, smoke, commit, gate = gate_repo
    (repo / "PROGRESS.md").write_text(SAMPLE.replace("- Verifier: PASS\n\n### M0", "- Verifier: TBD\n\n### M0"),
                                      encoding="utf-8")
    smoke()
    commit("S: progress")
    assert "Verifier" in gate()["reason"]


def test_gate_gives_up_after_three_blocks(gate_repo):
    repo, _smoke, _commit, gate = gate_repo
    (repo / "app.py").write_text("print('dirty')\n")
    for _ in range(3):
        assert gate({"stop_hook_active": True})["decision"] == "block"
    assert gate({"stop_hook_active": True}) is None  # lets Claude stop, with a loud stderr message


# =================================================================== observe-only safety switch


def test_forced_observe_only_env(monkeypatch):
    from warden.platform.input import forced_observe_only

    monkeypatch.delenv("WARDEN_FORCE_OBSERVE_ONLY", raising=False)
    assert not forced_observe_only()
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("WARDEN_FORCE_OBSERVE_ONLY", value)
        assert forced_observe_only()
    monkeypatch.setenv("WARDEN_FORCE_OBSERVE_ONLY", "0")
    assert not forced_observe_only()
