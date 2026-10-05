import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "coconala_reply_adapter.py"
SPEC = importlib.util.spec_from_file_location("coconala_reply_adapter_test", MODULE)
adapter_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(adapter_module)


def test_provider_rows_are_normalized_without_owning_lifecycle(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
        inventory_reader=lambda: [{
            "talkroom_id": "12",
            "last_message_identity_sha256": "a" * 64,
        }],
        thread_reader=lambda _thread: ({
            "conversation": [{"side": "buyer", "message_id": "m1", "body": "質問"}],
        }, {"last_sender": "buyer"}),
        sender=lambda *_args: (_ for _ in ()).throw(AssertionError("not called")),
    )
    rows = adapter.observe_threads()
    assert rows[0]["provider"] == "coconala"
    assert rows[0]["thread_id"] == "12"
    assert rows[0]["latest_event_id"] == "a" * 64
    refreshed = adapter.observe_one("12")
    assert refreshed["latest_event_id"] == "m1"
    assert adapter.context("12")["conversation"][-1]["body"] == "質問"


def test_context_carries_shared_privacy_contract_to_the_kernel(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
        grounding={
            "prompt_facts": [{"id": "role", "claim": "Python developer"}],
            "private_identity_values": ["Private Legal Name"],
            "provider_public_facts": {"display_name": "Kaito｜AI自動化"},
        },
        inventory_reader=lambda: [],
        thread_reader=lambda _thread: ({
            "conversation": [{"side": "buyer", "message_id": "m1", "body": "質問"}],
        }, {"last_sender": "buyer"}),
    )

    context = adapter.context("12")

    assert context["grounding"]["private_identity_values"] == ["Private Legal Name"]
    assert context["grounding"]["provider_public_facts"]["display_name"] == "Kaito｜AI自動化"


def test_buyer_last_uses_model_composer_and_seller_last_is_noop(tmp_path):
    seen = []
    composer = lambda context: seen.append(context) or "承知しました。"
    buyer = {"context": {"conversation": [{"role": "buyer", "body": "対応できますか"}]}}
    seller = {"context": {"conversation": [{"role": "seller", "body": "回答済み"}]}}
    planner = adapter_module.reply_planner.ReplyPlanner(composer)
    assert planner(buyer) == {
        "action": "reply", "payload": {"body": "承知しました。"}
    }
    assert planner(seller) == {
        "action": "noop", "classification": "awaiting_buyer"
    }
    assert len(seen) == 1


def test_mutation_and_official_readback_remain_provider_specific(tmp_path):
    effects = []

    def thread_reader(_thread):
        conversation = [{"side": "buyer", "message_id": "m1", "body": "質問"}]
        if effects:
            conversation.append({"side": "seller", "message_id": "m2", "body": "回答"})
        return {"conversation": conversation}, {"last_sender": conversation[-1]["side"]}

    def sender(thread, body, expected):
        assert (thread, body, expected) == ("12", "回答", "m1")
        effects.append(body)
        return {"provider_receipt_id": "m2", "observed_at": "2026-09-08T00:00:01Z"}

    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
        inventory_reader=lambda: [], thread_reader=thread_reader, sender=sender,
    )
    intent = {
        "action": "reply", "thread_id": "12", "latest_event_id": "m1",
        "effect_key": "effect", "payload": {"body": "回答"},
    }
    assert adapter.readback(intent) == {"authoritative_absent": True}
    adapter.mutate(intent)
    assert adapter.readback(intent)["provider_receipt_id"] == "m2"
    assert effects == ["回答"]


def test_official_sending_restriction_is_the_only_classified_mutation_wait(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    assert adapter.classify_mutation_error(
        RuntimeError("submit_rejected_sending_unavailable")
    ) == {
        "reason": "provider_sending_unavailable",
        "remaining_work": ["Wait for the provider message control to become available"],
    }
    assert adapter.classify_mutation_error(RuntimeError("network_timeout")) is None


def test_only_exact_navigation_timeout_is_classified_as_observation_wait(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    assert adapter.classify_observation_error(
        RuntimeError("authenticated tab did not finish navigation")
    ) == {"reason": "provider_readback_temporarily_unavailable"}
    assert adapter.classify_observation_error(RuntimeError("network_timeout")) is None


@pytest.mark.parametrize(
    "error_text,expected_reason",
    [
        (
            "collector_unhealthy:inbox_access_forbidden",
            "provider_inbox_access_forbidden",
        ),
        (
            "collector_unhealthy:inbox_provider_http_error",
            "provider_inbox_http_error",
        ),
    ],
)
def test_provider_inbox_access_errors_are_explicit_observation_waits(
    tmp_path, error_text, expected_reason,
):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    classified = adapter.classify_observation_error(RuntimeError(error_text))

    assert classified == {
        "reason": expected_reason,
        "remaining_work": ["Retry the authenticated Coconala inbox read and preserve the provider receipt"],
    }


@pytest.mark.parametrize(
    "error_text",
    [
        "collector_unhealthy:missing_container",
        "collector_unhealthy:inbox_coverage_incomplete",
        "collector_unhealthy:login_redirect",
    ],
)
def test_other_collector_boundaries_are_waits_not_failed_reply_wakes(
    tmp_path, error_text,
):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    assert adapter.classify_observation_error(RuntimeError(error_text)) == {
        "reason": "provider_inbox_observation_unavailable",
        "remaining_work": [
            "Retry the authenticated Coconala inbox observation before any reply effect",
        ],
    }


def test_default_runtime_paths_stay_inside_the_release(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
        inventory_reader=lambda: [],
        thread_reader=lambda _thread: ({}, {}),
        sender=lambda *_args: {},
    )
    assert adapter.cdp_helper == (
        adapter_module.REPO_ROOT / "skills/browser/scripts/cdp_default_tab.py"
    )
    assert adapter.cdp_helper.is_file()


def test_inventory_retries_transient_incomplete_coverage(monkeypatch, tmp_path):
    observations = []

    def inspect(*_args, **_kwargs):
        observations.append(True)
        if len(observations) == 1:
            raise adapter_module.snapshot.CollectorUnhealthy(
                "inbox_pagination_terminal_unproven"
            )
        return {
            "url": adapter_module.snapshot.MESSAGES_URL,
            "title": "メッセージ",
            "container_present": True,
            "coverage_complete": True,
            "termination_reason": "pagination_end",
            "pagination_pages": 1,
            "page_counts": [1],
            "pagination_container_present": True,
            "pagination_current_present": True,
            "pagination_terminal_proven": True,
            "pagination_current_page": 1,
            "pagination_highest_page": 1,
            "pagination_next_present": False,
            "cards_count": 1,
            "cards": [{
                "talkroom_url": "https://coconala.com/mypage/direct_message/12",
                "last_message_identity_sha256": "a" * 64,
            }],
        }

    monkeypatch.setattr(adapter_module.snapshot, "inspect_page_with_retry", inspect)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
    )

    rows = adapter._read_inventory()

    assert len(observations) == 2
    assert rows[0]["talkroom_id"] == "12"


def test_inventory_uses_visible_target_for_dynamic_direct_inbox(monkeypatch, tmp_path):
    seen = {}

    def inspect(_helper, url, expression, _screenshot, **kwargs):
        seen.update({
            "url": url,
            "expression": expression,
            "coverage_expression": kwargs.get("coverage_expression"),
            "hidden": kwargs["hidden"],
        })
        return {
            "url": url,
            "title": "メッセージ | マイページ | ココナラ",
            "container_present": True,
            "coverage_complete": True,
            "termination_reason": "fixed_point",
            "cards_count": 1,
            "cards": [{
                "talkroom_url": "https://coconala.com/mypage/direct_message/12",
                "last_message_identity_sha256": "a" * 64,
            }],
        }

    monkeypatch.setattr(adapter_module.snapshot, "inspect_page_with_retry", inspect)
    adapter = adapter_module.CoconalaReplyAdapter(state_root=tmp_path)

    rows = adapter._read_inventory()

    assert seen == {
        "url": "https://coconala.com/message?fromMyPage=true",
        "expression": adapter_module.snapshot.MESSAGES_EXPRESSION,
        "coverage_expression": adapter_module.snapshot.DIRECT_INBOX_COVERAGE_EXPRESSION,
        "hidden": False,
    }
    assert rows[0]["talkroom_id"] == "12"


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("403 Forbidden", "inbox_access_forbidden"),
        ("メッセージ | マイページ | ココナラ", "inbox_coverage_incomplete"),
    ],
)
def test_reply_query_failure_receipt_uses_direct_family(monkeypatch, tmp_path, title, reason):
    calls = []

    def inspect(_helper, url, _expression, _screenshot, **kwargs):
        calls.append((url, kwargs))
        return {
            "url": url,
            "title": title,
            "source": "b1_inbox",
            "cards": [],
            "cards_count": 0,
            "coverage_complete": False,
            "termination_reason": None,
            "iterations": 3,
        }

    monkeypatch.setattr(adapter_module.snapshot, "inspect_page_with_retry", inspect)
    adapter = adapter_module.CoconalaReplyAdapter(state_root=tmp_path)

    with pytest.raises(adapter_module.snapshot.CollectorUnhealthy, match=reason) as raised:
        adapter._read_inventory()

    assert raised.value.details["source"] == "direct_inbox"
    assert calls
    assert all(url == adapter_module.REPLY_INBOX_URL for url, _ in calls)
    assert all(kwargs["validate_coverage"] is False for _, kwargs in calls)


def test_query_failure_receipt_keeps_b1_default_despite_dom_source_label():
    with pytest.raises(
        adapter_module.snapshot.CollectorUnhealthy,
        match="inbox_access_forbidden",
    ) as raised:
        adapter_module.snapshot.validate_inbox_coverage({
            "url": adapter_module.REPLY_INBOX_URL,
            "title": "403 Forbidden",
            "source": "direct_inbox",
            "cards": [],
            "cards_count": 0,
            "coverage_complete": False,
            "termination_reason": None,
            "iterations": 3,
        })

    assert raised.value.details["source"] == "b1_inbox"


def test_direct_coverage_expression_selects_direct_links_on_mixed_query_inbox():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to evaluate the browser expression")
    harness = r"""
const direct = "https://coconala.com/mypage/direct_message/12";
const paid = "https://coconala.com/talkrooms/34";
const anchor = (href, text) => ({
  href, innerText: text, __vue__: null,
  closest() { return this; }, querySelector() { return null; },
});
const anchors = [anchor(direct, "Direct buyer message"), anchor(paid, "Paid talkroom")];
const root = {
  innerText: "Direct buyer message\nPaid talkroom",
  scrollHeight: 100,
  querySelector() { return null; },
  querySelectorAll(selector) {
    const hrefParts = [...selector.matchAll(/href\*='([^']+)'/g)].map(match => match[1]);
    return anchors.filter(item => hrefParts.some(part => item.href.includes(part)));
  },
};
const current = {innerText: "1", getAttribute(name) { return name === "data-page" ? "1" : null; }};
const next = {disabled: true, innerText: "", getAttribute(name) { return name === "aria-disabled" ? "true" : null; }, click() {}};
const pagination = {
  querySelector(selector) { return selector === ".pagination-link-current" ? current : next; },
  querySelectorAll() { return [current, next]; },
};
globalThis.location = {pathname: "/message", href: "https://coconala.com/message?fromMyPage=true", origin: "https://coconala.com"};
globalThis.document = {
  title: "メッセージ",
  body: root,
  querySelector(selector) { return selector === ".c-pagination" ? pagination : root; },
  querySelectorAll: (...args) => root.querySelectorAll(...args),
};
globalThis.window = {scrollTo() {}};
globalThis.crypto = {subtle: {digest: async () => new Uint8Array(32).buffer}};
(async () => {
  const expression = require("node:fs").readFileSync(0, "utf8");
  process.stdout.write(await eval(expression));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [node, "-e", harness],
        input=adapter_module.snapshot.DIRECT_INBOX_COVERAGE_EXPRESSION,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    dom = __import__("json").loads(result.stdout)
    assert dom["coverage_complete"] is True
    assert [row["talkroom_url"] for row in dom["cards"]] == [
        "https://coconala.com/mypage/direct_message/12",
    ]


def test_modern_smartphone_direct_message_route_is_canonicalized():
    dom = {
        "url": "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121",
        "title": "メッセージ | マイページ | ココナラ",
        "container_present": True,
        "coverage_complete": True,
        "termination_reason": "fixed_point",
        "cards_count": 1,
        "cards": [{
            "talkroom_url": "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121",
            "preview_sha256": "a" * 64,
            "last_message_identity_sha256": "b" * 64,
        }],
    }

    adapter_module.snapshot.validate_page_identity(
        dom, expected_url="https://coconala.com/mypage/direct_message/10107358",
        expected_title="メッセージ",
    )
    rows = adapter_module.snapshot.inquiries_from_dom({
        **dom,
        "url": adapter_module.snapshot.MESSAGES_URL,
        "title": "メッセージ | マイページ | ココナラ",
        "cards": [{
            **dom["cards"][0],
            "talkroom_url": "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121",
        }],
    })

    assert rows[0]["talkroom_id"] == "10107358"
    assert rows[0]["talkroom_url"] == (
        "https://coconala.com/mypage/direct_message/10107358"
    )
    assert rows[0]["browser_thread_url"] == (
        "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121"
    )


def test_reply_browser_accepts_uid_bound_smartphone_thread_url():
    modern = "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121"

    assert adapter_module.reply_browser.direct_message_path(modern) == (
        "/mypage/direct_message/10107358"
    )


def test_adapter_reuses_observed_browser_thread_url(tmp_path):
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
        inventory_reader=lambda: [],
    )
    modern = "https://coconala.com/smartphone/direct_messages/10107358?uid=2564121"
    adapter._thread_urls["10107358"] = modern

    assert adapter._thread_url("10107358") == modern


def test_modern_dom_contract_is_present_in_both_message_readers():
    assert ".bl_messages-list" in adapter_module.snapshot.MESSAGES_EXPRESSION
    assert ".bl_message" in adapter_module.snapshot.DIRECT_MESSAGE_EXPRESSION
    assert "/smartphone/direct_messages/" in adapter_module.snapshot.DIRECT_INBOX_COVERAGE_EXPRESSION


def test_direct_message_expression_is_javascript_parseable():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to parse the browser expression")
    result = subprocess.run(
        [node, "--check"],
        input=adapter_module.snapshot.DIRECT_MESSAGE_EXPRESSION + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("own_path", "author_path", "expected_side"),
    [
        ("/users/seller", "/users/seller", "seller"),
        ("/users/seller", "/users/buyer", "buyer"),
        ("/users/seller", None, None),
        (None, "/users/seller", None),
        (None, "/users/0", None),
        ("/users/seller", "/users/other", "buyer"),
    ],
)
def test_active_direct_offer_extractor_requires_author_and_own_proof(
        own_path, author_path, expected_side):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to evaluate the browser expression")
    harness = r"""
const input = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const user = path => path ? {href: `https://coconala.com${path}`} : null;
const author = user(input.author_path);
const own = user(input.own_path);
const title = {innerText: "開発"};
const content = {innerText: "実装\n完了予定日：2026-10-12（1週間後）"};
const time = {innerText: "2026-10-05T00:00:01Z"};
const offerLink = {href: "https://coconala.com/mypage/direct_offers/55"};
const offer = {
  innerText: "提案額 10,000 円 完了予定日：2026-10-12",
  querySelector(selector) {
    if (selector === ".customize-title-link[href]") return offerLink;
    if (selector === ".customize-title") return title;
    if (selector === "p.customize-content.wa_add-mt-4") return content;
    return null;
  },
};
const card = {
  closest(selector) { return selector === ".threadMessage" ? offer : null; },
  querySelector(selector) {
    return selector === ".message-customize-title"
      ? {innerText: "見積り提案をしました"} : null;
  },
};
const row = {
  id: "message-1",
  getAttribute(name) { return name === "data-message-id" ? "message-1" : null; },
  querySelector(selector) {
    if (selector === ".threadMessage") return offer;
    if (selector === '.threadUser a[href*="/users/"]') return author;
    if (selector === ".threadPostTime") return time;
    if (selector === ".js-translateMessageOriginalMessage,.threadMessage") {
      return {innerText: "見積り依頼"};
    }
    return null;
  },
  querySelectorAll(selector) { return selector === ".message-customize" ? [card] : []; },
};
const container = {
  querySelectorAll(selector) { return selector === ".threadColomun" ? [row] : []; },
};
globalThis.location = {
  origin: "https://coconala.com",
  href: "https://coconala.com/mypage/direct_message/12",
};
globalThis.document = {
  title: "メッセージ",
  body: {innerText: ""},
  querySelector(selector) {
    if (selector === ".bl_messages-list") return null;
    if (selector === ".js_thread-wrapper") return container;
    if (selector === '.sidebar-profile a[href*="/users/"]') return own;
    return null;
  },
  querySelectorAll() { return []; },
};
process.stdout.write(eval(input.expression));
"""
    observed = subprocess.run(
        [node, "-e", harness],
        input=json.dumps({
            "expression": adapter_module.snapshot.DIRECT_MESSAGE_EXPRESSION,
            "own_path": own_path,
            "author_path": author_path,
        }),
        text=True,
        capture_output=True,
        check=False,
    )
    assert observed.returncode == 0, observed.stderr
    dom = json.loads(observed.stdout)
    assert len(dom["structured_offers"]) == 1
    card = dom["structured_offers"][0]
    assert card.get("author_path") == author_path
    assert dom.get("own_user_path") == own_path
    assert card.get("sender_side") == expected_side

    from datetime import date
    semantic = adapter_module.requested_estimate
    today = date(2026, 10, 5)
    terms = semantic.materialize_delivery_content({
        "title": "開発", "content": "実装", "quantity": 1,
        "price_jpy": 10000, "delivery_days": 7, "purchase_plan": "single",
    }, today)
    outcome = semantic.classify_delivery(
        pre_click_cards=dom["structured_offers"], post_click_cards=[],
        terms=terms, click_started_at=None, today=today,
        request_sent_at="2026-10-05T00:00:00Z",
        own_user_path=dom.get("own_user_path"),
    )
    if expected_side == "seller":
        assert outcome["status"] == "already_delivered"
        assert len(outcome["cards"]) == 1
    else:
        assert outcome["status"] == "not_required"
        assert outcome["cards"] == []


def test_fill_expression_supports_current_smartphone_message_input():
    expression = adapter_module.reply_browser.fill_expression("返信本文")

    assert "textarea.message-input" in expression
    assert "const controls=legacy.length?legacy:modern;" in expression
    assert "input.classList.contains('message-input')" in expression


def test_inbox_403_is_classified_as_provider_access_denied():
    with pytest.raises(
        adapter_module.snapshot.CollectorUnhealthy,
        match="inbox_access_forbidden",
    ) as raised:
        adapter_module.snapshot.validate_inbox_coverage({
            "url": adapter_module.snapshot.MESSAGES_URL,
            "title": "403 Forbidden",
            "cards": [],
            "cards_count": 0,
            "coverage_complete": False,
            "termination_reason": None,
            "iterations": 3,
        })

    assert raised.value.details["provider_http_status"] == 403


def test_inventory_does_not_retry_non_transient_collector_failure(monkeypatch, tmp_path):
    observations = []

    def inspect(*_args, **_kwargs):
        observations.append(True)
        raise adapter_module.snapshot.CollectorUnhealthy("login_redirect")

    monkeypatch.setattr(adapter_module.snapshot, "inspect_page_with_retry", inspect)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path,
    )

    with pytest.raises(adapter_module.snapshot.CollectorUnhealthy, match="login_redirect"):
        adapter._read_inventory()

    assert len(observations) == 1


def test_inventory_classifies_default_tab_http_error(monkeypatch, tmp_path):
    def inspect(*_args, **_kwargs):
        raise RuntimeError(
            "failed to open authenticated default tab: "
            "HTTPError: HTTP Error 404: Not Found"
        )

    monkeypatch.setattr(adapter_module.snapshot, "inspect_page_with_retry", inspect)
    adapter = adapter_module.CoconalaReplyAdapter(state_root=tmp_path)

    with pytest.raises(
        adapter_module.snapshot.CollectorUnhealthy,
        match="inbox_provider_http_error",
    ) as raised:
        adapter._read_inventory()

    assert raised.value.details == {
        "provider_http_status": 404,
        "helper_error": (
            "failed to open authenticated default tab: "
            "HTTPError: HTTP Error 404: Not Found"
        ),
    }


def test_read_thread_retries_only_pre_effect_navigation_timeout(monkeypatch, tmp_path):
    attempts = []
    closed = []
    owners = []

    class Browser:
        raw = {"messages": [{"message_id": "m1"}]}

        def __init__(self, *_args, **kwargs):
            attempts.append(self)
            owners.append(kwargs.get("owner"))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            closed.append(self)
            return None

        def read_before(self):
            if len(attempts) == 1:
                raise RuntimeError("authenticated tab did not finish navigation")
            return ({
                "conversation": [{"side": "buyer", "message_id": "m1", "body": "質問"}],
            }, {"last_sender": "buyer"})

    monkeypatch.setattr(adapter_module.reply_browser, "CoconalaCdpReplyBrowser", Browser)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    context, bounded = adapter._read_thread("12")

    assert len(attempts) == 2
    assert closed == attempts
    assert owners == ["coconala-reply-12", "coconala-reply-12"]
    assert context["conversation"][-1]["message_id"] == "m1"
    assert bounded["last_sender"] == "buyer"


@pytest.mark.parametrize(
    "transient_error",
    [
        "collector_unhealthy:unexpected_title",
        "collector_unhealthy:dm_attachment_message_identity_changed",
    ],
)
def test_read_thread_retries_transient_read_boundary(monkeypatch, tmp_path, transient_error):
    attempts = []

    class Browser:
        raw = {"messages": [{"message_id": "m1"}]}

        def __init__(self, *_args, **_kwargs):
            attempts.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read_before(self):
            if len(attempts) == 1:
                raise RuntimeError(transient_error)
            return ({
                "conversation": [{"side": "buyer", "message_id": "m1", "body": "質問"}],
            }, {"last_sender": "buyer"})

    monkeypatch.setattr(adapter_module.reply_browser, "CoconalaCdpReplyBrowser", Browser)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    context, bounded = adapter._read_thread("12")

    assert len(attempts) == 2
    assert context["conversation"][-1]["message_id"] == "m1"
    assert bounded["last_sender"] == "buyer"


def test_read_thread_does_not_retry_non_navigation_failure(monkeypatch, tmp_path):
    attempts = []

    class Browser:
        def __init__(self, *_args, **_kwargs):
            attempts.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read_before(self):
            raise RuntimeError("coconala_conversation_invalid")

    monkeypatch.setattr(adapter_module.reply_browser, "CoconalaCdpReplyBrowser", Browser)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    with pytest.raises(RuntimeError, match="coconala_conversation_invalid"):
        adapter._read_thread("12")

    assert len(attempts) == 1


def test_read_thread_propagates_second_navigation_timeout(monkeypatch, tmp_path):
    attempts = []

    class Browser:
        def __init__(self, *_args, **_kwargs):
            attempts.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read_before(self):
            raise RuntimeError("authenticated tab did not finish navigation")

    monkeypatch.setattr(adapter_module.reply_browser, "CoconalaCdpReplyBrowser", Browser)
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
    )

    with pytest.raises(RuntimeError, match="authenticated tab did not finish navigation"):
        adapter._read_thread("12")

    assert len(attempts) == 2


def test_coconala_build_passes_shared_grounding_to_semantic_judge(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"candidate":{"gender":"male"},"facts":[]}', encoding="utf-8")
    public = tmp_path / "public.json"
    public.write_text('{"hours_limit":"31-40"}', encoding="utf-8")
    captured = {}

    class Judge:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(adapter_module.requested_estimate, "SemanticJudge", Judge)
    monkeypatch.setattr(
        adapter_module.requested_estimate, "RequestedEstimateComposer",
        lambda **_kwargs: object(),
    )
    adapter_module.build([
        "--state-root", str(tmp_path / "state"),
        "--cdp-helper", str(Path(__file__)),
        "--runner", str(Path(__file__)),
        "--schema", str(Path(__file__)),
        "--estimate-schema", str(Path(__file__)),
        "--candidate-profile", str(candidate),
        "--provider-profile", str(public),
    ])

    assert {row["claim"] for row in captured["seller_facts"]} >= {
        "性別: male", "週あたりの稼働時間: 31-40時間",
    }


def test_semantic_composer_projects_validated_judgement_without_provider_decide():
    class Adapter:
        def semantic_dom(self, thread_id):
            assert thread_id == "12"
            return {"version": "official", "estimate_url": "/direct_offers/add/12"}

        def official_application_context(self, _thread_id):
            raise AssertionError("application context not requested")

    calls = []

    def judge(dom, url, **kwargs):
        calls.append((dom, url, kwargs))
        return {"context_sha256": "a" * 64, "judgement": {
            "next_action": "send_estimate",
            "required_official_context": "none",
            "evidence_message_ids": ["m1"],
            "estimate_terms": {
                "title": "開発", "content": "実装", "quantity": 1,
                "price_jpy": 10000, "delivery_days": 7, "purchase_plan": "single",
            },
        }}

    composer = adapter_module.CoconalaSemanticComposer(Adapter(), judge)
    result = composer({
        "thread_id": "12",
        "conversation": [{"message_id": "m1", "sent_at": "2026-09-08T00:00:00Z"}],
    })
    assert result["next_action"] == "send_estimate"
    assert calls[0][1].endswith("/12")


def test_semantic_composer_waits_when_official_estimate_control_is_absent():
    class Adapter:
        def semantic_dom(self, _thread_id):
            return {"version": "official", "estimate_url": None}

        def official_application_context(self, _thread_id):
            raise AssertionError("application context not requested")

    def judge(_dom, _url, **_kwargs):
        return {"context_sha256": "a" * 64, "judgement": {
            "next_action": "send_estimate",
            "required_official_context": "none",
            "evidence_message_ids": ["m1"],
            "estimate_terms": {
                "title": "開発", "content": "実装", "quantity": 1,
                "price_jpy": 10000, "delivery_days": 7, "purchase_plan": "single",
            },
        }}

    result = adapter_module.CoconalaSemanticComposer(Adapter(), judge)({
        "thread_id": "12",
        "conversation": [{"message_id": "m1", "sent_at": "2026-09-08T00:00:00Z"}],
    })

    assert result == {
        "action": "wait",
        "reason": "provider_estimate_control_unavailable",
        "remaining_work": ["Wait for the official estimate control to become available"],
    }


def test_semantic_composer_refreshes_required_official_application_once():
    class Adapter:
        def __init__(self):
            self.version = 1

        def semantic_dom(self, _thread_id):
            return {"version": self.version}

        def official_application_context(self, _thread_id):
            self.version = 2
            return {"application": {"proposal_id": "7"}}

    calls = []

    def judge(dom, _url, **kwargs):
        calls.append((dom, kwargs))
        if not kwargs:
            return {"judgement": {
                "next_action": "wait",
                "required_official_context": "application",
                "uncertainty": ["公式応募条件"],
            }}
        return {"judgement": {
            "next_action": "reply", "required_official_context": "none",
            "reply_body": "対応可能です。",
        }}

    result = adapter_module.CoconalaSemanticComposer(Adapter(), judge)({"thread_id": "12"})
    assert result["reply_body"] == "対応可能です。"
    assert calls[1] == ({"version": 2}, {"official_context": {"application": {"proposal_id": "7"}}})


def test_semantic_composer_passes_multiple_verified_applications_without_guessing():
    applications = [{"offer_id": "7"}, {"offer_id": "8"}]

    class Adapter:
        def semantic_dom(self, _thread_id):
            return {"version": "official"}

        def official_application_context(self, _thread_id):
            return {"applications": applications}

    calls = []

    def judge(dom, _url, **kwargs):
        calls.append((dom, kwargs))
        if not kwargs:
            return {"judgement": {
                "next_action": "wait", "required_official_context": "application",
                "uncertainty": ["公式応募条件"],
            }}
        return {"judgement": {
            "next_action": "reply", "required_official_context": "none",
            "reply_body": "対応可能です。",
        }}

    result = adapter_module.CoconalaSemanticComposer(Adapter(), judge)({"thread_id": "12"})

    assert result["reply_body"] == "対応可能です。"
    assert calls[1][1] == {"official_context": {"applications": applications}}


def test_semantic_composer_preserves_official_sending_restriction_as_wait():
    class Adapter:
        def semantic_dom(self, _thread_id):
            raise AssertionError("restricted thread must not invoke the model")

    result = adapter_module.CoconalaSemanticComposer(
        Adapter(), lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())
    )({"thread_id": "12", "provider_sending_unavailable": True})

    assert result == {
        "action": "wait",
        "reason": "provider_sending_unavailable",
        "remaining_work": ["Wait for the provider message control to become available"],
    }


def _estimate_intent():
    return {
        "action": "estimate", "thread_id": "12", "effect_key": "effect",
        "payload": {
            "title": "開発", "content": "実装", "quantity": 1,
            "price_jpy": 10000, "delivery_days": 7, "purchase_plan": "single",
            "_semantic_context_sha256": "a" * 64,
            "_request_sent_at": "2026-09-08T00:00:00Z",
            "_estimate_url": "/direct_offers/add/12", "_offer_date": "2026-09-08",
        },
    }


def test_estimate_mutation_uses_provider_ceremony_and_caches_official_receipt(monkeypatch, tmp_path):
    calls = []

    class Composer:
        def select_category(self, level, _context, _form):
            return {"master": "M", "sub": "S", "type": "T"}[level]

        def terms_with_categories(self, context, **labels):
            return {
                **context["semantic_estimate_terms"],
                "master_category_label": labels["master"],
                "sub_category_label": labels["sub"],
                "category_type_label": labels["typ"],
            }

    class Browser:
        semantic_context_required = False

        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read_thread_context(self):
            return {"conversation": [{"message_id": "m1"}]}, {"own_user_path": "/users/1"}
        def open_form(self): calls.append("open"); return {"categories": {}}
        def select_master(self, _label): calls.append("master"); return {"categories": {}}
        def select_sub(self, _label): calls.append("sub"); return {"categories": {}}
        def fill(self, _terms, _completion): calls.append("fill"); return {"selected_categories": {}}
        def read_form(self): return {}
        def first_submit(self): calls.append("first")
        def read_confirmation(self): return {}
        def fresh_thread_context(self, own): return {"own_user_path": own, "conversation": [{"message_id": "m1"}]}
        def final_submit(self, *_args, **_kwargs): calls.append("final")
        def read_after(self):
            return {"structured_offers": [{}], "own_user_path": "/users/1"}

    semantic = adapter_module.requested_estimate
    monkeypatch.setattr(semantic, "semantic_context_sha256", lambda _rows: "a" * 64)
    monkeypatch.setattr(semantic, "validate_form_contract", lambda _form: True)
    monkeypatch.setattr(semantic, "_category_type_optional", lambda _form: False)
    monkeypatch.setattr(semantic, "validate_estimate_terms", lambda terms, _context: terms)
    monkeypatch.setattr(semantic, "materialize_delivery_content", lambda terms, _today: terms)
    monkeypatch.setattr(semantic, "validate_selected_categories", lambda *_args: True)
    monkeypatch.setattr(semantic, "validate_form_selection", lambda *_args: True)
    monkeypatch.setattr(semantic, "validate_confirmation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(semantic, "completion_date", lambda *_args: __import__("datetime").date(2026, 9, 15))
    monkeypatch.setattr(semantic, "classify_delivery", lambda **_kwargs: {
        "status": "verified", "cards": [{"offer_url": "/mypage/direct_offers/55"}],
    })
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
        thread_reader=lambda _thread: ({}, {}), sender=lambda *_args: {},
        estimate_composer=Composer(), estimate_browser_factory=lambda *_args: Browser(),
    )
    intent = _estimate_intent()
    adapter.mutate(intent)
    assert calls == ["open", "master", "sub", "fill", "first", "final"]
    assert adapter.readback(intent)["provider_receipt_id"] == "/mypage/direct_offers/55"


def test_estimate_readback_finds_existing_official_card_without_mutation(monkeypatch, tmp_path):
    factory_calls = []
    class Browser:
        semantic_context_required = False
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read_thread_context(self):
            return {"conversation": []}, {
                "structured_offers": [{"offer_url": "/mypage/direct_offers/55"}],
                "own_user_path": "/users/1",
            }

    semantic = adapter_module.requested_estimate
    monkeypatch.setattr(semantic, "semantic_context_sha256", lambda _rows: "a" * 64)
    monkeypatch.setattr(semantic, "materialize_delivery_content", lambda terms, _today: terms)
    monkeypatch.setattr(semantic, "classify_delivery", lambda **_kwargs: {
        "status": "already_delivered",
        "cards": [{"offer_url": "/mypage/direct_offers/55"}],
    })
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
        thread_reader=lambda _thread: ({}, {}), sender=lambda *_args: {},
        estimate_composer=object(),
        estimate_browser_factory=lambda *args: factory_calls.append(args) or Browser(),
    )
    assert adapter.readback(_estimate_intent())["provider_receipt_id"] == "/mypage/direct_offers/55"
    assert factory_calls[0][-1] == "coconala-reply-12"


def test_estimate_post_click_unknown_returns_for_reconciliation_without_retry_signal(monkeypatch, tmp_path):
    class Composer:
        def select_category(self, level, _context, _form):
            return {"master": "M", "sub": "S", "type": "T"}[level]
        def terms_with_categories(self, context, **labels):
            return {**context["semantic_estimate_terms"],
                    "master_category_label": labels["master"],
                    "sub_category_label": labels["sub"],
                    "category_type_label": labels["typ"]}

    class Browser:
        semantic_context_required = False
        final_clicks = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read_thread_context(self): return {"conversation": []}, {"own_user_path": "/users/1"}
        def open_form(self): return {}
        def select_master(self, _label): return {}
        def select_sub(self, _label): return {}
        def fill(self, *_args): return {"selected_categories": {}}
        def read_form(self): return {}
        def first_submit(self): return None
        def read_confirmation(self): return {}
        def fresh_thread_context(self, own): return {"own_user_path": own, "conversation": []}
        def final_submit(self, *_args, **_kwargs):
            self.final_clicks += 1
            raise RuntimeError("transition_unknown")

    semantic = adapter_module.requested_estimate
    monkeypatch.setattr(semantic, "semantic_context_sha256", lambda _rows: "a" * 64)
    monkeypatch.setattr(semantic, "validate_form_contract", lambda _form: True)
    monkeypatch.setattr(semantic, "_category_type_optional", lambda _form: False)
    monkeypatch.setattr(semantic, "validate_estimate_terms", lambda terms, _context: terms)
    monkeypatch.setattr(semantic, "materialize_delivery_content", lambda terms, _today: terms)
    monkeypatch.setattr(semantic, "validate_selected_categories", lambda *_args: True)
    monkeypatch.setattr(semantic, "validate_form_selection", lambda *_args: True)
    monkeypatch.setattr(semantic, "validate_confirmation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(semantic, "completion_date", lambda *_args: __import__("datetime").date(2026, 9, 15))
    adapter = adapter_module.CoconalaReplyAdapter(
        state_root=tmp_path, inventory_reader=lambda: [],
        thread_reader=lambda _thread: ({}, {}), sender=lambda *_args: {},
        estimate_composer=Composer(), estimate_browser_factory=lambda *_args: Browser(),
    )
    assert adapter.mutate(_estimate_intent()) is None
