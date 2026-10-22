import json
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.loop import money_liveness as ml  # noqa: E402

LANES = [{"id": "writer", "path": "w/articles.jsonl", "max_age_hours": 36,
          "reader": "writer_publication", "meaning": "公開済み記事がない", "look_at": "launchd.err.log"}]


def _publication(stamp):
    return {"ts": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
            "published_at": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
            "published": True, "verified": True, "identity_verified": True,
            "public_id": "article-1", "state": "live", "live_url": "https://example.test/article"}


def _native_carousel_receipt():
    script = r'''
const crypto = require("node:crypto");
const adapter = require("./apps/life-manager/lib/marketing-native-carousel-publication-adapter.js");
const lane = adapter.EN_SLIDESHOW_TIKTOK_LANE;
const hashes = lane.mediaRefs.map(ref => ref.slice(-64));
const receipt = {
  schema_version: 1, kind: "marketing_native_carousel_distribution", status: "published",
  product_id: lane.productId, format_id: lane.formatId, form: lane.form, locale: lane.locale,
  platform: lane.platform, account_id: lane.accountId, integration_ref: lane.integrationRef,
  creative_id: lane.creativeId, pack_sha256: lane.packRef.slice(-64), media_sha256: hashes,
  media_order_sha256: crypto.createHash("sha256").update(JSON.stringify(hashes)).digest("hex"),
  caption_sha256: lane.captionRef.slice(-64), caption_with_cta_sha256: "c".repeat(64),
  provider_post_id: "postiz-test-carousel-1", provider_reconciled: true, public_url: null,
  provider_state: "PUBLISHED", provider_integration_id: lane.integrationId,
  provider_content_sha256: "c".repeat(64), provider_title: lane.title,
  provider_posting_method: "DIRECT_POST", provider_release_id: "p_pub_url~v2.7678198747632977937",
  published_at: "2026-10-22T10:30:00.000Z"
};
if (!adapter.verifyMarketingNativeCarouselPublicationReceipt(receipt)) process.exit(1);
process.stdout.write(JSON.stringify(receipt));
'''
    return json.loads(subprocess.check_output(["node", "-e", script], cwd=ml.ROOT, text=True))


def _setup(tmp_path, age_hours):
    home = tmp_path / "home"
    (home / "w").mkdir(parents=True)
    f = home / "w" / "articles.jsonl"
    old = time.time() - age_hours * 3600
    f.write_text(json.dumps(_publication(old)) + "\n")
    os.utime(f, (old, old))
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"lanes": LANES}))
    return home, tmp_path / "state", cfg


def test_stale_lane_alerts_once_per_cooldown_then_recovers(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=219)
    sent = []
    send = lambda t: sent.append(t) or True  # noqa: E731
    now = int(time.time())
    first = ml.run(home, state, send=send, now=now, config=cfg)
    assert first["stale"] == ["writer"] and len(sent) == 1 and "219h" in sent[0]
    ml.run(home, state, send=send, now=now + 3600, config=cfg)
    assert len(sent) == 1  # inside the 12h cooldown: no spam
    ml.run(home, state, send=send, now=now + 13 * 3600, config=cfg)
    assert len(sent) == 2  # still broken after the cooldown: remind
    f = home / "w" / "articles.jsonl"
    with f.open("a") as stream:
        stream.write(json.dumps(_publication(now + 14 * 3600)) + "\n")
    ml.run(home, state, send=send, now=now + 14 * 3600, config=cfg)
    assert len(sent) == 3 and sent[-1].startswith("RECOVERED")
    ml.run(home, state, send=send, now=now + 15 * 3600, config=cfg)
    assert len(sent) == 3  # recovery is announced once


def test_fresh_lane_is_silent(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=1)
    sent = []
    result = ml.run(home, state, send=lambda t: sent.append(t) or True, config=cfg)
    assert result["stale"] == [] and sent == []


def test_missing_artifact_counts_as_stale(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=1)
    (home / "w" / "articles.jsonl").unlink()
    sent = []
    ml.run(home, state, send=lambda t: sent.append(t) or True, config=cfg)
    assert len(sent) == 1 and "never" in sent[0]


def test_failed_delivery_is_retried_next_tick(tmp_path):
    home, state, cfg = _setup(tmp_path, age_hours=219)
    now = int(time.time())
    ml.run(home, state, send=lambda t: False, now=now, config=cfg)
    sent = []
    ml.run(home, state, send=lambda t: sent.append(t) or True, now=now + 300, config=cfg)
    assert len(sent) == 1


def test_real_config_lanes_are_well_formed():
    lanes = json.loads(ml.CONFIG.read_text())["lanes"]
    assert lanes and all({"id", "path", "max_age_hours", "meaning", "look_at"} <= set(l) for l in lanes)


def test_failed_ledger_touch_does_not_recover_outcome(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ledger = home / "ledger.json"
    ledger.write_text(json.dumps({"2026-10-22-h19m30": {
        "status": "blocked", "destinations": {"aniccaai": {"status": "failed"}}
    }}))
    now = 1792665900.0
    os.utime(ledger, (now, now))
    lanes = [{"id": "capafy-articles", "path": "ledger.json", "reader": "capafy_distribution",
              "max_age_hours": 6, "meaning": "公開成果がない", "look_at": "ledger"}]
    rows = ml.evaluate(lanes, home, now)
    texts, memory = ml.messages(rows, {"capafy-articles": now - 3600}, now)
    assert rows[0]["stale"] is True
    assert rows[0]["last_verified_outcome"] is None
    assert not any(text.startswith("RECOVERED") for text in texts)
    assert "capafy-articles" in memory


def test_verified_receipt_advances_only_its_product_clock(tmp_path):
    p = tmp_path / "outcomes.jsonl"
    p.write_text(json.dumps({"product_id": "anicca-ios", "observed_at": "2026-10-22T10:00:00Z",
        "sources": {"revenuecat": {"status": "available", "evidence_sha256": "a" * 64,
                                    "data": {"charts": {"revenue": {"latest_complete": {}}}}}}}) + "\n")
    lanes = [{"id": product, "path": p.name, "reader": "business_readback", "product_id": product,
              "max_age_hours": 12} for product in ("anicca-ios", "honne-ai")]
    rows = ml.evaluate(lanes, tmp_path, 1792665900.0)
    assert rows[0]["stale"] is False
    assert rows[1]["stale"] is True
    assert rows[1]["last_verified_outcome"] is None
    assert all(row["last_paid"] is None for row in rows)


def test_no_work_is_not_revenue_recovery(tmp_path):
    (tmp_path / "published.jsonl").write_text("")
    (tmp_path / "terminals.jsonl").write_text(json.dumps({"schema_version": 1, "execution_id": "run-1",
        "phase": "terminal", "observed_at": "2026-10-22T10:00:00Z", "healthy": True,
        "rc": 0, "verdict": "CAP_FULL"}) + "\n")
    lanes = [{"id": "ship", "path": "published.jsonl", "reader": "capafy_submission",
              "terminal_path": "terminals.jsonl", "max_age_hours": 4}]
    now = 1792665900.0
    row = ml.evaluate(lanes, tmp_path, now)[0]
    texts, memory = ml.messages([row], {"ship": now - 3600}, now)
    assert row["outcome_status"] == "no_work"
    assert row["last_verified_outcome"] is None and row["last_paid"] is None
    assert texts == [] and "ship" in memory


def test_factory_failure_does_not_recover_from_recent_old_success(tmp_path):
    p = tmp_path / "terminals.jsonl"
    rows = [{"schema_version": 1, "execution_id": "old", "phase": "terminal",
             "observed_at": "2026-10-22T10:00:00Z", "healthy": True, "rc": 0},
            {"schema_version": 1, "execution_id": "new", "phase": "terminal",
             "observed_at": "2026-10-22T10:15:00Z", "healthy": False, "rc": 1}]
    p.write_text("\n".join(json.dumps(row) for row in rows))
    lane = {"id": "factory", "reader": "capafy_factory", "path": p.name, "max_age_hours": 1}
    assert ml.evaluate([lane], tmp_path, 1792665900.0)[0]["stale"] is True


def test_published_distribution_recovers_from_its_slot_once(tmp_path):
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"2026-10-22-h19m30": {"status": "published", "destinations": {
        "aniccaai": {"status": "published", "url": "https://example.test/live"}}}}))
    lane = {"id": "article", "reader": "capafy_distribution", "path": p.name, "max_age_hours": 6}
    now = 1792665900.0
    row = ml.evaluate([lane], tmp_path, now)[0]
    assert row["last_verified_outcome"] is not None
    assert row["last_paid"] is None and row["stale"] is False
    texts, memory = ml.messages([row], {"article": now - 3600}, now)
    assert len(texts) == 1 and texts[0].startswith("RECOVERED")
    assert ml.messages([row], memory, now + 10)[0] == []


def test_telegram_liveness_and_unreconciled_post_are_not_publications(tmp_path):
    p = tmp_path / "receipts.jsonl"
    receipt = _native_carousel_receipt()
    rows = [{"receipt": {**receipt, "kind": "telegram_marketing_liveness"}},
            {"receipt": {**receipt, "provider_reconciled": False}},
            {"receipt": {**receipt, "product_id": "honne-ai"}}]
    p.write_text("\n".join(json.dumps(row) for row in rows))
    lane = {"id": "mobile", "reader": "marketing_publication", "product_id": "anicca-ios", "path": p.name, "max_age_hours": 12}
    row = ml.evaluate([lane], tmp_path, 1792665900.0)[0]
    assert row["stale"] is True and row["last_verified_outcome"] is None
    with p.open("a") as stream:
        stream.write("\n" + json.dumps({"receipt": receipt}))
    assert ml.evaluate([lane], tmp_path, 1792665900.0)[0]["stale"] is False


def test_malformed_missing_future_and_date_only_rows_do_not_refresh(tmp_path):
    p = tmp_path / "articles.jsonl"
    rows = [_publication(1792665900.0), {"state": "failed"}]
    rows[0]["published_at"] = "2099-01-01T00:00:00Z"
    p.write_text("malformed\n[]\n" + "\n".join(json.dumps(row) for row in rows))
    lane = {"id": "writer", "reader": "writer_publication", "path": p.name, "max_age_hours": 36}
    assert ml.evaluate([lane], tmp_path, 1792665900.0)[0]["last_verified_outcome"] is None
    assert ml._timestamp("2026-10-22", 1792665900.0) is None
    p.unlink()
    assert ml.evaluate([lane], tmp_path, 1792665900.0)[0]["stale"] is True


def test_submission_producer_records_precise_verified_time(tmp_path):
    import subprocess
    script = ml.ROOT / "skills/capafy-autopublish/scripts/publish_finish.sh"
    ledger_block = script.read_text().split('step "[8] ledger"', 1)[1].split("<<'PY'\n", 1)[1].split("\nPY", 1)[0]
    listing, ledger = tmp_path / "LISTING.md", tmp_path / "published.jsonl"
    listing.write_text("## Title\nExample\n")
    result = subprocess.run([sys.executable, "-", "agent-1", "skill-1", str(listing), str(ledger)],
                            input=ledger_block, text=True, capture_output=True)
    assert result.returncode == 0
    row = json.loads(ledger.read_text())
    assert row["agent_id"] == "agent-1" and row["status"].startswith("submitted")
    assert ml._timestamp(row["submitted_at"], time.time()) is not None


def test_real_submission_can_recover_while_next_work_waits_for_review(tmp_path):
    (tmp_path / "published.jsonl").write_text(json.dumps({"agent_id": "agent-1", "status": "submitted (status=1 under review)",
        "submitted_at": "2026-10-22T10:00:00Z"}) + "\n")
    (tmp_path / "terminals.jsonl").write_text(json.dumps({"schema_version": 1, "execution_id": "run-1", "phase": "terminal",
        "observed_at": "2026-10-22T10:15:00Z", "healthy": True, "rc": 0, "verdict": "CAP_FULL"}) + "\n")
    lane = {"id": "ship", "reader": "capafy_submission", "path": "published.jsonl", "terminal_path": "terminals.jsonl", "max_age_hours": 4}
    row = ml.evaluate([lane], tmp_path, 1792665900.0)[0]
    assert row["outcome_status"] == "verified" and row["stale"] is False
    assert ml.messages([row], {"ship": 1792665800.0}, 1792665900.0)[0][0].startswith("RECOVERED")


def test_malformed_receipt_kind_does_not_crash_other_lanes(tmp_path):
    p = tmp_path / "receipts.jsonl"
    p.write_text(json.dumps({"receipt": {"product": "anicca-ios", "kind": [], "status": "published"}}))
    lane = {"id": "mobile", "reader": "marketing_publication", "product_id": "anicca-ios", "path": p.name, "max_age_hours": 12}
    assert ml.evaluate([lane], tmp_path, 1792665900.0)[0]["stale"] is True


def test_invalid_terminal_verdict_does_not_stop_other_lanes(tmp_path):
    (tmp_path / "published.jsonl").write_text("")
    (tmp_path / "terminals.jsonl").write_text(json.dumps({"schema_version": 1, "execution_id": "run-1", "phase": "terminal",
        "observed_at": "2026-10-22T10:00:00Z", "healthy": True, "rc": 0, "verdict": []}))
    lane = {"id": "ship", "reader": "capafy_submission", "path": "published.jsonl", "terminal_path": "terminals.jsonl", "max_age_hours": 4}
    assert len(ml.evaluate([lane, {**lane, "id": "next"}], tmp_path, 1792665900.0)) == 2


def test_official_photo_api_receipt_without_url_advances_only_its_product(tmp_path):
    receipt = _native_carousel_receipt()
    assert receipt["public_url"] is None
    (tmp_path / "receipts.jsonl").write_text(json.dumps({"receipt": receipt}))
    lanes = [{"id": product, "reader": "marketing_publication", "product_id": product,
              "path": "receipts.jsonl", "max_age_hours": 12} for product in ("anicca-ios", "honne-ai")]
    rows = ml.evaluate(lanes, tmp_path, 1792665900.0)
    assert rows[0]["stale"] is False and rows[0]["last_verified_outcome"] is not None
    assert rows[1]["stale"] is True and rows[1]["last_verified_outcome"] is None
