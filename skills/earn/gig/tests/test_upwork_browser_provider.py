from __future__ import annotations

import asyncio
import sys
import hashlib
import json
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PROVIDERS = SCRIPTS / "providers"
for directory in (SCRIPTS, PROVIDERS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import upwork_browser_provider as provider  # noqa: E402

from upwork_browser_provider import (  # noqa: E402
    load_candidates,
    parse_candidate,
    parse_catalog,
    parse_connects,
    parse_contracts,
    parse_inventory,
    parse_messages,
    parse_stable_entities,
    record_upwork_platform_manifest_wake,
    reconcile_terminal_transitions,
)


def test_upwork_platform_manifest_wake_hashes_account_before_bridge(tmp_path, monkeypatch):
    calls = []

    def bridge(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "inspected": 1, "held": 1}

    monkeypatch.setattr(provider, "run_upwork_platform_manifest_wake", bridge)
    state = {
        "version": 1,
        "provider": "upwork",
        "observed_at": "2026-09-30T04:10:00Z",
        "evidence_sha256": {
            "contracts": "c" * 64,
            "transactions": "d" * 64,
            "withdrawals": "e" * 64,
            "working-style": "f" * 64,
        },
        "active_contracts": [{"id": "private-contract-body"}],
    }

    result = record_upwork_platform_manifest_wake(
        state,
        account_id="private-account-id",
        run_id="upwork-manifest-test",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
    )

    assert result["status"] == "ok"
    assert len(calls) == 1
    snapshot = calls[0]["snapshot"]
    assert snapshot["account_id_sha256"] != "private-account-id"
    assert "private-account-id" not in repr(snapshot)
    assert "private-contract-body" not in repr(snapshot)


def test_application_decision_persists_without_blocking_on_reporter(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(provider, "DEFAULT_GIG_DIR", tmp_path)
    monkeypatch.setattr(provider.subprocess, "run", lambda command, **kwargs: calls.append(command))
    event = {
        "kind": "application", "event_key": "gig:decision:upwork:job-1",
        "entity_id": "job-1", "occurred_at": "2026-08-24T08:00:00+00:00",
        "state": "skipped", "action": "応募見送り", "result": "見送り",
        "next_action": "次の案件確認を続けます", "evidence": ["model_decision"],
        "attributes": {"platform": "upwork", "title": "Job", "reason_codes": ["Not feasible"]},
    }

    provider.publish_application_decisions([event])
    provider.publish_application_decisions([event])

    assert calls == []
    rows = [json.loads(line) for line in (tmp_path / "work-events.jsonl").read_text().splitlines()]
    assert rows == [event]


def test_verified_proposal_event_carries_official_id_connects_and_quote():
    payload = {
        "job_id": "~job-1", "job_url": "https://www.upwork.com/jobs/~job-1",
        "title": "High-value job",
        "terms": {"type": "hourly", "bid_usd": 40, "delivery_days": 2,
                  "required_connects": 11, "available_connects_before": 92},
    }

    event = provider.proposal_submitted_event(
        payload, proposal_id="proposal-1", connects_before=92, connects_after=81,
    )

    assert event["state"] == "verified"
    assert event["attributes"] == {
        "platform": "upwork", "title": "High-value job",
        "url": "https://www.upwork.com/jobs/~job-1", "job_id": "~job-1",
        "proposal_id": "proposal-1", "connects_before": 92,
        "connects_after": 81, "connects_spent": 11,
        "quote": {"currency": "USD", "amount": 40, "unit": "hourly"},
    }


def test_verified_offer_creates_replay_safe_general_agent_workspace(tmp_path):
    decision = {
        "action": "accept", "reason_codes": [], "decision_sha256": "a" * 64,
        "offer": {
            "offer_id": "offer-1", "scope": "Build one tested API integration.",
            "deadline": "2026-09-01",
        },
    }

    first = provider.create_offer_workspace(
        decision, contract_id="contract-1", contract_readback_sha256="b" * 64,
        projects_root=tmp_path / "projects",
    )
    replay = provider.create_offer_workspace(
        decision, contract_id="contract-1", contract_readback_sha256="b" * 64,
        projects_root=tmp_path / "projects",
    )

    assert first == replay
    workflow = json.loads(next(
        (Path(first["workspace"]) / "source" / "workflows").glob("*.json")
    ).read_text())
    assert workflow["skill_id"] == "general-agent"


def test_active_contract_resumes_existing_general_agent_owner(tmp_path, monkeypatch):
    decision = {
        "action": "accept", "reason_codes": [], "decision_sha256": "a" * 64,
        "offer": {
            "offer_id": "offer-1", "scope": "Build one tested API integration.",
            "deadline": "2026-09-01",
        },
    }
    workspace = provider.create_offer_workspace(
        decision, contract_id="contract-1", contract_readback_sha256="b" * 64,
        projects_root=tmp_path / "projects",
    )
    started = []
    monkeypatch.setattr(provider, "start_project_worker", started.append)

    owners = provider.resume_active_contract_workers(
        [{"id": "contract-1", "href": "https://www.upwork.com/ab/workroom/contract-1"}],
        projects_root=tmp_path / "projects",
    )

    assert owners == [{
        "contract_id": "contract-1", "state": "worker_resumed",
        "workspace": workspace["workspace"],
        "revision_sha256": workspace["revision_sha256"],
    }]
    assert started == [workspace]


def test_broken_contract_owner_does_not_block_other_contracts(tmp_path, monkeypatch):
    def make(contract_id):
        return provider.create_offer_workspace({
            "action": "accept", "reason_codes": [], "decision_sha256": "a" * 64,
            "offer": {"offer_id": f"offer-{contract_id}", "scope": "Build it.",
                      "deadline": "2026-09-01"},
        }, contract_id=contract_id, contract_readback_sha256="b" * 64,
            projects_root=tmp_path / "projects")

    broken, healthy = make("contract-broken"), make("contract-healthy")
    state_path = Path(broken["workspace"]) / "state.json"
    state = json.loads(state_path.read_text())
    state["request_id"] = "wrong-owner"
    state_path.write_text(json.dumps(state))
    started = []
    monkeypatch.setattr(provider, "start_project_worker", started.append)

    owners = provider.resume_active_contract_workers([
        {"id": "contract-broken"}, {"id": "contract-healthy"},
    ], projects_root=tmp_path / "projects")

    assert owners[0] == {"contract_id": "contract-broken", "state": "owner_blocked",
                         "reason": "shared_client_workspace_rejected"}
    assert owners[1]["state"] == "worker_resumed"
    assert started == [healthy]


def test_submitted_receipt_uses_new_official_proposal_with_exact_title():
    payload = {"job_id": "~job-1", "title": "High-value job"}
    state = {
        "submitted_proposal_entities": [
            {"id": "100", "title": "Old job"},
            {"id": "200", "title": "High-value job"},
        ],
        "active_proposal_entities": [],
    }

    receipt = provider.submitted_proposal_receipt(
        payload, state, evidence_sha256="a" * 64, existing_proposal_ids={"100"},
    )

    assert receipt == {
        "state": "submitted", "job_id": "~job-1", "proposal_id": "200",
        "evidence_sha256": "a" * 64,
    }


def test_independent_public_job_details_are_read_concurrently_in_source_order(tmp_path, monkeypatch):
    active = 0
    peak = 0

    async def navigate(pass_id, seq, label, url, action, settle_seconds, viewport_width):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        path = tmp_path / f"{seq}.json"
        path.write_text(json.dumps({
            "navigated_ok": True, "url": url, "rendered_text": f"detail {url}",
            "rendered_links": [],
        }))
        active -= 1
        return str(path)

    monkeypatch.setattr(provider, "navigate_and_snapshot", navigate)
    jobs = [
        {"id": f"~job-{index}", "href": f"https://www.upwork.com/jobs/~job-{index}",
         "title": f"Job {index}"}
        for index in range(3)
    ]

    results = asyncio.run(provider.read_public_job_details(jobs, pass_id="pass", base=30))

    assert peak == 3
    assert [job["id"] for job, _ in results] == [job["id"] for job in jobs]
    assert all(detail is not None for _, detail in results)


def test_discovery_inspects_every_unique_job_on_provider_page(tmp_path, monkeypatch):
    inspected = []
    search_urls = []

    async def navigate(pass_id, seq, label, url, action, settle_seconds, viewport_width):
        search_urls.append(url)
        path = tmp_path / f"{seq}.json"
        path.write_text(json.dumps({
            "navigated_ok": True, "url": url, "rendered_text": "Search jobs",
            "rendered_links": [
                {"href": f"https://www.upwork.com/jobs/Job-{index}_~0{index}",
                 "text": f"Job {index}"}
                for index in range(11)
            ],
        }))
        return str(path)

    async def read_details(jobs, **kwargs):
        inspected.append([job["id"] for job in jobs])
        return [(job, None) for job in jobs]

    monkeypatch.setattr(provider, "navigate_and_snapshot", navigate)
    monkeypatch.setattr(provider, "read_public_job_details", read_details)
    state = {
        "candidate_jobs": [], "balance": 0, "observed_at": "now",
        "evidence_sha256": {},
    }
    asyncio.run(provider.discover_affordable_proposal(
        state, pass_id="pass", sequence=30, proposals_dir=tmp_path / "proposals",
        inbound_dir=tmp_path / "inbound", inbound_evidence=tmp_path / "evidence",
        cursor_path=tmp_path / "cursor.json",
    ))

    assert len(inspected[0]) == 11
    assert search_urls[0].startswith("https://www.upwork.com/nx/search/jobs/?q=")
    assert "sort=recency&page=2" in search_urls[1]


def test_search_provider_unavailable_keeps_cursor_for_retry(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor.json"
    cursor.write_text(json.dumps({"version": 1, "next_page": 18}))

    async def navigate(pass_id, seq, label, url, action, settle_seconds, viewport_width):
        path = tmp_path / f"{seq}.json"
        path.write_text(json.dumps({
            "navigated_ok": True, "url": url,
            "rendered_text": "We can’t complete your request now\n"
                             "We’re currently experiencing an abnormally high volume of traffic.",
            "rendered_links": [],
        }))
        return str(path)

    monkeypatch.setattr(provider, "navigate_and_snapshot", navigate)
    state = {
        "candidate_jobs": [], "balance": 0, "observed_at": "now",
        "evidence_sha256": {},
    }
    assert asyncio.run(provider.discover_affordable_proposal(
        state, pass_id="pass", sequence=30, proposals_dir=tmp_path / "proposals",
        inbound_dir=tmp_path / "inbound", inbound_evidence=tmp_path / "evidence",
        cursor_path=cursor,
    )) is None

    assert json.loads(cursor.read_text())["next_page"] == 18
    assert state["proposal_discovery"]["provider_state"] == "unavailable"


def test_read_evidence_allows_only_canonical_message_room_redirect(tmp_path):
    def evidence(name, url):
        path = tmp_path / name
        path.write_text(json.dumps({
            "navigated_ok": True,
            "url": url,
            "rendered_text": "Messages",
            "rendered_links": [],
        }), encoding="utf-8")
        return path

    redirected = (
        "https://www.upwork.com/ab/messages/rooms/room_123"
        "?companyReference=abc&sidebar=true"
    )
    assert provider._read_evidence(
        evidence("redirect.json", redirected), provider.MESSAGES_URL,
    )[0] == "Messages"

    rejected_redirects = [
        "https://evil.example/ab/messages/rooms/room_123?sidebar=true",
        "https://www.upwork.com/ab/messages/room_123?sidebar=true",
        "https://www.upwork.com/ab/messages/rooms/room_",
        "https://www.upwork.com/ab/messages/rooms/room_123/extra",
    ]
    for index, url in enumerate(rejected_redirects):
        with pytest.raises(ValueError, match="upwork_readback_incomplete"):
            provider._read_evidence(
                evidence(f"rejected-{index}.json", url), provider.MESSAGES_URL,
            )

    with pytest.raises(ValueError, match="upwork_readback_incomplete"):
        provider._read_evidence(
            evidence("other-expected-url.json", provider.SEARCH_URL + "/room_123"),
            provider.SEARCH_URL,
        )


def test_read_evidence_allows_query_or_fragment_only_for_same_concrete_room(tmp_path):
    room_url = f"{provider.MESSAGES_URL}/room_8154dc46c1fed6b388c86d4bf15211cb"

    def evidence(name, url):
        path = tmp_path / name
        path.write_text(json.dumps({
            "navigated_ok": True,
            "url": url,
            "rendered_text": "Messages",
            "rendered_links": [],
        }), encoding="utf-8")
        return path

    for index, observed_url in enumerate((
        f"{room_url}?sidebar=true",
        f"{room_url}#room-detail",
    )):
        assert provider._read_evidence(
            evidence(f"allowed-{index}.json", observed_url), room_url,
        )[0] == "Messages"

    rejected_redirects = [
        f"{provider.MESSAGES_URL}/room_different?sidebar=true",
        f"https://evil.example/ab/messages/rooms/{room_url.rsplit('/', 1)[-1]}?sidebar=true",
        f"{room_url}/extra?sidebar=true",
        f"{provider.MESSAGES_URL}/room_?sidebar=true",
    ]
    for index, observed_url in enumerate(rejected_redirects):
        with pytest.raises(ValueError, match="upwork_readback_incomplete"):
            provider._read_evidence(
                evidence(f"rejected-concrete-{index}.json", observed_url), room_url,
            )

    with pytest.raises(ValueError, match="upwork_readback_incomplete"):
        provider._read_evidence(
            evidence("rejected-non-messages.json", f"{provider.SEARCH_URL}?sidebar=true"),
            provider.SEARCH_URL,
        )


def test_parses_zero_connects_without_inventing_a_reward():
    state = parse_connects(
        "Connects History\nMy balance\n0 Connects\nNo Connects transactions.\n"
    )
    assert state == {"balance": 0, "transactions_empty": True}


def test_parses_complete_zero_effect_inventory_and_account_task():
    state = parse_inventory(
        "Offers  (0)\nInvites from clients (0)\n0 connects to apply to these jobs\n"
        "Active proposals  (0)\nSubmitted proposals  (0)\n"
        "To do: Take the working style assessment.\n"
    )
    assert state == {
        "offers": 0,
        "invites": 0,
        "active_proposals": 0,
        "submitted_proposals": 0,
        "account_tasks": ["working_style_assessment"],
        "working_style": {"completed": False, "strengths": []},
    }


def test_completed_working_style_result_overrides_stale_todo_banner():
    state = parse_inventory(
        "Offers (0)\nInvites from clients (0)\nActive proposals (0)\n"
        "Submitted proposals (0)\nTo do: Take the working style assessment.\n",
        "Working style assessment results\nAccountable for outcomes\n"
        "Shown on profile\nDetail-oriented\nShown on profile\n",
    )
    assert state["account_tasks"] == []
    assert state["working_style"] == {
        "completed": True,
        "strengths": ["Accountable for outcomes", "Detail-oriented"],
    }


def test_parses_singular_submitted_proposal_count():
    state = parse_inventory(
        "Offers (0)\nInvites from clients (0)\nActive proposals (0)\nSubmitted proposal (1)\n"
    )
    assert state["submitted_proposals"] == 1


def test_parses_singular_active_proposal_count():
    state = parse_inventory(
        "Offers (0)\nInvites from clients (0)\nActive proposal (1)\nSubmitted proposal (1)\n"
    )
    assert state["active_proposals"] == 1


def test_parses_visible_catalog_inventory_without_inventing_an_order():
    state = parse_catalog(
        "Approved (1)\nUnder Review (0)\nDrafts (0)\n"
        "Views (30 days)\nOrders\nVisible\n"
        "You will get a Python script integrating one documented REST API endpoint\n"
        "0\n0\nMore Project Options\n"
    )
    assert state == {
        "catalog_approved": 1,
        "catalog_under_review": 0,
        "catalog_drafts": 0,
        "catalog_projects": [{
            "title": "You will get a Python script integrating one documented REST API endpoint",
            "visible": True,
            "views_30d": 0,
            "orders": 0,
        }],
    }


def test_parses_current_catalog_marker_only_project_with_unknown_metrics():
    state = parse_catalog(
        "Create and manage your services\nProjects\nApproved (1)\n"
        "Under Review (0)\nDrafts (0)\n"
        "You will get a Python script integrating one documented REST API endpoint\n"
        "More Project Options\nCreate a project...\n"
    )
    assert state == {
        "catalog_approved": 1,
        "catalog_under_review": 0,
        "catalog_drafts": 0,
        "catalog_projects": [{
            "title": "You will get a Python script integrating one documented REST API endpoint",
            "visible": True,
            "views_30d": None,
            "orders": None,
        }],
    }


def test_catalog_forbidden_is_unknown_without_blocking_other_surfaces():
    assert parse_catalog(
        "Upwork\nSorry, we can't let you in\n"
        "Make sure you're logged in with the right account\nError 403 (N)"
    ) == {
        "catalog_readback_state": "forbidden",
        "catalog_approved": None,
        "catalog_under_review": None,
        "catalog_drafts": None,
        "catalog_projects": [],
    }


def test_parses_zero_contract_and_message_effects_from_official_empty_states():
    assert parse_contracts(
        "Earnings available now: $0.00\nActive contracts\n"
        "There are no active contracts.\n",
        [],
    ) == {"earnings_available_usd_minor": 0, "active_contracts": []}
    assert parse_messages(
        "Messages\nUnread\nFavorites\nConversations will appear here\n",
        [],
    ) == {"message_rooms": [], "unread_message_room_ids": []}


def test_payment_observer_prioritizes_exception_without_recognizing_revenue():
    clear = provider.parse_payment_observer(
        "Transactions\nAvailable balance\n$0.00\nPending earnings\n$0.00\n"
        "No pending transactions\nNo more transactions.",
        "Withdrawals\nComplete your tax profile to access funds in your account\n"
        "Available balance\n$0.00\n+$0.00 pending\n"
        "You haven’t set up any withdrawal methods yet.",
    )
    exception = provider.parse_payment_observer(
        "Transactions\nAvailable balance\n$0.00\nPending earnings\n$25.00\n"
        "Aug 26, 2026\nRefund\n-$10.00",
        "Withdrawals\nAvailable balance\n$0.00\n+$25.00 pending",
    )

    assert clear == {
        "state": "clear", "priority": 2, "owner": "upwork-payment-observer",
        "next_check": "next_wake", "available_usd_minor": 0,
        "pending_usd_minor": 0, "tax_profile_complete": False,
        "withdrawal_method_configured": False, "recognized_revenue_usd_minor": None,
    }
    assert exception["state"] == "exception"
    assert exception["pending_usd_minor"] == 2500
    assert exception["recognized_revenue_usd_minor"] is None


def test_message_observation_prioritizes_unread_without_dropping_rooms():
    rooms = [
        {"id": f"room_{index}", "href": f"https://www.upwork.com/ab/messages/rooms/room_{index}"}
        for index in range(21)
    ]

    ordered = provider.prioritize_message_rooms({
        "message_rooms": rooms,
        "unread_message_room_ids": ["room_20"],
    })

    assert ordered[0]["id"] == "room_20"
    assert {room["id"] for room in ordered} == {room["id"] for room in rooms}


def test_extracts_stable_official_ids_instead_of_titles():
    state = parse_stable_entities(
        invite_links=[{
            "href": "https://www.upwork.com/jobs/python-task-~012ABC",
            "text": "Python task", "context": "Client invited you to apply",
        }],
        proposal_links=[
            {
                "href": "https://www.upwork.com/ab/proposals/offer-77",
                "text": "Offer", "context": "Offers Active offer",
            },
            {
                "href": "https://www.upwork.com/ab/proposals/active-88",
                "text": "Python API", "context": "Active proposals",
            },
            {
                "href": "https://www.upwork.com/ab/proposals/submitted-99",
                "text": "iOS fix", "context": "Submitted proposals",
            },
        ],
    )
    assert state["invitation_entities"][0]["id"] == "~012ABC"
    assert state["proposal_offer_entities"][0]["id"] == "offer-77"
    assert state["active_proposal_entities"][0]["id"] == "active-88"
    assert state["submitted_proposal_entities"][0]["id"] == "submitted-99"


def test_classifies_numeric_received_proposal_and_interview_as_invitation():
    state = parse_stable_entities(
        invite_links=[],
        proposal_links=[
            {
                "href": "https://www.upwork.com/nx/proposals/2091851780096692225",
                "text": "Python API", "context": "Received",
            },
            {
                "href": "https://www.upwork.com/nx/proposals/interview/uid/2092250550587497010",
                "text": "Interview", "context": "Received",
            },
        ],
    )
    assert [item["id"] for item in state["active_proposal_entities"]] == [
        "2091851780096692225"
    ]
    assert state["invitation_entities"] == [{
        "id": "2092250550587497010",
        "href": "https://www.upwork.com/nx/proposals/interview/uid/2092250550587497010",
        "title": "Interview",
    }]
    assert state["unclassified_proposal_entities"] == []
    assert provider.plan_zero_connect_inbound(state) == {
        "state": "invitation_detected",
        "resource_id": "2092250550587497010",
        "resource_url": "https://www.upwork.com/nx/proposals/interview/uid/2092250550587497010",
    }


def test_zero_connect_inbound_precedes_public_job_capacity():
    planner = getattr(provider, "plan_zero_connect_inbound", None)
    assert callable(planner)
    base = {"proposal_offer_entities": [], "invitation_entities": [], "catalog_projects": []}

    assert planner({**base, "invitation_entities": [{
        "id": "~invite-1", "href": "https://www.upwork.com/jobs/~invite-1",
    }]}) == {
        "state": "invitation_detected", "resource_id": "~invite-1",
        "resource_url": "https://www.upwork.com/jobs/~invite-1",
    }
    assert planner({
        **base, "proposal_offer_entities": [{
            "id": "offer-1", "href": "https://www.upwork.com/ab/proposals/offer-1",
        }],
        "invitation_entities": [{
            "id": "~invite-1", "href": "https://www.upwork.com/jobs/~invite-1",
        }],
    }) == {
        "state": "direct_offer_detected", "resource_id": "offer-1",
        "resource_url": "https://www.upwork.com/ab/proposals/offer-1",
    }
    assert planner({**base, "catalog_projects": [{"title": "API script", "orders": 1}]}) == {
        "state": "catalog_order_identity_pending", "order_count": 1,
    }
    assert planner({**base, "catalog_projects": [{"title": "API script", "orders": None}]}) is None
    assert planner(base) is None


def test_terminal_upwork_skip_excludes_only_that_inbound_entity(tmp_path, monkeypatch):
    monkeypatch.setattr(provider, "DEFAULT_GIG_DIR", tmp_path)
    events = tmp_path / "work-events.jsonl"
    events.write_text(
        "not-json\n"
        + json.dumps({
            "kind": "application", "state": "skipped", "entity_id": "terminal-1",
            "attributes": {"platform": "upwork", "terminal": True},
        })
        + "\n"
        + json.dumps({
            "kind": "application", "state": "skipped", "entity_id": "retry-1",
            "attributes": {"platform": "upwork"},
        })
        + "\n",
        encoding="utf-8",
    )
    state = {
        "proposal_offer_entities": [],
        "invitation_entities": [
            {"id": "terminal-1", "href": "https://www.upwork.com/jobs/terminal-1"},
            {"id": "retry-1", "href": "https://www.upwork.com/jobs/retry-1"},
        ],
        "catalog_projects": [],
    }

    excluded = provider.load_terminal_upwork_application_ids(events)

    assert provider.plan_zero_connect_inbound(state, excluded_entity_ids=excluded) == {
        "state": "invitation_detected", "resource_id": "retry-1",
        "resource_url": "https://www.upwork.com/jobs/retry-1",
    }
    assert provider.plan_zero_connect_inbound(
        {**state, "invitation_entities": [state["invitation_entities"][1]]},
        excluded_entity_ids=excluded,
    ) == {
        "state": "invitation_detected", "resource_id": "retry-1",
        "resource_url": "https://www.upwork.com/jobs/retry-1",
    }
    assert provider.plan_zero_connect_inbound(
        {
            **state,
            "invitation_entities": [state["invitation_entities"][0]],
            "catalog_projects": [{"title": "API script", "orders": 1}],
        },
        excluded_entity_ids=excluded,
    ) == {"state": "catalog_order_identity_pending", "order_count": 1}


def test_inbound_detail_is_actionable_only_from_official_controls():
    parser = getattr(provider, "parse_zero_connect_detail", None)
    assert callable(parser)
    assert parser("invitation_detected", "Accept and send a proposal  Decline") == "actionable"
    assert parser("direct_offer_detected", "Accept offer  Decline") == "actionable"
    assert parser("invitation_detected", "Client invited you to apply") == "unknown"
    assert parser("direct_offer_detected", "Offer details") == "unknown"


def test_actionable_inbound_is_sealed_privately_without_public_copy(tmp_path):
    sealer = getattr(provider, "seal_inbound_detail", None)
    assert callable(sealer)
    inbound = {
        "state": "invitation_detected", "resource_id": "~invite-1",
        "resource_url": "https://www.upwork.com/jobs/~invite-1",
    }

    digest = sealer(inbound, "Private invitation details", "a" * 64, tmp_path / "queue", "now")
    packet = tmp_path / "queue" / f"{digest}.json"

    assert packet.is_file()
    assert packet.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "queue").stat().st_mode & 0o777 == 0o700
    assert "Private invitation details" in packet.read_text()
    assert "Private invitation details" not in digest


def test_classifies_candidate_only_from_official_job_markers():
    candidate = {"job_id": "~01", "job_url": "https://www.upwork.com/jobs/~01"}
    opened = parse_candidate(
        candidate,
        "Job title\nSend a proposal for: 7 Connects\nAvailable Connects: 0\n",
        "a" * 64,
    )
    assert (opened["status"], opened["connects_required"]) == ("open", 7)
    parked = parse_candidate(
        candidate,
        "Required Connects to submit a proposal: 26\nAvailable Connects: 0\n",
        "e" * 64,
    )
    assert (parked["status"], parked["connects_required"]) == ("open", 26)
    assert parse_candidate(
        candidate, "This job is no longer available.\nHired: 1\n", "b" * 64,
    )["status"] == "closed"
    assert parse_candidate(
        candidate, "This job has been removed from Upwork.", "c" * 64,
    )["status"] == "removed"
    assert parse_candidate(candidate, "Job detail loading", "d" * 64)["status"] == "unknown"


def test_unknown_candidate_keeps_last_official_connects_cost_without_becoming_open():
    current = [{
        "job_id": "~01", "status": "unknown", "official_marker": "no_authoritative_marker",
        "connects_required": None, "evidence_sha256": "c" * 64,
    }]
    previous = {"candidate_jobs": [{
        "job_id": "~01", "status": "open", "official_marker": "proposal_entry",
        "connects_required": 7, "evidence_sha256": "p" * 64,
    }]}

    reconciled = provider.retain_last_official_candidate_costs(current, previous)

    assert reconciled == [{
        "job_id": "~01", "status": "unknown", "official_marker": "no_authoritative_marker",
        "connects_required": 7, "evidence_sha256": "c" * 64,
        "connects_evidence_sha256": "p" * 64,
    }]


def test_public_candidate_config_has_unique_exact_ids():
    path = SCRIPTS.parent / "config" / "upwork-candidates.public.json"
    candidates = load_candidates(path)
    assert len(candidates) == 3
    assert len({item["job_id"] for item in candidates}) == 3
    assert all(item["job_id"] in item["job_url"] for item in candidates)
    assert all(item["queue"] == "ready" for item in candidates)
    assert all(len(item["proposal_payload_sha256"]) == 64 for item in candidates)


def _sealed_proposal(
    path: Path, *, job_id: str = "~01", connects: int = 7,
    job_url: str | None = None,
) -> str:
    payload = {
        "attachments": [],
        "cover_letter": "A job-specific factual proposal.",
        "job_id": job_id,
        "job_source_sha256": "1" * 64,
        "job_url": job_url or f"https://www.upwork.com/jobs/{job_id}",
        "provider": "upwork",
        "screening_answers": [],
        "status": "frozen_waiting_for_connects",
        "terms": {
            "type": "fixed_price", "bid_usd": 15,
            "delivery_days": 1, "required_connects": connects,
            "available_connects_before": 0,
        },
        "title": "One bounded job",
        "unsupported_claims": [],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n"
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    payload["payload_sha256"] = digest
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return digest


def test_zero_balance_never_selects_a_private_proposal(tmp_path):
    proposals = tmp_path / "proposals"
    proposals.mkdir(mode=0o700)
    _sealed_proposal(proposals / "01.json")
    planner = getattr(provider, "plan_free_proposal", None)

    assert planner is not None
    assert planner({"balance": 0, "candidate_jobs": []}, proposals) is None


def test_exact_free_capacity_selects_only_the_hash_bound_live_job(tmp_path):
    proposals = tmp_path / "proposals"
    proposals.mkdir(mode=0o700)
    digest = _sealed_proposal(
        proposals / "01.json",
        job_url="https://www.upwork.com/jobs/One-bounded-job_~01/",
    )
    state = {
        "balance": 7,
        "candidate_jobs": [{
            "job_id": "~01", "status": "open", "queue": "ready",
            "job_url": "https://www.upwork.com/jobs/~01",
            "connects_required": 7, "proposal_payload_sha256": digest,
        }],
    }
    planner = getattr(provider, "plan_free_proposal", None)

    assert planner is not None
    selected = planner(state, proposals)
    assert selected["job_id"] == "~01"
    assert selected["payload_sha256"] == digest
    assert selected["terms"]["required_connects"] == 7
    assert planner(state, proposals, {"~01"}) is None


def test_terminal_transition_is_fsynced_once_and_replay_is_zero(tmp_path):
    output = tmp_path / "state.json"
    ledger = tmp_path / "transitions.jsonl"
    previous = {
        "observed_at": "2026-08-22T00:00:00+00:00",
        "candidate_jobs": [{
            "job_id": "~01", "status": "closed", "evidence_sha256": "a" * 64,
        }],
    }
    output.write_text(json.dumps(previous), encoding="utf-8")
    current = {
        "observed_at": "2026-08-22T00:05:00+00:00",
        "candidate_jobs": [{
            "job_id": "~01", "status": "closed",
            "official_marker": "no_longer_available", "evidence_sha256": "b" * 64,
        }],
    }
    first = reconcile_terminal_transitions(output, ledger, current)
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert first["terminal_transitions_appended"] == 1
    assert rows[0]["from_status"] == "legacy_observed"
    assert rows[0]["to_status"] == "closed"
    assert rows[0]["official_reason"] == "no_longer_available"
    first_size = ledger.stat().st_size

    replay = reconcile_terminal_transitions(output, ledger, current)
    assert replay["terminal_transitions_appended"] == 0
    assert ledger.stat().st_size == first_size
    assert ledger.stat().st_mode & 0o777 == 0o600


def test_reopen_then_remove_creates_a_distinct_terminal_transition(tmp_path):
    output, ledger = tmp_path / "state.json", tmp_path / "transitions.jsonl"
    opened = {
        "observed_at": "2026-08-22T00:10:00+00:00",
        "candidate_jobs": [{
            "job_id": "~01", "status": "open", "evidence_sha256": "c" * 64,
        }],
    }
    reconcile_terminal_transitions(output, ledger, opened)
    removed = {
        "observed_at": "2026-08-22T00:15:00+00:00",
        "candidate_jobs": [{
            "job_id": "~01", "status": "removed",
            "official_marker": "removed", "evidence_sha256": "d" * 64,
        }],
    }
    result = reconcile_terminal_transitions(output, ledger, removed)
    assert result["terminal_transitions_appended"] == 1
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert (row["from_status"], row["to_status"]) == ("open", "removed")


def test_no_reply_buyer_head_is_fsynced_once_as_terminal(tmp_path):
    output, ledger = tmp_path / "state.json", tmp_path / "transitions.jsonl"
    current = {
        "observed_at": "2026-08-26T08:58:07+00:00",
        "negotiation_intents": [{
            "event_id": "buyer-event-1",
            "room_id": "room_1",
            "head_sha256": "a" * 64,
            "decision": "no_reply",
            "reason_codes": ["client_filled_position", "no_response_owed"],
        }],
    }

    first = reconcile_terminal_transitions(output, ledger, current)
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert first["terminal_transitions_appended"] == 1
    assert row["resource_kind"] == "buyer_head"
    assert row["resource_id"] == "room_1"
    assert row["to_status"] == "terminal"

    replay = reconcile_terminal_transitions(output, ledger, current)
    assert replay["terminal_transitions_appended"] == 0
    assert len(ledger.read_text().splitlines()) == 1


@pytest.mark.parametrize("parser,text", [
    (parse_connects, "Connects History unavailable"),
    (parse_inventory, "Proposals and Offers loading"),
    (parse_catalog, "Create and manage your services\nProjects loading"),
])
def test_partial_provider_pages_fail_closed(parser, text):
    with pytest.raises(ValueError, match="upwork_readback_incomplete"):
        parser(text)


def test_browser_identity_resolution_returns_only_profile_owned_endpoint(tmp_path):
    resolver = tmp_path / "resolver.py"
    resolver.write_text(
        "import json\n"
        "print(json.dumps({\"identity\": \"upwork:dais\", \"profile\": \"/private/gig-upwork\","
        " \"endpoint\": \"http://127.0.0.1:9233\", \"reachable\": True,"
        " \"http_status\": 200, \"websocket_url_valid\": True}))\n",
        encoding="utf-8",
    )
    resolved = provider.resolve_browser_identity(
        "upwork:dais", registry=tmp_path / "browsers.toml", resolver=resolver,
    )

    assert resolved == {
        "identity": "upwork:dais",
        "profile": "/private/gig-upwork",
        "endpoint": "http://127.0.0.1:9233",
    }


def test_browser_identity_resolution_rejects_unreachable_endpoint(tmp_path):
    resolver = tmp_path / "resolver.py"
    resolver.write_text(
        "import json\n"
        "print(json.dumps({\"identity\": \"upwork:dais\", \"reachable\": False,"
        " \"error_class\": \"endpoint_unavailable\"}))\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="upwork_browser_identity_unavailable"):
        provider.resolve_browser_identity(
            "upwork:dais", registry=tmp_path / "browsers.toml", resolver=resolver,
        )


def test_launchd_job_is_zero_spend_and_runs_every_five_minutes(monkeypatch):
    import gig_release

    manifest = json.loads((SCRIPTS.parent / "config" / "launchd-jobs.json").read_text())
    jobs = manifest["jobs"]
    labels = [item["label"] for item in jobs]
    dedicated_label = "ai.anicca.life-manager-upwork-browser"
    assert dedicated_label in labels
    assert dedicated_label not in gig_release.DEFAULT_EXCLUDED
    browser_index = labels.index(dedicated_label)
    upwork_index = next(index for index, item in enumerate(jobs) if item["lane"] == "upwork-free")
    assert browser_index < upwork_index
    browser = jobs[browser_index]
    assert browser["program"] == [
        "/bin/bash",
        "{{RELEASE}}/skills/earn/gig/scripts/launch_gig_browser.sh",
    ]
    assert browser["env"]["GIG_BROWSER_PORT"] == "9233"
    assert browser["env"]["GIG_BROWSER_PROFILE"] == "{{HOME}}/.cloak/profiles/gig-upwork"
    assert browser["env"]["GIG_BROWSER_FINGERPRINT"] == "80138"
    assert browser["KeepAlive"] is True
    assert browser["log_basename"] == "upwork-browser-launchd"
    assert browser["ThrottleInterval"] == 30
    assert browser["ProcessType"] == "Interactive"
    job = jobs[upwork_index]
    identity_index = job["program"].index("--browser-identity")
    assert job["program"][identity_index + 1] == "upwork:dais"
    monkeypatch.setattr(gig_release, "OVERRIDES", Path("/nonexistent/install.json"))
    rendered_manifest, table = gig_release.settings(Path("/release"))
    rendered_browser = next(item for item in rendered_manifest["jobs"] if item["label"] == dedicated_label)
    rendered_env = gig_release.plist_for(rendered_browser, table)["EnvironmentVariables"]
    assert rendered_env["GIG_BROWSER_OWNER"] == "upwork-revenue-browser"
    assert rendered_env["SESSION_VAULT_DIR"] == str(Path.home() / ".cloak/vault/gig-upwork")
    assert rendered_env["CLOAK_BROWSER_LAUNCHD_LABEL"] == dedicated_label

    command = " ".join(job["program"]).lower()
    assert job["StartInterval"] == 300
    assert "upwork_browser_provider.py" in command
    assert "upwork-candidates.public.json" in command
    assert "upwork-free-transitions.jsonl" in command
    assert all(term not in command for term in ("buy", "billing", "plus", "boost"))
    assert "--cdp-base" not in job["program"]
    assert "CLOAK_CDP_BASE_URL" not in job["env"]
    assert job["env"]["CLOAK_BROWSER_LAUNCHD_LABEL"] == dedicated_label
