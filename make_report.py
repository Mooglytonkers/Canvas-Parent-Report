#!/usr/bin/env python3
"""Generate a one-page US Letter (portrait) Canvas missing-work report PDF.

Usage:
    python3 make_report.py DATA.json
    python3 make_report.py DATA.json -o output/Alex_Sample_Canvas_Report_2026-11-22.pdf
    python3 make_report.py DATA.json --html

If WeasyPrint is not installed (or its system libraries are missing), an HTML
file is written instead so you can still open or print the report from a browser.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ET_FALLBACK = ZoneInfo("America/New_York")

TITLE_DEFAULT = "Canvas Missing Work Report"
FOOTER_GRADED = "Source: Canvas. Graded work is treated as submitted."
FOOTER_PLAIN = "Source: Canvas."

CATEGORY_META = {
    "missing": {
        "label": "Missing",
        "bw_label": "MISSING",
        "tile_label": "Missing",
        "css": "pill-missing",
        "tile_css": "tile-missing",
    },
    "late": {
        "label": "Late",
        "bw_label": "LATE",
        "tile_label": "Late",
        "css": "pill-late",
        "tile_css": "tile-late",
    },
    "teacher_message": {
        "label": "Teacher message",
        "bw_label": "MESSAGE",
        "tile_label": "Teacher messages",
        "css": "pill-message",
        "tile_css": "tile-message",
    },
}


CSS = """
@page {
  size: letter portrait;
  margin: 0.48in 0.58in 0.48in 0.58in;
}

* {
  box-sizing: border-box;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

html, body {
  margin: 0;
  padding: 0;
  background: #fff;
  color: #1a2332;
  font-family: "IBM Plex Sans", "Source Sans Pro", "Liberation Sans", "Segoe UI", sans-serif;
  font-size: 10.5pt;
  line-height: 1.35;
}

body {
  min-height: 10.04in;
  display: flex;
  flex-direction: column;
}

.page-main {
  flex: 1 1 auto;
}

.topbar {
  height: 7px;
  background: #1b365d;
  margin: -0.48in -0.58in 0.22in -0.58in;
}

.header {
  margin-bottom: 0.18in;
}

.kicker {
  font-size: 8pt;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #1b365d;
  margin: 0 0 4px 0;
}

h1 {
  margin: 0;
  font-size: 20.5pt;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: #1b365d;
  line-height: 1.15;
}

.subtitle {
  margin: 7px 0 0 0;
  font-size: 9.5pt;
  color: #4a5568;
  line-height: 1.4;
}

.subtitle .sep {
  color: #a0aec0;
  padding: 0 0.28em;
}

.tiles {
  display: flex;
  gap: 10px;
  margin: 0 0 0.16in 0;
}

.tile {
  flex: 1;
  border: 1px solid #d5dde6;
  border-radius: 5px;
  padding: 11px 14px 10px 14px;
  background: #f8fafc;
  border-left: 5px solid #718096;
}

.tile-missing { border-left-color: #c53030; }
.tile-late { border-left-color: #c05621; }
.tile-message { border-left-color: #2b6cb0; }
.tile-missing.tile-zero { border-left-color: #2f855a; }

.tile .count {
  display: block;
  font-size: 26pt;
  font-weight: 650;
  line-height: 1;
  color: #1a2332;
  letter-spacing: -0.03em;
}

.tile .tile-label {
  display: block;
  margin-top: 4px;
  font-size: 8pt;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #4a5568;
}

.banner {
  border-radius: 5px;
  padding: 9px 14px;
  margin: 0 0 0.18in 0;
  font-size: 10.5pt;
  font-weight: 550;
  border: 1px solid #c6e6d0;
  background: #eaf8ef;
  color: #1c4532;
}

.banner-ok {
  border-color: #9ae6b4;
  background: #eaf8ef;
  color: #1c4532;
}

.banner-warn {
  border-color: #fbd38d;
  background: #fffaf0;
  color: #7b341e;
}

.banner .banner-tag {
  display: inline-block;
  font-size: 7.5pt;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 1px 5px;
  margin-right: 8px;
  vertical-align: 1px;
}

.section-label {
  font-size: 8pt;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #1b365d;
  margin: 0 0 6px 0;
}

table.items {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid #c5d0dc;
  border-radius: 5px;
  overflow: hidden;
}

table.items thead th {
  background: #1b365d;
  color: #fff;
  font-size: 7.3pt;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-align: left;
  padding: 7px 8px;
  border: none;
  white-space: nowrap;
  vertical-align: middle;
}

table.items td {
  font-size: 10pt;
  padding: 8px 8px;
  vertical-align: top;
  border-top: 1px solid #e2e8f0;
  color: #1a2332;
  hyphens: none;
  -weasy-hyphens: none;
}

table.items tbody tr:nth-child(even) td {
  background: #f4f7fa;
}

table.items tbody tr:nth-child(odd) td {
  background: #ffffff;
}

.col-cat { width: 0.95in; }
.col-course { width: 0.95in; }
.col-assign { width: 1.52in; }
.col-due { width: 1.28in; }
.col-score { width: 0.52in; }
.col-comment { width: auto; }

.due { white-space: nowrap; }
.score {
  font-variant-numeric: tabular-nums;
  font-weight: 550;
}

.empty {
  color: #a0aec0;
}

.pill {
  display: inline-block;
  font-size: 7.5pt;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-radius: 3px;
  padding: 2px 6px;
  border: 1px solid;
  line-height: 1.2;
  white-space: nowrap;
}

.pill-missing {
  color: #9b2c2c;
  background: #fed7d7;
  border-color: #c53030;
}

.pill-late {
  color: #7b341e;
  background: #feebc8;
  border-color: #c05621;
}

.pill-message {
  color: #1a365d;
  background: #bee3f8;
  border-color: #2b6cb0;
}

.muted { color: #4a5568; }
.small { font-size: 10pt; line-height: 1.4; }

.notes {
  margin-top: 0.15in;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 5px;
  padding: 8px 12px;
  font-size: 9.5pt;
  color: #2d3748;
}

.notes strong {
  font-weight: 600;
  color: #1b365d;
}

.notes ul {
  margin: 4px 0 0 0;
  padding-left: 1.1em;
}

.notes li { margin: 0 0 2px 0; }

.empty-table {
  border: 1px dashed #cbd5e0;
  border-radius: 5px;
  padding: 14px 12px;
  text-align: center;
  color: #4a5568;
  font-size: 10pt;
  background: #f8fafc;
}

.legend {
  margin-top: 0.13in;
  font-size: 8pt;
  color: #4a5568;
}

.legend .pill { margin-right: 4px; vertical-align: 1px; }
.legend span.leg-item { margin-right: 14px; white-space: nowrap; }

.todo-pages { page-break-before: always; }
.todo-card {
  border: 1px solid #d5dde6;
  border-left-width: 5px;
  border-radius: 5px;
  background: #f8fafc;
  padding: 10px 12px;
  margin: 0 0 10px 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
.todo-missing { border-left-color: #c53030; }
.todo-late { border-left-color: #c05621; }
.todo-later { border-left-color: #2b6cb0; }
.todo-top { display: flex; gap: 6px; align-items: center; }
.todo-course { margin-left: auto; color: #4a5568; font-size: 9pt; font-weight: 600; }
.todo-card h2 { margin: 6px 0 2px 0; font-size: 12pt; color: #1a2332; }
.todo-due, .todo-card p { margin: 2px 0; font-size: 9.5pt; }
.todo-kicker {
  margin-top: 6px;
  font-size: 7.5pt;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #1b365d;
  font-weight: 650;
}
.todo-locked { color: #7b341e; font-weight: 600; }
.todo-card ul { margin: 2px 0 0 1.1em; padding: 0; }

footer {
  flex: 0 0 auto;
  margin-top: 0.22in;
  padding-top: 8px;
  border-top: 1px solid #cbd5e0;
  font-size: 8pt;
  color: #4a5568;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

footer .left { flex: 1; }
footer .right { white-space: nowrap; color: #718096; }
"""


def esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _zone(name: str | None) -> ZoneInfo:
    if not name:
        return ET_FALLBACK
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ET_FALLBACK


def parse_datetime(value: str | None, tz: ZoneInfo | None = None) -> datetime | None:
    if not value:
        return None
    zone = tz or ET_FALLBACK
    text = value.strip()
    iso = text
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zone)
        return dt.astimezone(zone)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=zone)
        except ValueError:
            continue
    return None


def _hour12(dt: datetime) -> int:
    hour = dt.hour % 12
    return hour if hour else 12


def format_generated(value: str | None, tz: ZoneInfo | None = None) -> tuple[str, str]:
    """Return (display_string, yyyy-mm-dd used for the filename).

    Uses unpadded day and hour so this works on Windows as well as macOS/Linux.
    """
    zone = tz or ET_FALLBACK
    now = datetime.now(zone)
    if not value:
        return (_friendly_stamp(now), now.strftime("%Y-%m-%d"))
    dt = parse_datetime(value, zone)
    if dt:
        return (_friendly_stamp(dt), dt.strftime("%Y-%m-%d"))
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        label = value if re.search(r"\b[A-Z]{2,4}\b", value) else f"{value} {_tz_label(now)}"
        return (label, match.group(0))
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        month, day, year = match.groups()
        label = value if "ET" in value or re.search(r"\b[A-Z]{2,4}\b", value) else f"{value} {_tz_label(now)}"
        return (label, f"{year}-{int(month):02d}-{int(day):02d}")
    label = value if re.search(r"\b[A-Z]{2,4}\b", value) else f"{value} {_tz_label(now)}"
    return (label, now.strftime("%Y-%m-%d"))


def _tz_label(dt: datetime) -> str:
    name = dt.tzname()
    return name or "local"


def _friendly_stamp(dt: datetime) -> str:
    ampm = dt.strftime("%p")
    return (
        f"{dt.strftime('%B')} {dt.day}, {dt.year} at "
        f"{_hour12(dt)}:{dt.strftime('%M')} {ampm} {_tz_label(dt)}"
    )


def format_date(value: str | None, tz: ZoneInfo | None = None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    dt = parse_datetime(text, tz)
    if dt:
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    return text


def display_score(value: object) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def normalize_items(data: dict, tz: ZoneInfo | None = None) -> list[dict]:
    rows: list[dict] = []
    for item in data.get("missing") or []:
        rows.append(
            {
                "category": "missing",
                "course": item.get("course") or "",
                "assignment": item.get("assignment") or "",
                "due": format_date(item.get("due"), tz),
                "due_prefix": "",
                "score": display_score(item.get("score")),
                "comment": (item.get("comment") or "").strip(),
            }
        )
    for item in data.get("late") or []:
        rows.append(
            {
                "category": "late",
                "course": item.get("course") or "",
                "assignment": item.get("assignment") or "",
                "due": format_date(item.get("due"), tz),
                "due_prefix": "",
                "score": display_score(item.get("score")),
                "comment": (item.get("comment") or "").strip(),
            }
        )
    for item in data.get("teacher_messages") or []:
        teacher = (item.get("teacher") or "").strip()
        message = (item.get("message") or "").strip()
        if teacher and message:
            comment = f"{teacher} — {message}"
        else:
            comment = teacher or message
        rows.append(
            {
                "category": "teacher_message",
                "course": item.get("course") or "",
                "assignment": item.get("assignment") or "",
                "due": format_date(item.get("sent") or item.get("due"), tz),
                "due_prefix": "Sent ",
                "score": display_score(item.get("score")),
                "comment": comment,
            }
        )
    return rows


def cell_or_dash(value: str, extra_class: str = "") -> str:
    cls = f' class="{extra_class}"' if extra_class else ""
    if value:
        return f"<td{cls}>{esc(value)}</td>"
    return '<td class="empty">—</td>'


def render_row(row: dict) -> str:
    meta = CATEGORY_META[row["category"]]
    due = row["due"]
    due_html = (
        f'<td class="due">{esc(row["due_prefix"])}{esc(due)}</td>'
        if due
        else '<td class="empty">—</td>'
    )
    return f"""
      <tr>
        <td><span class="pill {meta['css']}">{esc(meta['bw_label'])}</span></td>
        {cell_or_dash(row['course'])}
        {cell_or_dash(row['assignment'])}
        {due_html}
        {cell_or_dash(row['score'], 'score')}
        {cell_or_dash(row['comment'], 'small')}
      </tr>
    """


def render_todo_html(data: dict) -> str:
    details = data.get("todo_details") or {}
    if not details.get("enabled"):
        return ""
    student = esc(data.get("student") or "Student")

    def tile(count: int, label: str, css: str) -> str:
        return (
            f'<div class="tile {css}"><span class="count">{count}</span>'
            f'<span class="tile-label">{esc(label)}</span></div>'
        )

    overdue = list(details.get("overdue") or [])
    this_week = list(details.get("this_week") or [])
    later = list(details.get("later") or [])
    overdue_css = "tile-missing" + ("" if overdue else " tile-zero")
    tiles = (
        tile(len(overdue), "Overdue", overdue_css)
        + tile(len(this_week), "Due this week", "tile-late")
        + tile(len(later), "Due later", "tile-message")
    )

    def card(item: dict, bar: str) -> str:
        messages = item.get("messages") or []
        if messages:
            message_html = "".join(f"<li>{esc(line)}</li>" for line in messages)
        else:
            message_html = "<li>No related messages.</li>"
        link = str(item.get("html_url") or "").strip()
        link_html = (
            f' · <a href="{esc(link)}">Open in Canvas</a>' if link else ""
        )
        locked = str(item.get("locked_until") or "").strip()
        locked_html = f'<p class="todo-locked">{esc(locked)}</p>' if locked else ""
        description = str(item.get("description") or "").strip()
        description_html = (
            f'<p class="todo-kicker">Description</p><p>{esc(description)}</p>' if description else ""
        )
        rubric = str(item.get("rubric") or "").strip()
        rubric_html = f"<p>{esc(rubric)}</p>" if rubric else ""
        meta = esc(item.get("meta") or "")
        return f"""
        <article class="todo-card todo-{bar}">
          <div class="todo-top">
            <span class="pill pill-{bar if bar != 'later' else 'message'}">{esc(item.get('status_label') or '')}</span>
            <span class="pill pill-message">{esc(item.get('type_label') or '')}</span>
            <span class="todo-course">{esc(item.get('course') or '')}</span>
          </div>
          <h2>{esc(item.get('title') or 'Untitled')}</h2>
          <p class="todo-due">{esc(item.get('due_label') or '')}</p>
          <p>{meta}{link_html}</p>
          {locked_html}
          {description_html}
          {rubric_html}
          <p class="todo-kicker">Related messages</p>
          <ul>{message_html}</ul>
        </article>
        """

    sections = []
    for heading, rows, bar in (
        ("Overdue", overdue, "missing"),
        ("Due this week", this_week, "late"),
        ("Due later", later, "later"),
    ):
        if not rows:
            continue
        sections.append(f'<h3 class="section-label">{esc(heading)}</h3>' + "".join(card(row, bar) for row in rows))
    if not sections:
        sections.append("<p>Nothing is overdue in this date range, and nothing is due in the days ahead.</p>")
    note = esc(details.get("observer_note") or "")
    note_html = f'<p class="muted">{note}</p>' if note else ""
    return f"""
    <section class="todo-pages">
      <h1>{student} — To Do — assignment details</h1>
      <p class="subtitle">{esc(details.get('window_label') or '')}</p>
      <div class="tiles">{tiles}</div>
      {note_html}
      {''.join(sections)}
    </section>
    """


def footer_text(data: dict) -> str:
    if data.get("footer"):
        return str(data["footer"])
    if data.get("graded_counts_as_submitted", True):
        return FOOTER_GRADED
    return FOOTER_PLAIN


def build_html(data: dict) -> str:
    student = data.get("student") or "Student"
    school = data.get("school") or ""
    title = data.get("title") or TITLE_DEFAULT
    scope = data.get("scope") or ""
    tz = _zone(data.get("timezone"))
    generated_display, _ = format_generated(data.get("generated_at"), tz)

    missing = list(data.get("missing") or [])
    late = list(data.get("late") or [])
    messages = list(data.get("teacher_messages") or [])
    notes = [n for n in (data.get("notes") or []) if n]
    rows = normalize_items(data, tz)

    missing_n, late_n, msg_n = len(missing), len(late), len(messages)
    header_title = f"{student} — {title}"

    missing_tile_css = "tile-missing" + (" tile-zero" if missing_n == 0 else "")
    if missing_n == 0:
        banner = (
            '<div class="banner banner-ok">'
            '<span class="banner-tag">All clear</span>'
            "No missing assignments in this date range."
            "</div>"
        )
    else:
        word = "assignment" if missing_n == 1 else "assignments"
        banner = (
            '<div class="banner banner-warn">'
            f'<span class="banner-tag">Action needed</span>'
            f"{missing_n} missing {word} in this date range."
            "</div>"
        )

    if rows:
        table_html = f"""
        <div class="section-label">Assignments and messages</div>
        <table class="items">
          <thead>
            <tr>
              <th class="col-cat">Category</th>
              <th class="col-course">Course</th>
              <th class="col-assign">Assignment</th>
              <th class="col-due">Due</th>
              <th class="col-score">Score</th>
              <th class="col-comment">Teacher comment/message</th>
            </tr>
          </thead>
          <tbody>
            {''.join(render_row(r) for r in rows)}
          </tbody>
        </table>
        """
    else:
        table_html = (
            '<div class="section-label">Assignments and messages</div>'
            '<div class="empty-table">No missing or late assignments, '
            "and no teacher messages, in this date range.</div>"
        )

    if notes:
        items = "".join(f"<li>{esc(n)}</li>" for n in notes)
        notes_html = (
            '<div class="notes"><strong>Notes</strong>'
            f"<ul>{items}</ul></div>"
        )
    else:
        notes_html = ""

    legend = """
    <div class="legend">
      <span class="leg-item"><span class="pill pill-missing">Missing</span> not submitted, past due</span>
      <span class="leg-item"><span class="pill pill-late">Late</span> submitted after the due date</span>
      <span class="leg-item"><span class="pill pill-message">Message</span> teacher comment or Canvas message</span>
    </div>
    """

    kicker = f"{school} Canvas" if school else "Canvas"
    subtitle_parts = [p for p in (school, scope, f"Generated {generated_display}") if p]
    subtitle = '<span class="sep">|</span>'.join(esc(p) for p in subtitle_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{esc(header_title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="page-main">
  <div class="topbar"></div>
  <header class="header">
    <div class="kicker">{esc(kicker)}</div>
    <h1>{esc(header_title)}</h1>
    <p class="subtitle">{subtitle}</p>
  </header>

  <div class="tiles">
    <div class="tile {missing_tile_css}">
      <span class="count">{missing_n}</span>
      <span class="tile-label">Missing</span>
    </div>
    <div class="tile tile-late">
      <span class="count">{late_n}</span>
      <span class="tile-label">Late</span>
    </div>
    <div class="tile tile-message">
      <span class="count">{msg_n}</span>
      <span class="tile-label">Teacher messages</span>
    </div>
  </div>

  {banner}
  {table_html}
  {notes_html}
  {legend}
  </div>

  {render_todo_html(data)}

  <footer>
    <div class="left">{esc(footer_text(data))}</div>
    <div class="right">Page 1 of 1</div>
  </footer>
</body>
</html>
"""


def load_data(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    missing = [f for f in ("student", "school", "scope") if not data.get(f)]
    if missing:
        raise ValueError("Missing required field(s): " + ", ".join(missing))
    for key in ("missing", "late", "teacher_messages", "notes"):
        if key in data and data[key] is not None and not isinstance(data[key], list):
            raise ValueError(f'"{key}" must be an array')
    return data


def slug_name(name: str) -> str:
    text = re.sub(r"[^\w]+", "_", (name or "").strip(), flags=re.UNICODE)
    return text.strip("_") or "Student"


def default_output_path(data: dict, data_path: Path, html: bool = False) -> Path:
    tz = _zone(data.get("timezone"))
    _, date_stamp = format_generated(data.get("generated_at"), tz)
    student = slug_name(str(data.get("student") or "Student"))
    suffix = ".html" if html else ".pdf"
    return data_path.parent / f"{student}_Canvas_Report_{date_stamp}{suffix}"


def write_html_file(data: dict, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(data), encoding="utf-8")
    return output


def _write_html_fallback(html_doc: str, output: Path, warning: str) -> Path:
    target = output.with_suffix(".html")
    target.write_text(html_doc, encoding="utf-8")
    print(warning, file=sys.stderr)
    return target


def _write_with_reportlab(data: dict, output: Path) -> bool:
    """Return True when ReportLab wrote a PDF. Used by the Windows app."""
    try:
        from report_pdf import write_report_pdf
    except ImportError:
        return False
    try:
        write_report_pdf(data, output)
    except Exception as exc:
        print(
            f"warning: ReportLab could not build the PDF ({exc.__class__.__name__}).",
            file=sys.stderr,
        )
        return False
    return output.is_file()


def write_pdf(data: dict, output: Path, *, prefer_html: bool = False) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    html_doc = build_html(data)
    if prefer_html or output.suffix.lower() in {".html", ".htm"}:
        target = output if output.suffix.lower() in {".html", ".htm"} else output.with_suffix(".html")
        target.write_text(html_doc, encoding="utf-8")
        return target
    engine = (os.environ.get("CPR_PDF_ENGINE") or "").strip().lower()
    # The desktop app sets this so a Windows install does not need GTK.
    if engine == "reportlab":
        if _write_with_reportlab(data, output):
            return output
        return _write_html_fallback(
            html_doc,
            output,
            "warning: ReportLab is not available, so an HTML report was written instead.\n"
            f"  {output.with_suffix('.html')}",
        )
    try:
        from weasyprint import HTML
    except ImportError:
        if _write_with_reportlab(data, output):
            print(
                "warning: WeasyPrint is not installed. A PDF was built with ReportLab instead.",
                file=sys.stderr,
            )
            return output
        return _write_html_fallback(
            html_doc,
            output,
            "warning: WeasyPrint is not installed, so an HTML report was written "
            f"instead of a PDF:\n  {output.with_suffix('.html')}\n"
            "Open it in a browser and use Print, or install WeasyPrint (see the README).",
        )
    try:
        HTML(string=html_doc, base_url=str(output.parent)).write_pdf(str(output))
    except Exception as exc:
        if _write_with_reportlab(data, output):
            print(
                "warning: WeasyPrint could not build a PDF "
                f"({exc.__class__.__name__}). A PDF was built with ReportLab instead.",
                file=sys.stderr,
            )
            return output
        return _write_html_fallback(
            html_doc,
            output,
            "warning: PDF generation failed "
            f"({exc.__class__.__name__}). An HTML report was written instead:\n"
            f"  {output.with_suffix('.html')}\n"
            "This usually means WeasyPrint's system libraries (Pango/GTK) are missing. "
            "See the README for install notes.",
        )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a one-page Canvas missing-work report PDF (or HTML)."
    )
    parser.add_argument("data", type=Path, help="Path to the report JSON data file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output PDF or HTML path (default: <Student>_Canvas_Report_YYYY-MM-DD.pdf "
        "next to the JSON file)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Write HTML instead of PDF",
    )
    args = parser.parse_args(argv)

    data_path = args.data.expanduser().resolve()
    if not data_path.is_file():
        print(f"error: data file not found: {data_path}", file=sys.stderr)
        return 1
    try:
        data = load_data(data_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = (
        args.output.expanduser().resolve()
        if args.output
        else default_output_path(data, data_path, html=args.html)
    )
    written = write_pdf(data, output, prefer_html=args.html)
    print(written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
