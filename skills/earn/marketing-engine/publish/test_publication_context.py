import json
import pathlib
import sys
from functools import partial

import pytest

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))

from intent_store import IntentStore, build_intent
from preflight import validate_preflight
from publication_context import PublishContext
import publish_cli
from publish_cli import (run_create_intent, run_native_candidates,
                         run_postiz_operation, run_reconcile, run_route_check,
                         run_shadow)
from test_postiz_adapter import FakePostiz


DESTINATION = "https://example.com/book?ct=factory_demo"

def asset_file(tmp_path):
    path = tmp_path / "preview.mp4"
    path.write_bytes(b"test-video")
    return path


def factory_context(**account_changes):
    account = {
        "account_id": "factory.account.demo", "product_id": "factory.product.demo",
        "platform": "instagram", "native_handle": "factory.monk",
        "status": "approved_active", "allowed_renderer_ids": ["heygen-avatar-iv"],
        "publisher_integration_id": "factory-integration",
        "publisher_provider": "instagram-standalone",
        "publisher_settings": {"__type": "instagram-standalone", "post_type": "post",
                               "is_trial_reel": False, "collaborators": []},
    } | account_changes
    return PublishContext(account=account,
        product={"product_id": "factory.product.demo", "cta": "Read this book"},
        destination_url=DESTINATION)


def create_args(tmp_path, context):
    return dict(
        engine=ENGINE, output_path=tmp_path / "intent.json",
        experiment_id="experiment.factory", creative_id="creative.factory",
        product_id=context.product["product_id"],
        account_id=context.account["account_id"], hook_id="hook.factory",
        renderer_id="heygen-avatar-iv", adapter="postiz", asset_path=asset_file(tmp_path),
        caption=f"Read this book {DESTINATION}", attribution_token="factory_demo",
        scheduled_at="2026-10-25T01:00:00Z",
        visual_approval_id="visual.accepted.factory", now="2026-10-24T00:00:00Z",
        context=context)


def test_create_intent_uses_factory_route_and_exact_product_destination(tmp_path):
    context = factory_context()
    args = create_args(tmp_path, context)
    result = run_create_intent(**args)
    intent = json.loads(args["output_path"].read_text())
    assert intent["account_id"] == "factory.account.demo"
    assert intent["integration_id"] == "factory-integration"
    assert intent["native_handle"] == "factory.monk"
    assert intent["caption"] == "Read this book https://example.com/book?ct=factory_demo"
    assert intent["attribution_token"] == "factory_demo"
    assert result["external_mutations"] == 0


@pytest.mark.parametrize("field,value", [
    ("account_id", "factory.account.other"), ("product_id", "factory.product.other"),
])
def test_context_rejects_a_different_intent_route_before_writing(tmp_path, field, value):
    args = create_args(tmp_path, factory_context()) | {field: value}
    with pytest.raises(ValueError, match="context.*mismatch"):
        run_create_intent(**args)
    assert not args["output_path"].exists()


@pytest.mark.parametrize("url", [
    DESTINATION + "x", DESTINATION + "&extra=1", DESTINATION + "#other",
    DESTINATION + " " + DESTINATION,
    DESTINATION + " " + DESTINATION + "x",
])
def test_context_destination_must_be_one_complete_token(tmp_path, url):
    args = create_args(tmp_path, factory_context()) | {"caption": "Read this book " + url}
    with pytest.raises(ValueError, match="destination URL"):
        run_create_intent(**args)
    assert not args["output_path"].exists()


def registered_factory(tmp_path, context):
    account = context.account
    intent = build_intent(
        experiment_id="experiment.factory", creative_id="creative.factory",
        product_id=context.product["product_id"], account_id=account["account_id"],
        hook_id="hook.factory", renderer_id="heygen-avatar-iv", adapter="postiz",
        asset_path=asset_file(tmp_path), caption=f"Read this book {DESTINATION}",
        attribution_token="factory_demo", scheduled_at="2026-10-25T01:00:00Z",
        integration_id=account["publisher_integration_id"], platform=account["platform"],
        native_handle=account["native_handle"], provider_settings=account["publisher_settings"],
        visual_approval_id="visual.accepted.factory")
    store = IntentStore(tmp_path / "jobs.sqlite3")
    store.register(intent)
    approvals = tmp_path / "approvals.jsonl"
    approvals.write_text(json.dumps({
        "approval_id": "visual.accepted.factory", "status": "accepted",
        "asset_sha256": intent["asset_sha256"], "product_id": "factory.product.demo",
        "account_id": "factory.account.demo"}) + "\n")
    return store, intent, approvals


def media_probe(_asset):
    return {"duration_seconds": 17.4, "format_names": ["mp4"], "video_codec": "h264",
            "audio_codec": "aac", "width": 720, "height": 1280}


def context_client():
    return FakePostiz(integrations=[{
        "id": "factory-integration", "identifier": "instagram-standalone",
        "profile": "factory.monk", "disabled": False}])


def test_context_preflight_keeps_asset_approval_and_exact_destination_checks(tmp_path):
    context = factory_context()
    _, intent, approvals = registered_factory(tmp_path, context)
    result = validate_preflight(intent, engine=ENGINE, approvals_path=approvals,
                                media_probe=media_probe, context=context)
    assert result["status"] == "dispatchable"
    for changed, error in [
        ({"caption": "Read this book " + DESTINATION + "x"}, "destination URL"),
        ({"caption": "Read this book " + DESTINATION + " " + DESTINATION}, "destination URL"),
        ({"caption": DESTINATION}, "CTA missing"),
        ({"asset_sha256": "0" * 64}, "asset hash mismatch"),
        ({"visual_approval_id": "visual.accepted.other"}, "accepted visual approval missing"),
        ({"native_handle": "someone.else"}, "native handle mismatch"),
        ({"integration_id": "other-integration"}, "integration mismatch"),
    ]:
        with pytest.raises(ValueError, match=error):
            validate_preflight(intent | changed, engine=ENGINE, approvals_path=approvals,
                               media_probe=media_probe, context=context)


def test_context_preflight_rejects_product_route_and_inactive_account(tmp_path):
    context = factory_context()
    _, intent, approvals = registered_factory(tmp_path, context)
    for changed_context, error in [
        (factory_context(product_id="factory.product.other"), "context.*mismatch"),
        (factory_context(status="disabled"), "not approved_active"),
    ]:
        with pytest.raises(ValueError, match=error):
            validate_preflight(intent, engine=ENGINE, approvals_path=approvals,
                               media_probe=media_probe, context=changed_context)


def test_shadow_uses_context_for_the_same_approval_gate_without_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_cli, "validate_preflight",
                        partial(validate_preflight, media_probe=media_probe))
    context = factory_context()
    store, intent, approvals = registered_factory(tmp_path, context)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(intent))
    result = run_shadow(intent_path=intent_path, db_path=store.path,
        approvals_path=approvals, owner="worker", now="2026-10-24T00:00:00Z",
        engine=ENGINE, context=context)
    assert result["status"] == "shadow_valid"
    assert result["dispatchable"] is True
    assert result["external_effects"] == []


def test_live_context_checks_the_current_route_before_every_fenced_operation(tmp_path):
    context = factory_context()
    store, intent, approvals = registered_factory(tmp_path, context)
    client = context_client()
    args = dict(db_path=store.path, publish_key=intent["publish_key"], operation="upload",
        approvals_path=approvals, owner="worker", now="2026-10-24T00:00:00Z",
        ttl_seconds=300, engine=ENGINE, production=True, client=client,
        media_probe=media_probe, context=context)
    first = run_postiz_operation(**args)
    second = run_postiz_operation(**(args | {"now": "2026-10-24T00:00:01Z"}))
    assert first["state"] == second["state"] == "accepted"
    assert client.upload_calls == 1
    assert store.get(intent["publish_key"])["provider_media_id"] == "media-123"
    client.integrations[0]["profile"] = "someone.else"
    with pytest.raises(ValueError, match="publisher route is not ready.*native profile mismatch"):
        run_postiz_operation(**(args | {"operation": "draft", "now": "2026-10-24T00:00:02Z"}))
    assert client.create_calls == 0


def test_context_route_check_does_not_accept_the_wrong_native_profile():
    client = context_client()
    args = dict(account_id="factory.account.demo", engine=ENGINE,
                client=client, context=factory_context())
    assert run_route_check(**args)["route_ready"] is True
    client.integrations[0]["profile"] = "someone.else"
    assert run_route_check(**args)["blockers"] == ["native profile mismatch"]


def test_context_reconcile_records_only_the_configured_native_identity(tmp_path):
    context = factory_context()
    store, intent, _ = registered_factory(tmp_path, context)
    store.reconcile_provider(intent["publish_key"], {"id": "post-123", "state": "QUEUE"})
    post = {"id": "post-123", "state": "PUBLISHED", "content": intent["caption"],
        "publishDate": intent["scheduled_at"], "releaseId": "native-123",
        "releaseURL": "https://www.instagram.com/reel/native-123/",
        "integration": {"id": "factory-integration", "providerIdentifier": "instagram"}}
    native = {"native_handle": "factory.monk", "native_post_id": "native-123",
        "native_post_url": "https://www.instagram.com/reel/native-123/",
        "caption": intent["caption"], "published_at": intent["scheduled_at"]}
    post_path, native_path, ledger = (tmp_path / name for name in
                                     ("post.json", "native.json", "identity.jsonl"))
    post_path.write_text(json.dumps(post))
    native_path.write_text(json.dumps([native]))
    args = dict(db_path=store.path, publish_key=intent["publish_key"], post_path=post_path,
                native_path=native_path, ledger_path=ledger,
                observed_at="2026-10-25T01:05:00Z", engine=ENGINE)
    with pytest.raises(ValueError, match="native handle differs"):
        run_reconcile(**args, context=factory_context(native_handle="someone.else"))
    assert not ledger.exists()
    result = run_reconcile(**args, context=context)
    assert result["status"] == "published_native_verified"
    assert json.loads(ledger.read_text())["native_post_id"] == "native-123"


def test_context_native_candidates_filter_posts_using_the_intent_handle(tmp_path):
    context = factory_context(platform="tiktok", native_handle="factory_monk",
        publisher_provider="tiktok", publisher_settings={"__type": "tiktok"})
    store, intent, _ = registered_factory(tmp_path, context)
    exact = {"native_handle": "factory_monk", "native_post_id": "7468922143619812626",
        "native_post_url": "https://www.tiktok.com/@factory_monk/video/7468922143619812626",
        "caption": intent["caption"], "published_at": intent["scheduled_at"]}
    args = dict(db_path=store.path, publish_key=intent["publish_key"],
        output_path=tmp_path / "native.json", engine=ENGINE, cdp_url="unused", wait_ms=1)
    collector_calls = []

    def collector(**kwargs):
        collector_calls.append(kwargs["expected_handle"])
        return {"api_responses_observed": 1, "profile_items_observed": 2,
                "candidates": [exact | {"native_handle": "someone_else"}, exact]}

    with pytest.raises(ValueError, match="native handle differs"):
        run_native_candidates(**args, collector=collector,
                              context=factory_context(native_handle="someone_else"))
    assert collector_calls == []
    result = run_native_candidates(**args, collector=collector, context=context)
    assert result["candidate_count"] == 1
    assert json.loads(args["output_path"].read_text()) == [exact]
    assert collector_calls == ["factory_monk"]
