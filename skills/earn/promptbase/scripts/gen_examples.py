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
        # The shared runner validates the provider result as JSON.  Codex's
        # Responses API requires the top-level schema to be an object, while
        # example outputs themselves are natural text.  Put the text in one
        # object field and unwrap it here instead of weakening the runner
        # contract.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="promptbase-", suffix=".json") as schema:
            json.dump({
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            }, schema)
            schema.flush()
            env = os.environ.copy()
            env.update({
                "ARTICLE_PROVIDER": "auto",
                "ARTICLE_CODEX_OUTPUT_SCHEMA": schema.name,
                "ARTICLE_RUN_ID": env.get("ARTICLE_RUN_ID", "promptbase-gen-examples"),
                "ARTICLE_MODEL_LOG": env.get("ARTICLE_MODEL_LOG", "/tmp/promptbase-model-runner.log"),
            })
            out = subprocess.run(
                [str(runner), "agent", "--prompt-file", handle.name],
                capture_output=True, text=True, timeout=600, check=True, cwd="/tmp", env=env,
            ).stdout.strip()
    if not out:
        raise RuntimeError("claude returned empty output")
    try:
        decoded = json.loads(out)
    except json.JSONDecodeError:
        decoded = out
    if isinstance(decoded, dict) and isinstance(decoded.get("text"), str):
        out = decoded["text"]
    elif isinstance(decoded, str):
        out = decoded
    if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in out):
        raise RuntimeError("example output contains Japanese; operator config leaked")
    return out


def _clean(text: str) -> str:
    # PromptBase rejects square brackets inside example inputs.
    return text.replace("[", "(").replace("]", ")").strip()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _load_complete_cache(path: Path, first_example: dict) -> list[dict]:
    try:
        examples = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("examples_cache_invalid") from error
    if (
        not isinstance(examples, list)
        or len(examples) != 4
        or any(
            not isinstance(example, dict)
            or not isinstance(example.get("input"), str)
            or not example["input"].strip()
            or "[" in example["input"]
            or "]" in example["input"]
            or not isinstance(example.get("output"), str)
            or not example["output"].strip()
            for example in examples
        )
    ):
        raise RuntimeError("examples_cache_invalid")
    if (
        examples[0] != first_example
        or len({example["input"] for example in examples}) != 4
        or len({example["output"] for example in examples}) != 4
    ):
        raise RuntimeError("examples_cache_invalid")
    return examples


def _load_progress(path: Path, first_example: dict) -> tuple[list[str], list[dict]]:
    try:
        progress = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("examples_progress_invalid") from error
    inputs = progress.get("inputs") if isinstance(progress, dict) else None
    examples = progress.get("examples") if isinstance(progress, dict) else None
    if (
        not isinstance(progress, dict)
        or progress.get("schema_version") != 1
        or not isinstance(inputs, list)
        or len(inputs) != 3
        or any(not isinstance(value, str) or not value for value in inputs)
        or any("[" in value or "]" in value for value in inputs)
        or len(set(inputs)) != 3
        or first_example["input"] in inputs
        or not isinstance(examples, list)
        or not 1 <= len(examples) <= 4
        or examples[0] != first_example
    ):
        raise RuntimeError("examples_progress_invalid")
    for index, example in enumerate(examples[1:]):
        if (
            not isinstance(example, dict)
            or example.get("input") != inputs[index]
            or not isinstance(example.get("output"), str)
            or not example["output"].strip()
        ):
            raise RuntimeError("examples_progress_invalid")
    if len({example.get("output") for example in examples if isinstance(example, dict)}) != len(examples):
        raise RuntimeError("examples_progress_invalid")
    return inputs, examples


def generate(catalog_dir: Path) -> list[dict]:
    target = EXAMPLES_DIR / f"{catalog_dir.name}.json"
    progress_path = EXAMPLES_DIR / f"{catalog_dir.name}.partial.json"
    skill_md = (catalog_dir / "SKILL.md").read_text(encoding="utf-8")
    first_in, first_out = _split_example(
        (catalog_dir / "evidence" / "verified-demonstration.md").read_text(encoding="utf-8"))
    first_example = {"input": _clean(first_in), "output": first_out.strip()}
    if target.exists():
        return _load_complete_cache(target, first_example)
    if progress_path.exists():
        inputs, examples = _load_progress(progress_path, first_example)
    else:
        raw = _claude(
            "Here is a skill a buyer uses:\n\n" + skill_md +
            "\n\nOne real buyer input was:\n" + first_in +
            "\n\nWrite 3 NEW realistic buyer inputs for this skill, each for a clearly different "
            "niche and situation, in the same style and length. Reply with a JSON array of 3 "
            "strings and nothing else.")
        generated_inputs = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        inputs = [_clean(str(text)) for text in generated_inputs[:3]]
        if (
            len(inputs) != 3
            or any(not text for text in inputs)
            or len({first_example["input"], *inputs}) != 4
        ):
            raise RuntimeError("examples_require_3_distinct_inputs")
        examples = [first_example]
        _write_json(progress_path, {"schema_version": 1, "inputs": inputs, "examples": examples})

    for text in inputs[len(examples) - 1:]:
        output = _claude(text, system=skill_md)
        if output in {example["output"] for example in examples}:
            raise RuntimeError("examples are not 4 distinct outputs")
        examples.append({"input": text, "output": output})
        _write_json(progress_path, {"schema_version": 1, "inputs": inputs, "examples": examples})
    if len(examples) != 4 or len({e["output"] for e in examples}) != 4:
        raise RuntimeError("examples are not 4 distinct outputs")
    _write_json(target, examples)
    progress_path.unlink(missing_ok=True)
    return examples


if __name__ == "__main__":
    print(len(generate(Path(sys.argv[1]))), "examples")
