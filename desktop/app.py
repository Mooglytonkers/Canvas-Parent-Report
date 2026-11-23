"""Start the desktop window, or the first-run wizard."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.paths import resource_path
from desktop.store import load_config
from desktop.theme import apply_theme
from desktop.updates import hold_window_mutex
from desktop.version import APP_NAME
from desktop.wizard import SetupWizard


class Controller:
    def __init__(self) -> None:
        self.wizard: SetupWizard | None = None
        self.main: MainWindow | None = None

    def start(self) -> None:
        if load_config().setup_complete:
            self.show_main()
            return
        self.wizard = SetupWizard(self)
        self.wizard.show()

    def show_main(self, banner: str = "", run_now: bool = False) -> None:
        self.main = MainWindow()
        self.main.show()
        if banner:
            self.main.show_banner("error", banner)
        if run_now:
            self.main.start_report()


def launch() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Cooper Street Press")
    apply_theme(app)
    icon = resource_path("icon.png")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    controller = Controller()
    app._update_mutex = hold_window_mutex()
    controller.start()
    app._controller = controller  # keep the windows alive
    return app.exec()
