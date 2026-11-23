#!/usr/bin/env bash
# Fetch Canvas data, build the missing-work PDF, and follow config.ini options.
# Reads CANVAS_TOKEN from the environment or a local .env file; never prints it.
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
