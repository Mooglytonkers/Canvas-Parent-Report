#!/usr/bin/env python3
"""Canvas Parent Report desktop app.

With no arguments, open the window. Task Scheduler uses --run, which builds
the report with no window.
"""

from __future__ import annotations

import sys

from desktop.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    setup_logging()
    if "--run" in args:
        from desktop.runner import run_headless

        return run_headless()
    from desktop.app import launch

    return launch()


if __name__ == "__main__":
    sys.exit(main())
