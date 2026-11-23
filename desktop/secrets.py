"""Token and SMTP password storage.

Windows uses Credential Manager (keyring). Other systems use a private
.env file in the app data folder. Values are never written to config.ini
and never logged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from desktop.paths import app_dir

SERVICE = "CanvasParentReport"
TOKEN_ACCOUNT = "canvas_token"
SMTP_ACCOUNT = "smtp_password"

_ENV_NAMES = {
    TOKEN_ACCOUNT: "CANVAS_TOKEN",
    SMTP_ACCOUNT: "SMTP_PASSWORD",
}


def _use_keyring() -> bool:
    return sys.platform == "win32"


def _env_file() -> Path:
    return app_dir() / ".env"


def _read_env(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        if key:
            found[key] = text
    return found


def _format_env(value: str) -> str:
    if any(ch.isspace() for ch in value) or "#" in value:
        if "'" not in value:
            return "'" + value + "'"
        if '"' not in value:
            return '"' + value + '"'
    return value


def _write_env(path: Path, values: dict[str, str]) -> None:
    lines = ["# Private. Do not share this file or email it."]
    for key in ("CANVAS_TOKEN", "SMTP_PASSWORD"):
        if key in values:
            lines.append(f"{key}={_format_env(values[key])}")
    for key, value in values.items():
        if key not in ("CANVAS_TOKEN", "SMTP_PASSWORD"):
            lines.append(f"{key}={_format_env(value)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def set_secret(account: str, value: str) -> None:
    if _use_keyring():
        import keyring

        if value:
            keyring.set_password(SERVICE, account, value)
        else:
            try:
                keyring.delete_password(SERVICE, account)
            except Exception:
                pass
        return
    current = _read_env(_env_file())
    env_name = _ENV_NAMES[account]
    if value:
        current[env_name] = value
    else:
        current.pop(env_name, None)
    _write_env(_env_file(), current)


def get_secret(account: str) -> str:
    if _use_keyring():
        import keyring

        try:
            return keyring.get_password(SERVICE, account) or ""
        except Exception:
            return ""
    return _read_env(_env_file()).get(_ENV_NAMES[account], "")


def set_token(value: str) -> None:
    set_secret(TOKEN_ACCOUNT, value)


def get_token() -> str:
    return get_secret(TOKEN_ACCOUNT)


def set_smtp_password(value: str) -> None:
    set_secret(SMTP_ACCOUNT, value)


def get_smtp_password() -> str:
    return get_secret(SMTP_ACCOUNT)


def apply_to_environ() -> None:
    """Put stored secrets into the process environment for the existing report code."""
    token = get_token()
    password = get_smtp_password()
    if token:
        os.environ["CANVAS_TOKEN"] = token
    if password:
        os.environ["SMTP_PASSWORD"] = password
