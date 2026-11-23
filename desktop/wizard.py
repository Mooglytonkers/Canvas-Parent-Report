"""First-run setup: eight plain-language steps."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.forms import (
    AddressForm,
    Banner,
    DeliveryForm,
    HeaderForm,
    OptionsForm,
    ScheduleForm,
    TokenForm,
    hint,
)
from desktop.paths import resource_path, secret_storage_note
from desktop.printers import list_installed_printers
from desktop.schedule import friendly_when, install_schedule, launch_parts, next_occurrence
from desktop.secrets import get_smtp_password, get_token, set_smtp_password, set_token
from desktop.store import AppConfig, load_config, save_config
from desktop.version import APP_NAME

TITLES = (
    "Welcome",
    "School website",
    "Access token",
    "Names on the report",
    "Save, print, and email",
    "How the list is built",
    "When to run it",
    "You're set",
)
SUBTITLES = (
    "A short setup. No command line.",
    "Where you sign in to Canvas.",
    "The code Canvas gives you. It stays on this computer.",
    "What parents see at the top of the PDF.",
    "Choose a folder, and turn printing or email on only if you want them.",
    "Both of these can stay as they are.",
    "Weekday mornings and evenings are a good start.",
    "You can run a report now, or open the app and do it later.",
)


def _scroll(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea { background: #f3f6f8; border: none; }")
    scroll.viewport().setStyleSheet("background: #f3f6f8;")
    widget.setStyleSheet("background: #f3f6f8;")
    scroll.setWidget(widget)
    return scroll


class SetupWizard(QWidget):
    def __init__(self, controller=None) -> None:
        super().__init__()
        self.controller = controller
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(880, 640)
        self.resize(1000, 760)
        self._step = 0
        self._saved_token = bool(get_token())
        self._saved_password = bool(get_smtp_password())

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        name = QLabel(APP_NAME)
        name.setObjectName("headerName")
        self.step_label = QLabel("Step 1 of 8")
        self.step_label.setObjectName("stepLabel")
        header.addWidget(name)
        header.addStretch(1)
        header.addWidget(self.step_label)
        root.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setRange(0, 7)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        root.addWidget(self.progress)

        self.title = QLabel(TITLES[0])
        self.title.setObjectName("title")
        self.subtitle = QLabel(SUBTITLES[0])
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        self.page_banner = Banner()
        root.addWidget(self.page_banner)

        self.address = AddressForm()
        self.token = TokenForm(self.address.value)
        self.header_form = HeaderForm()
        self.delivery = DeliveryForm()
        self.options = OptionsForm()
        self.schedule = ScheduleForm()
        self.done = QWidget()
        done_layout = QVBoxLayout(self.done)
        done_layout.setContentsMargins(0, 0, 0, 0)
        self.done_summary = QLabel()
        self.done_summary.setWordWrap(True)
        self.done_summary.setTextFormat(Qt.TextFormat.RichText)
        done_layout.addWidget(self.done_summary)
        done_layout.addWidget(hint(secret_storage_note()))
        done_layout.addStretch(1)

        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setContentsMargins(0, 4, 0, 0)
        welcome_layout.setSpacing(12)
        for text in (
            "This app signs in to your school's Canvas site and makes a one-page report of missing and late assignments.",
            "You can save the PDF, and if you want, email it or print it.",
            "You can also have it run on school mornings and evenings by itself.",
            "You will need the school's Canvas website and an access token. The next screens show you where to find both.",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            welcome_layout.addWidget(label)
        welcome_layout.addStretch(1)

        self.stack = QStackedWidget()
        for page in (
            welcome,
            self.address,
            self.token,
            self.header_form,
            self.delivery,
            self.options,
            self.schedule,
            self.done,
        ):
            self.stack.addWidget(_scroll(page))
        root.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("secondary")
        self.back_button.clicked.connect(self.back)
        self.next_button = QPushButton("Get started")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self.next)
        self.next_button.setDefault(True)
        self.run_button = QPushButton("Run a report now")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(lambda: self._finish(run_now=True))
        self.run_button.hide()
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        footer.addWidget(self.run_button)
        footer.addWidget(self.next_button)
        root.addLayout(footer)
        self._show_step(0)
        icon = resource_path("icon.png")
        if icon.is_file():
            from PySide6.QtGui import QIcon

            self.setWindowIcon(QIcon(str(icon)))

    def set_step(self, index: int) -> None:
        self._show_step(index)

    def apply_preview(self, printers: list[str] | None = None) -> None:
        """Fill fictional example values for screenshots. Does not contact Canvas."""
        self.address.set_value("https://yourschool.instructure.com")
        self.token.set_value("example-token")
        self.token.expand_help(True)
        self.token.banner.show_message(
            "success",
            "Connected as Alex Sample. This account follows more than one student. "
            "Choose which student the report is for.",
        )
        self.token.set_observees([("1001", "Alex Sample"), ("1002", "Jamie Sample")], "1001")
        self.header_form.student.setText("Alex Sample")
        self.header_form.school.setText("Example High School")
        self.delivery.folder.setText(r"C:\Users\Example\Documents\Canvas Parent Report")
        self.delivery.print_on.setChecked(True)
        self.delivery.set_printers(printers or ["Home Printer"], "Home Printer")
        self.delivery.email_on.setChecked(True)
        self.delivery.provider.setCurrentText("Gmail")
        self.delivery.email_to.setText("parent@example.com")
        self.delivery.email_from.setText("parent@example.com")
        self.delivery.smtp_username.setText("parent@example.com")
        self._show_step(0)

    def _show_step(self, index: int) -> None:
        self._step = index
        self.stack.setCurrentIndex(index)
        self.progress.setValue(index)
        self.step_label.setText(f"Step {index + 1} of 8")
        self.title.setText(TITLES[index])
        self.subtitle.setText(SUBTITLES[index])
        self.page_banner.clear()
        self.back_button.setEnabled(index > 0)
        last = index == 7
        self.run_button.setVisible(last)
        self.next_button.setText("Open the app" if last else ("Get started" if index == 0 else "Next"))
        if index == 4 and self.delivery.printers.count() <= 1:
            self.delivery.set_printers(list_installed_printers())
        if last:
            self.done_summary.setText(self._summary_html())

    def back(self) -> None:
        if self._step > 0:
            self._show_step(self._step - 1)

    def next(self) -> None:
        problem = self._validate_current()
        if problem:
            self.page_banner.show_message("error", problem)
            return
        if self._step >= 7:
            self._finish(run_now=False)
            return
        self._show_step(self._step + 1)

    def _validate_current(self) -> str | None:
        if self._step == 1:
            return self.address.validate()
        if self._step == 2:
            return self.token.validate(require_token=not self._saved_token)
        if self._step == 3:
            return self.header_form.validate()
        if self._step == 4:
            return self.delivery.validate()
        return None

    def collect(self) -> AppConfig:
        config = load_config()
        config.base_url = self.address.value()
        config.student_user_id = self.token.chosen_student_id()
        self.header_form.apply(config)
        self.delivery.apply(config)
        self.options.apply(config)
        self.schedule.apply(config)
        config.setup_complete = True
        return config

    def _summary_html(self) -> str:
        config = self.collect()
        config.setup_complete = False
        print_line = "Printing is off."
        if config.print_enabled:
            name = config.printer_name or "the default printer"
            copies = "1 copy" if config.print_copies == 1 else f"{config.print_copies} copies"
            print_line = f"Printing is on ({copies} to {name})."
        email_line = "Email is off."
        if config.email_enabled:
            email_line = f"Email is on, to {config.email_to}."
        upcoming = next_occurrence(config.schedule_days, [config.morning, config.evening])
        when = friendly_when(upcoming) if upcoming else "Not scheduled"
        days = ", ".join(day.title() for day in config.schedule_days) or "no days"
        return (
            f"<p>Reports will be saved in <b>{config.save_folder()}</b>.</p>"
            f"<p>{print_line}</p>"
            f"<p>{email_line}</p>"
            f"<p>Schedule: {days}. Next run: {when}.</p>"
            "<p>Choose <b>Run a report now</b> to try it, or open the app and come back when you are ready.</p>"
        )

    def _finish(self, *, run_now: bool) -> None:
        for step in (1, 2, 3, 4):
            self._step = step
            problem = self._validate_current()
            if problem:
                self._show_step(step)
                self.page_banner.show_message("error", problem)
                return
        config = self.collect()
        try:
            config.save_folder().mkdir(parents=True, exist_ok=True)
        except OSError:
            self._show_step(4)
            self.page_banner.show_message("error", "That save folder could not be created. Choose another folder.")
            return
        save_config(config)
        if self.token.value():
            set_token(self.token.value())
        if self.delivery.password():
            set_smtp_password(self.delivery.password())
        command, arguments = launch_parts()
        ok, schedule_message = install_schedule(config, command=command, arguments=arguments)
        banner = "" if ok else schedule_message
        if self.controller is not None:
            self.controller.show_main(banner=banner, run_now=run_now)
        self.close()
