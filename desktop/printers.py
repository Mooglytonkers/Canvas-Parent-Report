"""List printers installed on this computer."""

from __future__ import annotations

import subprocess
import sys


def list_installed_printers() -> list[str]:
    try:
        if sys.platform == "win32":
            return _windows_printers()
        return _lpstat_printers()
    except (OSError, subprocess.TimeoutExpired):
        return []


def _windows_printers() -> list[str]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance -ClassName Win32_Printer | Select-Object -ExpandProperty Name",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return _names(completed.stdout)


def _lpstat_printers() -> list[str]:
    completed = subprocess.run(
        ["lpstat", "-p"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    names: list[str] = []
    for line in (completed.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "printer":
            names.append(parts[1])
    return names


def _names(text: str) -> list[str]:
    found: list[str] = []
    for line in (text or "").splitlines():
        name = line.strip()
        if name and name.lower() != "name":
            found.append(name)
    return found
