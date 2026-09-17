from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


capacity = _load("writer_capacity_floor_w2", SCRIPTS / "writer_capacity_floor.py")
demand = _load("demand_card_w2", SCRIPTS / "demand_card.py")
image = _load("gpt_image_headline_w2", SCRIPTS / "gpt_image_headline.py")


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _observation(observation_id: str, url: str, family: str) -> dict[str, str]:
    body = f"Official full demand receipt for {observation_id} from {url}."
    return {
        "observation_id": observation_id,
        "source_family": family,
        "source_url": url,
        "full_body": body,
        "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "capture_method": "http_full_body",
    }


def _bindings() -> dict[str, object]:
    return {
        "buyer": "technical editors",
        "problem": "finding accepted work",
        "transformation": "publish-ready article",
        "deliverable": "one article",
        "price_hypothesis": {"amount": 49, "currency": "USD", "basis": "receipt"},
        "distribution_path": [{"channel": "publisher", "role": "submission"}],
        "binding_observation_ids": {
            field: ["duplicate-id"]
            for field in (
                "buyer",
                "problem",
                "transformation",
                "deliverable",
                "price_hypothesis",
                "distribution_path",
            )
        },
    }


def test_w2_boundaries_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capacity_receipt = tmp_path / "capacity" / "article-run-floor.json"
    capacity_receipt.parent.mkdir()
    capacity_receipt.write_text(
        json.dumps(
            {
                "schema": "writer.capacity-receipt",
                "version": 1,
                # JSON booleans are not measured integer counters.
                "observed_consumption_kib": True,
                "atomic_reserve_kib": 524_288,
                "required_free_kib": 524_289,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ARTICLE_CAPACITY_RECEIPT", raising=False)
    monkeypatch.delenv("ARTICLE_DISK_MIN_FREE_BYTES", raising=False)
    with pytest.raises(capacity.CapacityFloorError, match="capacity_receipt_invalid"):
        capacity.resolve_disk_floor_bytes(tmp_path)

    monkeypatch.setenv("ARTICLE_DISK_MIN_FREE_BYTES", "1")
    capacity_receipt.unlink()
    with pytest.raises(
        capacity.CapacityFloorError, match="disk_headroom_configuration_invalid"
    ):
        capacity.resolve_disk_floor_bytes(tmp_path)

    monkeypatch.setenv(
        "GIG_DISK_HEADROOM_KIB", str(capacity.CANONICAL_DISK_HEADROOM_KIB * 2)
    )
    monkeypatch.setenv(
        "ARTICLE_DISK_MIN_FREE_BYTES", str(capacity.CANONICAL_DISK_HEADROOM_BYTES)
    )
    with pytest.raises(
        capacity.CapacityFloorError, match="disk_headroom_configuration_invalid"
    ):
        capacity.resolve_disk_floor_bytes(tmp_path)
    monkeypatch.setenv(
        "GIG_DISK_HEADROOM_KIB", str(capacity.CANONICAL_DISK_HEADROOM_KIB)
    )

    observations = [
        _observation("duplicate-id", "https://paid.example/offer", "paid_market"),
        _observation("duplicate-id", "https://demand.example/job", "reader_demand"),
        _observation("publisher-id", "https://publisher.example/apply", "publisher_opportunity"),
        _observation("funnel-id", "https://funnel.example/cta", "owned_funnel"),
    ]
    with pytest.raises(demand.DemandCardError, match="unique"):
        demand.build_demand_card(observations, _bindings())

    prompt = tmp_path / "prompt.txt"
    alt = tmp_path / "alt.txt"
    candidate = tmp_path / "candidate.png"
    intent = tmp_path / "intent.json"
    receipt = tmp_path / "receipt.json"
    prompt.write_text("A specific article visual", encoding="utf-8")
    alt.write_text("An honest article visual", encoding="utf-8")
    candidate.write_bytes(PNG)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    with pytest.raises(image.HeadlineImageRefused, match="candidate-without-receipt"):
        image.generate(
            prompt_path=prompt,
            alt_path=alt,
            candidate=candidate,
            intent_path=intent,
            receipt_path=receipt,
            opener=lambda *_args, **_kwargs: pytest.fail("unreceipted candidate was sent"),
        )

    candidate.unlink()

    def unknown_opener(*_args: object, **_kwargs: object) -> object:
        raise TimeoutError("response delivery is unknown")

    with pytest.raises(image.HeadlineImageRefused, match="reconcile-before-retry"):
        image.generate(
            prompt_path=prompt,
            alt_path=alt,
            candidate=candidate,
            intent_path=intent,
            receipt_path=receipt,
            opener=unknown_opener,
        )
    assert json.loads(intent.read_text(encoding="utf-8"))["status"] == "delivery_unknown"
    assert not receipt.exists()
    with pytest.raises(image.HeadlineImageRefused, match="reconcile-before-retry"):
        image.generate(
            prompt_path=prompt,
            alt_path=alt,
            candidate=candidate,
            intent_path=intent,
            receipt_path=receipt,
            opener=lambda *_args, **_kwargs: pytest.fail("unknown delivery was retried"),
        )
