#!/usr/bin/env python3
"""Fetch Canvas data, build the missing-work PDF, then optional follow-up steps.

Order after the PDF is built: mark To Dos if enabled, print if enabled, email
if enabled. A print or email failure does not skip the other step.

Usage:
    python3 run_report.py
    python3 run_report.py --print
    python3 run_report.py --no-print
    python3 run_report.py --no-todo
    python3 run_report.py --test-print
    python3 run_report.py --test-email

Reads CANVAS_TOKEN from the environment or a local .env file only; never
prints its value. The SMTP password is handled the same way. Exit code 2
means the Canvas token was rejected (401).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from canvas_api import CanvasError, CanvasUnauthorized, handle_cli_error
from config import Settings, load_settings
from email_report import EmailResult, send_report_email, send_test_email
from fetch_canvas import build_report, default_output_path, print_markdown_table
from make_report import default_output_path as default_pdf_path
from make_report import write_pdf
from mark_graded_done import run as mark_todos
from print_report import PrintResult, print_pdf, test_print


def printing_requested(settings: Settings, *, do_print: bool, no_print: bool) -> bool:
    if no_print:
        return False
    if do_print:
        return True
    return bool(settings.print_enabled or (settings.print_command or "").strip())


def _pdf_problem(report_path: Path) -> str | None:
    if report_path.suffix.lower() != ".pdf":
        return "the report is HTML, not a PDF, so this step was skipped"
    if not report_path.is_file():
        return f"PDF not found: {report_path}"
    return None


def finish_report(
    settings: Settings,
    data: dict,
    report_path: Path,
    *,
    do_print: bool = False,
    no_print: bool = False,
    no_todo: bool = False,
) -> int:
    """Run To Do, print, and email steps. Print and email failures stay isolated."""
    summary: list[str] = [f"Report: {report_path}"]
    code = 0

    if settings.mark_graded_todos_done and not no_todo:
        try:
            todo_status = mark_todos(settings, settings.todo_since(), dry_run=False)
        except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
            todo_status = handle_cli_error(exc)
        if todo_status == 0:
            summary.append("To Do: finished")
        else:
            summary.append("To Do: failed")
            if todo_status == 2:
                code = 2
            elif code == 0:
                code = todo_status
    else:
        summary.append("To Do: off")

    if printing_requested(settings, do_print=do_print, no_print=no_print):
        problem = _pdf_problem(report_path)
        if problem:
            print(f"warning: {problem}.", file=sys.stderr)
            summary.append(f"Print: skipped ({problem})")
            if code == 0:
                code = 1
        else:
            try:
                printed = print_pdf(
                    report_path,
                    printer_name=settings.printer_name,
                    copies=settings.print_copies,
                    print_command=settings.print_command,
                )
            except Exception as exc:
                printed = PrintResult(False, f"Could not print ({exc}).")
            print(("Print: " if printed.ok else "warning: print: ") + printed.message)
            summary.append("Print: " + printed.message)
            if not printed.ok and code == 0:
                code = 1
    else:
        summary.append("Print: off")

    if settings.email_enabled:
        problem = _pdf_problem(report_path)
        if problem:
            print(f"warning: {problem}.", file=sys.stderr)
            summary.append(f"Email: skipped ({problem})")
            if code == 0:
                code = 1
        else:
            try:
                mailed = send_report_email(settings, data, report_path)
            except Exception as exc:
                mailed = EmailResult(False, f"Could not send email ({exc}).")
            print(("Email: " if mailed.ok else "warning: email: ") + mailed.message)
            summary.append("Email: " + mailed.message)
            if not mailed.ok and code == 0:
                code = 1
    else:
        summary.append("Email: off")

    print()
    print("Summary")
    print("-------")
    for line in summary:
        print(line)
    return code


def run_checks(settings: Settings, *, test_print_flag: bool, test_email_flag: bool) -> int:
    """Try printing and email without contacting Canvas."""
    summary: list[str] = []
    code = 0
    if test_print_flag:
        try:
            printed = test_print(
                output_dir=settings.output_dir,
                printer_name=settings.printer_name,
                copies=settings.print_copies,
                print_command=settings.print_command,
            )
        except Exception as exc:
            printed = PrintResult(False, f"Could not print ({exc}).")
        print(printed.message)
        summary.append("Print: " + printed.message)
        if not printed.ok:
            code = 1
    if test_email_flag:
        try:
            mailed = send_test_email(settings)
        except Exception as exc:
            mailed = EmailResult(False, f"Could not send email ({exc}).")
        print(mailed.message)
        summary.append("Email: " + mailed.message)
        if not mailed.ok and code == 0:
            code = 1
    print()
    print("Summary")
    print("-------")
    for line in summary:
        print(line)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Canvas missing/late work, build a PDF, and optionally "
        "mark To Dos, print, and email the report."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.ini (default: config.ini next to this script)",
    )
    parser.add_argument(
        "--print",
        dest="do_print",
        action="store_true",
        help="Print the PDF even if printing is off in config",
    )
    parser.add_argument(
        "--no-print",
        dest="no_print",
        action="store_true",
        help="Do not print, even if printing is on in config",
    )
    parser.add_argument(
        "--test-print",
        action="store_true",
        help="Print a one-page test PDF and exit (does not contact Canvas)",
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="Send a test email with a tiny PDF attached and exit (does not contact Canvas)",
    )
    parser.add_argument(
        "--no-todo",
        action="store_true",
        help="Do not mark graded To Do items done, even if that option is on in config",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Write HTML instead of PDF",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output PDF or HTML path (default: under output_dir from config)",
    )
    args = parser.parse_args(argv)

    if args.do_print and args.no_print:
        print("error: use only one of --print and --no-print.", file=sys.stderr)
        return 1

    try:
        settings = load_settings(args.config)
    except (OSError, ValueError) as exc:
        return handle_cli_error(exc)

    if args.test_print or args.test_email:
        return run_checks(
            settings,
            test_print_flag=args.test_print,
            test_email_flag=args.test_email,
        )

    try:
        data = build_report(settings)
    except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
        return handle_cli_error(exc)

    json_path = default_output_path(settings)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    pdf_target = (
        args.output.expanduser().resolve()
        if args.output
        else default_pdf_path(data, json_path, html=args.html)
    )
    # Keep generated PDFs in the configured output folder when using the default name.
    if args.output is None:
        pdf_target = settings.output_dir / pdf_target.name
    report_path = write_pdf(data, pdf_target, prefer_html=args.html)
    print(report_path)
    print_markdown_table(data)

    return finish_report(
        settings,
        data,
        report_path,
        do_print=args.do_print,
        no_print=args.no_print,
        no_todo=args.no_todo,
    )


if __name__ == "__main__":
    sys.exit(main())
