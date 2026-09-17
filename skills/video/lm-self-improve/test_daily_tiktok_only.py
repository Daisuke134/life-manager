import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("lm_self_improve", HERE / "daily.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_record_day_accepts_tiktok_only_distribution(tmp_path):
    bank = tmp_path / "bank.jsonl"
    bank.write_text(
        json.dumps({"id": "B03", "pain": "p3", "moment": "m3", "punchline": "h3"})
        + "\n"
        + json.dumps({"id": "B04", "pain": "p4", "moment": "m4", "punchline": "h4"})
        + "\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "self-improve.jsonl"
    rows = [{
        "platform": "tiktok",
        "status": "published",
        "creative_id": "B03",
        "video_sha256": "v" * 64,
        "caption_sha256": "c" * 64,
        "public_url": "https://www.tiktok.com/@anicca.comedy/video/123",
    }]

    result = MODULE.record_day(
        date="2026-09-18",
        distribution_rows=rows,
        metrics={"tiktok": {"views": 12, "likes": 2, "comments": 1}},
        bank_path=bank,
        ledger_path=ledger,
        platforms=("tiktok",),
    )

    assert result["metric_complete"] is True
    assert result["platforms"] == [{
        "platform": "tiktok",
        "url": "https://www.tiktok.com/@anicca.comedy/video/123",
        "views": 12,
        "likes": 2,
        "comments": 1,
        "watch_time": None,
        "completion_rate": None,
        "clicks": None,
        "signups": None,
        "source_limitation": result["platforms"][0]["source_limitation"],
    }]
    assert result["next_creative_id"] == "B04"


def test_unavailable_metric_result_is_explicit_and_does_not_claim_growth(tmp_path):
    bank = tmp_path / "bank.jsonl"
    bank.write_text(
        json.dumps({"id": "B03", "pain": "p3", "moment": "m3", "punchline": "h3"})
        + "\n"
        + json.dumps({"id": "B04", "pain": "p4", "moment": "m4", "punchline": "h4"})
        + "\n",
        encoding="utf-8",
    )
    rows = [{
        "platform": "tiktok",
        "status": "published",
        "creative_id": "B03",
        "video_sha256": "v" * 64,
        "caption_sha256": "c" * 64,
        "public_url": "https://www.tiktok.com/@anicca.comedy/video/123",
    }]

    result = MODULE.unavailable_metric_result(
        date="2026-09-18",
        distribution_rows=rows,
        bank_path=bank,
        platforms=("tiktok",),
        reason="TikTok public metric readback failed",
    )

    assert result["status"] == "unavailable"
    assert result["metric_complete"] is False
    assert result["day_index"] == 0
    assert result["next_creative_id"] == "B04"
    assert "no growth claim" in result["next_change_reason"]
