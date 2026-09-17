from __future__ import annotations

from job_search_loop.mercor_funnel import project_funnel


def test_duplicate_application_observations_count_once():
    application = {
        "application_id": "application-1",
        "listing_id": "listing-1",
        "status": "submitted",
        "observed_at": "2026-09-17T01:00:00Z",
        "evidence_ref": "https://work.mercor.com/application-1",
    }

    result = project_funnel(
        application_receipts=[application, dict(application)],
        reply_receipts=[],
        work_receipts=[],
        payment_receipts=[],
    )

    assert result["unique_applications"] == 1
    assert result["stage_counts"]["application"] == 1


def test_trial_invitation_is_not_a_contract_or_received_cash():
    result = project_funnel(
        application_receipts=[{
            "application_id": "application-1", "listing_id": "listing-1",
            "status": "submitted", "observed_at": "2026-09-17T01:00:00Z",
            "evidence_ref": "app://1",
        }],
        reply_receipts=[{
            "application_id": "application-1", "status": "trial_invited",
            "observed_at": "2026-09-17T02:00:00Z", "evidence_ref": "mail://trial",
        }],
        work_receipts=[],
        payment_receipts=[],
    )

    project = result["projects"]["application-1"]
    assert project["reply"]["status"] == "trial_invited"
    assert project["work"]["status"] == "unknown"
    assert project["payment"]["status"] == "unknown"
    assert result["received_usd"] == 0


def test_offer_without_billable_work_does_not_count_as_work_or_cash():
    result = project_funnel(
        application_receipts=[{
            "application_id": "application-1", "listing_id": "listing-1",
            "status": "submitted", "observed_at": "2026-09-17T01:00:00Z",
            "evidence_ref": "app://1",
        }],
        reply_receipts=[{
            "application_id": "application-1", "status": "offer",
            "observed_at": "2026-09-17T02:00:00Z", "evidence_ref": "offer://1",
        }],
        work_receipts=[],
        payment_receipts=[],
    )

    assert result["stage_counts"]["offer"] == 1
    assert result["stage_counts"]["work"] == 0
    assert result["received_usd"] == 0


def test_paid_trial_without_contract_is_settled_but_not_received():
    result = project_funnel(
        application_receipts=[],
        reply_receipts=[],
        work_receipts=[{
            "work_id": "trial-1", "status": "trial_submitted",
            "observed_at": "2026-09-17T03:00:00Z", "evidence_ref": "trial://1",
        }],
        payment_receipts=[{
            "payment_id": "payment-1", "work_id": "trial-1", "status": "settled",
            "amount_usd": "25.00", "observed_at": "2026-09-17T04:00:00Z",
            "evidence_ref": "earnings://payment-1",
        }],
    )

    project = result["projects"]["trial-1"]
    assert project["contract"]["status"] == "unknown"
    assert project["work"]["status"] == "trial_submitted"
    assert project["payment"]["status"] == "settled"
    assert result["settled_usd"] == 25.0
    assert result["received_usd"] == 0


def test_received_payout_requires_explicit_received_status():
    result = project_funnel(
        application_receipts=[],
        reply_receipts=[],
        work_receipts=[{
            "work_id": "work-1", "contract_id": "contract-1", "status": "accepted",
            "observed_at": "2026-09-17T03:00:00Z", "evidence_ref": "work://1",
        }],
        payment_receipts=[{
            "payment_id": "payment-1", "work_id": "work-1", "status": "received",
            "amount_usd": "100.00", "observed_at": "2026-09-17T04:00:00Z",
            "evidence_ref": "bank://1",
        }],
    )

    project = result["projects"]["work-1"]
    assert project["contract"]["contract_id"] == "contract-1"
    assert project["payment"]["status"] == "received"
    assert result["received_usd"] == 100.0
