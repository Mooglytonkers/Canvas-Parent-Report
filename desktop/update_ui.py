"""Update banner, download progress, and the button on the main window."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from desktop.logging_setup import get_logger
from desktop.theme import style_primary
from desktop.updates import (
    MSG_LATER,
    MSG_NOT_WINDOWS,
    PreparedUpdate,
    UpdateCancelled,
    UpdateCheckResult,
    UpdateError,
    UpdateOffer,
    can_apply_update,
    check_for_update,
    download_and_verify,
    new_update_dir,
    automatic_check_enabled,
    release_page_url,
    start_installer,
    updates_suppressed,
)


def format_bytes(size: int) -> str:
    value = max(0, int(size))
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _plain(label: QLabel) -> QLabel:
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class UpdatePrompt(QFrame):
    """The card shown when a newer release exists."""

    update_clicked = Signal()
    later_clicked = Signal()
    notes_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("updateCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(
            "QFrame#updateCard {"
            " background: #e7f2f4;"
            " border: 1px solid #b7d4d8;"
            " border-radius: 12px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.heading = _plain(QLabel("An update is available"))
        self.heading.setStyleSheet(
            "font-size: 16px; font-weight: 650; color: #1b2838; background: transparent; border: none;"
        )
        self.message = _plain(QLabel())
        self.message.setStyleSheet("color: #1f4e56; background: transparent; border: none;")
        self.notes_label = _plain(QLabel("What's new"))
        self.notes_label.setStyleSheet(
            "font-weight: 650; color: #243140; background: transparent; border: none;"
        )
        self.notes = _plain(QLabel())
        self.notes.setStyleSheet("color: #243140; background: transparent; border: none;")

        layout.addWidget(self.heading)
        layout.addWidget(self.message)
        layout.addWidget(self.notes_label)
        layout.addWidget(self.notes)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.update_button = QPushButton("Update now")
        style_primary(self.update_button)
        self.update_button.setMinimumSize(140, 40)
        self.update_button.clicked.connect(self.update_clicked.emit)
        self.later_button = QPushButton("Later")
        self.later_button.setObjectName("secondary")
        self.later_button.setMinimumSize(100, 40)
        self.later_button.clicked.connect(self.later_clicked.emit)
        self.notes_button = QPushButton("View release notes")
        self.notes_button.setMinimumSize(180, 40)
        self.notes_button.setStyleSheet(
            "QPushButton {"
            " background: transparent; color: #1f6f78; border: none;"
            " padding: 8px 10px; font-weight: 650;"
            "}"
            "QPushButton:hover { color: #134e55; }"
        )
        self.notes_button.clicked.connect(self.notes_clicked.emit)
        buttons.addWidget(self.update_button)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.notes_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.hide()

    def show_offer(self, offer: UpdateOffer, *, can_install: bool) -> None:
        install = can_install and offer.can_download
        self.message.setText(_offer_copy(offer, install=install))
        if offer.notes.strip():
            self.notes.setText(offer.notes.strip())
            self.notes_label.show()
            self.notes.show()
        else:
            self.notes.clear()
            self.notes_label.hide()
            self.notes.hide()
        self.update_button.setText("Update now" if install else "Open releases page")
        self.show()


def _offer_copy(offer: UpdateOffer, *, install: bool) -> str:
    lead = f"Version {offer.latest} is available. You have {offer.current}."
    if install and offer.checksum_url:
        extra = "The download is checked against the published SHA-256 checksum before it is installed."
    elif install:
        extra = (
            "This release does not include a checksum file. "
            "The download still comes only from the official GitHub release."
        )
    else:
        extra = "This copy opens the releases page instead of running the Windows installer."
    return f"{lead} {extra}"


class UpdateDownloadDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("root")
        self.setWindowTitle("Update Canvas Parent Report")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.resize(520, 230)
        self._mode = "cancel"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        self.title = _plain(QLabel("Downloading the update"))
        self.title.setObjectName("headerName")
        self.detail = _plain(QLabel("Starting the download…"))
        self.detail.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.amount = QLabel("Waiting…")
        self.amount.setObjectName("muted")
        self.amount.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addWidget(self.bar)
        layout.addWidget(self.amount)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setMinimumSize(110, 40)
        self.cancel_button.clicked.connect(self._on_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def set_status(self, text: str) -> None:
        self.detail.setStyleSheet("")
        self.detail.setObjectName("muted")
        self.detail.setText(text)
        self.detail.style().unpolish(self.detail)
        self.detail.style().polish(self.detail)

    def set_progress(self, received: int, total: int) -> None:
        if total > 0:
            percent = min(100, int(received * 100 / total))
            self.bar.setRange(0, 100)
            self.bar.setValue(percent)
            self.amount.setText(f"{format_bytes(received)} of {format_bytes(total)} ({percent}%)")
            return
        self.bar.setRange(0, 0)
        self.amount.setText(f"{format_bytes(received)} downloaded")

    def show_error(self, message: str) -> None:
        self.title.setText("The update did not finish")
        self.detail.setText(message)
        self.detail.setStyleSheet("color: #9b2c2c; background: transparent;")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.amount.setText("")
        self._mode = "close"
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Close")

    def show_cancelled(self) -> None:
        self.title.setText("Download canceled")
        self.set_status("Nothing was installed.")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.amount.setText("")
        self._mode = "close"
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Close")

    def _on_button(self) -> None:
        if self._mode == "cancel":
            self._mode = "canceling"
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Canceling…")
            self.cancel_requested.emit()
            return
        if self._mode == "close":
            self.accept()

    def reject(self) -> None:
        if self._mode == "cancel":
            self._on_button()
            return
        if self._mode == "canceling":
            return
        super().reject()


class _CheckThread(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            result = check_for_update()
        except Exception:
            get_logger().exception("update check failed")
            result = UpdateCheckResult(status="error", current="", message=MSG_LATER)
        self.done.emit(result)


class _DownloadThread(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, offer: UpdateOffer, parent=None) -> None:
        super().__init__(parent)
        self._offer = offer
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            prepared = download_and_verify(
                self._offer,
                new_update_dir(),
                progress=lambda got, total: self.progress.emit(int(got), int(total or 0)),
                cancel_event=self._cancel,
                on_status=lambda text: self.status.emit(text),
            )
        except UpdateCancelled:
            self.cancelled.emit()
            return
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            get_logger().exception("update download failed")
            self.failed.emit(MSG_LATER)
            return
        self.succeeded.emit(prepared)


class UpdateController(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self._auto_started = False
        self._manual = False
        self._check: _CheckThread | None = None
        self._download: _DownloadThread | None = None
        self._dialog: UpdateDownloadDialog | None = None
        self._offer: UpdateOffer | None = None
        window.update_prompt.update_clicked.connect(self.apply_update)
        window.update_prompt.later_clicked.connect(self.dismiss)
        window.update_prompt.notes_clicked.connect(self.open_notes)

    def start_automatic_once(self) -> None:
        if self._auto_started:
            return
        self._auto_started = True
        if not automatic_check_enabled():
            return
        self._begin(manual=False)

    def start_manual(self) -> None:
        if updates_suppressed():
            return
        self._begin(manual=True)

    def shutdown(self) -> None:
        if self._download is not None:
            self._download.cancel()

    def present_offer(self, offer: UpdateOffer, *, can_install: bool | None = None) -> None:
        self._offer = offer
        install = can_apply_update() if can_install is None else can_install
        self.window.update_prompt.show_offer(offer, can_install=install)
        self._make_room_for_prompt()

    def _make_room_for_prompt(self) -> None:
        """Grow the window so the update card does not cover the report buttons."""
        window = self.window
        target = 980
        screen = window.screen()
        if screen is not None:
            available = screen.availableGeometry().height() - 32
            if available >= 700:
                target = min(target, available)
        if window.height() < target:
            window.resize(max(window.width(), 880), target)
        window.setMinimumHeight(max(640, min(target, window.height())))

    def apply_update(self) -> None:
        offer = self._offer
        if offer is None:
            return
        if not can_apply_update() or not offer.can_download:
            self.open_notes()
            return
        if self._download is not None and self._download.isRunning():
            if self._dialog is not None:
                self._dialog.show()
                self._dialog.raise_()
            return
        dialog = UpdateDownloadDialog(self.window)
        dialog.cancel_requested.connect(self._cancel_download)
        self._dialog = dialog
        thread = _DownloadThread(offer, self)
        thread.progress.connect(dialog.set_progress)
        thread.status.connect(dialog.set_status)
        thread.succeeded.connect(self._on_ready)
        thread.failed.connect(self._on_failed)
        thread.cancelled.connect(self._on_cancelled)
        self._download = thread
        dialog.show()
        thread.start()

    def dismiss(self) -> None:
        self.window.update_prompt.hide()
        self.window.setMinimumHeight(640)

    def open_notes(self) -> None:
        offer = self._offer
        target = release_page_url(offer.html_url if offer is not None else "")
        QDesktopServices.openUrl(QUrl(target))

    def _begin(self, *, manual: bool) -> None:
        if self._check is not None and self._check.isRunning():
            self._manual = self._manual or manual
            if manual:
                self._show_checking()
            return
        self._manual = manual
        if manual:
            self._show_checking()
        thread = _CheckThread(self)
        thread.done.connect(self._on_result)
        self._check = thread
        thread.start()

    def _show_checking(self) -> None:
        button = self.window.check_button
        button.setEnabled(False)
        button.setText("Checking…")
        self.window.banner.show_message("info", "Checking for updates…")

    def _restore_button(self) -> None:
        button = self.window.check_button
        button.setEnabled(True)
        button.setText("Check for updates")

    def _on_result(self, result: UpdateCheckResult) -> None:
        manual = self._manual
        self._manual = False
        self._restore_button()
        get_logger().info(
            "update check %s current=%s latest=%s",
            result.status,
            result.current,
            result.latest,
        )
        if result.status == "update_available" and result.offer is not None:
            if manual:
                self.window.banner.clear()
            self.present_offer(result.offer)
            return
        if not manual:
            return
        if result.status == "up_to_date":
            self.window.update_prompt.hide()
            self.window.banner.show_message("success", result.message)
            return
        self.window.banner.show_message("error", result.message or MSG_LATER)

    def _cancel_download(self) -> None:
        if self._download is not None:
            self._download.cancel()

    def _on_ready(self, prepared: PreparedUpdate) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        if prepared.verification == "verified":
            dialog.set_status(
                "Checksum matched. Canvas Parent Report will close and reopen when installation finishes."
            )
        else:
            dialog.set_status(
                "This release did not include a checksum file. The download came from the official GitHub release. "
                "Canvas Parent Report will close and reopen when installation finishes."
            )
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        try:
            start_installer(prepared.installer, app_executable=sys.executable)
        except UpdateError as exc:
            dialog.show_error(str(exc) or MSG_NOT_WINDOWS)
            return
        if app is not None:
            app.quit()

    def _on_failed(self, message: str) -> None:
        if self._dialog is not None:
            self._dialog.show_error(message or MSG_LATER)

    def _on_cancelled(self) -> None:
        if self._dialog is not None:
            self._dialog.show_cancelled()
