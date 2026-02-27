#!/bin/bash
# build_linux.sh — Build the Linux standalone executable using PyInstaller
# Run from the project root: bash packaging/build_linux.sh

set -e  # Exit immediately on any error

cd "$(dirname "$0")/.."

echo "==> Activating virtual environment..."
source venv/bin/activate

echo "==> Installing / upgrading PyInstaller..."
pip install --quiet --upgrade pyinstaller

echo "==> Cleaning previous build artifacts..."
rm -rf build dist/FolderFlow FolderFlow.spec

echo "==> Building Linux executable..."
pyinstaller --noconfirm \
    --onefile \
    --windowed \
    --name "FolderFlow" \
    --icon=folderFlow-icon.png \
    --add-data "folderFlow-icon.png:." \
    --add-data "credentials.json:." \
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
echo "==> Build complete! Executable is at: dist/FolderFlow"
echo "    To run: chmod +x dist/FolderFlow && ./dist/FolderFlow"
