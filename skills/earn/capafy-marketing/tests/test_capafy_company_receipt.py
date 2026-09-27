from __future__ import annotations

import importlib.util
import inspect
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "capafy_company_receipt.py"
GOAL_MONITOR = Path(__file__).parents[1] / "capafy-goal-monitor.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_company_receipt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sources() -> dict:
    return {
        "inventory": {
            "readable": True,
            "counts": {"total": 32, "listed": 22, "occupied": 3, "free": 2, "retry": 7, "blocked": 0, "unknown": 0},
        },
        "candidate": {
            "candidate_id": "capafy-o13-interviews",
            "title": "Interview Synthesizer",
            "content_sha256": "sha256:" + "a" * 64,
            "state": "ready",
            "platform_state": "not_submitted",
        },
        "marketing": {
            "telegram_message_id": "27263",
            "outcome": {
                "agent_id": "7785270416",
                "title": "Data Analyst",
                "reel_url": "https://www.instagram.com/reel/abc/",
                "media_sha256": "sha256:" + "b" * 64,
                "owner_session_verified": True,
            },
        },
        "money": {
            "observed_at": "2026-08-22T10:00:00Z",
            "orders": 5,
            "money": {"gross_usd": "19.98", "one_time_revenue_usd": None, "pending_usd": "8.00", "realized_usd": "0.00", "refunds_usd": "0.00", "settled_mrr_usd": None, "net_mrr_usd": None},
            "money_status": {"settled_mrr_usd": "unknown_no_seller_subscription_source"},
        },
        "growth": {
            "signal": "sales",
            "company_orders": 1,
            "winner": {"agent_id": "6839055303", "name": "Academic Humanizer"},
            "attribution_status": "official_seller_ranking",
        },
    }


def test_receipt_joins_skill_slots_post_money_under_one_run_id() -> None:
    module = load_module()
    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")

    assert receipt["run_id"].startswith("capafy-")
    assert receipt["skill"]["candidate_id"] == "capafy-o13-interviews"
    assert receipt["slots"]["occupied"] == 3
    assert receipt["distribution"][0]["native_url"].endswith("/abc/")
    assert receipt["money"]["gross_usd"] == "19.98"
    assert receipt["money"]["settled_mrr_usd"] is None
    assert receipt["growth_signal"] == {
        "signal": "sales",
        "company_orders": 1,
        "winner_agent_id": "6839055303",
        "attribution_status": "official_seller_ranking",
    }
    assert receipt["telegram"] == {"status": "pending", "message_id": None}


def test_missing_marketing_terminal_uses_native_ig_ledger_without_claiming_session_proof(
    tmp_path: Path,
) -> None:
    module = load_module()
    ledger = tmp_path / "capafy-marketing-ig-ledger.jsonl"
    ledger.write_text(json.dumps({
        "platform": "ig", "agent_id": "7785270416", "listing_name": "Data Analyst",
        "reel_url": "https://www.instagram.com/reel/abc/", "artifact_sha256": "a" * 64,
    }) + "\n")

    marketing = module._marketing_from_ledger(ledger)
    receipt = module.build_receipt({**sources(), "marketing": marketing}, "2026-09-17T00:00:00Z")

    assert receipt["distribution"][0] == {
        "platform": "instagram", "skill_agent_id": "7785270416",
        "skill_name": "Data Analyst", "native_url": "https://www.instagram.com/reel/abc/",
        "creative_sha256": "sha256:" + "a" * 64, "owner_session_verified": None,
        "status": "native_ledger_observed",
    }
    assert module._marketing_from_ledger(tmp_path / "missing.jsonl")["status"] == "unknown_no_native_ig_ledger"


def test_semantic_replay_has_same_run_id_but_new_state_changes_it() -> None:
    module = load_module()
    first = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    replay = module.build_receipt(sources(), "2026-08-22T12:00:00Z")
    changed_sources = sources()
    changed_sources["inventory"]["counts"]["occupied"] = 4
    changed = module.build_receipt(changed_sources, "2026-08-22T12:00:00Z")

    assert first["run_id"] == replay["run_id"]
    assert changed["run_id"] != first["run_id"]


def test_delivery_sends_exact_state_once_and_persists_message_id(tmp_path: Path) -> None:
    module = load_module()
    calls = []

    def sender(message: str) -> str:
        calls.append(message)
        return "9001"

    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    first = module.deliver_receipt(receipt, tmp_path / "outbox.sqlite", tmp_path / "receipts", sender)
    replay = module.deliver_receipt(receipt, tmp_path / "outbox.sqlite", tmp_path / "receipts", sender)

    assert calls == [module.render_message(receipt)]
    assert first["telegram"] == {"status": "delivered", "message_id": "9001"}
    assert replay == first
    persisted = json.loads((tmp_path / "receipts" / f"{receipt['run_id']}.json").read_text())
    assert persisted["telegram"]["message_id"] == "9001"


def test_provider_without_message_id_is_quarantined_and_not_retried(tmp_path: Path) -> None:
    module = load_module()
    calls = 0

    def sender(_message: str) -> str:
        nonlocal calls
        calls += 1
        raise module.DeliveryUncertain("message_id_missing")

    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    first = module.deliver_receipt(receipt, tmp_path / "outbox.sqlite", tmp_path / "receipts", sender)
    replay = module.deliver_receipt(receipt, tmp_path / "outbox.sqlite", tmp_path / "receipts", sender)

    assert calls == 1
    assert first["telegram"]["status"] == "delivery_uncertain"
    assert replay == first


def test_direct_sender_returns_message_id_once_and_uses_life_manager_env(tmp_path: Path, monkeypatch) -> None:
    state_home = tmp_path / "life-manager"
    state_home.mkdir()
    (state_home / ".env").write_text("TELEGRAM_BOT_TOKEN=fixture-token\n", encoding="utf-8")
    monkeypatch.setenv("LIFE_MANAGER_STATE_HOME", str(state_home))
    monkeypatch.setenv("CAPAFY_TELEGRAM_TARGET", "fixture-chat")
    module = load_module()
    calls = []

    class StubTelegramClient:
        @classmethod
        def from_env(cls, *, environ, env_file):
            calls.append(("from_env", environ, env_file))
            return cls()

        def send_text(self, text, *, chat_id):
            calls.append(("send_text", text, chat_id))
            return {"status": "delivered", "message_ids": [9001]}

    monkeypatch.setattr(module, "TelegramClient", StubTelegramClient)
    assert module._telegram_sender("fixture report") == "9001"
    assert calls[0][0] == "from_env"
    assert calls[0][1]["TELEGRAM_CHAT_ID"] == "fixture-chat"
    assert calls[0][2] == state_home / ".env"
    assert calls[1:] == [
        ("send_text", "fixture report", "fixture-chat"),
    ]


@pytest.mark.parametrize("error_kind", ("transport_unknown", "provider_error"))
def test_direct_transport_or_provider_error_quarantines_once_and_replay_does_not_retry(
    tmp_path: Path, monkeypatch, error_kind: str
) -> None:
    state_home = tmp_path / "life-manager"
    state_home.mkdir()
    monkeypatch.setenv("LIFE_MANAGER_STATE_HOME", str(state_home))
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "fixture-chat")
    module = load_module()
    calls = 0

    class StubTelegramClient:
        @classmethod
        def from_env(cls, *, environ, env_file):
            assert environ["TELEGRAM_CHAT_ID"] == "fixture-chat"
            assert env_file == state_home / ".env"
            return cls()

        def send_text(self, _text, *, chat_id):
            nonlocal calls
            assert chat_id == "fixture-chat"
            calls += 1
            if error_kind == "transport_unknown":
                raise module.TelegramDeliveryUnknown("transport lost")
            raise module.TelegramError("provider rejected", error_code=400)

    monkeypatch.setattr(module, "TelegramClient", StubTelegramClient)
    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    outbox = tmp_path / "outbox.sqlite"
    receipts = tmp_path / "receipts"
    first = module.deliver_receipt(receipt, outbox, receipts, module._telegram_sender)
    replay = module.deliver_receipt(receipt, outbox, receipts, module._telegram_sender)

    assert calls == 1
    assert first["telegram"] == {"status": "delivery_uncertain", "message_id": None}
    assert replay == first
    with sqlite3.connect(outbox) as db:
        row = db.execute("SELECT status, attempt_count, provider_message_id, last_error_code FROM telegram_outbox").fetchone()
    expected_error = "sender_delivery_unknown" if error_kind == "transport_unknown" else "sender_provider_error_400"
    assert row == ("delivery_uncertain", 1, None, expected_error)


def test_direct_sender_has_no_openclaw_call_or_subprocess() -> None:
    module = load_module()
    source = inspect.getsource(module._telegram_sender).lower()

    assert "openclaw message send" not in source
    assert "subprocess" not in source


@pytest.mark.parametrize("outbox_status", ("delivery_uncertain", "delivered"))
def test_replay_recovers_missing_receipt_from_authoritative_outbox(tmp_path: Path, outbox_status: str) -> None:
    module = load_module()
    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    outbox = tmp_path / "outbox.sqlite"
    receipts = tmp_path / "receipts"
    message = module.render_message(receipt)
    assert module.enqueue(outbox, receipt["run_id"], message, receipt["observed_at"]) is True
    assert module.claim_next(outbox) is not None
    if outbox_status == "delivery_uncertain":
        module.mark_delivery_uncertain(outbox, receipt["run_id"], "sender_timeout")
    else:
        module.mark_delivered(outbox, receipt["run_id"], "9002", "2026-08-22T11:01:00Z")

    def sender(_message: str) -> str:
        raise AssertionError("exact replay must not call provider")

    recovered = module.deliver_receipt(receipt, outbox, receipts, sender)

    expected = {
        "status": "delivered" if outbox_status == "delivered" else "delivery_uncertain",
        "message_id": "9002" if outbox_status == "delivered" else None,
    }
    assert recovered["telegram"] == expected
    receipt_path = receipts / f"{receipt['run_id']}.json"
    if outbox_status == "delivered":
        persisted = json.loads(receipt_path.read_text())
        assert persisted["telegram"] == expected
    else:
        assert not receipt_path.exists()


def test_uncertain_replay_cannot_overwrite_existing_delivered_receipt(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    receipt_path = receipts / f"{receipt['run_id']}.json"
    delivered = {**receipt, "telegram": {"status": "delivered", "message_id": "9003"}}
    receipt_path.write_text(json.dumps(delivered), encoding="utf-8")
    outbox = tmp_path / "outbox.sqlite"
    module.enqueue(outbox, receipt["run_id"], module.render_message(receipt), receipt["observed_at"])

    class _Uncertain:
        event_key = receipt["run_id"]
        status = "delivery_uncertain"
        provider_message_id = None

    monkeypatch.setattr(module, "list_items", lambda _database: [_Uncertain()])
    replay = module.deliver_receipt(receipt, outbox, receipts, lambda _message: pytest.fail("must not send"))

    assert replay["telegram"] == delivered["telegram"]
    assert json.loads(receipt_path.read_text())["telegram"] == delivered["telegram"]


def _skill_analytics_fixture(**overrides) -> dict:
    fixture = {
        "schema_version": 1,
        "kind": "capafy_skill_analytics",
        "account_totals": {
            "_status": "fresh",
            "last_30d": {"gross_usd": "66.81", "net_usd": "66.81", "orders": 88, "refunds_usd": "0.00"},
            "last_7d": {"gross_usd": "17.91", "net_usd": "17.91", "orders": 9, "refunds_usd": "0.00"},
        },
        "per_skill_rows_status": "fresh",
        "per_skill_rows": [
            {"agent_id": "8123079349", "name": None, "since_launch_gross_usd": "34.88",
             "since_launch_skus": [{"skuType": "subscription_week"}]},
            {"agent_id": "8828622062", "name": None, "since_launch_gross_usd": "19.98",
             "since_launch_skus": [{"skuType": "subscription_month"}]},
            {"agent_id": "a3", "name": "Idle Skill", "since_launch_gross_usd": "0.00", "since_launch_skus": []},
        ],
        "rankings": {
            "top_by_earnings": [
                {"agent_id": "8123079349", "name": None, "creator_earnings_usd": "25.40"},
                {"agent_id": "8828622062", "name": None, "creator_earnings_usd": "15.20"},
            ],
            "zero_sales": [{"agent_id": "a3", "name": "Idle Skill"}],
        },
        "subscription_proxy": {"label": "proxy_not_mrr", "last_30d_net_usd": "0.00", "status": "partial"},
    }
    fixture.update(overrides)
    return fixture


def _business_outcomes_row(product_id: str, business_date: str, *, mrr=20.34, actives=5.0, trials=0.0) -> dict:
    return {
        "product_id": product_id,
        "business_date": business_date,
        "sources": {
            "revenuecat": {
                "status": "available",
                "data": {
                    "charts": {
                        "mrr": {"latest_complete": {"MRR": {"value": mrr}}},
                        "actives": {"latest_complete": {"Actives": {"value": actives}}},
                        "trials_new": {"latest_complete": {"New Trials": {"value": trials}}},
                    }
                },
            }
        },
    }


def test_skill_analytics_section_reads_fresh_top5_and_zero_sales(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(_skill_analytics_fixture()), encoding="utf-8")

    section = module._skill_analytics_section(path)

    assert section["status"] == "fresh"
    assert section["last_30d_net_usd"] == "66.81"
    assert section["last_30d_orders"] == 88
    assert section["last_7d_gross_usd"] == "17.91"
    assert section["top_skills"][0] == {"name": "8123079349", "earnings_usd": "25.40"}
    assert section["top_skills"][1] == {"name": "8828622062", "earnings_usd": "15.20"}
    assert section["zero_sales_count"] == 1
    assert section["total_skills"] == 3
    assert section["subscription_signal"] == {
        "amount_usd": "54.86", "label": "since-launch web-console gross, proxy not MRR, not last-30d",
    }


def test_skill_analytics_section_resolves_names_from_live_inventory_and_shortens_them(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(_skill_analytics_fixture()), encoding="utf-8")
    name_by_agent_id = {
        "8123079349": "Hook Lab — Win the First 3 Seconds",
        "8828622062": "Slide Maker — Any Content Into a Styled Deck",
    }

    section = module._skill_analytics_section(path, name_by_agent_id)

    assert section["top_skills"][0] == {"name": "Hook Lab", "earnings_usd": "25.40"}
    assert section["top_skills"][1] == {"name": "Slide Maker", "earnings_usd": "15.20"}


def test_skill_analytics_section_prefers_names_already_in_per_skill_rows(tmp_path: Path) -> None:
    module = load_module()
    fixture = _skill_analytics_fixture()
    fixture["per_skill_rows"][0]["name"] = "Hook Lab — Win the First 3 Seconds"
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    section = module._skill_analytics_section(path, {"8123079349": "Should Not Be Used"})

    assert section["top_skills"][0]["name"] == "Hook Lab"


def test_skill_analytics_section_falls_back_to_agent_id_without_any_name(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(_skill_analytics_fixture()), encoding="utf-8")

    section = module._skill_analytics_section(path)

    assert section["top_skills"][0]["name"] == "8123079349"


def test_subscription_signal_falls_back_to_since_launch_gross_when_settled_net_is_zero(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(_skill_analytics_fixture()), encoding="utf-8")

    section = module._skill_analytics_section(path)

    assert section["subscription_signal"] == {
        "amount_usd": "54.86", "label": "since-launch web-console gross, proxy not MRR, not last-30d",
    }


def test_subscription_signal_uses_settled_net_when_nonzero(tmp_path: Path) -> None:
    module = load_module()
    fixture = _skill_analytics_fixture()
    fixture["subscription_proxy"]["last_30d_net_usd"] = "12.34"
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    section = module._skill_analytics_section(path)

    assert section["subscription_signal"] == {"amount_usd": "12.34", "label": "last30d gross, proxy not MRR"}


def test_subscription_signal_unavailable_when_neither_net_nor_gross_is_real(tmp_path: Path) -> None:
    module = load_module()
    fixture = _skill_analytics_fixture()
    for row in fixture["per_skill_rows"]:
        row["since_launch_gross_usd"] = "0.00"
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    section = module._skill_analytics_section(path)

    assert section["subscription_signal"] == {"status": "unavailable", "reason": "settlement lag"}


def test_skill_analytics_section_missing_file_is_unavailable(tmp_path: Path) -> None:
    module = load_module()
    section = module._skill_analytics_section(tmp_path / "missing.json")
    assert section == {"status": "unavailable", "reason": "missing_capafy_skill_analytics"}


def test_skill_analytics_section_stale_source_is_unavailable(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    stale = _skill_analytics_fixture()
    stale["per_skill_rows_status"] = "stale"
    path.write_text(json.dumps(stale), encoding="utf-8")

    section = module._skill_analytics_section(path)
    assert section["status"] == "unavailable"
    assert "stale_capafy_skill_analytics" in section["reason"]


def test_skill_analytics_section_malformed_json_is_unavailable(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "capafy-skill-analytics.json"
    path.write_text("{not json", encoding="utf-8")
    section = module._skill_analytics_section(path)
    assert section == {"status": "unavailable", "reason": "malformed_capafy_skill_analytics"}


def test_product_metrics_section_picks_latest_revenuecat_available_row(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "business-outcomes.jsonl"
    rows = [
        _business_outcomes_row("anicca-ios", "2026-09-24", mrr=10.0),
        {"product_id": "anicca-ios", "business_date": "2026-09-25",
         "sources": {"revenuecat": {"status": "unavailable", "data": None}}},
        _business_outcomes_row("anicca-ios", "2026-09-26", mrr=20.34, actives=5.0, trials=0.0),
        _business_outcomes_row("honne-ai", "2026-09-26", mrr=0.0, actives=0.0, trials=0.0),
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    section = module._product_metrics_section(path, "anicca-ios")

    assert section == {
        "status": "fresh", "business_date": "2026-09-26", "mrr": 20.34, "actives": 5.0, "new_trials": 0.0,
    }


def test_product_metrics_section_missing_file_is_unavailable(tmp_path: Path) -> None:
    module = load_module()
    section = module._product_metrics_section(tmp_path / "missing.jsonl", "anicca-ios")
    assert section == {"status": "unavailable", "reason": "missing_business_outcomes"}


def test_product_metrics_section_skips_malformed_row_and_finds_valid_one(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "business-outcomes.jsonl"
    good = _business_outcomes_row("honne-ai", "2026-09-26", mrr=1.5, actives=2.0, trials=1.0)
    path.write_text("{not valid json\n" + json.dumps(good) + "\n", encoding="utf-8")

    section = module._product_metrics_section(path, "honne-ai")

    assert section == {
        "status": "fresh", "business_date": "2026-09-26", "mrr": 1.5, "actives": 2.0, "new_trials": 1.0,
    }


def test_product_metrics_section_no_revenuecat_row_is_unavailable(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "business-outcomes.jsonl"
    path.write_text(json.dumps({
        "product_id": "anicca-ios", "business_date": "2026-09-26",
        "sources": {"revenuecat": {"status": "unavailable"}},
    }) + "\n", encoding="utf-8")

    section = module._product_metrics_section(path, "anicca-ios")
    assert section == {"status": "unavailable", "reason": "no_revenuecat_row"}


def test_render_message_includes_fresh_skill_and_product_sections() -> None:
    module = load_module()
    receipt = module.build_receipt({
        **sources(),
        "skill_analytics": {
            "status": "fresh", "last_30d_net_usd": "66.81", "last_30d_orders": 88, "last_7d_gross_usd": "17.91",
            "top_skills": [{"name": "Hook Lab", "earnings_usd": "25.40"}],
            "zero_sales_count": 1, "total_skills": 3,
            "subscription_signal": {
                "amount_usd": "54.86", "label": "since-launch web-console gross, proxy not MRR, not last-30d",
            },
        },
        "product_metrics": {
            "anicca-ios": {"status": "fresh", "business_date": "2026-09-26", "mrr": 20.34, "actives": 5.0, "new_trials": 0.0},
            "honne-ai": {"status": "unavailable", "reason": "no_revenuecat_row"},
        },
    }, "2026-08-22T11:00:00Z")

    message = module.render_message(receipt)

    assert "Skills: net30d=$66.81 orders30d=88 gross7d=$17.91" in message
    assert "Hook Lab=$25.40" in message
    assert "zero-sales=1/3" in message
    assert "sub=$54.86 (since-launch web-console gross, proxy not MRR, not last-30d)" in message
    assert "anicca-ios@2026-09-26(MRR=$20.34 actives=5.0 trials=0.0)" in message
    assert "honne-ai=unavailable (no_revenuecat_row)" in message


def test_render_message_defaults_new_sections_to_unavailable_when_not_provided() -> None:
    module = load_module()
    receipt = module.build_receipt(sources(), "2026-08-22T11:00:00Z")
    message = module.render_message(receipt)
    assert "Skills(30d/7d): unavailable (not_provided)" in message
    assert "anicca-ios=unavailable (no_data)" in message
    assert "honne-ai=unavailable (no_data)" in message


def test_hourly_goal_monitor_uses_unified_receipt_before_shared_sender() -> None:
    source = GOAL_MONITOR.read_text()
    hourly = source.index('CAPAFY_REPORT_KIND:-morning')
    reconcile = source.index("capafy_hourly_reconcile.py", hourly)
    receipt = source.index("capafy_company_receipt.py", reconcile)
    shared = source.index("skills/_shared/send-telegram.sh", receipt)

    assert hourly < reconcile < receipt < shared
    assert 'if [ "$REPORT_KIND" = "hourly" ]' in source
    assert 'exit "$UNIFIED_RC"' in source
