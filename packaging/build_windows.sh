#!/bin/bash
# build_windows.sh — Build the Windows .exe using Wine + PyInstaller (best-effort)
# RECOMMENDED: Use the GitHub Actions workflow instead (see .github/workflows/build_windows.yml)
#
# Prerequisites on Linux:
#   1. Wine installed (wine64)
#   2. Python 3.11 for Windows installed inside Wine:
#      wine ~/Downloads/python-3.11.x-amd64.exe /quiet InstallAllUsers=0 PrependPath=1
#   3. All dependencies installed inside Wine Python:
#      wine "$WINE_PYTHON" -m pip install -r requirements.txt
#      wine "$WINE_PYTHON" -m pip install pyinstaller
#
# Run from the project root: bash packaging/build_windows.sh

set -e

cd "$(dirname "$0")/.."

WINE_PYTHON="${WINE_PYTHON:-/home/$USER/.wine/drive_c/Program Files/Python311/python.exe}"

if [ ! -f "$WINE_PYTHON" ]; then
    echo "ERROR: Wine Python not found at: $WINE_PYTHON"
    echo "Please install Python 3.11 for Windows inside Wine first."
    echo "See comments at the top of this script."
    exit 1
fi

echo "==> Cleaning previous Windows build artifacts..."
rm -rf dist/FolderFlow.exe

echo "==> Building Windows .exe via Wine..."
WINEDEBUG=-all wine "$WINE_PYTHON" -m PyInstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name "FolderFlow" \
    --icon=folderFlow-icon.png \
    --add-data "folderFlow-icon.png;." \
    --add-data "credentials.json;." \
    --hidden-import "PyQt6.sip" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "google.auth.transport.requests" \
    --hidden-import "google.oauth2.credentials" \
    --hidden-import "google_auth_oauthlib.flow" \
    --hidden-import "googleapiclient.discovery" \
    --hidden-import "googleapiclient._helpers" \
    --hidden-import "googleapiclient.http" \
    --hidden-import "src.paths" \
    --hidden-import "src.config" \
    --hidden-import "src.auth" \
    --hidden-import "src.engine" \
    --hidden-import "src.scheduler" \
    --hidden-import "src.tracker" \
    --collect-all "PyQt6" \
    --collect-all "google_auth_oauthlib" \
    --collect-all "googleapiclient" \
    --collect-all "google.auth" \
    main.py

echo ""
echo "==> Done. Windows executable at: dist/FolderFlow.exe"
