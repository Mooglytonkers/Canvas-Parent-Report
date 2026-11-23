"""Windows Task Scheduler command and XML generation.

One task, "Canvas Parent Report", with a weekday trigger for each time.
"Run when I sign in if a scheduled run was missed" maps to Task Scheduler's
StartWhenAvailable setting.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

TASK_NAME = "Canvas Parent Report"

DAY_XML = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _boundary(clock: str) -> str:
    hour, minute = _parse_clock(clock)
    return f"2026-01-05T{hour:02d}:{minute:02d}:00"


def _parse_clock(clock: str) -> tuple[int, int]:
    text = (clock or "").strip()
    hour_text, _, minute_text = text.partition(":")
    hour = int(hour_text)
    minute = int(minute_text or "0")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time must be HH:MM, got {clock!r}.")
    return hour, minute


def task_xml(
    *,
    command: str,
    arguments: str,
    days: list[str],
    times: list[str],
    run_missed: bool,
) -> str:
    """Build Task Scheduler XML. Times are 24-hour HH:MM strings."""
    chosen = [DAY_XML[day] for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if day in days]
    if not chosen:
        raise ValueError("Choose at least one day to schedule.")
    if not times:
        raise ValueError("Choose at least one time to schedule.")
    day_xml = "\n".join(f"          <{name} />" for name in chosen)
    triggers = []
    for clock in times:
        triggers.append(
            "    <CalendarTrigger>\n"
            f"      <StartBoundary>{_boundary(clock)}</StartBoundary>\n"
            "      <Enabled>true</Enabled>\n"
            "      <ScheduleByWeek>\n"
            "        <DaysOfWeek>\n"
            f"{day_xml}\n"
            "        </DaysOfWeek>\n"
            "        <WeeksInterval>1</WeeksInterval>\n"
            "      </ScheduleByWeek>\n"
            "    </CalendarTrigger>"
        )
    missed = "true" if run_missed else "false"
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        "    <Description>Build the Canvas missing-work report, then print or email it if those are turned on.</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        + "\n".join(triggers)
        + "\n  </Triggers>\n"
        "  <Principals>\n"
        "    <Principal>\n"
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        f"    <StartWhenAvailable>{missed}</StartWhenAvailable>\n"
        "    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>\n"
        "    <Enabled>true</Enabled>\n"
        "    <Hidden>false</Hidden>\n"
        "    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>\n"
        "  </Settings>\n"
        "  <Actions>\n"
        "    <Exec>\n"
        f"      <Command>{xml_escape(command)}</Command>\n"
        f"      <Arguments>{xml_escape(arguments)}</Arguments>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def schtasks_create_command(xml_path: Path) -> list[str]:
    return ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"]


def schtasks_delete_command() -> list[str]:
    return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]


def install_schedule(config, *, command: str, arguments: str) -> tuple[bool, str]:
    """Create or remove the Windows task. On other systems, only the settings are kept."""
    import subprocess
    import sys

    from desktop.logging_setup import get_logger
    from desktop.paths import app_dir

    log = get_logger()
    times = []
    for clock in (config.morning, config.evening):
        text = (clock or "").strip()
        if text and text not in times:
            times.append(text)
    if not config.schedule_days or not times:
        if sys.platform == "win32":
            subprocess.run(schtasks_delete_command(), capture_output=True, text=True, check=False)
        return True, "No schedule was created."
    try:
        xml = task_xml(
            command=command,
            arguments=arguments,
            days=list(config.schedule_days),
            times=times,
            run_missed=bool(config.run_missed_at_signin),
        )
    except ValueError as exc:
        return False, str(exc)
    if sys.platform != "win32":
        return True, "The schedule was saved for this computer."
    path = app_dir() / "schedule-task.xml"
    path.write_bytes(xml.encode("utf-16"))
    completed = subprocess.run(
        schtasks_create_command(path),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        log.info("schtasks failed: %s", detail or completed.returncode)
        return False, (
            "Windows did not save the schedule. You can try again from Settings. "
            "The report itself is ready to run."
        )
    return True, "The weekday schedule was saved."


def launch_parts(exe: str | None = None, script: str | None = None, frozen: bool | None = None) -> tuple[str, str]:
    """Return (command, arguments) for the scheduled --run launch."""
    import sys

    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        command = exe or sys.executable
        return command, "--run"
    command = exe or sys.executable
    script_path = script or str(Path(__file__).resolve().parents[1] / "desktop_app.py")
    return command, f'"{script_path}" --run'


def next_occurrence(
    days: list[str],
    times: list[str],
    now: datetime | None = None,
) -> datetime | None:
    """Next local time the schedule would run. `now` is not included."""
    indexes = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    wanted = {indexes[day] for day in days if day in indexes}
    clocks: list[tuple[int, int]] = []
    for text in times:
        if not str(text).strip():
            continue
        try:
            clocks.append(_parse_clock(text))
        except ValueError:
            continue
    if not wanted or not clocks:
        return None
    moment = now or datetime.now()
    moment = moment.replace(second=0, microsecond=0)
    for offset in range(0, 8):
        day = (moment + timedelta(days=offset)).date()
        if day.weekday() not in wanted:
            continue
        for hour, minute in sorted(clocks):
            candidate = datetime(day.year, day.month, day.day, hour, minute)
            if candidate > moment:
                return candidate
    return None


def friendly_when(moment: datetime) -> str:
    hour = moment.strftime("%I").lstrip("0") or "12"
    return (
        f"{moment.strftime('%A')}, {moment.strftime('%b')} {moment.day} "
        f"at {hour}:{moment.strftime('%M %p')}"
    )
