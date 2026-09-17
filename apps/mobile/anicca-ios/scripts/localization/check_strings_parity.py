#!/usr/bin/env python3
"""
Fail CI if localization keys drift across languages.

We enforce that:
- All `Localizable.strings` files share the exact same key set as `en.lproj`.
- All `InfoPlist.strings` files share the exact same key set as `en.lproj`.

This makes “forgot to localize one language” a CI failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]  # /workspace/aniccaios
APP_RESOURCES = ROOT / "aniccaios" / "Resources"

SUPPORTED_LOCALES = ["en", "ja", "de", "fr", "es", "pt-BR"]

PAIR_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*=\s*"(?P<value>(?:\\.|[^"])*)"\s*;\s*$')


def parse_strings_file(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        raise FileNotFoundError(str(path))
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("/*") or line.startswith("//"):
            continue
        m = PAIR_RE.match(raw)
        if m:
            keys.add(m.group("key"))
    return keys


def check_table(filename: str) -> int:
    base_path = APP_RESOURCES / "en.lproj" / filename
    base_keys = parse_strings_file(base_path)
    if not base_keys:
        print(f"[localization] ERROR: base file has no parsed keys: {base_path}", file=sys.stderr)
        return 1

    exit_code = 0
    for locale in SUPPORTED_LOCALES:
        file_path = APP_RESOURCES / f"{locale}.lproj" / filename
        keys = parse_strings_file(file_path)
        missing = sorted(base_keys - keys)
        extra = sorted(keys - base_keys)
        if missing or extra:
            exit_code = 1
            print(f"[localization] Key drift detected for {locale} {filename}", file=sys.stderr)
            if missing:
                print(f"  - missing ({len(missing)}): {missing[:50]}", file=sys.stderr)
            if extra:
                print(f"  - extra ({len(extra)}): {extra[:50]}", file=sys.stderr)
    return exit_code


def main() -> int:
    if not APP_RESOURCES.exists():
        print(f"[localization] ERROR: Resources dir missing: {APP_RESOURCES}", file=sys.stderr)
        return 2

    rc = 0
    for fname in ("Localizable.strings", "InfoPlist.strings"):
        rc = max(rc, check_table(fname))

    if rc == 0:
        print("[localization] OK: localization key parity (Localizable/InfoPlist)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

