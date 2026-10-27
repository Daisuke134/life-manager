#!/usr/bin/env python3
"""Retired compatibility entrypoint for the old monolithic CP1 driver.

CP1 must be driven through the screenshot-guided two-layer flow in
CP1_AGENTIC.md: run cp1_agent.py under the registered capafy:kosuke browser
lease, inspect each screenshot, then choose the next browser primitive.
"""
import sys


MESSAGE = (
    "drive_cp1.py is retired: it hardcoded localhost:9222 and ran the full CP1 "
    "form as one unchecked DOM sequence. Use CP1_AGENTIC.md and scripts/cp1_agent.py "
    "under skills/browser/with-browser.sh capafy:kosuke instead."
)


def main():
    print(MESSAGE, file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
