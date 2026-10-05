import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capafy_ig_reel_fence_reconcile as rec  # noqa: E402

Q = dt.datetime(2026, 10, 5, 11, 0, 8, tzinfo=dt.timezone.utc)
OCC = "life-manager-capafy-ig:18db9d1858bcbc20-12593"
INTEGRATION = "cmuuycr5402uzqw0yhanqggo9"


def proof(now_min, posts):
    return rec.build_proof(OCC, Q, now=Q + dt.timedelta(minutes=now_min), posts=posts,
                           integration_id=INTEGRATION)


def test_post_in_window_is_effected():
    posts = {"ok": True, "posts": [
        {"id": "p1", "integration": {"id": INTEGRATION}},
    ]}
    p = proof(5, posts)
    assert p["verified"] and p["effected"] and "p1" in p["provider_receipt_id"]


def test_post_for_other_integration_is_ignored():
    posts = {"ok": True, "posts": [
        {"id": "p1", "integration": {"id": "someone-else"}},
    ]}
    p = proof(90, posts)
    assert p["verified"] and p["effected"] is False


def test_no_post_too_recent_stays_fenced():
    p = proof(5, {"ok": True, "posts": []})
    assert not p["verified"]


def test_no_post_after_window_is_no_effect():
    p = proof(90, {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] is False
    assert "postiz" in p["provider_receipt_id"]


def test_readback_failure_stays_fenced():
    p = proof(90, {"ok": False, "reason": "postiz_key_missing"})
    assert not p["verified"]


def test_missing_integration_id_stays_fenced():
    p = rec.build_proof(OCC, Q, now=Q + dt.timedelta(minutes=90),
                        posts={"ok": True, "posts": []}, integration_id="")
    assert not p["verified"]
    assert p["reason"] == "integration_id_missing"


def test_postiz_key_falls_back_to_unique_credential_ssot(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"credentials": [
        {"service": "postiz", "api_key": "secret-from-ssot"},
    ]}))
    assert rec.postiz_key(path) == "secret-from-ssot"


def test_reconcile_wires_fenced_row_and_resolve(monkeypatch):
    def fake_fenced_row(owner_id, occurrence_id):
        assert owner_id == rec.OWNER_ID
        assert occurrence_id == OCC
        return "claimed", Q

    def fake_posts_fn(start, end):
        assert start == Q
        return {"ok": True, "posts": []}

    closed = {}

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        closed["called"] = True
        proof_payload = official_readback()
        assert proof_payload["verified"] is True
        return True

    monkeypatch.setenv("CAPAFY_IG_POSTIZ_INTEGRATION_ID", INTEGRATION)
    result = rec.reconcile(
        OCC, resolve=True, now=Q + dt.timedelta(minutes=90),
        fenced_row_fn=fake_fenced_row, posts_fn=fake_posts_fn, resolve_fn=fake_resolve,
    )
    assert result["effected"] is False
    assert result["closed"] is True
    assert closed["called"]


def test_integration_id_falls_back_to_marketing_env_file(tmp_path, monkeypatch):
    # 2026-10-05: lm-fence-reconciler runs the adapter without marketing.env loaded,
    # so CAPAFY_IG_POSTIZ_INTEGRATION_ID was empty -> adapter_held:integration_id_missing.
    monkeypatch.delenv("CAPAFY_IG_POSTIZ_INTEGRATION_ID", raising=False)
    env_file = tmp_path / "marketing.env"
    env_file.write_text("LM_POSTIZ_API_KEY=secret\nexport CAPAFY_IG_POSTIZ_INTEGRATION_ID=cmabc123\n", encoding="utf-8")
    assert rec.integration_id(env_file) == "cmabc123"
