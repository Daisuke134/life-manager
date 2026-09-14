from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ULID = "01KYPJ0M0ACF4DBAFSJVFN9K24"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


snapshot = load("application_snapshot")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("123", "123"), (123, "123"), (ULID, ULID)],
)
def test_canonical_request_id_accepts_single_and_retainer_identity(value, expected):
    assert snapshot.canonical_request_id(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "01kypj0m0acf4dbafsjvfn9k24", "01KYPJ0M0ACF4DBAFSJVFN9K2I", "0" * 24 + "A"],
)
def test_canonical_request_id_rejects_noncanonical_retainer_identity(value):
    with pytest.raises(snapshot.SnapshotContractError, match="request_id_must_be_decimal"):
        snapshot.canonical_request_id(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://www.coconala.com/requests/123/?tracking=ignored",
            "https://coconala.com/requests/123",
        ),
        (
            "https://coconala.com/job_matching/requests/123",
            "https://coconala.com/requests/123",
        ),
        (
            f"https://www.coconala.com/job_matching/outsources/{ULID}/",
            f"https://coconala.com/job_matching/outsources/{ULID}",
        ),
    ],
)
def test_canonical_request_url_derives_bucket_from_identity_path(value, expected):
    assert snapshot.canonical_request_url(value) == expected


def test_canonical_request_url_binds_numeric_and_retainer_identities():
    with pytest.raises(snapshot.SnapshotContractError, match="request_url_identity_mismatch"):
        snapshot.canonical_request_url(
            f"https://coconala.com/job_matching/outsources/{ULID}",
            request_id="123",
        )
    with pytest.raises(snapshot.SnapshotContractError, match="request_url_identity_mismatch"):
        snapshot.canonical_request_url(
            "https://coconala.com/requests/123",
            request_id=ULID,
        )


def test_canonical_source_url_accepts_retainer_source_and_preserves_single_query_rules():
    assert snapshot.canonical_source_url(
        "https://www.coconala.com/job_matching/outsources/?utm_source=x&b=2&a=1"
    ) == "https://coconala.com/job_matching/outsources?a=1&b=2"
    assert snapshot.canonical_source_url(
        "https://www.coconala.com/requests?utm_source=x&sort=new"
    ) == "https://coconala.com/requests?sort=new"


def _source(source_id: str, url: str, card_request_ids: list[str]) -> dict[str, object]:
    return {
        "source_id": source_id,
        "url": url,
        "page_index": 1,
        "card_request_ids": card_request_ids,
        "has_next": False,
        "exhausted": True,
        "screenshot_sha256": "a" * 64,
        "dom_sha256": "b" * 64,
    }


def _detail(request_id: str, canonical_url: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "canonical_url": canonical_url,
        "title": "案件タイトル",
        "category": "記事作成",
        "visible_text": "募集内容\n本文",
        "accepting_applications": True,
        "budget_min_jpy": None,
        "budget_max_jpy": None,
        "applicants_count": 0,
        "contracted_count": 0,
        "applicants": [],
        "observed_at": "2026-09-14T10:00:00Z",
    }


def _collector() -> dict[str, object]:
    return {
        "pass_id": "pass-1",
        "lease_fence": {"task": "gig", "token": "a" * 32, "generation": 1},
        "observed_at": "2026-09-14T10:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 2,
            "required_search_source_ids": ["single:new", "retainer:new"],
        },
        "search_sources": [
            _source(
                "single:new",
                "https://www.coconala.com/requests?utm_medium=x",
                ["2"],
            ),
            _source(
                "retainer:new",
                "https://www.coconala.com/job_matching/outsources/",
                [ULID],
            ),
        ],
        "request_details": [
            _detail("2", "https://www.coconala.com/job_matching/requests/2/"),
            _detail(
                ULID,
                f"https://www.coconala.com/job_matching/outsources/{ULID}/",
            ),
        ],
        "already_applied_ids": [ULID, "10", "2"],
    }


def test_mixed_identity_envelope_sorts_applied_ids_and_validates():
    envelope = snapshot.build_envelope(_collector())

    assert envelope["already_applied_ids"] == ["2", "10", ULID]
    assert snapshot.validate_snapshot(envelope) == []
    assert envelope["request_details"][0]["canonical_url"] == "https://coconala.com/requests/2"
    assert "bucket" not in envelope["request_details"][0]
    assert "bucket" not in envelope["request_details"][1]


def test_validate_snapshot_rejects_noncanonical_retainer_card_identity():
    envelope = snapshot.build_envelope(_collector())
    invalid = copy.deepcopy(envelope)
    invalid["search_sources"][1]["card_request_ids"] = [ULID.lower()]

    errors = snapshot.validate_snapshot(invalid)

    assert "source_card_ids_invalid" in errors
