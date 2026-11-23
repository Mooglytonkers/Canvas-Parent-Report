#!/usr/bin/env python3
"""Print and email failures stay isolated, and the steps run in order."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from canvas_api import CanvasError
from config import Settings
from email_report import EmailResult
from print_report import PrintResult
from run_report import finish_report, main


def _settings(**overrides) -> Settings:
    values = dict(
        student_name="Alex Sample",
        timezone="America/New_York",
        output_dir=Path("."),
        mark_graded_todos_done=True,
        print_enabled=True,
        printer_name="",
        print_copies=1,
        email_enabled=True,
        email_to="parent@example.com",
        email_from="reports@example.com",
        smtp_host="127.0.0.1",
        smtp_port=587,
        smtp_security="starttls",
    )
    values.update(overrides)
    return Settings(**values)


class FinishReportTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.write(b"%PDF-1.4\n%%EOF\n")
        handle.close()
        self.pdf = Path(handle.name)
        self.addCleanup(lambda: self.pdf.unlink(missing_ok=True))

    def test_print_failure_still_sends_email(self) -> None:
        events: list[str] = []

        def todo(settings, since, dry_run=False):
            events.append("todo")
            return 0

        def printed(path, **kwargs):
            events.append("print")
            return PrintResult(False, "printer offline")

        def mailed(settings, data, path, **kwargs):
            events.append("email")
            return EmailResult(True, "Sent to parent@example.com.")

        with mock.patch("run_report.mark_todos", todo), mock.patch(
            "run_report.print_pdf", printed
        ), mock.patch("run_report.send_report_email", mailed):
            code = finish_report(_settings(), {"student": "Alex Sample"}, self.pdf)
        self.assertEqual(events, ["todo", "print", "email"])
        self.assertEqual(code, 1)

    def test_email_failure_still_prints(self) -> None:
        events: list[str] = []

        def printed(path, **kwargs):
            events.append("print")
            return PrintResult(True, "Sent 1 copy to the default printer.")

        def mailed(settings, data, path, **kwargs):
            events.append("email")
            return EmailResult(False, "SMTP login failed.")

        with mock.patch("run_report.mark_todos", return_value=0), mock.patch(
            "run_report.print_pdf", printed
        ), mock.patch("run_report.send_report_email", mailed):
            code = finish_report(_settings(), {"student": "Alex Sample"}, self.pdf)
        self.assertEqual(events, ["print", "email"])
        self.assertEqual(code, 1)

    def test_todo_error_does_not_stop_later_steps(self) -> None:
        events: list[str] = []

        def todo(settings, since, dry_run=False):
            events.append("todo")
            raise CanvasError(500, "planner unavailable")

        def printed(path, **kwargs):
            events.append("print")
            return PrintResult(True, "Sent 1 copy to the default printer.")

        def mailed(settings, data, path, **kwargs):
            events.append("email")
            return EmailResult(True, "Sent to parent@example.com.")

        with mock.patch("run_report.mark_todos", todo), mock.patch(
            "run_report.print_pdf", printed
        ), mock.patch("run_report.send_report_email", mailed):
            code = finish_report(_settings(), {"student": "Alex Sample"}, self.pdf)
        self.assertEqual(events, ["todo", "print", "email"])
        self.assertEqual(code, 1)

    def test_no_print_skips_printing_but_still_emails(self) -> None:
        events: list[str] = []

        def printed(path, **kwargs):
            events.append("print")
            return PrintResult(True, "should not print")

        def mailed(settings, data, path, **kwargs):
            events.append("email")
            return EmailResult(True, "Sent to parent@example.com.")

        with mock.patch("run_report.print_pdf", printed), mock.patch(
            "run_report.send_report_email", mailed
        ):
            code = finish_report(
                _settings(mark_graded_todos_done=False),
                {"student": "Alex Sample"},
                self.pdf,
                no_print=True,
            )
        self.assertEqual(events, ["email"])
        self.assertEqual(code, 0)

    def test_flags_do_not_fetch_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.ini"
            config.write_text(
                "[canvas]\nbase_url = https://yourschool.instructure.com\n"
                "[report]\nstudent_name = Alex Sample\noutput_dir = output\n"
                "[email]\nenabled = true\nto = parent@example.com\n"
                "from = reports@example.com\nsmtp_host = 127.0.0.1\n"
                "smtp_port = 587\nsmtp_use_tls = true\n",
                encoding="utf-8",
            )
            with mock.patch("run_report.build_report") as build, mock.patch(
                "run_report.send_test_email",
                return_value=EmailResult(True, "Sent to parent@example.com."),
            ) as mailed, mock.patch(
                "run_report.test_print",
                return_value=PrintResult(True, "Test page: sent."),
            ) as printed:
                code = main(["--config", str(config), "--test-print", "--test-email"])
        self.assertFalse(build.called)
        self.assertTrue(printed.called)
        self.assertTrue(mailed.called)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
