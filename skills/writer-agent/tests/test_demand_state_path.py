import importlib.util
import hashlib
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "demand_observations.py"
SPEC = importlib.util.spec_from_file_location("demand_observations", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _config(skill_dir: Path) -> dict:
    config_dir = skill_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "opportunity-watch.json").write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "techi-author",
                        "publisher": "TECHi Author Program",
                        "official_program_url": "https://www.techi.com/authors/apply/",
                        "evidence_profile": "techi-author-v1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return {
        "demand_source_id": "techi-author",
        "demand_source_config": "config/opportunity-watch.json",
        "demand_source_receipt": "state/demand-source-bodies.json",
    }


def _body() -> bytes:
    return (
        "Apply to write for TECHi. Accepted work is reviewed by the editorial team. "
        "The program will pay per publish for approved articles, and contributors are "
        "paid monthly via Stripe. "
        "This additional context keeps the full official page receipt above the "
        "minimum body size and represents the visible application guidance."
    ).encode("utf-8")


def _current_techi_body() -> bytes:
    return (
        "Apply as Author. Authors do not pay TECHi. Approved contributors can receive "
        "a public byline and payment terms tied to accepted work. Pay per publish: "
        "flat rate per accepted piece, and contributors are paid monthly via Stripe. "
        "This current-page context keeps the receipt above the minimum body size and "
        "represents the visible application guidance."
    ).encode("utf-8")


def test_configured_publisher_receipt_uses_external_state_dir(tmp_path: Path) -> None:
    skill_dir = tmp_path / "release" / "skills" / "writer-agent"
    state_dir = tmp_path / "state"
    config = _config(skill_dir)
    observed_at = "2026-08-21T00:00:00Z"

    rows = MODULE.configured_full_body_observations(
        skill_dir,
        config,
        state_dir=state_dir,
        observed_at=observed_at,
        fetcher=lambda _source: _body(),
    )

    receipt = state_dir / "demand-source-bodies.json"
    assert len(rows) == 1
    assert receipt.is_file()
    assert not (skill_dir / "state" / "demand-source-bodies.json").exists()
    assert json.loads(receipt.read_text(encoding="utf-8"))["source_sha256"] == hashlib.sha256(
        _body().decode("utf-8").encode("utf-8")
    ).hexdigest()

    cached = MODULE.cached_full_body_observations(
        skill_dir,
        config,
        state_dir=state_dir,
        observed_at="2026-08-21T00:05:00Z",
    )
    assert cached[0]["reuse_reason"] == "official-source-unavailable"


def test_configured_publisher_receipt_reuses_verified_body_after_untrusted_fetch(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "release" / "skills" / "writer-agent"
    state_dir = tmp_path / "state"
    config = _config(skill_dir)

    MODULE.configured_full_body_observations(
        skill_dir,
        config,
        state_dir=state_dir,
        observed_at="2026-08-21T00:00:00Z",
        fetcher=lambda _source: _body(),
    )

    reused = MODULE.configured_full_body_observations(
        skill_dir,
        config,
        state_dir=state_dir,
        observed_at="2026-08-21T00:05:00Z",
        fetcher=lambda _source: b"transport succeeded but the page is only an interstitial",
    )

    assert reused[0]["reuse_reason"] == "official-source-unavailable"
    assert reused[0]["source_sha256"] == hashlib.sha256(
        _body().decode("utf-8").encode("utf-8")
    ).hexdigest()


def test_configured_publisher_accepts_current_techi_author_heading(tmp_path: Path) -> None:
    skill_dir = tmp_path / "release" / "skills" / "writer-agent"
    state_dir = tmp_path / "state"
    config = _config(skill_dir)

    rows = MODULE.configured_full_body_observations(
        skill_dir,
        config,
        state_dir=state_dir,
        observed_at="2026-09-18T00:00:00Z",
        fetcher=lambda _source: _current_techi_body(),
    )

    assert len(rows) == 1
    assert rows[0]["evidence_units"]
