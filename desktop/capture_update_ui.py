#!/usr/bin/env python3
"""Screenshots of the update controls. Fictional sample data only. No network."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CPR_UI_PLATFORM", "win32")
os.environ["CPR_SKIP_UPDATE_CHECK"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/cursor/artifacts")
    destination.mkdir(parents=True, exist_ok=True)
    app_dir = Path(tempfile.mkdtemp(prefix="cpr-update-shot-"))
    os.environ["CPR_APP_DIR"] = str(app_dir)

    from PySide6.QtWidgets import QApplication

    from desktop.main_window import MainWindow
    from desktop.store import append_history, AppConfig, save_config
    from desktop.theme import apply_theme
    from desktop.update_ui import UpdateDownloadDialog
    from desktop.updates import RELEASES_PAGE, UpdateOffer

    reports = app_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    pdf_path = reports / "Alex_Sample_Canvas_Report_2026-11-22.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% fictional sample\n")
    config = AppConfig(
        base_url="https://yourschool.instructure.com",
        student_name="Alex Sample",
        school_name="Example High School",
        start_date="2026-11-01",
        output_dir=str(reports),
        email_enabled=False,
        print_enabled=False,
        setup_complete=True,
        schedule_days=["mon", "tue", "wed", "thu", "fri"],
        morning="06:45",
        evening="18:45",
    )
    save_config(config)
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
    window = MainWindow()
    window.resize(1100, 860)
    window.show()
    app.processEvents()
    main_path = destination / "update_main_window.png"
    window.grab().save(str(main_path))
    print(main_path)

    offer = UpdateOffer(
        current="2.2.0",
        latest="2.3.0",
        notes=(
            "The app can check for updates and install them.\n"
            "Settings, the Canvas token, and the schedule stay on this computer."
        ),
        html_url=RELEASES_PAGE,
        installer_name="CanvasParentReport-Setup-2.3.0.exe",
        installer_url=(
            "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/"
            "v2.3.0/CanvasParentReport-Setup-2.3.0.exe"
        ),
        installer_size=28_000_000,
        checksum_name="SHA256SUMS.txt",
        checksum_url=(
            "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/"
            "v2.3.0/SHA256SUMS.txt"
        ),
    )
    window.resize(1100, 980)
    window.update_prompt.show_offer(offer, can_install=True)
    app.processEvents()
    available_path = destination / "update_available.png"
    window.grab().save(str(available_path))
    print(available_path)

    window.banner.show_message("success", "You're up to date. Version 2.2.0 is the latest.")
    window.update_prompt.hide()
    window.resize(1100, 860)
    app.processEvents()
    current_path = destination / "update_up_to_date.png"
    window.grab().save(str(current_path))
    print(current_path)

    dialog = UpdateDownloadDialog(window)
    dialog.set_status("Downloading CanvasParentReport-Setup-2.3.0.exe")
    dialog.set_progress(11_800_000, 28_000_000)
    dialog.resize(520, 240)
    dialog.show()
    app.processEvents()
    progress_path = destination / "update_download_progress.png"
    dialog.grab().save(str(progress_path))
    print(progress_path)
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
