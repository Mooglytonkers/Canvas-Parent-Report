@echo off
rem Fetch Canvas data, build the PDF, then mark To Dos, print, and email
rem when each option is enabled. Forwards flags such as --print, --no-print,
rem --test-print, and --test-email. Never prints CANVAS_TOKEN or SMTP_PASSWORD.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo error: Python was not found. Install Python 3.9 or newer from https://www.python.org/downloads/ and try again.
  exit /b 1
)

%PY% "%~dp0run_report.py" %*
exit /b %ERRORLEVEL%
