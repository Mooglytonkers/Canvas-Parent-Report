"""Check GitHub Releases and prepare a Windows in-place update.

Verification rule for an installer download:

1. The asset name matches ``CanvasParentReport-Setup-*.exe``.
2. The URL, and every redirect, is HTTPS with no username or password.
   ``github.com`` links must be this repository's ``/releases/download/``
   path. Redirects may land on ``githubusercontent.com`` asset hosts.
3. If the release includes ``SHA256SUMS.txt``, ``SHA256SUMS``, or a
   ``.sha256`` file, the downloaded installer is run only when its
   SHA-256 digest matches that file. A mismatch deletes the file and
   stops the update.
4. If the release has no checksum file, the URL checks above are the
   verification. The update dialog says a checksum was not published.
   Releases before 2.2.0 are in this group.

Scheduled ``--run`` report jobs never call this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from desktop.version import APP_VERSION

GITHUB_OWNER = "Mooglytonkers"
GITHUB_REPO = "Canvas-Parent-Report"
RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=30"
)
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
DOWNLOAD_PREFIX = f"/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/"
NOTES_PREFIX = f"/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

CHECK_TIMEOUT_SECONDS = 6.0
DOWNLOAD_TIMEOUT_SECONDS = 60.0
MAX_INSTALLER_BYTES = 300 * 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024

INSTALLER_NAME = re.compile(r"^CanvasParentReport-Setup-.+\.exe$", re.IGNORECASE)
VERSION_TEXT = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)
HEX64 = re.compile(r"\b([a-fA-F0-9]{64})\b")

MSG_OFFLINE = "Couldn't check for updates. Check your internet connection and try again."
MSG_LIMIT = "GitHub is limiting update checks right now. Try again in a little while."
MSG_LATER = "Couldn't check for updates. Try again in a little while."
MSG_UNTRUSTED = "The download link is not from GitHub. The update was stopped."
MSG_REDIRECT = "The download was redirected away from GitHub. The update was stopped."
MSG_MISMATCH = "The downloaded installer did not match the published checksum. The update was stopped."
MSG_CHECKSUM_MISSING_NAME = (
    "The release has a checksum file, but it does not list this installer. The update was stopped."
)
MSG_TOO_LARGE = "The download is larger than this app can install. The update was stopped."
MSG_NOT_WINDOWS = "Open the releases page to download the update."


class UpdateError(Exception):
    """A problem the window can show in a sentence."""


class UpdateCancelled(Exception):
    """The person chose Cancel."""


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int = 0


@dataclass(frozen=True)
class UpdateOffer:
    current: str
    latest: str
    notes: str
    html_url: str
    installer_name: str = ""
    installer_url: str = ""
    installer_size: int = 0
    checksum_name: str = ""
    checksum_url: str = ""
    checksum_rejected: bool = False

    @property
    def can_download(self) -> bool:
        return bool(self.installer_name and self.installer_url) and not self.checksum_rejected


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    current: str
    latest: str = ""
    message: str = ""
    offer: UpdateOffer | None = None


@dataclass(frozen=True)
class PreparedUpdate:
    installer: Path
    verification: str
    """``verified`` when a checksum matched, ``skipped`` when none was published."""


def updates_suppressed(argv: list[str] | None = None) -> bool:
    """True when this process is a scheduled or headless report run."""
    args = list(sys.argv if argv is None else argv)
    return "--run" in args


def automatic_check_enabled(argv: list[str] | None = None) -> bool:
    """Background checks stay off for ``--run`` and for screenshot runs.

    ``CPR_SKIP_UPDATE_CHECK=1`` only silences the check that runs when the
    window opens. The Check for updates button still works.
    """
    if updates_suppressed(argv):
        return False
    flag = (os.environ.get("CPR_SKIP_UPDATE_CHECK") or "").strip().lower()
    return flag not in {"1", "true", "yes"}


def can_apply_update() -> bool:
    """The Windows installer can replace a frozen build. Source runs open the browser."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def parse_version(value: str) -> Version:
    text = (value or "").strip()
    if len(text) >= 2 and text[0] in "vV" and text[1].isdigit():
        text = text[1:]
    match = VERSION_TEXT.fullmatch(text)
    if match is None:
        raise UpdateError(f"Unrecognized version {value!r}.")
    return Version(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("pre") or "",
    )


def compare_versions(left: Version, right: Version) -> int:
    for part, other in zip(
        (left.major, left.minor, left.patch),
        (right.major, right.minor, right.patch),
    ):
        if part != other:
            return -1 if part < other else 1
    if left.prerelease == right.prerelease:
        return 0
    if not left.prerelease:
        return 1
    if not right.prerelease:
        return -1
    if left.prerelease < right.prerelease:
        return -1
    if left.prerelease > right.prerelease:
        return 1
    return 0


def is_newer(latest: str, current: str) -> bool:
    return compare_versions(parse_version(latest), parse_version(current)) > 0


def _clean_url(url: str) -> urllib.parse.SplitResult | None:
    text = (url or "").strip()
    if not text or any(ch.isspace() or ord(ch) < 32 or ch == "\\" for ch in text):
        return None
    return urllib.parse.urlsplit(text)


def is_trusted_release_url(url: str) -> bool:
    parsed = _clean_url(url)
    if parsed is None or parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or ".." in host:
        return False
    if host == "github.com":
        return parsed.path.startswith(DOWNLOAD_PREFIX)
    return host == "githubusercontent.com" or host.endswith(".githubusercontent.com")


def is_release_notes_url(url: str) -> bool:
    parsed = _clean_url(url)
    if parsed is None or parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != "github.com":
        return False
    return parsed.path.startswith(NOTES_PREFIX)


def release_page_url(url: str) -> str:
    if is_release_notes_url(url):
        return url.strip()
    return RELEASES_PAGE


def user_agent() -> str:
    return f"CanvasParentReport/{APP_VERSION}"


def notes_excerpt(body: str, limit: int = 320) -> str:
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rstrip()
    gap = clipped.rfind(" ")
    if gap > limit // 2:
        clipped = clipped[:gap]
    return clipped.rstrip() + "…"


def is_checksum_name(name: str) -> bool:
    lower = Path(name).name.lower()
    return lower in {"sha256sums.txt", "sha256sums"} or lower.endswith(".sha256") or lower.endswith(".sha256.txt")


def safe_asset_name(name: str, *, kind: str) -> str:
    base = Path(name or "").name
    if base != (name or "") or base in {"", ".", ".."} or "/" in (name or "") or "\\" in (name or ""):
        raise UpdateError(MSG_UNTRUSTED)
    if kind == "installer" and INSTALLER_NAME.fullmatch(base) is None:
        raise UpdateError(MSG_UNTRUSTED)
    if kind == "checksum" and not is_checksum_name(base):
        raise UpdateError(MSG_UNTRUSTED)
    return base


def _asset(item: dict) -> ReleaseAsset | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "")
    url = str(item.get("browser_download_url") or "")
    try:
        size = int(item.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if not name or not url:
        return None
    return ReleaseAsset(name=name, url=url, size=size)


def select_installer_asset(assets: list[ReleaseAsset], version: str) -> ReleaseAsset | None:
    matches = [asset for asset in assets if INSTALLER_NAME.fullmatch(asset.name)]
    if not matches:
        return None
    preferred = f"CanvasParentReport-Setup-{version}.exe".lower()
    for asset in matches:
        if asset.name.lower() == preferred:
            return asset
    return matches[0]


def select_checksum_asset(assets: list[ReleaseAsset]) -> ReleaseAsset | None:
    matches = [asset for asset in assets if is_checksum_name(asset.name)]
    if not matches:
        return None
    for asset in matches:
        if asset.name.lower() in {"sha256sums.txt", "sha256sums"}:
            return asset
    return matches[0]


def choose_published_release(releases: list) -> dict | None:
    """Newest final release. Drafts, prereleases, and odd tags are ignored."""
    chosen: tuple[Version, dict] | None = None
    for item in releases:
        if not isinstance(item, dict):
            continue
        if item.get("draft") or item.get("prerelease"):
            continue
        try:
            version = parse_version(str(item.get("tag_name") or ""))
        except UpdateError:
            continue
        if version.prerelease:
            continue
        if chosen is None or compare_versions(version, chosen[0]) > 0:
            chosen = (version, item)
    if chosen is None:
        return None
    return chosen[1]


def _up_to_date(current: str, latest: str = "") -> UpdateCheckResult:
    shown = latest or current
    return UpdateCheckResult(
        status="up_to_date",
        current=current,
        latest=shown,
        message=f"You're up to date. Version {shown} is the latest.",
    )


def _offer_from(release: dict, current: str, latest: Version) -> UpdateOffer:
    raw_assets = release.get("assets") or []
    assets = [asset for asset in (_asset(item) for item in raw_assets) if asset is not None]
    installer = select_installer_asset(assets, str(latest))
    checksum = select_checksum_asset(assets) if installer is not None else None
    installer_url = ""
    installer_name = ""
    installer_size = 0
    if installer is not None and is_trusted_release_url(installer.url):
        installer_name = installer.name
        installer_url = installer.url
        installer_size = installer.size
    checksum_name = ""
    checksum_url = ""
    checksum_rejected = False
    if checksum is not None:
        if is_trusted_release_url(checksum.url):
            checksum_name = checksum.name
            checksum_url = checksum.url
        else:
            checksum_rejected = True
    return UpdateOffer(
        current=current,
        latest=str(latest),
        notes=notes_excerpt(str(release.get("body") or "")),
        html_url=release_page_url(str(release.get("html_url") or "")),
        installer_name=installer_name,
        installer_url=installer_url,
        installer_size=installer_size,
        checksum_name=checksum_name,
        checksum_url=checksum_url,
        checksum_rejected=checksum_rejected,
    )


def interpret_releases(payload: list, current: str | None = None) -> UpdateCheckResult:
    current_text = (current or APP_VERSION).strip()
    try:
        current_version = parse_version(current_text)
    except UpdateError:
        return UpdateCheckResult(status="error", current=current_text, message=MSG_LATER)
    release = choose_published_release(payload)
    if release is None:
        return _up_to_date(current_text)
    latest = parse_version(str(release.get("tag_name") or ""))
    if compare_versions(latest, current_version) <= 0:
        return _up_to_date(current_text, str(latest))
    offer = _offer_from(release, current_text, latest)
    return UpdateCheckResult(
        status="update_available",
        current=current_text,
        latest=str(latest),
        message=f"Version {latest} is available. You have {current_text}.",
        offer=offer,
    )


class TrustedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        joined = urllib.parse.urljoin(req.full_url, newurl)
        if not is_trusted_release_url(joined):
            raise UpdateError(MSG_REDIRECT)
        return super().redirect_request(req, fp, code, msg, headers, joined)


def build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(TrustedRedirectHandler)


def _request(url: str, accept: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": user_agent(),
        },
    )


def _friendly_network_error(exc: BaseException) -> UpdateError:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in {403, 429}:
            return UpdateError(MSG_LIMIT)
        return UpdateError(MSG_LATER)
    if isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError)):
        return UpdateError(MSG_OFFLINE)
    if isinstance(exc, UpdateError):
        return exc
    return UpdateError(MSG_LATER)


def fetch_release_payload(opener, timeout: float) -> list:
    try:
        response = opener.open(
            _request(RELEASES_API, "application/vnd.github+json"),
            timeout=timeout,
        )
    except UpdateError:
        raise
    except Exception as exc:
        raise _friendly_network_error(exc) from exc
    try:
        with response:
            raw = response.read()
    except Exception as exc:
        raise _friendly_network_error(exc) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError(MSG_LATER) from exc
    if not isinstance(payload, list):
        raise UpdateError(MSG_LATER)
    return payload


def check_for_update(
    *,
    timeout: float = CHECK_TIMEOUT_SECONDS,
    opener=None,
    current: str | None = None,
) -> UpdateCheckResult:
    """Return a result object. Network failures stay inside ``status='error'``."""
    client = opener if opener is not None else build_opener()
    try:
        payload = fetch_release_payload(client, timeout)
        return interpret_releases(payload, current)
    except UpdateError as exc:
        return UpdateCheckResult(
            status="error",
            current=(current or APP_VERSION).strip(),
            message=str(exc) or MSG_LATER,
        )
    except Exception:
        return UpdateCheckResult(
            status="error",
            current=(current or APP_VERSION).strip(),
            message=MSG_LATER,
        )


def expected_sha256(checksum_text: str, installer_name: str) -> str | None:
    """Digest for ``installer_name``, or the only bare digest in a one-line file."""
    wanted = installer_name.lower()
    named: str | None = None
    bare: list[str] = []
    content_lines = 0
    for raw in (checksum_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        content_lines += 1
        match = HEX64.search(line)
        if match is None:
            continue
        digest = match.group(1).lower()
        if wanted in line.lower():
            named = digest
        elif HEX64.fullmatch(line):
            bare.append(digest)
    if named:
        return named
    if len(bare) == 1 and content_lines == 1:
        return bare[0]
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installer(path: Path, checksum_text: str | None, installer_name: str) -> str:
    """Return ``verified`` or ``skipped``. Raise ``UpdateError`` when a checksum does not match."""
    if checksum_text is None:
        return "skipped"
    expected = expected_sha256(checksum_text, installer_name)
    if not expected:
        path.unlink(missing_ok=True)
        raise UpdateError(MSG_CHECKSUM_MISSING_NAME)
    actual = sha256_file(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise UpdateError(MSG_MISMATCH)
    return "verified"


def _read_to(
    response,
    dest: Path,
    *,
    limit: int,
    progress,
    cancel_event,
) -> None:
    total_header = 0
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            total_header = int(headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total_header = 0
    if total_header > limit:
        raise UpdateError(MSG_TOO_LARGE)
    partial = dest.with_name(dest.name + ".part")
    received = 0
    try:
        with partial.open("wb") as handle:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled()
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise UpdateError(MSG_TOO_LARGE)
                handle.write(chunk)
                if progress is not None:
                    progress(received, total_header)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise


def download_file(
    url: str,
    dest: Path,
    *,
    opener,
    timeout: float,
    limit: int,
    progress=None,
    cancel_event=None,
) -> None:
    if not is_trusted_release_url(url):
        raise UpdateError(MSG_UNTRUSTED)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = opener.open(_request(url, "application/octet-stream"), timeout=timeout)
    except UpdateCancelled:
        raise
    except UpdateError:
        raise
    except Exception as exc:
        raise _friendly_network_error(exc) from exc
    try:
        with response:
            final = response.geturl() if hasattr(response, "geturl") else url
            if not is_trusted_release_url(final):
                raise UpdateError(MSG_REDIRECT)
            _read_to(response, dest, limit=limit, progress=progress, cancel_event=cancel_event)
    except UpdateCancelled:
        dest.unlink(missing_ok=True)
        raise


def download_and_verify(
    offer: UpdateOffer,
    dest_dir: Path,
    *,
    opener=None,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    progress=None,
    cancel_event=None,
    on_status=None,
) -> PreparedUpdate:
    if offer.checksum_rejected:
        raise UpdateError(MSG_UNTRUSTED)
    if not offer.can_download:
        raise UpdateError(MSG_NOT_WINDOWS)
    installer_name = safe_asset_name(offer.installer_name, kind="installer")
    client = opener if opener is not None else build_opener()
    dest_dir.mkdir(parents=True, exist_ok=True)
    installer_path = dest_dir / installer_name
    if on_status is not None:
        on_status(f"Downloading {installer_name}…")

    def installer_progress(received: int, total: int) -> None:
        if progress is not None:
            progress(received, total or offer.installer_size)

    download_file(
        offer.installer_url,
        installer_path,
        opener=client,
        timeout=timeout,
        limit=MAX_INSTALLER_BYTES,
        progress=installer_progress,
        cancel_event=cancel_event,
    )
    try:
        checksum_text: str | None = None
        if offer.checksum_url:
            checksum_name = safe_asset_name(offer.checksum_name, kind="checksum")
            if on_status is not None:
                on_status("Downloading the checksum…")
            checksum_path = dest_dir / checksum_name
            download_file(
                offer.checksum_url,
                checksum_path,
                opener=client,
                timeout=timeout,
                limit=MAX_CHECKSUM_BYTES,
                progress=None,
                cancel_event=cancel_event,
            )
            checksum_text = checksum_path.read_text(encoding="utf-8", errors="replace")
            if on_status is not None:
                on_status("Checking the download…")
        verification = verify_installer(installer_path, checksum_text, installer_name)
    except Exception:
        installer_path.unlink(missing_ok=True)
        raise
    return PreparedUpdate(installer=installer_path, verification=verification)


def new_update_dir() -> Path:
    root = Path(tempfile.gettempdir()) / "CanvasParentReport-update"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="update-", dir=root))


def ps_literal(value: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text or "\x00" in text:
        raise UpdateError(MSG_UNTRUSTED)
    return "'" + text.replace("'", "''") + "'"


def build_apply_script(installer: Path, app_executable: str, pid: int) -> str:
    """Wait until this app exits, run the installer, then open the updated app.

    The helper does not change settings, Credential Manager, or Task Scheduler.
    ``/NORESTARTAPPLICATIONS`` keeps Inno from opening a second copy. The
    script itself starts the same executable path after a successful install.
    """
    if int(pid) <= 0:
        raise UpdateError(MSG_LATER)
    installer_lit = ps_literal(str(installer))
    app_lit = ps_literal(str(app_executable))
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue -Timeout 90\n"
        "$proc = Start-Process -FilePath "
        f"{installer_lit} -ArgumentList "
        "'/SILENT','/CLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS','/NORESTART' "
        "-Wait -PassThru\n"
        "if ($proc.ExitCode -eq 0) {\n"
        f"    Start-Process -FilePath {app_lit}\n"
        "}\n"
    )


def powershell_command(script: Path) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script),
    ]


def start_installer(
    installer: Path,
    *,
    app_executable: str,
    pid: int | None = None,
    popen=None,
) -> Path:
    """Write the helper script and start it. The caller should then exit."""
    if not can_apply_update() and popen is None:
        raise UpdateError(MSG_NOT_WINDOWS)
    if installer.suffix.lower() != ".exe" or not installer.is_file():
        raise UpdateError("The installer file is missing. The update was stopped.")
    script_path = installer.with_name("apply-update.ps1")
    script_path.write_text(
        build_apply_script(installer, app_executable, pid or os.getpid()),
        encoding="utf-8",
    )
    command = powershell_command(script_path)
    flags = 0
    if popen is None:
        flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        )
    runner = popen or subprocess.Popen
    try:
        runner(command, close_fds=True, creationflags=flags)
    except OSError:
        if popen is not None or not flags:
            raise
        runner(command, close_fds=True)
    return script_path


_WINDOW_MUTEX = None


def hold_window_mutex() -> object | None:
    """Hold the Inno Setup AppMutex while the window is open.

    Headless ``--run`` does not call this, so a scheduled report does not
    look like the window the installer should close. The handle is kept
    for the life of the process so Windows does not release the mutex.
    """
    global _WINDOW_MUTEX
    if sys.platform != "win32":
        return None
    import ctypes

    _WINDOW_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "CanvasParentReportMutex")
    return _WINDOW_MUTEX
