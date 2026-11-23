"""Log details to a file. The window never shows a stack trace."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from desktop.paths import log_dir

_READY = False


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:
            return True
        for key in ("CANVAS_TOKEN", "SMTP_PASSWORD"):
            secret = os.environ.get(key) or ""
            if secret and secret in text:
                text = text.replace(secret, "********")
        record.msg = text
        record.args = ()
        return True


def setup_logging() -> None:
    global _READY
    if _READY:
        return
    path = log_dir() / "app.log"
    handler = RotatingFileHandler(path, maxBytes=400_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    handler.addFilter(_RedactFilter())
    root = logging.getLogger("canvasparent")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False
    _READY = True


def get_logger() -> logging.Logger:
    setup_logging()
    return logging.getLogger("canvasparent")
