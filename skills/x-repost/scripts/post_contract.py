#!/usr/bin/env python3
"""Fail-closed contracts applied after model writing and before publishing."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]")
KANA = re.compile(r"[\u3040-\u30ff\uff66-\uff9f]")
LATIN = re.compile(r"[A-Za-z]")


def language_matches(language: str, text: str,
                     detected_language: str | None = None) -> bool:
    if detected_language is not None and detected_language != language:
        return False
    japanese_count = len(JAPANESE.findall(text))
    latin_count = len(LATIN.findall(text))
    japanese_dominant = bool(KANA.search(text)) and japanese_count >= max(2, latin_count // 2)
    return japanese_dominant if language == "ja" else (
        language == "en" and japanese_count == 0 and latin_count > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=("en", "ja"), required=True)
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--detected-language")
    args = parser.parse_args()
    text = args.text_file.read_text(encoding="utf-8").strip()
    matched = bool(text) and language_matches(
        args.language, text, args.detected_language)
    print(json.dumps({"language": args.language,
                      "detected_language": args.detected_language,
                      "matched": matched}, sort_keys=True))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
