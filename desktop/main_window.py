"""The window parents see after setup."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.forms import Banner
from desktop.paths import resource_path
from desktop.runner import RunResult, execute_report
from desktop.schedule import friendly_when, next_occurrence
from desktop.store import load_config, load_history
from desktop.version import APP_NAME, APP_VERSION
from desktop.workers import FnWorker


def _count_box(caption: str, color: str) -> tuple[QFrame, QLabel]:
    frame = QFrame()
    frame.setObjectName("countCard")
    frame.setStyleSheet(
        "QFrame#countCard { background: #ffffff; border: 1px solid #e4ebf2; border-radius: 12px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 10, 18, 12)
    value = QLabel("—")
    value.setStyleSheet(
        f"font-size: 28px; font-weight: 650; color: {color}; background: transparent; border: none;"
    )
    label = QLabel(caption)
    label.setStyleSheet("color: #5d6d7e; background: transparent; border: none;")
    layout.addWidget(value)
    layout.addWidget(label)
    return frame, value


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(880, 640)
        self.resize(1040, 760)
        icon = resource_path("icon.png")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self._worker = None
        self._pdf = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        if icon.is_file():
            mark = QLabel()
            from PySide6.QtGui import QPixmap

            mark.setPixmap(QPixmap(str(icon)).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(mark)
        titles = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("headerName")
        tag = QLabel("Missing and late work, in one page")
        tag.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(tag)
        header.addLayout(titles)
        header.addStretch(1)
        settings = QPushButton("Settings")
        settings.setObjectName("secondary")
        settings.clicked.connect(self.open_settings)
        header.addWidget(settings)
        root.addLayout(header)

        self.banner = Banner()
        root.addWidget(self.banner)

        status = QFrame()
        status.setObjectName("card")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(20, 18, 20, 18)
        text_col = QVBoxLayout()
        self.last_label = QLabel("Last run")
        self.last_label.setObjectName("fieldLabel")
        self.last_value = QLabel("No report yet")
        self.last_value.setWordWrap(True)
        self.result_value = QLabel("When you run a report, the result shows up here.")
        self.result_value.setObjectName("muted")
        self.result_value.setWordWrap(True)
        self.next_value = QLabel()
        self.next_value.setObjectName("muted")
        text_col.addWidget(self.last_label)
        text_col.addWidget(self.last_value)
        text_col.addWidget(self.result_value)
        text_col.addSpacing(8)
        text_col.addWidget(self.next_value)
        status_layout.addLayout(text_col, 1)
        self.run_button = QPushButton("Run report now")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumSize(190, 52)
        self.run_button.clicked.connect(self.start_report)
        status_layout.addWidget(self.run_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(status)

        latest = QFrame()
        latest.setObjectName("card")
        latest_layout = QVBoxLayout(latest)
        latest_layout.setContentsMargins(20, 16, 20, 16)
        latest_layout.addWidget(self._section("Latest report"))
        self.who = QLabel("No report yet")
        self.who.setObjectName("muted")
        latest_layout.addWidget(self.who)
        counts = QHBoxLayout()
        missing_box, self.missing_value = _count_box("Missing", "#c53030")
        late_box, self.late_value = _count_box("Late", "#c05621")
        counts.addWidget(missing_box)
        counts.addWidget(late_box)
        counts.addStretch(1)
        latest_layout.addLayout(counts)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Category", "Course", "Assignment", "Due"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(150)
        latest_layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.open_pdf = QPushButton("Open PDF")
        self.open_pdf.setObjectName("secondary")
        self.open_pdf.clicked.connect(self._open_pdf)
        self.open_folder = QPushButton("Open folder")
        self.open_folder.setObjectName("secondary")
        self.open_folder.clicked.connect(self._open_folder)
        buttons.addWidget(self.open_pdf)
        buttons.addWidget(self.open_folder)
        buttons.addStretch(1)
        latest_layout.addLayout(buttons)
        root.addWidget(latest, 1)

        root.addWidget(self._section("Recent reports"))
        self.history = QListWidget()
        self.history.setMaximumHeight(140)
        root.addWidget(self.history)
        version = QLabel(f"Version {APP_VERSION}")
        version.setObjectName("muted")
        root.addWidget(version)
        self.refresh()

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def show_banner(self, kind: str, text: str) -> None:
        self.banner.show_message(kind, text)

    def refresh(self) -> None:
        config = load_config()
        upcoming = next_occurrence(config.schedule_days, [config.morning, config.evening])
        if upcoming:
            self.next_value.setText("Next scheduled run: " + friendly_when(upcoming))
        elif config.schedule_days:
            self.next_value.setText("Next scheduled run: not scheduled")
        else:
            self.next_value.setText("Automatic runs are off.")
        rows = load_history()
        self.history.clear()
        if not rows:
            self.history.addItem("No reports yet.")
            self._show_empty()
            return
        for row in rows:
            when = _friendly_stamp(str(row.get("at") or ""))
            state = "Saved" if row.get("ok") else "Problem"
            self.history.addItem(
                f"{when}    {row.get('missing', 0)} missing, {row.get('late', 0)} late    {state}"
            )
        self._show_entry(rows[0])

    def _show_empty(self) -> None:
        self.last_value.setText("No report yet")
        self.result_value.setText("Choose Run report now. The summary will show up here.")
        self.who.setText("The latest PDF will be summarized here.")
        self.missing_value.setText("—")
        self.late_value.setText("—")
        self.table.setRowCount(0)
        self._pdf = ""
        self.open_pdf.setEnabled(False)
        self.open_folder.setEnabled(False)

    def _show_entry(self, row: dict) -> None:
        when = _friendly_stamp(str(row.get("at") or ""))
        self.last_value.setText(when or "Last report")
        message = str(row.get("message") or ("Report saved." if row.get("ok") else "The last run had a problem."))
        self.result_value.setText(message)
        student = row.get("student") or ""
        school = row.get("school") or ""
        who = " · ".join(part for part in (student, school) if part)
        self.who.setText(who or "Latest report")
        self.missing_value.setText(str(row.get("missing", 0)))
        self.late_value.setText(str(row.get("late", 0)))
        missing_color = "#2f855a" if str(row.get("missing", 0)) == "0" else "#c53030"
        self.missing_value.setStyleSheet(
            "font-size: 28px; font-weight: 650; "
            f"color: {missing_color}; background: transparent; border: none;"
        )
        preview = row.get("preview") or []
        self.table.setRowCount(len(preview))
        for index, item in enumerate(preview):
            for column, key in enumerate(("category", "course", "assignment", "due")):
                cell = QTableWidgetItem(str(item.get(key) or "—"))
                self.table.setItem(index, column, cell)
        self._pdf = str(row.get("pdf") or "")
        exists = bool(self._pdf) and Path(self._pdf).is_file()
        self.open_pdf.setEnabled(exists)
        folder = Path(self._pdf).parent if self._pdf else None
        self.open_folder.setEnabled(bool(folder and folder.is_dir()))

    def start_report(self) -> None:
        self.run_button.setEnabled(False)
        self.run_button.setText("Working…")
        self.banner.show_message("info", "Building the report. This can take a minute.")
        self._worker = FnWorker(execute_report, self)
        self._worker.succeeded.connect(self._finished)
        self._worker.failed.connect(self._failed)
        self._worker.start()

    def _finished(self, result: RunResult) -> None:
        self.run_button.setEnabled(True)
        self.run_button.setText("Run report now")
        self.refresh()
        if result.ok:
            self.banner.show_message(
                "success",
                f"Report ready: {result.missing} missing, {result.late} late.",
            )
        else:
            self.banner.show_message("error", result.message)

    def _failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.run_button.setText("Run report now")
        self.banner.show_message("error", message)

    def open_settings(self) -> None:
        from desktop.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        if dialog.exec():
            self.refresh()
            self.banner.show_message("success", "Settings saved.")

    def _open_pdf(self) -> None:
        if self._pdf:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._pdf))

    def _open_folder(self) -> None:
        if not self._pdf:
            return
        folder = str(Path(self._pdf).parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def _friendly_stamp(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    return friendly_when(moment)
