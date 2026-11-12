"""Filesystem locations used by the game and the control panel.

Works both from source and from a PyInstaller build:
- APP_DIR: where the user-editable files live (config/, logs/, assets/). From source this is the project folder;
  in a build it is the folder that contains LandHockey.exe, so settings are saved next to the .exe.
- BUNDLE_DIR: read-only files packed inside the build (fallback for assets).
"""

import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = BUNDLE_DIR = Path(__file__).resolve().parent.parent

ROOT = APP_DIR
CONFIG_DIR = APP_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
DEFAULTS_PATH = CONFIG_DIR / "defaults.json"
BACKUP_PATH = CONFIG_DIR / "settings.prev.json"
PRESETS_DIR = CONFIG_DIR / "presets"
ASSETS_DIR = APP_DIR / "assets" if (APP_DIR / "assets").exists() else BUNDLE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
SOUNDS_DIR = ASSETS_DIR / "sounds"
ICONS_DIR = ASSETS_DIR / "icons"
ORBS_DIR = ASSETS_DIR / "orbs"
IMAGES_DIR = ASSETS_DIR / "images"
LOGS_DIR = APP_DIR / "logs"
DOCS_DIR = APP_DIR / "docs"

GAME_EXE = "LandHockey"
PANEL_EXE = "ControlPanel"


def launch_command(which: str) -> list[str]:
    """Command line that starts the game ("game") or the control panel ("panel") as a separate process."""
    if FROZEN:
        name = GAME_EXE if which == "game" else PANEL_EXE
        exe = APP_DIR / (name + (".exe" if sys.platform == "win32" else ""))
        return [str(exe)]
    script = "main.py" if which == "game" else "settings_app.py"
    return [sys.executable, str(APP_DIR / script)]


def install_crash_log(name: str) -> None:
    """Write uncaught exceptions to logs/<name>_crash.log (a windowed .exe has no console to show them)."""
    import traceback

    def hook(exc_type, exc, tb):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOGS_DIR / f"{name}_crash.log", "a", encoding="utf-8") as fh:
                fh.write("".join(traceback.format_exception(exc_type, exc, tb)) + "\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook
