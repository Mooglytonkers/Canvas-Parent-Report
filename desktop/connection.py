"""Check a Canvas address and token, and describe problems in plain language."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from canvas_api import CanvasError, CanvasUnauthorized


@dataclass
class ConnectionResult:
    ok: bool
    message: str
    account_name: str = ""
    observees: list[tuple[str, str]] = field(default_factory=list)


def validate_base_url(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return "Enter the school's Canvas address. It looks like https://yourschool.instructure.com."
    if not (text.startswith("https://") or text.startswith("http://")):
        return (
            "That address needs https:// at the front. "
            "For example, https://yourschool.instructure.com."
        )
    if any(ch.isspace() for ch in text):
        return "The address cannot contain spaces."
    parsed = urlparse(text)
    host = parsed.netloc
    if not host or "." not in host or host.startswith("."):
        return (
            "That doesn't look like a full web address. "
            "Use the address you see in the browser while signed in to Canvas."
        )
    return None


def settings_page_url(base_url: str) -> str:
    return base_url.strip().rstrip("/") + "/profile/settings"


def friendly_error(exc: BaseException) -> str:
    """A sentence for a parent. Never includes the token."""
    if isinstance(exc, CanvasUnauthorized):
        return (
            "Canvas rejected that token. Copy it again from Canvas. "
            "If it still fails, the school may have turned off personal access tokens."
        )
    if isinstance(exc, CanvasError):
        if exc.status == 403:
            return (
                "The school accepted the address but blocked this request. "
                "Some schools turn off personal access tokens. "
                "Ask the school whether a parent token is allowed."
            )
        if exc.status is None:
            return (
                "Could not reach Canvas. Check the school address and your internet connection."
            )
        return "Canvas could not complete that request. Check the school address and try again."
    if isinstance(exc, OSError):
        return "No internet connection, or the school address could not be found."
    if isinstance(exc, ValueError):
        text = str(exc).strip()
        if text and "Traceback" not in text and len(text) < 240:
            return text
    return "Something went wrong. The details were saved in the log on this computer."


def test_connection(base_url: str, token: str) -> ConnectionResult:
    problem = validate_base_url(base_url)
    if problem:
        return ConnectionResult(False, problem)
    if not (token or "").strip():
        return ConnectionResult(False, "Paste the access token from Canvas first.")
    from canvas_api import get_json, set_base_url
    from fetch_canvas import display_name, list_observees

    try:
        set_base_url(base_url.strip().rstrip("/"))
        me = get_json("/api/v1/users/self", token=token.strip())
        rows = list_observees(token.strip())
    except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
        return ConnectionResult(False, friendly_error(exc))
    name = display_name(me) if isinstance(me, dict) else ""
    label = name or "your Canvas account"
    observees: list[tuple[str, str]] = []
    for row in rows:
        student_id = str(row.get("id") or "").strip()
        if not student_id:
            continue
        observees.append((student_id, display_name(row) or f"Student {student_id}"))
    if len(observees) > 1:
        message = (
            f"Connected as {label}. This account follows more than one student. "
            "Choose which student the report is for."
        )
    elif len(observees) == 1:
        message = f"Connected as {label}. The report will use {observees[0][1]}."
    else:
        message = f"Connected as {label}."
    return ConnectionResult(True, message, account_name=label, observees=observees)
