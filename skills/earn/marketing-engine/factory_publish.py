"""User-configured Factory publications through the existing fenced publisher."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

from factory_plan import _fields, build_plan
from factory_render import _host_data_root, _host_disk_admission
from ebook_distribute_daily import exclusive_lock
from render_eval.heygen_candidate import IDENTIFIER, require

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "publish"), str(HERE / "gates")]
from intent_store import IntentStore, file_sha256, normalize_caption, stable_id
from publication_context import PublishContext
from product_router import load_registry
from preflight import probe_media
import publish_cli

OPERATIONS = {"prepare", "shadow", "upload", "draft", "promote", "route-check",
              "status", "postiz-readback", "reconcile"}


def _context(config: dict, publication: dict) -> PublishContext:
    _fields(publication, {"schema_version", "native_handle", "publisher_provider", "provider_settings",
                         "publish_enabled", "cta", "caption", "attribution_token", "scheduled_at",
                         "visual_approval_id"}, "publication")
    require(publication["schema_version"] == "ai-monk-factory.publication.v1", "Factory publication schema invalid")
    for key in ("native_handle", "publisher_provider", "cta", "caption", "attribution_token", "scheduled_at", "visual_approval_id"):
        require(isinstance(publication[key], str) and bool(publication[key].strip()) and "\x00" not in publication[key],
                "Factory publication text invalid")
    require(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._]{0,63}", publication["native_handle"]) is not None,
            "Factory native handle invalid")
    require(type(publication["publish_enabled"]) is bool, "Factory publish_enabled must be boolean")
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", publication["attribution_token"]) is not None,
            "Factory attribution token invalid")
    require(publication["attribution_token"] in config["product"]["url"], "Factory tracking token missing from destination")
    caption = normalize_caption(publication["caption"])
    url = config["product"]["url"]
    require([word for word in caption.split() if url in word] == [url], "Factory destination must appear exactly once as a complete token")
    require(publication["cta"] in caption, "Factory CTA missing from caption")
    require(publication["visual_approval_id"].startswith("visual.accepted."), "Factory accepted visual approval ID required")
    try:
        scheduled = publish_cli.parse_time(publication["scheduled_at"])
        require(scheduled.tzinfo is not None, "Factory scheduled timezone required")
    except (ValueError, TypeError):
        raise ValueError("Factory scheduled time invalid") from None
    platform = config["postiz"]["platform"]
    settings = publication["provider_settings"]
    if platform == "tiktok":
        _fields(settings, {"__type", "title", "privacy_level", "duet", "stitch", "comment", "autoAddMusic",
                           "brand_content_toggle", "brand_organic_toggle", "video_made_with_ai", "content_posting_method"}, "TikTok settings")
        require(publication["publisher_provider"] == settings["__type"] == "tiktok", "Factory publisher provider mismatch")
        require(isinstance(settings["title"], str) and len(settings["title"]) <= 90, "Factory TikTok title invalid")
        require(settings["privacy_level"] == "PUBLIC_TO_EVERYONE" and settings["autoAddMusic"] == "no"
                and settings["content_posting_method"] == "DIRECT_POST", "Factory TikTok settings unsupported")
        require(all(type(settings[k]) is bool for k in ("duet", "stitch", "comment")), "Factory TikTok interaction settings invalid")
        require(settings["brand_content_toggle"] is False and settings["brand_organic_toggle"] is True
                and settings["video_made_with_ai"] is True, "Factory own-business and AI disclosure required")
    else:
        require(publication["publisher_provider"] == "instagram-standalone" and settings == {
            "__type": "instagram-standalone", "post_type": "post", "is_trial_reel": False, "collaborators": []},
            "Factory Instagram settings unsupported")
    registry = load_registry(HERE)
    for registered in registry.accounts.values():
        require(not (registered.get("publisher_integration_id") == config["postiz"]["integration_id"] or (
            registered.get("platform") == platform and
            str(registered.get("native_handle") or "").lower().lstrip("@") == publication["native_handle"].lower())),
            "Factory route is already registered; use its existing owner")
    product_id = stable_id("factory.product", [config["product"]["name"], url])
    account_id = stable_id("factory.account", [platform, config["postiz"]["integration_id"]])
    return PublishContext(account={"account_id": account_id, "product_id": product_id,
        "platform": platform, "native_handle": publication["native_handle"],
        "publisher_integration_id": config["postiz"]["integration_id"],
        "publisher_provider": publication["publisher_provider"], "publisher_settings": settings,
        "allowed_renderer_ids": ["heygen-avatar-iv"],
        "status": "approved_active" if publication["publish_enabled"] else "paused"},
        product={"product_id": product_id, "cta": publication["cta"]}, destination_url=url)


def _render_receipt(path: Path, plan: dict, asset: Path) -> dict:
    require(path.is_file(), "Factory render receipt missing")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(receipt, dict) and receipt.get("schema_version") == "marketing.heygen-effect.v1"
            and receipt.get("renderer_id") == "heygen-avatar-iv", "Factory render receipt invalid")
    require(receipt.get("request_sha256") == plan["request_sha256"] and receipt.get("output") == str(asset),
            "Factory render request/output mismatch")
    require(receipt.get("state") in {"completed", "cost_reconciliation_required"}
            and IDENTIFIER.fullmatch(str(receipt.get("video_id") or "")) is not None,
            "Factory completed render receipt required")
    require(receipt.get("state") == "completed" or receipt.get("provider_status") == "completed",
            "Factory provider completion missing")
    require(asset.is_file() and file_sha256(asset) == receipt.get("output_sha256"), "Factory render asset hash mismatch")
    return receipt


def publish_from_config(config: dict, script: str, publication: dict, run_id: str, operation: str, *,
                        production: bool = False, now: str | None = None, client=None,
                        media_probe=probe_media, post_path: Path | None = None,
                        native_path: Path | None = None) -> dict:
    plan = build_plan(config, script)
    require(isinstance(run_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", run_id) is not None,
            "Factory run ID invalid")
    require(operation in OPERATIONS, "Factory publication operation invalid")
    if operation in {"upload", "draft", "promote"}:
        require(production is True, "explicit --production flag required")
    if operation == "reconcile":
        require(post_path is not None and native_path is not None, "Factory post/native evidence required")
    context = _context(config, publication)
    root = _host_data_root() / "marketing/ebook"
    factory_root = root / "factory"
    intent_path = factory_root / "intents" / f"{plan['project_id']}.{run_id}.json"
    db_path = factory_root / "publications.sqlite3"
    approvals = factory_root / "visual-approvals.jsonl"
    asset = Path(plan["state_root"]) / "renders" / f"{plan['project_id']}.{run_id}.mp4"
    expected = {"experiment_id": stable_id("factory.experiment", [plan["project_id"], run_id]),
        "creative_id": stable_id("factory.creative", [plan["project_id"], run_id, plan["request_sha256"]]),
        "product_id": context.product["product_id"], "account_id": context.account["account_id"],
        "hook_id": stable_id("factory.hook", [hashlib.sha256(script.encode()).hexdigest()]),
        "renderer_id": "heygen-avatar-iv", "adapter": "postiz", "asset_path": str(asset.resolve()),
        "caption": normalize_caption(publication["caption"]), "attribution_token": publication["attribution_token"],
        "scheduled_at": publish_cli.parse_time(publication["scheduled_at"]).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "visual_approval_id": publication["visual_approval_id"],
        "integration_id": context.account["publisher_integration_id"], "platform": context.account["platform"],
        "native_handle": context.account["native_handle"], "provider_settings": context.account["publisher_settings"]}
    current = now or dt.datetime.now(dt.timezone.utc).isoformat()
    metadata = {"schema_version": "ai-monk-factory.publication-result.v1", "project_id": plan["project_id"],
        "run_id": run_id, "operation": operation, "account_id": expected["account_id"], "product_id": expected["product_id"],
        "intent_path": str(intent_path), "db_path": str(db_path), "approvals_path": str(approvals)}
    with exclusive_lock(factory_root / "locks" / f"{plan['project_id']}.{run_id}.lock"):
        if intent_path.exists():
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            require(all(intent.get(k) == v for k, v in expected.items()), "conflicting immutable Factory publication")
        else:
            require(operation == "prepare", "Factory publication intent missing; prepare first")
        if operation in {"prepare", "shadow", "upload", "draft", "promote"}:
            receipt = _render_receipt(root / "runs" / f"factory.{plan['project_id']}.{run_id}.heygen-effect.json", plan, asset)
            metadata.update(wallet_cost=receipt.get("wallet_cost"), cost_reconciliation_required=receipt.get("state") == "cost_reconciliation_required")
        if operation == "prepare":
            args = {k: expected[k] for k in ("experiment_id", "creative_id", "product_id", "account_id", "hook_id",
                    "renderer_id", "adapter", "caption", "attribution_token", "scheduled_at", "visual_approval_id")}
            result = publish_cli.run_create_intent(engine=HERE, output_path=intent_path,
                asset_path=asset, now=current, context=context, **args)
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            IntentStore(db_path).register(intent)
        elif operation == "route-check":
            result = publish_cli.run_route_check(account_id=expected["account_id"], engine=HERE, client=client, context=context)
        else:
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            require(IntentStore(db_path).get(intent["publish_key"])["intent"] == intent,
                    "conflicting immutable Factory publication store")
            common = {"db_path": db_path, "publish_key": intent["publish_key"]}
            if operation == "shadow":
                result = publish_cli.run_shadow(intent_path=intent_path, db_path=db_path, approvals_path=approvals,
                    owner=f"factory.{plan['project_id']}.{run_id}", now=current, ttl_seconds=300, engine=HERE, context=context)
            elif operation in {"upload", "draft", "promote"}:
                if not _host_disk_admission():
                    return {**metadata, "state": "deferred", "reason": "host_disk_admission_required", "external_effects": []}
                result = publish_cli.run_postiz_operation(**common, operation=operation, approvals_path=approvals,
                    owner=f"factory.{plan['project_id']}.{run_id}", now=current, ttl_seconds=300, engine=HERE,
                    production=production, client=client, media_probe=media_probe, context=context)
            elif operation == "status":
                result = publish_cli.run_status(**common)
            elif operation == "postiz-readback":
                result = publish_cli.run_postiz_readback(**common, output_path=factory_root / "readbacks" / f"{intent['publish_key']}.postiz.json", report_path=None, client=client)
            else:
                result = publish_cli.run_reconcile(**common, post_path=post_path, native_path=native_path,
                    ledger_path=factory_root / "publication-ledger.jsonl", observed_at=current, engine=HERE, context=context)
    return {**result, **metadata}
