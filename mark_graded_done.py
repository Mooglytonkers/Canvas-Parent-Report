#!/usr/bin/env python3
"""Mark graded Canvas planner / To Do items complete.

Usage:
    python3 mark_graded_done.py
    python3 mark_graded_done.py --since 2026-11-01
    python3 mark_graded_done.py --dry-run

Only writes planner overrides (marked_complete=true). Never submits or
changes assignments or grades. Reads CANVAS_TOKEN from the environment
or a local .env file only.

This feature is meant for a token created on the student's own account.
It is disabled for observer (parent) accounts, because planner overrides
belong to the token owner and would not reliably update the student's
To Do list.

A planner item is eligible when submissions.graded is true, or a score is
present, and the existing planner_override is missing or not already
marked_complete. Existing overrides are updated with PUT; otherwise a new
override is created with POST.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import date, datetime

from canvas_api import (
    CanvasError,
    CanvasUnauthorized,
    handle_cli_error,
    paginate,
    request,
    token_from_env,
)
from config import load_settings, require_base_url, Settings
from fetch_canvas import resolve_identity


def parse_since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def is_graded(item: dict) -> bool:
    sub = item.get("submissions")
    if not isinstance(sub, dict):
        return False
    if sub.get("graded") is True:
        return True
    if sub.get("score") is not None:
        return True
    return False


def already_complete(item: dict) -> bool:
    override = item.get("planner_override")
    return isinstance(override, dict) and override.get("marked_complete") is True


def override_id(item: dict) -> int | None:
    override = item.get("planner_override")
    if isinstance(override, dict) and override.get("id") is not None:
        return int(override["id"])
    return None


def plannable(item: dict) -> tuple[str | None, int | None, str]:
    ptype = item.get("plannable_type")
    pid = item.get("plannable_id")
    plannable_obj = item.get("plannable") or {}
    title = (plannable_obj.get("title") or plannable_obj.get("name") or "").strip()
    return (str(ptype) if ptype else None, int(pid) if pid is not None else None, title)


def fetch_items(since: date, until: date, token: str) -> list[dict]:
    return paginate(
        "/api/v1/planner/items",
        params={
            "start_date": since.isoformat(),
            "end_date": until.isoformat(),
            "per_page": 100,
        },
        token=token,
    )


def mark_item(item: dict, token: str) -> None:
    existing = override_id(item)
    if existing is not None:
        request(
            "PUT",
            f"/api/v1/planner/overrides/{existing}",
            body={"marked_complete": True},
            token=token,
        )
        return
    ptype, pid, _title = plannable(item)
    if not ptype or pid is None:
        raise CanvasError(None, "planner item is missing plannable_type or plannable_id")
    request(
        "POST",
        "/api/v1/planner/overrides",
        body={
            "plannable_type": ptype,
            "plannable_id": pid,
            "marked_complete": True,
        },
        token=token,
    )


def run(settings: Settings, since: date, dry_run: bool) -> int:
    require_base_url(settings)
    token = token_from_env()
    identity = resolve_identity(token, settings)
    if identity.get("mode") == "observer":
        print(
            "Skipped marking To Do items done: this token belongs to an observer "
            "(parent) account. Planner checkmarks would apply to the parent, not "
            "the student. Use a token created while logged in as the student to "
            "enable this option.",
            file=sys.stderr,
        )
        return 0

    until = datetime.now(settings.tzinfo()).date()
    items = fetch_items(since, until, token)

    already = 0
    eligible: list[dict] = []
    for item in items:
        if not is_graded(item):
            continue
        if already_complete(item):
            already += 1
            continue
        ptype, pid, _title = plannable(item)
        if not ptype or pid is None:
            continue
        eligible.append(item)

    if dry_run:
        print(
            f"Would mark {len(eligible)} To Do item"
            f"{'' if len(eligible) == 1 else 's'} done "
            f"({already} already complete, since {since.isoformat()})."
        )
        return 0

    marked = 0
    errors: list[str] = []
    for item in eligible:
        _ptype, pid, title = plannable(item)
        label = title or f"plannable {pid}"
        try:
            mark_item(item, token)
            marked += 1
        except CanvasUnauthorized:
            raise
        except CanvasError as exc:
            errors.append(f"{label}: {exc}")

    print(
        f"Marked {marked} To Do item{'' if marked == 1 else 's'} done "
        f"({already} already complete, {len(errors)} error"
        f"{'' if len(errors) == 1 else 's'}, since {since.isoformat()})."
    )
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mark graded Canvas planner items complete (overrides only)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.ini (default: config.ini next to this script)",
    )
    parser.add_argument(
        "--since",
        type=parse_since,
        default=None,
        help="Start date (YYYY-MM-DD) for the planner window "
        "(default: todo_since_date or start_date from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List how many items would be marked, without writing any overrides",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        since = args.since or settings.todo_since()
        return run(settings, since, args.dry_run)
    except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
        return handle_cli_error(exc)


if __name__ == "__main__":
    sys.exit(main())
