#!/usr/bin/env python3
"""
build_config.py — parse a LISTING.md (+ icon) into the JSON config that
cp1_agent.py consumes. Reads everything from the LISTING so the browser URL remains
in its separate protected file.

Usage: build_config.py <LISTING.md> <icon_path> [out.json]
LISTING.md must contain:
  header line with "Primary Model: <model>" and "category: <cat> ... tags: a, b, c"
  a pricing table:  | cycle | price | cap | trial |  rows (trial = "No Free Trial" only)
  ## Title / ## shortDescription / ## welcomeMessage / ## detailedDescription
test_input is extracted from the welcomeMessage "Example:" line.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path


NO_FREE_TRIAL = re.compile(r"no[\s_-]+free[\s_-]+trial", re.I)
MODEL_IDS = {
    "Claude Sonnet 4.6": "anthropic/claude-sonnet-4.6",
    "DeepSeek V4.1 Flash": "deepseek/deepseek-v4.1-flash",
}
HOSTED_MAX_TOKENS = {"Claude Sonnet 4.6": 128000, "DeepSeek V4.1 Flash": 8192}


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__.split("LISTING.md must contain:", 1)[0].strip(), file=sys.stderr)
        return 2
    listing, icon = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    L = open(listing, encoding="utf-8").read()

    title = re.search(r"## Title\n(.+)", L).group(1).strip()
    short = re.search(r"## shortDescription\n(.+?)\n## welcomeMessage", L, re.S).group(1).strip()
    welcome = re.search(r"## welcomeMessage\n(.+?)\n## detailedDescription", L, re.S).group(1).strip()
    detailed = re.split(r"\n## detailedDescription[^\n]*\n", L)[-1].strip()

    model_m = re.search(r"Primary Model:\s*([^·\n]+)", L)
    model = model_m.group(1).strip() if model_m else "Claude Sonnet 4.6"
    model_id = MODEL_IDS.get(model)
    if model_id is None:
        print(f"ERROR: unsupported hosted model: {model}", file=sys.stderr)
        return 2
    cat_m = re.search(r"category:\s*([^\(·\n]+)", L)
    category = cat_m.group(1).strip() if cat_m else "ライティング"
    tags_m = re.search(r"tags:\s*([^\n]+)", L)
    tags = [t.strip() for t in tags_m.group(1).split(",")][:3] if tags_m else []

    # pricing table rows
    plans = []
    for row in re.findall(r"\|\s*(day|week|month)\s*\|\s*\$?([0-9.]+)\s*\|\s*([0-9]+)\s*\|\s*([^|]+)\|", L, re.I):
        cyc, price, cap, trial = row
        if not NO_FREE_TRIAL.fullmatch(trial.strip()):
            print(
                f"ERROR: free trials are disabled; {cyc} plan trial must be No Free Trial",
                file=sys.stderr,
            )
            sys.exit(2)
        plans.append({"cycle": cyc.lower(), "price": price, "cap": cap,
                      "trial": None})
    if not plans:
        print("ERROR: no pricing rows parsed from LISTING", file=sys.stderr); sys.exit(2)

    ex = re.search(r'Example:\s*"?([^"\n]+)"?', welcome)
    test_input = ex.group(1).strip() if ex else "test input"

    cfg = {
        "title": title, "short": short, "welcome": welcome,
        "detailed": detailed, "privacy_url": "https://aniccaai.com/privacy",
        "support_email": "contact@aniccaai.com", "tags": tags, "category": category,
        "icon": icon, "model": model, "model_id": model_id,
        "max_tokens": HOSTED_MAX_TOKENS[model], "provider": "openrouter.ai",
        "test_input": test_input, "plans": plans,
    }
    js = json.dumps(cfg, ensure_ascii=False)
    if out:
        output = Path(out).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(output.parent, 0o700)
        fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
        temp_path = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(js)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, output)
            os.chmod(output, 0o600)
            dir_fd = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
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
        print(f"config → {out} | title={len(title)} short={len(short)} plans={len(plans)} cat={category} model={model}")
    else:
        print(js)


if __name__ == "__main__":
    raise SystemExit(main())
