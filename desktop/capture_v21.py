#!/usr/bin/env python3
"""Screenshots for To Do detail pages and schedule choices. Fictional data only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CPR_UI_PLATFORM", "win32")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAMPLE = {
    "student": "Alex Sample",
    "school": "Example High School",
    "title": "Canvas Missing Work Report",
    "scope": "Assignments due Nov 1, 2026 onward",
    "generated_at": "2026-11-23T08:00:00-05:00",
    "timezone": "America/New_York",
    "graded_counts_as_submitted": True,
    "missing": [
        {
            "course": "English 10",
            "assignment": "Essay: Hometown Story",
            "due": "2026-11-18",
            "score": None,
            "comment": None,
        }
    ],
    "late": [],
    "teacher_messages": [],
    "notes": [],
    "todo_details": {
        "enabled": True,
        "window_label": (
            "Overdue items due Nov 1, 2026 onward, plus work due in the next 14 days "
            "(through Dec 7, 2026)."
        ),
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
                "description": "Write one page about a place you know. Use the rubric for ideas and organization.",
                "rubric": "Rubric: Ideas (1 criterion)",
                "messages": ["Ms. Rivera — Please turn this in before Friday."],
            }
        ],
        "this_week": [
            {
                "status": "this_week",
                "status_label": "Due this week",
                "type_label": "Assignment",
                "course": "Geometry",
                "title": "Lesson 5 Practice Set",
                "due_label": "Wed, Nov 25, 2026 at 3:00 PM",
                "meta": "10 points · file upload",
                "html_url": "https://yourschool.instructure.com/courses/1/assignments/5",
                "locked_until": "",
                "description": "Finish the practice problems from lesson 5.",
                "rubric": "",
                "messages": [],
            }
        ],
        "later": [
            {
                "status": "later",
                "status_label": "Due later",
                "type_label": "Quiz",
                "course": "Chemistry",
                "title": "Lab safety quiz",
                "due_label": "Wed, Dec 2, 2026 at 11:59 PM",
                "meta": "15 points · quiz",
                "html_url": "https://yourschool.instructure.com/courses/1/assignments/9",
                "locked_until": "Locked until Mon, Nov 30, 2026 at 8:00 AM",
                "description": "A short quiz on the lab safety notes.",
                "rubric": "",
                "messages": [],
            }
        ],
    },
}


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/cursor/artifacts")
    destination.mkdir(parents=True, exist_ok=True)
    from report_pdf import write_report_pdf

    pdf = destination / "v21-sample-todo.pdf"
    write_report_pdf(SAMPLE, pdf)
    import subprocess

    prefix = destination / "v21-pdf-page"
    subprocess.run(["pdftoppm", "-png", "-r", "140", "-f", "2", "-l", "2", str(pdf), str(prefix)], check=True)
    page = destination / "v21-pdf-page-2.png"
    if not page.is_file():
        page = destination / "v21-pdf-page-1.png"
    page.replace(destination / "v21-pdf-todo-page2.png")

    from PySide6.QtWidgets import QApplication

    from desktop.theme import apply_theme
    from desktop.wizard import SetupWizard

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    wizard = SetupWizard()
    wizard.resize(1000, 820)
    wizard.address.set_value("https://yourschool.instructure.com")
    wizard.header_form.student.setText("Alex Sample")
    wizard.header_form.school.setText("Example High School")
    wizard.show()

    def grab(step: int, name: str) -> None:
        wizard.set_step(step)
        app.processEvents()
        wizard.grab().save(str(destination / name))
        print(destination / name)

    wizard.options.details.setChecked(True)
    grab(5, "v21-wizard-06-options.png")
    wizard.schedule.set_frequency("twice")
    grab(6, "v21-wizard-07-schedule-twice.png")
    wizard.schedule.set_frequency("daily")
    grab(6, "v21-wizard-07-schedule-once.png")
    wizard.schedule.set_frequency("weekly")
    grab(6, "v21-wizard-07-schedule-weekly.png")
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
