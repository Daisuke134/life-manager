import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capafy_distribute_fence_reconcile as rec  # noqa: E402

Q = dt.datetime(2026, 9, 29, 8, 0, tzinfo=dt.timezone.utc)
OCC = "capafy-distribute-daily:run-1"


def proof(now_min, commits, x, status=200):
    return rec.build_proof(OCC, Q, now=Q + dt.timedelta(minutes=now_min),
                           commits=commits, x_posts=x, page_status_fn=lambda slug: status)


def test_live_landing_commit_is_effected():
    p = proof(10, {"ok": True, "commits": [{"sha": "abc", "slug": "capafy-x-2026-09-29-h15"}]},
              {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] and "abc" in p["provider_receipt_id"]


def test_commit_without_live_page_stays_fenced():
    p = proof(200, {"ok": True, "commits": [{"sha": "abc", "slug": "s"}]},
              {"ok": True, "posts": []}, status=404)
    assert not p["verified"]


def test_no_commit_too_recent_stays_fenced():
    assert not proof(30, {"ok": True, "commits": []}, {"ok": True, "posts": []})["verified"]


def test_no_commit_no_post_after_window_is_no_effect():
    p = proof(200, {"ok": True, "commits": []}, {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] is False


def test_x_post_without_article_stays_fenced():
    assert not proof(200, {"ok": True, "commits": []}, {"ok": True, "posts": ["p1"]})["verified"]


def test_readback_failure_stays_fenced():
    assert not proof(200, {"ok": False, "reason": "x"}, {"ok": True, "posts": []})["verified"]


def test_postiz_key_falls_back_to_unique_credential_ssot(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"credentials": [
        {"service": "postiz", "api_key": "secret-from-ssot"},
    ]}))

    assert rec.postiz_key(path) == "secret-from-ssot"


def test_postiz_key_rejects_ambiguous_or_malformed_ssot(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"credentials": [
        {"service": "postiz", "api_key": "first"},
        {"service": "postiz", "api_key": "second"},
    ]}))
    assert rec.postiz_key(path) == ""
    path.write_text("not-json")
    assert rec.postiz_key(path) == ""
