#!/usr/bin/env python3
"""
build_config.py — parse a LISTING.md (+ icon) into the JSON config that
cp1_agent.py consumes. Reads everything from the LISTING so the browser URL remains
in its separate protected file.

Usage: build_config.py <LISTING.md> <icon_path> [out.json]
LISTING.md must contain:
  header line with "Primary Model: <model>" and "category: <cat> ... tags: a, b, c"
  a pricing table:  | cycle | price | cap | trial |  rows (trial = "No Free Trial" or
    "Free Trial <hours>h / <N> requests")
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
FREE_TRIAL = re.compile(r"free[\s_-]+trial\s+(\d+)\s*h\s*/\s*(\d+)\s*requests?", re.I)
MODEL_IDS = {
    "Claude Sonnet 4.6": "anthropic/claude-sonnet-4.6",
    "DeepSeek V4.1 Flash": "deepseek/deepseek-v4.1-flash",
}
# E (2026-09-28): Hook Lab (agent 8123079349, Sonnet-hosted) measured ~45k input
# tokens/request. This repo has no visibility into Capafy's server-side system
# prompt/history assembly, but a 128000 max_tokens ceiling lets one completion grow
# huge and then gets echoed back into the next turn's history on a multi-turn card,
# compounding input size run over run. Existing online agents (Hook Lab included)
# keep their already-published CP2 config; only NEW skills get the lower ceiling.
HOSTED_MAX_TOKENS = {"Claude Sonnet 4.6": 8192, "DeepSeek V4.1 Flash": 8192}


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

    cat_m = re.search(r"category:\s*([^\(·\n]+)", L)
    category = cat_m.group(1).strip() if cat_m else "ライティング"
    tags_m = re.search(r"tags:\s*([^\n]+)", L)
    tags = [t.strip() for t in tags_m.group(1).split(",")][:3] if tags_m else []

    # A "download" pricing row (one-time fee, no hosted LLM/CP2) is mutually
    # exclusive with the subscription day/week/month table below — Capafy's
    # Download mode has no Primary Model and no cap/trial (verified 2026-09-28
    # via publish-remote-status on agent 3332784488: agent_type=download,
    # is_confirmed_config_keys=false — CP2 is skipped entirely for downloads).
    download_m = re.search(r"\|\s*download\s*\|\s*\$?([0-9.]+)\s*\|", L, re.I)

    if download_m:
        model = model_id = max_tokens = None
        one_time_fee = download_m.group(1)
        plans = []
    else:
        model_m = re.search(r"Primary Model:\s*([^·\n]+)", L)
        model = model_m.group(1).strip() if model_m else "Claude Sonnet 4.6"
        model_id = MODEL_IDS.get(model)
        if model_id is None:
            print(f"ERROR: unsupported hosted model: {model}", file=sys.stderr)
            return 2
        one_time_fee = None
        plans = []

    # pricing table rows (subscription mode only). "year" is the exact
    # Capafy billing `cycleType` value (verified live 2026-09-29 in market
    # billings data, e.g. agent 5133292529's `cycleType: "year"` row) — not a
    # display label we invented.
    for row in ([] if download_m else re.findall(r"\|\s*(day|week|month|year)\s*\|\s*\$?([0-9.]+)\s*\|\s*([0-9]+)\s*\|\s*([^|]+)\|", L, re.I)):
        cyc, price, cap, trial = row
        trial = trial.strip()
        trial_match = FREE_TRIAL.fullmatch(trial)
        if trial_match:
            trial_value = {"hours": int(trial_match.group(1)), "requests": int(trial_match.group(2))}
        elif NO_FREE_TRIAL.fullmatch(trial):
            trial_value = None
        else:
            print(
                f"ERROR: {cyc} plan trial must be 'No Free Trial' or "
                f"'Free Trial <hours>h / <N> requests': {trial!r}",
                file=sys.stderr,
            )
            sys.exit(2)
        plans.append({"cycle": cyc.lower(), "price": price, "cap": cap,
                      "trial": trial_value})
    if not download_m and not plans:
        print("ERROR: no pricing rows parsed from LISTING", file=sys.stderr); sys.exit(2)

    ex = re.search(r'Example:\s*"?([^"\n]+)"?', welcome)
    test_input = ex.group(1).strip() if ex else "test input"

    cfg = {
        "title": title, "short": short, "welcome": welcome,
        "detailed": detailed, "privacy_url": "https://aniccaai.com/privacy",
        "support_email": "contact@aniccaai.com", "tags": tags, "category": category,
        "icon": icon, "model": model, "model_id": model_id,
        "max_tokens": HOSTED_MAX_TOKENS[model] if model else None,
        "provider": "openrouter.ai" if model else None,
        "test_input": test_input, "plans": plans,
        "pricing_mode": "download" if download_m else "subscription",
        "one_time_fee": one_time_fee,
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
