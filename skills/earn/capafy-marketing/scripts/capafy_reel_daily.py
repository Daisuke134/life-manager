#!/usr/bin/env python3
"""One voiced Hook Lab reel per day, scheduled to X and Instagram through Postiz ($0).

Copies the 2026-10-11 batch that already ran (capafy-videos/hooklab-*): a real Hook Lab
output for one creator niche -> capafy_reel_variant (hooklab-02 HyperFrames template) ->
HyperFrames render -> capafy_reel_voice (edge-tts + music bed + visible first frame) ->
Postiz schedule on the same accounts and times as the live queue. Idempotent per date.
Usage: capafy_reel_daily.py YYYY-MM-DD [--dry-run]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capafy_reel_variant  # noqa: E402
import capafy_reel_voice  # noqa: E402

BASE = capafy_reel_variant.BASE
HOOK_LAB_SKILL = HERE.parents[2] / "capafy" / "catalog" / "hook-lab" / "SKILL.md"
API = "https://api.postiz.com/public/v1"
X_ID = os.environ.get("CAPAFY_REEL_X_INTEGRATION", "cmt4l2jld031tqp0y8qtyo983")      # x: sela | AI Tools
IG_ID = os.environ.get("CAPAFY_REEL_IG_INTEGRATION", "cmuuycr5402uzqw0yhanqggo9")    # instagram: Hook Lab by Anicca
SETTINGS = {
    "x": {"__type": "x", "who_can_reply_post": "everyone", "made_with_ai": True, "paid_partnership": False},
    "ig": {"__type": "instagram-standalone", "post_type": "post", "is_trial_reel": False, "collaborators": []},
}
NICHES = [
    {"key": "baking", "topic": "home baking Reel"}, {"key": "language", "topic": "language-learning TikTok"},
    {"key": "travel", "topic": "budget travel Reel"}, {"key": "productivity", "topic": "productivity TikTok"},
    {"key": "garden", "topic": "small-space gardening Reel"}, {"key": "photo", "topic": "phone photography TikTok"},
    {"key": "cars", "topic": "car detailing Reel"}, {"key": "parenting", "topic": "parenting tips TikTok"},
    {"key": "books", "topic": "book review Reel"}, {"key": "guitar", "topic": "beginner guitar TikTok"},
    {"key": "makeup", "topic": "everyday makeup Reel"}, {"key": "smallbiz", "topic": "small business TikTok"},
    {"key": "organize", "topic": "home organization Reel"}, {"key": "running", "topic": "beginner running TikTok"},
]
LIMITS = {"hook_a": 40, "hook_b": 40, "title": 34, "label": 14, "quote": 80, "onscreen": 36}


def pick_niche(day: dt.date) -> dict:
    return NICHES[day.toordinal() % len(NICHES)]


def slots(day: dt.date) -> dict:
    return {"ig": f"{day.isoformat()}T13:00:00.000Z", "x": f"{day.isoformat()}T17:00:00.000Z"}


def caption(spec: dict) -> str:
    return (f"{spec['hook_a']} {spec['hook_b']}\n\n"
            "Hook Lab turns one line about your video into 5+ first-3-second hooks, a timed script and a caption.\n\n"
            "Search \"Hook Lab\" on Capafy to try it.")


def validate_spec(spec: dict) -> None:
    """The hooklab-02 template is fixed-size; overflowing copy renders cut off."""
    for k in ("hook_a", "hook_b", "title"):
        if not spec.get(k) or len(spec[k]) > LIMITS[k]:
            raise ValueError(f"{k} missing or longer than {LIMITS[k]}: {spec.get(k)!r}")
    cards = spec.get("cards") or []
    if len(cards) != 3:
        raise ValueError(f"need exactly 3 cards, got {len(cards)}")
    for label, quote, onscreen in cards:
        for name, value in (("label", label), ("quote", quote), ("onscreen", onscreen)):
            if not value or len(value) > LIMITS[name]:
                raise ValueError(f"card {name} missing or longer than {LIMITS[name]}: {value!r}")


def _claude(prompt: str) -> str:
    claude = os.environ.get("ARTICLE_CLAUDE_BIN") or str(Path.home() / ".local/bin/claude")
    env = {**os.environ, "USER": os.environ.get("USER") or Path.home().name}
    return subprocess.run([claude, "-p"], input=prompt, check=True, capture_output=True, text=True, env=env,
                          timeout=600).stdout  # stdin: a prompt starting with "---" parses as a flag


def hook_lab_output(niche: dict) -> str:
    return _claude(f"{HOOK_LAB_SKILL.read_text()}\n\n---\nUser request: Format: Instagram Reel, 30 seconds, "
                   f"direct tone. Topic: a {niche['topic']} for creators in that niche.")


def spec_from_output(output: str, niche: dict) -> dict:
    prompt = (
        "From the Hook Lab output below, return ONLY a JSON object, no prose:\n"
        '{"noun": "<what the creator posts, e.g. baking video>", "hook_a": "Your <noun> is good.", '
        '"hook_b": "They swipe in 3 seconds.", "title": "<niche> <Reel|TikTok>: 3 hooks, e.g. Home baking Reel: 3 hooks", '
        '"cards": [["<one-word hook type>", "<a hook copied verbatim from the output>", "<on-screen text>"], x3]}\n'
        f"Limits (characters): hook_a {LIMITS['hook_a']}, title {LIMITS['title']}, card type {LIMITS['label']}, "
        f"hook {LIMITS['quote']}, on-screen {LIMITS['onscreen']}. Pick the three strongest hooks that fit.\n\n{output}")
    last = None
    for _ in range(2):
        raw = _claude(prompt)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            spec = json.loads(m.group(0) if m else raw)
            validate_spec(spec)
            return spec
        except (ValueError, json.JSONDecodeError) as exc:  # one retry with the reason
            last = exc
            prompt += f"\n\nYour previous answer was rejected: {exc}. Fix it."
    raise ValueError(f"no layout-safe spec for {niche['key']}: {last}")


def _req(key: str, url: str, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers={"Authorization": key, **(headers or {})}, method=method)
    body = urllib.request.urlopen(r, timeout=180).read()
    return json.loads(body) if body else {}


def schedule(slug: str, spec: dict, day: dt.date, key: str, nets: tuple = ("ig", "x")) -> dict:
    mp4 = BASE / slug / "renders-v2" / "video.mp4"
    out = {}
    for net, integration in (("ig", IG_ID), ("x", X_ID)):
        if net not in nets:
            continue
        receipt = BASE / slug / f"{net}-receipts-v3.jsonl"
        if receipt.exists():
            out[net] = "already_scheduled"
            continue
        bnd = uuid.uuid4().hex
        data = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{slug}.mp4\"\r\n"
                f"Content-Type: video/mp4\r\n\r\n").encode() + mp4.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
        up = _req(key, f"{API}/upload", data, {"Content-Type": f"multipart/form-data; boundary={bnd}"}, "POST")
        payload = {"type": "schedule", "date": slots(day)[net], "shortLink": False, "tags": [],
                   "posts": [{"integration": {"id": integration},
                              "value": [{"content": caption(spec), "image": [{"id": up["id"], "path": up["path"]}]}],
                              "settings": SETTINGS[net]}]}
        cr = _req(key, f"{API}/posts", json.dumps(payload).encode(), {"Content-Type": "application/json"}, "POST")
        rec = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "slug": slug, "asset": str(mp4), "upload": up,
               "create": cr, "scheduled_for": slots(day)[net], "integration": integration}
        receipt.write_text(json.dumps(rec) + "\n")
        out[net] = cr
    return out


def run(day: dt.date, dry_run: bool = False, nets: tuple = ("ig", "x")) -> dict:
    niche = pick_niche(day)
    slug = f"hooklab-d{day:%Y%m%d}-{niche['key']}"
    d = BASE / slug
    if not d.exists():
        output = hook_lab_output(niche)
        BASE.mkdir(parents=True, exist_ok=True)
        (BASE / f"{slug}.out").write_text(output)
        spec = spec_from_output(output, niche)
        capafy_reel_variant.make({**spec, "slug": slug, "source": f"{slug}.out"})
        (d / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    spec = json.loads((d / "spec.json").read_text())
    if not (d / "renders" / "video.mp4").exists():
        subprocess.run(["npx", "--yes", "hyperframes@0.8.140", "render", str(d), "-o", str(d / "renders" / "video.mp4")],
                       check=True, capture_output=True, timeout=1200)
    if not (d / "renders-v2" / "video.mp4").exists():
        capafy_reel_voice.build(slug)
    result = {"slug": slug, "niche": niche["key"], "slots": slots(day)}
    if not dry_run:
        result["scheduled"] = schedule(slug, spec, day, os.environ["LM_POSTIZ_API_KEY"], nets)
    return result


if __name__ == "__main__":
    nets = tuple(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else ("ig", "x")
    print(json.dumps(run(dt.date.fromisoformat(sys.argv[1]), "--dry-run" in sys.argv, nets), default=str))
