#!/usr/bin/env python3
"""Optional To Do detail pages. Read-only. Off unless TODO_DETAIL_PAGE is on.

The window is overdue work due on or after the report start date, plus items
due in the next TODO_DAYS_AHEAD days (default 14). Upcoming items are split
into the rest of this calendar week and later days inside that window.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any

from make_report import parse_datetime

STATUS_LABEL = {
    "overdue": "Overdue",
    "this_week": "Due this week",
    "later": "Due later",
}

TYPE_LABEL = {
    "assignment": "Assignment",
    "quiz": "Quiz",
    "discussion_topic": "Discussion",
    "wiki_page": "Page",
    "planner_note": "To do",
    "announcement": "Announcement",
    "calendar_event": "Event",
}

SUBMISSION_LABEL = {
    "online_text_entry": "online text",
    "online_url": "website URL",
    "online_upload": "file upload",
    "online_quiz": "quiz",
    "media_recording": "media recording",
    "student_annotation": "annotation",
    "discussion_topic": "discussion",
    "on_paper": "on paper",
    "none": "no submission",
    "external_tool": "external tool",
    "online": "online",
}


def strip_html(value: object, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def bucket_for(due: datetime, now: datetime, start: date, days_ahead: int) -> str | None:
    """Return overdue, this_week, later, or None when the item is outside the window."""
    if due.date() < start:
        return None
    if due < now:
        return "overdue"
    horizon = now.date() + timedelta(days=max(0, days_ahead))
    if due.date() > horizon:
        return None
    days_until_sunday = (6 - now.weekday()) % 7
    week_end = now.date() + timedelta(days=days_until_sunday)
    if due.date() <= week_end:
        return "this_week"
    return "later"


def window_label(start: date, days_ahead: int, now: datetime) -> str:
    end = now.date() + timedelta(days=days_ahead)
    return (
        f"Overdue items due {start.strftime('%b')} {start.day}, {start.year} onward, "
        f"plus work due in the next {days_ahead} days "
        f"(through {end.strftime('%b')} {end.day}, {end.year})."
    )


def format_due_label(when: datetime) -> str:
    hour = when.strftime("%I").lstrip("0") or "12"
    return (
        f"{when.strftime('%a')}, {when.strftime('%b')} {when.day}, {when.year} "
        f"at {hour}:{when.strftime('%M %p')}"
    )


def _course_id(item: dict[str, Any]) -> int | None:
    if item.get("course_id"):
        return int(item["course_id"])
    if str(item.get("context_type") or "") == "Course" and item.get("context_id"):
        return int(item["context_id"])
    code = str(item.get("context_code") or "")
    if code.startswith("course_"):
        try:
            return int(code.split("_", 1)[1])
        except ValueError:
            return None
    return None


def _assignment_id(item: dict[str, Any]) -> int | None:
    plannable = item.get("plannable") or {}
    kind = str(item.get("plannable_type") or "")
    raw = None
    if kind == "assignment":
        raw = item.get("plannable_id") or plannable.get("id")
    else:
        raw = plannable.get("assignment_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_finished(item: dict[str, Any]) -> bool:
    override = item.get("planner_override") or {}
    if isinstance(override, dict) and override.get("marked_complete"):
        return True
    submissions = item.get("submissions")
    if isinstance(submissions, dict) and submissions.get("submitted"):
        return True
    if item.get("submitted") is True:
        return True
    return False


def _due_of(item: dict[str, Any], zone) -> datetime | None:
    plannable = item.get("plannable") or {}
    raw = (
        plannable.get("due_at")
        or item.get("plannable_date")
        or item.get("todo_date")
        or plannable.get("todo_date")
    )
    if not raw:
        return None
    when = parse_datetime(str(raw), zone)
    if when is None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw)):
        year, month, day = (int(part) for part in str(raw).split("-"))
        when = datetime(year, month, day, 23, 59, tzinfo=zone)
    return when


def _submission_phrase(types: object) -> str:
    if not isinstance(types, list) or not types:
        return ""
    labels = [SUBMISSION_LABEL.get(str(item), str(item).replace("_", " ")) for item in types]
    return ", ".join(labels)


def _rubric_headline(assignment: dict[str, Any] | None) -> str:
    if not assignment:
        return ""
    rubric = assignment.get("rubric") or []
    if not isinstance(rubric, list) or not rubric:
        return ""
    first = rubric[0] if isinstance(rubric[0], dict) else {}
    title = str(first.get("description") or first.get("ratings", [{}])[0].get("description") or "").strip()
    count = len(rubric)
    word = "criterion" if count == 1 else "criteria"
    if title:
        return f"Rubric: {strip_html(title, 120)} ({count} {word})"
    return f"Rubric: {count} {word}"


def empty_todo_details(settings, now: datetime | None = None) -> dict[str, Any]:
    zone = settings.tzinfo()
    moment = now or datetime.now(zone)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return {
        "enabled": True,
        "window_label": window_label(settings.start_date, settings.todo_days_ahead, moment),
        "observer_note": "",
        "overdue": [],
        "this_week": [],
        "later": [],
    }


def group_cards(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {"overdue": [], "this_week": [], "later": []}
    order = {"overdue": 0, "this_week": 1, "later": 2}
    for card in sorted(cards, key=lambda row: (order.get(row.get("status"), 9), row.get("due_sort") or "")):
        status = card.get("status")
        if status in grouped:
            grouped[status].append(card)
    return grouped


def build_card(
    *,
    status: str,
    kind: str,
    course: str,
    title: str,
    due: datetime | None,
    points: object,
    submission_types: object,
    html_url: str,
    locked_until: str,
    description: str,
    rubric: str,
    messages: list[str],
) -> dict[str, Any]:
    point_text = ""
    if points not in (None, ""):
        point_text = str(points).rstrip("0").rstrip(".") if isinstance(points, float) else str(points)
        point_text = f"{point_text} points" if point_text else ""
    parts = [part for part in (point_text, _submission_phrase(submission_types)) if part]
    return {
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "type_label": TYPE_LABEL.get(kind, kind.replace("_", " ").title() or "Item"),
        "course": course or "Course",
        "title": title or "Untitled",
        "due_label": format_due_label(due) if due else "No due date",
        "due_sort": due.isoformat() if due else "",
        "meta": " · ".join(parts),
        "html_url": html_url or "",
        "locked_until": locked_until or "",
        "description": description or "",
        "rubric": rubric or "",
        "messages": [line for line in messages if line] or [],
    }


def fetch_todo_details(settings, token: str, student_id: int | None, account_mode: str, course_ids: list[int]) -> dict[str, Any]:
    """Read planner items and related read-only Canvas data. Never writes."""
    from canvas_api import CanvasError, get_json, paginate
    from fetch_canvas import fetch_conversation, fetch_conversations, fetch_planner_items, fetch_submission

    zone = settings.tzinfo()
    now = datetime.now(zone)
    payload = empty_todo_details(settings, now)
    end = now.date() + timedelta(days=settings.todo_days_ahead)
    try:
        planner = fetch_planner_items(settings.start_date, end, token, student_id, course_ids)
    except CanvasError:
        planner = []

    observer_note = ""
    conversations: list[dict[str, Any]] = []
    try:
        conversations = fetch_conversations(token)
    except CanvasError:
        if account_mode == "observer":
            observer_note = (
                "Canvas inbox conversations were not available for this parent account, "
                "so those messages are not listed."
            )
        conversations = []

    announcements: list[dict[str, Any]] = []
    codes = [("context_codes[]", f"course_{cid}") for cid in course_ids]
    if codes:
        try:
            announcements = paginate("/api/v1/announcements", params=[*codes, ("per_page", "50")], token=token)
        except CanvasError:
            announcements = []

    cards: list[dict[str, Any]] = []
    for item in planner:
        if not isinstance(item, dict) or _is_finished(item):
            continue
        due = _due_of(item, zone)
        if due is None:
            continue
        status = bucket_for(due, now, settings.start_date, settings.todo_days_ahead)
        if status is None:
            continue
        plannable = item.get("plannable") or {}
        kind = str(item.get("plannable_type") or "assignment")
        course_id = _course_id(item)
        assignment_id = _assignment_id(item)
        course_name = str(item.get("context_name") or plannable.get("course_name") or "Course")
        title = str(plannable.get("title") or item.get("title") or "Untitled")
        assignment: dict[str, Any] | None = None
        if course_id and assignment_id:
            try:
                loaded = get_json(
                    f"/api/v1/courses/{course_id}/assignments/{assignment_id}",
                    token=token,
                )
                assignment = loaded if isinstance(loaded, dict) else None
            except CanvasError:
                assignment = None
        html_url = ""
        points = None
        submission_types: object = []
        description = ""
        locked_until = ""
        if assignment:
            html_url = str(assignment.get("html_url") or "")
            points = assignment.get("points_possible")
            submission_types = assignment.get("submission_types") or []
            description = strip_html(assignment.get("description") or "")
            unlock = assignment.get("unlock_at")
            if unlock:
                unlock_dt = parse_datetime(str(unlock), zone)
                if unlock_dt and unlock_dt > now:
                    locked_until = f"Locked until {format_due_label(unlock_dt)}"
        if not html_url:
            html_url = str(item.get("html_url") or plannable.get("html_url") or "")
        if not description:
            description = strip_html(plannable.get("description") or item.get("description") or "")

        messages: list[str] = []
        if course_id and assignment_id:
            submission = fetch_submission(course_id, assignment_id, token, student_id)
            comments = (submission or {}).get("submission_comments") or []
            if isinstance(comments, list):
                for comment in comments:
                    if not isinstance(comment, dict):
                        continue
                    author = str(comment.get("author_name") or "Teacher").strip()
                    body = strip_html(comment.get("comment") or "", 240)
                    if body:
                        messages.append(f"{author} — {body}")
        title_key = title.casefold()
        for preview in conversations:
            if not isinstance(preview, dict):
                continue
            blob = " ".join(
                str(preview.get(key) or "")
                for key in ("subject", "last_message", "workflow_state")
            )
            if title_key and title_key in blob.casefold():
                subject = strip_html(preview.get("subject") or "Message", 160)
                if subject and subject not in messages:
                    messages.append(subject)
                continue
            conv_id = preview.get("id")
            if not conv_id or not title_key:
                continue
            full = fetch_conversation(int(conv_id), token)
            if not full:
                continue
            full_blob = strip_html(str(full), 2000).casefold()
            if title_key in full_blob:
                subject = strip_html(full.get("subject") or preview.get("subject") or "Message", 160)
                if subject:
                    messages.append(subject)
        for announcement in announcements:
            if not isinstance(announcement, dict):
                continue
            context = str(announcement.get("context_code") or "")
            if course_id and context and context != f"course_{course_id}":
                continue
            blob = strip_html(
                f"{announcement.get('title') or ''} {announcement.get('message') or ''}",
                2000,
            )
            if title_key and title_key in blob.casefold():
                label = strip_html(announcement.get("title") or "Announcement", 160)
                if label:
                    messages.append(f"Announcement — {label}")

        cards.append(
            build_card(
                status=status,
                kind=kind,
                course=course_name,
                title=title,
                due=due,
                points=points,
                submission_types=submission_types,
                html_url=html_url,
                locked_until=locked_until,
                description=description,
                rubric=_rubric_headline(assignment),
                messages=messages[:6],
            )
        )

    grouped = group_cards(cards)
    payload.update(grouped)
    payload["observer_note"] = observer_note
    return payload
