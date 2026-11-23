#!/usr/bin/env python3
"""Mock the Linux and Windows print commands. lp does not need to exist."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from print_report import STARTFILE, print_pdf, test_print

PDF_BYTES = b"%PDF-1.4\n%print-test\n%%EOF\n"


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class PrintReportTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.write(PDF_BYTES)
        handle.close()
        self.pdf = Path(handle.name)
        self.addCleanup(lambda: self.pdf.unlink(missing_ok=True))

    def test_linux_default_and_named_printer(self) -> None:
        calls: list[list[str]] = []

        def which(name: str) -> str | None:
            return "/usr/bin/lp" if name == "lp" else None

        def run(cmd, timeout):
            calls.append(list(cmd))
            return _Completed(0)

        default = print_pdf(
            self.pdf,
            copies=1,
            platform_name="linux",
            which=which,
            run=run,
            wait_seconds=0,
        )
        self.assertTrue(default.ok, default.message)
        self.assertEqual(calls[0], ["/usr/bin/lp", "-n", "1", str(self.pdf)])
        self.assertIn("default printer", default.message)

        named = print_pdf(
            self.pdf,
            printer_name="Office",
            copies=2,
            platform_name="linux",
            which=which,
            run=run,
            wait_seconds=0,
        )
        self.assertTrue(named.ok, named.message)
        self.assertEqual(
            calls[1],
            ["/usr/bin/lp", "-n", "2", "-d", "Office", str(self.pdf)],
        )
        self.assertIn("Office", named.message)

    def test_linux_missing_lp_does_not_raise(self) -> None:
        def which(name: str) -> None:
            return None

        def run(cmd, timeout):
            raise AssertionError("lp should not be executed when it is missing")

        result = print_pdf(
            self.pdf,
            platform_name="linux",
            which=which,
            run=run,
            wait_seconds=0,
        )
        self.assertFalse(result.ok)
        self.assertIn("lp", result.message)

    def test_dry_run_does_not_execute(self) -> None:
        def which(name: str) -> str | None:
            return "/usr/bin/lp" if name == "lp" else None

        def run(cmd, timeout):
            raise AssertionError("dry run should not execute")

        result = print_pdf(
            self.pdf,
            printer_name="Office",
            copies=1,
            platform_name="darwin",
            which=which,
            run=run,
            dry_run=True,
            wait_seconds=0,
        )
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.commands[0][0], "/usr/bin/lp")
        self.assertIn("-d", result.commands[0])
        self.assertIn("Dry run", result.message)

    def test_windows_sumatra_then_adobe_then_startfile(self) -> None:
        calls: list[list[str]] = []
        launches: list[tuple[str, str]] = []

        def run(cmd, timeout):
            calls.append(list(cmd))
            return _Completed(0)

        def startfile(path: str, operation: str) -> None:
            launches.append((path, operation))

        sumatra = print_pdf(
            self.pdf,
            printer_name="Lab Printer",
            copies=2,
            platform_name="win32",
            which=lambda name: None,
            exists=lambda path: path.name == "SumatraPDF.exe",
            environ={"LOCALAPPDATA": "C:/Users/Example/AppData/Local"},
            run=run,
            startfile=startfile,
            wait_seconds=0,
        )
        self.assertTrue(sumatra.ok, sumatra.message)
        self.assertEqual(len(calls), 1)
        command = calls[0]
        self.assertTrue(command[0].endswith("SumatraPDF.exe"))
        self.assertIn("-print-to", command)
        self.assertIn("Lab Printer", command)
        self.assertIn("-silent", command)
        self.assertIn("-print-settings", command)
        self.assertIn("2x", command)
        self.assertEqual(launches, [])

        calls.clear()
        adobe = print_pdf(
            self.pdf,
            printer_name="Lab Printer",
            copies=3,
            platform_name="win32",
            which=lambda name: None,
            exists=lambda path: path.name == "AcroRd32.exe",
            environ={"PROGRAMFILES": "C:/Program Files"},
            run=run,
            startfile=startfile,
            wait_seconds=0,
        )
        self.assertTrue(adobe.ok, adobe.message)
        self.assertEqual(len(calls), 3)
        for command in calls:
            self.assertEqual(command[1], "/t")
            self.assertEqual(command[3], "Lab Printer")
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(launches, [])

        calls.clear()
        default = print_pdf(
            self.pdf,
            copies=2,
            platform_name="win32",
            which=lambda name: None,
            exists=lambda path: False,
            environ={},
            run=run,
            startfile=startfile,
            wait_seconds=0,
        )
        self.assertTrue(default.ok, default.message)
        self.assertEqual(calls, [])
        self.assertEqual(launches, [(str(self.pdf), "print"), (str(self.pdf), "print")])
        self.assertEqual(default.commands[0][0], STARTFILE)

    def test_windows_named_printer_without_helper_fails(self) -> None:
        result = print_pdf(
            self.pdf,
            printer_name="Lab Printer",
            platform_name="win32",
            which=lambda name: None,
            exists=lambda path: False,
            environ={},
            run=lambda cmd, timeout: (_ for _ in ()).throw(AssertionError("should not run")),
            wait_seconds=0,
        )
        self.assertFalse(result.ok)
        self.assertIn("SumatraPDF", result.message)

    def test_command_failure_is_reported(self) -> None:
        result = print_pdf(
            self.pdf,
            platform_name="linux",
            which=lambda name: "/usr/bin/lp" if name == "lp" else None,
            run=lambda cmd, timeout: _Completed(2),
            wait_seconds=0,
        )
        self.assertFalse(result.ok)
        self.assertIn("code 2", result.message)

    def test_timeout_is_treated_as_queued(self) -> None:
        def run(cmd, timeout):
            raise subprocess.TimeoutExpired(cmd, timeout)

        result = print_pdf(
            self.pdf,
            platform_name="linux",
            which=lambda name: "/usr/bin/lp" if name == "lp" else None,
            run=run,
            wait_seconds=0,
        )
        self.assertTrue(result.ok, result.message)

    def test_custom_command_substitutes_path_only(self) -> None:
        calls: list[list[str]] = []

        def run(cmd, timeout):
            calls.append(list(cmd))
            return _Completed(0)

        result = print_pdf(
            self.pdf,
            print_command="lp -d Office {pdf}",
            platform_name="linux",
            run=run,
            wait_seconds=0,
        )
        self.assertTrue(result.ok, result.message)
        self.assertEqual(calls[0], ["lp", "-d", "Office", str(self.pdf)])

    def test_test_print_uses_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            calls: list[list[str]] = []

            def run(cmd, timeout):
                calls.append(list(cmd))
                return _Completed(0)

            result = test_print(
                output_dir=Path(folder),
                platform_name="linux",
                which=lambda name: "/usr/bin/lp" if name == "lp" else None,
                run=run,
                wait_seconds=0,
            )
            self.assertTrue(result.ok, result.message)
            self.assertTrue((Path(folder) / "print-test.pdf").is_file())
            self.assertEqual(calls[0][-1], str(Path(folder) / "print-test.pdf"))


if __name__ == "__main__":
    unittest.main()
