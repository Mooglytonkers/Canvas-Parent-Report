#!/usr/bin/env python3
"""Fetch Canvas missing/late work and related teacher messages.

Usage:
    python3 fetch_canvas.py
    python3 fetch_canvas.py -o output/data.json
    python3 fetch_canvas.py --list-observees

Reads CANVAS_TOKEN from the environment or a local .env file only.
Never prints or writes the token. Writes the JSON schema expected by
make_report.py and prints the output path to stdout. Exits 2 on a 401
(token revoked, expired, or disabled by the school).
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from canvas_api import (
    CanvasError,
    CanvasUnauthorized,
    get_json,
    handle_cli_error,
    paginate,
    token_from_env,
)
from config import load_settings, notice_regex, require_base_url, Settings


def now_in(settings: Settings) -> datetime:
    return datetime.now(settings.tzinfo())


def parse_dt(value: str | None, settings: Settings) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    tz = settings.tzinfo()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def due_date_local(value: str | None, settings: Settings) -> date | None:
    dt = parse_dt(value, settings)
    return dt.date() if dt else None


def in_window(due: date | None, start: date) -> bool:
    return due is not None and due >= start


def short_course_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if " - " in text:
        text = text.rsplit(" - ", 1)[0].strip()
    if text.lower().startswith("general "):
        text = text[8:].strip()
    return text


def clean_title(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def format_score(value: Any) -> int | float | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = str(value).strip()
    try:
        num = float(text)
        return int(num) if num.is_integer() else num
    except ValueError:
        return text


def strip_html(text: str) -> str:
    text = text.replace("\u2028", "\n").replace("\u2029", "\n")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def default_output_path(settings: Settings, when: datetime | None = None) -> Path:
    when = when or now_in(settings)
    ampm = "AM" if when.hour < 12 else "PM"
    return settings.output_dir / f"data_{when.strftime('%Y-%m-%d')}_{ampm}.json"


def display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return (user.get("short_name") or user.get("name") or user.get("sortable_name") or "").strip()


def list_observees(token: str) -> list[dict[str, Any]]:
    try:
        rows = paginate("/api/v1/users/self/observees", params={"per_page": 100}, token=token)
    except CanvasError as exc:
        if exc.status in (403, 404):
            return []
        raise
    return [row for row in rows if isinstance(row, dict)]


def resolve_identity(token: str, settings: Settings) -> dict[str, Any]:
    """Decide student vs observer mode.

    * student_user_id set in config: observer mode for that student.
    * otherwise, if this account observes exactly one student: use that student.
    * if it observes more than one: ask the user to set student_user_id.
    * if it observes none: treat the token as the student's own account.
    """
    me = get_json("/api/v1/users/self", token=token)
    if not isinstance(me, dict) or me.get("id") is None:
        raise CanvasError(None, "Canvas did not return a profile for this token.")
    me_id = int(me["id"])
    observees = list_observees(token)

    if settings.student_user_id is not None:
        sid = int(settings.student_user_id)
        match = next((o for o in observees if int(o.get("id") or 0) == sid), None)
        if sid == me_id:
            return {
                "mode": "student",
                "self": me,
                "self_id": me_id,
                "student_id": None,
                "student": me,
            }
        return {
            "mode": "observer",
            "self": me,
            "self_id": me_id,
            "student_id": sid,
            "student": match or {"id": sid, "name": settings.student_name or f"User {sid}"},
        }

    if len(observees) == 1 and observees[0].get("id") is not None:
        student = observees[0]
        return {
            "mode": "observer",
            "self": me,
            "self_id": me_id,
            "student_id": int(student["id"]),
            "student": student,
        }
    if len(observees) > 1:
        lines = []
        for row in observees:
            oid = row.get("id")
            name = display_name(row) or "(no name)"
            lines.append(f"  {oid}  {name}")
        listing = "\n".join(lines)
        raise CanvasError(
            None,
            "This Canvas account observes more than one student. Set "
            "student_user_id in config.ini to the Canvas user ID of the "
            "student you want a report for.\n" + listing,
        )
    return {
        "mode": "student",
        "self": me,
        "self_id": me_id,
        "student_id": None,
        "student": me,
    }


def load_courses(token: str, student_id: int | None) -> dict[int, dict[str, Any]]:
    courses: dict[int, dict[str, Any]] = {}

    def add(row: dict[str, Any]) -> None:
        cid = row.get("id")
        if cid is not None:
            courses[int(cid)] = row

    if student_id is not None:
        try:
            for course in paginate(
                f"/api/v1/users/{student_id}/courses",
                params=[("per_page", "100"), ("include[]", "enrollments")],
                token=token,
            ):
                add(course)
        except CanvasError:
            pass
        try:
            for course in paginate(
                "/api/v1/courses",
                params=[
                    ("enrollment_type", "observer"),
                    ("include[]", "enrollments"),
                    ("per_page", "100"),
                ],
                token=token,
            ):
                for enrollment in course.get("enrollments") or []:
                    associated = enrollment.get("associated_user_id")
                    if associated is not None and int(associated) == int(student_id):
                        add(course)
                        break
        except CanvasError:
            pass
        return courses

    for course in paginate(
        "/api/v1/courses",
        params=[("per_page", "100"), ("include[]", "enrollments")],
        token=token,
    ):
        add(course)
    return courses


def load_teacher_ids(course_ids: list[int], token: str) -> set[int]:
    teachers: set[int] = set()
    params = [
        ("type[]", "TeacherEnrollment"),
        ("type[]", "TaEnrollment"),
        ("per_page", "100"),
    ]
    for cid in course_ids:
        try:
            rows = paginate(
                f"/api/v1/courses/{cid}/enrollments",
                params=params,
                token=token,
            )
        except CanvasError:
            continue
        for row in rows:
            uid = row.get("user_id")
            if uid is not None:
                teachers.add(int(uid))
    return teachers


def fetch_missing_assignments(
    token: str,
    student_id: int | None,
    course_ids: list[int],
) -> list[dict[str, Any]]:
    if student_id is not None:
        params: list[tuple[str, Any]] = [
            ("include[]", "course"),
            ("per_page", "100"),
        ]
        if course_ids:
            params.append(("observed_user_id", str(student_id)))
            for cid in course_ids:
                params.append(("course_ids[]", str(cid)))
            return paginate(
                f"/api/v1/users/{student_id}/missing_submissions",
                params=params,
                token=token,
            )
        # No course list: try the student path without observed_user_id.
        try:
            return paginate(
                f"/api/v1/users/{student_id}/missing_submissions",
                params=params,
                token=token,
            )
        except CanvasError:
            return []
    return paginate(
        "/api/v1/users/self/missing_submissions",
        params=[("include[]", "course"), ("per_page", "100")],
        token=token,
    )


def fetch_planner_items(
    start: date,
    end: date,
    token: str,
    student_id: int | None,
    course_ids: list[int],
) -> list[dict[str, Any]]:
    date_params: list[tuple[str, Any]] = [
        ("start_date", start.isoformat()),
        ("end_date", end.isoformat()),
        ("per_page", "100"),
    ]
    if student_id is not None:
        try:
            return paginate(
                f"/api/v1/users/{student_id}/planner/items",
                params=date_params,
                token=token,
            )
        except CanvasError:
            if not course_ids:
                return []
            params = list(date_params)
            params.append(("observed_user_id", str(student_id)))
            for cid in course_ids:
                params.append(("context_codes[]", f"course_{cid}"))
            return paginate("/api/v1/planner/items", params=params, token=token)
    return paginate("/api/v1/planner/items", params=date_params, token=token)


def fetch_submission(
    course_id: int,
    assignment_id: int,
    token: str,
    student_id: int | None,
) -> dict[str, Any] | None:
    user_part = str(student_id) if student_id is not None else "self"
    try:
        data = get_json(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_part}",
            params=[("include[]", "submission_comments")],
            token=token,
        )
    except CanvasError:
        return None
    return data if isinstance(data, dict) else None


def collect_candidates(
    missing_assignments: list[dict[str, Any]],
    planner_items: list[dict[str, Any]],
    window_start: date,
    now: datetime,
    settings: Settings,
) -> dict[tuple[int, int], dict[str, Any]]:
    """Map (course_id, assignment_id) to candidate metadata."""
    candidates: dict[tuple[int, int], dict[str, Any]] = {}

    def add(
        course_id: int | None,
        assignment_id: int | None,
        *,
        title: str,
        course_name: str,
        due_at: str | None,
        planner_sub: dict[str, Any] | None = None,
    ) -> None:
        if course_id is None or assignment_id is None:
            return
        key = (int(course_id), int(assignment_id))
        due = due_date_local(due_at, settings)
        if not in_window(due, window_start):
            return
        existing = candidates.get(key)
        if existing:
            if not existing.get("course") and course_name:
                existing["course"] = course_name
            if not existing.get("assignment") and title:
                existing["assignment"] = title
            if not existing.get("due_at") and due_at:
                existing["due_at"] = due_at
            return
        candidates[key] = {
            "course_id": int(course_id),
            "assignment_id": int(assignment_id),
            "course": course_name,
            "assignment": title,
            "due_at": due_at,
            "due": due,
            "planner_sub": planner_sub,
        }

    for assignment in missing_assignments:
        course = assignment.get("course") or {}
        add(
            assignment.get("course_id") or course.get("id"),
            assignment.get("id"),
            title=clean_title(assignment.get("name")),
            course_name=short_course_name(course.get("name") or course.get("course_code")),
            due_at=assignment.get("due_at"),
        )

    for item in planner_items:
        ptype = item.get("plannable_type")
        if ptype not in ("assignment", "quiz", "discussion_topic"):
            continue
        plannable = item.get("plannable") or {}
        course_id = item.get("course_id")
        assignment_id = item.get("plannable_id")
        if ptype == "discussion_topic":
            assignment_id = plannable.get("assignment_id") or assignment_id
            if not plannable.get("assignment_id"):
                sub = item.get("submissions")
                if not isinstance(sub, dict):
                    continue
        due_at = plannable.get("due_at") or item.get("plannable_date")
        due = due_date_local(due_at, settings)
        if not in_window(due, window_start):
            continue
        sub = item.get("submissions") if isinstance(item.get("submissions"), dict) else None
        if not _planner_is_candidate(sub, due, now, settings):
            continue
        add(
            course_id,
            assignment_id,
            title=clean_title(plannable.get("title") or plannable.get("name")),
            course_name=short_course_name(item.get("context_name")),
            due_at=due_at,
            planner_sub=sub,
        )
    return candidates


def _planner_is_candidate(
    sub: dict[str, Any] | None,
    due: date | None,
    now: datetime,
    settings: Settings,
) -> bool:
    if not sub:
        due_dt = datetime.combine(due, datetime.min.time(), tzinfo=settings.tzinfo()) if due else None
        return bool(due_dt and now > due_dt)
    if sub.get("late") or sub.get("missing"):
        return True
    if sub.get("excused"):
        return False
    graded = bool(sub.get("graded")) or sub.get("score") is not None
    if graded and settings.graded_counts_as_submitted:
        return False
    submitted = bool(sub.get("submitted"))
    if due is not None:
        past_due = due < now.date() or (due == now.date() and now.hour >= 23)
        if past_due and not submitted:
            return True
    return False


def classify_submission(
    sub: dict[str, Any] | None,
    due_at: str | None,
    now: datetime,
    settings: Settings,
    planner_sub: dict[str, Any] | None = None,
) -> str | None:
    """Return 'missing', 'late', or None (exclude)."""
    flags = sub or {}
    if not sub and planner_sub:
        flags = planner_sub

    late = bool(flags.get("late"))
    missing_flag = bool(flags.get("missing"))
    excused = bool(flags.get("excused"))
    score = flags.get("score")
    grade = flags.get("grade")
    has_grade = (
        (score is not None)
        or (grade is not None and grade != "")
        or flags.get("graded") is True
    )
    submitted = bool(
        flags.get("submitted_at")
        or flags.get("submission_type")
        or flags.get("submitted") is True
        or flags.get("workflow_state") in ("submitted", "pending_review", "graded")
    )
    if late:
        return "late"
    if excused:
        return None
    if has_grade and settings.graded_counts_as_submitted:
        return None
    if missing_flag:
        return "missing"
    due_dt = parse_dt(due_at, settings)
    if due_dt and now > due_dt and not submitted and not (
        has_grade and settings.graded_counts_as_submitted
    ):
        return "missing"
    return None


def comments_from_teachers(
    sub: dict[str, Any] | None,
    skip_ids: set[int],
    teacher_ids: set[int],
) -> str | None:
    if not sub:
        return None
    parts: list[str] = []
    for comment in sub.get("submission_comments") or []:
        author_id = comment.get("author_id")
        if author_id is not None and int(author_id) in skip_ids:
            continue
        if teacher_ids and author_id is not None and int(author_id) not in teacher_ids:
            continue
        text = strip_html(comment.get("comment") or "")
        if not text:
            continue
        name = (comment.get("author_name") or "").strip()
        parts.append(f"{name}: {text}" if name else text)
    return " ".join(parts) if parts else None


def fetch_conversations(token: str) -> list[dict[str, Any]]:
    return paginate("/api/v1/conversations", params={"per_page": 50}, token=token)


def fetch_conversation(conv_id: int, token: str) -> dict[str, Any] | None:
    try:
        data = get_json(f"/api/v1/conversations/{conv_id}", token=token)
    except CanvasError:
        return None
    return data if isinstance(data, dict) else None


def context_course_id(conv: dict[str, Any]) -> int | None:
    code = conv.get("context_code") or ""
    match = re.match(r"course_(\d+)$", str(code))
    return int(match.group(1)) if match else None


def is_course_wide(conv: dict[str, Any], message: dict[str, Any] | None = None) -> bool:
    if conv.get("private") is True:
        return False
    participants = conv.get("participants") or []
    audience = conv.get("audience") or []
    ids = (message or {}).get("participating_user_ids") or []
    return max(len(participants), len(audience), len(ids)) > 2


def mentions_flagged(
    text: str,
    conv: dict[str, Any],
    flagged_course_ids: set[int],
    flagged_course_names: set[str],
    flagged_assignments: set[str],
) -> bool:
    cid = context_course_id(conv)
    if cid is not None and cid in flagged_course_ids:
        return True
    context = short_course_name(conv.get("context_name"))
    lowered = text.lower()
    if context and context.lower() in flagged_course_names:
        return True
    for name in flagged_course_names:
        if name and name in lowered:
            return True
    for title in flagged_assignments:
        if title and len(title) >= 5 and title.lower() in lowered:
            return True
    return False


def select_teacher_messages(
    conversations: list[dict[str, Any]],
    *,
    skip_ids: set[int],
    teacher_ids: set[int],
    courses: dict[int, dict[str, Any]],
    flagged_course_ids: set[int],
    flagged_course_names: set[str],
    flagged_assignments: set[str],
    window_start: date,
    token: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    cutoff = datetime.combine(window_start, datetime.min.time(), tzinfo=settings.tzinfo())
    selected: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    notice_re = notice_regex(settings.notice_keywords)

    for preview in conversations:
        last_at = parse_dt(
            preview.get("last_message_at") or preview.get("last_authored_message_at"),
            settings,
        )
        if last_at is not None and last_at < cutoff:
            continue
        conv_id = preview.get("id")
        if conv_id is None:
            continue
        full = fetch_conversation(int(conv_id), token) or preview
        messages = full.get("messages") if isinstance(full.get("messages"), list) else []
        if not messages:
            messages = [
                {
                    "id": full.get("id"),
                    "author_id": None,
                    "created_at": full.get("last_message_at"),
                    "body": full.get("last_message") or "",
                    "participating_user_ids": full.get("audience") or [],
                }
            ]
        participants = {
            int(p["id"]): p for p in (full.get("participants") or []) if p.get("id") is not None
        }
        cid = context_course_id(full)
        course_name = short_course_name(
            full.get("context_name")
            or ((courses.get(cid) or {}).get("name") if cid is not None else "")
        )
        subject = clean_title(full.get("subject")) or "Canvas message"

        for message in messages:
            mid = message.get("id")
            key = (int(conv_id), int(mid) if mid is not None else 0)
            if key in seen:
                continue
            created = parse_dt(message.get("created_at") or full.get("last_message_at"), settings)
            if created is None or created.date() < window_start:
                continue
            author_id = message.get("author_id")
            if author_id is None:
                author_id = next((pid for pid in participants if pid in teacher_ids), None)
            if author_id is not None and int(author_id) in skip_ids:
                continue
            if teacher_ids and author_id is not None and int(author_id) not in teacher_ids:
                continue
            if author_id is None:
                continue
            body = strip_html(message.get("body") or "")
            if not body:
                continue
            blob = f"{subject}\n{body}"
            course_wide = is_course_wide(full, message)
            relevant = mentions_flagged(
                blob, full, flagged_course_ids, flagged_course_names, flagged_assignments
            )
            grade_notice = course_wide and bool(notice_re.search(blob))
            if not (relevant or grade_notice):
                continue
            teacher = (participants.get(int(author_id)) or {}).get("name") or "Teacher"
            sign = re.search(
                r"(?:^|\n)\s*((?:Ms|Mrs|Mr|Miss|Dr|Mx)\.?\s+[A-Z][\w'-]+)\s*$",
                body,
            )
            if sign:
                teacher = sign.group(1).replace("\n", " ").strip()
            seen.add(key)
            selected.append(
                {
                    "course": course_name,
                    "teacher": teacher,
                    "assignment": subject,
                    "sent": created.date().isoformat(),
                    "message": body,
                }
            )
    selected.sort(key=lambda row: (row.get("sent") or "", row.get("assignment") or ""))
    return selected


def build_report(settings: Settings) -> dict[str, Any]:
    require_base_url(settings)
    token = token_from_env()
    generated = now_in(settings)
    identity = resolve_identity(token, settings)
    self_id = int(identity["self_id"])
    student_id = identity.get("student_id")
    student = identity.get("student") or {}
    mode = identity["mode"]

    student_name = settings.student_name or display_name(student) or "Student"
    school_name = settings.school_name or "School"
    skip_ids = {self_id}
    if student_id is not None:
        skip_ids.add(int(student_id))

    courses = load_courses(token, student_id)
    course_ids = list(courses)
    teacher_ids = load_teacher_ids(course_ids, token)

    missing_assignments = fetch_missing_assignments(token, student_id, course_ids)
    planner_items = fetch_planner_items(
        settings.start_date, generated.date(), token, student_id, course_ids
    )
    candidates = collect_candidates(
        missing_assignments, planner_items, settings.start_date, generated, settings
    )

    missing_rows: list[dict[str, Any]] = []
    late_rows: list[dict[str, Any]] = []
    had_any_teacher_comment = False

    for (course_id, assignment_id), meta in sorted(
        candidates.items(),
        key=lambda kv: (kv[1].get("due") or date.max, kv[1].get("assignment") or ""),
    ):
        sub = fetch_submission(course_id, assignment_id, token, student_id)
        kind = classify_submission(
            sub, meta.get("due_at"), generated, settings, meta.get("planner_sub")
        )
        if kind not in ("missing", "late"):
            continue
        comment = comments_from_teachers(sub, skip_ids, teacher_ids)
        if comment:
            had_any_teacher_comment = True
        score = None
        if sub:
            score = format_score(
                sub.get("score") if sub.get("score") is not None else sub.get("grade")
            )
        elif meta.get("planner_sub"):
            score = format_score(meta["planner_sub"].get("score"))
        course_name = meta.get("course") or short_course_name(
            (courses.get(course_id) or {}).get("name")
        )
        due_value = meta.get("due") or due_date_local(meta.get("due_at"), settings)
        row = {
            "course": course_name,
            "assignment": meta.get("assignment") or f"Assignment {assignment_id}",
            "due": due_value.isoformat() if due_value else None,
            "score": score,
            "comment": comment,
        }
        if kind == "late":
            late_rows.append(row)
        else:
            missing_rows.append(row)

    flagged_course_ids: set[int] = set()
    flagged_course_names: set[str] = set()
    flagged_assignments: set[str] = set()
    for row in missing_rows + late_rows:
        if row.get("course"):
            flagged_course_names.add(row["course"].lower())
        if row.get("assignment"):
            flagged_assignments.add(row["assignment"])
    titled = {(r["course"], r["assignment"]) for r in missing_rows + late_rows}
    for (cid, _aid), meta in candidates.items():
        if (meta.get("course"), meta.get("assignment")) in titled:
            flagged_course_ids.add(cid)

    conversations = fetch_conversations(token)
    teacher_messages = select_teacher_messages(
        conversations,
        skip_ids=skip_ids,
        teacher_ids=teacher_ids,
        courses=courses,
        flagged_course_ids=flagged_course_ids,
        flagged_course_names=flagged_course_names,
        flagged_assignments=flagged_assignments,
        window_start=settings.start_date,
        token=token,
        settings=settings,
    )

    notes: list[str] = []
    if not had_any_teacher_comment:
        notes.append("No submission comments from teachers on any assignment.")
    if mode == "observer":
        notes.append(
            "This report used an observer (parent) account. Canvas messages "
            "come from the parent inbox; the student's private inbox is not included."
        )

    return {
        "student": student_name,
        "school": school_name,
        "title": "Canvas Missing Work Report",
        "scope": settings.scope_label(),
        "generated_at": generated.isoformat(timespec="seconds"),
        "graded_counts_as_submitted": settings.graded_counts_as_submitted,
        "account_mode": mode,
        "missing": missing_rows,
        "late": late_rows,
        "teacher_messages": teacher_messages,
        "notes": notes,
    }


def print_markdown_table(data: dict[str, Any], file=None) -> None:
    """Print a compact markdown table of report rows."""
    out = file or sys.stdout
    print("| Category | Course | Assignment | Due | Score | Teacher comment/message |", file=out)
    print("|---|---|---|---|---|---|", file=out)

    def due_cell(value: str | None, prefix: str = "") -> str:
        if not value:
            return "—"
        return f"{prefix}{value}"

    def score_cell(value: Any) -> str:
        return "—" if value is None or value == "" else str(value)

    def comment_cell(value: str | None) -> str:
        if not value:
            return "—"
        return " ".join(str(value).split())

    rows = 0
    for item in data.get("missing") or []:
        print(
            f"| Missing | {item.get('course') or '—'} | {item.get('assignment') or '—'} | "
            f"{due_cell(item.get('due'))} | {score_cell(item.get('score'))} | "
            f"{comment_cell(item.get('comment'))} |",
            file=out,
        )
        rows += 1
    for item in data.get("late") or []:
        print(
            f"| Late | {item.get('course') or '—'} | {item.get('assignment') or '—'} | "
            f"{due_cell(item.get('due'))} | {score_cell(item.get('score'))} | "
            f"{comment_cell(item.get('comment'))} |",
            file=out,
        )
        rows += 1
    for item in data.get("teacher_messages") or []:
        teacher = (item.get("teacher") or "").strip()
        message = comment_cell(item.get("message"))
        combined = f"{teacher} — {message}" if teacher and message != "—" else (teacher or message)
        print(
            f"| Teacher message | {item.get('course') or '—'} | {item.get('assignment') or '—'} | "
            f"{due_cell(item.get('sent'), 'Sent ')} | — | {combined} |",
            file=out,
        )
        rows += 1
    if rows == 0:
        print("| — | — | — | — | — | No missing or late assignments, and no teacher messages. |", file=out)


def print_observees(settings: Settings) -> int:
    require_base_url(settings)
    token = token_from_env()
    me = get_json("/api/v1/users/self", token=token)
    name = display_name(me) if isinstance(me, dict) else ""
    print(f"Signed in as: {name or 'this Canvas account'}")
    observees = list_observees(token)
    if not observees:
        print("This account is not observing any students (or cannot list them).")
        print("A token from the student's own account will still work.")
        return 0
    print("Observed students:")
    for row in observees:
        print(f"  {row.get('id')}  {display_name(row) or '(no name)'}")
    if len(observees) > 1:
        print("Set student_user_id in config.ini to one of the IDs above.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Canvas missing/late work into a make_report.py JSON file."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: output/data_YYYY-MM-DD_AM|PM.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.ini (default: config.ini next to this script)",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="Also print a compact markdown table of the report to stderr",
    )
    parser.add_argument(
        "--list-observees",
        action="store_true",
        help="List students linked to this observer account and exit",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.list_observees:
            return print_observees(settings)
        data = build_report(settings)
    except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
        return handle_cli_error(exc)

    output = (args.output or default_output_path(settings)).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    if args.table:
        print_markdown_table(data, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
