"""Calm light theme for the desktop app."""

from __future__ import annotations

STYLESHEET = """
QWidget#root, QDialog#root {
    background: #f3f6f8;
    color: #1b2838;
}
QLabel {
    color: #1b2838;
    background: transparent;
}
QLabel#title {
    font-size: 26px;
    font-weight: 650;
}
QLabel#headerName {
    font-size: 20px;
    font-weight: 650;
}
QLabel#muted, QLabel#hint {
    color: #5d6d7e;
}
QLabel#fieldLabel {
    font-weight: 600;
    color: #243140;
}
QLabel#stepLabel {
    color: #1f6f78;
    font-weight: 650;
}
QFrame#card {
    background: #ffffff;
    border: 1px solid #e4ebf2;
    border-radius: 16px;
}
QFrame#banner {
    border-radius: 10px;
}
QFrame#banner[kind="error"] {
    background: #fdeeee;
    border: 1px solid #f3c1c1;
}
QFrame#banner[kind="error"] QLabel { color: #9b2c2c; }
QFrame#banner[kind="success"] {
    background: #e8f6ef;
    border: 1px solid #b7e4c7;
}
QFrame#banner[kind="success"] QLabel { color: #1e7a46; }
QFrame#banner[kind="info"] {
    background: #e7f2f4;
    border: 1px solid #c5e0e4;
}
QFrame#banner[kind="info"] QLabel { color: #1f4e56; }
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
    background: #ffffff;
    border: 1px solid #d5dde6;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 22px;
    color: #1b2838;
    selection-background-color: #d5ecee;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {
    border: 1px solid #1f6f78;
}
QComboBox, QDateEdit, QTimeEdit {
    padding-right: 28px;
}
QComboBox::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow, QDateEdit::down-arrow, QTimeEdit::down-arrow {
    image: url(__CHEVRON__);
    width: 12px;
    height: 8px;
}
QPushButton#primary {
    background-color: #1f6f78;
    color: #ffffff;
    border: 1px solid #1f6f78;
    border-radius: 10px;
    padding: 10px 18px;
    min-height: 22px;
    font-weight: 650;
}
QPushButton#primary:hover {
    background-color: #185e66;
    color: #ffffff;
    border: 1px solid #185e66;
}
QPushButton#primary:pressed {
    background-color: #134e55;
    color: #ffffff;
    border: 1px solid #134e55;
}
QPushButton#primary:disabled {
    background-color: #d7e6e8;
    color: #3e5c61;
    border: 1px solid #d7e6e8;
}
QPushButton#secondary {
    background-color: #ffffff;
    color: #1b2838;
    border: 1px solid #cfd8e3;
    border-radius: 10px;
    padding: 10px 18px;
    min-height: 22px;
}
QPushButton#secondary:hover {
    background-color: #f4f7fa;
    color: #1b2838;
    border: 1px solid #cfd8e3;
}
QPushButton#secondary:disabled {
    background-color: #f4f7fa;
    color: #8aa0ad;
    border: 1px solid #e4ebf2;
}
QPushButton#link {
    background: transparent;
    color: #1f6f78;
    border: none;
    text-align: left;
    padding: 0px;
    font-weight: 650;
}
QPushButton#link:hover { color: #134e55; }
QToolButton#disclosure {
    background: transparent;
    color: #1f6f78;
    border: none;
    font-weight: 650;
    padding: 2px 0;
}
QFrame#helpBox {
    background: #f7fafc;
    border: 1px solid #e4ebf2;
    border-radius: 10px;
}
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #6d7c8a;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:hover {
    border: 1px solid #1f6f78;
    background: #f3fbfb;
}
QCheckBox::indicator:checked {
    border: 1px solid #1f6f78;
    background: #1f6f78;
    image: url(__CHECK__);
}
QCheckBox::indicator:checked:hover {
    border: 1px solid #185e66;
    background: #185e66;
    image: url(__CHECK__);
}
QCheckBox::indicator:disabled {
    border: 1px solid #d5dde6;
    background: #f4f7fa;
}
QCheckBox::indicator:checked:disabled {
    border: 1px solid #b7c5c8;
    background: #b7c5c8;
    image: url(__CHECK__);
}
QProgressBar {
    background: #e1e8ee;
    border: none;
    border-radius: 4px;
    max-height: 8px;
}
QProgressBar::chunk {
    background: #1f6f78;
    border-radius: 4px;
}
QScrollArea { background: transparent; border: none; }
QTableWidget {
    background: #ffffff;
    border: 1px solid #e4ebf2;
    border-radius: 12px;
    gridline-color: #eef2f6;
    selection-background-color: #e7f2f4;
    selection-color: #1b2838;
}
QHeaderView::section {
    background: #f7fafc;
    color: #5d6d7e;
    border: none;
    border-bottom: 1px solid #e4ebf2;
    padding: 8px 12px;
    font-weight: 650;
}
QTableWidget::item {
    padding: 8px 12px;
}
QListWidget {
    background: #ffffff;
    border: 1px solid #e4ebf2;
    border-radius: 12px;
    padding: 4px;
}
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:selected { background: #e7f2f4; color: #1b2838; }
QTabWidget::pane {
    border: 1px solid #e4ebf2;
    border-radius: 12px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #5d6d7e;
    padding: 8px 14px;
    margin-right: 4px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #1f6f78;
    font-weight: 650;
    border-bottom: 2px solid #1f6f78;
}
"""


PRIMARY_BUTTON = """
QPushButton {
    background-color: #1f6f78;
    color: #ffffff;
    border: 1px solid #1f6f78;
    border-radius: 10px;
    padding: 10px 18px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #185e66;
    color: #ffffff;
    border: 1px solid #185e66;
}
QPushButton:pressed {
    background-color: #134e55;
    color: #ffffff;
    border: 1px solid #134e55;
}
QPushButton:disabled {
    background-color: #d7e6e8;
    color: #3e5c61;
    border: 1px solid #d7e6e8;
}
"""


def style_primary(button) -> None:
    """Paint a filled button on the widget itself so a parent rule cannot wash it out."""
    button.setObjectName("primary")
    button.setFlat(False)
    button.setStyleSheet(PRIMARY_BUTTON)


def apply_theme(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from desktop.paths import resource_path

    if not isinstance(app, QApplication):
        return
    app.setStyle("Fusion")
    families = set(QFontDatabase.families())
    for name in ("Segoe UI", "Nunito Sans", "Liberation Sans", "DejaVu Sans"):
        if name in families:
            app.setFont(QFont(name, 11))
            break
    arrow = resource_path("chevron.png")
    check = resource_path("check.png")
    sheet = STYLESHEET
    if arrow.is_file():
        sheet = sheet.replace("__CHEVRON__", arrow.as_posix())
    if check.is_file():
        sheet = sheet.replace("__CHECK__", check.as_posix())
    app.setStyleSheet(sheet)
