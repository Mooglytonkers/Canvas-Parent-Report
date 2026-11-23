#!/usr/bin/env python3
"""Send a report through a local SMTP stub and check the PDF attachment."""

from __future__ import annotations

import json
import socketserver
import threading
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest import mock

import smtplib

from config import Settings
from email_report import (
    build_message,
    deliver,
    format_stamp,
    send_report_email,
    subject_for,
)
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "examples" / "sample_data.json").read_text(encoding="utf-8"))
PDF_BYTES = b"%PDF-1.4\n%canvas-parent-report-test-attachment\n%%EOF\n"


class SmtpStub(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _SmtpHandler)
        self.messages: list[bytes] = []


class _SmtpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.wfile.write(b"220 localhost ESMTP\r\n")
        self.wfile.flush()
        while True:
            line = self.rfile.readline()
            if not line:
                break
            upper = line.decode("utf-8", "replace").strip().upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self.wfile.write(b"250-localhost\r\n250 AUTH PLAIN\r\n")
            elif upper == "DATA":
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                self.wfile.flush()
                chunks: list[bytes] = []
                while True:
                    data_line = self.rfile.readline()
                    if data_line in (b".\r\n", b".\n", b""):
                        break
                    if data_line.startswith(b".."):
                        data_line = data_line[1:]
                    chunks.append(data_line)
                self.server.messages.append(b"".join(chunks))
                self.wfile.write(b"250 OK\r\n")
            elif upper.startswith("AUTH"):
                self.wfile.write(b"235 OK\r\n")
            elif upper == "QUIT":
                self.wfile.write(b"221 Bye\r\n")
                self.wfile.flush()
                break
            else:
                self.wfile.write(b"250 OK\r\n")
            self.wfile.flush()


def _settings(port: int, **overrides) -> Settings:
    values = dict(
        student_name="Alex Sample",
        school_name="Example High School",
        timezone="America/New_York",
        email_enabled=True,
        email_to="parent@example.com, other@example.com",
        email_from="reports@example.com",
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_security="plain",
        smtp_username="reports@example.com",
        smtp_password="mailbox-secret",
    )
    values.update(overrides)
    return Settings(**values)


class EmailReportTests(unittest.TestCase):
    def test_stamp_and_subject(self) -> None:
        tz = ZoneInfo("America/New_York")
        self.assertEqual(
            format_stamp(datetime(2026, 11, 23, 0, 45, tzinfo=tz)),
            "Nov 23, 2026 12:45 AM",
        )
        self.assertEqual(
            format_stamp(datetime(2026, 11, 23, 12, 5, tzinfo=tz)),
            "Nov 23, 2026 12:05 PM",
        )
        self.assertEqual(
            format_stamp(datetime(2026, 11, 23, 18, 45, tzinfo=tz)),
            "Nov 23, 2026 6:45 PM",
        )
        self.assertEqual(
            subject_for("Alex Sample", datetime(2026, 11, 22, 18, 45, tzinfo=tz)),
            "Canvas report for Alex Sample - Nov 22, 2026 6:45 PM",
        )

    def test_local_smtp_receives_pdf_attachment(self) -> None:
        server = SmtpStub()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        with self._pdf() as pdf:
            result = send_report_email(_settings(port), SAMPLE, pdf, timeout=5)
        self.assertTrue(result.ok, result.message)
        self.assertIn("parent@example.com", result.message)
        self.assertEqual(len(server.messages), 1)
        message = BytesParser(policy=policy.default).parsebytes(server.messages[0])
        self.assertEqual(
            message["Subject"],
            "Canvas report for Alex Sample - Nov 22, 2026 6:45 PM",
        )
        self.assertEqual(message["From"], "reports@example.com")
        self.assertEqual(message["To"], "parent@example.com, other@example.com")
        plain = message.get_body(preferencelist=("plain",))
        html_part = message.get_body(preferencelist=("html",))
        self.assertIsNotNone(plain)
        self.assertIsNotNone(html_part)
        plain_text = plain.get_content()
        html_text = html_part.get_content()
        self.assertIn("Essay: Hometown Story", plain_text)
        self.assertIn("| Missing |", plain_text)
        self.assertIn("| Late |", plain_text)
        self.assertIn("Lesson 5 Practice Set", plain_text)
        self.assertNotIn("mailbox-secret", plain_text)
        self.assertNotIn("mailbox-secret", html_text)
        self.assertNotIn("mailbox-secret", message["Subject"])
        self.assertIn("<table", html_text)
        self.assertIn("Essay: Hometown Story", html_text)
        self.assertIn(">Missing<", html_text)
        self.assertIn(">Late<", html_text)
        attachments = [
            part
            for part in message.iter_attachments()
            if part.get_content_type() == "application/pdf"
        ]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), pdf.name)
        self.assertEqual(attachments[0].get_content(), PDF_BYTES)

    def test_starttls_and_ssl_paths(self) -> None:
        with self._pdf() as pdf:
            settings = _settings(587, smtp_security="starttls", smtp_host="smtp.example.com")
            message = build_message(settings, SAMPLE, pdf)

            class FakeSMTP:
                def __init__(self, host, port, timeout=None, context=None):
                    self.host = host
                    self.port = port
                    self.calls: list[str] = []
                    self.login_args = None
                    self.sent = None

                def ehlo(self) -> None:
                    self.calls.append("ehlo")

                def starttls(self, context=None) -> None:
                    self.calls.append("starttls")

                def login(self, user, password) -> None:
                    self.login_args = (user, password)
                    self.calls.append("login")

                def send_message(self, outgoing) -> None:
                    self.sent = outgoing

                def quit(self) -> None:
                    self.calls.append("quit")

            holder: list[FakeSMTP] = []

            def factory(*args, **kwargs):
                client = FakeSMTP(*args, **kwargs)
                holder.append(client)
                return client

            with mock.patch("email_report.smtplib.SMTP", factory):
                result = deliver(settings, message)
            self.assertTrue(result.ok, result.message)
            self.assertEqual(holder[0].calls.count("starttls"), 1)
            self.assertEqual(holder[0].login_args, ("reports@example.com", "mailbox-secret"))
            self.assertIsNotNone(holder[0].sent)

            ssl_settings = _settings(465, smtp_security="ssl", smtp_host="smtp.example.com")
            ssl_holder: list[FakeSMTP] = []

            def ssl_factory(*args, **kwargs):
                client = FakeSMTP(*args, **kwargs)
                ssl_holder.append(client)
                return client

            with mock.patch("email_report.smtplib.SMTP_SSL", ssl_factory), mock.patch(
                "email_report.smtplib.SMTP",
                side_effect=AssertionError("plain SMTP should not be used on port 465"),
            ):
                ssl_result = deliver(ssl_settings, message)
            self.assertTrue(ssl_result.ok, ssl_result.message)
            self.assertEqual(ssl_holder[0].port, 465)
            self.assertNotIn("starttls", ssl_holder[0].calls)

    def test_auth_failure_hides_password(self) -> None:
        class Rejecting:
            def __init__(self, host, port, timeout=None, context=None):
                pass

            def ehlo(self) -> None:
                return None

            def starttls(self, context=None) -> None:
                return None

            def login(self, user, password) -> None:
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

            def send_message(self, message) -> None:
                raise AssertionError("should not send")

            def quit(self) -> None:
                return None

        with self._pdf() as pdf:
            settings = _settings(587, smtp_security="starttls")
            message = build_message(settings, SAMPLE, pdf)
            with mock.patch("email_report.smtplib.SMTP", Rejecting):
                result = deliver(settings, message)
        self.assertFalse(result.ok)
        self.assertNotIn("mailbox-secret", result.message)
        self.assertIn("SMTP login failed", result.message)

    def test_missing_settings_do_not_raise(self) -> None:
        with self._pdf() as pdf:
            settings = _settings(587, email_to="", smtp_host="")
            result = send_report_email(settings, SAMPLE, pdf, timeout=2)
        self.assertFalse(result.ok)
        self.assertIn("EMAIL_TO", result.message)
        self.assertIn("SMTP_HOST", result.message)

    def _pdf(self):
        import tempfile

        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.write(PDF_BYTES)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return _OpenPath(path)


class _OpenPath:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *exc) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
