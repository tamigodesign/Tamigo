#!/bin/bash
# Gradi Finder .app za arhitekturu ovog Maca.
# x86_64 -> Tamigo-macos-intel.zip
# arm64  -> Tamigo-macos-apple-silicon.zip
# Linux ne može da napravi taj paket.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Ova izgradnja mora da se pokrene na macOS. Na $(uname -s) ne nastaje Finder aplikacija." >&2
  exit 2
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ZIP_NAME="Tamigo-macos-intel.zip" ;;
  arm64) ZIP_NAME="Tamigo-macos-apple-silicon.zip" ;;
  *)
    echo "Nepoznata arhitektura: $ARCH. Podržani su x86_64 (Intel) i arm64." >&2
    exit 3
    ;;
esac

cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
"$PY" -m pip install -r requirements.txt "pyinstaller>=6.6"

echo "macOS: $(sw_vers -productVersion) ($ARCH)"
"$PY" - << PY
import pathlib, platform, subprocess, sys
print("python", platform.python_version(), platform.machine(), platform.mac_ver()[0])
if platform.machine() != "$ARCH":
    sys.exit("Python ne radi kao $ARCH.")
import PySide6
root = pathlib.Path(PySide6.__file__).resolve().parent
samples = [path for path in root.rglob("*") if path.suffix in {".so", ".dylib"} or path.name.startswith("Qt")]
checked = 0
bad = []
for path in samples:
    if not path.is_file():
        continue
    kind = subprocess.check_output(["file", "-b", str(path)], text=True)
    if "Mach-O" not in kind:
        continue
    checked += 1
    if "$ARCH" not in kind:
        bad.append(f"{path}: {kind.strip()}")
print(f"PySide6 Mach-O uzoraka: {checked}")
if checked < 1 or bad:
    print("\n".join(bad[:20]))
    sys.exit("PySide6 nije $ARCH.")
PY

"$PY" -m PyInstaller --noconfirm --clean packaging/tamigo.spec
APP="dist/Tamigo Accessibility Intelligence.app"
BIN="$APP/Contents/MacOS/Tamigo Accessibility Intelligence"
test -x "$BIN"
codesign --force --deep --sign - "$APP"

"$PY" - << PY
import os, subprocess, sys
app = "$APP"
expect = "$ARCH"
checked = 0
bad = []
for root, dirs, files in os.walk(app):
    for name in files:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        if not (name.endswith((".dylib", ".so")) or os.access(path, os.X_OK)):
            continue
        kind = subprocess.check_output(["file", "-b", path], text=True)
        if "Mach-O" not in kind:
            continue
        checked += 1
        if expect not in kind:
            bad.append(f"{path}: {kind.strip()}")
print(f"Paket Mach-O fajlova sa {expect}: {checked}")
if checked < 5 or bad:
    print("\n".join(bad[:30]))
    sys.exit(f"Paket nije {expect}.")
PY

file "$BIN"
ditto -c -k --keepParent "$APP" "dist/$ZIP_NAME"
echo "Napravljeno: $APP"
echo "Arhiva: dist/$ZIP_NAME"
echo "Arhitektura: $ARCH"
echo "Podaci ostaju u ~/Library/Application Support/TamigoIntel i ne zavise od ovog foldera."
