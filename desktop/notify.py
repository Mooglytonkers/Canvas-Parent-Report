"""Optional Windows notification after a scheduled report."""

from __future__ import annotations

import subprocess
import sys

from desktop.logging_setup import get_logger


def report_ready_text(missing: int, late: int) -> str:
    return f"Report ready: {missing} missing, {late} late"


def notify_report_ready(missing: int, late: int) -> None:
    """Show a short Windows balloon. Failures are logged and do not stop the run."""
    message = report_ready_text(missing, late)
    log = get_logger()
    log.info(message)
    if sys.platform != "win32":
        return
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(8000, 'Canvas Parent Report', $env:CPR_TOAST, 'Info'); "
        "Start-Sleep -Seconds 8; "
        "$n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            env={**dict(**__import__("os").environ), "CPR_TOAST": message},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError) as exc:
        log.info("Notification was not shown (%s).", exc.__class__.__name__)
