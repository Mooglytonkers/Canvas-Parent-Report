"""Background work so the window stays responsive."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from desktop.connection import friendly_error
from desktop.logging_setup import get_logger


class FnWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            get_logger().exception("background task failed")
            self.failed.emit(friendly_error(exc))
            return
        self.succeeded.emit(result)
