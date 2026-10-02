#!/usr/bin/env python3
"""Make 4 distinct, real example outputs for one catalog skill.

PromptBase rejects a submission whose 4 example outputs are identical
("Some of your example outputs are the same", live 2026-09-29 reels-hook-lab),
so repeating the one verified demonstration can never pass. This keeps that
verified pair as example 1 and actually runs the skill's SKILL.md through
Claude on 3 new buyer inputs for examples 2-4. Output is cached in
state/promptbase-examples/<slug>.json (releases are read-only) and never
regenerated once present.

Usage: gen_examples.py <catalog_dir>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_listing import _split_example  # noqa: E402

EXAMPLES_DIR = Path.home() / ".local/state/life-manager/state/promptbase-examples"
REPO_ROOT = Path(__file__).resolve().parents[4]
MODEL_RUNNER = REPO_ROOT / "skills" / "writer-agent" / "runtime" / "model-runner.sh"


def _claude(prompt: str, system: str = "You are a helpful assistant. Answer in natural, complete English.") -> str:
    runner = Path(os.environ.get("ARTICLE_MODEL_RUNNER", str(MODEL_RUNNER)))
    combined_prompt = (
        "## SYSTEM INSTRUCTIONS\n"
        + system.strip()
        + "\n\n## BUYER PROMPT\n"
        + prompt.strip()
        + "\n"
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="promptbase-", suffix=".txt") as handle:
        handle.write(combined_prompt)
        handle.flush()
        env = os.environ.copy()
        env.update({
            "ARTICLE_PROVIDER": "auto",
            "ARTICLE_RUN_ID": env.get("ARTICLE_RUN_ID", "promptbase-gen-examples"),
            "ARTICLE_MODEL_LOG": env.get("ARTICLE_MODEL_LOG", "/tmp/promptbase-model-runner.log"),
        })
        out = subprocess.run(
            [str(runner), "agent", "--prompt-file", handle.name],
            capture_output=True, text=True, timeout=600, check=True, cwd="/tmp", env=env,
        ).stdout.strip()
    if not out:
        raise RuntimeError("claude returned empty output")
    if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in out):
        raise RuntimeError("example output contains Japanese; operator config leaked")
    return out


def _clean(text: str) -> str:
    # PromptBase rejects square brackets inside example inputs.
    return text.replace("[", "(").replace("]", ")").strip()


def generate(catalog_dir: Path) -> list[dict]:
    target = EXAMPLES_DIR / f"{catalog_dir.name}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    skill_md = (catalog_dir / "SKILL.md").read_text(encoding="utf-8")
    first_in, first_out = _split_example(
        (catalog_dir / "evidence" / "verified-demonstration.md").read_text(encoding="utf-8"))
    raw = _claude(
        "Here is a skill a buyer uses:\n\n" + skill_md +
        "\n\nOne real buyer input was:\n" + first_in +
        "\n\nWrite 3 NEW realistic buyer inputs for this skill, each for a clearly different "
        "niche and situation, in the same style and length. Reply with a JSON array of 3 "
        "strings and nothing else.")
    inputs = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
    examples = [{"input": _clean(first_in), "output": first_out.strip()}]
    for text in inputs[:3]:
        text = _clean(str(text))
        output = _claude(text, system=skill_md)
        examples.append({"input": text, "output": output})
    if len({e["output"] for e in examples}) != 4:
        raise RuntimeError("examples are not 4 distinct outputs")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return examples


if __name__ == "__main__":
    print(len(generate(Path(sys.argv[1]))), "examples")
