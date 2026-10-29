#!/bin/bash
# Wraps dist/Warden.app in a drag-to-Applications disk image.
#
#   scripts/mac/build_dmg.sh <arch>      e.g. arm64 or x86_64
#
# Runs on GitHub's macOS runners (.github/workflows/mac-release.yml); users
# never run this. A DMG keeps the app's executable bits and signature intact,
# which a plain .zip download was losing.
set -euo pipefail

ARCH="${1:?usage: build_dmg.sh <arch>}"
APP="dist/Warden.app"
DMG="dist/Warden-mac-${ARCH}.dmg"
STAGING="$(mktemp -d)"

if [ ! -d "$APP" ]; then
    echo "error: $APP not found - run 'pyinstaller warden.spec --clean' first" >&2
    exit 1
fi

# PyInstaller ad-hoc signs the bundle; make sure that signature is valid
# (re-sign ad hoc only if it isn't). No Developer ID / notarization here.
if ! codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "ad-hoc signing $APP"
    codesign --force --deep --sign - "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"

ditto "$APP" "$STAGING/Warden.app"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG"
hdiutil create -volname "Warden" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"

hdiutil verify "$DMG"
shasum -a 256 "$DMG" | tee "$DMG.sha256"
echo "built $DMG"
