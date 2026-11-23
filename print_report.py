#!/usr/bin/env python3
"""Print a Canvas report PDF. Off unless printing is enabled.

Windows tries SumatraPDF, then Adobe Acrobat or Reader, then the default
print action. macOS and Linux use the lp command. One job is sent at a
time. A failure is reported and does not raise.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which as shutil_which
from typing import Callable, Mapping, Sequence

# A tiny PDF used by --test-print. It does not contain personal information.
MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 55>>stream
BT /F1 18 Tf 72 720 Td (Canvas report test page) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
%%EOF
"""

STARTFILE = "os.startfile"
QUEUE_WAIT_SECONDS = 1.0


@dataclass
class PrintResult:
    ok: bool
    message: str
    commands: list[list[str]] = field(default_factory=list)


def _is_windows(platform_name: str) -> bool:
    return platform_name.lower().startswith("win")


def _default_run(cmd: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), check=False, timeout=timeout)


def _default_startfile(path: str, operation: str) -> None:
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("os.startfile is only available on Windows")
    startfile(path, operation)


def _find_on_path(which: Callable[[str], str | None], names: Sequence[str]) -> str | None:
    for name in names:
        found = which(name)
        if found:
            return found
    return None


def _find_sumatra(
    which: Callable[[str], str | None],
    exists: Callable[[Path], bool],
    env: Mapping[str, str],
) -> str | None:
    found = _find_on_path(which, ("SumatraPDF", "SumatraPDF.exe"))
    if found:
        return found
    for key in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = (env.get(key) or "").strip()
        if not root:
            continue
        candidate = Path(root) / "SumatraPDF" / "SumatraPDF.exe"
        if exists(candidate):
            return str(candidate)
    return None


def _find_adobe(
    which: Callable[[str], str | None],
    exists: Callable[[Path], bool],
    env: Mapping[str, str],
) -> str | None:
    found = _find_on_path(which, ("AcroRd32", "AcroRd32.exe", "Acrobat", "Acrobat.exe"))
    if found:
        return found
    relative = (
        Path("Adobe") / "Acrobat DC" / "Acrobat" / "Acrobat.exe",
        Path("Adobe") / "Acrobat Reader DC" / "Reader" / "AcroRd32.exe",
        Path("Adobe") / "Acrobat Reader DC" / "Reader" / "AcroRd64.exe",
    )
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = (env.get(key) or "").strip()
        if not root:
            continue
        for rel in relative:
            candidate = Path(root) / rel
            if exists(candidate):
                return str(candidate)
    return None


def _sumatra_command(executable: str, pdf: Path, printer_name: str, copies: int) -> list[str]:
    command = [executable]
    if printer_name:
        command.extend(["-print-to", printer_name])
    else:
        command.append("-print-to-default")
    command.extend(["-print-settings", f"{copies}x", "-silent", "-exit-when-done", str(pdf)])
    return command


def _adobe_commands(executable: str, pdf: Path, printer_name: str, copies: int) -> list[list[str]]:
    # Adobe's /t switch prints one copy to a named printer and often stays open.
    # Submit one copy at a time so jobs queue in order.
    return [[executable, "/t", str(pdf), printer_name] for _ in range(copies)]


def _startfile_commands(pdf: Path, copies: int) -> list[list[str]]:
    return [[STARTFILE, str(pdf), "print"] for _ in range(copies)]


def _lp_command(lp: str, pdf: Path, printer_name: str, copies: int) -> list[str]:
    command = [lp, "-n", str(copies)]
    if printer_name:
        command.extend(["-d", printer_name])
    command.append(str(pdf))
    return command


def plan_print(
    pdf_path: Path,
    *,
    printer_name: str = "",
    copies: int = 1,
    print_command: str = "",
    platform_name: str | None = None,
    which: Callable[[str], str | None] | None = None,
    exists: Callable[[Path], bool] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[list[str]], str | None]:
    """Return (commands, error). error is set when no command can be built."""
    system = platform_name or sys.platform
    lookup = which or shutil_which
    file_exists = exists or (lambda path: path.is_file())
    env = environ if environ is not None else os.environ
    printer = (printer_name or "").strip()
    count = copies if copies >= 1 else 1
    custom = (print_command or "").strip()
    if custom:
        return [_custom_command(custom, pdf_path, system)], None

    if _is_windows(system):
        sumatra = _find_sumatra(lookup, file_exists, env)
        if sumatra:
            return [_sumatra_command(sumatra, pdf_path, printer, count)], None
        adobe = _find_adobe(lookup, file_exists, env)
        if adobe and printer:
            return _adobe_commands(adobe, pdf_path, printer, count), None
        if not printer:
            return _startfile_commands(pdf_path, count), None
        return [], (
            "Could not find SumatraPDF or Adobe Acrobat/Reader, so the named "
            f"printer {printer!r} was not used. Install SumatraPDF for reliable "
            "silent printing, or leave the printer name blank to use the Windows "
            "default printer."
        )

    lp = lookup("lp")
    if not lp:
        return [], (
            "The lp command was not found. macOS includes it. On Linux, install "
            "CUPS and try again."
        )
    return [_lp_command(lp, pdf_path, printer, count)], None


def _custom_command(command: str, pdf_path: Path, platform_name: str) -> list[str]:
    path = str(pdf_path)
    text = command.strip()
    if text.lower() in ("default", "system", "yes", "true"):
        if _is_windows(platform_name):
            return [STARTFILE, path, "print"]
        return ["lp", path]
    posix = not _is_windows(platform_name)
    if "{pdf}" in text:
        parts = shlex.split(text, posix=posix)
        return [path if part == "{pdf}" else part.replace("{pdf}", path) for part in parts]
    return shlex.split(text, posix=posix) + [path]


def _destination(printer_name: str) -> str:
    name = (printer_name or "").strip()
    if name:
        return f"printer {name}"
    return "the default printer"


def _wait(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def print_pdf(
    pdf_path: Path,
    *,
    printer_name: str = "",
    copies: int = 1,
    print_command: str = "",
    platform_name: str | None = None,
    which: Callable[[str], str | None] | None = None,
    exists: Callable[[Path], bool] | None = None,
    environ: Mapping[str, str] | None = None,
    run: Callable[[Sequence[str], float], subprocess.CompletedProcess] | None = None,
    startfile: Callable[[str, str], None] | None = None,
    wait_seconds: float = QUEUE_WAIT_SECONDS,
    timeout: float = 60,
    dry_run: bool = False,
) -> PrintResult:
    """Print one PDF. Never raises for a missing printer or a failed command."""
    path = Path(pdf_path)
    if copies < 1:
        return PrintResult(False, "PRINT_COPIES must be at least 1.")
    if not path.is_file():
        return PrintResult(False, f"PDF not found: {path}")

    try:
        commands, error = plan_print(
            path,
            printer_name=printer_name,
            copies=copies,
            print_command=print_command,
            platform_name=platform_name,
            which=which,
            exists=exists,
            environ=environ,
        )
    except (OSError, ValueError) as exc:
        return PrintResult(False, f"Could not prepare the print job ({exc}).")
    if error:
        return PrintResult(False, error, commands)
    if not commands:
        return PrintResult(False, "No print command was available.")

    destination = _destination(printer_name)
    copy_word = "copy" if copies == 1 else "copies"
    preview = " ; ".join(" ".join(cmd) for cmd in commands)
    if dry_run:
        return PrintResult(
            True,
            f"Dry run: would send {copies} {copy_word} to {destination}. {preview}",
            commands,
        )

    runner = run or _default_run
    launch = startfile or _default_startfile
    for index, command in enumerate(commands):
        try:
            if command and command[0] == STARTFILE:
                launch(command[1], command[2] if len(command) > 2 else "print")
            else:
                completed = runner(command, timeout)
                code = getattr(completed, "returncode", 1)
                if code not in (0, None):
                    return PrintResult(
                        False,
                        f"The print command exited with code {code}.",
                        commands,
                    )
        except subprocess.TimeoutExpired:
            # GUI helpers such as Adobe Reader often stay open after queueing.
            pass
        except OSError as exc:
            return PrintResult(False, f"Could not print ({exc}).", commands)
        except Exception as exc:
            return PrintResult(False, f"Could not print ({exc}).", commands)
        # Wait so the next copy, if any, is submitted only after this one is queued.
        if index < len(commands) - 1 or wait_seconds:
            _wait(wait_seconds)

    return PrintResult(
        True,
        f"Sent {copies} {copy_word} to {destination}.",
        commands,
    )


def test_print(
    *,
    output_dir: Path,
    printer_name: str = "",
    copies: int = 1,
    print_command: str = "",
    **kwargs,
) -> PrintResult:
    """Print a one-page test PDF. Does not contact Canvas."""
    folder = Path(output_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        pdf = folder / "print-test.pdf"
        pdf.write_bytes(MINIMAL_PDF)
    except OSError as exc:
        return PrintResult(False, f"Could not write a test page ({exc}).")
    result = print_pdf(
        pdf,
        printer_name=printer_name,
        copies=copies,
        print_command=print_command,
        **kwargs,
    )
    result.message = f"Test page: {result.message}"
    return result
