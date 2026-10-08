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

import subprocess
import sys
import tempfile
from pathlib import Path

CLI = Path.home() / ".agents/skills/chatgpt-imagegen/chatgpt-imagegen"


class ChatGptImageGenUnavailable(RuntimeError):
    pass


def generate(prompt: str, *, size: str = "1024x1024", timeout: int = 280) -> Path:
    """Generate one PNG and return its path (caller owns deleting it). Raises
    ChatGptImageGenUnavailable on any failure (CLI missing, timeout, generation error) so callers
    can fall back to a paid backend without this exception looking like a generic bug."""
    if not CLI.is_file():
        raise ChatGptImageGenUnavailable("chatgpt-imagegen is not installed at " + str(CLI))
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out_path = Path(handle.name)
    handle.close()
    try:
        done = subprocess.run(
            [str(CLI), prompt, "-o", str(out_path), "--size", size, "--backend", "auto",
             "--quiet", "--timeout", str(timeout)],
            capture_output=True, text=True, timeout=timeout + 30, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out_path.unlink(missing_ok=True)
        raise ChatGptImageGenUnavailable(f"chatgpt-imagegen timed out: {exc}") from exc
    if done.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise ChatGptImageGenUnavailable(
            f"chatgpt-imagegen failed rc={done.returncode}: {done.stderr[-400:]}")
    return out_path


def log_fallback(task_label: str, exc: Exception) -> None:
    print(f"chatgpt_imagegen_fallback:{task_label}:{exc}", file=sys.stderr)
