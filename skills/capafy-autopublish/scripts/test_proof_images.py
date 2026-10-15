#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from proof_images import sections

MD = """# Verified demo

## Concrete input

```text
secret input
```

## Actual output

# Clip Lab: One-on-Ones

## Evidence boundary

- Supplied quote.

## Hook options

1. Your first one-on-one is not a status meeting.

## Caption

Hear the full conversation.
"""


def test_sections_use_only_the_actual_output_and_keep_headings():
    got = sections(MD)
    assert [h for h, _ in got] == ["Hook options", "Caption"]
    assert "secret input" not in json.dumps(got)
    assert got[0][1].startswith("1. Your first one-on-one")


def test_sections_cap_at_four_and_truncate_long_bodies():
    md = "## Actual output\n" + "\n".join(f"## S{i}\n\n" + "word " * 400 for i in range(6))
    got = sections(md)
    assert len(got) == 4 and all(len(b) <= 700 for _, b in got)


def test_build_config_lists_proof_images_from_env(tmp_path):
    proof = tmp_path / "proof"
    proof.mkdir()
    for n in ("proof-02.png", "proof-01.png", "notes.txt"):
        (proof / n).write_bytes(b"x")
    listing = Path(__file__).resolve().parents[2] / "capafy/catalog/podcast-clip-hook-lab/LISTING.md"
    out = tmp_path / "cfg.json"
    env = {**os.environ, "CAPAFY_PROOF_DIR": str(proof)}
    subprocess.run([sys.executable, str(Path(__file__).with_name("build_config.py")), str(listing), "icon.png", str(out)],
                   check=True, env=env, capture_output=True)
    cfg = json.loads(out.read_text())
    assert cfg["proof_images"] == [str(proof / "proof-01.png"), str(proof / "proof-02.png")]


def test_sources_without_actual_output_yield_no_cards():
    assert sections("# Case 1\n\n## Input\n\nComment: hi\n\n## Expected properties\n\n- warm") == []


def test_markdown_marks_and_table_rules_are_cleaned():
    md = "## Actual output\n## Blueprint\n\n| Time | Text |\n| --- | --- |\n| 0.0s | `HOOK` **now** |\n"
    assert sections(md) == [("Blueprint", "Time · Text\n0.0s · HOOK now")]
