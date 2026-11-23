#!/usr/bin/env python3
"""Send the Canvas report PDF by email. Off unless email is enabled.

Uses the Python standard library (smtplib and email.message). The SMTP
password is read from the environment or a gitignored .env file only and is
never printed or written into the message.
"""

from __future__ import annotations

import html
import smtplib
import ssl
import tempfile
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from config import Settings

# A tiny one-page PDF used by --test-email so the check can attach a file
# without calling Canvas or WeasyPrint.
MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 68>>stream
BT /F1 18 Tf 72 720 Td (Canvas report email test) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
%%EOF
"""


@dataclass
class EmailResult:
    ok: bool
    message: str


def split_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _valid_address(value: str) -> bool:
    text = value.strip()
    if "@" not in text or any(ch.isspace() for ch in text):
        return False
    local, _, domain = text.partition("@")
    return bool(local and domain and "." in domain)


def student_label(data: dict[str, Any] | None, settings: Settings) -> str:
    name = ""
    if data:
        name = str(data.get("student") or "").strip()
    if not name:
        name = (settings.student_name or "").strip()
    return name or "Student"


def report_timestamp(data: dict[str, Any] | None, settings: Settings) -> datetime:
    raw = ""
    if data:
        raw = str(data.get("generated_at") or "").strip()
    if raw:
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            when = None
        else:
            if when.tzinfo is None:
                when = when.replace(tzinfo=settings.tzinfo())
            return when.astimezone(settings.tzinfo())
    return datetime.now(settings.tzinfo())


def format_stamp(when: datetime) -> str:
    """Clock time like 'Nov 23, 2026 6:45 AM' without a leading zero on the hour."""
    hour_text = when.strftime("%I").lstrip("0") or "12"
    return f"{when.strftime('%b')} {when.day}, {when.year} {hour_text}:{when.strftime('%M %p')}"


def subject_for(student: str, when: datetime) -> str:
    return f"Canvas report for {student} - {format_stamp(when)}"


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return " ".join(str(value).split())


def summary_rows(data: dict[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source = data or {}
    for item in source.get("missing") or []:
        rows.append(
            {
                "category": "Missing",
                "course": _cell(item.get("course")),
                "assignment": _cell(item.get("assignment")),
                "due": _cell(item.get("due")),
                "score": _cell(item.get("score")),
                "comment": _cell(item.get("comment")),
            }
        )
    for item in source.get("late") or []:
        rows.append(
            {
                "category": "Late",
                "course": _cell(item.get("course")),
                "assignment": _cell(item.get("assignment")),
                "due": _cell(item.get("due")),
                "score": _cell(item.get("score")),
                "comment": _cell(item.get("comment")),
            }
        )
    return rows


def _plain_body(
    data: dict[str, Any] | None,
    student: str,
    when: datetime,
    *,
    test: bool,
) -> str:
    source = data or {}
    rows = summary_rows(source)
    missing_n = sum(1 for row in rows if row["category"] == "Missing")
    late_n = sum(1 for row in rows if row["category"] == "Late")
    lines = [
        f"Canvas missing-work report for {student}",
    ]
    school = str(source.get("school") or "").strip()
    scope = str(source.get("scope") or "").strip()
    if school:
        lines.append(school)
    if scope:
        lines.append(scope)
    lines.append(f"Generated {format_stamp(when)}")
    if test:
        lines.append("")
        lines.append("This is a test message. No Canvas data was fetched.")
    lines.append("")
    lines.append(f"Missing: {missing_n}")
    lines.append(f"Late: {late_n}")
    lines.append("")
    lines.append("| Category | Course | Assignment | Due | Score | Comment |")
    lines.append("|---|---|---|---|---|---|")
    if not rows:
        lines.append("| — | — | — | — | — | No missing or late assignments. |")
    else:
        for row in rows:
            lines.append(
                "| {category} | {course} | {assignment} | {due} | {score} | {comment} |".format(
                    **row
                )
            )
    lines.append("")
    lines.append("The PDF report is attached.")
    return "\n".join(lines) + "\n"


def _html_body(
    data: dict[str, Any] | None,
    student: str,
    when: datetime,
    *,
    test: bool,
) -> str:
    source = data or {}
    rows = summary_rows(source)
    missing_n = sum(1 for row in rows if row["category"] == "Missing")
    late_n = sum(1 for row in rows if row["category"] == "Late")

    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    body_rows = []
    if not rows:
        body_rows.append(
            "<tr><td colspan=\"6\">No missing or late assignments.</td></tr>"
        )
    else:
        for row in rows:
            body_rows.append(
                "<tr>"
                f"<td>{esc(row['category'])}</td>"
                f"<td>{esc(row['course'])}</td>"
                f"<td>{esc(row['assignment'])}</td>"
                f"<td>{esc(row['due'])}</td>"
                f"<td>{esc(row['score'])}</td>"
                f"<td>{esc(row['comment'])}</td>"
                "</tr>"
            )
    school = str(source.get("school") or "").strip()
    scope = str(source.get("scope") or "").strip()
    extras = []
    if school:
        extras.append(f"<p>{esc(school)}</p>")
    if scope:
        extras.append(f"<p>{esc(scope)}</p>")
    if test:
        extras.append("<p>This is a test message. No Canvas data was fetched.</p>")
    table = (
        "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">"
        "<thead><tr>"
        "<th>Category</th><th>Course</th><th>Assignment</th>"
        "<th>Due</th><th>Score</th><th>Comment</th>"
        "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )
    return (
        "<!DOCTYPE html><html><body>"
        f"<p>Canvas missing-work report for {esc(student)}</p>"
        + "".join(extras)
        + f"<p>Generated {esc(format_stamp(when))}</p>"
        f"<p>Missing: {missing_n}<br>Late: {late_n}</p>"
        + table
        + "<p>The PDF report is attached.</p>"
        "</body></html>"
    )


def build_message(
    settings: Settings,
    data: dict[str, Any] | None,
    pdf_path: Path,
    *,
    test: bool = False,
) -> EmailMessage:
    """Build the report message. Raises ValueError if required fields are missing."""
    recipients = split_recipients(settings.email_to)
    missing = []
    if not recipients:
        missing.append("EMAIL_TO")
    elif any(not _valid_address(item) for item in recipients):
        raise ValueError(
            "EMAIL_TO must be one or more email addresses, separated by commas."
        )
    sender = (settings.email_from or "").strip()
    if not sender:
        missing.append("EMAIL_FROM")
    elif not _valid_address(sender):
        raise ValueError("EMAIL_FROM must be an email address.")
    if not (settings.smtp_host or "").strip():
        missing.append("SMTP_HOST")
    if missing:
        raise ValueError(
            "Email settings are incomplete. Set " + ", ".join(missing) + "."
        )
    if not pdf_path.is_file():
        raise ValueError(f"PDF not found: {pdf_path}")

    when = report_timestamp(data, settings)
    student = student_label(data, settings)
    message = EmailMessage()
    message["Subject"] = subject_for(student, when)
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Date"] = format_datetime(when)
    message.set_content(_plain_body(data, student, when, test=test))
    message.add_alternative(_html_body(data, student, when, test=test), subtype="html")
    payload = pdf_path.read_bytes()
    message.add_attachment(
        payload,
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    return message


def _safe_error(exc: BaseException, password: str) -> str:
    text = str(exc) or exc.__class__.__name__
    if password:
        text = text.replace(password, "********")
    return text


def deliver(settings: Settings, message: EmailMessage, *, timeout: float = 30) -> EmailResult:
    """Send an already-built message. Does not raise for SMTP failures."""
    host = (settings.smtp_host or "").strip()
    port = int(settings.smtp_port or 587)
    mode = settings.smtp_security or "starttls"
    username = (settings.smtp_username or "").strip()
    password = settings.smtp_password or ""
    if mode != "plain" and not password and username:
        return EmailResult(
            False,
            "SMTP_PASSWORD is not set. Put it in .env only, then try again.",
        )
    try:
        if mode == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                host, port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        try:
            client.ehlo()
            if mode == "starttls":
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if username:
                client.login(username, password)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError:
        return EmailResult(
            False,
            "SMTP login failed. Check SMTP_USERNAME and SMTP_PASSWORD in .env. "
            "Some school Microsoft 365 accounts have SMTP AUTH turned off.",
        )
    except (OSError, smtplib.SMTPException, TimeoutError) as exc:
        return EmailResult(False, "Could not send email (" + _safe_error(exc, password) + ").")
    except Exception as exc:
        return EmailResult(False, "Could not send email (" + _safe_error(exc, password) + ").")

    recipients = message.get("To", "")
    return EmailResult(True, f"Sent to {recipients}.")


def send_report_email(
    settings: Settings,
    data: dict[str, Any] | None,
    pdf_path: Path,
    *,
    timeout: float = 30,
    test: bool = False,
) -> EmailResult:
    """Build and send the report. Failures are returned, not raised."""
    try:
        message = build_message(settings, data, pdf_path, test=test)
    except (OSError, ValueError) as exc:
        return EmailResult(False, str(exc))
    password = settings.smtp_password or ""
    if _secret_in_visible_text(message, password):
        return EmailResult(
            False,
            "Refusing to send because the SMTP password appeared in the message text.",
        )
    return deliver(settings, message, timeout=timeout)


def _secret_in_visible_text(message: EmailMessage, password: str) -> bool:
    """True when the password shows up in headers or the text body, not the PDF bytes."""
    if not password:
        return False
    for key in ("Subject", "From", "To", "Date"):
        if password in str(message.get(key, "")):
            return True
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_maintype() == "multipart":
            continue
        try:
            content = part.get_content()
        except Exception:
            continue
        if isinstance(content, str) and password in content:
            return True
    return False


def send_test_email(settings: Settings, *, timeout: float = 30) -> EmailResult:
    """Send a short test with a tiny PDF attached. Does not contact Canvas."""
    student = (settings.student_name or "").strip() or "Test"
    now = datetime.now(settings.tzinfo())
    data = {
        "student": student,
        "school": settings.school_name or "",
        "scope": "SMTP test (no Canvas data)",
        "generated_at": now.isoformat(timespec="seconds"),
        "missing": [],
        "late": [],
    }
    handle = tempfile.NamedTemporaryFile(
        prefix="canvas-report-email-test-",
        suffix=".pdf",
        delete=False,
    )
    path = Path(handle.name)
    try:
        handle.write(MINIMAL_PDF)
        handle.close()
        return send_report_email(settings, data, path, timeout=timeout, test=True)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
