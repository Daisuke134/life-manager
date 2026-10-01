"""CrowdWorks human-required reply work never reaches a provider mutation."""

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / "skills" / "earn" / "crowdworks" / "scripts" / "reply_adapter.py"


def _load():
    spec = importlib.util.spec_from_file_location("crowdworks_human_required_hold_test", ADAPTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_google_form_interview_exam_and_identity_work_are_human_required():
    module = _load()
    adapter = module.CrowdWorksReplyAdapter({})
    adapter.rows = {"thread-1": {"thread_id": "thread-1", "proposal_status": "proposed"}}

    cases = (
        ({"body": "Googleフォームへ回答してください", "links": ["https://forms.gle/example"]}, "Google Form"),
        ({"body": "面接に参加してください", "links": []}, "面接"),
        ({"body": "選考試験を受けてください", "links": []}, "試験"),
        ({"body": "本人確認書類を提出してください", "links": []}, "本人確認"),
    )
    for message, label in cases:
        adapter.conversations = {"thread-1": [{"role": "buyer", **message}]}
        action = adapter._external_form_action("thread-1")
        assert action["action"] == "human"
        assert action["reason"] == "human_required"
        assert label in action["remaining_work"][0]
        assert action["handoff"]["url"] == "https://crowdworks.jp/messages/thread-1"


def test_google_form_route_failure_stays_human_required():
    module = _load()

    result = module.CrowdWorksReplyAdapter.classify_mutation_error(
        RuntimeError("google_form_route_invalid:accounts.google.com")
    )

    assert result == {
        "reason": "human_required",
        "remaining_work": ["Google Form は自動送信せず、人手で確認する"],
    }
