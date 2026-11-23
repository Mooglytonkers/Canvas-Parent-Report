"""Edit the same choices as the setup wizard."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.forms import AddressForm, Banner, DeliveryForm, HeaderForm, OptionsForm, ScheduleForm, TokenForm
from desktop.printers import list_installed_printers
from desktop.schedule import install_schedule, launch_parts
from desktop.secrets import get_smtp_password, get_token, set_smtp_password, set_token
from desktop.store import AppConfig, load_config, save_config
from desktop.theme import style_primary


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("root")
        self.setWindowTitle("Settings")
        self.setMinimumSize(720, 560)
        self.resize(780, 640)
        self.config = load_config()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        intro = QLabel("These are the same choices as the first-time setup. Secrets stay out of the settings file.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)
        self.banner = Banner()
        layout.addWidget(self.banner)

        self.address = AddressForm()
        self.token = TokenForm(self.address.value)
        self.header = HeaderForm()
        self.delivery = DeliveryForm()
        self.options = OptionsForm()
        self.schedule = ScheduleForm()

        self.address.set_value(self.config.base_url)
        self.token.set_keep_placeholder(bool(get_token()))
        if self.config.student_user_id:
            self.token.set_observees(
                [(self.config.student_user_id, "Saved student")],
                self.config.student_user_id,
            )
        self.header.load(self.config)
        self.delivery.load(self.config, password_saved=bool(get_smtp_password()))
        self.delivery.set_printers(list_installed_printers(), self.config.printer_name)
        self.options.load(self.config)
        self.schedule.load(self.config)

        tabs = QTabWidget()
        tabs.addTab(self._page(self.address, self.token), "School")
        tabs.addTab(self._page(self.header), "Report")
        tabs.addTab(self._page(self.delivery), "Delivery")
        options_note = QLabel("The defaults work for most families.")
        options_note.setObjectName("muted")
        options_note.setWordWrap(True)
        tabs.addTab(self._page(options_note, self.options), "Options")
        tabs.addTab(self._page(self.schedule), "Schedule")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save is not None:
            style_primary(save)
        layout.addWidget(buttons)

    def _page(self, *widgets: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        for widget in widgets:
            layout.addWidget(widget)
        return page

    def _save(self) -> None:
        for check in (
            self.address.validate(),
            self.token.validate(require_token=not get_token()),
            self.header.validate(),
            self.delivery.validate(),
        ):
            if check:
                self.banner.show_message("error", check)
                return
        config = AppConfig()
        config.base_url = self.address.value()
        config.student_user_id = self.token.chosen_student_id() or self.config.student_user_id
        self.header.apply(config)
        self.delivery.apply(config)
        self.options.apply(config)
        self.schedule.apply(config)
        config.setup_complete = True
        try:
            config.save_folder().mkdir(parents=True, exist_ok=True)
            save_config(config)
        except OSError:
            self.banner.show_message("error", "Those settings could not be saved. Check the save folder and try again.")
            return
        if self.token.value():
            set_token(self.token.value())
        if self.delivery.password():
            set_smtp_password(self.delivery.password())
        command, arguments = launch_parts()
        ok, message = install_schedule(config, command=command, arguments=arguments)
        if not ok:
            self.banner.show_message("error", message)
            return
        self.accept()
