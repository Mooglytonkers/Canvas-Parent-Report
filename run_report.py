#!/usr/bin/env python3
"""Fetch Canvas data, build the missing-work PDF, and optionally mark To Dos.

Usage:
    python3 run_report.py
    python3 run_report.py --print
    python3 run_report.py --no-todo

Reads CANVAS_TOKEN from the environment or a local .env file only; never
prints its value. Exit code 2 means the token was rejected (401).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from canvas_api import CanvasError, CanvasUnauthorized, handle_cli_error
from config import load_settings
from fetch_canvas import build_report, default_output_path, print_markdown_table
from make_report import default_output_path as default_pdf_path
from make_report import write_pdf
from mark_graded_done import run as mark_todos


def _print_file(pdf_path: Path, print_command: str) -> int:
    """Send the PDF to a printer. Never interpolates secrets."""
    path = str(pdf_path)
    command = (print_command or "default").strip()
    if command.lower() in ("default", "system", "yes", "true"):
        if os.name == "nt":
            try:
                os.startfile(path, "print")  # type: ignore[attr-defined]
                print(f"Sent to the default printer: {pdf_path}")
                return 0
            except OSError as exc:
                print(f"error: could not print ({exc}).", file=sys.stderr)
                return 1
        lp = _which("lp")
        if not lp:
            print(
                "error: no print command is configured, and the lp command was not found. "
                "Set print_command in config.ini (use {pdf} as the file placeholder).",
                file=sys.stderr,
            )
            return 1
        command = f"{lp} {{pdf}}"
    if "{pdf}" in command:
        # Substitute only the path; do not run a shell, to avoid surprises.
        parts = shlex.split(command, posix=(os.name != "nt"))
        parts = [path if part == "{pdf}" else part.replace("{pdf}", path) for part in parts]
    else:
        parts = shlex.split(command, posix=(os.name != "nt")) + [path]
    try:
        result = subprocess.run(parts, check=False)
    except OSError as exc:
        print(f"error: could not run the print command ({exc}).", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(
            f"error: the print command exited with code {result.returncode}.",
            file=sys.stderr,
        )
        return 1
    print(f"Sent to the printer: {pdf_path}")
    return 0


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Canvas missing/late work, build a PDF, and optionally "
        "mark graded To Do items done."
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
        help="Print the PDF after it is built (uses print_command, or the system default)",
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

    try:
        settings = load_settings(args.config)
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

    status = 0
    if settings.mark_graded_todos_done and not args.no_todo:
        try:
            todo_status = mark_todos(settings, settings.todo_since(), dry_run=False)
        except (CanvasUnauthorized, CanvasError, OSError, ValueError) as exc:
            return handle_cli_error(exc)
        if todo_status != 0:
            status = todo_status

    should_print = args.do_print or bool(settings.print_command)
    if should_print:
        if report_path.suffix.lower() not in {".pdf"}:
            print(
                "warning: the report is HTML, not a PDF, so it was not sent to the printer. "
                "Open the HTML file in a browser and use Print, or install WeasyPrint.",
                file=sys.stderr,
            )
        else:
            print_status = _print_file(report_path, settings.print_command or "default")
            if print_status != 0 and status == 0:
                status = print_status
    return status


if __name__ == "__main__":
    sys.exit(main())
