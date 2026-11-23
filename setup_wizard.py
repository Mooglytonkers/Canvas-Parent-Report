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


def write_env(token: str, base_url: str) -> None:
    path = HERE / ".env"
    # Keep any other existing keys, but refresh token and base URL.
    existing: dict[str, str] = {}
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.strip().startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            existing[key.strip()] = value
    existing["CANVAS_TOKEN"] = token
    existing["CANVAS_BASE_URL"] = base_url
    lines = [
        "# Local secrets — do not share or commit this file.",
        f"CANVAS_BASE_URL={base_url}",
        f"CANVAS_TOKEN={token}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    say(f"Saved your token to {path} (this file stays on your computer).")


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
) -> None:
    example = HERE / "config.example.ini"
    dest = HERE / "config.ini"
    # Build a complete file from the example comments plus chosen values.
    contents = f"""# Local settings for the Canvas missing-work report.
# This file is listed in .gitignore so it is not published by accident.
# The access token does NOT belong here. Put it in .env or CANVAS_TOKEN.

[canvas]
# Your school's Canvas website, with no trailing slash.
base_url = {base_url}

# Time zone used for due dates and the "generated at" stamp.
# Use a name from the IANA list, for example America/Chicago or America/Los_Angeles.
timezone = {timezone}

# Optional. Only needed if you created the token on a parent/observer account
# and that account is linked to more than one student. Leave blank to auto-detect.
student_user_id = {student_user_id}

[report]
student_name = {student_name}
school_name = {school_name}

# Only include assignments due on or after this date (YYYY-MM-DD).
start_date = {start_date}

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

# Optional. If blank, the start_date above is used. Set an earlier date if
# you also want older graded items marked done.
todo_since_date =

[print]
# Optional. Leave blank to skip printing. Use {{pdf}} as the file path.
# Examples:
#   default                  — Windows default printer, or "lp" on macOS/Linux
#   lp -d PrinterName {{pdf}}
# Or run: python3 run_report.py --print
print_command =

[messages]
# Course-wide Canvas messages are included when they mention a flagged
# assignment, or when they look like a class notice about grades or missing
# work. Edit this comma-separated list if you want different keywords.
notice_keywords = grade, grades, grading, graded, missing, late, failing, failed, failure, deadline, deadlines, d or an f, d or f, emails home, emailing families
"""
    dest.write_text(contents, encoding="utf-8")
    say(f"Wrote {dest}")
    if example.is_file():
        say("You can also look at config.example.ini for comments and options.")


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
    say("Create a Canvas access token: sign in to Canvas, open Account > Settings,")
    say("and click + New Access Token. Paste it below. The characters will not")
    say("appear as you type. Treat this token like a password.")
    token = getpass.getpass("Canvas access token: ").strip()
    if not token:
        say("No token was entered. You can add CANVAS_TOKEN to a .env file later.")
    else:
        write_env(token, base_url)
        if ask_yes("Check the token with Canvas now?", True):
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
