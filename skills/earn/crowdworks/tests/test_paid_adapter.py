from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/paid_adapter.py"
OWNER = ROOT / "skills/earn/crowdworks/scripts/paid-owner"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_paid_adapter_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cdp_connection_retries_until_one_browser_context_is_available():
    module = load()
    attempts = []
    stopped = []

    class Browser:
        contexts = [object()]

    class Chromium:
        def connect_over_cdp(self, _url, timeout):
            attempts.append(timeout)
            if len(attempts) < 3:
                raise RuntimeError("transient cdp failure")
            return Browser()

    class Runtime:
        chromium = Chromium()
        def stop(self): stopped.append(True)

    class Launcher:
        def start(self): return Runtime()

    module.sync_playwright = lambda: Launcher()
    module.time.sleep = lambda _seconds: None

    runtime, browser = module._connect_existing_cdp()

    assert len(attempts) == 3
    assert browser.contexts == [browser.contexts[0]]
    assert stopped == [True, True]
    runtime.stop()


def funded():
    return {"work_id": "63570481", "title": "Webデザイン業務", "client": "buyer",
            "provider_state": "funded", "milestone_id": "13798056",
            "form_url": "https://forms.gle/abc123", "application_date": "2026-09-09"}


def escrow():
    return {"work_id": "63568785", "title": "教材フィードバック", "client": "buyer2",
            "provider_state": "awaiting_escrow", "milestone_id": None, "form_url": None,
            "application_date": "2026-09-10"}


def delivered():
    return {"work_id": "63570481", "title": "Webデザイン業務", "client": "buyer",
            "provider_state": "delivered", "milestone_id": None, "form_url": None,
            "application_date": "2026-09-09"}


def load_kernel():
    path = ROOT / "skills/_shared/marketplace-core/scripts/paid_kernel.py"
    spec = importlib.util.spec_from_file_location("paid_kernel_crowdworks_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_two_official_active_contracts_normalize_to_unique_stable_observations():
    module = load()
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", inventory_reader=lambda: {"ok": True, "source_complete": True,
            "contract_candidates": [funded(), escrow()]})
    rows = adapter.observe_active()
    assert [(row["work_id"], row["provider_state"]) for row in rows] == [
        ("63570481", "funded"), ("63568785", "awaiting_escrow")]
    first = {key: value for key, value in rows[0].items() if key != "observed_at"}
    assert first == {key: value for key, value in adapter._observation(funded()).items()
                     if key != "observed_at"}
    assert len({row["latest_event_id"] for row in rows}) == 2


def test_detail_expands_folded_buyer_messages_before_readback():
    module = load()
    events = []

    class Folding:
        def count(self): return 1
        def nth(self, index): return self
        def is_visible(self): return True
        def click(self): events.append("click")

    class Page:
        def get_by_text(self, pattern, exact):
            assert exact is False
            assert "メッセージを表示" in pattern.pattern
            return Folding()

        def wait_for_timeout(self, value): events.append(("wait", value))

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._expand_folded_messages()
    assert events == ["click", ("wait", 300)]


def test_latest_buyer_event_reads_message_api_identity_without_storing_body():
    module = load()

    class Root:
        def get_attribute(self, name):
            assert name == "data"
            return json.dumps({"id": 304340335, "messageableId": 63570481})

    class Page:
        def locator(self, selector):
            assert selector == "#pack-message-thread"
            return Root()

        def evaluate(self, _script, thread_id):
            assert thread_id == 304340335
            return {"status": 200, "body": json.dumps({"messages": [
                {"id": 426426361, "own_message": False,
                 "senddate": "2026年09月10日 11:22", "body": "buyer"},
                {"id": 427573234, "own_message": False,
                 "senddate": "2026年09月16日 11:43", "body": "correction"},
            ]})}

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()

    assert adapter._latest_buyer_event() == {
        "message_thread_id": "304340335",
        "buyer_event_id": "427573234",
        "buyer_event_at": "2026-09-16T11:43:00+09:00",
    }


def test_funded_contract_decides_one_form_then_one_milestone_submission():
    module = load()
    action = module.decide({"context": {"contract": funded()}})
    assert action["action"] == "submit"
    assert action["payload"] == {"form_url": "https://forms.gle/abc123",
                                  "form_sha256": hashlib.sha256(b"https://forms.gle/abc123").hexdigest(),
                                  "milestone_id": "13798056"}


def test_funded_contract_without_labeled_official_application_date_waits_truthfully():
    module = load()
    action = module.decide({"context": {"contract": {key: value for key, value in funded().items()
                                                         if key != "application_date"}}})
    assert action["action"] == "wait"
    assert action["reason"] == "official_application_date_required"


def test_funded_contract_without_google_form_waits_without_blocking_inventory():
    module = load()
    contract = {**funded(), "work_id": "63568785", "form_url": None}
    contract["buyer_event_id"] = "427573234"
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", inventory_reader=lambda: {
            "ok": True, "source_complete": True, "contract_candidates": [contract, funded()],
        },
    )

    rows = adapter.observe_active()
    action = module.decide({"context": {"contract": contract}})

    assert [row["work_id"] for row in rows] == ["63568785", "63570481"]
    assert action["action"] == "wait"
    assert action["reason"] == "buyer_task_detail_required"


def test_multi_form_contract_uses_model_selected_url():
    module = load()
    urls = ["https://forms.gle/video", "https://forms.gle/ads", "https://forms.gle/common"]
    contract = {**funded(), "form_url": None, "form_urls": urls}

    action = module.decide(
        {"context": {"contract": contract}},
        form_selector=lambda item: item["form_urls"][1],
    )

    assert action["action"] == "submit"
    assert action["payload"]["form_url"] == urls[1]
    assert action["payload"]["milestone_id"] == contract["milestone_id"]


def test_multi_form_contract_waits_when_model_cannot_choose():
    module = load()
    contract = {**funded(), "form_url": None,
                "form_urls": ["https://forms.gle/video", "https://forms.gle/ads"]}

    action = module.decide({"context": {"contract": contract}})

    assert action == {
        "action": "wait",
        "reason": "form_selection_required",
        "remaining_work": ["model must select one official form from the buyer context"],
    }


def test_all_selected_forms_advance_to_separate_formal_delivery():
    module = load()
    url = "https://forms.gle/ads"
    contract = {**funded(), "form_url": None, "form_urls": [url],
                "completed_form_urls": [url]}

    action = module.decide({"context": {"contract": contract}},
                           form_selector=lambda _item: module.FORM_SELECTION_COMPLETE)

    assert action == {
        "action": "formal_delivery",
        "payload": {
            "milestone_id": contract["milestone_id"],
            "message": "Googleフォームへの回答を完了しました。ご確認のほどよろしくお願いいたします。",
            "completed_form_urls": [url],
            "ignored_form_urls": [],
        },
    }


def test_formal_delivery_requires_at_least_one_form_receipt():
    module = load()
    urls = ["https://forms.gle/ads", "https://forms.gle/common"]
    contract = {**funded(), "form_url": None, "form_urls": urls,
                "completed_form_urls": [], "ignored_form_urls": urls}

    action = module.decide({"context": {"contract": contract}},
                           form_selector=lambda _item: module.FORM_SELECTION_COMPLETE)

    assert action["action"] == "wait"
    assert action["reason"] == "form_selection_required"


def test_form_selector_uses_candidate_context_and_exact_allowed_url(tmp_path, monkeypatch):
    module = load()
    urls = ["https://forms.gle/video", "https://forms.gle/ads"]
    seen = []
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding",
                        lambda **_kwargs: {"candidate": {"display_name": "Kaito"}})
    monkeypatch.setattr(module.composer, "compose", lambda context, **_kwargs: seen.append(context) or urls[1])
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", state_path=tmp_path,
        candidate_profile=tmp_path / "candidate.json",
        provider_profile={"display_name": "Kaito"},
    )

    chosen = adapter._select_form_url({
        **funded(),
        "form_url": None,
        "form_urls": urls,
        "form_candidates": [
            {"url": urls[0], "title": "動画作品提出", "body": "動画作品URLを提出"},
            {"url": urls[1], "title": "Web広告実績", "body": "広告運用実績と指標を提出"},
        ],
    })

    assert chosen == urls[1]
    assert seen[0]["action_contract"]["allowed_choices"] == [*urls, module.FORM_SELECTION_COMPLETE]
    assert "Web広告実績" in seen[0]["conversation"][0]["body"]


def test_completed_form_can_be_selected_as_a_buyer_correction_revision(tmp_path, monkeypatch):
    module = load()
    url = "https://forms.gle/correction"
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding",
                        lambda **_kwargs: {"candidate": {}})
    monkeypatch.setattr(module.composer, "compose", lambda *_args, **_kwargs: url)
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", state_path=tmp_path,
        candidate_profile=tmp_path / "candidate.json",
        provider_profile={"display_name": "Kaito"},
    )
    item = {**funded(), "form_url": None, "form_urls": [url],
            "completed_form_urls": [url],
            "form_candidates": [{"url": url, "title": "顧客宛メール", "body": "顧客宛回答"}],
            "buyer_context": "買い手が顧客宛回答の欠落を指摘した",
            "buyer_event_id": "427573234", "buyer_event_at": "2026-09-16T11:43:00+09:00"}
    adapter._correction_ready = lambda *_args: True
    assert adapter._select_form_url(item) == url
    assert item["form_revision"] is True


def test_decide_emits_new_event_binding_for_form_correction():
    module = load()
    url = "https://forms.gle/correction"
    contract = {**funded(), "form_url": None, "form_urls": [url],
                "completed_form_urls": [url], "form_revision": True,
                "buyer_event_id": "427573234"}
    action = module.decide(
        {"latest_event_id": "contract-digest", "context": {"contract": contract}},
        form_selector=lambda _item: url,
    )
    assert action["action"] == "submit"
    assert action["payload"]["revision_event_id"] == "427573234"


def test_form_binding_preserves_revision_event_as_a_new_receipt_namespace(tmp_path):
    module = load()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    binding = adapter._form_binding({**funded(), "form_revision_event_id": "buyer-event-2"}, "a" * 64)
    assert binding["revision_event_id"] == "buyer-event-2"


def test_form_correction_readback_uses_revision_event_binding(tmp_path, monkeypatch):
    module = load()
    url = "https://forms.gle/correction"
    bindings = []
    form_sha = hashlib.sha256(url.encode()).hexdigest()
    monkeypatch.setattr(module.google_form, "bound_receipt",
                        lambda _root, binding: bindings.append(binding) or {
                            "url_sha256": form_sha, "confirmation_sha256": "confirmed",
                        })
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    adapter._goto_contract = lambda _work_id: None

    result = adapter.readback({"action": "submit", "work_id": "63570481", "effect_key": "revision",
                               "payload": {"form_url": url, "form_sha256": form_sha,
                                           "milestone_id": "13798056",
                                           "revision_event_id": "buyer-event-2"}})

    assert result["verified"] is True
    assert bindings[0]["revision_event_id"] == "buyer-event-2"


def test_completed_form_without_new_buyer_event_cannot_be_selected(tmp_path, monkeypatch):
    module = load()
    url = "https://forms.gle/correction"
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding",
                        lambda **_kwargs: {"candidate": {}})
    monkeypatch.setattr(module.composer, "compose", lambda *_args, **_kwargs: url)
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", state_path=tmp_path,
        candidate_profile=tmp_path / "candidate.json",
        provider_profile={"display_name": "Kaito"},
    )
    item = {**funded(), "form_url": None, "form_urls": [url],
            "completed_form_urls": [url],
            "form_candidates": [{"url": url, "title": "顧客宛メール", "body": "顧客宛回答"}],
            "buyer_context": "買い手の依頼"}

    assert adapter._select_form_url(item) == module.FORM_SELECTION_COMPLETE
    assert "form_revision" not in item


def test_context_reopens_browser_before_fetching_cached_form_candidates():
    module = load()
    urls = ["https://forms.gle/video", "https://forms.gle/ads"]
    item = {**funded(), "form_url": None, "form_urls": urls}
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._cache_replace([item])
    calls = []
    adapter._open = lambda: calls.append("open")
    adapter._form_candidates = lambda values: [
        {"url": values[0], "title": "video", "body": "video"},
        {"url": values[1], "title": "ads", "body": "ads"},
    ]
    adapter.close = lambda: None

    context = adapter.context(item["work_id"])

    assert calls == ["open"]
    assert [candidate["title"] for candidate in context["contract"]["form_candidates"]] == ["video", "ads"]


def test_context_fetches_single_completed_form_candidate_for_correction():
    module = load()
    url = "https://forms.gle/correction"
    item = {**funded(), "form_url": None, "form_urls": [url],
            "completed_form_urls": [url]}
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._contract_cache = {item["work_id"]: dict(item)}
    calls = []
    adapter._open = lambda: calls.append("open")
    adapter._form_candidates = lambda values: [
        {"url": values[0], "title": "顧客宛メール", "body": "顧客宛回答"},
    ]
    adapter.close = lambda: None

    context = adapter.context(item["work_id"])

    assert calls == ["open"]
    assert context["contract"]["form_candidates"][0]["title"] == "顧客宛メール"


def test_answer_prompt_requires_permission_request_when_buyer_context_is_inaccessible(tmp_path, monkeypatch):
    module = load()
    seen = []
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding",
                        lambda **_kwargs: {"candidate": {}})
    monkeypatch.setattr(module.composer, "compose",
                        lambda context, **_kwargs: seen.append(context) or "権限を付与してください。")
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", state_path=tmp_path,
        candidate_profile=tmp_path / "candidate.json",
        provider_profile={"display_name": "Kaito"},
    )

    answer = adapter._compose_answer({**funded(), "form_url": None,
                                      "buyer_context": "編集権限をリクエスト と表示されています"})

    assert answer == "権限を付与してください。"
    assert "作業完了を主張せず" in seen[0]["action_contract"]["question"]


def test_submit_effect_does_not_formal_deliver_in_same_mutation():
    module = load()
    events = []
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._targeted_detail = lambda _work_id: funded()
    adapter._submit_form_once = lambda item: events.append(("form", item["work_id"]))
    adapter._complete_once = lambda *_args: (_ for _ in ()).throw(AssertionError("delivery combined"))

    adapter.mutate({"action": "submit", "work_id": "63570481",
                    "payload": {"form_url": funded()["form_url"],
                                "form_sha256": hashlib.sha256(funded()["form_url"].encode()).hexdigest(),
                                "milestone_id": funded()["milestone_id"]}})

    assert events == [("form", "63570481")]


def test_form_correction_revision_can_resubmit_completed_form_with_new_event():
    module = load()
    url = funded()["form_url"]
    events = []
    current = {**funded(), "form_url": None, "form_urls": [url],
               "completed_form_urls": [url], "buyer_event_id": "buyer-correction-2"}
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._targeted_detail = lambda _work_id: current
    adapter._submit_form_once = lambda item: events.append(item["form_revision_event_id"])

    adapter.mutate({"action": "submit", "work_id": current["work_id"],
                    "payload": {"form_url": url,
                                "form_sha256": hashlib.sha256(url.encode()).hexdigest(),
                                "milestone_id": current["milestone_id"],
                                "revision_event_id": "buyer-correction-2"}})

    assert events == ["buyer-correction-2"]


def test_form_correction_mutation_rejects_stale_buyer_event():
    module = load()
    url = funded()["form_url"]
    current = {**funded(), "form_url": None, "form_urls": [url],
               "completed_form_urls": [url], "buyer_event_id": "new-event"}
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._targeted_detail = lambda _work_id: current
    adapter._submit_form_once = lambda _item: (_ for _ in ()).throw(
        AssertionError("stale correction must not submit"))

    with pytest.raises(RuntimeError, match="crowdworks_paid_context_changed"):
        adapter.mutate({"action": "submit", "work_id": current["work_id"],
                        "payload": {"form_url": url,
                                    "form_sha256": hashlib.sha256(url.encode()).hexdigest(),
                                    "milestone_id": current["milestone_id"],
                                    "revision_event_id": "old-event"}})


def test_formal_delivery_is_a_separate_mutation():
    module = load()
    events = []
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._targeted_detail = lambda _work_id: {
        **funded(), "form_url": None, "form_urls": ["https://forms.gle/ads"],
        "completed_form_urls": ["https://forms.gle/ads"],
    }
    adapter._complete_once = lambda item, payload: events.append((item["work_id"], payload["milestone_id"]))

    adapter.mutate({"action": "formal_delivery", "work_id": "63570481",
                    "payload": {"milestone_id": funded()["milestone_id"], "message": "done",
                                "completed_form_urls": ["https://forms.gle/ads"],
                                "ignored_form_urls": []}})

    assert events == [("63570481", "13798056")]


def test_formal_delivery_rejects_missing_form_progress():
    module = load()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._targeted_detail = lambda _work_id: funded()
    adapter._complete_once = lambda *_args: (_ for _ in ()).throw(AssertionError("delivery must be fenced"))

    with pytest.raises(RuntimeError, match="crowdworks_paid_form_progress_changed"):
        adapter.mutate({"action": "formal_delivery", "work_id": "63570481",
                        "payload": {"milestone_id": "13798056", "message": "done",
                                    "completed_form_urls": ["https://forms.gle/ads"],
                                    "ignored_form_urls": []}})


def test_no_form_contract_does_not_require_application_date():
    module = load()
    contract = {key: value for key, value in funded().items()
                if key not in {"form_url", "application_date"}}
    contract["buyer_event_id"] = "427573234"
    action = module.decide({"context": {"contract": contract}})

    assert action["action"] == "wait"
    assert action["reason"] == "buyer_task_detail_required"


def test_answer_mutation_posts_one_contract_message():
    module = load()
    events = []

    class Area:
        def is_visible(self): return True
        def fill(self, value): events.append(("fill", value))

    class Areas:
        def count(self): return 1
        def nth(self, index): return Area()

    class Button:
        def count(self): return 1
        def is_visible(self): return True
        def is_enabled(self): return True
        def click(self): events.append(("click", "message"))

    class Page:
        def locator(self, selector):
            assert selector == 'textarea[name="message[body]"]'
            return Areas()

        def get_by_role(self, role, name, exact):
            assert (role, name, exact) == ("button", "メッセージを投稿する", True)
            return Button()

        def wait_for_timeout(self, timeout): events.append(("wait", timeout))

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda work_id: events.append(("contract", work_id))
    adapter._targeted_detail = lambda work_id: funded()

    adapter.mutate({"action": "answer", "work_id": "63570481",
                    "payload": {"body": "顧客向け回答を再提出します。"}})

    assert events == [
        ("contract", "63570481"),
        ("fill", "顧客向け回答を再提出します。"),
        ("click", "message"),
        ("wait", 2000),
    ]


def test_answer_readback_requires_seller_visible_body():
    module = load()

    class Body:
        def inner_text(self): return "buyer text\n顧客向け回答を再提出します。"

    class Page:
        def locator(self, selector):
            assert selector == "body"
            return Body()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda work_id: None
    result = adapter.readback({"action": "answer", "work_id": "63570481",
                               "effect_key": "answer-key",
                               "payload": {"body": "顧客向け回答を再提出します。"}})

    assert result["verified"] is True
    assert result["provider_receipt_id"] == "contract:63570481:answer:answer-key"


def test_answer_readback_requires_a_new_seller_message_after_buyer_event():
    module = load()
    expected = "顧客向け回答を再提出します。"

    class Body:
        def inner_text(self): return "old buyer\n" + expected

    class Root:
        def get_attribute(self, name):
            assert name == "data"
            return json.dumps({"id": 304340335, "messageableId": 63570481})

    class Page:
        def locator(self, selector):
            if selector == "body": return Body()
            if selector == "#pack-message-thread": return Root()
            raise AssertionError(selector)

        def evaluate(self, _script, thread_id):
            assert thread_id == 304340335
            return {"status": 200, "body": json.dumps({"messages": [
                {"id": 427573234, "own_message": False,
                 "senddate": "2026年09月16日 11:43", "body": "buyer"},
                {"id": 427573200, "own_message": True,
                 "senddate": "2026年09月16日 11:44", "body": expected},
            ]})}

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda _work_id: None
    result = adapter.readback({"action": "answer", "work_id": "63570481",
                               "effect_key": "answer-key",
                               "payload": {"body": expected, "buyer_event_id": "427573234"}})

    assert result["authoritative_absent"] is True


def test_answer_readback_accepts_new_seller_message_bound_to_buyer_event():
    module = load()
    expected = "権限付与後に確認します。"

    class Body:
        def inner_text(self): return expected

    class Root:
        def get_attribute(self, name):
            assert name == "data"
            return json.dumps({"id": 304340335, "messageableId": 63568785})

    class Page:
        def locator(self, selector):
            if selector == "body": return Body()
            if selector == "#pack-message-thread": return Root()
            raise AssertionError(selector)

        def evaluate(self, _script, thread_id):
            assert thread_id == 304340335
            return {"status": 200, "body": json.dumps({"messages": [
                {"id": 427573234, "own_message": False,
                 "senddate": "2026年09月16日 11:43", "body": "buyer"},
                {"id": 427573240, "own_message": True,
                 "senddate": "2026年09月16日 11:44", "body": expected},
            ]})}

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda _work_id: None
    result = adapter.readback({"action": "answer", "work_id": "63568785",
                               "effect_key": "answer-key",
                               "payload": {"body": expected, "buyer_event_id": "427573234"}})

    assert result["verified"] is True


def test_document_access_reports_permission_required_without_verifying_artifact():
    module = load()

    class Body:
        def inner_text(self): return "編集権限をリクエスト"

    class Page:
        def goto(self, *_args, **_kwargs): return None
        def locator(self, selector):
            assert selector == "body"
            return Body()
        def close(self): return None

    class Context:
        def new_page(self): return Page()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.owned_context = Context()
    assert adapter._document_access(["https://docs.google.com/document/d/abc/edit"]) == {
        "artifact_required": True, "artifact_access": "permission_required",
        "artifact_verified": False,
    }


def test_cached_inventory_detail_is_reused_until_explicit_refresh():
    module = load()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    calls = []
    row = funded()
    adapter._list_contracts = lambda: [row]
    adapter._detail = lambda value: calls.append(value["work_id"]) or dict(value)

    adapter._inventory()
    adapter.observe_one(row["work_id"])
    adapter.refresh_one(row["work_id"])

    assert calls == [row["work_id"], row["work_id"]]


def test_detail_retains_multiple_buyer_form_links_for_later_task_selection():
    module = load()
    title, client = "buyer task", "buyer"
    links = [
        "https://docs.google.com/forms/d/e/one/viewform",
        "https://docs.google.com/forms/d/e/two/viewform",
    ]

    class Form:
        def get_attribute(self, name):
            assert name == "action"
            return "/milestones/13798056/complete"

    class Forms:
        def count(self):
            return 2

        def nth(self, index):
            return Form()

    class Locator:
        def __init__(self, selector):
            self.selector = selector

        def inner_text(self):
            return f"{title} {client} 業務を開始しています 検収"

        def evaluate_all(self, expression):
            assert "href" in expression
            return links

    class Page:
        def locator(self, selector):
            if selector.startswith('form[action^="/milestones/"]'):
                return Forms()
            return Locator(selector)

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda work_id: None
    adapter._proposal_application_date = lambda proposal_id: None

    detail = adapter._detail_once({"work_id": "63570481", "title": title, "client": client})

    assert detail["form_urls"] == links
    assert detail["form_url"] is None


def test_inventory_row_clears_singular_form_when_multiple_urls_are_present():
    module = load()
    row = {**funded(), "form_urls": [
        "https://forms.gle/one", "https://forms.gle/two",
    ]}

    normalized = module.CrowdWorksPaidAdapter._row_from_list(row)

    assert normalized["form_urls"] == ["https://forms.gle/one", "https://forms.gle/two"]
    assert normalized["form_url"] is None


def test_exact_verified_apply_receipt_is_jst_application_date_fallback(tmp_path):
    module = load()
    receipt = {"record_type": "application_receipt", "platform": "crowdworks", "status": "verified",
               "opportunity_external_id": "13440101", "application_external_id": "305139864",
               "opportunity_title": funded()["title"], "observed_at": "2026-09-09T11:34:46.521685+00:00"}
    path = tmp_path / "application-receipts.jsonl"; path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", application_receipts_path=path)
    assert adapter._receipt_application_date(funded()["title"], "305139864") == "2026-09-09"


def test_proposal_timeout_falls_through_to_verified_receipt_lookup():
    module = load()
    closed = []

    class Proposal:
        def close(self):
            closed.append(True)

    class Context:
        def new_page(self):
            return Proposal()

    class Browser:
        contexts = [Context()]

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.browser = Browser()
    adapter.owned_context = adapter.browser.contexts[0]
    adapter._goto = lambda *args: (_ for _ in ()).throw(module.CrowdWorksPaidProposalTimeout())

    assert adapter._proposal_application_date("305139864") is None
    assert closed == [True]


def test_ambiguous_or_nonexact_apply_receipt_never_supplies_date(tmp_path):
    module = load()
    valid = {"record_type": "application_receipt", "platform": "crowdworks", "status": "verified",
             "opportunity_external_id": "13440101", "application_external_id": "305139864",
             "opportunity_title": funded()["title"], "observed_at": "2026-09-09T11:34:46+00:00"}
    path = tmp_path / "application-receipts.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in (valid, {**valid, "observed_at": "2026-09-10T00:00:00+00:00"})) + "\n", encoding="utf-8")
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", application_receipts_path=path)
    assert adapter._receipt_application_date(funded()["title"], "305139864") is None
    assert adapter._receipt_application_date("other title", "305139864") is None


def test_apply_receipt_date_converts_to_asia_tokyo_before_form_use(tmp_path):
    module = load()
    row = {"record_type": "application_receipt", "platform": "crowdworks", "status": "verified",
           "opportunity_external_id": "13440101", "application_external_id": "305139864",
           "opportunity_title": funded()["title"], "observed_at": "2026-09-09T16:00:00+00:00"}
    path = tmp_path / "application-receipts.jsonl"; path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert module.CrowdWorksPaidAdapter(account_id="7145638", application_receipts_path=path)._receipt_application_date(
        funded()["title"], "305139864") == "2026-09-10"


def test_adapter_opens_injected_thread_owned_cdp_connection_not_account_browser():
    module = load()
    calls = []

    class Page:
        def set_default_timeout(self, timeout):
            calls.append(("timeout", timeout))

        def close(self):
            calls.append(("page_close",))

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        contexts = [Context()]

    class Runtime:
        def stop(self):
            calls.append(("runtime_stop",))

    original = module.account._browser
    module.account._browser = lambda *_: (_ for _ in ()).throw(AssertionError("global browser forbidden"))
    try:
        adapter = module.CrowdWorksPaidAdapter(account_id="7145638",
            connection_factory=lambda: (Runtime(), Browser()),
            context_factory=lambda _browser, source: source)
        adapter._open()
        adapter.close()
    finally:
        module.account._browser = original
    assert calls == [("timeout", 15_000), ("page_close",), ("runtime_stop",)]


def test_default_open_clones_auth_into_owned_context_and_closes_it():
    module = load()
    calls = []
    auth_state = {"cookies": [{"name": "session", "value": "private"}], "origins": []}

    class Page:
        def set_default_timeout(self, timeout): calls.append(("timeout", timeout))
        def close(self): calls.append(("page_close",))

    class SourceContext:
        def storage_state(self): return auth_state
        def new_page(self): raise AssertionError("persistent_context_page_forbidden")

    class OwnedContext:
        def new_page(self): return Page()
        def close(self): calls.append(("context_close",))

    class Browser:
        contexts = [SourceContext()]
        def new_context(self, **kwargs):
            calls.append(("new_context", kwargs["storage_state"] is not auth_state, kwargs["storage_state"] == auth_state))
            return OwnedContext()

    class Runtime:
        def stop(self): calls.append(("runtime_stop",))

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()))
    adapter._open()
    adapter.close()

    assert calls == [
        ("new_context", True, True), ("timeout", 15_000), ("page_close",),
        ("context_close",), ("runtime_stop",),
    ]


def test_open_falls_back_to_source_context_when_clone_creation_fails():
    module = load()
    calls = []

    class Page:
        def set_default_timeout(self, timeout): calls.append(("timeout", timeout))
        def close(self): calls.append(("page_close",))

    class SourceContext:
        def storage_state(self): return {"cookies": [], "origins": []}
        def new_page(self): calls.append(("source_page",)); return Page()

    source = SourceContext()

    class Browser:
        contexts = [source]
        def new_context(self, **_kwargs): raise RuntimeError("clone unavailable")

    class Runtime:
        def stop(self): calls.append(("runtime_stop",))

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()))
    adapter._open()

    assert adapter.owned_context is source
    assert adapter.owns_context is False
    assert ("source_page",) in calls
    adapter.close()


def test_active_inventory_falls_back_to_locked_persistent_context_after_clone_timeout():
    module = load()
    calls = []

    class Page:
        def set_default_timeout(self, timeout): calls.append(("timeout", timeout))
        def close(self): calls.append(("page_close",))

    class SourceContext:
        def storage_state(self): return {"cookies": [], "origins": []}
        def new_page(self): calls.append(("source_page",)); return Page()

    class OwnedContext:
        def new_page(self): calls.append(("owned_page",)); return Page()
        def close(self): calls.append(("context_close",))

    class Browser:
        contexts = [SourceContext()]
        def new_context(self, **_kwargs): return OwnedContext()

    class Runtime:
        def stop(self): calls.append(("runtime_stop",))

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()))
    adapter._open()
    attempts = [0]

    def list_once():
        attempts[0] += 1
        if attempts[0] == 1:
            raise module.PlaywrightTimeoutError("clone timeout")
        return [{"work_id": "63583795"}]

    adapter._list_contracts_once = list_once
    assert adapter._list_contracts() == [{"work_id": "63583795"}]
    assert attempts == [2]
    assert ("source_page",) in calls
    adapter.close()


def test_three_workers_never_open_a_page_in_the_persistent_context():
    module = load()
    lock, created, seen = threading.Lock(), [], []
    barrier = threading.Barrier(3)

    class Page:
        def set_default_timeout(self, _timeout): pass
        def close(self): pass

    class SourceContext:
        def storage_state(self): return {"cookies": [], "origins": []}
        def new_page(self): raise AssertionError("persistent_context_page_forbidden")

    class OwnedContext:
        def __init__(self, identity): self.identity = identity
        def new_page(self): return Page()
        def close(self): pass

    class Browser:
        contexts = [SourceContext()]
        def new_context(self, **_kwargs):
            with lock:
                context = OwnedContext(len(created) + 1)
                created.append(context)
                return context

    class Runtime:
        chromium = None
        def stop(self): pass

    browser = Browser()
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), browser))

    def worker():
        adapter._open()
        barrier.wait(timeout=3)
        seen.append(adapter.owned_context.identity)
        adapter.close()

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(seen) == [1, 2, 3]
    assert len({id(context) for context in created}) == 3


def test_connect_existing_cdp_retries_once_with_bounded_timeout(monkeypatch):
    module = load()
    calls = []

    class Chromium:
        def __init__(self, result):
            self.result = result

        def connect_over_cdp(self, url, *, timeout):
            calls.append(("connect", url, timeout))
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    class Runtime:
        def __init__(self, result):
            self.chromium = Chromium(result)

        def stop(self):
            calls.append(("stop",))

    runtimes = iter((Runtime(TimeoutError()), Runtime(TimeoutError()),
                     Runtime(TimeoutError()), Runtime("browser")))
    monkeypatch.setattr(module, "sync_playwright", lambda: type(
        "Starter", (), {"start": lambda self: next(runtimes)})())
    monkeypatch.setattr(module.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))

    runtime, browser = module._connect_existing_cdp()

    assert browser == "browser"
    assert runtime.chromium.result == "browser"
    assert calls == [
        ("connect", module.account.CDP_URL, 10_000), ("stop",), ("sleep", 0.5),
        ("connect", module.account.CDP_URL, 10_000), ("stop",), ("sleep", 0.5),
        ("connect", module.account.CDP_URL, 10_000), ("stop",), ("sleep", 0.5),
        ("connect", module.account.CDP_URL, 10_000),
    ]


def test_connect_existing_cdp_stops_both_failed_runtimes(monkeypatch):
    module = load()
    stopped = []

    class Runtime:
        class Chromium:
            def connect_over_cdp(self, url, *, timeout):
                raise TimeoutError

        chromium = Chromium()

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(module, "sync_playwright", lambda: type(
        "Starter", (), {"start": lambda self: Runtime()})())
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="^crowdworks_paid_browser_unavailable$"):
        module._connect_existing_cdp()
    assert stopped == [True, True, True, True]


def test_active_contract_timeout_has_bounded_stage_specific_name():
    module = load()

    class Page:
        def set_default_timeout(self, timeout):
            pass

        def goto(self, *args, **kwargs):
            raise module.PlaywrightTimeoutError("untrusted provider text is never diagnostic state")

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        contexts = [Context()]

    class Runtime:
        def stop(self):
            pass

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638",
        connection_factory=lambda: (Runtime(), Browser()),
        context_factory=lambda _browser, source: source)
    with pytest.raises(module.CrowdWorksPaidActiveContractsTimeout) as error:
        adapter._list_contracts()
    assert str(error.value) == ""
    assert error.value.paid_error_code == "crowdworks_paid_active_contracts_timeout"
    adapter.close()


def test_provider_navigation_starts_after_commit_and_uses_locator_timeout():
    module = load()
    observed = []

    class Page:
        def goto(self, url, *, wait_until, timeout):
            observed.append((url, wait_until, timeout))

    module.CrowdWorksPaidAdapter._goto(Page(), module.ACTIVE_CONTRACTS_URL, "active_contracts")

    assert observed == [(module.ACTIVE_CONTRACTS_URL, "commit", 20_000)]


def test_active_contract_dom_timeout_has_same_safe_stage_code():
    module = load()

    class Locator:
        def evaluate_all(self, *_):
            raise module.PlaywrightTimeoutError("untrusted provider text")

    class Page:
        url = module.ACTIVE_CONTRACTS_URL

        def set_default_timeout(self, timeout):
            pass

        def goto(self, *args, **kwargs):
            pass

        def locator(self, *_):
            return Locator()

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        contexts = [Context()]

    class Runtime:
        def stop(self):
            pass

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()),
        context_factory=lambda _browser, source: source)
    with pytest.raises(module.CrowdWorksPaidActiveContractsTimeout) as error:
        adapter._list_contracts()
    assert error.value.paid_error_code == "crowdworks_paid_active_contracts_timeout"
    adapter.close()


def test_empty_active_contract_inventory_fails_closed_instead_of_reporting_zero():
    module = load()

    class Locator:
        def evaluate_all(self, *_): return []

    class Page:
        url = module.ACTIVE_CONTRACTS_URL
        def set_default_timeout(self, _timeout): pass
        def goto(self, *_args, **_kwargs): pass
        def locator(self, _selector): return Locator()

    class Context:
        def new_page(self): return Page()

    class Browser:
        contexts = [Context()]

    class Runtime:
        def stop(self): pass

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()),
        context_factory=lambda _browser, source: source)
    with pytest.raises(RuntimeError, match="crowdworks_paid_contract_source_unavailable"):
        adapter._list_contracts_once()
    adapter.close()


def test_contract_detail_dom_timeout_has_safe_contract_stage_code():
    module = load()

    class Locator:
        def inner_text(self):
            raise module.PlaywrightTimeoutError("untrusted provider text")

    class Page:
        def locator(self, *_):
            return Locator()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda *_: None
    with pytest.raises(module.CrowdWorksPaidContractTimeout) as error:
        adapter._detail(funded())
    assert error.value.paid_error_code == "crowdworks_paid_contract_timeout"


def test_inspection_pending_contract_is_read_as_delivered_without_resubmission():
    module = load()
    title, client = "急募のCS業務", "ミラフル採用"

    class Body:
        def inner_text(self):
            return (f"{title} {client} 業務を開始しています。"
                    "クライアント（発注者）が検収を行っています。"
                    "検収完了までしばらくお待ちください。")

    class Page:
        def locator(self, selector):
            assert selector == "body"
            return Body()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter._goto_contract = lambda work_id: None

    detail = adapter._detail_once({"work_id": "63583795", "title": title, "client": client})

    assert detail["provider_state"] == "delivered"
    assert detail["milestone_id"] is None
    assert detail["form_url"] is None
    assert module.decide({"context": {"contract": detail}}) == {
        "action": "noop", "classification": "completed",
    }


def test_contract_detail_dom_timeout_retries_once_on_fresh_page():
    module = load()
    calls = []

    class Page:
        def set_default_timeout(self, timeout):
            calls.append(("timeout", timeout))

        def close(self):
            calls.append(("close",))

    fresh = Page()

    class Context:
        def new_page(self):
            calls.append(("new_page",))
            return fresh

    class Browser:
        contexts = [Context()]

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.browser = Browser()
    adapter.owned_context = adapter.browser.contexts[0]
    adapter.page = Page()
    attempts = iter((module.PlaywrightTimeoutError("provider text"), funded()))
    adapter._detail_once = lambda *_: (
        (_ for _ in ()).throw(value) if isinstance((value := next(attempts)), Exception) else value
    )

    assert adapter._detail(funded()) == funded()
    assert calls == [("close",), ("new_page",), ("timeout", 15_000)]


def test_contract_detail_timeout_falls_back_to_narrow_surface():
    module = load()
    calls = []

    class Page:
        def set_default_timeout(self, _timeout): pass
        def close(self): calls.append("close")

    class Context:
        def new_page(self): return Page()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()
    adapter.owned_context = Context()
    adapter._fallback_to_source_context = lambda: False
    attempts = [0]

    def detail_once(_basic):
        attempts[0] += 1
        if attempts[0] < 3:
            raise module.PlaywrightTimeoutError("detail timeout")
        return {"work_id": "63570481", "provider_state": "funded"}

    adapter._detail_once = detail_once
    adapter._switch_to_narrow_contract = lambda work_id: calls.append(("narrow", work_id))

    assert adapter._detail(funded()) == {"work_id": "63570481", "provider_state": "funded"}
    assert ("narrow", "63570481") in calls


def test_detail_timeout_keeps_basic_contract_and_does_not_block_other_rows():
    module = load()
    rows = [funded(), {**funded(), "work_id": "63568785", "title": "教材フィードバック"}]
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._list_contracts = lambda: rows

    def detail(row):
        if row["work_id"] == "63570481":
            raise module.CrowdWorksPaidContractTimeout()
        return {**row, "provider_state": "funded", "form_url": None, "milestone_id": None}

    adapter._detail = detail
    observed = adapter._inventory()

    assert [row["work_id"] for row in observed] == ["63570481", "63568785"]
    assert adapter._cached_item("63570481")["detail_unavailable"] is True
    assert adapter._cached_item("63568785").get("detail_unavailable") is not True


def test_detail_timeout_decision_waits_for_retryable_official_context():
    module = load()
    action = module.decide({"context": {"contract": {**funded(), "detail_unavailable": True}}})

    assert action == {
        "action": "wait",
        "reason": "contract_detail_timeout",
        "remaining_work": ["retry official CrowdWorks contract detail readback"],
    }


def test_contract_navigation_timeout_retries_once_on_fresh_page():
    module = load()
    calls = []

    class Page:
        url = "https://crowdworks.jp/contracts/63570481"

        def __init__(self, fails):
            self.fails = fails

        def set_default_timeout(self, timeout):
            calls.append(("timeout", timeout))

        def goto(self, url, **kwargs):
            calls.append(("goto", url))
            if self.fails:
                raise module.PlaywrightTimeoutError("provider text")

        def close(self):
            calls.append(("close", self.fails))

    pages = [Page(True), Page(False)]

    class Context:
        def new_page(self):
            return pages.pop(0)

    context = Context()

    class Browser:
        contexts = [context]

    class Runtime:
        def stop(self):
            pass

    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", connection_factory=lambda: (Runtime(), Browser()),
        context_factory=lambda _browser, source: source)
    adapter._goto_contract("63570481")
    assert [call[0] for call in calls] == ["timeout", "goto", "close", "timeout", "goto"]
    assert not pages
    adapter.close()


def test_observation_keeps_adapter_account_identity():
    module = load()
    adapter = module.CrowdWorksPaidAdapter(account_id="different-account")
    assert adapter._observation(funded())["account_id"] == "different-account"


def test_awaiting_escrow_never_authorizes_work_or_delivery():
    module = load()
    action = module.decide({"context": {"contract": escrow()}})
    assert action["action"] == "wait"
    assert action["reason"] == "awaiting_client_escrow"


def test_no_form_funded_contract_uses_full_buyer_context_for_answer(tmp_path, monkeypatch):
    module = load()
    captured = []
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding",
                        lambda **_kwargs: {"verified": ["seller fact"]})
    monkeypatch.setattr(module.composer, "compose",
                        lambda context, **_kwargs: captured.append(context) or
                        "編集権限を付与いただければ、内容を確認して対応します。")
    contract = {**funded(), "form_url": None, "form_urls": [],
                "buyer_context": "Google Docs assignment link and buyer request",
                "buyer_event_id": "427573234"}
    adapter = module.CrowdWorksPaidAdapter(
        account_id="7145638", state_path=tmp_path,
        candidate_profile=tmp_path / "candidate.json", provider_profile={"display_name": "Kaito"})
    action = module.decide({"context": {"contract": contract}},
                           answer_selector=adapter._compose_answer)
    assert action == {"action": "answer", "payload": {
        "body": "編集権限を付与いただければ、内容を確認して対応します。",
        "buyer_event_id": "427573234"}}
    assert captured and captured[0]["conversation"][0]["role"] == "buyer"
    assert "Google Docs assignment link" in captured[0]["conversation"][0]["body"]


def test_no_form_answer_waits_until_external_artifact_is_verified(tmp_path, monkeypatch):
    module = load()
    contract = {**funded(), "form_url": None, "form_urls": [],
                "buyer_context": "Google Docs assignment", "buyer_event_id": "buyer-1",
                "artifact_required": True, "artifact_verified": False}

    action = module.decide({"context": {"contract": contract}},
                           answer_selector=lambda _item: "完了しました。")

    assert action["action"] == "wait"
    assert action["reason"] == "buyer_task_detail_required"


def test_no_form_permission_request_can_be_answered_without_claiming_completion():
    module = load()
    contract = {**funded(), "form_url": None, "form_urls": [],
                "buyer_context": "Google Docs assignment", "buyer_event_id": "buyer-1",
                "artifact_required": True, "artifact_access": "permission_required",
                "artifact_verified": False}

    action = module.decide({"context": {"contract": contract}},
                           answer_selector=lambda _item: "権限を付与してください。")

    assert action == {"action": "answer", "payload": {
        "body": "権限を付与してください。", "buyer_event_id": "buyer-1"}}


def test_no_form_answer_requires_buyer_event_identity():
    module = load()
    contract = {**funded(), "form_url": None, "form_urls": [],
                "buyer_context": "依頼内容", "artifact_required": False}

    action = module.decide({"context": {"contract": contract}},
                           answer_selector=lambda _item: "回答")

    assert action["action"] == "wait"
    assert action["reason"] == "buyer_event_required"


def test_no_form_without_buyer_context_stays_waiting():
    module = load()
    contract = {**funded(), "form_url": None, "form_urls": [], "buyer_context": ""}
    action = module.decide({"context": {"contract": contract}},
                           answer_selector=lambda _item: "must not send")
    assert action["action"] == "wait"
    assert action["reason"] == "buyer_task_detail_required"


def test_delivered_contract_is_kernel_noop_and_replay_zero(tmp_path):
    module, kernel = load(), load_kernel()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", inventory_reader=lambda: {
        "ok": True, "source_complete": True, "contract_candidates": [delivered()]})
    result = kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path)
    replay = kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path)
    assert result["effect"] == replay["effect"] == 0
    assert result["items"][0]["status"] == replay["items"][0]["status"] == "completed"


def test_kernel_concurrency_keeps_paid_adapter_thread_state_isolated(tmp_path):
    module, kernel = load(), load_kernel()
    rows = [funded(), {**funded(), "work_id": "63570482", "milestone_id": "13798057"}]
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", inventory_reader=lambda: {
        "ok": True, "source_complete": True, "contract_candidates": rows})
    barrier, seen, mutated = threading.Barrier(2), [], set()

    def observe_one(work_id):
        item = next(row for row in rows if row["work_id"] == work_id)
        return adapter._observation(item)

    def context(work_id):
        return {"contract": next(row for row in rows if row["work_id"] == work_id)}

    def mutate(intent):
        barrier.wait(timeout=3)
        seen.append((threading.get_ident(), intent["work_id"]))
        mutated.add(intent["work_id"])

    adapter.observe_one, adapter.context, adapter.mutate = observe_one, context, mutate
    adapter.readback = lambda intent: ({"verified": True, "provider_receipt_id": intent["work_id"], "observed_at": "now"}
                                      if intent["work_id"] in mutated else {"authoritative_absent": True})
    result = kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path, max_workers=2)
    assert result["effect"] == 2 and result["failed"] == 0
    assert len({thread for thread, _ in seen}) == 2


def test_real_kernel_paths_close_every_thread_owned_runtime(tmp_path):
    module, kernel = load(), load_kernel()
    events = []

    class Page:
        url = ""

        def set_default_timeout(self, timeout):
            pass

        def goto(self, url, **kwargs):
            self.url = url

        def wait_for_load_state(self, *args, **kwargs):
            pass

        def locator(self, selector):
            return Locator(selector)

        def close(self):
            events.append("page")

    class Locator:
        def __init__(self, selector):
            self.selector = selector

        def evaluate_all(self, expression):
            # The funded contract's completion form remains visible, and no
            # receipt exists in this synthetic browser.  That is authoritative
            # absence for the kernel's pre/post-mutation reconciliation.
            return []

        def inner_text(self):
            return "業務を開始しています"

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        contexts = [Context()]

    class Runtime:
        def stop(self):
            events.append("runtime")

    def adapter_for(rows):
        adapter = module.CrowdWorksPaidAdapter(account_id="7145638",
            connection_factory=lambda: (Runtime(), Browser()),
            context_factory=lambda _browser, source: source,
            state_path=tmp_path / "receipts")
        adapter._list_contracts = lambda: rows
        adapter._detail = lambda row: (adapter._open(), dict(row))[1]
        return adapter

    # wait, completed/no-op, failed mutation, and submitted mutation all run
    # through paid_kernel; each public adapter call owns/tears down its runtime.
    waiting = adapter_for([escrow()])
    completed = adapter_for([delivered()])
    failing = adapter_for([funded()])
    failing._submit_form_once = lambda item: (_ for _ in ()).throw(RuntimeError("form_failed"))
    submitted = adapter_for([funded()])
    submitted._submit_form_once = lambda item: {"confirmation_sha256": "already-confirmed"}
    submitted._complete_once = lambda item, payload: None
    for index, adapter in enumerate((waiting, completed, failing, submitted)):
        kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path / str(index), max_workers=1)
    assert events.count("page") == events.count("runtime")
    # Every public adapter call owns and tears down its runtime; cached
    # observations intentionally avoid reopening the browser for wait/no-op rows.
    assert events.count("runtime") >= 11


def test_kernel_does_not_repeat_full_inventory_for_each_worker_call(tmp_path):
    module, kernel = load(), load_kernel()
    rows, list_calls, details = [escrow(), delivered()], [], []
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter._list_contracts = lambda: (list_calls.append("full"), rows)[1]
    adapter._detail = lambda row: (details.append(row["work_id"]), dict(row))[1]

    result = kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path, max_workers=2)

    assert result["failed"] == 0
    assert list_calls == ["full"]
    # Initial inventory details both contracts once. Wait/no-op rows consume the
    # cached facts and do not reopen a browser; mutation rows use refresh_one.
    assert details[:2] == ["63568785", "63570481"]
    assert details[2:] == []


def test_mutation_targeted_refresh_rejects_changed_contract_before_submit(tmp_path):
    module, kernel = load(), load_kernel()
    original = funded()
    changed = {**funded(), "milestone_id": "13798057", "form_url": "https://forms.gle/changed"}
    reads, sent = [], []

    def inventory():
        reads.append(1)
        current = original if len(reads) < 4 else changed
        return {"ok": True, "source_complete": True, "contract_candidates": [current]}

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", inventory_reader=inventory)
    adapter.readback = lambda intent: {"authoritative_absent": True}
    adapter._submit_form_once = lambda item: sent.append(item)
    result = kernel.run_wake(adapter=adapter, decide=module.decide, state_root=tmp_path, max_workers=1)

    assert result["failed"] == 1
    assert reads == [1, 1, 1, 1]
    assert sent == []


def test_prepared_form_receipt_fences_replay_before_any_second_post(tmp_path):
    module = load()
    url = funded()["form_url"]
    digest = hashlib.sha256(url.encode()).hexdigest()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    binding = adapter._form_binding(funded(), digest)
    receipt = tmp_path / "external-actions" / f"{digest}.json"
    receipt.parent.mkdir()
    (tmp_path / "external-actions" / f"index-{module.google_form._identity(binding)}.json").write_text(
        json.dumps({"version": 1, "status": "prepared", "receipt_key": digest}), encoding="utf-8")
    receipt.write_text(json.dumps({"version": 1, "status": "prepared", "url_sha256": digest,
                                   "binding": binding}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="google_form_submission_uncertain"):
        adapter._submit_form_once(funded())


def test_milestone_completion_targets_only_the_visible_duplicate_form():
    module = load()
    selected = []
    page = None

    class Control:
        def __init__(self, owner, visible=False):
            self.owner, self.visible = owner, visible

        def is_visible(self):
            return self.visible

        def fill(self, value):
            selected.append(("fill", self.owner, value))

        def count(self):
            return 1

        def is_disabled(self):
            return False

        def click(self):
            selected.append(("click", self.owner))
            if self.owner == "todo-tab":
                page.todo_open = True

        def wait_for(self, **kwargs):
            selected.append(("wait", self.owner, kwargs))

    class Form:
        def __init__(self, owner, visible):
            self.owner, self.visible = owner, visible

        def locator(self, selector):
            selected.append(("control", self.owner, selector))
            return Control(self.owner, self.visible if selector.startswith("textarea") else False)

    class Forms:
        @property
        def values(self):
            return [Form("visible", page.todo_open), Form("hidden", False)]

        def count(self):
            return len(self.values)

        def nth(self, index):
            return self.values[index]

    class Page:
        todo_open = False
        mobile = False

        def locator(self, selector):
            selected.append(("form", selector))
            if selector.endswith(':visible'):
                return Control("visible-textarea", self.todo_open)
            return Forms()

        def get_by_text(self, text, exact=False):
            selected.append(("tab", text, exact))
            return FormsForTab()

        def set_viewport_size(self, size):
            self.mobile = True
            selected.append(("viewport", size))

        def wait_for_load_state(self, *args, **kwargs):
            selected.append(("readback-wait", None))

    class FormsForTab:
        def count(self):
            return 1

        def nth(self, index):
            return Control("todo-tab", True)

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    page = Page()
    adapter.page = page
    adapter._goto_contract = lambda work_id: selected.append(("contract", work_id))

    adapter._complete_once(funded(), {"milestone_id": "13798056"})

    assert ("form", 'form[action="/milestones/13798056/complete"]') in selected
    assert ("click", "todo-tab") in selected
    assert any(row[:2] == ("fill", "visible") for row in selected)
    assert ("click", "visible") in selected
    assert not any(row[:2] == ("fill", "hidden") for row in selected)


def test_milestone_completion_opens_the_contract_dialog_anchor():
    module = load()
    events = []
    page = None

    class Control:
        def __init__(self, visible=True): self.visible = visible
        def is_visible(self): return self.visible
        def count(self): return 1
        def click(self, **kwargs): events.append(("dialog", kwargs)); page.dialog_open = True
        def fill(self, value): events.append(("fill", value))
        def is_disabled(self): return False
        def wait_for(self, **kwargs): events.append(("wait", kwargs))

    class Form:
        def locator(self, selector):
            return Control(page.dialog_open)

    class Forms:
        def count(self): return 1
        def nth(self, index): return Form()

    class Page:
        dialog_open = False
        def locator(self, selector):
            if selector.startswith('a[href="#message-dialog-completion-'):
                return Control(True)
            if selector.startswith('form[action="/milestones/13798056/complete"]') and "textarea" in selector:
                return Control(page.dialog_open)
            if selector.startswith('form[action="/milestones/13798056/complete"]'):
                return Forms()
            return Control(False)
        def get_by_text(self, text, exact=False):
            class EmptyTabs:
                def count(self): return 0
            return EmptyTabs()
        def wait_for_load_state(self, *args, **kwargs): pass

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    page = Page()
    adapter.page = page
    adapter._goto_contract = lambda work_id: None

    adapter._complete_once(funded(), {"milestone_id": "13798056"})

    assert any(item[0] == "dialog" for item in events if isinstance(item, tuple))
    assert any(item[0] == "fill" for item in events if isinstance(item, tuple))

def test_delivery_primes_visible_duplicate_message_textareas():
    module = load()
    events = []

    class Area:
        def __init__(self, visible): self.visible = visible
        def is_visible(self): return self.visible
        def fill(self, value): events.append(value)

    class Areas:
        def count(self): return 3
        def nth(self, index): return [Area(True), Area(False), Area(True)][index]

    class Page:
        def locator(self, selector):
            assert selector == 'textarea[name="message[body]"]'
            return Areas()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = Page()

    adapter._fill_delivery_message("納品メッセージ")

    assert events == ["納品メッセージ", "納品メッセージ"]

def test_milestone_completion_reveals_mobile_only_todo_surface_before_effect():
    module = load()
    events = []
    page = None

    class Control:
        def __init__(self, kind): self.kind = kind
        def is_visible(self): return page.mobile if self.kind == "tab" else page.todo_open
        def click(self):
            events.append(("click", self.kind))
            if self.kind == "tab": page.todo_open = True
        def fill(self, value): events.append(("fill", value))
        def count(self): return 1
        def is_disabled(self): return False
        def wait_for(self, **kwargs): events.append(("wait", kwargs))

    class Form:
        def locator(self, selector): return Control("textarea" if selector.startswith("textarea") else "submit")

    class Forms:
        def count(self): return 1
        def nth(self, index): return Form()

    class Tabs:
        def count(self): return 1
        def nth(self, index): return Control("tab")

    class Page:
        mobile = False
        todo_open = False
        def locator(self, selector): return Control("textarea") if selector.endswith(":visible") else Forms()
        def get_by_text(self, text, exact=False): return Tabs()
        def wait_for_load_state(self, *args, **kwargs): pass

    page = Page()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.page = page
    adapter._goto_contract = lambda work_id: events.append(("contract", work_id))
    def switch(work_id):
        page.mobile = True
        events.append(("narrow-context", work_id))
    adapter._switch_to_narrow_contract = switch

    adapter._complete_once(funded(), {"milestone_id": "13798056"})

    assert ("narrow-context", "63570481") in events
    assert events.index(("narrow-context", "63570481")) < events.index(("click", "tab"))
    assert events[-1] == ("click", "submit")


def test_narrow_contract_clones_auth_and_changes_only_isolated_device_cookie():
    module = load()
    canonical = {"cookies": [{"name": "mobylette_device", "value": "pc",
                               "domain": "crowdworks.jp", "path": "/"}], "origins": []}
    received = []

    class Page:
        def set_default_timeout(self, value): pass
        def close(self): pass

    class BaseContext:
        def storage_state(self): return canonical
        def close(self): pass

    class MobileContext:
        def new_page(self): return Page()
        def close(self): pass

    class Browser:
        contexts = [BaseContext()]
        def new_context(self, **kwargs):
            received.append(kwargs)
            return MobileContext()

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.browser = Browser()
    adapter.owned_context = adapter.browser.contexts[0]
    adapter.page = Page()
    adapter._goto_contract = lambda work_id: received.append({"work_id": work_id})

    adapter._switch_to_narrow_contract("63570481")

    assert canonical["cookies"][0]["value"] == "pc"
    assert received[0]["storage_state"]["cookies"][0]["value"] == "sp"
    assert received[0]["is_mobile"] is True
    assert received[1] == {"work_id": "63570481"}


def test_narrow_contract_closes_new_context_when_cookie_setup_fails():
    module = load()
    events = []

    class SourceContext:
        def storage_state(self): return {"cookies": [], "origins": []}

    class MobileContext:
        def add_cookies(self, cookies): raise RuntimeError("cookie-failed")
        def close(self): events.append("mobile-close")

    class Browser:
        def new_context(self, **kwargs): return MobileContext()

    source = SourceContext()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638")
    adapter.browser = Browser()
    adapter.owned_context = source

    with pytest.raises(RuntimeError, match="cookie-failed"):
        adapter._switch_to_narrow_contract("63570481")

    assert events == ["mobile-close"]
    assert adapter.owned_context is source


def test_paid_form_uses_only_the_worker_owned_context(tmp_path, monkeypatch):
    module = load()
    owned = object()
    seen = []

    class Browser:
        @property
        def contexts(self): raise AssertionError("persistent context accessed")

    monkeypatch.setattr(module.google_form, "submit_once",
                        lambda **kwargs: seen.append(kwargs) or {"confirmation_sha256": "ok"})
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    adapter.browser = Browser()
    adapter.owned_context = owned

    adapter._submit_form_once(funded())

    assert seen[0]["context"] is owned
    assert "browser" not in seen[0]


def test_paid_form_receipts_are_isolated_by_contract_binding(tmp_path):
    module = load()
    binding = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)._form_binding(
        funded(), hashlib.sha256(funded()["form_url"].encode()).hexdigest())
    other = {**binding, "contract_id": "63570482", "milestone_id": "13798057"}
    key = module.google_form._identity({**binding, "submission_payload_sha256": "payload"})
    receipt = tmp_path / "external-actions" / f"{key}.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({"binding": binding, "confirmation_sha256": "receipt"}), encoding="utf-8")
    (tmp_path / "external-actions" / f"index-{module.google_form._identity(binding)}.json").write_text(
        json.dumps({"receipt_key": key, "status": "confirmed"}), encoding="utf-8")
    assert module.google_form.bound_receipt(tmp_path, binding)["confirmation_sha256"] == "receipt"
    assert module.google_form.bound_receipt(tmp_path, other) is None


def test_date_question_uses_google_forms_year_month_day_fields(tmp_path):
    module = load()

    class Locator:
        def inner_text(self):
            return "task"

    class Page:
        def locator(self, selector):
            assert selector == "body"
            return Locator()

        def evaluate(self, expression):
            return [[None, "応募日", None, 9, [[12, [], True]]]]

    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    fields = dict(adapter._form_fields(Page(), funded()))
    assert set(fields) == {"entry.12_year", "entry.12_month", "entry.12_day"}


def test_required_form_choice_is_model_owned_and_exactly_validated(tmp_path, monkeypatch):
    module = load()
    seen = []

    class Locator:
        def inner_text(self):
            return "契約済みの業務説明"

    class Page:
        def locator(self, selector):
            assert selector == "body"
            return Locator()

        def evaluate(self, expression):
            return [[None, "希望する業務", None, 2, [[12, [["Web制作"], ["事務"]], True]]]]

    def compose(context, **kwargs):
        seen.append(context)
        return "Web制作"

    monkeypatch.setattr(module.composer, "compose", compose)
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding", lambda **kwargs: {"candidate": {}})
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    adapter.candidate_profile = tmp_path / "candidate.json"
    adapter.provider_profile = {"display_name": "Kaito"}

    assert dict(adapter._form_fields(Page(), funded())) == {"entry.12": "Web制作"}
    assert seen[0]["action_contract"] == {
        "kind": "required_form_field", "question": "希望する業務",
        "allowed_choices": ["Web制作", "事務"]}


def test_required_form_choice_rejects_model_output_outside_official_choices(tmp_path, monkeypatch):
    module = load()
    monkeypatch.setattr(module.composer, "compose", lambda *args, **kwargs: "その他")
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding", lambda **kwargs: {"candidate": {}})
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    adapter.candidate_profile = tmp_path / "candidate.json"
    adapter.provider_profile = {"display_name": "Kaito"}
    with pytest.raises(RuntimeError, match="crowdworks_paid_form_choice_invalid"):
        adapter._compose_text(question="希望する業務", source="説明", item=funded(),
                              choices=["Web制作", "事務"])


def test_readback_rejects_non_submit_without_browser_mutation(tmp_path):
    module = load()
    adapter = module.CrowdWorksPaidAdapter(account_id="7145638", state_path=tmp_path)
    assert adapter.readback({"action": "noop"}) == {"authoritative_absent": True}


def test_owner_uses_shared_kernel_and_provider_adapter_state_root():
    source = OWNER.read_text(encoding="utf-8")
    assert "skills/_shared/marketplace-core/scripts/paid_kernel.py" in source
    assert "skills/earn/crowdworks/scripts/paid_adapter.py" in source
    assert '--state-root "$STATE_ROOT/paid"' in source
    assert '--state-path "$STATE_ROOT/paid"' in source
    assert '--max-workers 1' in source
