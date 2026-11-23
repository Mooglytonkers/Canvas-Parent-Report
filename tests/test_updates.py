#!/usr/bin/env python3
"""Update checks, checksum verification, and headless skip."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CPR_SKIP_UPDATE_CHECK", "1")

from desktop import __version__ as package_version
from desktop.updates import (
    CHECK_TIMEOUT_SECONDS,
    MSG_CHECKSUM_MISSING_NAME,
    MSG_LATER,
    MSG_LIMIT,
    MSG_MISMATCH,
    MSG_OFFLINE,
    MSG_REDIRECT,
    MSG_UNTRUSTED,
    RELEASES_API,
    RELEASES_PAGE,
    PreparedUpdate,
    TrustedRedirectHandler,
    UpdateCancelled,
    UpdateCheckResult,
    UpdateError,
    UpdateOffer,
    Version,
    automatic_check_enabled,
    build_apply_script,
    check_for_update,
    choose_published_release,
    compare_versions,
    download_and_verify,
    download_file,
    expected_sha256,
    hold_window_mutex,
    interpret_releases,
    is_newer,
    is_release_notes_url,
    is_trusted_release_url,
    notes_excerpt,
    parse_version,
    release_page_url,
    select_checksum_asset,
    select_installer_asset,
    start_installer,
    updates_suppressed,
    verify_installer,
)
from desktop.updates import ReleaseAsset
from desktop.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
SETUP = "CanvasParentReport-Setup-2.3.0.exe"
SETUP_URL = (
    "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/"
    "v2.3.0/CanvasParentReport-Setup-2.3.0.exe"
)
SUMS_URL = (
    "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/"
    "v2.3.0/SHA256SUMS.txt"
)


def _asset(name: str, url: str, size: int = 10) -> dict:
    return {"name": name, "browser_download_url": url, "size": size}


def _release(tag: str, *, draft: bool = False, prerelease: bool = False, body: str = "", assets: list | None = None, html: str = "") -> dict:
    version = tag[1:] if tag[:1] in "vV" else tag
    if assets is None:
        assets = [
            _asset(
                f"CanvasParentReport-Setup-{version}.exe",
                f"https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/{tag}/CanvasParentReport-Setup-{version}.exe",
                2048,
            ),
            _asset(
                "SHA256SUMS.txt",
                f"https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/{tag}/SHA256SUMS.txt",
                90,
            ),
        ]
    return {
        "tag_name": tag,
        "name": f"Canvas Parent Report {version}",
        "draft": draft,
        "prerelease": prerelease,
        "body": body,
        "html_url": html or f"https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/tag/{tag}",
        "assets": assets,
    }


class FakeResponse:
    def __init__(self, data: bytes, url: str, headers: dict | None = None) -> None:
        self._data = data
        self._pos = 0
        self._url = url
        self.headers = {"Content-Length": str(len(data))}
        if headers:
            self.headers.update(headers)

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            amount = len(self._data) - self._pos
        chunk = self._data[self._pos : self._pos + amount]
        self._pos += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args) -> bool:
        return False


class FakeOpener:
    def __init__(self, payload, url: str = RELEASES_API, error: BaseException | None = None, finals: dict | None = None) -> None:
        self.payload = payload
        self.url = url
        self.error = error
        self.finals = finals or {}
        self.timeout = None
        self.requests = []

    def open(self, request, timeout=None):
        self.timeout = timeout
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        target = request.full_url
        mapped = (
            isinstance(self.payload, dict)
            and bool(self.payload)
            and all(isinstance(value, (bytes, bytearray)) for value in self.payload.values())
        )
        if mapped:
            data = self.payload[target]
            final = self.finals.get(target, target)
        elif isinstance(self.payload, bytes):
            data = self.payload
            final = self.finals.get(target, self.url)
        else:
            data = json.dumps(self.payload).encode()
            final = self.url
        return FakeResponse(data, final)


class VersionTests(unittest.TestCase):
    def test_parses_optional_v_and_ignores_build_metadata(self) -> None:
        self.assertEqual(parse_version("v2.2.0"), Version(2, 2, 0))
        self.assertEqual(parse_version("V2.2.0"), Version(2, 2, 0))
        self.assertEqual(parse_version("2.2.0"), Version(2, 2, 0))
        self.assertEqual(parse_version("2.2.0+build.5"), Version(2, 2, 0))
        self.assertEqual(parse_version("v2.2.0-beta.1").prerelease, "beta.1")

    def test_numeric_comparison_not_text_order(self) -> None:
        self.assertGreater(compare_versions(parse_version("v2.10.0"), parse_version("v2.9.0")), 0)
        self.assertGreater(compare_versions(parse_version("2.2.0"), parse_version("2.1.9")), 0)
        self.assertEqual(compare_versions(parse_version("v2.2.0"), parse_version("2.2.0")), 0)
        self.assertFalse(is_newer("2.2.0", "v2.2.0"))
        self.assertTrue(is_newer("v2.3.0", "2.2.0"))
        self.assertFalse(is_newer("v2.2.0-beta", "2.2.0"))
        self.assertTrue(is_newer("2.2.0", "v2.2.0-beta"))

    def test_rejects_non_semver(self) -> None:
        with self.assertRaises(UpdateError):
            parse_version("latest")
        with self.assertRaises(UpdateError):
            parse_version("2.2")


class ReleaseParsingTests(unittest.TestCase):
    def test_skips_drafts_prereleases_and_odd_tags(self) -> None:
        releases = [
            _release("v9.0.0", draft=True),
            _release("v8.0.0", prerelease=True),
            _release("v2.3.0-beta"),
            _release("nightly"),
            _release("v2.0.0"),
            _release("v2.1.0"),
        ]
        chosen = choose_published_release(releases)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["tag_name"], "v2.1.0")

    def test_update_available_uses_latest_published(self) -> None:
        result = interpret_releases(
            [_release("v2.1.0"), _release("v2.3.0", body="Hello [notes](https://example.com)")],
            current="2.2.0",
        )
        self.assertEqual(result.status, "update_available")
        self.assertEqual(result.latest, "2.3.0")
        self.assertEqual(result.current, "2.2.0")
        self.assertIn("2.3.0", result.message)
        self.assertIn("2.2.0", result.message)
        offer = result.offer
        self.assertIsNotNone(offer)
        self.assertEqual(offer.installer_name, SETUP)
        self.assertEqual(offer.checksum_name, "SHA256SUMS.txt")
        self.assertIn("Hello notes", offer.notes)
        self.assertNotIn("https://example.com", offer.notes)
        self.assertTrue(offer.can_download)

    def test_same_and_newer_local_versions_are_current(self) -> None:
        same = interpret_releases([_release("v2.2.0")], current="2.2.0")
        self.assertEqual(same.status, "up_to_date")
        self.assertIn("2.2.0", same.message)
        ahead = interpret_releases([_release("v2.1.0")], current="2.2.0")
        self.assertEqual(ahead.status, "up_to_date")
        empty = interpret_releases([], current="2.2.0")
        self.assertEqual(empty.status, "up_to_date")

    def test_installer_asset_selection(self) -> None:
        assets = [
            ReleaseAsset("source.zip", "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/v2.3.0/source.zip"),
            ReleaseAsset("CanvasParentReport-Setup-old.exe", SETUP_URL.replace("2.3.0", "old")),
            ReleaseAsset(SETUP, SETUP_URL, 50),
            ReleaseAsset("notes.txt", "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/v2.3.0/notes.txt"),
        ]
        chosen = select_installer_asset(assets, "2.3.0")
        self.assertEqual(chosen.name, SETUP)
        sums = select_checksum_asset(
            [
                ReleaseAsset("CanvasParentReport-Setup-2.3.0.exe.sha256", SUMS_URL),
                ReleaseAsset("SHA256SUMS.txt", SUMS_URL),
            ]
        )
        self.assertEqual(sums.name, "SHA256SUMS.txt")
        self.assertIsNone(select_installer_asset([], "2.3.0"))
        self.assertIsNone(select_checksum_asset([]))

    def test_untrusted_asset_urls_are_not_downloadable(self) -> None:
        bad_setup = _release(
            "v2.3.0",
            assets=[
                _asset(SETUP, "https://evil.example/CanvasParentReport-Setup-2.3.0.exe"),
                _asset("SHA256SUMS.txt", SUMS_URL),
            ],
        )
        offer = interpret_releases([bad_setup], current="2.2.0").offer
        self.assertFalse(offer.can_download)
        self.assertEqual(offer.installer_url, "")
        bad_sum = _release(
            "v2.3.0",
            assets=[
                _asset(SETUP, SETUP_URL),
                _asset("SHA256SUMS.txt", "http://github.com/Mooglytonkers/Canvas-Parent-Report/SHA256SUMS.txt"),
            ],
        )
        rejected = interpret_releases([bad_sum], current="2.2.0").offer
        self.assertTrue(rejected.checksum_rejected)
        self.assertFalse(rejected.can_download)

    def test_notes_excerpt_truncates(self) -> None:
        text = notes_excerpt("word " * 200, limit=40)
        self.assertLessEqual(len(text), 40)
        self.assertTrue(text.endswith("…"))


class UrlTrustTests(unittest.TestCase):
    def test_accepts_this_repo_and_github_asset_hosts(self) -> None:
        self.assertTrue(is_trusted_release_url(SETUP_URL))
        self.assertTrue(is_trusted_release_url("https://objects.githubusercontent.com/github-production-release-asset/abc"))
        self.assertTrue(is_trusted_release_url("https://release-assets.githubusercontent.com/abc?token=1"))
        self.assertTrue(is_release_notes_url("https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/tag/v2.3.0"))

    def test_rejects_http_other_hosts_and_credentials(self) -> None:
        self.assertFalse(is_trusted_release_url(SETUP_URL.replace("https://", "http://")))
        self.assertFalse(is_trusted_release_url("https://user:pass@github.com/Mooglytonkers/Canvas-Parent-Report/releases/download/v2.3.0/x.exe"))
        self.assertFalse(is_trusted_release_url("https://github.com.evil.example/Mooglytonkers/Canvas-Parent-Report/releases/download/v2.3.0/x.exe"))
        self.assertFalse(is_trusted_release_url("https://evil.github.com/releases/download/v2.3.0/x.exe"))
        self.assertFalse(is_trusted_release_url("https://github.com/other/repo/releases/download/v2.3.0/CanvasParentReport-Setup-2.3.0.exe"))
        self.assertFalse(is_trusted_release_url("https://github.com/Mooglytonkers/Canvas-Parent-Report/archive/v2.3.0.zip"))
        self.assertFalse(is_trusted_release_url("https://example.com/setup.exe"))
        self.assertFalse(is_trusted_release_url("javascript:alert(1)"))
        self.assertEqual(release_page_url("https://evil.example/phish"), RELEASES_PAGE)
        self.assertEqual(
            release_page_url("https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/tag/v2.3.0"),
            "https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/tag/v2.3.0",
        )

    def test_redirect_handler_blocks_untrusted_hosts(self) -> None:
        handler = TrustedRedirectHandler()
        request = urllib.request.Request(SETUP_URL)
        allowed = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://release-assets.githubusercontent.com/download/setup.exe",
        )
        self.assertIsNotNone(allowed)
        with self.assertRaises(UpdateError) as caught:
            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/setup.exe")
        self.assertEqual(str(caught.exception), MSG_REDIRECT)


class ChecksumTests(unittest.TestCase):
    def test_parses_common_checksum_layouts(self) -> None:
        digest = "ab" * 32
        self.assertEqual(expected_sha256(f"{digest}  {SETUP}\n", SETUP), digest)
        self.assertEqual(expected_sha256(f"{digest} *{SETUP}\n", SETUP), digest)
        self.assertEqual(expected_sha256(f"{SETUP}: {digest}\n", SETUP), digest)
        self.assertEqual(expected_sha256(digest + "\n", SETUP), digest)
        other = "cd" * 32
        listed = f"{other}  other.exe\n{digest}  {SETUP}\n"
        self.assertEqual(expected_sha256(listed, SETUP), digest)
        self.assertIsNone(expected_sha256(f"{other}  other.exe\n", SETUP))
        self.assertIsNone(expected_sha256(f"{digest}\n{other}\n", SETUP))

    def test_verify_matches_and_rejects_mismatch(self) -> None:
        payload = b"installer-bytes"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / SETUP
            path.write_bytes(payload)
            self.assertEqual(verify_installer(path, None, SETUP), "skipped")
            self.assertEqual(verify_installer(path, f"{digest}  {SETUP}\n", SETUP), "verified")
            path.write_bytes(payload)
            with self.assertRaises(UpdateError) as caught:
                verify_installer(path, f"{'ff' * 32}  {SETUP}\n", SETUP)
            self.assertEqual(str(caught.exception), MSG_MISMATCH)
            self.assertFalse(path.exists())


class NetworkTests(unittest.TestCase):
    def test_check_uses_short_timeout_and_user_agent(self) -> None:
        opener = FakeOpener([_release("v2.2.0")])
        result = check_for_update(opener=opener, current="2.2.0")
        self.assertEqual(result.status, "up_to_date")
        self.assertEqual(opener.timeout, CHECK_TIMEOUT_SECONDS)
        self.assertLessEqual(CHECK_TIMEOUT_SECONDS, 8)
        self.assertEqual(opener.requests[0].full_url, RELEASES_API)
        self.assertIn("CanvasParentReport/", opener.requests[0].get_header("User-agent"))

    def test_offline_rate_limit_and_bad_payload(self) -> None:
        offline = check_for_update(
            opener=FakeOpener(b"", error=urllib.error.URLError("offline")),
            current="2.2.0",
        )
        self.assertEqual(offline.status, "error")
        self.assertEqual(offline.message, MSG_OFFLINE)
        limited = check_for_update(
            opener=FakeOpener(b"", error=urllib.error.HTTPError(RELEASES_API, 429, "Too Many", hdrs=None, fp=io.BytesIO(b""))),
            current="2.2.0",
        )
        self.assertEqual(limited.message, MSG_LIMIT)
        broken = check_for_update(opener=FakeOpener(b"{"), current="2.2.0")
        self.assertEqual(broken.status, "error")
        self.assertEqual(broken.message, MSG_LATER)
        weird = check_for_update(opener=FakeOpener({"message": "nope"}), current="2.2.0")
        self.assertEqual(weird.status, "error")

    def test_download_verifies_checksum_and_allows_missing_checksum(self) -> None:
        payload = b"MZ-fake-installer"
        digest = hashlib.sha256(payload).hexdigest()
        offer = UpdateOffer(
            current="2.2.0",
            latest="2.3.0",
            notes="",
            html_url=RELEASES_PAGE,
            installer_name=SETUP,
            installer_url=SETUP_URL,
            checksum_name="SHA256SUMS.txt",
            checksum_url=SUMS_URL,
        )
        files = {
            SETUP_URL: payload,
            SUMS_URL: f"{digest}  {SETUP}\n".encode(),
        }
        seen: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared = download_and_verify(
                offer,
                Path(tmp),
                opener=FakeOpener(files),
                progress=lambda got, total: seen.append((got, total)),
            )
            self.assertEqual(prepared.verification, "verified")
            self.assertEqual(prepared.installer.read_bytes(), payload)
            self.assertTrue(seen)
            self.assertEqual(seen[-1][0], len(payload))

        plain = UpdateOffer(
            current="2.2.0",
            latest="2.3.0",
            notes="",
            html_url=RELEASES_PAGE,
            installer_name=SETUP,
            installer_url=SETUP_URL,
        )
        with tempfile.TemporaryDirectory() as tmp:
            prepared = download_and_verify(plain, Path(tmp), opener=FakeOpener({SETUP_URL: payload}))
            self.assertEqual(prepared.verification, "skipped")

    def test_download_aborts_on_mismatch_cancel_and_bad_redirect(self) -> None:
        payload = b"MZ-fake-installer"
        offer = UpdateOffer(
            current="2.2.0",
            latest="2.3.0",
            notes="",
            html_url=RELEASES_PAGE,
            installer_name=SETUP,
            installer_url=SETUP_URL,
            checksum_name="SHA256SUMS.txt",
            checksum_url=SUMS_URL,
        )
        files = {SETUP_URL: payload, SUMS_URL: f"{'ab' * 32}  {SETUP}\n".encode()}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError) as caught:
                download_and_verify(offer, Path(tmp), opener=FakeOpener(files))
            self.assertEqual(str(caught.exception), MSG_MISMATCH)
            self.assertFalse((Path(tmp) / SETUP).exists())

        missing_name = {SETUP_URL: payload, SUMS_URL: f"{'ab' * 32}  other.exe\n".encode()}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError) as caught:
                download_and_verify(offer, Path(tmp), opener=FakeOpener(missing_name))
            self.assertEqual(str(caught.exception), MSG_CHECKSUM_MISSING_NAME)

        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateCancelled):
                download_file(
                    SETUP_URL,
                    Path(tmp) / SETUP,
                    opener=FakeOpener({SETUP_URL: payload}),
                    timeout=5,
                    limit=1000,
                    cancel_event=cancel,
                )
            self.assertFalse((Path(tmp) / SETUP).exists())

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError) as caught:
                download_file(
                    SETUP_URL,
                    Path(tmp) / SETUP,
                    opener=FakeOpener({SETUP_URL: payload}, finals={SETUP_URL: "https://evil.example/setup.exe"}),
                    timeout=5,
                    limit=1000,
                )
            self.assertEqual(str(caught.exception), MSG_REDIRECT)

        with self.assertRaises(UpdateError):
            download_file(
                "https://evil.example/setup.exe",
                Path("unused.exe"),
                opener=FakeOpener({}),
                timeout=5,
                limit=1000,
            )


class InstallPlanTests(unittest.TestCase):
    def test_helper_waits_closes_and_relaunches_without_touching_settings(self) -> None:
        installer = Path(r"C:\Users\Example\AppData\Local\Temp\CanvasParentReport-update\update-1") / SETUP
        app_exe = r"C:\Users\Example\AppData\Local\Canvas Parent Report\CanvasParentReport.exe"
        script = build_apply_script(installer, app_exe, 4242)
        self.assertIn("Wait-Process -Id 4242", script)
        self.assertIn("'/SILENT'", script)
        self.assertIn("'/CLOSEAPPLICATIONS'", script)
        self.assertIn("'/NORESTARTAPPLICATIONS'", script)
        self.assertIn("'/NORESTART'", script)
        self.assertIn(app_exe, script)
        self.assertNotIn("schtasks", script.lower())
        self.assertNotIn("Remove-Item", script)
        self.assertNotIn("Credential", script)

    def test_start_installer_invokes_helper_without_running_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / SETUP
            installer.write_bytes(b"MZ")
            calls = []

            def popen(command, close_fds=False, creationflags=0):
                calls.append((command, close_fds, creationflags))
                return mock.Mock()

            script = start_installer(
                installer,
                app_executable=r"C:\Users\Example\AppData\Local\Canvas Parent Report\CanvasParentReport.exe",
                pid=7,
                popen=popen,
            )
            self.assertTrue(script.is_file())
            self.assertEqual(calls[0][0][0], "powershell")
            self.assertIn("-File", calls[0][0])
            self.assertIn(str(script), calls[0][0])
            self.assertEqual(calls[0][2], 0)

    def test_source_runs_do_not_install_in_place(self) -> None:
        from desktop.updates import can_apply_update

        self.assertFalse(can_apply_update())
        if sys.platform != "win32":
            self.assertIsNone(hold_window_mutex())


class HeadlessTests(unittest.TestCase):
    def test_run_flag_suppresses_checks(self) -> None:
        self.assertTrue(updates_suppressed(["--run"]))
        self.assertTrue(updates_suppressed(["desktop_app.py", "--run"]))
        self.assertFalse(updates_suppressed(["desktop_app.py"]))
        self.assertFalse(automatic_check_enabled(["--run"]))
        previous = os.environ.get("CPR_SKIP_UPDATE_CHECK")
        os.environ["CPR_SKIP_UPDATE_CHECK"] = "1"
        try:
            self.assertFalse(updates_suppressed([]))
            self.assertFalse(automatic_check_enabled([]))
        finally:
            if previous is None:
                os.environ.pop("CPR_SKIP_UPDATE_CHECK", None)
            else:
                os.environ["CPR_SKIP_UPDATE_CHECK"] = previous

    def test_headless_modules_do_not_check_for_updates(self) -> None:
        runner = (ROOT / "desktop/runner.py").read_text(encoding="utf-8")
        entry = (ROOT / "desktop_app.py").read_text(encoding="utf-8")
        self.assertNotIn("check_for_update", runner)
        self.assertNotIn("update_ui", runner)
        self.assertNotIn("hold_window_mutex", runner)
        self.assertIn('if "--run" in args:', entry)
        app_source = (ROOT / "desktop/app.py").read_text(encoding="utf-8")
        self.assertIn("hold_window_mutex", app_source)

    def test_headless_entry_point_does_not_call_the_checker(self) -> None:
        from desktop.logging_setup import close_logging

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CPR_APP_DIR"] = tmp
            try:
                with mock.patch("desktop.runner.run_headless", return_value=0) as run:
                    with mock.patch("desktop.updates.check_for_update") as check:
                        import desktop_app

                        code = desktop_app.main(["--run"])
                self.assertEqual(code, 0)
                run.assert_called_once()
                check.assert_not_called()
            finally:
                close_logging()

    def test_close_logging_releases_the_log_file(self) -> None:
        from desktop.logging_setup import close_logging, get_logger

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CPR_APP_DIR"] = tmp
            close_logging()
            get_logger().info("headless run started")
            log_path = Path(tmp) / "logs" / "app.log"
            self.assertTrue(log_path.is_file())
            close_logging()
            log_path.unlink()
            self.assertFalse(log_path.exists())


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_is_2_2_0_everywhere(self) -> None:
        self.assertEqual(APP_VERSION, "2.2.0")
        self.assertEqual(package_version, "2.2.0")
        iss = (ROOT / "installer/CanvasParentReport.iss").read_text(encoding="utf-8")
        self.assertIn('#define MyAppVersion "2.2.0"', iss)
        self.assertIn("OutputBaseFilename=CanvasParentReport-Setup-2.2.0", iss)
        self.assertIn("{{8C4E2A71-5B19-4D33-9F60-2A7C1E8B44D0}", iss)
        self.assertIn("CloseApplications=yes", iss)
        self.assertIn("RestartApplications=yes", iss)
        self.assertIn("UsePreviousAppDir=yes", iss)
        self.assertIn("AppMutex=CanvasParentReportMutex", iss)
        self.assertIn("PrivilegesRequired=lowest", iss)
        self.assertNotIn("UninstallDelete", iss)
        self.assertNotIn("{userappdata}", iss.lower())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("CanvasParentReport-Setup-2.2.0.exe", readme)
        self.assertIn("Check for updates", readme)
        self.assertIn("SHA256SUMS.txt", readme)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertTrue(any(line.startswith("## 2.2.0") for line in changelog.splitlines()))
        workflow = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("Get-FileHash -Algorithm SHA256", workflow)
        self.assertIn("SHA256SUMS.txt", workflow)
        self.assertIn("MyAppVersion", workflow)
        self.assertIn("CanvasParentReport-Setup-${{ needs.installer.outputs.version }}.exe", workflow)


def _offer(*, checksum: bool = True) -> UpdateOffer:
    return UpdateOffer(
        current="2.2.0",
        latest="2.3.0",
        notes="Built-in updates. Settings stay on this computer.",
        html_url="https://github.com/Mooglytonkers/Canvas-Parent-Report/releases/tag/v2.3.0",
        installer_name=SETUP,
        installer_url=SETUP_URL,
        installer_size=10_000_000,
        checksum_name="SHA256SUMS.txt" if checksum else "",
        checksum_url=SUMS_URL if checksum else "",
    )


class UpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        os.environ["CPR_SKIP_UPDATE_CHECK"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["CPR_APP_DIR"] = self._tmp.name

    def tearDown(self) -> None:
        from desktop.logging_setup import close_logging

        close_logging()
        self._tmp.cleanup()

    def _window(self):
        from desktop.main_window import MainWindow
        from desktop.theme import apply_theme

        apply_theme(self._app)
        window = MainWindow()
        window.resize(1040, 820)
        return window

    def _wait_thread(self, thread) -> None:
        for _ in range(100):
            self._app.processEvents()
            if thread is None or not thread.isRunning():
                self._app.processEvents()
                return
            time.sleep(0.02)
        self.fail("background update work did not finish")

    def test_prompt_copy_for_install_and_browser(self) -> None:
        from desktop.update_ui import UpdateDownloadDialog, UpdatePrompt

        prompt = UpdatePrompt()
        prompt.show_offer(_offer(), can_install=True)
        self.assertEqual(prompt.update_button.text(), "Update now")
        self.assertIn("SHA-256", prompt.message.text())
        self.assertIn("2.3.0", prompt.message.text())
        self.assertIn("2.2.0", prompt.message.text())
        prompt.show_offer(_offer(checksum=False), can_install=True)
        self.assertIn("does not include a checksum", prompt.message.text())
        prompt.show_offer(_offer(), can_install=False)
        self.assertEqual(prompt.update_button.text(), "Open releases page")
        self.assertIn("releases page", prompt.message.text())

        dialog = UpdateDownloadDialog()
        dialog.set_status("Downloading CanvasParentReport-Setup-2.3.0.exe")
        dialog.set_progress(4_200_000, 10_000_000)
        self.assertEqual(dialog.bar.value(), 42)
        self.assertIn("42%", dialog.amount.text())
        self.assertEqual(dialog.cancel_button.text(), "Cancel")
        dialog.show_error(MSG_OFFLINE)
        self.assertEqual(dialog.cancel_button.text(), "Close")
        self.assertIn("internet", dialog.detail.text())

    def test_later_hides_the_prompt_and_source_runs_open_the_browser(self) -> None:
        window = self._window()
        window.show()
        self._app.processEvents()
        window._updates.present_offer(_offer(), can_install=True)
        self._app.processEvents()
        self.assertFalse(window.update_prompt.isHidden())
        window.update_prompt.later_button.click()
        self._app.processEvents()
        self.assertTrue(window.update_prompt.isHidden())

        window._updates.present_offer(_offer(), can_install=False)
        with mock.patch("desktop.update_ui.QDesktopServices.openUrl") as open_url:
            with mock.patch("desktop.update_ui.download_and_verify") as download:
                window.update_prompt.update_button.click()
                self._app.processEvents()
        open_url.assert_called_once()
        download.assert_not_called()
        target = open_url.call_args.args[0].toString()
        self.assertTrue(target.startswith("https://github.com/Mooglytonkers/Canvas-Parent-Report/releases"))

    def test_manual_check_announces_result_and_auto_check_stays_quiet(self) -> None:
        current = UpdateCheckResult(
            status="up_to_date",
            current="2.2.0",
            latest="2.2.0",
            message="You're up to date. Version 2.2.0 is the latest.",
        )
        window = self._window()
        window.show()
        with mock.patch("desktop.update_ui.check_for_update", return_value=current):
            window.check_for_updates()
            self._wait_thread(window._updates._check)
        self.assertIn("up to date", window.banner._label.text().lower())
        self.assertIn("2.2.0", window.banner._label.text())
        self.assertEqual(window.check_button.text(), "Check for updates")
        self.assertTrue(window.check_button.isEnabled())

        failed = UpdateCheckResult(status="error", current="2.2.0", message=MSG_OFFLINE)
        with mock.patch("desktop.update_ui.check_for_update", return_value=failed):
            window.check_for_updates()
            self._wait_thread(window._updates._check)
        self.assertEqual(window.banner._label.text(), MSG_OFFLINE)

        available = UpdateCheckResult(
            status="update_available",
            current="2.2.0",
            latest="2.3.0",
            message="Version 2.3.0 is available. You have 2.2.0.",
            offer=_offer(),
        )
        os.environ.pop("CPR_SKIP_UPDATE_CHECK", None)
        quiet = self._window()
        try:
            with mock.patch("desktop.update_ui.check_for_update", return_value=available) as check:
                quiet.show()
                self._wait_thread(quiet._updates._check)
            check.assert_called()
        finally:
            os.environ["CPR_SKIP_UPDATE_CHECK"] = "1"
        self.assertFalse(quiet.update_prompt.isHidden())
        self.assertEqual(quiet.update_prompt.update_button.text(), "Open releases page")
        self.assertTrue(quiet.banner.isHidden())
        self.assertEqual(quiet.check_button.text(), "Check for updates")

        os.environ.pop("CPR_SKIP_UPDATE_CHECK", None)
        silent_error = self._window()
        try:
            with mock.patch("desktop.update_ui.check_for_update", return_value=failed):
                silent_error.show()
                self._wait_thread(silent_error._updates._check)
        finally:
            os.environ["CPR_SKIP_UPDATE_CHECK"] = "1"
        self.assertTrue(silent_error.banner.isHidden())
        self.assertTrue(silent_error.update_prompt.isHidden())

    def test_checksum_failure_does_not_launch_the_installer(self) -> None:
        window = self._window()
        window.show()
        window._updates.present_offer(_offer(), can_install=True)
        with mock.patch("desktop.update_ui.can_apply_update", return_value=True):
            with mock.patch("desktop.update_ui.download_and_verify", side_effect=UpdateError(MSG_MISMATCH)):
                with mock.patch("desktop.update_ui.start_installer") as start:
                    window.update_prompt.update_button.click()
                    self._wait_thread(window._updates._download)
        start.assert_not_called()
        self.assertIsNotNone(window._updates._dialog)
        self.assertIn("checksum", window._updates._dialog.detail.text().lower())
        self.assertEqual(window._updates._dialog.cancel_button.text(), "Close")

    def test_verified_download_launches_installer_then_closes_the_app(self) -> None:
        window = self._window()
        window.show()
        window._updates.present_offer(_offer(), can_install=True)
        prepared = PreparedUpdate(installer=Path(r"C:\Users\Example\AppData\Local\Temp\CanvasParentReport-update\update-1") / SETUP, verification="verified")
        with mock.patch("desktop.update_ui.can_apply_update", return_value=True):
            with mock.patch("desktop.update_ui.download_and_verify", return_value=prepared):
                with mock.patch("desktop.update_ui.start_installer") as start:
                    with mock.patch.object(self._app, "quit") as quit_app:
                        window.update_prompt.update_button.click()
                        self._wait_thread(window._updates._download)
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], prepared.installer)
        quit_app.assert_called_once()
        self.assertIn("Checksum matched", window._updates._dialog.detail.text())


if __name__ == "__main__":
    unittest.main()
