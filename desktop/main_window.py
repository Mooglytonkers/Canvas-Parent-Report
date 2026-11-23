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
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.forms import Banner
from desktop.paths import resource_path
from desktop.runner import RunResult, execute_report
from desktop.schedule import friendly_when, next_occurrence, schedule_plan
from desktop.store import load_config, load_history
from desktop.theme import style_primary
from desktop.update_ui import UpdateController, UpdatePrompt
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
        self.check_button = QPushButton("Check for updates")
        self.check_button.setObjectName("secondary")
        self.check_button.setMinimumSize(176, 40)
        self.check_button.setToolTip("Look for a newer version of this app")
        self.check_button.clicked.connect(self.check_for_updates)
        header.addWidget(self.check_button)
        settings = QPushButton("Settings")
        settings.setObjectName("secondary")
        settings.setMinimumHeight(40)
        settings.clicked.connect(self.open_settings)
        header.addWidget(settings)
        root.addLayout(header)

        self.update_prompt = UpdatePrompt()
        root.addWidget(self.update_prompt)

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
        style_primary(self.run_button)
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
        counts.setSpacing(12)
        missing_box, self.missing_value = _count_box("Missing", "#c53030")
        late_box, self.late_value = _count_box("Late", "#c05621")
        message_box, self.message_value = _count_box("Teacher messages", "#2b6cb0")
        for box in (missing_box, late_box, message_box):
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            counts.addWidget(box, 1)
        latest_layout.addLayout(counts)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Category", "Course", "Assignment", "Due", "Score"])
        self._prepare_table(self.table, stretch=2, right_columns={3, 4})
        self.table.setMinimumHeight(168)
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
        self.history_empty = QLabel("No reports yet. Run a report and each one will be listed here.")
        self.history_empty.setObjectName("muted")
        self.history_empty.setWordWrap(True)
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(["When", "Missing", "Late", "Messages", "Result"])
        self._prepare_table(self.history, stretch=0, right_columns=set())
        history_header = self.history.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 110), (2, 90), (3, 130), (4, 110)):
            history_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.history.setColumnWidth(column, width)
        self.history.setMaximumHeight(168)
        root.addWidget(self.history_empty)
        root.addWidget(self.history)
        version = QLabel(f"Version {APP_VERSION}")
        version.setObjectName("muted")
        root.addWidget(version)
        self._updates = UpdateController(self)
        self.refresh()

    def _prepare_table(self, table: QTableWidget, *, stretch: int, right_columns: set[int]) -> None:
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setWordWrap(False)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column == stretch
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(column, mode)
            item = table.horizontalHeaderItem(column)
            if item is None:
                continue
            align = (
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                if column in right_columns
                else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            item.setTextAlignment(align)

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._updates.start_automatic_once()

    def closeEvent(self, event) -> None:
        self._updates.shutdown()
        super().closeEvent(event)

    def check_for_updates(self) -> None:
        self._updates.start_manual()

    def show_banner(self, kind: str, text: str) -> None:
        self.banner.show_message(kind, text)

    def refresh(self) -> None:
        config = load_config()
        days, times = schedule_plan(config)
        upcoming = next_occurrence(days, times)
        if upcoming:
            self.next_value.setText("Next scheduled run: " + friendly_when(upcoming))
        elif days:
            self.next_value.setText("Next scheduled run: not scheduled")
        else:
            self.next_value.setText("Automatic runs are off.")
        rows = load_history()
        if not rows:
            self.history.setRowCount(0)
            self.history.hide()
            self.history_empty.show()
            self._show_empty()
            return
        self.history_empty.hide()
        self.history.show()
        self.history.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [
                _friendly_stamp(str(row.get("at") or "")) or "—",
                str(row.get("missing", 0)),
                str(row.get("late", 0)),
                str(row.get("messages", 0)),
                "Saved" if row.get("ok") else "Problem",
            ]
            for column, text in enumerate(values):
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.history.setItem(index, column, cell)
        self._show_entry(rows[0])

    def _show_empty(self) -> None:
        self.last_value.setText("No report yet")
        self.result_value.setText("Choose Run report now. The summary will show up here.")
        self.who.setText("The latest PDF will be summarized here.")
        self.missing_value.setText("—")
        self.late_value.setText("—")
        self.message_value.setText("—")
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
        self.message_value.setText(str(row.get("messages", 0)))
        missing_color = "#2f855a" if str(row.get("missing", 0)) == "0" else "#c53030"
        self.missing_value.setStyleSheet(
            "font-size: 28px; font-weight: 650; "
            f"color: {missing_color}; background: transparent; border: none;"
        )
        preview = row.get("preview") or []
        self.table.setRowCount(len(preview))
        keys = ("category", "course", "assignment", "due", "score")
        for index, item in enumerate(preview):
            for column, key in enumerate(keys):
                raw = item.get(key)
                if key == "due":
                    text = friendly_due(raw)
                elif key == "score":
                    text = "—" if raw is None or raw == "" else str(raw)
                else:
                    text = str(raw) if raw else "—"
                cell = QTableWidgetItem(text)
                align = (
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    if column >= 3
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                cell.setTextAlignment(align)
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


def friendly_due(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        moment = datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return text
    return f"{moment.strftime('%b')} {moment.day}"


def _friendly_stamp(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    return friendly_when(moment)
