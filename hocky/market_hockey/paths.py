"""Filesystem locations used by the game and the control panel."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
DEFAULTS_PATH = CONFIG_DIR / "defaults.json"
BACKUP_PATH = CONFIG_DIR / "settings.prev.json"
PRESETS_DIR = CONFIG_DIR / "presets"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
SOUNDS_DIR = ASSETS_DIR / "sounds"
ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"
LOGS_DIR = ROOT / "logs"
DOCS_DIR = ROOT / "docs"
