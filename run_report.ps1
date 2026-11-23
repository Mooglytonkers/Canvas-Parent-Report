# Fetch Canvas data, build the missing-work PDF, and follow config.ini options.
# Reads CANVAS_TOKEN from the environment or a local .env file; never prints it.
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
