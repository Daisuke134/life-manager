#!/usr/bin/env python3
"""Safe CLI operations for the durable publication boundary."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

import jsonschema

from intent_store import IntentStore, build_intent
from postiz_adapter import HttpPostizClient, PostizAdapter, parse_time, unique_remote_match
from preflight import probe_media, validate_preflight
from route_status import evaluate_route
from reconcile import reconcile_postiz_result
from approval_store import record_visual_approval
from browser_adapter import unique_native_match
from native_candidates import collect_tiktok_candidates, write_candidates, write_json_atomic


def run_create_intent(*, engine: pathlib.Path, output_path: pathlib.Path,
                      experiment_id: str, creative_id: str, product_id: str,
                      account_id: str, hook_id: str, renderer_id: str, adapter: str,
                      asset_path: pathlib.Path, caption: str, attribution_token: str,
                      scheduled_at: str, visual_approval_id: str,
                      now: str | None = None, script_db_path: pathlib.Path | None = None,
                      script_id: str | None = None) -> dict:
    import sys
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry

    registry = load_registry(engine)
    if product_id not in registry.products:
        raise ValueError("publication product unknown")
    if account_id not in registry.accounts:
        raise ValueError("publication account unknown")
    account = registry.accounts[account_id]
    product = registry.products[product_id]
    if account["product_id"] != product_id:
        raise ValueError("account product mismatch")
    if renderer_id not in account["allowed_renderer_ids"]:
        raise ValueError("renderer not allowed for account")
    if adapter not in {"postiz", "browser"}:
        raise ValueError("publication adapter unsupported")
    if not account["publisher_integration_id"] or not account["publisher_settings"]:
        raise ValueError("account publisher route is not configured")
    normalized_caption = " ".join(caption.split())
    if product_id == "hook-lab":
        measure_dir = pathlib.Path(engine) / "measure"
        if str(measure_dir) not in sys.path:
            sys.path.insert(0, str(measure_dir))
        from attribution import publication_campaign_token

        expected_token = publication_campaign_token({
            "experiment_id": experiment_id,
            "creative_id": creative_id,
            "product_id": product_id,
            "account_id": account_id,
            "hook_id": hook_id,
            "renderer_id": renderer_id,
            "scheduled_at": scheduled_at,
        })
        registered_ct = ((product.get("distribution_profile") or {}).get("destination") or {}).get("campaign_token")
        if not isinstance(registered_ct, str) or attribution_token not in {registered_ct, expected_token}:
            raise ValueError("Hook Lab attribution token is not registered or publication-bound")
        old_owned_url = f"https://aniccaai.com/go/{attribution_token}"
        owned_url_tokens = [token for token in normalized_caption.split() if old_owned_url in token]
        if owned_url_tokens != [old_owned_url]:
            raise ValueError("Hook Lab owned attribution URL must appear exactly once as a complete token")
        normalized_caption = normalized_caption.replace(
            old_owned_url, f"https://aniccaai.com/go/{expected_token}", 1)
        attribution_token = expected_token
    if product["cta"] not in normalized_caption:
        raise ValueError("product CTA missing from caption")
    owned_url = f"https://aniccaai.com/go/{attribution_token}"
    if owned_url not in normalized_caption:
        raise ValueError("owned attribution URL missing from caption")
    if (script_db_path is None) != (script_id is None):
        raise ValueError("script receipt and script ledger must be supplied together")
    if script_id is not None:
        brain = pathlib.Path(engine) / "brain"
        if str(brain) not in sys.path:
            sys.path.insert(0, str(brain))
        from script_ledger import ScriptLedger
        script = ScriptLedger(script_db_path).get(script_id)
        allowed_script_accounts = {account_id, f"product:{product_id}"}
        if (script["product_id"], script["creative_id"], script["renderer_id"]) != (product_id, creative_id, renderer_id) or script["account_id"] not in allowed_script_accounts:
            raise ValueError("script receipt does not bind this publication")

    intent = build_intent(
        experiment_id=experiment_id, creative_id=creative_id,
        product_id=product_id, account_id=account_id, hook_id=hook_id,
        renderer_id=renderer_id, adapter=adapter, asset_path=asset_path,
        caption=normalized_caption, attribution_token=attribution_token,
        scheduled_at=scheduled_at,
        integration_id=account["publisher_integration_id"],
        platform=account["platform"], native_handle=account["native_handle"],
        provider_settings=account["publisher_settings"],
        visual_approval_id=visual_approval_id, script_id=script_id)
    current = parse_time(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("timestamp timezone required")
    if parse_time(intent["scheduled_at"]) <= current:
        raise ValueError("scheduled time must be in the future")
    schema = json.loads((pathlib.Path(engine) / "schemas/publication-intent.schema.json").read_text(
        encoding="utf-8"))
    jsonschema.validate(intent, schema)

    output = pathlib.Path(output_path)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != intent:
            raise ValueError("conflicting immutable intent output")
        created = False
    else:
        write_json_atomic(output, intent)
        created = True
    return {"status": "intent_ready", "created": created,
            "publish_key": intent["publish_key"], "output": str(output),
            "external_mutations": 0}


def run_shadow(*, intent_path: pathlib.Path, db_path: pathlib.Path,
               approvals_path: pathlib.Path, owner: str, now: str,
               ttl_seconds: int = 300, engine: pathlib.Path) -> dict:
    intent = json.loads(pathlib.Path(intent_path).read_text(encoding="utf-8"))
    schema = json.loads((pathlib.Path(engine) / "schemas/publication-intent.schema.json").read_text(
        encoding="utf-8"))
    jsonschema.validate(intent, schema)
    store = IntentStore(db_path)
    registration = store.register(intent)
    lease = store.acquire(intent["publish_key"], owner=owner, now=now, ttl_seconds=ttl_seconds)
    if lease is None:
        raise ValueError("publication intent is leased by another worker")
    shadow = PostizAdapter(store, client=None).shadow(
        intent["publish_key"], owner, lease["fence"], now=now)
    blocker = None
    try:
        validate_preflight(intent, engine=engine, approvals_path=approvals_path)
    except ValueError as exc:
        blocker = str(exc)
    return {
        **shadow,
        "intent_created": registration["created"],
        "dispatchable": blocker is None,
        "preflight_blocker": blocker,
        "lease_fence": lease["fence"],
    }


def run_postiz_operation(*, db_path: pathlib.Path, publish_key: str, operation: str,
                         approvals_path: pathlib.Path, owner: str, now: str,
                         ttl_seconds: int, engine: pathlib.Path, production: bool,
                         client=None, media_probe=probe_media) -> dict:
    if not production:
        raise ValueError("explicit --production flag required")
    if operation not in {"upload", "draft", "promote"}:
        raise ValueError("unsupported Postiz operation")
    store = IntentStore(db_path)
    intent = store.get(publish_key)["intent"]
    validate_preflight(intent, engine=engine, approvals_path=approvals_path,
                       media_probe=media_probe)
    active_client = client or HttpPostizClient(os.environ.get("POSTIZ_API_KEY", ""))
    import sys
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry
    account = load_registry(engine).accounts[intent["account_id"]]
    route = evaluate_route(account, active_client.list_integrations())
    if not route["route_ready"]:
        raise ValueError("publisher route is not ready: " + "; ".join(route["blockers"]))
    lease = store.acquire(publish_key, owner=owner, now=now, ttl_seconds=ttl_seconds)
    if lease is None:
        raise ValueError("publication intent is leased by another worker")
    adapter = PostizAdapter(store, active_client)
    action = {"upload": adapter.upload_media,
              "draft": adapter.create_draft,
              "promote": adapter.promote}[operation]
    result = action(publish_key, owner, lease["fence"], now=now)
    return {**result, "operation": operation, "lease_fence": lease["fence"]}


def run_route_check(*, account_id: str, engine: pathlib.Path, client=None) -> dict:
    import sys
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry

    registry = load_registry(engine)
    if account_id not in registry.accounts:
        raise ValueError("publication account unknown")
    active_client = client or HttpPostizClient(os.environ.get("POSTIZ_API_KEY", ""))
    rows = active_client.list_integrations()
    if not isinstance(rows, list):
        raise ValueError("Postiz integrations response must be a list")
    return evaluate_route(registry.accounts[account_id], rows)


def run_reconcile(*, db_path: pathlib.Path, publish_key: str,
                  post_path: pathlib.Path, native_path: pathlib.Path,
                  ledger_path: pathlib.Path, observed_at: str,
                  engine: pathlib.Path) -> dict:
    import sys
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry

    store = IntentStore(db_path)
    intent = store.get(publish_key)["intent"]
    registry = load_registry(engine)
    account = registry.accounts.get(intent["account_id"])
    if account is None:
        raise ValueError("publication account unknown")
    if account["native_handle"].casefold() != intent["native_handle"].casefold():
        raise ValueError("registry native handle differs from immutable intent")
    post = json.loads(pathlib.Path(post_path).read_text(encoding="utf-8"))
    native_items = json.loads(pathlib.Path(native_path).read_text(encoding="utf-8"))
    if not isinstance(post, dict) or not isinstance(native_items, list):
        raise ValueError("reconciliation inputs have invalid shape")
    return reconcile_postiz_result(
        store=store, publish_key=publish_key, post=post,
        native_items=native_items, expected_handle=intent["native_handle"],
        observed_at=observed_at, ledger_path=ledger_path)


def run_native_candidates(*, db_path: pathlib.Path, publish_key: str,
                          output_path: pathlib.Path, engine: pathlib.Path,
                          cdp_url: str, wait_ms: int,
                          collector=collect_tiktok_candidates,
                          report_path: pathlib.Path | None = None) -> dict:
    import sys
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry

    store = IntentStore(db_path)
    intent = store.get(publish_key)["intent"]
    if intent["platform"] != "tiktok":
        raise ValueError("native candidate collector currently supports TikTok only")
    registry = load_registry(engine)
    account = registry.accounts.get(intent["account_id"])
    if account is None:
        raise ValueError("publication account unknown")
    if account["native_handle"].casefold() != intent["native_handle"].casefold():
        raise ValueError("registry native handle differs from immutable intent")
    scan = collector(expected_handle=intent["native_handle"],
                     cdp_url=cdp_url, wait_ms=wait_ms)
    if (not isinstance(scan, dict) or
            not isinstance(scan.get("api_responses_observed"), int) or
            not isinstance(scan.get("profile_items_observed"), int) or
            not isinstance(scan.get("candidates"), list)):
        raise ValueError("native candidate collector returned invalid evidence")
    rows = scan["candidates"]
    match = unique_native_match(intent, rows, expected_handle=intent["native_handle"])
    selected = [] if match is None else [match]
    schema = json.loads((pathlib.Path(engine) / "schemas/native-candidates.schema.json").read_text(
        encoding="utf-8"))
    jsonschema.validate(selected, schema)
    write_candidates(output_path, selected)
    status = ("collector_unverified" if scan["api_responses_observed"] == 0 else
              "candidate_found" if selected else "pending_native_receipt")
    result = {"schema_version": "marketing.native-candidate-scan.v1",
              "status": status, "publish_key": publish_key,
              "candidate_count": len(selected),
              "api_responses_observed": scan["api_responses_observed"],
              "profile_items_observed": scan["profile_items_observed"],
              "output": str(pathlib.Path(output_path)), "external_mutations": 0}
    report_schema = json.loads((pathlib.Path(engine) /
                                "schemas/native-candidate-scan.schema.json").read_text(
                                    encoding="utf-8"))
    jsonschema.validate(result, report_schema)
    if report_path is not None:
        write_json_atomic(report_path, result)
    return result


def run_postiz_readback(*, db_path: pathlib.Path, publish_key: str,
                        output_path: pathlib.Path,
                        report_path: pathlib.Path | None, client=None) -> dict:
    import datetime as dt

    store = IntentStore(db_path)
    current = store.get(publish_key)
    intent = current["intent"]
    stored_post_id = current.get("provider_post_id")
    if not stored_post_id:
        raise ValueError("Postiz readback requires stored postId")
    scheduled = parse_time(intent["scheduled_at"])
    active_client = client or HttpPostizClient(os.environ.get("POSTIZ_API_KEY", ""))
    rows = active_client.list_posts(scheduled - dt.timedelta(minutes=15),
                                    scheduled + dt.timedelta(minutes=15))
    if not isinstance(rows, list):
        raise ValueError("Postiz posts response must be a list")
    match = unique_remote_match(intent, rows)
    if match is not None and str(match.get("id") or match.get("postId") or "") != stored_post_id:
        raise ValueError("Postiz readback conflicts with stored postId")
    if match is not None:
        store.reconcile_provider(publish_key, match)
        write_json_atomic(output_path, match)
    result = {
        "schema_version": "marketing.postiz-readback.v1",
        "status": "post_found" if match is not None else "pending_provider_receipt",
        "publish_key": publish_key,
        "stored_post_id": stored_post_id,
        "posts_observed": len(rows),
        "output": str(pathlib.Path(output_path)) if match is not None else None,
        "external_mutations": 0,
    }
    schema = json.loads((pathlib.Path(__file__).resolve().parent.parent /
                         "schemas/postiz-readback.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(result, schema)
    if report_path is not None:
        write_json_atomic(report_path, result)
    return result


def run_status(*, db_path: pathlib.Path, publish_key: str) -> dict:
    store = IntentStore(db_path)
    current = store.get(publish_key)
    intent = current["intent"]
    return {
        "schema_version": "marketing.publication-status.v1",
        "publish_key": publish_key,
        "state": current["state"],
        "experiment_id": intent["experiment_id"],
        "product_id": intent["product_id"],
        "account_id": intent["account_id"],
        "native_handle": intent["native_handle"],
        "scheduled_at": intent["scheduled_at"],
        "provider_media_id": current.get("provider_media_id"),
        "provider_post_id": current.get("provider_post_id"),
        "native_post_id": current.get("native_post_id"),
        "native_post_url": current.get("native_post_url"),
        "lease_owner": current.get("lease_owner"),
        "lease_expires_epoch": current.get("lease_expires_epoch"),
        "fence": current.get("fence"),
        "last_error": current.get("last_error"),
        "attempts": store.attempts_for(publish_key),
    }
