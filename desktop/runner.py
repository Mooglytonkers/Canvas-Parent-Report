"""Run one report with no window. Used by the app and by Task Scheduler."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from desktop.connection import friendly_error
from desktop.logging_setup import get_logger
from desktop.secrets import apply_to_environ
from desktop.store import AppConfig, append_history, load_config


@dataclass
class RunResult:
    ok: bool
    code: int
    message: str
    pdf_path: str = ""
    missing: int = 0
    late: int = 0
    summary: list[str] = field(default_factory=list)
    preview: list[dict] = field(default_factory=list)


def _preview(data: dict) -> list[dict]:
    rows: list[dict] = []
    for kind, key in (("Missing", "missing"), ("Late", "late")):
        for item in data.get(key) or []:
            rows.append(
                {
                    "category": kind,
                    "course": item.get("course") or "",
                    "assignment": item.get("assignment") or "",
                    "due": item.get("due") or "",
                }
            )
            if len(rows) >= 8:
                return rows
    return rows


def _message_from(summary: list[str], code: int) -> str:
    if code == 0:
        return "Report saved."
    interesting = [line for line in summary if line.startswith(("Print:", "Email:", "To Do:"))]
    failed = [line for line in interesting if "fail" in line.lower() or "could not" in line.lower() or "skipped" in line.lower()]
    if failed:
        return failed[0]
    return "The report finished with a problem. Details are in the log."


def execute_report(config: AppConfig | None = None) -> RunResult:
    """Fetch Canvas, build the PDF, then To Dos, print, and email."""
    log = get_logger()
    config = config or load_config()
    apply_to_environ()
    os.environ["CPR_PDF_ENGINE"] = "reportlab"
    if not (os.environ.get("CANVAS_TOKEN") or "").strip():
        return RunResult(False, 1, "The Canvas token is missing. Add it in Settings.")
    settings = config.to_settings()
    if not settings.base_url:
        return RunResult(False, 1, "The school Canvas address is missing. Add it in Settings.")
    try:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return RunResult(False, 1, "The save folder could not be created. Choose another folder in Settings.")

    from canvas_api import CanvasError, CanvasUnauthorized, set_base_url
    from fetch_canvas import build_report, default_output_path
    from make_report import default_output_path as default_pdf_path
    from make_report import write_pdf
    from run_report import finish_report

    try:
        set_base_url(settings.base_url)
        data = build_report(settings)
    except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
        log.exception("fetch failed")
        return RunResult(False, 2 if isinstance(exc, CanvasUnauthorized) else 1, friendly_error(exc))

    json_path = default_output_path(settings)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pdf_target = settings.output_dir / default_pdf_path(data, json_path).name
    try:
        report_path = write_pdf(data, pdf_target)
    except (OSError, ValueError) as exc:
        log.exception("pdf failed")
        return RunResult(False, 1, friendly_error(exc))

    outcomes: dict = {}
    try:
        code = finish_report(settings, data, report_path, outcomes=outcomes)
    except Exception as exc:
        log.exception("delivery failed")
        return RunResult(
            False,
            1,
            friendly_error(exc),
            pdf_path=str(report_path),
            missing=len(data.get("missing") or []),
            late=len(data.get("late") or []),
            preview=_preview(data),
        )
    summary = list(outcomes.get("summary") or [])
    missing = len(data.get("missing") or [])
    late = len(data.get("late") or [])
    result = RunResult(
        ok=code == 0,
        code=code,
        message=_message_from(summary, code),
        pdf_path=str(report_path),
        missing=missing,
        late=late,
        summary=summary,
        preview=_preview(data),
    )
    append_history(
        {
            "at": datetime.now().isoformat(timespec="minutes"),
            "ok": result.ok,
            "missing": missing,
            "late": late,
            "pdf": result.pdf_path,
            "message": result.message,
            "preview": result.preview,
            "student": data.get("student") or config.student_name,
            "school": data.get("school") or config.school_name,
        }
    )
    log.info(
        "run finished ok=%s missing=%s late=%s pdf=%s",
        result.ok,
        missing,
        late,
        result.pdf_path,
    )
    return result


def run_headless() -> int:
    """Entry point for Task Scheduler: --run, no window."""
    log = get_logger()
    config = load_config()
    if not config.setup_complete:
        log.info("headless run skipped because setup is not finished")
        return 1
    result = execute_report(config)
    if result.ok or result.pdf_path:
        from desktop.notify import notify_report_ready

        try:
            notify_report_ready(result.missing, result.late)
        except Exception:
            log.exception("notification failed")
    if not result.ok:
        log.info("headless run problem: %s", result.message)
    return 0 if result.ok else (result.code or 1)
