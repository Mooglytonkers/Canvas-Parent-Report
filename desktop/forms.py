"""Setup sections shared by the first-run wizard and Settings."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt, QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop.connection import settings_page_url, test_connection, validate_base_url
from desktop.paths import default_save_dir, secret_storage_note
from desktop.store import AppConfig, default_start_date

TIMEZONES = (
    ("Eastern", "America/New_York"),
    ("Central", "America/Chicago"),
    ("Mountain", "America/Denver"),
    ("Arizona", "America/Phoenix"),
    ("Pacific", "America/Los_Angeles"),
)

EMAIL_PRESETS = {
    "Gmail": ("smtp.gmail.com", 587, "true"),
    "Outlook": ("smtp.office365.com", 587, "true"),
    "Other": ("", 587, "true"),
}

GMAIL_HELP = "https://support.google.com/accounts/answer/185833"
DAYS = (
    ("mon", "Mon"),
    ("tue", "Tue"),
    ("wed", "Wed"),
    ("thu", "Thu"),
    ("fri", "Fri"),
    ("sat", "Sat"),
    ("sun", "Sun"),
)


class Banner(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self._label = QLabel()
        self._label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(self._label)
        self.hide()

    def show_message(self, kind: str, text: str) -> None:
        self.setProperty("kind", kind)
        self._label.setText(text)
        self.show()
        self.style().unpolish(self)
        self.style().polish(self)

    def clear(self) -> None:
        self.hide()
        self._label.clear()


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def _vbox(parent: QWidget) -> QVBoxLayout:
    parent.setObjectName("form")
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    return layout


class AddressForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = _vbox(self)
        layout.addWidget(
            hint(
                "This is the address in the browser when you are signed in to Canvas. "
                "It often ends in instructure.com."
            )
        )
        layout.addWidget(field_label("School Canvas address"))
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://yourschool.instructure.com")
        self.url.setClearButtonEnabled(True)
        layout.addWidget(self.url)
        layout.addWidget(hint("Example: https://yourschool.instructure.com"))
        layout.addStretch(1)

    def value(self) -> str:
        return self.url.text().strip().rstrip("/")

    def set_value(self, url: str) -> None:
        self.url.setText(url)

    def validate(self) -> str | None:
        return validate_base_url(self.value())


class TokenForm(QWidget):
    def __init__(self, url_provider, parent=None) -> None:
        super().__init__(parent)
        self._url_provider = url_provider
        self._worker = None
        self.auto_student_id = ""
        layout = _vbox(self)
        layout.addWidget(
            hint(
                "A token is a code from Canvas that lets this app read the report. "
                "Treat it like a password. "
                + secret_storage_note()
            )
        )
        layout.addWidget(field_label("Access token"))
        row = QHBoxLayout()
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Paste the token from Canvas")
        self.show_token = QCheckBox("Show")
        self.show_token.toggled.connect(self._toggle_echo)
        row.addWidget(self.token, 1)
        row.addWidget(self.show_token)
        layout.addLayout(row)

        self.help_toggle = QToolButton()
        self.help_toggle.setObjectName("disclosure")
        self.help_toggle.setText("How do I get this?")
        self.help_toggle.setCheckable(True)
        self.help_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.help_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.help_toggle.toggled.connect(self._toggle_help)
        layout.addWidget(self.help_toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        self.help_box = QFrame()
        self.help_box.setObjectName("helpBox")
        help_layout = QVBoxLayout(self.help_box)
        help_layout.setContentsMargins(12, 10, 12, 10)
        help_text = QLabel(
            "1. Sign in to your school's Canvas site in a browser.\n"
            "2. Open Account (your picture), then Settings.\n"
            "3. Under Approved Integrations, choose + New Access Token.\n"
            "4. Name it Canvas Parent Report, then choose Generate Token.\n"
            "5. Copy the token and paste it here. Canvas shows the full code only once.\n\n"
            "If you do not see New Access Token, the school may have turned that off. "
            "Ask the school's technology office whether a parent token is allowed."
        )
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        self.help_box.hide()
        layout.addWidget(self.help_box)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Open Canvas settings")
        self.open_button.setObjectName("secondary")
        self.open_button.clicked.connect(self.open_settings)
        self.test_button = QPushButton("Test connection")
        self.test_button.setObjectName("primary")
        self.test_button.clicked.connect(self.test)
        actions.addWidget(self.open_button)
        actions.addWidget(self.test_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.banner = Banner()
        layout.addWidget(self.banner)

        self.student_wrap = QWidget()
        student_layout = QVBoxLayout(self.student_wrap)
        student_layout.setContentsMargins(0, 0, 0, 0)
        student_layout.addWidget(field_label("Which student?"))
        self.students = QComboBox()
        student_layout.addWidget(self.students)
        student_layout.addWidget(hint("This login follows more than one student. Pick the one for the report."))
        self.student_wrap.hide()
        layout.addWidget(self.student_wrap)
        layout.addStretch(1)

    def _toggle_echo(self, show: bool) -> None:
        self.token.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )

    def _toggle_help(self, open_: bool) -> None:
        self.help_toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )
        self.help_box.setVisible(open_)

    def expand_help(self, open_: bool = True) -> None:
        self.help_toggle.setChecked(open_)

    def value(self) -> str:
        return self.token.text().strip()

    def set_value(self, token: str) -> None:
        self.token.setText(token)

    def set_keep_placeholder(self, keep: bool) -> None:
        if keep:
            self.token.setPlaceholderText("Leave blank to keep the saved token")

    def chosen_student_id(self) -> str:
        if self.student_wrap.isVisible():
            return str(self.students.currentData() or "")
        return self.auto_student_id

    def set_observees(self, rows: list[tuple[str, str]], select_id: str = "") -> None:
        self.students.clear()
        self.auto_student_id = ""
        if len(rows) > 1:
            for student_id, name in rows:
                self.students.addItem(name, student_id)
            if select_id:
                index = self.students.findData(select_id)
                if index >= 0:
                    self.students.setCurrentIndex(index)
            self.student_wrap.show()
        elif len(rows) == 1:
            self.auto_student_id = rows[0][0]
            self.student_wrap.hide()
        else:
            self.student_wrap.hide()

    def validate(self, *, require_token: bool) -> str | None:
        if require_token and not self.value():
            return "Paste the access token from Canvas."
        if self.student_wrap.isVisible() and not self.chosen_student_id():
            return "Choose which student this report is for."
        return None

    def open_settings(self) -> None:
        problem = validate_base_url(self._url_provider())
        if problem:
            self.banner.show_message("error", problem)
            return
        QDesktopServices.openUrl(QUrl(settings_page_url(self._url_provider())))

    def test(self) -> None:
        from desktop.workers import FnWorker

        token = self.value()
        self.banner.show_message("info", "Checking with Canvas…")
        self.test_button.setEnabled(False)
        self.test_button.setText("Checking…")

        def work():
            return test_connection(self._url_provider(), token)

        self._worker = FnWorker(work, self)
        self._worker.succeeded.connect(self._tested)
        self._worker.failed.connect(self._test_failed)
        self._worker.start()

    def _tested(self, result) -> None:
        self.test_button.setEnabled(True)
        self.test_button.setText("Test connection")
        self.banner.show_message("success" if result.ok else "error", result.message)
        if result.ok:
            self.set_observees(result.observees)

    def _test_failed(self, message: str) -> None:
        self.test_button.setEnabled(True)
        self.test_button.setText("Test connection")
        self.banner.show_message("error", message)


class HeaderForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = _vbox(self)
        layout.addWidget(
            hint("These names appear at the top of the PDF. The date is the earliest due date to include.")
        )
        layout.addWidget(field_label("Student name"))
        self.student = QLineEdit()
        self.student.setPlaceholderText("Alex Sample")
        layout.addWidget(self.student)
        layout.addWidget(field_label("School name"))
        self.school = QLineEdit()
        self.school.setPlaceholderText("Example High School")
        layout.addWidget(self.school)
        layout.addWidget(field_label("Include work due on or after"))
        self.start = QDateEdit()
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("MMM d, yyyy")
        start = default_start_date()
        self.start.setDate(QDate(start.year, start.month, start.day))
        layout.addWidget(self.start)
        layout.addWidget(field_label("Time zone"))
        self.timezone = QComboBox()
        for label, zone in TIMEZONES:
            self.timezone.addItem(label, zone)
        layout.addWidget(self.timezone)
        layout.addWidget(hint("Used for due dates and the time printed on the report."))
        layout.addStretch(1)

    def apply(self, config: AppConfig) -> None:
        config.student_name = self.student.text().strip()
        config.school_name = self.school.text().strip()
        config.start_date = self.start.date().toString("yyyy-MM-dd")
        config.timezone = str(self.timezone.currentData() or "America/New_York")

    def load(self, config: AppConfig) -> None:
        self.student.setText(config.student_name)
        self.school.setText(config.school_name)
        if config.start_date:
            parts = config.start_date.split("-")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                self.start.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
        index = self.timezone.findData(config.timezone)
        if index >= 0:
            self.timezone.setCurrentIndex(index)

    def validate(self) -> str | None:
        if not self.student.text().strip():
            return "Enter the student's name as you want it on the report."
        if not self.school.text().strip():
            return "Enter the school name as you want it on the report."
        return None


class DeliveryForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = None
        layout = _vbox(self)
        layout.addWidget(field_label("Save reports in"))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setText(str(default_save_dir()))
        browse = QPushButton("Browse")
        browse.setObjectName("secondary")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        layout.addWidget(field_label("Print"))
        self.print_on = QCheckBox("Print the PDF after each report")
        self.print_on.toggled.connect(self._toggle_print)
        layout.addWidget(self.print_on)
        print_row = QHBoxLayout()
        self.printers = QComboBox()
        self.printers.addItem("System default", "")
        self.copies = QSpinBox()
        self.copies.setRange(1, 20)
        self.copies.setValue(1)
        print_row.addWidget(self.printers, 1)
        print_row.addWidget(QLabel("Copies"))
        print_row.addWidget(self.copies)
        layout.addLayout(print_row)
        layout.addWidget(
            hint("For the most reliable silent printing on Windows, install SumatraPDF. The app uses it when it is installed.")
        )

        layout.addWidget(field_label("Email"))
        self.email_on = QCheckBox("Email the PDF after each report")
        self.email_on.toggled.connect(self._toggle_email)
        layout.addWidget(self.email_on)
        layout.addWidget(field_label("Email provider"))
        self.provider = QComboBox()
        self.provider.addItems(["Gmail", "Outlook", "Other"])
        self.provider.currentTextChanged.connect(self._preset)
        layout.addWidget(self.provider)
        self.guidance = hint("")
        self.guidance_link = QPushButton("How to create a Gmail App Password")
        self.guidance_link.setObjectName("link")
        self.guidance_link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GMAIL_HELP))
        )
        layout.addWidget(self.guidance)
        layout.addWidget(self.guidance_link, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(field_label("Send to"))
        self.email_to = QLineEdit()
        self.email_to.setPlaceholderText("parent@example.com, other@example.com")
        layout.addWidget(self.email_to)
        layout.addWidget(field_label("From"))
        self.email_from = QLineEdit()
        self.email_from.setPlaceholderText("you@example.com")
        layout.addWidget(self.email_from)
        host_row = QHBoxLayout()
        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("smtp.gmail.com")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(587)
        host_row.addWidget(self.smtp_host, 1)
        host_row.addWidget(QLabel("Port"))
        host_row.addWidget(self.smtp_port)
        layout.addLayout(host_row)
        self.tls = QCheckBox("Use a secure connection (recommended)")
        self.tls.setChecked(True)
        layout.addWidget(self.tls)
        layout.addWidget(field_label("Mailbox username"))
        self.smtp_username = QLineEdit()
        self.smtp_username.setPlaceholderText("Usually the same as the From address")
        layout.addWidget(self.smtp_username)
        layout.addWidget(field_label("Mailbox password"))
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_password.setPlaceholderText("App password, not your normal mailbox password")
        layout.addWidget(self.smtp_password)
        layout.addWidget(hint(secret_storage_note()))
        self.test_email = QPushButton("Send test email")
        self.test_email.setObjectName("secondary")
        self.test_email.clicked.connect(self.send_test)
        layout.addWidget(self.test_email, alignment=Qt.AlignmentFlag.AlignLeft)
        self.banner = Banner()
        layout.addWidget(self.banner)
        layout.addStretch(1)
        self._preset("Gmail")
        self._toggle_print(False)
        self._toggle_email(False)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder for reports", self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def _toggle_print(self, on: bool) -> None:
        self.printers.setEnabled(on)
        self.copies.setEnabled(on)

    def _toggle_email(self, on: bool) -> None:
        for widget in (
            self.provider,
            self.email_to,
            self.email_from,
            self.smtp_host,
            self.smtp_port,
            self.tls,
            self.smtp_username,
            self.smtp_password,
            self.test_email,
            self.guidance_link,
        ):
            widget.setEnabled(on)
        self.guidance.setEnabled(True)

    def _preset(self, name: str) -> None:
        host, port, tls = EMAIL_PRESETS.get(name, EMAIL_PRESETS["Other"])
        if name != "Other":
            self.smtp_host.setText(host)
            self.smtp_port.setValue(port)
            self.tls.setChecked(tls == "true")
        if name == "Gmail":
            self.guidance.setText(
                "Gmail will not accept your normal password. Turn on 2-Step Verification, "
                "then create an App Password and paste that here."
            )
            self.guidance_link.setText("How to create a Gmail App Password")
            self.guidance_link.show()
        elif name == "Outlook":
            self.guidance.setText(
                "Use smtp.office365.com on port 587. Some school Microsoft 365 accounts "
                "have mail sending turned off by an administrator."
            )
            self.guidance_link.hide()
        else:
            self.guidance.setText("Enter the outgoing mail server from your email provider.")
            self.guidance_link.hide()

    def set_printers(self, names: list[str], selected: str = "") -> None:
        current = selected or str(self.printers.currentData() or "")
        self.printers.clear()
        self.printers.addItem("System default", "")
        for name in names:
            if name:
                self.printers.addItem(name, name)
        index = self.printers.findData(current)
        if index >= 0:
            self.printers.setCurrentIndex(index)

    def apply(self, config: AppConfig) -> None:
        config.output_dir = self.folder.text().strip()
        config.print_enabled = self.print_on.isChecked()
        config.printer_name = str(self.printers.currentData() or "")
        config.print_copies = int(self.copies.value())
        config.email_enabled = self.email_on.isChecked()
        config.email_to = self.email_to.text().strip()
        config.email_from = self.email_from.text().strip()
        config.smtp_host = self.smtp_host.text().strip()
        config.smtp_port = int(self.smtp_port.value())
        config.smtp_use_tls = "true" if self.tls.isChecked() else "false"
        config.smtp_username = self.smtp_username.text().strip()

    def password(self) -> str:
        return self.smtp_password.text()

    def load(self, config: AppConfig, *, password_saved: bool = False) -> None:
        if config.output_dir:
            self.folder.setText(config.output_dir)
        self.print_on.setChecked(config.print_enabled)
        self.copies.setValue(config.print_copies or 1)
        self.set_printers([config.printer_name] if config.printer_name else [], config.printer_name)
        self.email_on.setChecked(config.email_enabled)
        self.email_to.setText(config.email_to)
        self.email_from.setText(config.email_from)
        self.smtp_host.setText(config.smtp_host)
        self.smtp_port.setValue(config.smtp_port or 587)
        self.tls.setChecked(str(config.smtp_use_tls).lower() not in ("false", "0", "no", "plain"))
        self.smtp_username.setText(config.smtp_username)
        host = (config.smtp_host or "").lower()
        if "gmail" in host:
            self.provider.setCurrentText("Gmail")
        elif "office365" in host or "outlook" in host:
            self.provider.setCurrentText("Outlook")
        elif host:
            self.provider.setCurrentText("Other")
        if password_saved:
            self.smtp_password.setPlaceholderText("Leave blank to keep the saved password")
        self._toggle_print(config.print_enabled)
        self._toggle_email(config.email_enabled)

    def validate(self) -> str | None:
        if not self.folder.text().strip():
            return "Choose a folder where the PDF should be saved."
        if not self.email_on.isChecked():
            return None
        if "@" not in self.email_to.text():
            return "Enter the email address that should receive the report. Separate extra addresses with commas."
        if "@" not in self.email_from.text():
            return "Enter the From address for the email."
        if not self.smtp_host.text().strip():
            return "Enter the outgoing mail server, or choose Gmail or Outlook."
        return None

    def send_test(self) -> None:
        from desktop.workers import FnWorker

        problem = self.validate()
        if problem:
            self.banner.show_message("error", problem)
            return
        self.banner.show_message("info", "Sending a test message…")
        self.test_email.setEnabled(False)
        config = AppConfig(student_name="Test", school_name="")
        self.apply(config)
        password = self.password()

        def work():
            import os

            from desktop.secrets import get_smtp_password
            from email_report import send_test_email

            os.environ["SMTP_PASSWORD"] = password or get_smtp_password()
            settings = config.to_settings()
            if not settings.student_name:
                settings.student_name = "Test"
            return send_test_email(settings, timeout=20)

        self._worker = FnWorker(work, self)
        self._worker.succeeded.connect(self._tested)
        self._worker.failed.connect(self._failed)
        self._worker.start()

    def _tested(self, result) -> None:
        self.test_email.setEnabled(self.email_on.isChecked())
        self.banner.show_message("success" if result.ok else "error", result.message)

    def _failed(self, message: str) -> None:
        self.test_email.setEnabled(self.email_on.isChecked())
        self.banner.show_message("error", message)


class OptionsForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = _vbox(self)
        self.graded = QCheckBox("Treat graded work as turned in")
        self.graded.setChecked(True)
        layout.addWidget(self.graded)
        layout.addWidget(
            hint("If an assignment already has a grade, it is left off the missing list. Late work can still show.")
        )
        self.todos = QCheckBox("Mark graded To Do items done")
        self.todos.setChecked(False)
        layout.addWidget(self.todos)
        layout.addWidget(
            hint(
                "After each report, check off graded items on the student's Canvas To Do list. "
                "This does not submit work or change grades. Leave this off until you have looked at a report. "
                "It only works with the student's own token, not a parent token."
            )
        )
        layout.addStretch(1)

    def apply(self, config: AppConfig) -> None:
        config.graded_counts_as_submitted = self.graded.isChecked()
        config.mark_graded_todos_done = self.todos.isChecked()

    def load(self, config: AppConfig) -> None:
        self.graded.setChecked(config.graded_counts_as_submitted)
        self.todos.setChecked(config.mark_graded_todos_done)


class ScheduleForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = _vbox(self)
        layout.addWidget(
            hint(
                "The computer needs to be on and signed in to Windows at these times. "
                "You can change this later in Settings."
            )
        )
        layout.addWidget(field_label("Days"))
        day_row = QHBoxLayout()
        self.days: dict[str, QCheckBox] = {}
        for key, label in DAYS:
            box = QCheckBox(label)
            box.setChecked(key not in ("sat", "sun"))
            self.days[key] = box
            day_row.addWidget(box)
        layout.addLayout(day_row)
        times = QHBoxLayout()
        morning_col = QVBoxLayout()
        morning_col.addWidget(field_label("Morning"))
        self.morning = QTimeEdit()
        self.morning.setDisplayFormat("h:mm AP")
        self.morning.setTime(QTime(6, 45))
        morning_col.addWidget(self.morning)
        evening_col = QVBoxLayout()
        evening_col.addWidget(field_label("Evening"))
        self.evening = QTimeEdit()
        self.evening.setDisplayFormat("h:mm AP")
        self.evening.setTime(QTime(18, 45))
        evening_col.addWidget(self.evening)
        times.addLayout(morning_col)
        times.addLayout(evening_col)
        times.addStretch(1)
        layout.addLayout(times)
        self.missed = QCheckBox("If the computer was off or asleep, run the report after I sign in")
        self.missed.setChecked(True)
        layout.addWidget(self.missed)
        layout.addWidget(
            hint("This catches a missed morning or evening run the next time Windows is available. It does not run on every sign-in.")
        )
        layout.addStretch(1)

    def selected_days(self) -> list[str]:
        return [key for key, box in self.days.items() if box.isChecked()]

    def apply(self, config: AppConfig) -> None:
        config.schedule_days = self.selected_days()
        config.morning = self.morning.time().toString("HH:mm")
        config.evening = self.evening.time().toString("HH:mm")
        config.run_missed_at_signin = self.missed.isChecked()

    def load(self, config: AppConfig) -> None:
        chosen = set(config.schedule_days)
        for key, box in self.days.items():
            box.setChecked(key in chosen)
        self._set_time(self.morning, config.morning or "06:45")
        self._set_time(self.evening, config.evening or "18:45")
        self.missed.setChecked(config.run_missed_at_signin)

    def _set_time(self, widget: QTimeEdit, text: str) -> None:
        hour_text, _, minute_text = text.partition(":")
        if hour_text.isdigit() and minute_text.isdigit():
            widget.setTime(QTime(int(hour_text), int(minute_text)))
