#!/usr/bin/env python3
"""Validate and atomically store one official Capafy edit-link response."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit


CAPAFY_HOST = "capafy.ai"
SHORT_REVIEW_HOST = "api.capafy.ai"
CREATE_AGENT_PATH = "/developer/createAgent"


def _fail(message: str) -> int:
    print(f"save_review_url: {message}", file=sys.stderr)
    return 1


def _is_edit_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or parts.fragment
        or not url
        or url != url.strip()
        or any(char.isspace() for char in url)
    ):
        return False
    if (
        parts.netloc == SHORT_REVIEW_HOST
        and re.fullmatch(r"/(?:E[1-9][0-9]{18}|[1-9][0-9]{19}|R[1-9][0-9]{18})", parts.path) is not None
        and not parts.query
        and url == f"https://{SHORT_REVIEW_HOST}{parts.path}"
    ):
        return True
    if parts.netloc.lower() != CAPAFY_HOST or parts.path != CREATE_AGENT_PATH:
        return False
    try:
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    keys = [key for key, _value in query]
    if len(set(keys)) != len(keys):
        return False
    values = dict(query)
    if set(keys) == {"source", "token", "page"}:
        return (
            len(query) == 3
            and values.get("source") == "temp-link"
            and re.fullmatch(r"[0-9]+", values.get("token", "")) is not None
            and values.get("page") == "edit"
        )
    if set(keys) == {"draftKey", "page"}:
        return (
            len(query) == 2
            and bool(values.get("draftKey", "").strip())
            and values.get("page") == "edit"
        )
    return False


def _write_atomic(path: Path, content: str) -> None:
    parent = path.parent
    directories = [parent]
    if parent.parent.name == "review-urls":
        directories.insert(0, parent.parent)
    for directory in directories:
        if directory.exists() and directory.is_symlink():
            raise ValueError("review URL directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
        dir_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read(), strict=False)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail(f"invalid refresh response JSON: {exc}")
    if not isinstance(payload, dict):
        return _fail("refresh response must be an object")
    expected_agent_id = str(args.agent_id or "").strip()
    response_agent_id = str(payload.get("agent_id") or "").strip()
    if not expected_agent_id or response_agent_id != expected_agent_id:
        return _fail("refresh response agent_id does not match the selected Agent")
    review_url = payload.get("review_url")
    if not isinstance(review_url, str) or not _is_edit_url(review_url):
        return _fail("refresh response review_url is not an exact Capafy page=edit URL")
    try:
        output = Path(args.output).expanduser()
        _write_atomic(output, review_url)
    except (OSError, ValueError) as exc:
        return _fail(f"could not store review URL securely: {exc}")
    print(f"EDIT_URL_FILE={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
