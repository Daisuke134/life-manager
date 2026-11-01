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
import runpy
import subprocess
import sys
import urllib.request
import time
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
TT_ID = os.environ.get("CAPAFY_REEL_TT_INTEGRATION", "cmvc98itr1d3clu0yf8vy3dgx")    # tiktok: @hooklab.capafy
# TikTok reaches non-followers (our 1-follower slideshow account: 3,158 views/7d) while X and
# IG Hook Lab reach ~0, so reels go to TikTok too -- only after anicca-warmup-flip marks the
# new account live (7-day warm-up; fresh-account posting got spam-blocked before).
WARMUP_STATE = Path(os.environ.get("CAPAFY_REEL_WARMUP_STATE", str(
    Path.home() / ".local/state/life-manager/warmup-flip-daily/state/postiz-integrations.json")))
JST = dt.timezone(dt.timedelta(hours=9))
# Accounts limited to one post per Tokyo day (video and slideshow count together).
DAILY_CAP_INTEGRATIONS = {TT_ID}
ACCOUNT_DAILY_STATE = Path(os.environ.get("CAPAFY_REEL_ACCOUNT_DAILY_STATE", str(
    Path.home() / ".local/state/life-manager/capafy-reel/account-daily.json")))


def _tokyo_day(slot_iso: str) -> str:
    when = dt.datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
    return when.astimezone(JST).date().isoformat()


def _account_day_taken(integration: str, slot_iso: str) -> str | None:
    if integration not in DAILY_CAP_INTEGRATIONS:
        return None
    try:
        data = json.loads(ACCOUNT_DAILY_STATE.read_text())
    except (OSError, ValueError):
        data = {}
    return (data.get(integration) or {}).get(_tokyo_day(slot_iso))


def _claim_account_day(integration: str, slot_iso: str, label: str) -> None:
    if integration not in DAILY_CAP_INTEGRATIONS:
        return
    try:
        data = json.loads(ACCOUNT_DAILY_STATE.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault(integration, {})[_tokyo_day(slot_iso)] = label
    ACCOUNT_DAILY_STATE.parent.mkdir(parents=True, exist_ok=True)
    _durable_write(ACCOUNT_DAILY_STATE, json.dumps(data, sort_keys=True) + "\n")


SETTINGS = {
    "x": {"__type": "x", "who_can_reply_post": "everyone", "made_with_ai": True, "paid_partnership": False},
    "ig": {"__type": "instagram-standalone", "post_type": "post", "is_trial_reel": False, "collaborators": []},
    "tt": {"__type": "tiktok", "privacy_level": "PUBLIC_TO_EVERYONE", "duet": False, "stitch": False, "comment": True,
           "autoAddMusic": "yes", "brand_content_toggle": False, "brand_organic_toggle": False,
           "video_made_with_ai": True, "content_posting_method": "DIRECT_POST"},
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


SLOT_TIMES = {1: ("13:00", "17:00", "14:00", "20:00"), 2: ("23:00", "11:00", "01:00", "08:00")}  # (ig, x, tt, tc) UTC


def pick_niche(day: dt.date, slot: int = 1) -> dict:
    return NICHES[(day.toordinal() + 7 * (slot - 1)) % len(NICHES)]


def slots(day: dt.date, slot: int = 1) -> dict:
    ig, x, tt, tc = SLOT_TIMES[slot]
    return {"ig": f"{day.isoformat()}T{ig}:00.000Z", "x": f"{day.isoformat()}T{x}:00.000Z",
            "tt": f"{day.isoformat()}T{tt}:00.000Z", "tc": f"{day.isoformat()}T{tc}:00.000Z"}


def render_carousel(slug: str, spec: dict) -> list[Path]:
    """Six 1080x1920 JPEG slides for a TikTok photo post (slideshows reach non-followers:
    our 1-follower slideshow account drew 3,158 views/7d): pain hook, promise, 3 hooks, recap."""
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    import textwrap  # noqa: PLC0415
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    out_dir = BASE / slug / "carousel"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = [(spec["hook_a"], spec["hook_b"]), (spec["title"], "Hooks Hook Lab wrote. Swipe.")]
    pages += [(quote, f"{label} hook · on screen: {onscreen}") for label, quote, onscreen in spec["cards"]]
    pages.append((spec["title"], " / ".join(onscreen for _label, _quote, onscreen in spec["cards"])))
    paths = []
    for i, (head, sub) in enumerate(pages, 1):
        img = Image.new("RGB", (1080, 1920), (14, 14, 18))
        d = ImageDraw.Draw(img)
        y = 620
        for row in textwrap.wrap(head, 18):
            d.text((540, y), row, font=ImageFont.truetype(bold, 92), fill=(255, 196, 0), anchor="mm")
            y += 112
        y += 60
        for row in textwrap.wrap(sub, 30):
            d.text((540, y), row, font=ImageFont.truetype(bold, 52), fill=(245, 245, 245), anchor="mm")
            y += 70
        d.text((540, 1800), f"{i}/6", font=ImageFont.truetype(bold, 40), fill=(150, 150, 160), anchor="mm")
        path = out_dir / f"slide-{i}.jpg"
        img.save(path, "JPEG", quality=90)
        paths.append(path)
    return paths


def tiktok_live() -> bool:
    try:
        rows = json.loads(WARMUP_STATE.read_text()).get("integrations") or []
    except (OSError, ValueError):
        return False
    return any(r.get("id") == TT_ID and r.get("active") and r.get("warmup_phase") == "live" for r in rows)


def caption(spec: dict) -> str:
    """Caption built only from this post's own content: no fixed promo sentence or CTA.

    TikTok flagged identical promo text across posts as spam (2026-11-01), so every line
    here comes from the spec of this one post.
    """
    lines = [f"{spec['hook_a']} {spec['hook_b']}", spec["title"]]
    lines += [f"{label}: {quote}" for label, quote, _onscreen in spec.get("cards") or []]
    return "\n\n".join(lines)


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


def _generate_text(prompt: str) -> str:
    repo = HERE.parents[3]
    evidence = (Path(os.environ.get("CAPAFY_REEL_RUN_DIR", BASE))
                / "agent-runner-evidence" / "text" / uuid.uuid4().hex)
    evidence.mkdir(parents=True, mode=0o700)
    env = {key: value for key, value in os.environ.items() if key not in {
        "LM_POSTIZ_API_KEY", "LIFE_MANAGER_RESULT_HINT_PATH", "LIFE_MANAGER_OCCURRENCE_ID",
    }}
    command = [
        sys.executable, str(repo / "runtime/agent-runner/agent_runner.py"),
        "--task-class", "composition-agent", "--prompt-stdin",
        "--schema", str(repo / "skills/writer-agent/runtime/shared-agent-output.schema.json"),
        "--evidence-dir", str(evidence), "--task-label", "capafy-reel-text",
        "--loop", "capafy-reel-daily", "--workdir", str(repo),
        "--read-only", "--timeout-seconds", "600",
    ]
    request = ("Complete only the text task below. Do not use tools, modify files, or publish. "
               "Return the schema object with the full answer in text. "
               "If the task asks for JSON, encode that JSON as a string in text.\n\nTASK:\n" + prompt)
    done = subprocess.run(command, input=request, capture_output=True, text=True, env=env)
    if done.returncode:
        raise RuntimeError(f"capafy_reel_text_failed:rc={done.returncode}:evidence={evidence}")
    try:
        summary = json.loads((evidence / "summary.json").read_text())
        if summary["status"] != "success":
            raise ValueError("runner did not succeed")
        result_path = Path(summary["result_path"]).resolve(strict=True)
        result_path.relative_to(evidence.resolve())
        parse_result = runpy.run_path(
            str(repo / "skills/writer-agent/runtime/shared-model-runner.py"))["parse_contract_result"]
        result = parse_result(result_path.read_text())
        if (not isinstance(result, dict) or set(result) != {"text"}
                or not isinstance(result["text"], str) or not result["text"].strip()):
            raise ValueError("invalid text envelope")
    except (OSError, KeyError, TypeError, ValueError):
        raise RuntimeError(f"capafy_reel_text_result_invalid:evidence={evidence}") from None
    return result["text"]


WINNER_OPENERS = Path.home() / ".local/state/life-manager/marketing/winner-openers.json"
# Shorts tabs of creator-economy channels studied in creative/winner-patterns.md (yt-dlp search
# returns long-form only, measured 2026-10-18).
WINNER_SOURCES = ("https://www.youtube.com/@JadeBeason/shorts", "https://www.youtube.com/@VanessaLau/shorts",
                  "https://www.youtube.com/@aliabdaal/shorts")


def top_short_titles(entries: list, n: int = 15) -> list:
    """Titles of the most-viewed <=60 s videos: what currently stops the scroll."""
    shorts = [e for e in entries if (e.get("duration") or 0) <= 60 and e.get("title")
              and not e["title"].upper().startswith("AD |")]
    return [e["title"] for e in sorted(shorts, key=lambda e: -(e.get("view_count") or 0))[:n]]


def winner_openers() -> list:
    """Weekly yt-dlp metadata refresh (no video download) of top short-video titles; the
    reel copies the winners' opener structure (Dais 2026-10-16: copy what top creators do)."""
    try:
        cached = json.loads(WINNER_OPENERS.read_text())
        if (dt.date.today() - dt.date.fromisoformat(cached["fetched_at"])).days < 7:
            return cached["titles"]
    except (OSError, ValueError, KeyError):
        cached = None
    entries = []
    for source in WINNER_SOURCES:
        try:
            out = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--playlist-end", "30", source],
                                 capture_output=True, text=True, timeout=120).stdout
            entries += json.loads(out).get("entries") or []
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    titles = top_short_titles(entries)
    if titles:
        WINNER_OPENERS.parent.mkdir(parents=True, exist_ok=True)
        WINNER_OPENERS.write_text(json.dumps({"fetched_at": dt.date.today().isoformat(), "titles": titles}, indent=1))
        return titles
    return (cached or {}).get("titles") or []


def hook_lab_output(niche: dict) -> str:
    openers = winner_openers()
    reference = ("\nCurrently top-viewed short-video openers (study their structure; never copy their words):\n- "
                 + "\n- ".join(openers[:10])) if openers else ""
    return _generate_text(f"{HOOK_LAB_SKILL.read_text()}\n\n---\nUser request: Format: Instagram Reel, 30 seconds, "
                   f"direct tone. Topic: a {niche['topic']} for creators in that niche.{reference}")


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
        raw = _generate_text(prompt)
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


UPLOAD_ATTEMPTS = 3
UPLOAD_RETRY_STATUS = {502, 503, 504}


def _upload(key: str, data: bytes, boundary: str) -> dict:
    """POST /upload, retrying only transient gateway errors.

    An upload only returns a media id, so repeating it creates no post; /posts is never retried.
    """
    last = None
    for attempt in range(UPLOAD_ATTEMPTS):
        try:
            return _req(key, f"{API}/upload", data,
                        {"Content-Type": f"multipart/form-data; boundary={boundary}"}, "POST")
        except urllib.error.HTTPError as exc:
            if exc.code not in UPLOAD_RETRY_STATUS:
                raise
            last = exc
            if attempt + 1 < UPLOAD_ATTEMPTS:
                time.sleep(5 * (attempt + 1))
    raise last


def _durable_write(path: Path, text: str) -> None:
    with open(path, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def schedule(slug: str, spec: dict, day: dt.date, key: str, nets: tuple = ("ig", "x", "tt", "tc"), *,
             run_dir: Path | None = None, existing_fn=None, slot: int = 1) -> dict:
    mp4 = BASE / slug / "renders-v2" / "video.mp4"
    out = {}
    for net, integration in (("ig", IG_ID), ("x", X_ID), ("tt", TT_ID), ("tc", TT_ID)):
        if net not in nets:
            continue
        if net in ("tt", "tc") and not tiktok_live():
            out[net] = "warmup_skip"
            continue
        receipt = BASE / slug / f"{net}-receipts-v3.jsonl"
        if receipt.exists():
            out[net] = "already_scheduled"
            continue
        if _account_day_taken(integration, slots(day, slot)[net]):
            out[net] = "daily_cap_skip"
            continue
        found = existing_fn(net, slots(day, slot)[net]) if existing_fn else None
        if found:  # provider already has this slot (earlier crash after create): record, never re-create
            receipt.write_text(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "slug": slug,
                                           "readback_existing_post": found, "scheduled_for": slots(day, slot)[net]}) + "\n")
            _claim_account_day(integration, slots(day, slot)[net], f"{slug}:{net}")
            out[net] = {"existing": found}
            continue
        if run_dir is not None:  # durable pre-dispatch marker for capafy_reel_fence_reconcile
            _durable_write(run_dir / f"dispatch-{net}{'' if slot == 1 else f'-s{slot}'}.json",
                           json.dumps({"slug": slug, "net": net, "slot": slots(day, slot)[net]}) + "\n")
        assets = render_carousel(slug, spec) if net == "tc" else [mp4]
        uploads = []
        for asset in assets:
            bnd = uuid.uuid4().hex
            kind = "image/jpeg" if asset.suffix == ".jpg" else "video/mp4"
            data = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{slug}-{asset.name}\"\r\n"
                    f"Content-Type: {kind}\r\n\r\n").encode() + asset.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
            uploads.append(_upload(key, data, bnd))
        up = uploads[0]
        settings = ({**SETTINGS["tt"], "title": spec["hook_a"]} if net in ("tt", "tc") else SETTINGS[net])
        payload = {"type": "schedule", "date": slots(day, slot)[net], "shortLink": False, "tags": [],
                   "posts": [{"integration": {"id": integration},
                              "value": [{"content": caption(spec),
                                         "image": [{"id": u["id"], "path": u["path"]} for u in uploads]}],
                              "settings": settings}]}
        cr = _req(key, f"{API}/posts", json.dumps(payload).encode(), {"Content-Type": "application/json"}, "POST")
        rec = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "slug": slug, "asset": str(mp4), "upload": up,
               "create": cr, "scheduled_for": slots(day, slot)[net], "integration": integration}
        receipt.write_text(json.dumps(rec) + "\n")
        _claim_account_day(integration, slots(day, slot)[net], f"{slug}:{net}")
        out[net] = cr
    return out


def run(day: dt.date, dry_run: bool = False, nets: tuple = ("ig", "x", "tt", "tc"), run_dir: Path | None = None,
        slot: int = 1) -> dict:
    niche = pick_niche(day, slot)
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
    result = {"slug": slug, "niche": niche["key"], "slots": slots(day, slot)}
    if not dry_run:
        from capafy_reel_fence_reconcile import postiz_posts_at  # noqa: PLC0415
        result["scheduled"] = schedule(slug, spec, day, os.environ["LM_POSTIZ_API_KEY"], nets,
                                       run_dir=run_dir, existing_fn=postiz_posts_at, slot=slot)
    return result


if __name__ == "__main__":
    nets = tuple(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else ("ig", "x", "tt", "tc")
    run_dir = Path(os.environ["CAPAFY_REEL_RUN_DIR"]) if os.environ.get("CAPAFY_REEL_RUN_DIR") else None
    slot = int(sys.argv[sys.argv.index("--slot") + 1]) if "--slot" in sys.argv else 1
    print(json.dumps(run(dt.date.fromisoformat(sys.argv[1]), "--dry-run" in sys.argv, nets, run_dir, slot), default=str))
