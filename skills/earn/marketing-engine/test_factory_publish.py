import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "publish"), str(HERE / "gates")]
from factory_plan import build_plan
from factory_publish import publish_from_config
from approval_store import record_visual_approval
from intent_store import IntentStore
from test_postiz_adapter import FakePostiz

MEDIA = {"duration_seconds": 13.2, "format_names": ["mp4"], "video_codec": "h264",
         "audio_codec": "aac", "width": 1080, "height": 1920}


@pytest.fixture
def request_args(tmp_path, monkeypatch):
    monkeypatch.setenv("LM_DATA_DIR", str(tmp_path / "host"))
    monkeypatch.setattr("factory_publish._host_disk_admission", lambda: True)
    config = {"schema_version": "ai-monk-factory.config.v1", "project_id": "demo", "language": "en",
              "heygen": {"avatar_id": "avatar123", "voice_id": "voice123"},
              "postiz": {"platform": "tiktok", "integration_id": "factory-test-integration"},
              "product": {"name": "My Book", "url": "https://example.com/book?utm_campaign=launch"},
              "state_root": str(tmp_path / "project")}
    publication = {"schema_version": "ai-monk-factory.publication.v1", "native_handle": "factory_test_monk",
                   "publisher_provider": "tiktok", "publish_enabled": True,
                   "provider_settings": {"__type": "tiktok", "title": "", "privacy_level": "PUBLIC_TO_EVERYONE",
                       "duet": False, "stitch": False, "comment": True, "autoAddMusic": "no",
                       "brand_content_toggle": False, "brand_organic_toggle": True,
                       "video_made_with_ai": True, "content_posting_method": "DIRECT_POST"},
                   "cta": "Read My Book", "caption": "Read My Book https://example.com/book?utm_campaign=launch",
                   "attribution_token": "launch", "scheduled_at": "2026-10-24T00:00:00Z",
                   "visual_approval_id": "visual.accepted.factory-test"}
    args = dict(config=config, script="Pause for a moment and notice what you can do today.",
                publication=publication, run_id="first", now="2026-10-23T09:00:00Z")
    make_render(args)
    return args


def make_render(args):
    plan = build_plan(args["config"], args["script"])
    asset = Path(plan["state_root"]) / "renders" / f"{plan['project_id']}.{args['run_id']}.mp4"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"owned completed video")
    import os
    sidecar = Path(os.environ["LM_DATA_DIR"]) / "marketing/ebook/runs" / f"factory.{plan['project_id']}.{args['run_id']}.heygen-effect.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps({"schema_version": "marketing.heygen-effect.v1", "renderer_id": "heygen-avatar-iv",
          "request_sha256": plan["request_sha256"], "output": str(asset), "state": "completed",
          "video_id": "video123", "provider_status": "completed", "wallet_cost": {"amount_usd": "0.50"},
          "output_sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}))
    return asset, sidecar


def prepare(args):
    return publish_from_config(**args, operation="prepare")


def approve(result):
    intent = json.loads(Path(result["intent_path"]).read_text())
    record_visual_approval(ledger_path=Path(result["approvals_path"]),
        approval_id=intent["visual_approval_id"], asset_path=Path(intent["asset_path"]),
        product_id=intent["product_id"], account_id=intent["account_id"],
        owner_confirmation="Fixture owner confirmed this exact asset", confirmation_ref="fixture://visual-review",
        approved_at="2026-10-23T09:00:00Z")
    return intent


def client(args, **kwargs):
    return FakePostiz(integrations=[{"id": args["config"]["postiz"]["integration_id"],
        "identifier": "tiktok", "profile": args["publication"]["native_handle"], "disabled": False}],
        create_result=[{"postId": "factory-post", "integration": args["config"]["postiz"]["integration_id"]}],
        promote_result={"id": "factory-post", "state": "QUEUE"}, **kwargs)


def test_prepare_reuses_shared_store_without_fabricating_approval(request_args):
    first = prepare(request_args)
    again = prepare(request_args)
    assert first["publish_key"] == again["publish_key"]
    assert first["account_id"].startswith("factory.account.")
    assert not Path(first["approvals_path"]).exists()
    assert first["external_mutations"] == 0
    assert IntentStore(Path(first["db_path"])).get(first["publish_key"])["state"] == "registered"


def test_other_project_cannot_reserve_same_integration_slot(request_args):
    first = prepare(request_args)
    other = copy.deepcopy(request_args)
    other["config"]["project_id"] = "other"
    other["config"]["state_root"] += "-other"
    make_render(other)
    with pytest.raises(ValueError, match="slot already reserved"):
        prepare(other)
    assert len(IntentStore(Path(first["db_path"])).attempts_for(first["publish_key"])) == 0


@pytest.mark.parametrize("change", ["caption", "scheduled_at", "state_root", "script"])
def test_same_run_refuses_changed_publication_identity(request_args, change):
    prepare(request_args)
    args = copy.deepcopy(request_args)
    if change == "state_root": args["config"][change] += "-changed"
    elif change == "script": args[change] += " A different sentence."
    elif change == "caption": args["publication"][change] += " Changed."
    else: args["publication"][change] = "2026-10-24T01:00:00Z"
    with pytest.raises(ValueError):
        prepare(args)


@pytest.mark.parametrize("change", ["unknown", "credential", "disabled", "ai_off", "own_business_off", "foreign_provider", "bad_destination"])
def test_invalid_publication_refused_before_provider(request_args, change):
    p = request_args["publication"]
    if change == "unknown": p["extra"] = True
    elif change == "credential": p["api_key"] = "DO_NOT_ECHO_THIS_SECRET"
    elif change == "disabled": p["publish_enabled"] = "true"
    elif change == "ai_off": p["provider_settings"]["video_made_with_ai"] = False
    elif change == "own_business_off": p["provider_settings"]["brand_organic_toggle"] = False
    elif change == "foreign_provider": p["publisher_provider"] = "x"
    else: p["caption"] += " https://example.com/book?utm_campaign=launch-invalid"
    with pytest.raises(ValueError) as error:
        prepare(request_args)
    assert "DO_NOT_ECHO_THIS_SECRET" not in str(error.value)


@pytest.mark.parametrize("field", ["request_sha256", "output_sha256", "video_id", "state"])
def test_render_receipt_must_bind_completed_asset(request_args, field):
    _, sidecar = make_render(request_args)
    row = json.loads(sidecar.read_text()); row[field] = "../wrong" if field == "video_id" else "wrong"
    sidecar.write_text(json.dumps(row))
    with pytest.raises(ValueError): prepare(request_args)


def test_registered_dais_route_cannot_be_reapproved_by_factory(request_args):
    request_args["config"]["postiz"]["integration_id"] = "cmo5rwq2p00twn10yrsdglng3"
    with pytest.raises(ValueError, match="registered"):
        prepare(request_args)


def test_missing_approval_and_production_flag_do_not_upload(request_args):
    result = prepare(request_args); fake = client(request_args)
    with pytest.raises(ValueError, match="production"):
        publish_from_config(**request_args, operation="upload", client=fake, media_probe=lambda _: MEDIA)
    with pytest.raises(ValueError, match="approval"):
        publish_from_config(**request_args, operation="upload", production=True, client=fake, media_probe=lambda _: MEDIA)
    assert fake.upload_calls == fake.create_calls == fake.promote_calls == 0
    assert not Path(result["approvals_path"]).exists()


def test_each_provider_operation_is_fenced_and_scheduled_is_not_published(request_args):
    result = prepare(request_args); approve(result); fake = client(request_args)
    for operation in ("upload", "draft", "promote"):
        first = publish_from_config(**request_args, operation=operation, production=True, client=fake, media_probe=lambda _: MEDIA)
        second = publish_from_config(**request_args, operation=operation, production=True, client=fake, media_probe=lambda _: MEDIA)
        assert first["state"] == second["state"] == "accepted"
    assert (fake.upload_calls, fake.create_calls, fake.promote_calls) == (1, 1, 1)
    status = publish_from_config(**request_args, operation="status")
    assert status["state"] == "scheduled" and status["native_post_url"] is None


def test_uncertain_upload_is_not_resent(request_args):
    result = prepare(request_args); approve(result)
    fake = client(request_args, upload_error=TimeoutError("fixture timeout"))
    for _ in range(2):
        publish_from_config(**request_args, operation="upload", production=True, client=fake, media_probe=lambda _: MEDIA)
    assert fake.upload_calls == 1
    assert IntentStore(Path(result["db_path"])).attempts_for(result["publish_key"])[0]["state"] == "uncertain"


def test_disabled_live_route_blocks_mutation(request_args):
    result = prepare(request_args); approve(result); fake = client(request_args)
    fake.integrations[0]["disabled"] = True
    with pytest.raises(ValueError, match="route"):
        publish_from_config(**request_args, operation="upload", production=True, client=fake, media_probe=lambda _: MEDIA)
    assert fake.upload_calls == 0


def test_status_after_schedule_does_not_recreate_future_intent(request_args):
    result = prepare(request_args)
    request_args["now"] = "2026-10-25T00:00:00Z"
    status = publish_from_config(**request_args, operation="status")
    assert status["publish_key"] == result["publish_key"]


def test_factory_publish_is_available_at_real_cli_boundary(tmp_path):
    result = subprocess.run([sys.executable, str(HERE / "bin/lm"), "factory", "publish", "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "--publication" in result.stdout and "--operation" in result.stdout


@pytest.mark.parametrize("run_id", ["../escape", "", "A", "x" * 65])
def test_invalid_run_does_not_create_factory_store(request_args, run_id):
    request_args["run_id"] = run_id
    import os
    with pytest.raises(ValueError, match="run ID"):
        prepare(request_args)
    assert not (Path(os.environ["LM_DATA_DIR"]) / "marketing/ebook/factory").exists()


def test_registered_handle_cannot_bypass_owner_with_another_integration(request_args):
    request_args["publication"]["native_handle"] = "monk_anicca"
    with pytest.raises(ValueError, match="registered"):
        prepare(request_args)


def test_cost_unknown_asset_preserves_unknown_without_regenerating(request_args):
    _, sidecar = make_render(request_args)
    row = json.loads(sidecar.read_text())
    row.update(state="cost_reconciliation_required", wallet_cost=None)
    sidecar.write_text(json.dumps(row))
    result = prepare(request_args)
    assert result["wallet_cost"] is None and result["cost_reconciliation_required"] is True


def test_host_gate_denial_does_not_dispatch(request_args, monkeypatch):
    result = prepare(request_args); approve(result); fake = client(request_args)
    monkeypatch.setattr("factory_publish._host_disk_admission", lambda: False)
    deferred = publish_from_config(**request_args, operation="upload", production=True, client=fake, media_probe=lambda _: MEDIA)
    assert deferred["state"] == "deferred"
    assert fake.integration_calls == fake.upload_calls == 0


def test_changed_asset_cannot_use_prior_visual_approval(request_args):
    result = prepare(request_args); approve(result); fake = client(request_args)
    Path(json.loads(Path(result["intent_path"]).read_text())["asset_path"]).write_bytes(b"different video")
    with pytest.raises(ValueError, match="hash"):
        publish_from_config(**request_args, operation="upload", production=True, client=fake, media_probe=lambda _: MEDIA)
    assert fake.upload_calls == 0


def test_instagram_context_keeps_standalone_provider_and_own_destination(request_args):
    request_args["config"]["postiz"]["platform"] = "instagram"
    request_args["publication"]["publisher_provider"] = "instagram-standalone"
    request_args["publication"]["provider_settings"] = {"__type": "instagram-standalone", "post_type": "post", "is_trial_reel": False, "collaborators": []}
    result = prepare(request_args)
    intent = json.loads(Path(result["intent_path"]).read_text())
    assert intent["platform"] == "instagram"
    assert "https://example.com/book?utm_campaign=launch" in intent["caption"]
    assert intent["provider_settings"]["__type"] == "instagram-standalone"


def test_intent_file_cannot_point_to_a_different_stored_publication(request_args):
    first = prepare(request_args)
    other = copy.deepcopy(request_args)
    other["run_id"] = "second"
    other["publication"]["scheduled_at"] = "2026-10-24T01:00:00Z"
    make_render(other)
    second = prepare(other)
    path = Path(first["intent_path"])
    row = json.loads(path.read_text()); row["publish_key"] = second["publish_key"]
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="immutable"):
        publish_from_config(**request_args, operation="status")


def test_real_cli_prepare_uses_user_route_and_creates_no_approval(request_args, tmp_path):
    import os
    files = [tmp_path / name for name in ("config.json", "script.txt", "publication.json")]
    files[0].write_text(json.dumps(request_args["config"]))
    files[1].write_text(request_args["script"])
    publication = request_args["publication"] | {"scheduled_at": "2099-01-01T00:00:00Z"}
    files[2].write_text(json.dumps(publication))
    result = subprocess.run([sys.executable, str(HERE / "bin/lm"), "factory", "publish",
        "--config", str(files[0]), "--script", str(files[1]), "--publication", str(files[2]),
        "--run-id", "first", "--operation", "prepare"], capture_output=True, text=True,
        env={"PATH": os.defpath, "HOME": str(tmp_path / "home"), "LM_DATA_DIR": os.environ["LM_DATA_DIR"],
             "LIFE_MANAGER_HEYGEN": "/factory-test-no-provider", "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert row["status"] == "intent_ready" and row["external_mutations"] == 0
    assert not Path(row["approvals_path"]).exists()
    intent = json.loads(Path(row["intent_path"]).read_text())
    assert intent["native_handle"] == "factory_test_monk"
    assert intent["integration_id"] == "factory-test-integration"


@pytest.mark.parametrize("same_instant", ["2026-10-24T09:00:00+09:00", "2026-10-24T00:00:00+00:00", "2026-10-24T00:00:00.000Z"])
def test_same_epoch_slot_cannot_be_reused_with_a_different_timezone_format(request_args, same_instant):
    prepare(request_args)
    other = copy.deepcopy(request_args)
    other["config"]["project_id"] = "other"
    other["config"]["state_root"] += "-other"
    other["publication"]["scheduled_at"] = same_instant
    make_render(other)
    with pytest.raises(ValueError, match="slot already reserved"):
        prepare(other)
