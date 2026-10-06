#!/usr/bin/env python3
"""Pre-publish checks for target script and critic language code.

The pipeline checks script compatibility before calling the independent critic,
then requires the critic's exact ISO-639-1 result before publish. Latin-language
classification belongs to that critic; this helper does not guess from word lists.
"""

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
    """Check script evidence and exact critic-code agreement when provided.

    A missing code is the pre-critic script gate. A supplied code is the final
    independent language judgment and must match the requested target exactly.
    """
    if detected_language is not None and detected_language != language:
        return False
    japanese_count = len(JAPANESE.findall(text))
    latin_count = len(LATIN.findall(text))
    japanese_dominant = bool(KANA.search(text)) and japanese_count >= max(2, latin_count // 2)
    if language == "ja":
        return japanese_dominant
    if language != "en" or japanese_count or latin_count == 0:
        return False
    return True


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
