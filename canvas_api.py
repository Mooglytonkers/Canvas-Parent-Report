#!/usr/bin/env python3
"""Shared Canvas API client.

Reads CANVAS_TOKEN from the environment (or a local .env loaded by config.py).
Never prints, logs, or writes the token value.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "CanvasParentReport/1.0"
TIMEOUT_SEC = 45
MAX_RETRIES = 5

LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"', re.I)

_base_url: str | None = None


class CanvasError(Exception):
    """Request failed for a reason other than a missing token."""

    def __init__(self, status: int | None, message: str) -> None:
        self.status = status
        super().__init__(message)


class CanvasUnauthorized(CanvasError):
    """401 — token missing from Canvas's point of view (revoked or expired)."""


def set_base_url(url: str) -> None:
    """Set the Canvas site URL, for example https://yourschool.instructure.com."""
    global _base_url
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        raise CanvasError(None, "CANVAS_BASE_URL is empty.")
    if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
        raise CanvasError(
            None,
            "CANVAS_BASE_URL must start with https:// (for example "
            "https://yourschool.instructure.com).",
        )
    _base_url = cleaned


def get_base_url() -> str:
    if _base_url:
        return _base_url
    env = (os.environ.get("CANVAS_BASE_URL") or "").strip()
    if env:
        set_base_url(env)
        return _base_url or env.rstrip("/")
    raise CanvasError(
        None,
        "CANVAS_BASE_URL is not set. Add it to config.ini, .env, or your environment.",
    )


def token_from_env() -> str:
    value = os.environ.get("CANVAS_TOKEN")
    if value is None or not str(value).strip():
        print(
            "error: CANVAS_TOKEN is not set. "
            "Add a Canvas personal access token to your .env file or environment "
            "and try again.",
            file=sys.stderr,
        )
        sys.exit(1)
    return str(value).strip()


def _encode_query(params: dict[str, Any] | list[tuple[str, Any]] | None) -> str:
    if not params:
        return ""
    if isinstance(params, dict):
        pairs: list[tuple[str, str]] = []
        for key, val in params.items():
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    pairs.append((key, str(item)))
            elif isinstance(val, bool):
                pairs.append((key, "true" if val else "false"))
            else:
                pairs.append((key, str(val)))
    else:
        pairs = [(k, str(v)) for k, v in params if v is not None]
    return urllib.parse.urlencode(pairs)


def request(
    method: str,
    path: str,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    base_url: str | None = None,
) -> tuple[Any, str, int]:
    """GET/POST/PUT a Canvas path. `path` may be a path or a full URL.

    Returns (parsed JSON or None, Link header, status).
    Raises CanvasUnauthorized on 401 and CanvasError on other failures.
    """
    auth = token if token is not None else token_from_env()
    root = (base_url or get_base_url()).rstrip("/")
    url = path if path.startswith("http") else root + "/" + path.lstrip("/")
    query = _encode_query(params)
    if query:
        url += ("&" if "?" in url else "?") + query

    data = None
    headers = {
        "Authorization": "Bearer " + auth,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(
                req, context=ssl.create_default_context(), timeout=TIMEOUT_SEC
            ) as resp:
                raw = resp.read()
                link = resp.headers.get("Link") or resp.headers.get("link") or ""
                parsed = json.loads(raw) if raw else None
                return parsed, link, resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            # Drain the body so the connection can close; never log headers
            # (they may include Authorization).
            try:
                err_raw = exc.read()
            except Exception:
                err_raw = b""
            if status == 401:
                raise CanvasUnauthorized(
                    401,
                    "Canvas API returned 401 Unauthorized. The access token "
                    "looks revoked or expired, or the school may have disabled "
                    "personal access tokens. Update CANVAS_TOKEN and try again.",
                ) from None
            if status in (429, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = max(1.0, float(retry_after)) if retry_after else 2.0 * (attempt + 1)
                except ValueError:
                    wait = 2.0 * (attempt + 1)
                time.sleep(wait)
                last_error = exc
                continue
            detail = ""
            if err_raw:
                try:
                    payload = json.loads(err_raw)
                    if isinstance(payload, dict):
                        detail = str(
                            payload.get("errors")
                            or payload.get("message")
                            or payload.get("error")
                            or ""
                        )
                    elif isinstance(payload, list):
                        detail = "; ".join(str(x) for x in payload[:3])
                except Exception:
                    detail = ""
            extra = f" ({detail})" if detail else ""
            raise CanvasError(status, f"Canvas API returned HTTP {status}{extra}.") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < MAX_RETRIES - 1 and not isinstance(exc, json.JSONDecodeError):
                time.sleep(2.0 * (attempt + 1))
                last_error = exc
                continue
            raise CanvasError(
                None, f"Canvas API request failed: {exc.__class__.__name__}."
            ) from None
    raise CanvasError(
        None,
        "Canvas API request failed after retries: "
        f"{last_error.__class__.__name__ if last_error else 'unknown'}.",
    )


def get_json(
    path: str,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    token: str | None = None,
) -> Any:
    parsed, _, _ = request("GET", path, params=params, token=token)
    return parsed


def paginate(
    path: str,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    token: str | None = None,
    page_limit: int = 50,
) -> list[Any]:
    """Follow Link-header pagination and return the combined list."""
    items: list[Any] = []
    parsed, link, _ = request("GET", path, params=params, token=token)
    if isinstance(parsed, list):
        items.extend(parsed)
    elif parsed is not None:
        return [parsed]
    pages = 1
    while link and pages < page_limit:
        match = LINK_NEXT.search(link)
        if not match:
            break
        parsed, link, _ = request("GET", match.group(1), token=token)
        pages += 1
        if isinstance(parsed, list):
            items.extend(parsed)
        elif parsed is None:
            break
        else:
            items.append(parsed)
            break
    return items


def handle_cli_error(exc: BaseException) -> int:
    """Print a safe error message and return an exit code. Never prints the token."""
    if isinstance(exc, CanvasUnauthorized):
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if isinstance(exc, CanvasError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
    return 1
