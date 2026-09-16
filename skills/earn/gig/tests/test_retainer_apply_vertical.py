from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import asyncio
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
ULID = "01KYPJ0M0ACF4DBAFSJVFN9K24"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"retainer_vertical_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


parent = load("application_parent")
planner = load("application_planner")
eligibility = load("application_eligibility")
gate = load("b2_result_gate")
fence = load("application_effect_fence")
readback = load("coconala_applied_readback")
direct = load("application_direct")
nav = load("cdp_nav_snapshot")


def _snapshot() -> dict[str, object]:
    return parent.snapshot_contract.build_envelope({
        "pass_id": "retainer-test",
        "lease_fence": {"task": "retainer-test", "token": "1" * 32, "generation": 1},
        "observed_at": "2026-09-14T00:00:00Z",
        "objective": {"target_applications": 1, "max_applications": 1, "required_search_source_ids": ["retainer:new"]},
        "search_sources": [{
            "source_id": "retainer:new", "url": "https://coconala.com/job_matching/outsources",
            "page_index": 1, "card_request_ids": [ULID], "has_next": False, "exhausted": True,
            "screenshot_sha256": "a" * 64, "dom_sha256": "b" * 64,
        }],
        "request_details": [{
            "request_id": ULID,
            "canonical_url": f"https://coconala.com/job_matching/outsources/{ULID}",
            "title": "継続開発支援", "category": "IT・プログラミング",
            "visible_text": "募集内容\n非同期で継続する開発支援をお願いします。",
            "accepting_applications": True, "budget_min_jpy": None, "budget_max_jpy": None,
            "applicants_count": 0, "contracted_count": 0, "applicants": [],
            "observed_at": "2026-09-14T00:00:00Z",
        }],
        "already_applied_ids": [],
    })


def _decision() -> dict[str, object]:
    return {"decisions": [{
        "request_id": ULID, "business_class": "submit_required", "reason_codes": [],
        "proposal_text": "継続開発支援の目的と優先順位を整理し、毎週の実装、検証、記録まで責任を持って進めます。" * 5,
        "price_jpy": 120_000, "deliver_date": "2026-10-01",
        "work_frequency": "WEEK_THREE", "weekly_hours_min": 12, "weekly_hours_max": 18,
        "screening_answers": [],
    }]}


def _snapshot_with_questions() -> dict[str, object]:
    base = _snapshot()
    detail = dict(base["request_details"][0])
    detail["application_questions"] = [
        {"question": "自治体案件の経験はありますか？", "required": True, "max_length": 1000},
        {"question": "面談可能な候補日時を3つ記載してください。", "required": True, "max_length": 1000},
    ]
    return parent.snapshot_contract.build_envelope({
        "pass_id": base["pass_id"], "lease_fence": base["lease_fence"],
        "observed_at": base["observed_at"], "objective": base["objective"],
        "search_sources": base["search_sources"], "request_details": [detail],
        "already_applied_ids": base["already_applied_ids"],
    })


def _single_snapshot() -> dict[str, object]:
    return parent.snapshot_contract.build_envelope({
        "pass_id": "single-test",
        "lease_fence": {"task": "single-test", "token": "2" * 32, "generation": 1},
        "observed_at": "2026-09-14T00:00:00Z",
        "objective": {"target_applications": 1, "max_applications": 1,
                      "required_search_source_ids": ["single:new"]},
        "search_sources": [{
            "source_id": "single:new", "url": "https://coconala.com/requests?sort=new&recruiting=true",
            "page_index": 1, "card_request_ids": ["123"], "has_next": False, "exhausted": True,
            "screenshot_sha256": "c" * 64, "dom_sha256": "d" * 64,
        }],
        "request_details": [{
            "request_id": "123", "canonical_url": "https://coconala.com/requests/123",
            "title": "資料整理", "category": "IT・プログラミング",
            "visible_text": "募集内容\n資料を整理して納品してください。",
            "accepting_applications": True, "budget_min_jpy": 10_000,
            "budget_max_jpy": 20_000, "applicants_count": 0, "contracted_count": 0,
            "applicants": [], "observed_at": "2026-09-14T00:00:00Z",
        }],
        "already_applied_ids": [],
    })


def test_retainer_terms_are_required_and_bound_to_the_durable_intent() -> None:
    decision = _decision()
    assert planner.validate_decisions(_snapshot(), decision) == []
    intent = fence.intent_payload(
        request_id=ULID, snapshot_sha256="2" * 64,
        proposal_text=decision["decisions"][0]["proposal_text"], price_jpy=120_000,
        deliver_date="2026-10-01", lease_fence={"task": "retainer-test", "token": "1" * 32, "generation": 1},
        retainer_terms={"work_frequency": "WEEK_THREE", "weekly_hours_min": 12, "weekly_hours_max": 18},
        screening_answers=[],
    )
    assert intent["version"] == 4
    assert fence.validate_intent(intent) == []
    changed = dict(intent)
    changed["retainer_terms"] = {**intent["retainer_terms"], "weekly_hours_max": 19}
    assert "retainer_terms_sha256_mismatch" in fence.validate_intent(changed)


def test_retainer_screening_answers_match_snapshot_and_are_fenced() -> None:
    snapshot = _snapshot_with_questions()
    decision = _decision()
    answers = [
        {"question": "自治体案件の経験はありますか？", "answer": "自治体案件の実務経験はありません。"},
        {"question": "面談可能な候補日時を3つ記載してください。", "answer": "9月18日10時、9月19日14時、9月21日16時が可能です。"},
    ]
    decision["decisions"][0]["screening_answers"] = answers

    assert planner.validate_decisions(snapshot, decision) == []
    intent = fence.intent_payload(
        request_id=ULID, snapshot_sha256="2" * 64,
        proposal_text=decision["decisions"][0]["proposal_text"], price_jpy=120_000,
        deliver_date="2026-10-01", lease_fence={"task": "retainer-test", "token": "1" * 32, "generation": 1},
        retainer_terms={"work_frequency": "WEEK_THREE", "weekly_hours_min": 12, "weekly_hours_max": 18},
        screening_answers=answers,
    )
    assert intent["version"] == 4
    assert fence.validate_intent(intent) == []
    changed = {**intent, "screening_answers": [*answers[:-1], {**answers[-1], "answer": "別の日時"}]}
    assert "screening_answers_sha256_mismatch" in fence.validate_intent(changed)


def test_retainer_terms_are_read_from_official_listing_when_planner_returns_null() -> None:
    base = _snapshot()
    detail = dict(base["request_details"][0])
    detail["visible_text"] = (
        "稼働日数\n週1日以上\n(週あたり1~10時間)\n募集内容の詳細\n"
        "完全在宅でWebサイトを構築してください。"
    )
    snapshot = parent.snapshot_contract.build_envelope({
        "pass_id": base["pass_id"], "lease_fence": base["lease_fence"],
        "observed_at": base["observed_at"], "objective": base["objective"],
        "search_sources": base["search_sources"], "request_details": [detail],
        "already_applied_ids": base["already_applied_ids"],
    })
    decisions = _decision()
    row = decisions["decisions"][0]
    row["work_frequency"] = "MONTH_ONE"
    row["weekly_hours_min"] = None
    row["weekly_hours_max"] = None

    repaired = planner.bind_retainer_terms_from_snapshot(snapshot, decisions)

    assert repaired["decisions"][0]["work_frequency"] == "WEEK_ONE"
    assert repaired["decisions"][0]["weekly_hours_min"] == 1
    assert repaired["decisions"][0]["weekly_hours_max"] == 10
    assert planner.validate_decisions(snapshot, repaired) == []


def test_retainer_legacy_projection_keeps_bucket_url_and_terms() -> None:
    snapshot = _snapshot()
    decision = _decision()

    projected = parent.project_legacy_b2(
        snapshot,
        decision,
        [{"request_id": ULID, "status": "submission_failed:test"}],
    )

    inspected = projected["current_b2"]["inspected_requests"][0]
    assert inspected["bucket"] == "retainer"
    assert inspected["url"] == f"https://coconala.com/job_matching/outsources/{ULID}"
    assert inspected["compensation_type"] == "recurring"
    assert inspected["weekly_days"] == "WEEK_THREE"
    assert inspected["weekly_hours_min"] == 12
    assert inspected["weekly_hours_max"] == 18


def test_retainer_commit_uses_the_existing_effect_fence_and_exact_readback(tmp_path, monkeypatch) -> None:
    snapshot = _snapshot()
    effects = parent.FixtureEffects(snapshot, {"official_applied_ids": [ULID]})
    monkeypatch.setattr(parent.gig_disk_guard, "disk_headroom_ok", lambda: True)

    results = parent.commit_decisions(snapshot, _decision(), store=fence.IntentStore(tmp_path), effects=effects)

    assert results[0]["status"] == "confirmed"
    assert effects.click_count == 2
    assert effects.exact_id_readback_ids == [ULID]
    assert results[0]["application"]["bucket"] == "retainer"
    assert results[0]["application"]["weekly_days"] == "WEEK_THREE"


def test_retainer_commit_fills_and_reads_back_screening_answers(tmp_path, monkeypatch) -> None:
    snapshot = _snapshot_with_questions()
    decision = _decision()
    decision["decisions"][0]["screening_answers"] = [
        {"question": "自治体案件の経験はありますか？", "answer": "自治体案件の実務経験はありません。"},
        {"question": "面談可能な候補日時を3つ記載してください。", "answer": "9月18日10時、9月19日14時、9月21日16時が可能です。"},
    ]
    effects = parent.FixtureEffects(snapshot, {"official_applied_ids": [ULID]})
    monkeypatch.setattr(parent.gig_disk_guard, "disk_headroom_ok", lambda: True)

    results = parent.commit_decisions(
        snapshot, decision, store=fence.IntentStore(tmp_path), effects=effects
    )

    assert results[0]["status"] == "confirmed"
    assert effects._filled[ULID]["screening_answers"] == decision["decisions"][0]["screening_answers"]
    assert fence.validate_intent(json.loads((tmp_path / f"{ULID}.json").read_text())) == []


def test_retainer_confirmation_failure_stays_pre_effect_and_retryable(tmp_path, monkeypatch) -> None:
    class ConfirmationBlocked(parent.FixtureEffects):
        def preflight_submit(self, request_id: str) -> None:
            raise parent.ParentContractError("retainer_application_confirmation_invalid")

    snapshot = _snapshot()
    effects = ConfirmationBlocked(snapshot, {})
    monkeypatch.setattr(parent.gig_disk_guard, "disk_headroom_ok", lambda: True)

    results = parent.commit_decisions(
        snapshot, _decision(), store=fence.IntentStore(tmp_path), effects=effects
    )

    assert results[0]["status"].startswith("pre_submit_aborted:submit_preflight")
    retired = json.loads((tmp_path / f"{ULID}.json").read_text())
    assert retired["state"] == fence.RETIRED_ABSENT
    assert retired["effect_phase"] == fence.PRE_EFFECT
    assert effects.click_count == 1


def test_old_retainer_confirmation_failure_is_safe_nonlanding_evidence(tmp_path) -> None:
    origin_pass = "gig-apply-direct-123-456"
    origin_evidence = tmp_path / origin_pass / "coverage-evidence-2"
    worker = origin_evidence / "commit-workers" / ULID
    worker.mkdir(parents=True)
    (worker / f"gig-{origin_pass}-B2-{ULID}-retainer-form.png").write_bytes(b"png")
    (origin_evidence / "parent-commit.json").write_text(json.dumps({
        "results": [{
            "request_id": ULID,
            "status": "submission_failed:retainer_application_confirmation_invalid",
        }],
    }))
    current = tmp_path / "gig-apply-direct-999-888" / "coverage-evidence"
    current.mkdir(parents=True)
    effects = parent.CdpParentEffects(
        ws_url="ws://example.test/devtools/page/1",
        evidence_dir=current,
        ledger_path=tmp_path / "ledger.jsonl",
        pass_id="gig-apply-direct-999-888",
    )
    intent = {
        "lease_fence": {
            "task": f"{origin_pass}-coverage-2-commit-{ULID}"
        }
    }

    assert effects.saved_nonlanding_submit_evidence(ULID, intent) is True


def test_retainer_submit_has_no_effect_fence_bypass() -> None:
    assert not hasattr(nav, "submit_retainer_application")
    assert not hasattr(nav, "_submit_retainer_application_main")


def test_retainer_confirmation_requires_exact_canonical_ulid() -> None:
    same_title_without_exact_link = [
        "https://coconala.com/job_matching/outsources",
        "https://coconala.com/job_matching/outsources/not-an-id",
    ]
    assert readback.extract_retainer_ids(same_title_without_exact_link) == []
    assert not hasattr(readback, "match_retainer_ids_by_title")
    exact_url = f"https://coconala.com/job_matching/outsources/{ULID}/apply"
    assert parent._retainer_application_is_officially_applied(
        ULID, url=exact_url, title="応募内容を確認する | ココナラ"
    )
    assert not parent._retainer_application_is_officially_applied(
        ULID, url=exact_url, title="応募する | ココナラ"
    )
    assert not parent._retainer_application_is_officially_applied(
        ULID, url=f"https://coconala.com/job_matching/outsources/{'0' * 26}/apply",
        title="応募内容を確認する | ココナラ",
    )


def test_retainer_question_selector_does_not_assume_native_required_or_fixed_limit() -> None:
    observer = inspect.getsource(parent.CdpParentEffects._retainer_form_state_async)
    filler = inspect.getsource(parent.CdpParentEffects._fill_retainer_async)
    assert 'textarea[placeholder="回答を入力"]' in observer
    assert 'textarea[placeholder="回答を入力"][required]' not in observer
    assert "area.maxLength>0" in observer
    assert "aria-required" in observer
    assert 'textarea[placeholder="回答を入力"]' in filler


def test_retainer_exact_readback_waits_past_the_previous_document(tmp_path, monkeypatch) -> None:
    effects = parent.CdpParentEffects(
        ws_url="ws://example.test/devtools/page/1",
        evidence_dir=tmp_path / "evidence",
        ledger_path=tmp_path / "ledger.jsonl",
        pass_id="retainer-test",
    )
    states = iter([
        {"url": parent.RETAINER_APPLIED_URL, "title": "応募・スカウト管理", "ready": "complete"},
        {
            "url": f"https://coconala.com/job_matching/outsources/{ULID}/apply",
            "title": "応募内容を確認する | ココナラ",
            "ready": "complete",
        },
    ])

    async def fake_eval(_ws, _expression, call_id):
        return next(states), call_id + 1

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(effects, "_eval_json", fake_eval)
    monkeypatch.setattr(parent.asyncio, "sleep", no_sleep)
    state, call_id = asyncio.run(
        effects._settle_retainer_application_readback(object(), ULID, 10)
    )
    assert state["title"] == "応募内容を確認する | ココナラ"
    assert call_id == 12


def test_retainer_form_waits_past_the_previous_document(tmp_path, monkeypatch) -> None:
    effects = parent.CdpParentEffects(
        ws_url="ws://example.test/devtools/page/1",
        evidence_dir=tmp_path / "evidence",
        ledger_path=tmp_path / "ledger.jsonl",
        pass_id="retainer-test",
    )
    states = iter([
        {"url": "https://coconala.com/", "ready": "complete"},
        {
            "url": f"https://coconala.com/job_matching/outsources/{ULID}/apply",
            "ready": "complete",
        },
    ])

    async def fake_eval(_ws, _expression, call_id):
        return next(states), call_id + 1

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(effects, "_eval_json", fake_eval)
    monkeypatch.setattr(parent.asyncio, "sleep", no_sleep)
    call_id = asyncio.run(effects._settle_on_application_form(object(), ULID, 20))
    assert call_id == 22


def test_retainer_is_evaluated_by_the_same_capability_gate_not_bucket_refused() -> None:
    result = eligibility.evaluate_application(
        "非同期の文章作成を継続します", "納品と改善案を作成します",
        bucket="retainer", market={"client_order_rate": 80},
    )
    assert result["allowed"] is True
    assert "retainer_applications_disabled" not in result["reason_codes"]

    without_single_market_card = eligibility.evaluate_application(
        "非同期の文章作成を継続します", "納品と改善案を作成します",
        bucket="retainer", market=None,
    )
    assert without_single_market_card["allowed"] is True
    assert "market_snapshot_missing" not in without_single_market_card["reason_codes"]


def test_context_requires_the_retainer_source_and_target() -> None:
    context = gate.build_context({
        "apply_skip_thresholds": {"min_budget_jpy": 0}, "max_apply_per_pass": 20,
        "target_apply_per_pass": 19, "target_retainer_apply_per_pass": 1,
    }, Path("/nonexistent-applied.jsonl"))
    assert context["target_applications"] == 19
    assert context["target_retainer_applications"] == 1
    assert context["max_applications"] == 20
    assert "retainer:new" in context["required_search_source_ids"]
    assert parent.CdpSnapshotCollector._source_url("retainer:new") == (
        "https://coconala.com/job_matching/outsources"
    )


def test_retainer_identity_survives_applied_exclusion_projection() -> None:
    assert parent.snapshot_applied_ids({"20", ULID, "dm-20"}) == ["20", ULID]


def test_quota_reserves_one_retainer_slot_across_shards_and_source_anchors() -> None:
    required = ["single:new", "retainer:new", "single:category:a", "single:keyword"]
    plan = parent._source_capacity_plan(required, batch=20)
    assert plan["retainer:new"] == 1
    assert sum(plan.values()) == 20
    assert sum(plan[source] for source in required if source != "retainer:new") == 19
    # Shards receive the same global source allocations, not a fresh 20-slot budget.
    assert sum(plan[source] for source in required[:2]) + sum(plan[source] for source in required[2:]) == 20
    details = [
        {"request_id": str(index), "budget_max_jpy": index}
        for index in range(25)
    ] + [{"request_id": ULID, "budget_max_jpy": 999}]
    bounded = parent._bounded_application_details(details, batch=20)
    assert sum(str(row["request_id"]).isdigit() for row in bounded) == 19
    assert [row["request_id"] for row in bounded if not str(row["request_id"]).isdigit()] == [ULID]


def test_retainer_does_not_satisfy_the_single_cursor_target(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({
        "current_b2": {"search_sources": [], "inspected_requests": []},
        "applications": [{"request_id": ULID}],
    }), encoding="utf-8")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({
        "status": "success", "task_label": "gig-B2", "result_path": str(result_path),
    }), encoding="utf-8")
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps({
        "target_applications": 1, "target_retainer_applications": 1,
        "required_search_source_ids": ["single:new", "retainer:new"],
    }), encoding="utf-8")
    assert gate.next_search_cursor(summary_path, context_path)["source_id"] == "single:new"


def test_retainer_title_binding_is_durable_and_hydration_helper_is_shared(tmp_path) -> None:
    first = parent.CdpParentEffects(
        ws_url="ws://example.test/devtools/page/1", evidence_dir=tmp_path / "phase-evidence",
        ledger_path=tmp_path / "ledger.jsonl", pass_id="retainer-test",
    )
    first._persist_retainer_title(ULID, {"title": "継続開発支援"})
    restarted = parent.CdpParentEffects(
        ws_url="ws://example.test/devtools/page/2", evidence_dir=tmp_path / "phase-reconcile-evidence",
        ledger_path=tmp_path / "ledger.jsonl", pass_id="retainer-test",
    )
    assert restarted._fresh_details == {}
    assert restarted._retainer_titles({ULID}) == {ULID: "継続開発支援"}
    assert inspect.getsource(parent._wait_for_retainer_page) == inspect.getsource(
        readback._wait_for_retainer_page
    )


def test_direct_wrapper_accepts_retainer_lifecycle_observation() -> None:
    fields = {
        "page_state": "present", "accepting_control": "present",
        "deadline_state": "future", "deadline_value": None, "form_state": "present",
    }
    canonical_url = f"https://coconala.com/job_matching/outsources/{ULID}"
    digest = parent._lifecycle_digest(ULID, canonical_url, **fields)
    payload = {
        "version": 1, "raw_request_ids": [ULID], "already_applied_ids": [],
        "quarantined_ids": [], "filtered_results": [],
        "lifecycle_results": [{
            "request_id": ULID, "title": "継続開発支援", "canonical_url": canonical_url,
            "observed_at": "2026-09-14T00:00:00Z", "lifecycle_sha256": digest, **fields,
        }],
    }
    assert direct._validated_observations(payload) == payload


def test_fence_rejects_cross_bucket_versions_and_noncanonical_ulids() -> None:
    base = {
        "snapshot_sha256": "2" * 64,
        "proposal_text": "提案内容です。" * 100,
        "price_jpy": 10_000,
        "deliver_date": "2026-10-01",
        "lease_fence": {"task": "retainer-test", "token": "1" * 32, "generation": 1},
    }
    assert "retainer_terms_required" in _fence_error(lambda: fence.intent_payload(request_id=ULID, **base))
    assert "retainer_terms_for_single_forbidden" in _fence_error(lambda: fence.intent_payload(
        request_id="123", retainer_terms={"work_frequency": "WEEK_ONE", "weekly_hours_min": 1, "weekly_hours_max": 2}, **base
    ))
    assert "request_id_invalid" in _fence_error(lambda: fence.intent_payload(request_id="8" + ULID[1:], **base))
    retainer = fence.intent_payload(
        request_id=ULID, retainer_terms={"work_frequency": "WEEK_ONE", "weekly_hours_min": 1, "weekly_hours_max": 2},
        screening_answers=[], **base
    )
    old_retainer = {
        key: value for key, value in retainer.items()
        if key not in {"screening_answers", "screening_answers_sha256"}
    }
    old_retainer["version"] = 3
    old_retainer["cas"] = fence.build_cas(
        ULID, base["snapshot_sha256"], fence.proposal_sha256(base["proposal_text"]),
        10_000, "2026-10-01", old_retainer["retainer_terms_sha256"],
    )
    assert fence.validate_intent(old_retainer) == []
    numeric_v4 = dict(retainer)
    numeric_v4["request_id"] = "123"
    numeric_v4["cas"] = fence.build_cas(
        "123", base["snapshot_sha256"], fence.proposal_sha256(base["proposal_text"]),
        10_000, "2026-10-01", numeric_v4["retainer_terms_sha256"],
        numeric_v4["screening_answers_sha256"],
    )
    assert "single_intent_version_invalid" in fence.validate_intent(numeric_v4)
    noncanonical = "8" + ULID[1:]
    assert parent._is_retainer_request(noncanonical) is False
    assert gate._valid_request_id(noncanonical) is False
    assert readback._valid_identity(noncanonical) is False


def _fence_error(operation):
    try:
        operation()
    except fence.IntentFenceError as error:
        return str(error)
    return ""


def test_decision_schema_has_disjoint_single_and_retainer_shapes() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((SCRIPTS.parent / "schemas" / "application_decisions.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    item_schema = schema["properties"]["decisions"]["items"]
    assert set(item_schema["required"]) == set(item_schema["properties"])
    def schema_keys(value):
        if isinstance(value, dict):
            return set(value).union(*(schema_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(schema_keys(item) for item in value))
        return set()
    assert not {"allOf", "if", "then", "else"}.intersection(schema_keys(schema))
    single = {**_decision()["decisions"][0],
              "price_jpy": 12_000,
              "work_frequency": None, "weekly_hours_min": None, "weekly_hours_max": None}
    single["request_id"] = "123"
    assert not list(validator.iter_errors({"decisions": [single]}))
    assert planner.validate_decisions(_single_snapshot(), {"decisions": [single]}) == []
    bad_single = {**single, "work_frequency": "WEEK_ONE"}
    assert "decision[0]_single_retainer_terms_must_be_null" in planner.validate_decisions(
        _single_snapshot(), {"decisions": [bad_single]},
    )
    assert list(validator.iter_errors({"decisions": [{
        key: value for key, value in single.items() if key != "work_frequency"
    }]}))
    retainer = _decision()["decisions"][0]
    assert not list(validator.iter_errors({"decisions": [retainer]}))
    assert list(validator.iter_errors({"decisions": [{
        key: value for key, value in retainer.items() if key != "weekly_hours_max"
    }]}))
