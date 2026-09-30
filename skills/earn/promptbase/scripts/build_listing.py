#!/usr/bin/env python3
"""Build a PromptBase listing payload from one Capafy catalog skill.

Pure text transform, no network/browser. Mirrors the structure of the live
"Hook Lab Win The First 3 Seconds" listing (https://promptbase.com/prompt/
hook-lab-win-the-first-3-seconds-2): item type Prompt, generation type Text,
model Claude 5 Sonnet, price $4.99, SKILL.md pasted as the prompt
instructions, and the catalog's verified-demonstration.md split into an
example input/output pair.

Catalog layout (skills/capafy/catalog/<slug>/):
  SKILL.md                          -> becomes the prompt instructions
  LISTING.md                        -> title/description source
  evidence/verified-demonstration.md -> example input/output source
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TITLE_MAX = 40
DESCRIPTION_MAX = 500
# Matches the live Hook Lab listing: Claude / 5 Sonnet / Text / $4.99 / one-time.
MODEL = "Claude"
MODEL_VERSION = "5 Sonnet"
GENERATION_TYPE = "Text"
PRICE_USD = 4.99
ITEM_TYPE = "Prompt"
# The one bracketed variable this builder itself injects into the prompt
# template (see build_listing() below). PromptBase auto-detects every
# "[...]" run in the template as a fillable variable and requires an example
# value for each one per example row before it will submit -- publish.py's
# _fill_step2 maps input boxes with this exact placeholder back to
# listing.example_input, and fills any *other* detected variable (e.g. a
# literal "[ADD: your number]" inside a catalog skill's own SKILL.md body)
# with a generic non-fabricated placeholder instead.
INPUT_VARIABLE_LABEL = "TOPIC / PRODUCT / CLIP IDEA"
TAGS = ["claude", "prompts"]


@dataclass(frozen=True)
class Listing:
    slug: str
    title: str
    description: str
    model: str
    model_version: str
    generation_type: str
    price_usd: float
    item_type: str
    tags: list
    prompt_instructions: str
    example_input: str
    example_output: str
    examples: list = None  # 4 distinct {"input","output"} from state/promptbase-examples/<slug>.json


def _slug_title(slug: str) -> str:
    """slug -> Title Case, matching Hook Lab's plain "Hook Lab Win The First 3
    Seconds" style (no punctuation, so it survives PromptBase's 40-char cap and
    URL-slug rules)."""
    words = slug.replace("-", " ").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def _extract_short_description(listing_md: str) -> str:
    m = re.search(
        r"^##\s*shortDescription\s*\n(.+?)(?=\n##\s|\Z)",
        listing_md,
        re.S | re.M,
    )
    if not m:
        raise ValueError("listing_md_missing_shortDescription")
    return " ".join(m.group(1).split())


def _extract_title(listing_md: str, fallback_slug: str) -> str:
    m = re.search(r"^##\s*Title\s*\n(.+?)(?=\n##\s|\Z)", listing_md, re.S | re.M)
    if m:
        return " ".join(m.group(1).split())
    return _slug_title(fallback_slug)


def _split_example(evidence_md: str) -> tuple[str, str]:
    """Split verified-demonstration.md into (example_input, example_output).

    Contract: a fenced ```text block under "## Concrete input" is the input;
    everything from "## Actual output" up to (not including) "## Verification
    notes" is the output — the notes are internal QA, not buyer-facing copy.
    """
    input_match = re.search(
        r"##\s*Concrete input\s*\n```(?:text)?\n(.*?)\n```",
        evidence_md,
        re.S,
    )
    if not input_match:
        raise ValueError("evidence_missing_concrete_input")
    example_input = input_match.group(1).strip()

    output_match = re.search(
        r"##\s*Actual output\s*\n(.*?)(?=\n##\s*Verification notes|\Z)",
        evidence_md,
        re.S,
    )
    if not output_match:
        raise ValueError("evidence_missing_actual_output")
    example_output = output_match.group(1).strip()
    return example_input, example_output


def build_listing(catalog_dir: Path) -> Listing:
    catalog_dir = Path(catalog_dir)
    slug = catalog_dir.name
    skill_md = (catalog_dir / "SKILL.md").read_text(encoding="utf-8")
    listing_md = (catalog_dir / "LISTING.md").read_text(encoding="utf-8")
    evidence_md = (catalog_dir / "evidence" / "verified-demonstration.md").read_text(
        encoding="utf-8"
    )

    title = _truncate(_extract_title(listing_md, slug), TITLE_MAX)
    description = _truncate(_extract_short_description(listing_md), DESCRIPTION_MAX)
    example_input, example_output = _split_example(evidence_md)

    # The live Hook Lab prompt template opens with "[VAR]: value" lines --
    # PromptBase renders those as the public "Example input" block, separate
    # from the SKILL.md body that follows. Reproduce that shape with this
    # catalog skill's own concrete input as the value.
    prompt_instructions = (
        f"[{INPUT_VARIABLE_LABEL}]: {example_input}\n\n{skill_md.strip()}"
    )

    return Listing(
        slug=slug,
        title=title,
        description=description,
        model=MODEL,
        model_version=MODEL_VERSION,
        generation_type=GENERATION_TYPE,
        price_usd=PRICE_USD,
        item_type=ITEM_TYPE,
        tags=list(TAGS),
        prompt_instructions=prompt_instructions,
        example_input=example_input,
        example_output=example_output,
        examples=_load_examples(catalog_dir, example_input, example_output),
    )


def _load_examples(catalog_dir: Path, example_input: str, example_output: str) -> list:
    path = Path.home() / ".local/state/life-manager/state/promptbase-examples" / f"{catalog_dir.name}.json"
    if path.exists():
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    return [{"input": example_input, "output": example_output}]


def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_dir", type=Path)
    args = parser.parse_args()
    listing = build_listing(args.catalog_dir)
    print(json.dumps(listing.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
