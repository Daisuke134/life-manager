import hashlib
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "claim_supply.py"
SPEC = importlib.util.spec_from_file_location("claim_supply", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _row(observation_id: str, url: str, family: str) -> dict:
    body = f"Full official body for {observation_id} with paid acceptance terms."
    return {
        "observation_id": observation_id,
        "source_family": family,
        "source_url": url,
        "full_body": body,
        "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "capture_method": "http_full_body",
    }


def test_full_body_normalization_preserves_model_bindings() -> None:
    observations = [
        _row("publisher-1", "https://techi.com/authors", "publisher_opportunity"),
        _row("publisher-2", "https://civo.com/write", "publisher_opportunity"),
    ]
    card = {
        "buyer": "technical editors",
        "problem": "finding accepted work",
        "transformation": "publish-ready article",
        "deliverable": "one article",
        "price_hypothesis": {"amount": 49, "currency": "USD", "basis": "receipt"},
        "distribution_path": [{"channel": "publisher", "role": "submission"}],
        "observation_ids": ["publisher-1", "publisher-2"],
    }

    normalized = MODULE._normalize_model_demand_observation_ids(card, observations)

    assert normalized["buyer"] == "technical editors"
    assert normalized["deliverable"] == "one article"
    assert normalized["observation_ids"] == ["publisher-1", "publisher-2"]


def test_normalization_includes_selected_binding_receipts() -> None:
    observations = [
        _row("publisher-1", "https://techi.com/authors", "publisher_opportunity"),
        _row("price-1", "https://example.com/rate", "paid_market"),
    ]
    card = {
        "observation_ids": ["publisher-1"],
        "binding_observation_ids": {"price_hypothesis": ["price-1"]},
    }

    normalized = MODULE._normalize_model_demand_observation_ids(card, observations)

    assert normalized["observation_ids"] == ["publisher-1", "price-1"]


def test_nfkc_equivalent_observation_and_binding_ids_share_normalization() -> None:
    observations = [
        _row("ｐｕｂｌｉｓｈｅｒ－１", "https://techi.com/authors", "publisher_opportunity"),
        _row("price-1", "https://example.com/rate", "paid_market"),
        _row("reader-1", "https://reader.example/job", "reader_demand"),
        _row("funnel-1", "https://funnel.example/cta", "owned_funnel"),
    ]
    fields = (
        "buyer",
        "problem",
        "transformation",
        "deliverable",
        "price_hypothesis",
        "distribution_path",
    )
    card = {
        "buyer": "technical editors",
        "problem": "finding accepted work",
        "transformation": "publish-ready article",
        "deliverable": "one article",
        "price_hypothesis": {"amount": 49, "currency": "USD", "basis": "receipt"},
        "distribution_path": [{"channel": "publisher", "role": "submission"}],
        "observation_ids": ["publisher-1", "price-1", "reader-1", "funnel-1"],
        "binding_observation_ids": {
            field: ["ｐｕｂｌｉｓｈｅｒ－１"] for field in fields
        },
    }

    normalized = MODULE._normalize_model_demand_observation_ids(card, observations)
    assert normalized["observation_ids"] == [
        "publisher-1", "price-1", "reader-1", "funnel-1"
    ]

    demand_card = MODULE.build_demand_card(
        observations,
        {field: normalized[field] for field in fields}
        | {"binding_observation_ids": normalized["binding_observation_ids"]},
    )
    assert demand_card["observations"][0]["observation_id"] == "publisher-1"
    assert demand_card["binding_observation_ids"]["buyer"] == ["publisher-1"]
