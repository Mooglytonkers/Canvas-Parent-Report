#!/usr/bin/env python3
"""Load settings from config.ini, an optional .env file, and environment variables.

Environment variables always win. The access token is never read from
config.ini (only from CANVAS_TOKEN or a gitignored .env file) and is never
printed.
"""

from __future__ import annotations

import os
import re
import sys
from configparser import ConfigParser
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HERE = Path(__file__).resolve().parent

DEFAULT_NOTICE_KEYWORDS = [
    "grade",
    "grades",
    "grading",
    "graded",
    "missing",
    "late",
    "failing",
    "failed",
    "failure",
    "deadline",
    "deadlines",
    "d or an f",
    "d or f",
    "emails home",
    "emailing families",
]

_ENV_KEYS = (
    "CANVAS_BASE_URL",
    "CANVAS_TOKEN",
    "STUDENT_NAME",
    "SCHOOL_NAME",
    "START_DATE",
    "GRADED_COUNTS_AS_SUBMITTED",
    "MARK_GRADED_TODOS_DONE",
    "TODO_SINCE_DATE",
    "OUTPUT_DIR",
    "STUDENT_USER_ID",
    "TIMEZONE",
    "PRINT_COMMAND",
    "PRINT_ENABLED",
    "PRINTER_NAME",
    "PRINT_COPIES",
    "EMAIL_ENABLED",
    "EMAIL_TO",
    "EMAIL_FROM",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USE_TLS",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "NOTICE_KEYWORDS",
)


def project_dir() -> Path:
    return HERE


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs into os.environ if the key is not already set.

    Existing environment variables are left unchanged. Values are never printed.
    """
    path = path or (HERE / ".env")
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_quotes(value)


def _ini_get(parser: ConfigParser, section: str, option: str, fallback: str = "") -> str:
    if parser.has_option(section, option):
        return parser.get(section, option).strip()
    return fallback



def default_school_year_start(today: date | None = None) -> date:
    """August 1 of the current academic year (Aug–Jul)."""
    today = today or date.today()
    year = today.year if today.month >= 8 else today.year - 1
    return date(year, 8, 1)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError(f"Expected a true/false value, got {value!r}.")


def _as_date(value: str | None, field_name: str) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value!r}.") from exc


def _as_keywords(value: str | None) -> list[str]:
    if value is None or str(value).strip() == "":
        return list(DEFAULT_NOTICE_KEYWORDS)
    text = str(value).strip()
    if "\n" in text:
        parts = [p.strip() for p in text.splitlines()]
    else:
        parts = [p.strip() for p in text.split(",")]
    keywords = [p for p in parts if p]
    return keywords or list(DEFAULT_NOTICE_KEYWORDS)


def notice_regex(keywords: Iterable[str]) -> re.Pattern[str]:
    parts: list[str] = []
    for raw in keywords:
        kw = str(raw).strip()
        if not kw:
            continue
        escaped = re.escape(kw)
        if re.search(r"\s", kw):
            parts.append(escaped)
        else:
            parts.append(rf"\b{escaped}\b")
    if not parts:
        return re.compile(r"(?!)")
    return re.compile("|".join(parts), re.I)


def _parse_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"STUDENT_USER_ID must be a number, got {value!r}.") from exc


def _as_port(value: str | None) -> int:
    text = "587" if value is None or str(value).strip() == "" else str(value).strip()
    try:
        port = int(text)
    except ValueError as exc:
        raise ValueError(f"SMTP_PORT must be a number, got {value!r}.") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"SMTP_PORT must be between 1 and 65535, got {port}.")
    return port


def _as_copies(value: str | None) -> int:
    text = "1" if value is None or str(value).strip() == "" else str(value).strip()
    try:
        copies = int(text)
    except ValueError as exc:
        raise ValueError(f"PRINT_COPIES must be a number, got {value!r}.") from exc
    if copies < 1:
        raise ValueError(f"PRINT_COPIES must be at least 1, got {copies}.")
    if copies > 20:
        raise ValueError(f"PRINT_COPIES is limited to 20, got {copies}.")
    return copies


def smtp_security(value: str | None, port: int) -> str:
    """Return 'starttls', 'ssl', or 'plain'. Port 465 always uses SSL."""
    text = "" if value is None else str(value).strip().lower()
    if text in ("ssl", "smtps", "implicit"):
        mode = "ssl"
    elif text in ("0", "false", "no", "n", "off", "none", "plain"):
        mode = "plain"
    elif text in ("", "1", "true", "yes", "y", "on", "starttls", "tls"):
        mode = "starttls"
    else:
        raise ValueError(
            "SMTP_USE_TLS must be true (STARTTLS), false, or ssl. "
            f"Got {value!r}."
        )
    if port == 465:
        return "ssl"
    return mode


@dataclass
class Settings:
    base_url: str = ""
    student_name: str = ""
    school_name: str = ""
    start_date: date = field(default_factory=lambda: default_school_year_start())
    timezone: str = "America/New_York"
    graded_counts_as_submitted: bool = True
    mark_graded_todos_done: bool = False
    todo_since_date: date | None = None
    output_dir: Path = field(default_factory=lambda: HERE / "output")
    student_user_id: int | None = None
    print_command: str = ""
    print_enabled: bool = False
    printer_name: str = ""
    print_copies: int = 1
    email_enabled: bool = False
    email_to: str = ""
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""
    notice_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_NOTICE_KEYWORDS))
    config_path: Path | None = None

    def tzinfo(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Unknown timezone {self.timezone!r}. Use a name like America/New_York."
            ) from exc

    def todo_since(self) -> date:
        return self.todo_since_date or self.start_date

    def scope_label(self) -> str:
        start = self.start_date
        try:
            month = start.strftime("%b")
        except Exception:
            month = start.isoformat()
        return f"Assignments due {month} {start.day}, {start.year} onward"

    def apply_to_env(self) -> None:
        """Expose non-secret settings for child processes. Never touches CANVAS_TOKEN."""
        if self.base_url and "CANVAS_BASE_URL" not in os.environ:
            os.environ["CANVAS_BASE_URL"] = self.base_url


def default_config_path() -> Path:
    override = (os.environ.get("CONFIG_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return HERE / "config.ini"


def load_settings(config_path: Path | None = None, *, load_env: bool = True) -> Settings:
    if load_env:
        load_dotenv()

    parser = ConfigParser()
    path = config_path or default_config_path()
    path = path.expanduser()
    if not path.is_absolute():
        path = (HERE / path).resolve()
    if path.is_file():
        parser.read(path, encoding="utf-8")

    def pick(env_key: str, section: str, option: str, fallback: str = "") -> str:
        if env_key in os.environ and str(os.environ.get(env_key, "")).strip() != "":
            return str(os.environ[env_key]).strip()
        return _ini_get(parser, section, option, fallback)

    base_url = pick("CANVAS_BASE_URL", "canvas", "base_url")
    timezone = pick("TIMEZONE", "canvas", "timezone", "America/New_York") or "America/New_York"
    student_user_id = _parse_int(pick("STUDENT_USER_ID", "canvas", "student_user_id"))

    student_name = pick("STUDENT_NAME", "report", "student_name")
    school_name = pick("SCHOOL_NAME", "report", "school_name")
    start_raw = pick("START_DATE", "report", "start_date", "")
    start_date = _as_date(start_raw, "START_DATE") or default_school_year_start()
    graded = _as_bool(
        pick("GRADED_COUNTS_AS_SUBMITTED", "report", "graded_counts_as_submitted", "true"),
        True,
    )
    output_raw = pick("OUTPUT_DIR", "report", "output_dir", str(HERE / "output"))
    output_dir = Path(output_raw or "output").expanduser()
    if not output_dir.is_absolute():
        output_dir = (HERE / output_dir).resolve()

    mark_done = _as_bool(
        pick("MARK_GRADED_TODOS_DONE", "todo", "mark_graded_todos_done", "false"),
        False,
    )
    todo_since = _as_date(pick("TODO_SINCE_DATE", "todo", "todo_since_date"), "TODO_SINCE_DATE")

    print_command = pick("PRINT_COMMAND", "print", "print_command")
    print_enabled = _as_bool(pick("PRINT_ENABLED", "print", "enabled", "false"), False)
    printer_name = pick("PRINTER_NAME", "print", "printer_name")
    print_copies = _as_copies(pick("PRINT_COPIES", "print", "copies", "1"))

    email_enabled = _as_bool(pick("EMAIL_ENABLED", "email", "enabled", "false"), False)
    email_to = pick("EMAIL_TO", "email", "to")
    email_from = pick("EMAIL_FROM", "email", "from")
    smtp_host = pick("SMTP_HOST", "email", "smtp_host")
    smtp_port = _as_port(pick("SMTP_PORT", "email", "smtp_port", "587"))
    security = smtp_security(pick("SMTP_USE_TLS", "email", "smtp_use_tls", "true"), smtp_port)
    # Username and password are never read from config.ini.
    if _ini_get(parser, "email", "smtp_password"):
        print(
            "warning: an SMTP password in config.ini was ignored. "
            "Put SMTP_PASSWORD in .env only.",
            file=sys.stderr,
        )
    if _ini_get(parser, "email", "smtp_username"):
        print(
            "warning: SMTP_USERNAME in config.ini was ignored. Put it in .env only.",
            file=sys.stderr,
        )
    smtp_username = (os.environ.get("SMTP_USERNAME") or "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD") or ""
    keywords = _as_keywords(pick("NOTICE_KEYWORDS", "messages", "notice_keywords"))

    settings = Settings(
        base_url=base_url.rstrip("/"),
        student_name=student_name,
        school_name=school_name,
        start_date=start_date,
        timezone=timezone,
        graded_counts_as_submitted=graded,
        mark_graded_todos_done=mark_done,
        todo_since_date=todo_since,
        output_dir=output_dir,
        student_user_id=student_user_id,
        print_command=print_command,
        print_enabled=print_enabled,
        printer_name=printer_name,
        print_copies=print_copies,
        email_enabled=email_enabled,
        email_to=email_to,
        email_from=email_from,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_security=security,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        notice_keywords=keywords,
        config_path=path if path.is_file() else None,
    )
    settings.apply_to_env()
    try:
        from canvas_api import set_base_url

        if settings.base_url:
            set_base_url(settings.base_url)
    except Exception:
        # canvas_api may not be needed by every caller (for example make_report).
        if settings.base_url:
            os.environ.setdefault("CANVAS_BASE_URL", settings.base_url)
    return settings


def require_base_url(settings: Settings) -> str:
    if settings.base_url:
        return settings.base_url
    print(
        "error: CANVAS_BASE_URL is not set. Copy config.example.ini to config.ini "
        "and add your school's Canvas web address, or set CANVAS_BASE_URL.",
        file=sys.stderr,
    )
    sys.exit(1)
