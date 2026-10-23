from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from skills.earn.lancers.tests.test_create_package import _b3_digest, _b3_pending_case
from skills.earn.lancers.tests.test_storefront_offer_reads_catalog import _private_catalog, _private_product


SCRIPT = Path(__file__).parents[1] / "scripts" / "storefront_effect_reconcile.py"
OWNER = "lancers-revenue-storefront"
OCCURRENCE = f"{OWNER}:18d67d28fc8af5c0-77700"


def load_module():
    spec = importlib.util.spec_from_file_location("lancers_storefront_effect_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "lancers"
    state.mkdir()
    (state / "listing.json").write_text(json.dumps({
        "listing_external_id": "1338228",
        "catalog_listings": {"a": {"listing_external_id": "1344056"},
                             "b": {"listing_external_id": "1344057"}},
    }), encoding="utf-8")
    product = _private_product(tmp_path / "private", listing_external_id="1338228",
                               superseded_listing_ids=["1338229"])
    value = json.loads(product.read_text())
    value["portfolio"]["external_id"] = "743964"
    value["software_portfolio"]["external_id"] = "743987"
    product.write_text(json.dumps(value), encoding="utf-8")
    return state, product


def roster(**overrides) -> dict:
    value = {
        "ok": True, "action": "roster_readback", "aligned": True, "mismatched_fields": [],
        "listing_external_id": "1338228", "listing_ids": ["1344057", "1338228", "1344056"],
        "superseded_status": {"1338229": "archived"},
        "portfolio_external_ids": {"portfolio": "743964", "software_portfolio": "743987"},
        "portfolio_duplicate_external_ids": {"portfolio": [], "software_portfolio": []},
    }
    return value | overrides


def runner_for(value: dict, returncode: int = 0) -> Mock:
    stdout = "log line\n" + json.dumps(value) + "\n"
    return Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, ""))


def private_setup(tmp_path):
    product = _private_product(tmp_path / ".config/anicca/lancers")
    state = tmp_path / "owner-state"
    state.mkdir()
    (state / "listing.json").write_text(json.dumps({"listing_external_id": "91001"}))
    value = roster(listing_external_id="91001", listing_ids=["91001"], superseded_status={},
                   portfolio_external_ids={"portfolio": "81001", "software_portfolio": "81002"})
    return state, product, value


def test_private_default_product_is_passed_to_same_roster_caller(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    state, product, value = private_setup(tmp_path)
    module = load_module()
    runner = runner_for(value)
    code = module.main(["--occurrence", OCCURRENCE, "--state-root", str(state),
                        "--admission-db", str(admission(tmp_path))], runner=runner)
    command = runner.call_args.args[0]
    assert command[command.index("--product") + 1] == str(product)
    assert code == 0
    assert json.loads(capsys.readouterr().out)["state"] == "PROOF_READY"


def test_private_catalog_is_forwarded_to_roster_readback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    state, product, value = private_setup(tmp_path)
    catalog = _private_catalog(tmp_path / "catalog")
    module = load_module()
    runner = runner_for(value)
    code = module.main(["--occurrence", OCCURRENCE, "--state-root", str(state),
                        "--product", str(product), "--catalog", str(catalog),
                        "--admission-db", str(admission(tmp_path))], runner=runner)
    command = runner.call_args.args[0]
    assert command[command.index("--catalog") + 1] == str(catalog)
    assert code == 0


def test_private_missing_proof_holds_before_browser_and_fence_resolution(tmp_path, monkeypatch, capsys):
    state, product, value = private_setup(tmp_path)
    (product.parent / "other-avatar.png").unlink()
    module = load_module()
    runner = runner_for(value)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    database = admission(tmp_path)
    before = database.read_bytes()
    assert call(module, state, product, runner, "--resolve", database=database) != 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "HELD"
    assert result.get("error") == "setup_required"
    runner.assert_not_called()
    resolver.assert_not_called()
    assert database.read_bytes() == before


def admission(root: Path, state: str = "claimed", unknown: int = 1) -> Path:
    path = root / "admission-v2.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS occurrences "
                   "(occurrence_id TEXT, owner_id TEXT, state TEXT, effect_unknown INTEGER)")
        db.execute("DELETE FROM occurrences")
        db.execute("INSERT INTO occurrences VALUES (?,?,?,?)", (OCCURRENCE, OWNER, state, unknown))
    return path


def call(module, state, product, runner, *extra, database=None):
    database = database or admission(state.parent)
    return module.main(["--occurrence", OCCURRENCE, "--state-root", str(state),
                        "--product", str(product), "--admission-db", str(database), *extra],
                       runner=runner)


def test_roster_matching_owner_ledger_resolves_through_official_readback(
        tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    runner = runner_for(roster())

    code = call(module, state, product, runner, "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["state"] == "RECONCILED" and result["verified"] is True
    assert result["owner_id"] == OWNER and result["occurrence_id"] == OCCURRENCE
    assert result["provider_receipt_id"].startswith("lancers-storefront-roster:")
    command = runner.call_args.args[0]
    assert command[:4] == ["bash", str(module.WITH_BROWSER), "lancers:dais", "--"]
    assert "--roster-readback" in command
    environment = runner.call_args.kwargs["env"]
    assert environment["BROWSER_WAIT_SECONDS"] == "0"
    assert environment["LIFE_MANAGER_BROWSER_IDENTITY"] == "lancers:dais"
    assert environment["LIFE_MANAGER_BROWSER_TARGET_OWNER"] == "lancers-revenue-browser"
    proof = resolver.call_args.kwargs["official_readback"]()
    assert proof["provider_receipt_id"] == result["provider_receipt_id"]
    assert resolver.call_args.kwargs["expected_state"] == "claimed"


def test_without_resolve_reports_proof_and_never_closes(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    code = call(module, state, product, runner_for(roster()))
    result = json.loads(capsys.readouterr().out)

    assert code == 0 and result["state"] == "PROOF_READY"
    resolver.assert_not_called()


def test_pending_create_stays_held_even_when_existing_roster_matches(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    path = state / "listing.json"
    ledger = json.loads(path.read_text())
    ledger["pending_create"] = {"product_id": "unconfirmed-new-listing"}
    path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    resolver = Mock(return_value=True)
    runner = runner_for(roster())
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    code = call(module, state, product, runner, "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 1 and result["state"] == "HELD"
    assert result["reason"] == "creation_pending"
    assert path.read_bytes() == before
    runner.assert_not_called()
    resolver.assert_not_called()


def held(module, state, product, value, capsys, returncode=0):
    code = call(module, state, product, runner_for(value, returncode), "--resolve")
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["state"] == "HELD" and result["verified"] is False
    return result["reason"]


def test_unledgered_listing_stays_fenced(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", Mock(side_effect=AssertionError))
    extra = roster(listing_ids=["1338228", "1344056", "1344057", "1350000"])
    assert held(module, state, product, extra, capsys) == "official_listing_roster_differs_from_ledger"


def test_misaligned_canonical_listing_stays_fenced(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", Mock(side_effect=AssertionError))
    value = roster(aligned=False, mismatched_fields=["plans"])
    assert held(module, state, product, value, capsys) == "canonical_listing_not_aligned"


def test_visible_superseded_listing_stays_fenced(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    value = roster(superseded_status={"1338229": "active"})
    assert held(module, state, product, value, capsys) == "superseded_listing_not_archived"


def test_unknown_portfolio_stays_fenced(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    value = roster(portfolio_external_ids={"portfolio": "743964", "software_portfolio": None})
    assert held(module, state, product, value, capsys) == "portfolio_roster_differs_from_product"


def test_same_title_portfolio_duplicate_stays_fenced(tmp_path, monkeypatch, capsys):
    # 757333 beside the pinned 743987 (2026-10-18) is an unledgered public effect.
    module = load_module()
    state, product = setup(tmp_path)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", Mock(side_effect=AssertionError))
    value = roster(portfolio_duplicate_external_ids={"portfolio": [], "software_portfolio": ["757333"]})
    assert held(module, state, product, value, capsys) == "portfolio_duplicate_present"
    missing = roster()
    del missing["portfolio_duplicate_external_ids"]
    assert held(module, state, product, missing, capsys) == "portfolio_duplicate_present"


def test_unreadable_roster_stays_fenced(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    value = {"ok": False, "error": "account_unavailable"}
    assert held(module, state, product, value, capsys, returncode=1) == "official_roster_unavailable"


def test_other_owner_occurrence_is_refused(tmp_path, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    runner = runner_for(roster())
    code = module.main(["--occurrence", "lancers-revenue-application:x", "--state-root",
                        str(state), "--product", str(product)], runner=runner)
    assert code == 1 and json.loads(capsys.readouterr().out)["reason"] == "occurrence_owner_mismatch"
    runner.assert_not_called()


def test_released_effect_unknown_occurrence_resolves_with_its_real_state(
        tmp_path, monkeypatch, capsys):
    # Production row 18dee27f88679da0-92746 is state=released, effect_unknown=1. A hard-coded
    # expected_state="claimed" matched zero rows, so a verified roster proof still printed HELD.
    module = load_module()
    state, product = setup(tmp_path)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    code = call(module, state, product, runner_for(roster()), "--resolve",
                database=admission(tmp_path, state="released"))

    assert code == 0 and json.loads(capsys.readouterr().out)["state"] == "RECONCILED"
    assert resolver.call_args.kwargs["expected_state"] == "released"


def test_occurrence_not_effect_unknown_is_held_before_browser(tmp_path, monkeypatch, capsys):
    module = load_module()
    state, product = setup(tmp_path)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", Mock(side_effect=AssertionError))
    runner = runner_for(roster())
    code = call(module, state, product, runner, "--resolve",
                database=admission(tmp_path, unknown=0))
    assert code == 1 and json.loads(capsys.readouterr().out)["reason"] == "occurrence_not_effect_unknown"
    runner.assert_not_called()


def _creation_case(module, tmp_path, *, kind="listing", scoped=True):
    case = _b3_pending_case(tmp_path, module=module.offer, kind=kind, scoped=scoped)
    case.context["occurrence_id"] = OCCURRENCE
    if scoped:
        ledger = json.loads(case.ledger.read_text())
        ledger["pending_create_context"] = case.context
        case.ledger.write_text(json.dumps(ledger))
    return case


def _creation_readback(case, **updates):
    return {"ok": True, "action": "creation_readback", "kind": case.kind,
            "external_id": "88001" if "portfolio" in case.kind else "92001",
            "intent_sha256": _b3_digest(case.intent), "readback_sha256": "b" * 64,
            "context": case.context, **updates}


def _creation_runner(case, *, value=None, on_read=lambda: None):
    def run(command, **_kwargs):
        assert "--creation-readback" in command and "--roster-readback" not in command
        assert command[command.index("--occurrence") + 1] == OCCURRENCE
        assert command[command.index("--product") + 1] == str(case.path)
        if case.catalog is not None:
            assert command[command.index("--catalog") + 1] == str(case.catalog)
        on_read()
        result = value if value is not None else _creation_readback(case)
        return subprocess.CompletedProcess(command, 0, json.dumps(result) + "\n", "")
    return Mock(side_effect=run)


def _creation_call(module, case, runner, *extra, database=None):
    catalog = ["--catalog", str(case.catalog)] if case.catalog is not None else []
    return call(module, case.state.parent, case.path, runner, *catalog, *extra, database=database)


@pytest.mark.parametrize("kind", ["listing", "portfolio"])
def test_b3_scoped_pending_target_proof_is_dry_run_and_ignores_future_portfolios(
    tmp_path, monkeypatch, capsys, kind,
):
    module = load_module()
    case = _creation_case(module, tmp_path, kind=kind)
    database = admission(tmp_path)
    before = {path: path.read_bytes() for path in (case.path, case.ledger, database)}
    resolver = Mock(side_effect=AssertionError("dry run reached resolver"))
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    runner = _creation_runner(case)
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", "c" * 40)

    code = _creation_call(module, case, runner, database=database)
    result = json.loads(capsys.readouterr().out)

    assert code == 0 and result["state"] == "PROOF_READY" and result["verified"] is True
    assert result["proof_type"] == "official_creation_matches_owner_intent"
    assert result["owner_id"] == OWNER and result["occurrence_id"] == OCCURRENCE
    assert isinstance(result["provider_receipt_id"], str) and result["provider_receipt_id"]
    assert runner.call_count == 1 and resolver.call_count == 0
    assert {path: path.read_bytes() for path in before} == before
    assert case.context["release_sha"] == "a" * 40
    assert "/profile/other-seller" not in json.dumps(result)


def test_b3_target_proof_receipt_binds_official_id_and_fresh_readback_digest(tmp_path):
    module = load_module()
    case = _creation_case(module, tmp_path)
    first = module.official_proof(OCCURRENCE, case.state.parent, case.path,
                                  runner=_creation_runner(case))
    other_id = module.official_proof(OCCURRENCE, case.state.parent, case.path,
                                     runner=_creation_runner(case, value=_creation_readback(case, external_id="92002")))
    other_readback = module.official_proof(OCCURRENCE, case.state.parent, case.path,
                                           runner=_creation_runner(case, value=_creation_readback(case, readback_sha256="d" * 64)))
    assert len({proof["provider_receipt_id"] for proof in (first, other_id, other_readback)}) == 3
    assert all(proof["owner_id"] == OWNER and proof["occurrence_id"] == OCCURRENCE
               and proof["verified"] is True for proof in (first, other_id, other_readback))


@pytest.mark.parametrize("scope", ["unscoped", "other-occurrence"])
def test_b3_pending_without_matching_occurrence_context_never_resolves(tmp_path, monkeypatch, capsys, scope):
    module = load_module()
    case = _creation_case(module, tmp_path, scoped=scope != "unscoped")
    if scope == "other-occurrence":
        ledger = json.loads(case.ledger.read_text())
        ledger["pending_create_context"]["occurrence_id"] = OWNER + ":different"
        case.ledger.write_text(json.dumps(ledger))
    before = case.path.read_bytes(), case.ledger.read_bytes()
    resolver = Mock(side_effect=AssertionError("unscoped proof reached resolver"))
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    runner = _creation_runner(case)

    assert _creation_call(module, case, runner, "--resolve") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "HELD" and result["verified"] is False
    assert (case.path.read_bytes(), case.ledger.read_bytes()) == before
    resolver.assert_not_called()
    runner.assert_not_called()


@pytest.mark.parametrize("corruption", ["context", "intent", "readback-digest"])
def test_b3_target_protocol_must_match_the_owner_intent_and_occurrence(
    tmp_path, monkeypatch, capsys, corruption,
):
    module = load_module()
    case = _creation_case(module, tmp_path)
    value = _creation_readback(case)
    if corruption == "context":
        value["context"] = case.context | {"occurrence_id": OWNER + ":different"}
    else:
        value["intent_sha256" if corruption == "intent" else "readback_sha256"] = "PRIVATE-INVALID-DIGEST"
    before = case.path.read_bytes(), case.ledger.read_bytes()
    resolver = Mock(side_effect=AssertionError("invalid target proof reached resolver"))
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    assert _creation_call(module, case, _creation_runner(case, value=value), "--resolve") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "HELD" and result["verified"] is False
    assert "PRIVATE" not in json.dumps(result)
    assert (case.path.read_bytes(), case.ledger.read_bytes()) == before
    resolver.assert_not_called()


def test_b3_resolver_failure_after_local_restore_rechecks_the_same_last_target(tmp_path, monkeypatch, capsys):
    module = load_module()
    case = _creation_case(module, tmp_path)
    inside = []
    events = []
    write = module.offer._write_private

    def save(path, value):
        assert inside, "local restore escaped the official_readback callback"
        events.append("write")
        write(path, value)

    def resolve(owner, occurrence, *, official_readback, expected_state):
        assert (owner, occurrence, expected_state) == (OWNER, OCCURRENCE, "claimed")
        inside.append(True)
        try:
            proof = official_readback()
            assert proof["verified"] is True
        finally:
            inside.pop()
        return False

    monkeypatch.setattr(module.offer, "_write_private", save)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolve)
    runner = _creation_runner(case, on_read=lambda: events.append("fresh" if inside else "dry-read"))

    assert _creation_call(module, case, runner, "--resolve") == 1
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "HELD"
    assert "fresh" in events and "write" in events and events.index("fresh") < events.index("write")
    assert first.get("resolved") is False
    assert json.loads(case.path.read_text())["listing_external_id"] == "92001"
    ledger = json.loads(case.ledger.read_text())
    assert ledger.get("last_creation", {}).get("intent") == case.intent
    assert ledger["last_creation"].get("context") == case.context
    assert ledger["last_creation"].get("external_id") == "92001"
    assert "pending_create" not in ledger and "pending_create_context" not in ledger
    before = case.path.read_bytes(), case.ledger.read_bytes()
    assert _creation_call(module, case, runner) == 0
    assert json.loads(capsys.readouterr().out)["proof_type"] == "official_creation_matches_owner_intent"
    assert (case.path.read_bytes(), case.ledger.read_bytes()) == before
    wrong_target = _creation_runner(case, value=_creation_readback(case, external_id="92002"))
    assert _creation_call(module, case, wrong_target) == 1
    assert json.loads(capsys.readouterr().out)["state"] == "HELD"
    assert (case.path.read_bytes(), case.ledger.read_bytes()) == before


@pytest.mark.parametrize("failure", ["input-changed", "enospc"])
def test_b3_resolve_revalidates_current_input_and_keeps_failed_save_pending(
    tmp_path, monkeypatch, capsys, failure,
):
    module = load_module()
    case = _creation_case(module, tmp_path)
    callbacks = []
    write = module.offer._write_private

    def save(path, value):
        if failure == "enospc" and Path(path) == case.path:
            raise OSError(28, "PRIVATE-STORAGE-DETAIL")
        write(path, value)

    def resolve(_owner, _occurrence, *, official_readback, **_kwargs):
        callbacks.append(True)
        if failure == "input-changed":
            raw = json.loads(case.path.read_text())
            raw["description"] += " 本人が差し替えた入力"
            case.path.write_text(json.dumps(raw, ensure_ascii=False))
        official_readback()
        return True

    monkeypatch.setattr(module.offer, "_write_private", save)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolve)
    assert _creation_call(module, case, _creation_runner(case), "--resolve") == 1
    result = json.loads(capsys.readouterr().out)
    assert callbacks == [True]
    assert result["state"] == "HELD" and result["verified"] is False
    assert json.loads(case.path.read_text())["listing_external_id"] == ""
    ledger = json.loads(case.ledger.read_text())
    assert ledger["pending_create"] == case.intent and ledger["pending_create_context"] == case.context
    assert "PRIVATE" not in json.dumps(result)
    if failure == "enospc":
        monkeypatch.setattr(module.offer, "_write_private", write)
        assert _creation_call(module, case, _creation_runner(case), "--resolve") == 0
        assert json.loads(capsys.readouterr().out)["state"] == "RECONCILED"
        assert json.loads(case.path.read_text())["listing_external_id"] == "92001"
        assert json.loads(case.ledger.read_text())["last_creation"]["external_id"] == "92001"


def test_b3_catalog_resolve_restores_only_its_family_cursor(tmp_path, monkeypatch, capsys):
    module = load_module()
    case = _creation_case(module, tmp_path, kind="catalog_listing")
    before, ledger = case.path.read_bytes(), json.loads(case.ledger.read_text())

    def resolve(_owner, _occurrence, *, official_readback, **_kwargs):
        return official_readback()["verified"] is True

    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolve)
    assert _creation_call(module, case, _creation_runner(case), "--resolve") == 0
    assert json.loads(capsys.readouterr().out)["state"] == "RECONCILED"
    after = json.loads(case.ledger.read_text())
    assert case.path.read_bytes() == before
    assert after["listing_external_id"] == ledger["listing_external_id"] == "91001"
    assert after["catalog_listings"]["keep-family"] == ledger["catalog_listings"]["keep-family"]
    assert after["catalog_listings"]["other"]["listing_external_id"] == "92001"
    assert "pending_create" not in after and "pending_create_context" not in after
