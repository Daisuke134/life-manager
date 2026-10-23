#!/usr/bin/env python3
"""Load and validate the product, account, and renderer routing registry."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from dataclasses import dataclass


PRODUCT_FIELDS = {
    "schema_version", "product_id", "type", "live_status", "destination_url",
    "price", "approved_claims", "cta", "conversion_events", "revenue_events",
    "margin_rule", "audiences", "metric_adapters", "primary_metric",
    "attribution_method",
}
PRODUCT_TYPES = {"ios_app", "ebook", "web_app", "marketplace_agent"}
MARKETPLACE_PROFILE_FIELDS = {
    "economic_role", "related_loop_id", "buyer_problem", "offer_snapshot",
    "allowed_channel_accounts", "destination", "outcome_sources",
}
BUYER_PROBLEM_FIELDS = {"statement", "source_ref", "validation_status"}
OFFER_SNAPSHOT_FIELDS = {
    "seller_agent_id", "published_version", "observed_at", "latest_public_readback_at",
    "price_status", "frozen", "trial_days", "price_tiers", "source_refs", "source_conflicts",
}
PRICE_TIER_FIELDS = {"period", "amount", "currency", "cap"}
SOURCE_CONFLICT_FIELDS = {"source_ref", "detail", "resolution"}
CHANNEL_ACCOUNT_FIELDS = {
    "account_ref", "platform", "native_handle", "publisher_integration_id",
    "campaign_token", "last_observed_at", "operational_status", "publish_enabled",
}
DESTINATION_FIELDS = {"url", "campaign_token", "per_slot_attribution", "source_ref"}
OUTCOME_SOURCE_FIELDS = {
    "metric", "source", "status", "attribution_granularity", "source_ref",
}
ACCOUNT_FIELDS = {
    "schema_version", "account_id", "product_id", "product_ids", "platform",
    "native_handle", "publisher_integration_id", "integration_null_reason",
    "publisher_provider", "publisher_settings", "language", "audience",
    "allowed_renderer_ids", "status",
}
RENDERER_FIELDS = {
    "schema_version", "renderer_id", "kind", "languages", "status",
}
PRODUCT_ID_ALIASES = {
    "aniccaios": "anicca-ios",
    "honne": "honne-ai",
}


class RoutingError(ValueError):
    pass


def canonical_product_id(product_id: object) -> object:
    """Map identifiers emitted by the predecessor runtime at read boundaries."""

    if not isinstance(product_id, str):
        return product_id
    return PRODUCT_ID_ALIASES.get(product_id, product_id)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RoutingError(message)


def load_object(path: pathlib.Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"manifest must be an object: {path}")
    return value


def _validate_timezone_datetime(value: object, field: str, path: pathlib.Path) -> None:
    require(isinstance(value, str) and value, f"marketplace {field} missing: {path}")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RoutingError(f"marketplace {field} invalid: {path}") from None
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"marketplace {field} must include timezone: {path}")


def _validate_text_fields(row: dict, fields: set[str], label: str, path: pathlib.Path) -> None:
    for field in fields:
        require(isinstance(row[field], str) and row[field].strip(),
                f"marketplace {label} {field} missing: {path}")


def _validate_distribution_profile(profile: object, path: pathlib.Path) -> None:
    require(isinstance(profile, dict) and set(profile) == MARKETPLACE_PROFILE_FIELDS,
            f"marketplace distribution_profile fields differ: {path}")
    _validate_text_fields(profile, {"economic_role", "related_loop_id"},
                          "distribution_profile", path)

    buyer = profile["buyer_problem"]
    require(isinstance(buyer, dict) and set(buyer) == BUYER_PROBLEM_FIELDS,
            f"marketplace buyer_problem fields differ: {path}")
    _validate_text_fields(buyer, BUYER_PROBLEM_FIELDS, "buyer_problem", path)

    offer = profile["offer_snapshot"]
    require(isinstance(offer, dict) and set(offer) == OFFER_SNAPSHOT_FIELDS,
            f"marketplace offer_snapshot fields differ: {path}")
    _validate_text_fields(offer, {"seller_agent_id", "published_version", "price_status"},
                          "offer_snapshot", path)
    require(offer["price_status"] in {"current_verified", "stale_unverified"},
            f"marketplace offer_snapshot price_status invalid: {path}")
    _validate_timezone_datetime(offer["observed_at"], "offer_snapshot observed_at", path)
    _validate_timezone_datetime(offer["latest_public_readback_at"],
                                "offer_snapshot latest_public_readback_at", path)
    require(isinstance(offer["frozen"], bool),
            f"marketplace offer_snapshot frozen invalid: {path}")
    require(isinstance(offer["trial_days"], int) and not isinstance(offer["trial_days"], bool)
            and offer["trial_days"] >= 0, f"marketplace offer_snapshot trial_days invalid: {path}")
    tiers = offer["price_tiers"]
    require(isinstance(tiers, list) and tiers, f"marketplace offer_snapshot price_tiers missing: {path}")
    tier_periods: set[str] = set()
    for tier in tiers:
        require(isinstance(tier, dict) and set(tier) == PRICE_TIER_FIELDS,
                f"marketplace offer_snapshot price_tier fields differ: {path}")
        _validate_text_fields(tier, {"period", "currency"}, "price_tier", path)
        require(tier["period"] not in tier_periods,
                f"marketplace offer_snapshot duplicate price period: {path}")
        tier_periods.add(tier["period"])
        require(isinstance(tier["amount"], (int, float)) and not isinstance(tier["amount"], bool)
                and tier["amount"] >= 0, f"marketplace offer_snapshot price amount invalid: {path}")
        require(isinstance(tier["cap"], int) and not isinstance(tier["cap"], bool)
                and tier["cap"] >= 1, f"marketplace offer_snapshot price cap invalid: {path}")
    require(isinstance(offer["source_refs"], list) and offer["source_refs"] and
            all(isinstance(ref, str) and ref.strip() for ref in offer["source_refs"]),
            f"marketplace offer_snapshot source_refs invalid: {path}")
    require(isinstance(offer["source_conflicts"], list),
            f"marketplace offer_snapshot source_conflicts invalid: {path}")
    for conflict in offer["source_conflicts"]:
        require(isinstance(conflict, dict) and set(conflict) == SOURCE_CONFLICT_FIELDS,
                f"marketplace offer_snapshot source_conflict fields differ: {path}")
        _validate_text_fields(conflict, SOURCE_CONFLICT_FIELDS, "source_conflict", path)

    channels = profile["allowed_channel_accounts"]
    require(isinstance(channels, list) and channels,
            f"marketplace allowed_channel_accounts missing: {path}")
    for channel in channels:
        require(isinstance(channel, dict) and set(channel) == CHANNEL_ACCOUNT_FIELDS,
                f"marketplace allowed_channel_account fields differ: {path}")
        _validate_text_fields(channel, {
            "account_ref", "platform", "native_handle", "publisher_integration_id",
            "campaign_token", "operational_status",
        }, "allowed_channel_account", path)
        require(channel["platform"] in {"instagram", "tiktok", "youtube"},
                f"marketplace allowed_channel_account platform invalid: {path}")
        _validate_timezone_datetime(channel["last_observed_at"],
                                    "allowed_channel_account last_observed_at", path)
        require(isinstance(channel["publish_enabled"], bool),
                f"marketplace allowed_channel_account publish_enabled invalid: {path}")

    destination = profile["destination"]
    require(isinstance(destination, dict) and set(destination) == DESTINATION_FIELDS,
            f"marketplace destination fields differ: {path}")
    _validate_text_fields(destination, DESTINATION_FIELDS, "destination", path)
    require(destination["url"].startswith("https://"),
            f"marketplace destination must be https: {path}")

    outcomes = profile["outcome_sources"]
    require(isinstance(outcomes, list) and outcomes,
            f"marketplace outcome_sources missing: {path}")
    metrics: set[str] = set()
    for outcome in outcomes:
        require(isinstance(outcome, dict) and set(outcome) == OUTCOME_SOURCE_FIELDS,
                f"marketplace outcome_sources fields differ: {path}")
        _validate_text_fields(outcome, OUTCOME_SOURCE_FIELDS, "outcome_source", path)
        require(outcome["metric"] not in metrics,
                f"marketplace outcome_sources duplicate metric: {path}")
        metrics.add(outcome["metric"])
    require({"settled_net_contribution", "actual_model_cost"} <= metrics,
            f"marketplace outcome_sources missing settled_net_contribution or actual_model_cost: {path}")


@dataclass(frozen=True)
class Registry:
    engine: pathlib.Path
    products: dict[str, dict]
    accounts: dict[str, dict]
    renderers: dict[str, dict]


def _validate_product(row: dict, path: pathlib.Path) -> None:
    require(row.get("type") in PRODUCT_TYPES, f"product type invalid: {path}")
    has_profile = "distribution_profile" in row
    expected_fields = PRODUCT_FIELDS | ({"distribution_profile"} if has_profile else set())
    require(set(row) == expected_fields, f"product fields differ: {path}")
    require(row["schema_version"] == "marketing.product.v1", f"product schema differs: {path}")
    if row["type"] == "marketplace_agent":
        require(has_profile, f"marketplace product requires distribution_profile: {path}")
    require(isinstance(row["destination_url"], str) and row["destination_url"].startswith("https://"),
            f"product destination must be https: {path}")
    price = row["price"]
    require(isinstance(price, dict) and set(price) == {"amount", "currency", "basis"},
            f"product price invalid: {path}")
    require(isinstance(price["amount"], (int, float)) and price["amount"] >= 0,
            f"product price amount invalid: {path}")
    for field in ("approved_claims", "conversion_events", "revenue_events", "audiences",
                  "metric_adapters"):
        require(isinstance(row[field], list) and row[field] and
                all(isinstance(item, str) and item for item in row[field]),
                f"product {field} invalid: {path}")
    for field in ("product_id", "live_status", "cta", "margin_rule", "primary_metric",
                  "attribution_method"):
        require(isinstance(row[field], str) and row[field], f"product {field} missing: {path}")
    if has_profile:
        profile = row["distribution_profile"]
        _validate_distribution_profile(profile, path)
        destination = profile["destination"]
        require(destination["url"] == row["destination_url"],
                f"marketplace destination differs from product destination_url: {path}")
        channel_tokens = {
            channel["campaign_token"] for channel in profile["allowed_channel_accounts"]
        }
        require(destination["campaign_token"] in channel_tokens,
                f"marketplace destination campaign_token has no allowed channel account: {path}")
        outcome_metrics = {outcome["metric"] for outcome in profile["outcome_sources"]}
        require(row["primary_metric"] in outcome_metrics,
                f"marketplace primary_metric has no outcome_source: {path}")


def _validate_renderer(row: dict, path: pathlib.Path) -> None:
    require(set(row) == RENDERER_FIELDS, f"renderer fields differ: {path}")
    require(row["schema_version"] == "marketing.renderer.v1", f"renderer schema differs: {path}")
    require(isinstance(row["languages"], list) and row["languages"],
            f"renderer languages invalid: {path}")
    require(row["status"] in {"baseline", "challenger", "restricted"},
            f"renderer status invalid: {path}")


def _validate_account(row: dict, path: pathlib.Path, products: dict, renderers: dict) -> None:
    require(set(row) == ACCOUNT_FIELDS, f"account fields differ: {path}")
    require(row["schema_version"] == "marketing.account.v1", f"account schema differs: {path}")
    require(isinstance(row["product_ids"], list) and len(row["product_ids"]) == 1,
            f"account must have exactly one product: {path}")
    require(row["product_ids"][0] == row["product_id"], f"account product fields differ: {path}")
    require(row["product_id"] in products, f"account product unknown: {path}")
    require(row["platform"] in {"tiktok", "instagram", "youtube"},
            f"account platform invalid: {path}")
    require(row["language"] in {"en", "ja"}, f"account language invalid: {path}")
    require(isinstance(row["allowed_renderer_ids"], list) and row["allowed_renderer_ids"],
            f"account renderer list invalid: {path}")
    require(set(row["allowed_renderer_ids"]) <= set(renderers),
            f"account renderer unknown: {path}")
    if row["publisher_integration_id"] is None:
        require(isinstance(row["integration_null_reason"], str) and row["integration_null_reason"],
                f"account integration null reason missing: {path}")
        require(row["publisher_provider"] is None and row["publisher_settings"] is None,
                f"account without integration cannot have provider settings: {path}")
    else:
        require(isinstance(row["publisher_integration_id"], str) and
                row["publisher_integration_id"], f"account integration invalid: {path}")
        require(row["integration_null_reason"] is None,
                f"account integration null reason must be null: {path}")
        provider = row["publisher_provider"]
        settings = row["publisher_settings"]
        require(isinstance(provider, str) and provider, f"account publisher provider invalid: {path}")
        require(isinstance(settings, dict) and settings.get("__type") == provider,
                f"account publisher settings invalid: {path}")
        if row["platform"] == "tiktok":
            required = {"__type", "title", "privacy_level", "duet", "stitch", "comment",
                        "autoAddMusic", "brand_content_toggle", "brand_organic_toggle",
                        "video_made_with_ai", "content_posting_method"}
            require(provider == "tiktok" and set(settings) == required,
                    f"TikTok provider settings incomplete: {path}")
            require(settings["privacy_level"] in {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS",
                                                   "SELF_ONLY", "FOLLOWER_OF_CREATOR"},
                    f"TikTok privacy invalid: {path}")
            require(settings["autoAddMusic"] in {"yes", "no"} and
                    settings["content_posting_method"] in {"DIRECT_POST", "UPLOAD"},
                    f"TikTok posting settings invalid: {path}")
            for field in ("duet", "stitch", "comment", "brand_content_toggle",
                          "brand_organic_toggle", "video_made_with_ai"):
                require(isinstance(settings[field], bool), f"TikTok boolean invalid: {path}")
        elif row["platform"] == "instagram":
            require(provider in {"instagram", "instagram-standalone"} and settings == {
                "__type": provider, "post_type": "post", "is_trial_reel": False,
                "collaborators": []}, f"Instagram provider settings invalid: {path}")
        elif row["platform"] == "youtube":
            required = {"__type", "title", "type", "selfDeclaredMadeForKids", "thumbnail", "tags"}
            require(provider == "youtube" and set(settings) == required,
                    f"YouTube provider settings incomplete: {path}")
            require(2 <= len(settings["title"]) <= 100 and
                    settings["type"] in {"public", "private", "unlisted"} and
                    settings["selfDeclaredMadeForKids"] in {"yes", "no"} and
                    settings["thumbnail"] is None and isinstance(settings["tags"], list),
                    f"YouTube provider settings invalid: {path}")
    if "watercolor-monk" in row["allowed_renderer_ids"]:
        require(row["product_id"] == "ebook-ja", "watercolor renderer is restricted to ebook-ja")
    if "heygen-avatar-iv" in row["allowed_renderer_ids"]:
        require(row["product_id"] in {"ebook-en", "ebook-ja"}, "HeyGen renderer is restricted to ebook products")


def load_registry(engine: pathlib.Path) -> Registry:
    engine = pathlib.Path(engine)
    root = engine / "registry"
    products: dict[str, dict] = {}
    for path in sorted((root / "products").glob("*.json")):
        row = load_object(path)
        _validate_product(row, path)
        product_id = row["product_id"]
        require(product_id not in products, f"duplicate product_id: {product_id}")
        products[product_id] = row
    require(bool(products), "product registry is empty")

    renderer_doc = load_object(root / "renderers.json")
    require(renderer_doc.get("schema_version") == "marketing.renderer-registry.v1" and
            isinstance(renderer_doc.get("renderers"), list), "renderer registry invalid")
    renderers: dict[str, dict] = {}
    for row in renderer_doc["renderers"]:
        _validate_renderer(row, root / "renderers.json")
        require(row["renderer_id"] not in renderers, f"duplicate renderer: {row['renderer_id']}")
        renderers[row["renderer_id"]] = row

    accounts: dict[str, dict] = {}
    native_keys: set[tuple[str, str]] = set()
    for path in sorted((root / "accounts").glob("*.json")):
        row = load_object(path)
        _validate_account(row, path, products, renderers)
        account_id = row["account_id"]
        native_key = (row["platform"], row["native_handle"].lower())
        require(account_id not in accounts, f"duplicate account_id: {account_id}")
        require(native_key not in native_keys, f"duplicate native account: {native_key}")
        accounts[account_id] = row
        native_keys.add(native_key)
    require(bool(accounts), "account registry is empty")
    return Registry(engine=engine, products=products, accounts=accounts, renderers=renderers)
