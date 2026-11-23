# Fetch Canvas data, build the missing-work PDF, then follow config.ini:
# mark To Dos, print, and email, in that order, when each one is enabled.
# Flags such as --print, --no-print, --test-print, and --test-email are forwarded.
# Reads CANVAS_TOKEN and SMTP_PASSWORD from the environment or a local .env file;
# never prints them.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$pyExe = $null
$pyArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe = "py"
    $pyArgs = @("-3")
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pyExe = "python3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyExe = "python"
}

if (-not $pyExe) {
    Write-Error "Python was not found. Install Python 3.9 or newer from https://www.python.org/downloads/ and try again."
    exit 1
}

& $pyExe @pyArgs (Join-Path $PSScriptRoot "run_report.py") @args
exit $LASTEXITCODE
