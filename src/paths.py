"""
Centralized path resolution for FolderFlow.

Two kinds of paths:
1. resource_path() - Read-only assets bundled with the app (icon, credentials.json).
   - Frozen (PyInstaller): points to sys._MEIPASS (temp extraction dir)
   - Source: points to project root

2. user_data_dir() - Writable directory for user data (config.json, token.json, sync.db).
   - Always points to ~/.config/folderflow/ (Linux) or %APPDATA%/FolderFlow/ (Windows)
   - Created automatically if it doesn't exist
"""

import os
import sys

APP_NAME = "FolderFlow"


def is_frozen() -> bool:
    """Return True if running as a PyInstaller bundle."""
    return getattr(sys, 'frozen', False)


def resource_path(relative: str = "") -> str:
    """Return the absolute path to a bundled read-only resource.

    When frozen, PyInstaller extracts data files to a temporary directory
    stored in sys._MEIPASS.  When running from source, resources live in
    the project root (one level above src/).
    """
    if is_frozen():
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # src/paths.py -> src/ -> project_root/
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if relative:
        return os.path.join(base, relative)
    return base


def user_data_dir() -> str:
    """Return a writable directory for persistent user data.

    - Linux/macOS: ~/.config/folderflow/
    - Windows:     %APPDATA%/FolderFlow/

    The directory is created if it doesn't exist.
    """
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(base, APP_NAME)
    else:
        xdg = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
        data_dir = os.path.join(xdg, APP_NAME.lower())

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


# ---------------------------------------------------------------------------
# One-time migration: move user data from old locations to user_data_dir()
# ---------------------------------------------------------------------------
_MIGRATED = False

_MIGRATABLE_FILES = ('config.json', 'token.json', 'sync.db')


def migrate_old_data():
    """Copy config.json / token.json / sync.db from the old location
    (project root or next-to-executable) into user_data_dir() if they
    don't already exist there.  Called once at startup.
    """
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True

    dest_dir = user_data_dir()

    # Possible old locations: project root (source) or executable dir (frozen)
    if is_frozen():
        old_dir = os.path.dirname(sys.executable)
    else:
        old_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for fname in _MIGRATABLE_FILES:
        old_path = os.path.join(old_dir, fname)
        new_path = os.path.join(dest_dir, fname)

        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                import shutil
                shutil.copy2(old_path, new_path)
            except Exception:
                pass  # best-effort; don't crash startup over migration
