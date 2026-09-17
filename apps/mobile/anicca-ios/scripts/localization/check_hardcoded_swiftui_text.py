#!/usr/bin/env python3
"""
Fail CI if we detect likely user-facing hardcoded SwiftUI Text("...") strings.

We intentionally allow:
- localization keys like `Text("common_continue")` (SwiftUI LocalizedStringKey)
- emoji-only strings (👍, 👎, 🤖, etc.)
- specific allowlisted literals (e.g. brand name)

We also strip `#if DEBUG ... #endif` blocks before scanning, because debug-only UI is out of scope.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]  # /workspace/aniccaios
APP_SRC = ROOT / "aniccaios"

# Extremely small allowlist — keep tight.
ALLOWED_LITERALS = {
    "Anicca",
}

SWIFT_TEXT_RE = re.compile(r'Text\("(?P<lit>(?:\\.|[^"\\])*)"\)')
SNAKE_KEY_RE = re.compile(r"^[a-z0-9_]+$")

# Remove debug blocks (simple, line-oriented).
DEBUG_BLOCK_RE = re.compile(r"(?ms)^[ \t]*#if[ \t]+DEBUG\b.*?^[ \t]*#endif\b")


def strip_debug_blocks(src: str) -> str:
    return DEBUG_BLOCK_RE.sub("", src)


def is_emoji_only(s: str) -> bool:
    # Allow strings with no letters/numbers/spaces (covers emojis + punctuation).
    return not re.search(r"[A-Za-z0-9\u3040-\u30FF\u4E00-\u9FFF\s]", s)


def is_likely_localization_key(s: str) -> bool:
    return bool(SNAKE_KEY_RE.match(s))


def should_flag_literal(s: str) -> bool:
    candidate = s
    # Strip Swift string interpolations (treat as placeholders).
    if "\\(" in candidate:
        candidate = re.sub(r"\\\([^)]*\)", "", candidate).strip()
        # If nothing remains after removing interpolations, it's not translatable copy.
        if not candidate:
            return False

    if candidate in ALLOWED_LITERALS:
        return False
    if is_emoji_only(candidate):
        return False
    if is_likely_localization_key(candidate):
        return False
    # Anything with spaces is almost certainly user-facing copy → must be localized.
    if " " in candidate:
        return True
    # Also flag Japanese/human text without spaces.
    if re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", candidate):
        return True
    # Flag if it contains lowercase letters (most human strings) and isn't a key.
    if re.search(r"[a-z]", candidate):
        return True
    return False


def main() -> int:
    if not APP_SRC.exists():
        print(f"[hardcoded] ERROR: app source dir missing: {APP_SRC}", file=sys.stderr)
        return 2

    offenders: list[tuple[str, str]] = []
    for path in APP_SRC.rglob("*.swift"):
        raw = path.read_text(encoding="utf-8")
        text = strip_debug_blocks(raw)
        for m in SWIFT_TEXT_RE.finditer(text):
            lit = m.group("lit")
            if should_flag_literal(lit):
                offenders.append((str(path.relative_to(ROOT)), lit))

    if offenders:
        print("[hardcoded] ERROR: Found likely hardcoded SwiftUI Text strings:", file=sys.stderr)
        for fp, lit in offenders[:100]:
            print(f"  - {fp}: Text(\"{lit}\")", file=sys.stderr)
        if len(offenders) > 100:
            print(f"  ... and {len(offenders) - 100} more", file=sys.stderr)
        return 1

    print("[hardcoded] OK: no hardcoded SwiftUI Text(\"...\") detected (production scope)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

