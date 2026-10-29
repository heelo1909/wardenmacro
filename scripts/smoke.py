"""Smoke runner: prove nothing broke. Prints ``SMOKE: PASS`` or ``SMOKE: FAIL``.

    python scripts/smoke.py            # everything (what every stage must run)
    python scripts/smoke.py --quick    # smoke checks + selftest only (no pytest); never counts for the gate

Steps, all with real input switched off (WARDEN_FORCE_OBSERVE_ONLY=1) and a
throwaway data folder (WARDEN_HOME), so the user's Roblox and config are never touched:
  1. every script in smoke_checks/ (each exits non-zero on failure)
  2. python -m warden --selftest
  3. the full pytest suite; the only failures allowed are the ones listed for
     this OS in scripts/known_env_failures.json

Writes .smoke/last-run.json (read by the Stop hook) and regenerates STATUS.md.
Re-runs itself with the repo's .venv Python when one exists.
Part of the harness (protected): change only with the user's OK.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_common as hc  # noqa: E402
import progress_view as pv  # noqa: E402

ROOT = hc.ROOT
CHECK_TIMEOUT_S = 180
PYTEST_TIMEOUT_S = 1800


def _venv_python() -> Path | None:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python3", ".venv/bin/python"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def _maybe_reexec_in_venv() -> None:
    venv = _venv_python()
    if venv is None or os.environ.get("WARDEN_SMOKE_REEXEC") == "1":
        return
    try:
        if Path(sys.executable).resolve() == venv.resolve():
            return
    except OSError:
        return
    env = dict(os.environ, WARDEN_SMOKE_REEXEC="1")
    sys.exit(subprocess.call([str(venv), str(Path(__file__).resolve()), *sys.argv[1:]], env=env))


def _env(home: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "WARDEN_FORCE_OBSERVE_ONLY": "1",
        "WARDEN_HOME": home,
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": str(ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _tail(text: str, n: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def run_checks(env: dict[str, str]) -> list[dict]:
    results = []
    for script in sorted((ROOT / "smoke_checks").glob("*.py")):
        if script.name.startswith("_"):
            continue
        start = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True,
                                  text=True, timeout=CHECK_TIMEOUT_S)
            ok, out = proc.returncode == 0, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            ok, out = False, f"timed out after {CHECK_TIMEOUT_S}s"
        results.append({"name": script.name, "ok": ok, "seconds": round(time.monotonic() - start, 1),
                        "output": "" if ok else _tail(out)})
        print(f"  {'ok  ' if ok else 'FAIL'} {script.name}")
    return results


def run_selftest(env: dict[str, str]) -> dict:
    proc = subprocess.run([sys.executable, "-m", "warden", "--selftest"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=CHECK_TIMEOUT_S)
    ok = proc.returncode == 0
    print(f"  {'ok  ' if ok else 'FAIL'} warden --selftest")
    return {"name": "warden --selftest", "ok": ok, "output": "" if ok else _tail(proc.stdout + proc.stderr)}


def _node_id(tc: ET.Element) -> str:
    cls = tc.get("classname", "")
    return cls.replace(".", "/") + ".py::" + tc.get("name", "")


def run_pytest(env: dict[str, str], known: set[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        try:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                   f"--junit-xml={xml}"], cwd=ROOT, env=env, capture_output=True, text=True,
                                  timeout=PYTEST_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return {"ok": False, "total": 0, "failed": [], "unexpected": ["pytest timed out"], "now_passing": []}
        if not xml.exists():
            return {"ok": False, "total": 0, "failed": [], "unexpected": ["pytest produced no report"],
                    "now_passing": [], "output": _tail(proc.stdout + proc.stderr)}
        root = ET.parse(xml).getroot()
    cases = list(root.iter("testcase"))
    failed = sorted(_node_id(tc) for tc in cases
                    if tc.find("failure") is not None or tc.find("error") is not None)
    unexpected = [f for f in failed if f not in known]
    now_passing = sorted(known - set(failed))
    ok = not unexpected and len(cases) > 0
    print(f"  {'ok  ' if ok else 'FAIL'} pytest: {len(cases)} tests, {len(failed)} failed "
          f"({len(failed) - len(unexpected)} known environment-only, {len(unexpected)} unexpected)")
    for f in unexpected[:30]:
        print(f"         unexpected: {f}")
    return {"ok": ok, "total": len(cases), "failed": failed, "unexpected": unexpected, "now_passing": now_passing}


def write_status(result: dict) -> None:
    text = (ROOT / "PROGRESS.md").read_text(encoding="utf-8") if (ROOT / "PROGRESS.md").exists() else ""
    status = pv.current_status(text)
    nxt = pv.next_stage(text)
    lines = [
        "# STATUS.md",
        "",
        "_Generated by `scripts/smoke.py`. Don't edit by hand._",
        "",
        f"- **Smoke:** {result['result']} ({result['finished_at']}, {result['platform']}, commit {result['git_head'][:8]})",
        f"- **Next stage:** {status.get('Next stage') or (nxt.id + ' ' + nxt.title if nxt else 'none')}",
        f"- **Last stage:** {status.get('Last stage', '-')}",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for c in result["checks"]:
        lines.append(f"| {c['name']} | {'pass' if c['ok'] else '**FAIL**'} |")
    pt = result.get("pytest")
    if pt:
        lines.append(f"| pytest ({pt['total']} tests) | {'pass' if pt['ok'] else '**FAIL**'}"
                     f" ({len(pt['failed'])} failed, {len(pt['unexpected'])} unexpected) |")
    (ROOT / "STATUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    _maybe_reexec_in_venv()
    quick = "--quick" in argv
    started = datetime.now(timezone.utc)
    print(f"Warden smoke - {started.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} - {sys.platform}")
    fingerprint = hc.code_fingerprint()
    known_all = json.loads((ROOT / "scripts" / "known_env_failures.json").read_text(encoding="utf-8"))
    known = set(known_all.get(sys.platform, []))

    with tempfile.TemporaryDirectory(prefix="warden-smoke-") as home:
        env = _env(home)
        print("smoke checks:")
        checks = run_checks(env)
        checks.append(run_selftest(env))
        pytest_result = None if quick else run_pytest(env, known)

    ok = all(c["ok"] for c in checks) and (pytest_result is None or pytest_result["ok"])
    if not checks[:-1]:
        ok = False
        print("  FAIL no smoke checks found in smoke_checks/")
    result = {
        "result": "PASS" if ok else "FAIL",
        "quick": quick,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "git_head": hc.git("rev-parse", "HEAD").stdout.strip() or "unknown",
        "code_fingerprint": fingerprint,
        "checks": checks,
        "pytest": pytest_result,
    }
    if hc.code_fingerprint() != fingerprint:
        result["result"] = "FAIL"
        ok = False
        print("  FAIL code changed while smoke was running; run it again")
    if not quick:
        hc.SMOKE_DIR.mkdir(exist_ok=True)
        hc.LAST_RUN.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        write_status(result)
    if pytest_result and pytest_result["now_passing"]:
        print(f"  note: {len(pytest_result['now_passing'])} listed environment-only failures passed here;"
              " they can be removed from scripts/known_env_failures.json (ask the user)")
    print("SMOKE: PASS" if ok else "SMOKE: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
