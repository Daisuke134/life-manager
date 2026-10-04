from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "rejection_queue.py"

SAMPLE_BODY = (
    "Agent Marketing Strategist — The One Move to Make\n"
    "Agent ID 9563867391\n"
    "Version v1.0.2\n"
    "Reason [2.2 Information accuracy](https://capafy.ai/developer/doc#4.2)"
)

SAMPLE_BODY_NO_LINK = (
    "Agent Marketing Strategist — The One Move to Make\n"
    "Agent ID 9563867391\n"
    "Version v1.0.2\n"
    "Reason 2.2 Information accuracy"
)


def load_module():
    spec = importlib.util.spec_from_file_location("rejection_queue_reasons", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_rejection_mail_with_link() -> None:
    module = load_module()
    parsed = module.parse_rejection_mail(SAMPLE_BODY)
    assert parsed == {
        "agent_id": "9563867391",
        "version": "v1.0.2",
        "reason": "2.2 Information accuracy",
    }


def test_parse_rejection_mail_without_link() -> None:
    module = load_module()
    parsed = module.parse_rejection_mail(SAMPLE_BODY_NO_LINK)
    assert parsed == {
        "agent_id": "9563867391",
        "version": "v1.0.2",
        "reason": "2.2 Information accuracy",
    }


def test_html_mail_body_converts_to_parseable_text() -> None:
    module = load_module()
    html = (
        "<div><span>Agent ID</span>\n<span>9563867391</span></div>"
        "<div><span>Version</span>\n<span>v1.0.2</span></div>"
        "<div><span>Reason</span>\n"
        '<a href="https://capafy.ai/developer/doc#4.2">2.2 Information accuracy</a></div>'
    )
    text = module._html_to_text(html)
    parsed = module.parse_rejection_mail(text)
    assert parsed == {
        "agent_id": "9563867391",
        "version": "v1.0.2",
        "reason": "2.2 Information accuracy",
    }


def test_parse_rejection_mail_no_agent_id_returns_none() -> None:
    module = load_module()
    assert module.parse_rejection_mail("no agent id here") is None


def test_gmail_merge_sets_reason_observed_and_state_queued() -> None:
    module = load_module()
    agent = {
        "agent_id": "9563867391",
        "name": "Marketing Strategist",
        "latest_version_id": "version-old",
        "latest_version_name": "v1.0.2",
        "remote_status": "review_rejected",
        "lifecycle": "retry",
    }
    detail = {
        "ok": True,
        "agent_id": "9563867391",
        "latest_version": {
            "agentId": "9563867391",
            "agentVersionId": "version-old",
            "versionNo": 2,
            "versionName": "v1.0.2",
            "status": 2,
            "auditStatus": 3,
        },
    }
    details = {"9563867391": detail}
    gmail_reasons = {
        "9563867391": {
            "version": "v1.0.2",
            "reason": "2.2 Information accuracy",
            "observed_mail_at": "2026-09-01T00:00:00Z",
        }
    }
    module._merge_gmail_reasons(details, [agent], gmail_reasons)
    queue = module.build_queue({}, [agent], details, "2026-09-02T00:00:00Z")
    item = queue["items"][0]
    assert item["reason_status"] == "observed"
    assert item["state"] == "queued"
    assert item["rejection_reason"] == "2.2 Information accuracy"


def test_stale_item_for_now_listed_agent_becomes_listed() -> None:
    module = load_module()
    agent = {
        "agent_id": "1111111111",
        "name": "Old Rejected Agent",
        "latest_version_id": "version-old",
        "latest_version_name": "1.0.0",
        "remote_status": "review_rejected",
        "lifecycle": "retry",
    }
    detail = {
        "ok": True,
        "agent_id": "1111111111",
        "latest_version": {
            "agentId": "1111111111",
            "agentVersionId": "version-old",
            "versionNo": 1,
        },
    }
    existing = module.build_queue({}, [agent], {"1111111111": detail}, "2026-08-01T00:00:00Z")
    assert existing["items"][0]["state"] == "needs_diagnosis"

    now_listed = [
        {"agent_id": "1111111111", "remote_status": "online", "lifecycle": "listed"},
    ]
    replay = module.build_queue(existing, [], {}, "2026-09-01T00:00:00Z", all_agents=now_listed)
    assert replay["items"][0]["state"] == "listed"


def test_gmail_rejection_reasons_returns_empty_on_gog_failure(monkeypatch) -> None:
    module = load_module()

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0] if args else "gog")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capafy_publisher_email", lambda: "someone@example.com")
    assert module.gmail_rejection_reasons() == {}


def test_gmail_rejection_reasons_returns_empty_without_credential(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "_capafy_publisher_email", lambda: None)
    assert module.gmail_rejection_reasons() == {}
