#!/usr/bin/env python3
"""Save wizard and main-window screenshots. No network and no real secrets."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CPR_UI_PLATFORM", "win32")


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/cursor/artifacts")
    destination.mkdir(parents=True, exist_ok=True)
    app_dir = Path(tempfile.mkdtemp(prefix="cpr-shot-"))
    os.environ["CPR_APP_DIR"] = str(app_dir)

    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication

    from desktop.app import Controller
    from desktop.main_window import MainWindow
    from desktop.store import AppConfig, append_history, save_config
    from desktop.theme import apply_theme
    from desktop.wizard import SetupWizard
    from report_pdf import write_report_pdf

    sample = json.loads((ROOT / "examples" / "sample_data.json").read_text(encoding="utf-8"))
    pdf_path = app_dir / "reports" / "Alex_Sample_Canvas_Report_2026-11-22.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    write_report_pdf(sample, pdf_path)
    config = AppConfig(
        base_url="https://yourschool.instructure.com",
        student_name="Alex Sample",
        school_name="Example High School",
        start_date="2026-11-01",
        output_dir=str(pdf_path.parent),
        email_enabled=False,
        print_enabled=False,
        setup_complete=True,
        schedule_days=["mon", "tue", "wed", "thu", "fri"],
        morning="06:45",
        evening="18:45",
    )
    save_config(config)
    history_file = app_dir / "history.json"
    if history_file.exists():
        history_file.unlink()
    append_history(
        {
            "at": "2026-11-22T18:45:00",
            "ok": True,
            "missing": 2,
            "late": 1,
            "messages": 1,
            "pdf": str(pdf_path),
            "message": "Report saved.",
            "student": "Alex Sample",
            "school": "Example High School",
            "preview": [
                {
                    "category": "Missing",
                    "course": "English 10",
                    "assignment": "Essay: Hometown Story",
                    "due": "2026-11-18",
                    "score": "",
                },
                {
                    "category": "Missing",
                    "course": "World History",
                    "assignment": "Map Skills Worksheet",
                    "due": "2026-11-20",
                    "score": "",
                },
                {
                    "category": "Late",
                    "course": "Geometry",
                    "assignment": "Lesson 5 Practice Set",
                    "due": "2026-11-13",
                    "score": "4",
                },
            ],
        }
    )

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    wizard = SetupWizard(Controller())
    wizard.resize(1000, 820)
    wizard.apply_preview(["Home Printer"])
    wizard.header_form.start.setDate(QDate(2026, 11, 1))
    wizard.show()
    app.processEvents()

    names = (
        "v2-wizard-01-welcome.png",
        "v2-wizard-02-school.png",
        "v2-wizard-03-token.png",
        "v2-wizard-04-names.png",
        "v2-wizard-05-delivery.png",
        "v2-wizard-06-options.png",
        "v2-wizard-07-schedule.png",
        "v2-wizard-08-done.png",
    )
    for index, name in enumerate(names):
        wizard.resize(1000, 1240 if index == 4 else 820)
        wizard.set_step(index)
        scroll = wizard.stack.currentWidget()
        if hasattr(scroll, "verticalScrollBar"):
            scroll.verticalScrollBar().setValue(0)
        app.processEvents()
        target = destination / name
        wizard.grab().save(str(target))
        print(target)
    wizard.close()

    window = MainWindow()
    window.resize(1040, 820)
    window.show()
    app.processEvents()
    main_path = destination / "v2-main-window.png"
    window.grab().save(str(main_path))
    print(main_path)
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
