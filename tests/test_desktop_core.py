#!/usr/bin/env python3
"""Config storage, scheduler commands, and connection messages."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from canvas_api import CanvasError, CanvasUnauthorized
from desktop.connection import friendly_error, validate_base_url
from desktop.notify import report_ready_text
from desktop.schedule import (
    TASK_NAME,
    friendly_when,
    launch_parts,
    next_occurrence,
    schtasks_create_command,
    task_xml,
)
from desktop.secrets import get_token, set_smtp_password, set_token
from desktop.store import AppConfig, load_config, save_config

ROOT = Path(__file__).resolve().parents[1]


class ScheduleTests(unittest.TestCase):
    def test_task_xml_and_schtasks_command(self) -> None:
        xml = task_xml(
            command=r"C:\Program Files\Canvas & Report\CanvasParentReport.exe",
            arguments="--run",
            days=["mon", "tue", "wed", "thu", "fri"],
            times=["06:45", "18:45"],
            run_missed=True,
        )
        self.assertIn("<Monday />", xml)
        self.assertIn("<Friday />", xml)
        self.assertNotIn("<Saturday />", xml)
        self.assertNotIn("<Sunday />", xml)
        self.assertIn("06:45:00", xml)
        self.assertIn("18:45:00", xml)
        self.assertEqual(xml.count("<CalendarTrigger>"), 2)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)
        self.assertIn("--run", xml)
        self.assertIn("Canvas &amp; Report", xml)
        self.assertNotIn("Canvas & Report", xml.split("<Command>")[-1].split("</Command>")[0])
        command = schtasks_create_command(Path(r"C:\Users\Example\AppData\Roaming\CanvasParentReport\schedule-task.xml"))
        self.assertEqual(command[:4], ["schtasks", "/Create", "/TN", TASK_NAME])
        self.assertIn("/XML", command)
        self.assertIn("/F", command)
        self.assertTrue(command[-1] == "/F" or "/F" in command)

    def test_missed_run_can_be_turned_off(self) -> None:
        xml = task_xml(
            command="CanvasParentReport.exe",
            arguments="--run",
            days=["mon"],
            times=["06:45"],
            run_missed=False,
        )
        self.assertIn("<StartWhenAvailable>false</StartWhenAvailable>", xml)
        self.assertEqual(xml.count("<CalendarTrigger>"), 1)

    def test_frozen_launch_uses_run_flag(self) -> None:
        command, arguments = launch_parts(
            exe=r"C:\Apps\CanvasParentReport.exe",
            frozen=True,
        )
        self.assertEqual(command, r"C:\Apps\CanvasParentReport.exe")
        self.assertEqual(arguments, "--run")

    def test_next_occurrence(self) -> None:
        # 2026-11-23 is a Monday. Wednesday the 25th at 10:00 is before the evening run.
        wednesday = datetime(2026, 11, 25, 10, 0)
        nxt = next_occurrence(["mon", "tue", "wed", "thu", "fri"], ["06:45", "18:45"], wednesday)
        self.assertEqual(nxt, datetime(2026, 11, 25, 18, 45))
        after_evening = datetime(2026, 11, 25, 19, 0)
        nxt = next_occurrence(["mon", "tue", "wed", "thu", "fri"], ["06:45", "18:45"], after_evening)
        self.assertEqual(nxt, datetime(2026, 11, 26, 6, 45))
        saturday = datetime(2026, 11, 28, 12, 0)
        nxt = next_occurrence(["mon", "tue", "wed", "thu", "fri"], ["06:45", "18:45"], saturday)
        self.assertEqual(nxt, datetime(2026, 11, 30, 6, 45))
        self.assertIn("Monday", friendly_when(datetime(2026, 11, 23, 6, 45)))
        self.assertIn("6:45 AM", friendly_when(datetime(2026, 11, 23, 6, 45)))


class StoreAndSecretTests(unittest.TestCase):
    def test_config_does_not_keep_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            os.environ["CPR_APP_DIR"] = str(root)
            self.addCleanup(os.environ.pop, "CPR_APP_DIR", None)
            config = AppConfig(
                base_url="https://yourschool.instructure.com",
                student_name="Alex Sample",
                school_name="Example High School",
                start_date="2026-11-01",
                output_dir=str(root / "reports"),
                email_enabled=True,
                email_to="parent@example.com",
                email_from="parent@example.com",
                smtp_host="smtp.gmail.com",
                smtp_username="parent@example.com",
                print_enabled=True,
                printer_name="Home Printer",
                print_copies=2,
                setup_complete=True,
            )
            path = save_config(config, root / "config.ini")
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            self.assertNotIn("smtp_password", lowered)
            self.assertNotIn("canvas_token", lowered)
            self.assertNotIn("test-token-value", text)
            self.assertNotIn("mailbox-secret", text)
            loaded = load_config(path)
            self.assertEqual(loaded.student_name, "Alex Sample")
            self.assertEqual(loaded.base_url, "https://yourschool.instructure.com")
            self.assertTrue(loaded.email_enabled)
            self.assertEqual(loaded.print_copies, 2)
            self.assertTrue(loaded.setup_complete)
            self.assertEqual(loaded.schedule_days, ["mon", "tue", "wed", "thu", "fri"])

            with mock.patch("desktop.secrets.sys.platform", "linux"):
                set_token("test-token-value")
                set_smtp_password("mailbox-secret")
                self.assertEqual(get_token(), "test-token-value")
            env_text = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("test-token-value", env_text)
            self.assertIn("mailbox-secret", env_text)
            self.assertNotIn("test-token-value", path.read_text(encoding="utf-8"))
            self.assertNotIn("mailbox-secret", path.read_text(encoding="utf-8"))

    def test_windows_secrets_use_keyring(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            os.environ["CPR_APP_DIR"] = str(folder)
            self.addCleanup(os.environ.pop, "CPR_APP_DIR", None)
            with mock.patch("desktop.secrets.sys.platform", "win32"), mock.patch(
                "keyring.set_password"
            ) as set_password, mock.patch("keyring.get_password", return_value="from-keyring"):
                set_token("test-token-value")
                self.assertEqual(get_token(), "from-keyring")
            set_password.assert_called()
            self.assertFalse((Path(folder) / ".env").exists())


class ConnectionMessageTests(unittest.TestCase):
    def test_url_validation(self) -> None:
        self.assertIsNone(validate_base_url("https://yourschool.instructure.com"))
        self.assertIsNone(validate_base_url("https://yourschool.instructure.com/"))
        self.assertIsNotNone(validate_base_url("yourschool.instructure.com"))
        self.assertIsNotNone(validate_base_url("https://"))
        self.assertIsNotNone(validate_base_url(""))

    def test_friendly_errors_do_not_leak_a_token(self) -> None:
        rejected = friendly_error(CanvasUnauthorized(401, "Canvas API returned 401 Unauthorized."))
        self.assertIn("token", rejected.lower())
        self.assertNotIn("test-token-value", rejected)
        blocked = friendly_error(CanvasError(403, "Canvas API returned HTTP 403."))
        self.assertIn("blocked", blocked.lower())
        offline = friendly_error(CanvasError(None, "Canvas API request failed: URLError."))
        self.assertIn("internet", offline.lower())
        self.assertIn("Report ready: 0 missing, 1 late", report_ready_text(0, 1))


class ReportPdfTests(unittest.TestCase):
    def test_reportlab_pdf_from_sample(self) -> None:
        try:
            from report_pdf import write_report_pdf
        except ImportError:
            self.skipTest("reportlab is not installed")
        data = json.loads((ROOT / "examples" / "sample_data.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sample.pdf"
            write_report_pdf(data, target)
            blob = target.read_bytes()
        self.assertTrue(blob.startswith(b"%PDF"))
        self.assertGreater(len(blob), 1000)


if __name__ == "__main__":
    unittest.main()
