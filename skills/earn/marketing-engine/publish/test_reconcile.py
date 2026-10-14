import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intent_store import IntentStore
from reconcile import reconcile_postiz_result
from test_intent_store import fixture_intent


def setup(tmp_path):
    store = IntentStore(tmp_path / "jobs.sqlite3")
    intent = store.register(fixture_intent(tmp_path))["intent"]
    store.reconcile_provider(intent["publish_key"], {"id": "post-123", "state": "QUEUE"})
    return store, intent, tmp_path / "publication-identity.jsonl"


def published_post(intent):
    return {
        "id": "post-123", "group": "group-123", "state": "PUBLISHED",
        "content": intent["caption"], "publishDate": intent["scheduled_at"],
        "creationMethod": "api", "releaseId": "native-123",
        "releaseURL": "https://www.instagram.com/reel/native-123/",
        "integration": {"id": intent["integration_id"],
                        "providerIdentifier": intent["platform"], "name": "anicca.en"},
    }


def native_candidate(intent):
    return {
        "native_handle": "anicca.en", "native_post_id": "native-123",
        "native_post_url": "https://www.instagram.com/reel/native-123/",
        "caption": intent["caption"], "published_at": intent["scheduled_at"],
    }


def test_published_requires_native_readback_and_writes_identity_once(tmp_path):
    store, intent, ledger = setup(tmp_path)
    first = reconcile_postiz_result(
        store=store, publish_key=intent["publish_key"], post=published_post(intent),
        native_items=[native_candidate(intent)], expected_handle="anicca.en",
        observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    second = reconcile_postiz_result(
        store=store, publish_key=intent["publish_key"], post=published_post(intent),
        native_items=[native_candidate(intent)], expected_handle="anicca.en",
        observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert first["status"] == second["status"] == "published_native_verified"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    for field in (
        "publish_key", "experiment_id", "creative_id", "product_id", "account_id",
        "hook_id", "renderer_id", "attribution_token", "scheduled_at",
    ):
        assert row[field] == intent[field]
    assert row["experiment_id"] == "experiment.123"
    assert row["creative_sha256"] == intent["asset_sha256"]
    assert row["native_post_id"] == "native-123"
    assert row["native_post_url"] == "https://www.instagram.com/reel/native-123/"
    assert store.get(intent["publish_key"])["state"] == "published"


def test_provider_display_name_is_not_treated_as_native_handle(tmp_path):
    store, intent, ledger = setup(tmp_path)
    post = published_post(intent)
    post["integration"]["name"] = "アニッチャ - 無常の教え"
    result = reconcile_postiz_result(
        store=store, publish_key=intent["publish_key"], post=post,
        native_items=[native_candidate(intent)], expected_handle="anicca.en",
        observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert result["status"] == "published_native_verified"


def test_published_without_native_candidate_stays_pending(tmp_path):
    store, intent, ledger = setup(tmp_path)
    result = reconcile_postiz_result(
        store=store, publish_key=intent["publish_key"], post=published_post(intent),
        native_items=[], expected_handle="anicca.en",
        observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert result["status"] == "pending_native_receipt"
    assert not ledger.exists()
    assert store.get(intent["publish_key"])["state"] == "published_provider"


def test_multiple_native_candidates_fail_closed(tmp_path):
    store, intent, ledger = setup(tmp_path)
    first = native_candidate(intent)
    with pytest.raises(ValueError, match="multiple native candidates"):
        reconcile_postiz_result(
            store=store, publish_key=intent["publish_key"], post=published_post(intent),
            native_items=[first, first | {"native_post_id": "native-456",
                "native_post_url": "https://www.instagram.com/reel/native-456/"}],
            expected_handle="anicca.en", observed_at="2026-08-02T01:05:00Z",
            ledger_path=ledger)
    assert not ledger.exists()


def test_provider_error_remains_error_and_writes_no_identity(tmp_path):
    store, intent, ledger = setup(tmp_path)
    post = published_post(intent) | {"state": "ERROR", "releaseId": None, "releaseURL": None}
    result = reconcile_postiz_result(
        store=store, publish_key=intent["publish_key"], post=post,
        native_items=[], expected_handle="anicca.en",
        observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert result["status"] == "provider_error"
    assert store.get(intent["publish_key"])["state"] == "provider_error"
    assert not ledger.exists()


def test_wrong_integration_fails_before_ledger_write(tmp_path):
    store, intent, ledger = setup(tmp_path)
    post = published_post(intent) | {"integration": {
        "id": "wrong", "providerIdentifier": "instagram", "name": "anicca.en"}}
    with pytest.raises(ValueError, match="reconciled integration mismatch"):
        reconcile_postiz_result(
            store=store, publish_key=intent["publish_key"], post=post,
            native_items=[native_candidate(intent)], expected_handle="anicca.en",
            observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert not ledger.exists()


def test_wrong_provider_fails_before_ledger_write(tmp_path):
    store, intent, ledger = setup(tmp_path)
    post = published_post(intent)
    post["integration"]["providerIdentifier"] = "wrong-provider"
    with pytest.raises(ValueError, match="reconciled provider mismatch"):
        reconcile_postiz_result(
            store=store, publish_key=intent["publish_key"], post=post,
            native_items=[native_candidate(intent)], expected_handle="anicca.en",
            observed_at="2026-08-02T01:05:00Z", ledger_path=ledger)
    assert not ledger.exists()
