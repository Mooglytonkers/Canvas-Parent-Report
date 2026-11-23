#!/usr/bin/env python3
"""Interactive setup for the Canvas missing-work report.

Walks a parent through checking Python, installing packages, creating
config.ini and a gitignored .env file, and optionally verifying the
Canvas token. The token is typed with hidden input and is never printed.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_PY = (3, 9)


def say(text: str = "") -> None:
    print(text)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return value or default


def ask_yes(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    value = ask(f"{prompt} ({hint})", "")
    if not value:
        return default
    return value.lower() in ("y", "yes", "1", "true")


def python_ok() -> bool:
    return sys.version_info >= MIN_PY


def run_pip() -> bool:
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(HERE / "requirements.txt")]
    say("Installing Python packages (this may take a minute)...")
    try:
        result = subprocess.run(cmd, cwd=str(HERE))
    except OSError as exc:
        say(f"Could not run pip ({exc}). You can install later with:")
        say("  " + " ".join(cmd))
        return False
    if result.returncode != 0:
        say("Package install had a problem. You can try again later, or keep going.")
        say("If PDF generation fails, see the WeasyPrint notes in the README.")
        return False
    say("Packages installed.")
    return True


def _env_format(value: str) -> str:
    if any(ch.isspace() for ch in value) or "#" in value:
        if "'" not in value:
            return "'" + value + "'"
        if '"' not in value:
            return '"' + value + '"'
    return value


def read_env_file(path: Path) -> dict[str, str]:
    existing: dict[str, str] = {}
    if not path.is_file():
        return existing
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        existing[key] = text
    return existing


def write_env(updates: dict[str, str], dest_dir: Path | None = None) -> Path:
    """Merge keys into .env. Values are not printed."""
    root = dest_dir or HERE
    path = root / ".env"
    existing = read_env_file(path)
    existing.update(updates)
    preferred = [
        "CANVAS_BASE_URL",
        "CANVAS_TOKEN",
        "EMAIL_ENABLED",
        "EMAIL_TO",
        "EMAIL_FROM",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USE_TLS",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "PRINT_ENABLED",
        "PRINTER_NAME",
        "PRINT_COPIES",
    ]
    ordered = [key for key in preferred if key in existing]
    ordered.extend(key for key in existing if key not in ordered)
    lines = ["# Local secrets — do not share or commit this file."]
    for key in ordered:
        lines.append(f"{key}={_env_format(existing[key])}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _ini_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def render_config(
    *,
    base_url: str,
    student_name: str,
    school_name: str,
    start_date: str,
    timezone: str,
    graded: bool,
    mark_todos: bool,
    student_user_id: str,
    email_enabled: bool = False,
    email_to: str = "",
    email_from: str = "",
    smtp_host: str = "",
    smtp_port: str = "587",
    smtp_use_tls: str = "true",
    print_enabled: bool = False,
    printer_name: str = "",
    print_copies: str = "1",
) -> str:
    """Config text. SMTP_USERNAME and SMTP_PASSWORD are never included."""
    return f"""# Local settings for the Canvas missing-work report.
# This file is listed in .gitignore so it is not published by accident.
# The access token does NOT belong here. Put it in .env or CANVAS_TOKEN.
# SMTP_USERNAME and SMTP_PASSWORD do NOT belong here. Put them in .env only.

[canvas]
# Your school's Canvas website, with no trailing slash.
base_url = {_ini_line(base_url)}

# Time zone used for due dates and the "generated at" stamp.
# Use a name from the IANA list, for example America/Chicago or America/Los_Angeles.
timezone = {_ini_line(timezone)}

# Optional. Only needed if you created the token on a parent/observer account
# and that account is linked to more than one student. Leave blank to auto-detect.
student_user_id = {_ini_line(student_user_id)}

[report]
student_name = {_ini_line(student_name)}
school_name = {_ini_line(school_name)}

# Only include assignments due on or after this date (YYYY-MM-DD).
start_date = {_ini_line(start_date)}

# If true, any graded item is treated as submitted and is left off the
# missing list (a LATE flag can still appear).
graded_counts_as_submitted = {"true" if graded else "false"}

# Where JSON and PDF files are written.
output_dir = output

[todo]
# If true, after each report the script marks graded items done on the
# student's Canvas To Do list. This only changes checkmarks; it does not
# submit work or change grades. Default is false. Requires a token created
# on the student's own account (not an observer/parent token).
mark_graded_todos_done = {"true" if mark_todos else "false"}

# TODO_DETAIL_PAGE. Off by default. Adds one card per open To Do item.
todo_detail_page = false

# TODO_DAYS_AHEAD. Days ahead to include, besides overdue work from start_date.
todo_days_ahead = 14

# Optional. If blank, the start_date above is used. Set an earlier date if
# you also want older graded items marked done.
todo_since_date =

[email]
# EMAIL_ENABLED. Off by default. The PDF is emailed only when this is true.
enabled = {"true" if email_enabled else "false"}

# EMAIL_TO. Comma-separated addresses.
to = {_ini_line(email_to)}

# EMAIL_FROM. Address the message is sent from.
from = {_ini_line(email_from)}

# SMTP_HOST, SMTP_PORT (default 587), SMTP_USE_TLS (true means STARTTLS).
# Port 465 uses SSL. See the README for Gmail and Outlook examples.
smtp_host = {_ini_line(smtp_host)}
smtp_port = {_ini_line(smtp_port) or "587"}
smtp_use_tls = {_ini_line(smtp_use_tls) or "true"}

# SMTP_USERNAME and SMTP_PASSWORD are stored in .env only, never in this file.

[print]
# PRINT_ENABLED. Off by default.
enabled = {"true" if print_enabled else "false"}

# PRINTER_NAME. Leave blank for the system default printer.
printer_name = {_ini_line(printer_name)}

# PRINT_COPIES. Default 1. One job is sent at a time.
copies = {_ini_line(print_copies) or "1"}

# Optional custom command. Leave blank to use the built-in printer support.
# Use {{pdf}} as the file path, for example: lp -d PrinterName {{pdf}}
print_command =

[messages]
# Course-wide Canvas messages are included when they mention a flagged
# assignment, or when they look like a class notice about grades or missing
# work. Edit this comma-separated list if you want different keywords.
notice_keywords = grade, grades, grading, graded, missing, late, failing, failed, failure, deadline, deadlines, d or an f, d or f, emails home, emailing families
"""


def write_config(
    *,
    base_url: str,
    student_name: str,
    school_name: str,
    start_date: str,
    timezone: str,
    graded: bool,
    mark_todos: bool,
    student_user_id: str,
    email_enabled: bool = False,
    email_to: str = "",
    email_from: str = "",
    smtp_host: str = "",
    smtp_port: str = "587",
    smtp_use_tls: str = "true",
    print_enabled: bool = False,
    printer_name: str = "",
    print_copies: str = "1",
    dest_dir: Path | None = None,
) -> Path:
    root = dest_dir or HERE
    example = root / "config.example.ini"
    if not example.is_file():
        example = HERE / "config.example.ini"
    dest = root / "config.ini"
    dest.write_text(
        render_config(
            base_url=base_url,
            student_name=student_name,
            school_name=school_name,
            start_date=start_date,
            timezone=timezone,
            graded=graded,
            mark_todos=mark_todos,
            student_user_id=student_user_id,
            email_enabled=email_enabled,
            email_to=email_to,
            email_from=email_from,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_use_tls=smtp_use_tls,
            print_enabled=print_enabled,
            printer_name=printer_name,
            print_copies=print_copies,
        ),
        encoding="utf-8",
    )
    say(f"Wrote {dest}")
    if example.is_file():
        say("You can also look at config.example.ini for comments and options.")
    return dest


def verify_token(base_url: str, token: str) -> bool:
    say("Checking the token with Canvas (the token itself will not be printed)...")
    env = os.environ.copy()
    env["CANVAS_BASE_URL"] = base_url
    env["CANVAS_TOKEN"] = token
    code = r"""
import os, sys
sys.path.insert(0, os.environ.get("CPR_ROOT", "."))
from canvas_api import set_base_url, get_json, CanvasUnauthorized, CanvasError, token_from_env
set_base_url(os.environ["CANVAS_BASE_URL"])
token = token_from_env()
try:
    me = get_json("/api/v1/users/self", token=token)
except CanvasUnauthorized as exc:
    print("TOKEN_STATUS=401")
    print(str(exc))
    sys.exit(2)
except CanvasError as exc:
    print("TOKEN_STATUS=error")
    print(str(exc))
    sys.exit(1)
name = (me or {}).get("short_name") or (me or {}).get("name") or "this Canvas account"
print("TOKEN_STATUS=ok")
print("Signed in as: " + name)
# List observees without failing the check if the endpoint is unavailable.
try:
    from canvas_api import paginate
    rows = paginate("/api/v1/users/self/observees", params={"per_page": 100}, token=token)
except Exception:
    rows = []
if rows:
    print("Observed students:")
    for row in rows:
        label = (row.get("short_name") or row.get("name") or "").strip() or "(no name)"
        print(f"  {row.get('id')}  {label}")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(HERE),
            env={**env, "CPR_ROOT": str(HERE)},
            check=False,
        )
    except OSError as exc:
        say(f"Could not verify the token ({exc}). You can test later with a regular run.")
        return False
    if result.returncode == 2:
        say(
            "Canvas rejected the token (401). It may be expired, revoked, or typed "
            "incorrectly, or the school may have disabled personal access tokens."
        )
        return False
    if result.returncode != 0:
        say("The check did not succeed. You can still save your settings and try a full run later.")
        return False
    say("Token looks good.")
    return True


def main() -> int:
    say("Canvas missing-work report — setup")
    say("==================================")
    say("This wizard saves settings on your computer. Your access token is")
    say("stored only in a private .env file and is never printed.")
    say()

    if not python_ok():
        say(
            f"This project needs Python {MIN_PY[0]}.{MIN_PY[1]} or newer. "
            f"You are running {sys.version.split()[0]}."
        )
        say("Install a newer Python from https://www.python.org/downloads/ and try again.")
        return 1
    say(f"Python {sys.version.split()[0]} is fine.")

    if ask_yes("Install required Python packages now?", True):
        run_pip()
    else:
        say("Skipping package install. Run this later:")
        say(f"  {sys.executable} -m pip install -r \"{HERE / 'requirements.txt'}\"")

    say()
    say("Your school's Canvas address looks like:")
    say("  https://yourschool.instructure.com")
    say("You can copy it from the browser while signed in to Canvas.")
    base_url = ask("Canvas website").rstrip("/")
    while not (base_url.startswith("https://") or base_url.startswith("http://")):
        say("Please include https:// at the front.")
        base_url = ask("Canvas website").rstrip("/")

    student_name = ask("Student's name (shown on the PDF)", "Alex Sample")
    school_name = ask("School name (shown on the PDF)", "Example High School")
    from datetime import date as _date
    _today = _date.today()
    _year = _today.year if _today.month >= 8 else _today.year - 1
    _default_start = f"{_year}-08-01"
    start_date = ask("Only include work due on or after this date (YYYY-MM-DD)", _default_start)
    timezone = ask("Time zone", "America/New_York")
    say()
    say("If an assignment already has a grade, should it be treated as submitted")
    say("and left off the missing list? (A late flag can still appear.)")
    graded = ask_yes("Treat graded work as submitted?", True)
    say()
    say("Optionally, after each report, mark graded items done on the student's")
    say("Canvas To Do list. This only changes checkmarks — it does not submit")
    say("work or change grades. It needs a token from the student's account,")
    say("not a parent/observer token. Recommended: leave this off until you")
    say("have looked at a report.")
    mark_todos = ask_yes("Mark graded To Do items done after each report?", False)
    student_user_id = ask(
        "Canvas student user ID (leave blank unless you use a parent account linked to more than one student)",
        "",
    )

    say()
    say("Optional: email the PDF after each report (EMAIL_ENABLED). This stays")
    say("off unless you turn it on. The SMTP password is saved only in .env")
    say("and is never written to config.ini or printed.")
    email_enabled = ask_yes("Email the report after each run?", False)
    email_to = ""
    email_from = ""
    smtp_host = ""
    smtp_port = "587"
    smtp_use_tls = "true"
    smtp_username = ""
    smtp_password = ""
    if email_enabled:
        email_to = ask("EMAIL_TO, comma-separated addresses")
        email_from = ask("EMAIL_FROM address")
        say("Gmail: smtp.gmail.com port 587, with an App Password.")
        say("Outlook / Microsoft 365: smtp.office365.com port 587.")
        say("Port 465 uses SSL instead of STARTTLS.")
        smtp_host = ask("SMTP_HOST", "smtp.gmail.com")
        smtp_port = ask("SMTP_PORT", "587") or "587"
        if smtp_port.strip() == "465":
            smtp_use_tls = "ssl"
            say("Port 465 selected, so SMTP_USE_TLS is set to ssl.")
        else:
            use_tls = ask_yes("SMTP_USE_TLS (STARTTLS)?", True)
            smtp_use_tls = "true" if use_tls else "false"
        smtp_username = ask("SMTP_USERNAME (usually the mailbox address)")
        smtp_password = getpass.getpass(
            "SMTP_PASSWORD (hidden, stored only in .env): "
        ).strip()

    say()
    say("Optional: print the PDF after each report (PRINT_ENABLED). This stays")
    say("off unless you turn it on. On Windows, SumatraPDF is the most reliable")
    say("way to print silently. Leave the printer name blank for the default.")
    print_enabled = ask_yes("Print the report after each run?", False)
    printer_name = ""
    print_copies = "1"
    if print_enabled:
        printer_name = ask("PRINTER_NAME (blank for the system default)", "")
        print_copies = ask("PRINT_COPIES", "1") or "1"

    say()
    say("Create a Canvas access token: sign in to Canvas, open Account > Settings,")
    say("and click + New Access Token. Paste it below. The characters will not")
    say("appear as you type. Treat this token like a password.")
    token = getpass.getpass("Canvas access token: ").strip()
    if not token:
        say("No token was entered. You can add CANVAS_TOKEN to a .env file later.")
    env_updates: dict[str, str] = {}
    if token:
        env_updates["CANVAS_TOKEN"] = token
        env_updates["CANVAS_BASE_URL"] = base_url
    if email_enabled:
        env_updates["SMTP_USERNAME"] = smtp_username
        env_updates["SMTP_PASSWORD"] = smtp_password
    if env_updates:
        env_path = write_env(env_updates)
        if token:
            say(f"Saved your token to {env_path} (this file stays on your computer).")
        if email_enabled:
            say("Saved the SMTP username and password in .env only (not in config.ini).")
        if token and ask_yes("Check the token with Canvas now?", True):
            verify_token(base_url, token)

    write_config(
        base_url=base_url,
        student_name=student_name,
        school_name=school_name,
        start_date=start_date,
        timezone=timezone,
        graded=graded,
        mark_todos=mark_todos,
        student_user_id=student_user_id,
        email_enabled=email_enabled,
        email_to=email_to,
        email_from=email_from,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_use_tls=smtp_use_tls,
        print_enabled=print_enabled,
        printer_name=printer_name,
        print_copies=print_copies,
    )

    py = sys.executable
    say()
    say("Setup is complete. Next, try a test run:")
    say(f'  "{py}" "{HERE / "run_report.py"}"')
    say()
    say("On Windows you can also double-click run_report.bat, or from PowerShell:")
    say("  .\\run_report.ps1")
    say("On macOS or Linux:")
    say("  ./run_report.sh")
    say()
    say("See the README for how to run this automatically twice a day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
