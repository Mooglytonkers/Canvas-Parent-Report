#!/usr/bin/env python3
"""SMTP secrets stay out of config.ini and off unless enabled."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from config import load_dotenv, load_settings, smtp_security
from setup_wizard import read_env_file, render_config, write_config, write_env

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = (
    "SMTP_PASSWORD",
    "SMTP_USERNAME",
    "EMAIL_ENABLED",
    "EMAIL_TO",
    "EMAIL_FROM",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USE_TLS",
    "PRINT_ENABLED",
    "PRINTER_NAME",
    "PRINT_COPIES",
    "CANVAS_TOKEN",
)


class ConfigSecretTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in SECRET_KEYS}
        for key in SECRET_KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_example_defaults_are_off(self) -> None:
        settings = load_settings(ROOT / "config.example.ini", load_env=False)
        self.assertFalse(settings.email_enabled)
        self.assertFalse(settings.print_enabled)
        self.assertEqual(settings.smtp_port, 587)
        self.assertEqual(settings.smtp_security, "starttls")
        self.assertEqual(settings.print_copies, 1)
        self.assertEqual(settings.printer_name, "")
        self.assertEqual(settings.smtp_username, "")
        self.assertEqual(settings.smtp_password, "")

    def test_ini_password_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.ini"
            path.write_text(
                "[email]\nenabled = true\nto = parent@example.com\n"
                "from = reports@example.com\nsmtp_host = smtp.example.com\n"
                "smtp_port = 465\nsmtp_use_tls = true\n"
                "smtp_username = ini-user\nsmtp_password = ini-secret\n"
                "[print]\nenabled = true\nprinter_name = Office\ncopies = 2\n",
                encoding="utf-8",
            )
            os.environ["SMTP_USERNAME"] = "env-user"
            os.environ["SMTP_PASSWORD"] = "env-secret"
            with _capture_stderr() as err:
                settings = load_settings(path, load_env=False)
        text = err.getvalue()
        self.assertIn("SMTP password", text)
        self.assertIn("SMTP_USERNAME", text)
        self.assertEqual(settings.smtp_password, "env-secret")
        self.assertEqual(settings.smtp_username, "env-user")
        self.assertNotIn("ini-secret", settings.smtp_password)
        self.assertEqual(settings.smtp_security, "ssl")
        self.assertEqual(settings.smtp_port, 465)
        self.assertTrue(settings.email_enabled)
        self.assertTrue(settings.print_enabled)
        self.assertEqual(settings.printer_name, "Office")
        self.assertEqual(settings.print_copies, 2)

    def test_security_modes(self) -> None:
        self.assertEqual(smtp_security("true", 587), "starttls")
        self.assertEqual(smtp_security("false", 25), "plain")
        self.assertEqual(smtp_security("ssl", 2525), "ssl")
        self.assertEqual(smtp_security("true", 465), "ssl")

    def test_wizard_keeps_password_out_of_config(self) -> None:
        text = render_config(
            base_url="https://yourschool.instructure.com",
            student_name="Alex Sample",
            school_name="Example High School",
            start_date="2026-11-01",
            timezone="America/New_York",
            graded=True,
            mark_todos=False,
            student_user_id="",
            email_enabled=True,
            email_to="parent@example.com",
            email_from="reports@example.com",
            smtp_host="smtp.example.com",
            smtp_port="587",
            smtp_use_tls="true",
            print_enabled=True,
            printer_name="Office",
            print_copies="1",
        )
        for line in text.splitlines():
            code = line.split("#", 1)[0]
            lowered = code.lower()
            self.assertNotIn("smtp_password", lowered)
            self.assertNotIn("smtp_username", lowered)
        self.assertNotIn("mailbox-secret", text)
        self.assertIn("enabled = true", text)
        with tempfile.TemporaryDirectory() as folder:
            dest = write_config(
                base_url="https://yourschool.instructure.com",
                student_name="Alex Sample",
                school_name="Example High School",
                start_date="2026-11-01",
                timezone="America/New_York",
                graded=True,
                mark_todos=False,
                student_user_id="",
                email_enabled=True,
                email_to="parent@example.com",
                email_from="reports@example.com",
                smtp_host="smtp.example.com",
                print_enabled=False,
                dest_dir=Path(folder),
            )
            written = dest.read_text(encoding="utf-8")
            self.assertNotIn("mailbox-secret", written)
            self.assertTrue(dest.name == "config.ini")

    def test_env_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_env(
                {"CANVAS_TOKEN": "canvas-token", "SMTP_PASSWORD": "p@ss word"},
                root,
            )
            write_env({"SMTP_USERNAME": "reports@example.com"}, root)
            saved = read_env_file(root / ".env")
            self.assertEqual(saved["CANVAS_TOKEN"], "canvas-token")
            self.assertEqual(saved["SMTP_PASSWORD"], "p@ss word")
            self.assertEqual(saved["SMTP_USERNAME"], "reports@example.com")
            if os.name != "nt":
                mode = (root / ".env").stat().st_mode & 0o777
                self.assertEqual(mode, 0o600)
            load_dotenv(root / ".env")
            self.assertEqual(os.environ["SMTP_PASSWORD"], "p@ss word")
            self.assertNotIn("p@ss word", (root / "config.ini").read_text(encoding="utf-8") if (root / "config.ini").exists() else "")


class _capture_stderr:
    def __enter__(self):
        import io
        import sys

        self._old = sys.stderr
        self.buffer = io.StringIO()
        sys.stderr = self.buffer
        return self.buffer

    def __exit__(self, *exc) -> None:
        import sys

        sys.stderr = self._old


if __name__ == "__main__":
    unittest.main()
