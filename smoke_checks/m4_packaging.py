"""M4: packaging/CI files are in place and the selftest passes from source."""

from _util import ROOT, check, run


def main():
    spec = (ROOT / "warden.spec").read_text(encoding="utf-8")
    check("bundle id", 'bundle_identifier="com.heelo1909.warden"' in spec)
    check("Mac icon exists", (ROOT / "assets" / "warden.icns").is_file())
    dmg = (ROOT / "scripts" / "mac" / "build_dmg.sh").read_text(encoding="utf-8")
    check("DMG via hdiutil UDZO", 'hdiutil create -volname "Warden"' in dmg and "UDZO" in dmg)
    wf = (ROOT / ".github" / "workflows" / "mac-release.yml").read_text(encoding="utf-8")
    for needle in ("macos-15", "macos-15-intel", "--selftest", "tags:"):
        check(f"workflow has {needle}", needle in wf)
    from warden.tools import selftest

    lines = []
    check("selftest passes (non-Mac module set)", selftest.run(platform_name="linux", emit=lines.append) == 0,
          lines[0][-400:] if lines else "")


run(main)
