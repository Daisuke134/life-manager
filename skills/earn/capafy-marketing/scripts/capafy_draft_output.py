#!/usr/bin/env python3
"""Materialize a tool-free Codex JSON draft into wrapper-owned run files."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_response(path: Path, run_dir: Path) -> dict[str, str] | None:
    try:
        if path.parent != run_dir or path.is_symlink() or run_dir.is_symlink():
            return None
        directory = run_dir.stat()
        source = path.stat()
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) != 0o700
                or not stat.S_ISREG(source.st_mode) or source.st_uid != os.getuid()
                or source.st_nlink != 1 or stat.S_IMODE(source.st_mode) != 0o600
                or source.st_size > 200_000):
            return None
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if (not isinstance(value, dict)
            or set(value) != {"article_markdown", "x_caption"}
            or not isinstance(value["article_markdown"], str)
            or len(value["article_markdown"].strip()) < 500
            or not isinstance(value["x_caption"], str)
            or len(value["x_caption"].strip()) < 30):
        return None
    return value


def materialize(response_path: Path, run_dir: Path) -> bool:
    value = _read_response(response_path, run_dir)
    if value is None:
        return False
    for name, content in (("article-en.md", value["article_markdown"]),
                          ("x-caption.txt", value["x_caption"])):
        try:
            descriptor = os.open(
                run_dir / name,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content.rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materialize", choices=("materialize",))
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not materialize(args.response, args.run_dir):
        print("CAPAFY_DRAFT_OUTPUT=HELD")
        return 1
    print("CAPAFY_DRAFT_OUTPUT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
