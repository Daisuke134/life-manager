#!/usr/bin/env python3
import datetime as dt
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_daily import NICHES, caption, pick_niche, slots, validate_spec

SPEC = {"noun": "baking video", "hook_a": "Your baking video is good.", "hook_b": "They swipe in 3 seconds.",
        "title": "Baking Reel: 3 hooks",
        "cards": [["Mistake", "Your sourdough isn't flat because of the flour.", "The real reason it's flat"],
                  ["Question", "Why do bakery loaves rise higher than yours?", "Bakery loaves vs yours"],
                  ["Result", "One fold, one night, one perfect loaf.", "One fold. One night."]]}


def test_pick_niche_rotates_by_date_and_covers_every_niche():
    start = dt.date(2026, 10, 22)
    picked = {pick_niche(start + dt.timedelta(days=i))["key"] for i in range(len(NICHES))}
    assert picked == {n["key"] for n in NICHES}


def test_slots_match_existing_queue_times():
    assert slots(dt.date(2026, 10, 22)) == {"ig": "2026-10-22T13:00:00.000Z", "x": "2026-10-22T17:00:00.000Z",
                                           "tt": "2026-10-22T14:00:00.000Z",
                                           "tc": "2026-10-22T20:00:00.000Z"}


@pytest.fixture(autouse=True)
def _isolated_account_day_state(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    monkeypatch.setattr(m, "ACCOUNT_DAILY_STATE", tmp_path / "account-daily.json")


OTHER = {"noun": "guitar video", "hook_a": "Your guitar video is fine.", "hook_b": "Nobody hears the riff.",
         "title": "Guitar TikTok: 3 hooks",
         "cards": [["Mistake", "You tune after you hit record.", "Tune first"],
                   ["Question", "Why does your G chord buzz?", "The buzz fix"],
                   ["Result", "Three chords, one clean take.", "One clean take"]]}


def test_caption_is_built_only_from_this_posts_content():
    text = caption(SPEC)
    assert text.startswith("Your baking video is good. They swipe in 3 seconds.")
    assert "Capafy" not in text and "Search" not in text and "Hook Lab turns" not in text


def test_two_different_posts_share_no_caption_sentence():
    def sentences(t):
        return {s.strip() for s in re.split(r"[\n.!?]+", t) if s.strip()}
    assert not sentences(caption(SPEC)) & sentences(caption(OTHER))


def test_last_slide_has_no_fixed_cta(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    seen = []
    monkeypatch.setattr(m, "BASE", tmp_path)
    (tmp_path / "s").mkdir()
    import PIL.ImageDraw as ImageDraw
    real = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text",
                        lambda self, xy, text, *a, **k: (seen.append(text), real(self, xy, text, *a, **k))[1])
    m.render_carousel("s", SPEC)
    joined = " ".join(seen)
    assert "Capafy" not in joined and "Search" not in joined
    assert "Bakery loaves vs yours" in joined


def test_tiktok_account_gets_at_most_one_post_per_tokyo_day(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    for slug in ("a", "b", "c"):
        (tmp_path / slug / "renders-v2").mkdir(parents=True)
        (tmp_path / slug / "renders-v2" / "video.mp4").write_bytes(b"x")
    monkeypatch.setattr(m, "TT_ID", "tt-id")
    monkeypatch.setattr(m, "DAILY_CAP_INTEGRATIONS", {"tt-id"})
    monkeypatch.setattr(m, "WARMUP_STATE", _warmup(tmp_path, "live"))
    creates = []

    def fake_req(key, url, data=None, headers=None, method=None):
        if url.endswith("/upload"):
            return {"id": "u", "path": "https://u/1"}
        creates.append(url)
        return [{"postId": "p"}]

    monkeypatch.setattr(m, "_req", fake_req)
    day = dt.date(2026, 11, 2)
    first = m.schedule("a", SPEC, day, "k", ("tt", "tc"), slot=2)   # 10:00 and 17:00 JST
    assert first["tc"] == "daily_cap_skip" and len(creates) == 1
    second = m.schedule("b", SPEC, day, "k", ("tt",), slot=1)       # 23:00 JST, same Tokyo day
    assert second == {"tt": "daily_cap_skip"} and len(creates) == 1
    third = m.schedule("c", SPEC, dt.date(2026, 11, 3), "k", ("tt",), slot=2)
    assert len(creates) == 2 and third["tt"] != "daily_cap_skip"


def test_tokyo_day_crosses_midnight_utc():
    import capafy_reel_daily as m
    assert m._tokyo_day("2026-11-02T20:00:00.000Z") == "2026-11-03"
    assert m._tokyo_day("2026-11-02T01:00:00.000Z") == "2026-11-02"


def test_validate_spec_accepts_layout_safe_copy_and_rejects_overflow():
    validate_spec(SPEC)
    long = {**SPEC, "cards": [["Mistake", "x" * 120, "ok"]] + SPEC["cards"][1:]}
    with pytest.raises(ValueError):
        validate_spec(long)
    with pytest.raises(ValueError):
        validate_spec({**SPEC, "cards": SPEC["cards"][:2]})


def test_schedule_writes_dispatch_marker_before_upload_and_skips_existing(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    monkeypatch.setattr(m, "BASE", tmp_path)
    (tmp_path / "s" / "renders-v2").mkdir(parents=True)
    (tmp_path / "s" / "renders-v2" / "video.mp4").write_bytes(b"x")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    seen = []

    def fake_req(key, url, *a, **k):
        seen.append(("req", url, sorted(p.name for p in run_dir.iterdir())))
        raise RuntimeError("stop after first provider call")

    monkeypatch.setattr(m, "_req", fake_req)
    existing = {"ig": "ig-already", "x": None}
    with pytest.raises(RuntimeError):
        m.schedule("s", SPEC, dt.date(2026, 10, 29), "k", run_dir=run_dir, existing_fn=lambda net, slot: existing[net])
    assert (tmp_path / "s" / "ig-receipts-v3.jsonl").exists()  # existing post recorded, not re-created
    assert not (run_dir / "dispatch-ig.json").exists()
    assert seen and seen[0][2] == ["dispatch-x.json"]  # marker on disk before the first provider call


def test_second_slot_uses_other_times_and_a_different_niche():
    day = dt.date(2026, 10, 23)
    assert slots(day, slot=2) == {"ig": "2026-10-23T23:00:00.000Z", "x": "2026-10-23T11:00:00.000Z",
                                  "tt": "2026-10-23T01:00:00.000Z",
                                  "tc": "2026-10-23T08:00:00.000Z"}
    assert pick_niche(day, slot=2)["key"] != pick_niche(day)["key"]


def _video(tmp_path, m, monkeypatch):
    monkeypatch.setattr(m, "BASE", tmp_path)
    (tmp_path / "s" / "renders-v2").mkdir(parents=True)
    (tmp_path / "s" / "renders-v2" / "video.mp4").write_bytes(b"x")


def _warmup(tmp_path, phase):
    import json
    f = tmp_path / "warmup.json"
    f.write_text(json.dumps({"integrations": [{"id": "tt-id", "platform": "tiktok", "warmup_phase": phase, "active": True}]}))
    return f


def test_tiktok_is_skipped_while_the_account_is_still_warming_up(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    monkeypatch.setattr(m, "TT_ID", "tt-id")
    monkeypatch.setattr(m, "WARMUP_STATE", _warmup(tmp_path, "warmup"))
    monkeypatch.setattr(m, "_req", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no provider call")))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert m.schedule("s", SPEC, dt.date(2026, 10, 29), "k", ("tt",), run_dir=run_dir) == {"tt": "warmup_skip"}
    assert not list(run_dir.iterdir())


def test_tiktok_posts_directly_once_the_account_is_live(tmp_path, monkeypatch):
    import json
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    monkeypatch.setattr(m, "TT_ID", "tt-id")
    monkeypatch.setattr(m, "WARMUP_STATE", _warmup(tmp_path, "live"))
    calls = []

    def fake_req(key, url, data=None, headers=None, method=None):
        calls.append((url, data))
        return {"id": "u1", "path": "p"} if url.endswith("/upload") else [{"postId": "post-1"}]

    monkeypatch.setattr(m, "_req", fake_req)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    m.schedule("s", SPEC, dt.date(2026, 10, 29), "k", ("tt",), run_dir=run_dir)
    payload = json.loads(calls[-1][1])
    post = payload["posts"][0]
    assert post["integration"]["id"] == "tt-id" and payload["date"] == "2026-10-29T14:00:00.000Z"
    assert post["settings"]["__type"] == "tiktok" and post["settings"]["content_posting_method"] == "DIRECT_POST"
    assert post["settings"]["title"] == SPEC["hook_a"]
    assert (run_dir / "dispatch-tt.json").exists()


def test_carousel_renders_six_vertical_jpeg_slides(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    from PIL import Image
    monkeypatch.setattr(m, "BASE", tmp_path)
    (tmp_path / "s").mkdir()
    slides = m.render_carousel("s", SPEC)
    assert len(slides) == 6 and all(p.suffix == ".jpg" for p in slides)
    assert Image.open(slides[0]).size == (1080, 1920)


def test_tiktok_carousel_posts_six_images_once_live(tmp_path, monkeypatch):
    import json
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    monkeypatch.setattr(m, "TT_ID", "tt-id")
    monkeypatch.setattr(m, "WARMUP_STATE", _warmup(tmp_path, "live"))
    calls = []

    def fake_req(key, url, data=None, headers=None, method=None):
        calls.append((url, data, headers))
        return {"id": f"u{len(calls)}", "path": f"https://u/{len(calls)}.jpg"} if url.endswith("/upload") else [{"postId": "p"}]

    monkeypatch.setattr(m, "_req", fake_req)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    m.schedule("s", SPEC, dt.date(2026, 10, 29), "k", ("tc",), run_dir=run_dir)
    uploads = [c for c in calls if c[0].endswith("/upload")]
    assert len(uploads) == 6 and all(b"image/jpeg" in c[1] for c in uploads)
    post = json.loads(calls[-1][1])["posts"][0]
    assert len(post["value"][0]["image"]) == 6 and post["settings"]["__type"] == "tiktok"
    assert json.loads(calls[-1][1])["date"] == "2026-10-29T20:00:00.000Z"
    assert (run_dir / "dispatch-tc.json").exists()


def test_winner_openers_pick_top_viewed_shorts_and_feed_the_hook_prompt(tmp_path, monkeypatch):
    import json
    import capafy_reel_daily as m
    entries = [{"title": "Long video", "view_count": 9_000_000, "duration": 900},
               {"title": "Stop opening with your name", "view_count": 800_000, "duration": 31},
               {"title": "Nobody tells you this about hooks", "view_count": 1_200_000, "duration": 45}]
    assert m.top_short_titles(entries, 2) == ["Nobody tells you this about hooks", "Stop opening with your name"]
    cache = tmp_path / "winner-openers.json"
    cache.write_text(json.dumps({"fetched_at": dt.date.today().isoformat(), "titles": ["Nobody tells you this about hooks"]}))
    monkeypatch.setattr(m, "WINNER_OPENERS", cache)
    seen = {}
    monkeypatch.setattr(m, "_generate_text", lambda prompt: seen.setdefault("p", prompt) or "out")
    m.hook_lab_output({"key": "baking", "topic": "home baking Reel"})
    assert "Nobody tells you this about hooks" in seen["p"]


def _text_runner_fixture(tmp_path, monkeypatch, payload, *, escape=False, rc=0, wrapper=None):
    import json
    from types import SimpleNamespace
    import capafy_reel_daily as m
    monkeypatch.setenv("CAPAFY_REEL_RUN_DIR", str(tmp_path / "run"))
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        evidence = Path(command[command.index("--evidence-dir") + 1])
        evidence.mkdir(parents=True, exist_ok=True)
        result = evidence.parent / "outside.json" if escape else evidence / "result.json"
        raw = json.dumps(payload)
        result.write_text(wrapper(raw) if wrapper else raw)
        (evidence / "summary.json").write_text(json.dumps({
            "status": "success", "result_path": str(result),
        }))
        return SimpleNamespace(returncode=rc, stdout="private provider transcript",
                               stderr="private provider diagnostic")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    return m, calls


def test_generate_text_uses_shared_composition_and_private_unique_evidence(tmp_path, monkeypatch):
    import json
    m, calls = _text_runner_fixture(tmp_path, monkeypatch, {"text": "actual output\n"})
    for name in ("LM_POSTIZ_API_KEY", "LIFE_MANAGER_RESULT_HINT_PATH", "LIFE_MANAGER_OCCURRENCE_ID"):
        monkeypatch.setenv(name, "publisher-only")

    assert m._generate_text("A concrete bounded text task.") == "actual output\n"
    assert m._generate_text("A second bounded text task.") == "actual output\n"

    evidence_dirs = []
    for command, kwargs in calls:
        assert command[command.index("--task-class") + 1] == "composition-agent"
        assert "--prompt-stdin" in command and "--read-only" in command
        assert command[command.index("--timeout-seconds") + 1] == "600"
        assert "--model" not in command
        for name in ("LM_POSTIZ_API_KEY", "LIFE_MANAGER_RESULT_HINT_PATH", "LIFE_MANAGER_OCCURRENCE_ID"):
            assert name not in kwargs["env"]
        schema = json.loads(Path(command[command.index("--schema") + 1]).read_text())
        assert schema["required"] == ["text"]
        evidence = Path(command[command.index("--evidence-dir") + 1])
        assert evidence.is_relative_to(tmp_path / "run" / "agent-runner-evidence")
        assert evidence.stat().st_mode & 0o077 == 0
        evidence_dirs.append(evidence)
    assert evidence_dirs[0] != evidence_dirs[1]
    assert "A concrete bounded text task." in calls[0][1]["input"]


@pytest.mark.parametrize("payload", [
    {"text": ""}, {"text": "   "}, {"text": 7},
    {"message": "wrong envelope"}, {"text": "valid", "extra": True},
])
def test_generate_text_rejects_invalid_text_contract(tmp_path, monkeypatch, payload):
    m, calls = _text_runner_fixture(tmp_path, monkeypatch, payload)
    with pytest.raises(RuntimeError, match="capafy_reel_text_result_invalid"):
        m._generate_text("A concrete bounded text task.")


def test_generate_text_rejects_result_outside_current_evidence(tmp_path, monkeypatch):
    m, calls = _text_runner_fixture(tmp_path, monkeypatch, {"text": "outside"}, escape=True)
    with pytest.raises(RuntimeError, match="capafy_reel_text_result_invalid"):
        m._generate_text("A concrete bounded text task.")


def test_generate_text_failure_reports_rc_and_evidence_without_transcript(tmp_path, monkeypatch):
    m, calls = _text_runner_fixture(tmp_path, monkeypatch, {"text": "unused"}, rc=75)
    with pytest.raises(RuntimeError) as caught:
        m._generate_text("A concrete bounded text task.")
    message = str(caught.value)
    assert "rc=75" in message and "evidence=" in message
    assert "private provider" not in message


@pytest.mark.parametrize("wrapper", [
    lambda raw: "Done.\n" + raw,
    lambda raw: "```json\n" + raw + "\n```",
])
def test_generate_text_accepts_runner_supported_preamble_and_fences(tmp_path, monkeypatch, wrapper):
    m, calls = _text_runner_fixture(tmp_path, monkeypatch, {"text": "usable answer"}, wrapper=wrapper)
    assert m._generate_text("A concrete bounded text task.") == "usable answer"


# --- Postiz upload retry (2026-10-25 09:50 JST: HTTP 502 on /upload killed the whole daily run) ---

def _http_error(code):
    import urllib.error
    return urllib.error.HTTPError("https://api.postiz.com/public/v1/upload", code, "x", {}, None)


def test_upload_retries_a_transient_502_then_succeeds(monkeypatch):
    import capafy_reel_daily as m
    calls = []

    def flaky(key, url, *a, **k):
        calls.append(url)
        if len(calls) < 3:
            raise _http_error(502)
        return {"id": "u1", "path": "p"}

    monkeypatch.setattr(m, "_req", flaky)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    assert m._upload("k", b"data", "boundary") == {"id": "u1", "path": "p"}
    assert len(calls) == 3


def test_upload_gives_up_after_three_attempts(monkeypatch):
    import urllib.error
    import capafy_reel_daily as m
    calls = []
    monkeypatch.setattr(m, "_req", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(_http_error(502)))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        m._upload("k", b"data", "boundary")
    assert len(calls) == 3


def test_upload_does_not_retry_a_client_error(monkeypatch):
    import urllib.error
    import capafy_reel_daily as m
    calls = []
    monkeypatch.setattr(m, "_req", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(_http_error(401)))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        m._upload("k", b"data", "boundary")
    assert len(calls) == 1


# --- PR 9078 review follow-up: per-destination caption limits and the daily cap ---

LONG = {"noun": "n", "hook_a": "A" * 40, "hook_b": "B" * 40, "title": "T" * 34,
        "cards": [["L" * 14, "Q" * 80, "O" * 36]] * 3}


def test_long_valid_spec_gives_x_a_short_post_within_weighted_limit():
    import capafy_reel_daily as m
    validate_spec(LONG)
    assert len(caption(LONG)) > 280
    x = m.caption_for("x", LONG)
    assert x and m.x_weighted_length(x) <= m.X_WEIGHTED_LIMIT
    assert m.caption_for("ig", LONG) == caption(LONG) and m.caption_for("tt", LONG) == caption(LONG)


def test_x_weighted_length_counts_cjk_double_and_falls_back_or_skips():
    import capafy_reel_daily as m
    assert m.x_weighted_length("ab") == 2 and m.x_weighted_length("日本") == 4
    jp = {**SPEC, "hook_a": "あ" * 100, "hook_b": "い" * 100}
    assert m.caption_for("x", jp) is None


def test_over_limit_x_caption_is_skipped_without_provider_call(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    monkeypatch.setattr(m, "_req", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no provider call")))
    jp = {**SPEC, "hook_a": "あ" * 100, "hook_b": "い" * 100}
    assert m.schedule("s", jp, dt.date(2026, 11, 2), "k", ("x",)) == {"x": "caption_too_long_skip"}


def test_x_payload_uses_the_short_caption(tmp_path, monkeypatch):
    import json
    import capafy_reel_daily as m
    _video(tmp_path, m, monkeypatch)
    calls = []
    monkeypatch.setattr(m, "_req", lambda key, url, data=None, *a, **k: calls.append((url, data)) or
                        ({"id": "u", "path": "p"} if url.endswith("/upload") else [{"postId": "p"}]))
    m.schedule("s", LONG, dt.date(2026, 11, 2), "k", ("x",))
    content = json.loads(calls[-1][1])["posts"][0]["value"][0]["content"]
    assert m.x_weighted_length(content) <= 270


def _cap_env(tmp_path, monkeypatch, m, slugs):
    monkeypatch.setattr(m, "BASE", tmp_path)
    for slug in slugs:
        (tmp_path / slug / "renders-v2").mkdir(parents=True)
        (tmp_path / slug / "renders-v2" / "video.mp4").write_bytes(b"x")
    monkeypatch.setattr(m, "TT_ID", "tt-id")
    monkeypatch.setattr(m, "DAILY_CAP_INTEGRATIONS", {"tt-id"})
    monkeypatch.setattr(m, "WARMUP_STATE", _warmup(tmp_path, "live"))
    creates = []

    def fake_req(key, url, data=None, headers=None, method=None):
        if url.endswith("/upload"):
            return {"id": "u", "path": "p"}
        creates.append(url)
        return [{"postId": "p"}]

    monkeypatch.setattr(m, "_req", fake_req)
    return creates


def test_receipt_without_day_claim_still_blocks_a_second_slug_same_tokyo_day(tmp_path, monkeypatch):
    """Reproduces the review: receipt saved, run killed before the day claim."""
    import json
    import capafy_reel_daily as m
    creates = _cap_env(tmp_path, monkeypatch, m, ("a", "b"))
    day = dt.date(2026, 11, 2)
    (tmp_path / "a" / "tt-receipts-v3.jsonl").write_text(json.dumps(
        {"slug": "a", "scheduled_for": slots(day, 2)["tt"]}) + "\n")
    assert not m.ACCOUNT_DAILY_STATE.exists()
    assert m.schedule("b", SPEC, day, "k", ("tt",), slot=1) == {"tt": "daily_cap_skip"}
    assert creates == []
    assert m._account_day_taken("tt-id", slots(day, 2)["tt"]) == "a:tt"


def test_early_return_on_existing_receipt_restores_the_claim(tmp_path, monkeypatch):
    import json
    import capafy_reel_daily as m
    creates = _cap_env(tmp_path, monkeypatch, m, ("a",))
    day = dt.date(2026, 11, 2)
    (tmp_path / "a" / "tt-receipts-v3.jsonl").write_text(json.dumps({"slug": "a", "scheduled_for": slots(day)["tt"]}) + "\n")
    monkeypatch.setattr(m, "restore_account_days_from_receipts", lambda: None)
    assert m.schedule("a", SPEC, day, "k", ("tt",)) == {"tt": "already_scheduled"}
    assert m._account_day_taken("tt-id", slots(day)["tt"]) == "a:tt" and creates == []


def test_day_is_claimed_before_post_creation_and_survives_a_crash(tmp_path, monkeypatch):
    import capafy_reel_daily as m
    creates = _cap_env(tmp_path, monkeypatch, m, ("a", "b"))
    day = dt.date(2026, 11, 2)
    seen = []

    def crash(key, url, data=None, headers=None, method=None):
        if url.endswith("/upload"):
            return {"id": "u", "path": "p"}
        seen.append(m._account_day_taken("tt-id", slots(day)["tt"]))
        raise RuntimeError("killed after create, before receipt")

    monkeypatch.setattr(m, "_req", crash)
    with pytest.raises(RuntimeError):
        m.schedule("a", SPEC, day, "k", ("tt",))
    assert seen == ["a:tt"]
    monkeypatch.setattr(m, "_req", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no second post")))
    assert m.schedule("b", SPEC, day, "k", ("tt",), slot=2) == {"tt": "daily_cap_skip"}
    # the same slug may retry; the provider readback records the existing post instead of re-creating
    assert m.schedule("a", SPEC, day, "k", ("tt",), existing_fn=lambda net, slot: "post-a") == {"tt": {"existing": "post-a"}}
