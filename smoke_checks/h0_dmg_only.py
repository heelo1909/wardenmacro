"""H0: on a Mac, Warden runs from the DMG only (no .command launchers; README says DMG)."""

from _util import ROOT, check, run


def main():
    commands = sorted(p.name for p in ROOT.glob("*.command"))
    check("no .command launchers in the repo root", not commands, ", ".join(commands))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    check("README points Mac users at the DMG", "Warden-mac-arm64.dmg" in readme)
    check("README doesn't tell anyone to double-click a .command", "double-click **`Run Warden (Mac).command`**" not in readme
          and "double-click `Run Warden (Mac).command`" not in readme)
    wf = (ROOT / ".github" / "workflows" / "mac-release.yml").read_text(encoding="utf-8")
    check("release workflow builds the DMG", "build_dmg.sh" in wf and "Warden-mac-" in wf)
    check("Windows launchers still there", (ROOT / "Run Warden.bat").is_file())


run(main)
