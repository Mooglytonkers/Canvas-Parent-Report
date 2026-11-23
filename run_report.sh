#!/usr/bin/env bash
# Fetch Canvas data, build the missing-work PDF, then follow config.ini:
# mark To Dos, print, and email, in that order, when each one is enabled.
# Flags such as --print, --no-print, --test-print, and --test-email are forwarded.
# Reads CANVAS_TOKEN and SMTP_PASSWORD from the environment or a local .env file;
# never prints them.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  else
    PYTHON=python
  fi
fi

exec "$PYTHON" "$DIR/run_report.py" "$@"
