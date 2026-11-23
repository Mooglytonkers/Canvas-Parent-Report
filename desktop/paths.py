"""Folders for settings, logs, and saved secrets on this computer."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Settings live in %APPDATA%\\CanvasParentReport on Windows."""
    override = (os.environ.get("CPR_APP_DIR") or "").strip()
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(root) / "CanvasParentReport"
    else:
        path = Path.home() / ".config" / "CanvasParentReport"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_dir() / "config.ini"


def history_path() -> Path:
    return app_dir() / "history.json"


def log_dir() -> Path:
    path = app_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_save_dir() -> Path:
    documents = Path.home() / "Documents"
    if documents.is_dir():
        return documents / "Canvas Parent Report"
    return app_dir() / "reports"


def resource_path(name: str) -> Path:
    """Icon and other files, including inside a PyInstaller build."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "assets" / name
    return Path(__file__).resolve().parents[1] / "assets" / name


def ui_platform() -> str:
    """Allow screenshots to show the Windows wording on another system."""
    return (os.environ.get("CPR_UI_PLATFORM") or sys.platform).lower()


def secret_storage_note() -> str:
    if ui_platform().startswith("win"):
        return (
            "Your Canvas token and email password are stored in Windows "
            "Credential Manager on this PC. They are not written into the settings file."
        )
    return (
        "Your Canvas token and email password are stored in a private file on "
        "this computer. They are not written into the settings file."
    )
