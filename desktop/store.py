"""Read and write config.ini in the app data folder. Secrets are not stored here."""

from __future__ import annotations

import json
from configparser import ConfigParser
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from config import Settings, _as_bool, _as_copies, _as_date, _as_port, default_school_year_start, smtp_security
from desktop.paths import config_path, default_save_dir, history_path

DAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _ini_bool(value: bool) -> str:
    return "true" if value else "false"


@dataclass
class AppConfig:
    base_url: str = ""
    timezone: str = "America/New_York"
    student_user_id: str = ""
    student_name: str = ""
    school_name: str = ""
    start_date: str = ""
    graded_counts_as_submitted: bool = True
    output_dir: str = ""
    mark_graded_todos_done: bool = False
    email_enabled: bool = False
    email_to: str = ""
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: str = "true"
    smtp_username: str = ""
    print_enabled: bool = False
    printer_name: str = ""
    print_copies: int = 1
    schedule_days: list[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])
    morning: str = "06:45"
    evening: str = "18:45"
    run_missed_at_signin: bool = True
    setup_complete: bool = False

    def save_folder(self) -> Path:
        raw = (self.output_dir or "").strip()
        path = Path(raw).expanduser() if raw else default_save_dir()
        return path

    def to_settings(self) -> Settings:
        import os

        start = _as_date(self.start_date, "START_DATE") or default_school_year_start()
        output = self.save_folder()
        port = _as_port(str(self.smtp_port or 587))
        student_id = None
        text = (self.student_user_id or "").strip()
        if text:
            student_id = int(text)
        return Settings(
            base_url=(self.base_url or "").strip().rstrip("/"),
            student_name=(self.student_name or "").strip(),
            school_name=(self.school_name or "").strip(),
            start_date=start,
            timezone=(self.timezone or "America/New_York").strip() or "America/New_York",
            graded_counts_as_submitted=self.graded_counts_as_submitted,
            mark_graded_todos_done=self.mark_graded_todos_done,
            output_dir=output,
            student_user_id=student_id,
            print_enabled=self.print_enabled,
            printer_name=(self.printer_name or "").strip(),
            print_copies=_as_copies(str(self.print_copies or 1)),
            email_enabled=self.email_enabled,
            email_to=(self.email_to or "").strip(),
            email_from=(self.email_from or "").strip(),
            smtp_host=(self.smtp_host or "").strip(),
            smtp_port=port,
            smtp_security=smtp_security(self.smtp_use_tls, port),
            smtp_username=(self.smtp_username or "").strip(),
            smtp_password=os.environ.get("SMTP_PASSWORD") or "",
        )


def _get(parser: ConfigParser, section: str, option: str, fallback: str = "") -> str:
    if parser.has_option(section, option):
        return parser.get(section, option).strip()
    return fallback


def load_config(path: Path | None = None) -> AppConfig:
    parser = ConfigParser()
    target = path or config_path()
    if target.is_file():
        parser.read(target, encoding="utf-8")
    days_raw = _get(parser, "schedule", "days", "mon,tue,wed,thu,fri")
    days = [part.strip().lower() for part in days_raw.split(",") if part.strip()]
    start_default = default_school_year_start().isoformat()
    copies_raw = _get(parser, "print", "copies", "1") or "1"
    port_raw = _get(parser, "email", "smtp_port", "587") or "587"
    try:
        copies = _as_copies(copies_raw)
    except ValueError:
        copies = 1
    try:
        port = _as_port(port_raw)
    except ValueError:
        port = 587
    return AppConfig(
        base_url=_get(parser, "canvas", "base_url"),
        timezone=_get(parser, "canvas", "timezone", "America/New_York") or "America/New_York",
        student_user_id=_get(parser, "canvas", "student_user_id"),
        student_name=_get(parser, "report", "student_name"),
        school_name=_get(parser, "report", "school_name"),
        start_date=_get(parser, "report", "start_date", start_default) or start_default,
        graded_counts_as_submitted=_as_bool(
            _get(parser, "report", "graded_counts_as_submitted", "true"), True
        ),
        output_dir=_get(parser, "report", "output_dir"),
        mark_graded_todos_done=_as_bool(
            _get(parser, "todo", "mark_graded_todos_done", "false"), False
        ),
        email_enabled=_as_bool(_get(parser, "email", "enabled", "false"), False),
        email_to=_get(parser, "email", "to"),
        email_from=_get(parser, "email", "from"),
        smtp_host=_get(parser, "email", "smtp_host"),
        smtp_port=port,
        smtp_use_tls=_get(parser, "email", "smtp_use_tls", "true") or "true",
        smtp_username=_get(parser, "email", "smtp_username"),
        print_enabled=_as_bool(_get(parser, "print", "enabled", "false"), False),
        printer_name=_get(parser, "print", "printer_name"),
        print_copies=copies,
        schedule_days=days or ["mon", "tue", "wed", "thu", "fri"],
        morning=_get(parser, "schedule", "morning", "06:45") or "06:45",
        evening=_get(parser, "schedule", "evening", "18:45") or "18:45",
        run_missed_at_signin=_as_bool(
            _get(parser, "schedule", "run_missed_at_signin", "true"), True
        ),
        setup_complete=_as_bool(_get(parser, "app", "setup_complete", "false"), False),
    )


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Write settings. Refuses to persist a token or SMTP password if one was attached."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    days = [day for day in DAY_ORDER if day in set(config.schedule_days)]
    parser = ConfigParser()
    parser["canvas"] = {
        "base_url": config.base_url.strip().rstrip("/"),
        "timezone": config.timezone.strip() or "America/New_York",
        "student_user_id": config.student_user_id.strip(),
    }
    parser["report"] = {
        "student_name": config.student_name.strip(),
        "school_name": config.school_name.strip(),
        "start_date": config.start_date.strip(),
        "graded_counts_as_submitted": _ini_bool(config.graded_counts_as_submitted),
        "output_dir": str(config.save_folder()),
    }
    parser["todo"] = {
        "mark_graded_todos_done": _ini_bool(config.mark_graded_todos_done),
    }
    parser["email"] = {
        "enabled": _ini_bool(config.email_enabled),
        "to": config.email_to.strip(),
        "from": config.email_from.strip(),
        "smtp_host": config.smtp_host.strip(),
        "smtp_port": str(config.smtp_port or 587),
        "smtp_use_tls": (config.smtp_use_tls or "true").strip(),
        "smtp_username": config.smtp_username.strip(),
    }
    parser["print"] = {
        "enabled": _ini_bool(config.print_enabled),
        "printer_name": config.printer_name.strip(),
        "copies": str(config.print_copies or 1),
    }
    parser["schedule"] = {
        "days": ",".join(days),
        "morning": config.morning.strip() or "06:45",
        "evening": config.evening.strip() or "18:45",
        "run_missed_at_signin": _ini_bool(config.run_missed_at_signin),
    }
    parser["app"] = {"setup_complete": _ini_bool(config.setup_complete)}
    with target.open("w", encoding="utf-8") as handle:
        handle.write(
            "# Canvas Parent Report settings.\n"
            "# The Canvas token and SMTP password are not stored in this file.\n"
        )
        parser.write(handle)
    text = target.read_text(encoding="utf-8").lower()
    if "smtp_password" in text or "canvas_token" in text:
        raise RuntimeError("Refusing to write secrets into config.ini.")
    return target


def load_history(path: Path | None = None) -> list[dict]:
    target = path or history_path()
    if not target.is_file():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def append_history(entry: dict, path: Path | None = None) -> None:
    target = path or history_path()
    rows = load_history(target)
    rows.insert(0, entry)
    del rows[30:]
    target.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def default_start_date() -> date:
    return default_school_year_start()
