#!/bin/bash
# Gradi Finder .app. Mora da se pokrene na macOS. Linux ne može da napravi taj paket.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Ova izgradnja mora da se pokrene na macOS. Na $(uname -s) ne nastaje Finder aplikacija." >&2
  exit 2
fi

cd "$(dirname "$0")/.."
python3 -m pip install -r requirements.txt "pyinstaller>=6.6"
python3 -m PyInstaller --noconfirm --clean packaging/tamigo.spec
codesign --force --deep --sign - "dist/Tamigo Accessibility Intelligence.app"
ditto -c -k --keepParent "dist/Tamigo Accessibility Intelligence.app" "dist/Tamigo-macos.zip"
echo "Napravljeno: dist/Tamigo Accessibility Intelligence.app"
echo "Arhiva: dist/Tamigo-macos.zip"
echo "Podaci ostaju u ~/Library/Application Support/TamigoIntel i ne zavise od ovog foldera."
