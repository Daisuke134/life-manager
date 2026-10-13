#!/usr/bin/env python3
"""Cost-free image generation via the user's ChatGPT subscription (Dais 2026-10-08: image
generation must be cost-free via the ChatGPT subscription, not Gemini/fal).

Wraps ``~/.agents/skills/chatgpt-imagegen`` (see its SKILL.md): ``--backend auto`` tries the
logged-in ChatGPT browser first (no metered usage at all) and falls back to the headless
``codex`` backend (bills Codex-usage, not an API $ cost) only if the browser path is
unavailable. Either way this is $0 against our own metered spend, so callers record
``cost_usd "0"`` for a successful call.

Generate-only (no reference-image input, no native transparent background) - callers that need
chroma-key removal must still ask for a solid colour background in the prompt text and run their
own keying afterward (see line_sticker_static.py's ``_fit_sticker``). Callers that need
image-conditioned consistency (an existing character reference) keep Gemini as the explicit
fallback when this CLI fails or is not installed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CLI = Path.home() / ".agents/skills/chatgpt-imagegen/chatgpt-imagegen"
BROWSER_BIN_CANDIDATES = ("chrome-use", "agent-browser", "agent-browser-stealth", "abs")
BROWSER_CLOSE_TIMEOUT_SECONDS = 15


class ChatGptImageGenUnavailable(RuntimeError):
    pass


def run_session_name() -> str:
    """Keep imagegen browser tabs scoped to one Life Manager occurrence."""
    run_id = os.environ.get("LIFE_MANAGER_RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        run_id = f"manual-{os.getpid()}"
    return f"line-sticker-{run_id}"


def _close_run_browser_session(session: str) -> str | None:
    """Close only the named Line Sticker run session; return a sanitized failure code."""
    if not session.startswith("line-sticker-"):
        return "not_run_scoped"
    browser = next((found for name in BROWSER_BIN_CANDIDATES
                    if (found := shutil.which(name))), None)
    if browser is None:
        return "browser_binary_unavailable"
    try:
        result = subprocess.run(
            [browser, "close", "--session", session], capture_output=True, text=True,
            timeout=BROWSER_CLOSE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return "browser_close_timeout"
    except OSError:
        return "browser_close_error"
    return f"browser_close_exit_{result.returncode}" if result.returncode else None


def timeout_failure(session: str) -> ChatGptImageGenUnavailable:
    cleanup_failure = _close_run_browser_session(session)
    detail = f"; browser_session_cleanup_failed:{cleanup_failure}" if cleanup_failure else ""
    return ChatGptImageGenUnavailable(f"chatgpt-imagegen timed out{detail}")


def generate(prompt: str, *, size: str = "1024x1024", timeout: int = 280) -> Path:
    """Generate one PNG and return its path (caller owns deleting it). Raises
    ChatGptImageGenUnavailable on any failure (CLI missing, timeout, generation error) so callers
    can fall back to a paid backend without this exception looking like a generic bug."""
    if not CLI.is_file():
        raise ChatGptImageGenUnavailable("chatgpt-imagegen is not installed at " + str(CLI))
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out_path = Path(handle.name)
    handle.close()
    session = run_session_name()
    try:
        done = subprocess.run(
            [str(CLI), prompt, "-o", str(out_path), "--size", size, "--backend", "auto",
             "--quiet", "--timeout", str(timeout), "--session", session],
            capture_output=True, text=True, timeout=timeout + 30, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out_path.unlink(missing_ok=True)
        raise timeout_failure(session) from exc
    if done.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise ChatGptImageGenUnavailable(
            f"chatgpt-imagegen failed rc={done.returncode}: {done.stderr[-400:]}")
    return out_path


def log_fallback(task_label: str, exc: Exception) -> None:
    print(f"chatgpt_imagegen_fallback:{task_label}:{exc}", file=sys.stderr)
