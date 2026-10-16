#!/usr/bin/env python3
"""Render one Mermaid body diagram into a PNG candidate X can show readably.

The Writer model used to render the body diagram itself (kroki or mermaid-cli).
2026-10-16 run 20261016-134344: kroki.io returned HTTP 500 for every diagram and
mmdc was not installed, so all four destinations stayed pending on
media-renderer-unavailable. This CLI is the one deterministic renderer:

  1. kroki POST (same request as _shared/embed-mermaid-substack.py, explicit UA
     because kroki 403s the bare urllib UA);
  2. mermaid.ink GET fallback (urlsafe base64, width=1300, white background).

A response counts only if it is a real PNG (magic bytes, >= MIN_PNG_BYTES,
decodes). Tall diagrams get transparent side margins via media_create_once's own
padding so the projected height at X's 587px column lands in 110-650px; too-flat
diagrams are refused because padding cannot make their text readable.

CLI: render_body_diagram.py --in <body-diagram.mmd> --out <candidate.png>
stdout on success: one JSON line. Exit 1 with every renderer's reason otherwise.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import media_create_once as media  # noqa: E402

MIN_PNG_BYTES = 2000  # below this, the renderer returned an error blob, not a diagram
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
UA = "Mozilla/5.0"
TIMEOUT = 40


def fetch_kroki(source: str) -> bytes:
    req = urllib.request.Request(
        "https://kroki.io/mermaid/png",
        data=source.encode("utf-8"),
        headers={"Content-Type": "text/plain", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_mermaid_ink(source: str) -> bytes:
    code = base64.urlsafe_b64encode(source.encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        f"https://mermaid.ink/img/{code}?type=png&bgColor=FFFFFF&width=1300",
        headers={"User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


RENDERERS = (("kroki", fetch_kroki), ("mermaid.ink", fetch_mermaid_ink))


def png_problem(data: bytes) -> str | None:
    if len(data) < MIN_PNG_BYTES:
        return f"{len(data)} bytes < {MIN_PNG_BYTES}, not a real diagram PNG"
    if not data.startswith(PNG_MAGIC):
        return "response is not a PNG (magic bytes missing)"
    from PIL import Image

    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception as exc:  # any decode failure means unusable bytes
        return f"PNG does not decode: {exc}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in", dest="source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    source = args.source.read_text(encoding="utf-8").strip()
    if not source:
        print(f"render_body_diagram FAILED: {args.source} is empty", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.{os.getpid()}.render")
    failures: list[str] = []
    for name, fetch in RENDERERS:
        try:
            data = fetch(source)
        except (OSError, ValueError) as exc:  # URLError/HTTPError/timeout are OSError
            failures.append(f"{name}: request failed: {exc}")
            continue
        problem = png_problem(data)
        if problem:
            failures.append(f"{name}: {problem}")
            continue
        temporary.write_bytes(data)
        media._pad_tall_body_candidate(temporary)
        from PIL import Image

        with Image.open(temporary) as image:
            width, height = image.size
        projected = round(media.X_RENDER_WIDTH * height / width, 2)
        if not media.X_BODY_MIN_HEIGHT <= projected <= media.X_BODY_MAX_HEIGHT:
            temporary.unlink()
            failures.append(
                f"{name}: projected height {projected}px at {media.X_RENDER_WIDTH}px is outside "
                f"{media.X_BODY_MIN_HEIGHT}-{media.X_BODY_MAX_HEIGHT}px; too flat, rewrite the "
                "source as one vertical flowchart TD chain of 4-6 nodes"
            )
            continue
        os.replace(temporary, args.out)
        print(json.dumps({
            "renderer": name,
            "out": str(args.out),
            "bytes": args.out.stat().st_size,
            "width": width,
            "height": height,
            "projected_height_at_587": projected,
        }))
        return 0
    print("render_body_diagram FAILED: " + "; ".join(failures), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
