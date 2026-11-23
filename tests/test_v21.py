#!/usr/bin/env python3
"""To Do detail windows and schedule frequency."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from desktop.schedule import schedule_plan, task_xml
from desktop.store import AppConfig, load_config, save_config
from todo_details import bucket_for, strip_html, window_label

EASTERN = ZoneInfo("America/New_York")


class TodoWindowTests(unittest.TestCase):
    def test_buckets_use_start_date_and_fourteen_days(self) -> None:
        now = datetime(2026, 11, 23, 8, 0, tzinfo=EASTERN)  # Monday
        start = datetime(2026, 11, 1, tzinfo=EASTERN).date()
        self.assertIsNone(bucket_for(datetime(2026, 10, 15, 12, tzinfo=EASTERN), now, start, 14))
        self.assertEqual(bucket_for(datetime(2026, 11, 18, 23, 59, tzinfo=EASTERN), now, start, 14), "overdue")
        self.assertEqual(bucket_for(datetime(2026, 11, 25, 15, tzinfo=EASTERN), now, start, 14), "this_week")
        self.assertEqual(bucket_for(datetime(2026, 12, 2, 15, tzinfo=EASTERN), now, start, 14), "later")
        self.assertIsNone(bucket_for(datetime(2026, 12, 20, 15, tzinfo=EASTERN), now, start, 14))

    def test_strip_html_caps_length(self) -> None:
        raw = "<p>Hello <b>there</b></p>" + (" word" * 200)
        text = strip_html(raw, 40)
        self.assertNotIn("<", text)
        self.assertLessEqual(len(text), 40)
        self.assertTrue(text.endswith("…"))

    def test_window_label_mentions_fourteen_days(self) -> None:
        label = window_label(datetime(2026, 11, 1).date(), 14, datetime(2026, 11, 23, tzinfo=EASTERN))
        self.assertIn("14 days", label)
        self.assertIn("Nov 1, 2026", label)


class ScheduleFrequencyTests(unittest.TestCase):
    def test_legacy_config_maps_to_twice_a_day(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.ini"
            path.write_text(
                "[schedule]\ndays = mon,tue,wed,thu,fri\nmorning = 06:45\nevening = 18:45\n",
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertEqual(loaded.frequency, "twice")
            days, times = schedule_plan(loaded)
            self.assertEqual(days, ["mon", "tue", "wed", "thu", "fri"])
            self.assertEqual(times, ["06:45", "18:45"])

    def test_xml_for_each_frequency(self) -> None:
        twice = AppConfig(frequency="twice", schedule_days=["mon", "wed"], morning="06:45", evening="18:45")
        days, times = schedule_plan(twice)
        xml = task_xml(command="CanvasParentReport.exe", arguments="--run", days=days, times=times, run_missed=True)
        self.assertEqual(xml.count("<CalendarTrigger>"), 2)
        self.assertIn("<Monday />", xml)
        self.assertIn("<Wednesday />", xml)
        self.assertNotIn("<Friday />", xml)

        daily = AppConfig(frequency="daily", schedule_days=["mon", "fri"], daily_time="07:15", morning="07:15")
        days, times = schedule_plan(daily)
        xml = task_xml(command="CanvasParentReport.exe", arguments="--run", days=days, times=times, run_missed=False)
        self.assertEqual(xml.count("<CalendarTrigger>"), 1)
        self.assertIn("07:15:00", xml)
        self.assertIn("<Friday />", xml)
        self.assertNotIn("18:45:00", xml)

        weekly = AppConfig(frequency="weekly", weekly_day="sun", daily_time="09:00", schedule_days=["sun"])
        days, times = schedule_plan(weekly)
        xml = task_xml(command="CanvasParentReport.exe", arguments="--run", days=days, times=times, run_missed=True)
        self.assertEqual(days, ["sun"])
        self.assertEqual(xml.count("<Sunday />"), 1)
        self.assertNotIn("<Monday />", xml)
        self.assertIn("09:00:00", xml)

    def test_saved_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.ini"
            config = AppConfig(
                frequency="weekly",
                weekly_day="wed",
                daily_time="08:30",
                todo_detail_page=True,
                todo_days_ahead=14,
                student_name="Alex Sample",
                school_name="Example High School",
                base_url="https://yourschool.instructure.com",
            )
            save_config(config, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("frequency = weekly", text)
            self.assertIn("todo_detail_page = true", text)
            loaded = load_config(path)
            self.assertEqual(loaded.frequency, "weekly")
            self.assertEqual(loaded.weekly_day, "wed")
            self.assertTrue(loaded.todo_detail_page)
            self.assertEqual(schedule_plan(loaded), (["wed"], ["08:30"]))


class TodoPdfTests(unittest.TestCase):
    def test_reportlab_adds_a_second_page(self) -> None:
        from report_pdf import write_report_pdf

        data = {
            "student": "Alex Sample",
            "school": "Example High School",
            "title": "Canvas Missing Work Report",
            "scope": "Assignments due Nov 1, 2026 onward",
            "generated_at": "2026-11-23T08:00:00-05:00",
            "timezone": "America/New_York",
            "graded_counts_as_submitted": True,
            "missing": [],
            "late": [],
            "teacher_messages": [],
            "notes": [],
            "todo_details": {
                "enabled": True,
                "window_label": "Overdue items due Nov 1, 2026 onward, plus work due in the next 14 days (through Dec 7, 2026).",
                "observer_note": "",
                "overdue": [
                    {
                        "status": "overdue",
                        "status_label": "Overdue",
                        "type_label": "Assignment",
                        "course": "English 10",
                        "title": "Essay: Hometown Story",
                        "due_label": "Tue, Nov 18, 2026 at 11:59 PM",
                        "meta": "20 points · online text",
                        "html_url": "https://yourschool.instructure.com/courses/1/assignments/2",
                        "locked_until": "",
                        "description": "Write one page about a place you know.",
                        "rubric": "Rubric: Ideas (1 criterion)",
                        "messages": ["Ms. Rivera — Please turn this in before Friday."],
                    }
                ],
                "this_week": [],
                "later": [],
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.pdf"
            write_report_pdf(data, target)
            blob = target.read_bytes()
        self.assertTrue(blob.startswith(b"%PDF"))
        pages = len(__import__("re").findall(rb"/Type\s*/Page(?!s)", blob))
        self.assertGreaterEqual(pages, 2)


if __name__ == "__main__":
    unittest.main()
