#!/usr/bin/env python3
"""Thin CrowdWorks boundary for the shared marketplace Paid kernel."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[2] / "_shared/marketplace-core/scripts"
ACTIVE_CONTRACTS_URL = "https://crowdworks.jp/e/contracts?status=active"
ACCOUNT_ID = "7145638"
DEFAULT_APPLICATION_RECEIPTS = Path.home() / ".local/state/anicca/crowdworks/application-receipts.jsonl"
FORM_SELECTION_COMPLETE = "__no_additional_form_required__"
PERMISSION_REQUEST_BODY = "リンク先の閲覧権限を付与いただくか、本文を貼り付けてください。"


def _delivery_message(milestone_id: str, *, form: bool) -> str:
    prefix = ("Googleフォームへの回答を完了しました。"
              if form else "依頼内容への対応を完了しました。")
    return f"{prefix}（納品対象マイルストーン: {milestone_id}）ご確認のほどよろしくお願いいたします。"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


account = _load("crowdworks_paid_account", HERE / "account.py")
composer = _load("crowdworks_paid_composer", SHARED / "reply_composer.py")
grounding_module = _load("crowdworks_paid_grounding", SHARED / "reply_grounding.py")
profile_module = _load("crowdworks_paid_profile", HERE / "profile.py")
google_form = _load("crowdworks_paid_google_form", HERE / "google_form.py")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any, error: str = "crowdworks_paid_invalid") -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise RuntimeError(error)
    return str(value).strip()


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _google_form_url(value: str) -> bool:
    return google_form.is_google_form_url(value)


class CrowdWorksPaidBrowserUnavailable(RuntimeError):
    paid_error_code = "crowdworks_paid_browser_unavailable"


def _connect_existing_cdp() -> tuple[Any, Any]:
    """Connect only; never create, repair, or close the CrowdWorks browser process."""
    for attempt in range(4):
        runtime = sync_playwright().start()
        try:
            browser = runtime.chromium.connect_over_cdp(account.CDP_URL, timeout=10_000)
            contexts = getattr(browser, "contexts", None)
            if contexts is not None and len(contexts) != 1:
                raise RuntimeError("crowdworks_paid_browser_context_unavailable")
            return runtime, browser
        except Exception:
            runtime.stop()
            if attempt < 3:
                time.sleep(0.5)
    raise CrowdWorksPaidBrowserUnavailable("crowdworks_paid_browser_unavailable") from None


class CrowdWorksPaidWait(RuntimeError):
    def __init__(self, reason: str, remaining_work: list[str]):
        super().__init__(reason)
        self.paid_wait_reason = reason
        self.paid_remaining_work = remaining_work


class CrowdWorksPaidActiveContractsTimeout(RuntimeError):
    paid_error_code = "crowdworks_paid_active_contracts_timeout"


class CrowdWorksPaidContractTimeout(RuntimeError):
    paid_error_code = "crowdworks_paid_contract_timeout"


class CrowdWorksPaidProposalTimeout(RuntimeError):
    paid_error_code = "crowdworks_paid_proposal_timeout"


class CrowdWorksPaidMilestoneTimeout(RuntimeError):
    paid_error_code = "crowdworks_paid_milestone_timeout"


_TIMEOUTS = {
    "active_contracts": CrowdWorksPaidActiveContractsTimeout,
    "contract": CrowdWorksPaidContractTimeout,
    "proposal": CrowdWorksPaidProposalTimeout,
    "milestone": CrowdWorksPaidMilestoneTimeout,
}


class CrowdWorksPaidAdapter:
    """CrowdWorks-only observation and effects; kernel owns durable lifecycle."""

    def __init__(self, *, account_id: str, inventory_reader: Callable[[], Mapping[str, Any]] | None = None,
                 state_path: Path | None = None, candidate_profile: Path | None = None,
                 provider_profile: Mapping[str, Any] | None = None,
                 connection_factory: Callable[[], tuple[Any, Any]] | None = None,
                 context_factory: Callable[[Any, Any], Any] | None = None,
                 application_receipts_path: Path = DEFAULT_APPLICATION_RECEIPTS):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("crowdworks_account_id_invalid")
        self.account_id = account_id.strip()
        self.inventory_reader = inventory_reader
        self.state_path = Path(state_path) if state_path is not None else None
        self.candidate_profile = Path(candidate_profile) if candidate_profile is not None else None
        self.provider_profile = dict(provider_profile) if provider_profile is not None else None
        self.connection_factory = connection_factory or _connect_existing_cdp
        self._requires_isolation = context_factory is None
        self.context_factory = context_factory or self._isolated_context
        self.application_receipts_path = Path(application_receipts_path).expanduser()
        self._local = threading.local()
        self._cache_lock = threading.Lock()
        # Contract facts only: never a Playwright runtime, browser, context, or page.
        self._contract_cache: dict[str, dict[str, Any]] = {}

    @property
    def browser(self):
        return getattr(self._local, "browser", None)

    @browser.setter
    def browser(self, value) -> None:
        self._local.browser = value

    @property
    def page(self):
        return getattr(self._local, "page", None)

    @page.setter
    def page(self, value) -> None:
        self._local.page = value

    @property
    def runtime(self):
        return getattr(self._local, "runtime", None)

    @runtime.setter
    def runtime(self, value) -> None:
        self._local.runtime = value

    @property
    def owned_context(self):
        return getattr(self._local, "owned_context", None)

    @owned_context.setter
    def owned_context(self, value) -> None:
        self._local.owned_context = value

    @property
    def source_context(self):
        return getattr(self._local, "source_context", None)

    @source_context.setter
    def source_context(self, value) -> None:
        self._local.source_context = value

    @property
    def owns_context(self) -> bool:
        return bool(getattr(self._local, "owns_context", False))

    @owns_context.setter
    def owns_context(self, value: bool) -> None:
        self._local.owns_context = bool(value)

    def _open(self) -> None:
        if self.page is not None:
            return
        self.runtime, self.browser = self.connection_factory()
        contexts = getattr(self.browser, "contexts", ())
        if len(contexts) != 1:
            self.runtime.stop()
            self.runtime = self.browser = None
            raise RuntimeError("crowdworks_paid_browser_unavailable")
        try:
            self.source_context = contexts[0]
            self.owned_context = self.context_factory(self.browser, contexts[0])
            self.owns_context = self.owned_context is not contexts[0]
            if self._requires_isolation and self.owned_context is contexts[0]:
                raise RuntimeError("crowdworks_paid_browser_state_invalid")
            self.page = self.owned_context.new_page()
            self.page.set_default_timeout(15_000)
        except Exception as error:
            if (self.source_context is not None
                    and str(error) != "crowdworks_paid_browser_state_invalid"):
                try:
                    if self.owns_context and self.owned_context is not None:
                        self.owned_context.close()
                    self.owned_context = self.source_context
                    self.owns_context = False
                    self.page = self.source_context.new_page()
                    self.page.set_default_timeout(15_000)
                    return
                except Exception:
                    pass
            if self.owned_context is not None and self.owns_context:
                try: self.owned_context.close()
                except Exception: pass
            self.owned_context = None
            self.runtime.stop()
            self.runtime = self.browser = None
            raise

    def _fallback_to_source_context(self) -> bool:
        source = self.source_context
        if source is None or self.owned_context is source:
            return False
        try:
            if self.page is not None:
                self.page.close()
        except Exception:
            pass
        if self.owns_context and self.owned_context is not None:
            try:
                self.owned_context.close()
            except Exception:
                pass
        self.owned_context = source
        self.owns_context = False
        self.page = source.new_page()
        self.page.set_default_timeout(15_000)
        return True

    @staticmethod
    def _isolated_context(browser: Any, source_context: Any) -> Any:
        state = source_context.storage_state()
        if not isinstance(state, Mapping) or not isinstance(state.get("cookies"), list):
            raise RuntimeError("crowdworks_paid_browser_state_invalid")
        return browser.new_context(storage_state=json.loads(json.dumps(state)))

    @staticmethod
    def _goto(page: Any, url: str, stage: str) -> None:
        try:
            page.goto(url, wait_until="commit", timeout=20_000)
        except PlaywrightTimeoutError:
            raise _TIMEOUTS[stage]() from None

    def _goto_contract(self, work_id: str) -> None:
        self._open()
        if not re.fullmatch(r"\d+", work_id):
            raise RuntimeError("crowdworks_paid_work_invalid")
        url = f"https://crowdworks.jp/contracts/{work_id}"
        try:
            self._goto(self.page, url, "contract")
        except CrowdWorksPaidContractTimeout:
            context = self.owned_context
            if context is None:
                raise RuntimeError("crowdworks_paid_browser_state_invalid")
            self.page.close()
            self.page = context.new_page()
            self.page.set_default_timeout(15_000)
            self._goto(self.page, url, "contract")
        parsed = urlsplit(str(self.page.url))
        if (parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment) != (
                "https", "crowdworks.jp", f"/contracts/{work_id}", "", ""):
            raise RuntimeError("crowdworks_paid_contract_unavailable")

    def _switch_to_narrow_contract(self, work_id: str) -> None:
        """Clone auth into a short-lived mobile context without changing shared cookies."""
        source_context = self.owned_context
        if source_context is None:
            raise RuntimeError("crowdworks_paid_browser_unavailable")
        state = source_context.storage_state()
        if not isinstance(state, Mapping) or not isinstance(state.get("cookies"), list):
            raise RuntimeError("crowdworks_paid_browser_state_invalid")
        copied = json.loads(json.dumps(state))
        found_device = False
        for cookie in copied["cookies"]:
            if (isinstance(cookie, dict) and cookie.get("name") == "mobylette_device"
                    and str(cookie.get("domain") or "").lstrip(".") == "crowdworks.jp"):
                cookie["value"] = "sp"
                found_device = True
        mobile_context = self.browser.new_context(
            storage_state=copied, viewport={"width": 390, "height": 844}, is_mobile=True,
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
                        "Mobile/15E148 Safari/604.1"))
        try:
            if not found_device:
                mobile_context.add_cookies([{"name": "mobylette_device", "value": "sp",
                                             "domain": "crowdworks.jp", "path": "/",
                                             "secure": True, "sameSite": "None"}])
            mobile_page = mobile_context.new_page()
            mobile_page.set_default_timeout(15_000)
        except Exception:
            mobile_context.close()
            raise
        old_page = self.page
        old_owns_context = self.owns_context
        self.page = mobile_page
        self.owned_context = mobile_context
        self.owns_context = True
        if old_page is not None:
            try:
                old_page.close()
            except Exception:
                pass
        if old_owns_context:
            try:
                source_context.close()
            except Exception:
                pass
        self._goto_contract(work_id)

    @staticmethod
    def _row_from_list(raw: Mapping[str, Any]) -> dict[str, str]:
        work_id, title, client, status = (_text(raw.get(key)) for key in
                                          ("work_id", "title", "client", "provider_state"))
        if status not in {"funded", "awaiting_escrow", "delivered"}:
            raise RuntimeError("crowdworks_paid_contract_state_invalid")
        result: dict[str, Any] = {"work_id": work_id, "title": title, "client": client,
                                  "provider_state": status}
        for key in ("milestone_id", "form_url", "application_date", "message_thread_id",
                    "buyer_event_id", "buyer_event_at", "artifact_access", "artifact_content"):
            value = raw.get(key)
            if value is not None:
                result[key] = _text(value)
        document_urls = raw.get("document_urls")
        if document_urls is not None:
            if (not isinstance(document_urls, list)
                    or not all(isinstance(value, str) for value in document_urls)):
                raise RuntimeError("crowdworks_paid_task_unavailable")
            result["document_urls"] = sorted(set(document_urls))
        for key in ("artifact_required", "artifact_verified"):
            value = raw.get(key)
            if value is not None:
                if not isinstance(value, bool):
                    raise RuntimeError("crowdworks_paid_task_unavailable")
                result[key] = value
        form_urls = raw.get("form_urls")
        if form_urls is not None:
            if (not isinstance(form_urls, list)
                    or not all(isinstance(value, str) and _google_form_url(value) for value in form_urls)):
                raise RuntimeError("crowdworks_paid_task_unavailable")
            normalized_urls = sorted(set(form_urls))
            result["form_urls"] = normalized_urls
            result["form_url"] = result.get("form_url") if len(normalized_urls) == 1 else None
        return result

    def _list_contracts(self) -> list[dict[str, str]]:
        try:
            return self._list_contracts_once()
        except PlaywrightTimeoutError:
            if self._fallback_to_source_context():
                try:
                    return self._list_contracts_once()
                except PlaywrightTimeoutError:
                    pass
            raise CrowdWorksPaidActiveContractsTimeout() from None

    def _list_contracts_once(self) -> list[dict[str, str]]:
        self._open()
        self._goto(self.page, ACTIVE_CONTRACTS_URL, "active_contracts")
        parsed = urlsplit(str(self.page.url))
        if ((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)
                != ("https", "crowdworks.jp", "/e/contracts", "status=active", "")):
            raise RuntimeError("crowdworks_paid_contract_source_unavailable")
        links = self.page.locator('a[href^="/contracts/"]')
        links.nth(0).wait_for(state="attached", timeout=20_000)
        values = links.evaluate_all(
            """nodes => nodes.map(a => { const row=a.closest('tr'); return {
              href:a.getAttribute('href'), title:a.innerText.trim(), row:row?.innerText.trim() || ''
            }}).filter(x => x.href && x.title && x.row)"""
        )
        if not isinstance(values, list):
            raise RuntimeError("crowdworks_paid_contract_source_unavailable")
        result: list[dict[str, str]] = []
        for value in values:
            if not isinstance(value, Mapping):
                raise RuntimeError("crowdworks_paid_contract_source_unavailable")
            match = re.fullmatch(r"/contracts/(\d+)", str(value.get("href") or ""))
            row = _text(value.get("row"), "crowdworks_paid_contract_source_unavailable")
            if match is None:
                raise RuntimeError("crowdworks_paid_contract_source_unavailable")
            state = ("funded" if "進行中" in row else "awaiting_escrow" if "仮払い待ち" in row
                     else "delivered" if "検収中" in row or "納品済み" in row else "")
            parts = [part.strip() for part in re.split(r"[\t\r\n]+", row) if part.strip()]
            if not state or len(parts) < 3:
                raise RuntimeError("crowdworks_paid_contract_state_invalid")
            result.append({"work_id": match.group(1), "title": _text(value.get("title")),
                           "client": parts[0], "provider_state": state})
        if not result:
            raise RuntimeError("crowdworks_paid_contract_source_unavailable")
        if len({row["work_id"] for row in result}) != len(result):
            raise RuntimeError("crowdworks_paid_contract_duplicate")
        return result

    def _detail(self, basic: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self._detail_once(basic)
        except PlaywrightTimeoutError:
            context = self.owned_context
            if context is None:
                raise CrowdWorksPaidContractTimeout() from None
            self.page.close()
            self.page = context.new_page()
            self.page.set_default_timeout(15_000)
            try:
                return self._detail_once(basic)
            except PlaywrightTimeoutError:
                try:
                    self._switch_to_narrow_contract(_text(basic.get("work_id")))
                    return self._detail_once(basic)
                except (PlaywrightTimeoutError, CrowdWorksPaidContractTimeout):
                    raise CrowdWorksPaidContractTimeout() from None

    def _detail_once(self, basic: Mapping[str, Any]) -> dict[str, Any]:
        work_id = _text(basic.get("work_id"))
        self._goto_contract(work_id)
        self._expand_folded_messages()
        body = _text(self.page.locator("body").inner_text(), "crowdworks_paid_contract_unavailable")
        buyer_event = self._latest_buyer_event(work_id) or {}
        title, client = (_text(basic.get(key)) for key in ("title", "client"))
        if title not in body or client not in body:
            raise RuntimeError("crowdworks_paid_contract_context_invalid")
        inspection_pending = ("クライアント（発注者）が検収を行っています" in body
                              and "検収完了まで" in body)
        state = ("delivered" if inspection_pending else
                 "funded" if "業務を開始しています" in body else
                 "awaiting_escrow" if "仮払いを行っています" in body and "業務を開始しない" in body else
                 "delivered" if any(token in body for token in ("納品済み", "納品完了")) else "")
        if not state:
            raise RuntimeError("crowdworks_paid_contract_state_changed")
        if state == "awaiting_escrow":
            return {"work_id": work_id, "title": title, "client": client, "provider_state": state,
                    "milestone_id": None, "form_url": None, "proposal_id": None,
                    "application_date": None, "buyer_context": body}
        if state == "delivered":
            if inspection_pending:
                return {"work_id": work_id, "title": title, "client": client,
                        "provider_state": state, "milestone_id": None,
                        "form_url": None, "proposal_id": None,
                        "application_date": None, "buyer_context": body}
            forms = self.page.locator('form[action^="/milestones/"][action$="/complete"]')
            if forms.count() or not any(token in body for token in ("納品済み", "納品完了")):
                raise RuntimeError("crowdworks_paid_contract_state_changed")
            return {"work_id": work_id, "title": title, "client": client, "provider_state": state,
                    "milestone_id": None, "form_url": None, "proposal_id": None,
                    "application_date": None, "buyer_context": body}
        forms = self.page.locator('form[action^="/milestones/"][action$="/complete"]')
        actions = {str(forms.nth(i).get_attribute("action") or "") for i in range(forms.count())}
        match = re.fullmatch(r"/milestones/(\d+)/complete", actions.pop()) if len(actions) == 1 else None
        proposal_ids = sorted({found.group(1) for href in self.page.locator('a[href]').evaluate_all(
            "nodes => nodes.map(a => a.getAttribute('href')).filter(Boolean)") if isinstance(href, str)
                               for found in [re.match(r"^/proposals/(\d+)(?:/|$)", href)] if found})
        proposal_id = proposal_ids[0] if len(proposal_ids) == 1 else None
        links = self.page.locator('a[href]').evaluate_all("nodes => nodes.map(a => a.href).filter(Boolean)")
        form_urls = sorted({link for link in links if isinstance(link, str) and _google_form_url(link)})
        document_urls = sorted({link for link in links if isinstance(link, str) and self._document_url(link)})
        artifact = self._document_access(document_urls)
        application_date = basic.get("application_date") if basic.get("proposal_id") == proposal_id else None
        if application_date is None and proposal_id is not None and form_urls:
            application_date = self._proposal_application_date(proposal_id)
        if application_date is None and proposal_id is not None and form_urls:
            application_date = self._receipt_application_date(title, proposal_id)
        if match is None:
            raise RuntimeError("crowdworks_paid_task_unavailable")
        return {"work_id": work_id, "title": title, "client": client, "provider_state": state,
                "milestone_id": match.group(1), "form_urls": form_urls,
                "form_url": form_urls[0] if len(form_urls) == 1 else None,
                "proposal_id": proposal_id, "application_date": application_date,
                "buyer_context": body, **buyer_event,
                "document_urls": document_urls, **artifact}

    @staticmethod
    def _message_datetime(value: str) -> str | None:
        match = re.fullmatch(r"\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})\s*", value)
        if match is None:
            return None
        try:
            stamp = datetime(*(int(part) for part in match.groups()), tzinfo=ZoneInfo("Asia/Tokyo"))
        except ValueError:
            return None
        return stamp.isoformat()

    def _latest_buyer_event(self, work_id: str | None = None) -> dict[str, str] | None:
        if self.page is None:
            return None
        try:
            thread_id, messages = self._message_api(work_id)
            buyer = [message for message in messages or []
                     if isinstance(message, Mapping) and message.get("own_message") is False
                     and isinstance(message.get("id"), int) and not isinstance(message.get("id"), bool)]
            if not buyer:
                return None
            latest = max(buyer, key=lambda message: int(message["id"]))
            sent_at = self._message_datetime(str(latest.get("senddate") or ""))
            if sent_at is None:
                return None
            return {"message_thread_id": str(thread_id), "buyer_event_id": str(latest["id"]),
                    "buyer_event_at": sent_at}
        except Exception:
            return None

    def _message_api(self, work_id: str | None = None) -> tuple[int, list[Mapping[str, Any]]]:
        if self.page is None:
            raise RuntimeError("crowdworks_paid_message_thread_unavailable")
        root = self.page.locator("#pack-message-thread")
        raw = root.get_attribute("data")
        config = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        thread_id = config.get("id")
        messageable_id = config.get("messageableId")
        if (not isinstance(thread_id, int) or isinstance(thread_id, bool)
                or (work_id is not None and str(messageable_id) != str(work_id))):
            raise RuntimeError("crowdworks_paid_message_thread_invalid")
        response = self.page.evaluate(
            """async (id) => { const response = await fetch(`/message/threads/${id}/messages.json`, {credentials: 'same-origin'}); return {status: response.status, body: await response.text()}; }""",
            thread_id,
        )
        if not isinstance(response, Mapping) or response.get("status") != 200:
            raise RuntimeError("crowdworks_paid_message_thread_unavailable")
        payload = json.loads(str(response.get("body") or ""))
        messages = payload.get("messages") if isinstance(payload, Mapping) else None
        if not isinstance(messages, list):
            raise RuntimeError("crowdworks_paid_message_thread_invalid")
        return thread_id, [message for message in messages if isinstance(message, Mapping)]

    def _latest_seller_message(self, work_id: str | None = None) -> Mapping[str, Any] | None:
        _, messages = self._message_api(work_id)
        seller = [message for message in messages
                  if message.get("own_message") is True and isinstance(message.get("id"), int)
                  and not isinstance(message.get("id"), bool)]
        return max(seller, key=lambda message: int(message["id"])) if seller else None

    def _seller_message_contains(self, work_id: str, buyer_event_id: str, body: str) -> bool:
        if not buyer_event_id.isdigit():
            return False
        _, messages = self._message_api(work_id)
        return any(
            message.get("own_message") is True
            and isinstance(message.get("id"), int)
            and int(message["id"]) > int(buyer_event_id)
            and body in str(message.get("body") or "")
            for message in messages
        )

    @staticmethod
    def _document_url(value: str) -> bool:
        parsed = urlsplit(value)
        return (parsed.scheme, parsed.netloc) == ("https", "docs.google.com") and "/document/" in parsed.path

    def _document_access(self, urls: list[str]) -> dict[str, Any]:
        if not urls or self.owned_context is None:
            return {"artifact_required": bool(urls), "artifact_access": "unknown" if urls else None,
                    "artifact_verified": False}
        permission_seen = False
        unknown_seen = False
        readable: list[str] = []
        for url in urls:
            page = self.owned_context.new_page()
            try:
                page.goto(url, wait_until="commit", timeout=20_000)
                body = str(page.locator("body").inner_text() or "")
                if "編集権限をリクエスト" in body:
                    permission_seen = True
                    continue
                # A Google Docs shell, login page, or error page can have body
                # text without exposing the document.  Require a visible Docs
                # editor/page surface before treating the artifact as readable.
                for selector in (".kix-appview-editor", ".kix-page",
                                 '[role="textbox"][aria-label*="Document content"]'):
                    try:
                        surface = page.locator(selector)
                        if surface.count() < 1:
                            continue
                        visible = [surface.nth(index) for index in range(surface.count())
                                   if surface.nth(index).is_visible()]
                        if not visible:
                            continue
                        content = "\n".join(str(item.inner_text() or "") for item in visible).strip()
                        if content:
                            readable.append(f"[{url}]\n{content}")
                            break
                    except Exception:
                        continue
                else:
                    unknown_seen = True
            except Exception:
                unknown_seen = True
                continue
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        if permission_seen:
            return {"artifact_required": True, "artifact_access": "permission_required",
                    "artifact_verified": False}
        if unknown_seen:
            return {"artifact_required": True, "artifact_access": "unknown", "artifact_verified": False}
        if readable:
            combined = "\n\n".join(readable)
            if len(combined) > 12_000:
                return {"artifact_required": True, "artifact_access": "unknown", "artifact_verified": False}
            return {"artifact_required": True, "artifact_access": "readable",
                    "artifact_content": combined, "artifact_verified": False}
        return {"artifact_required": True, "artifact_access": "unknown", "artifact_verified": False}

    def _expand_folded_messages(self) -> None:
        if self.page is None:
            return
        finder = getattr(self.page, "get_by_text", None)
        if not callable(finder):
            return
        try:
            folded = finder(re.compile(r"他の\d+件のメッセージを表示"), exact=False)
            initial_count = folded.count()
        except Exception as error:
            raise RuntimeError("crowdworks_paid_message_context_incomplete") from error
        attempts = 0
        while True:
            try:
                remaining = folded.count()
                visible = [folded.nth(index) for index in range(remaining)
                           if folded.nth(index).is_visible()]
            except Exception as error:
                raise RuntimeError("crowdworks_paid_message_context_incomplete") from error
            if not visible:
                return
            attempts += 1
            if attempts > max(initial_count * 2, 8):
                raise RuntimeError("crowdworks_paid_message_context_incomplete")
            try:
                visible[0].click()
                self.page.wait_for_timeout(300)
            except Exception as error:
                raise RuntimeError("crowdworks_paid_message_context_incomplete") from error

    def _proposal_application_date(self, proposal_id: str) -> str | None:
        if self.owned_context is None:
            raise RuntimeError("crowdworks_paid_browser_state_invalid")
        proposal = self.owned_context.new_page()
        try:
            try:
                self._goto(proposal, f"https://crowdworks.jp/proposals/{proposal_id}", "proposal")
            except CrowdWorksPaidProposalTimeout:
                return None
            route = urlsplit(str(proposal.url))
            if (route.scheme, route.netloc, route.path, route.query, route.fragment) != (
                    "https", "crowdworks.jp", f"/proposals/{proposal_id}", "", ""):
                return None
            body = _text(proposal.locator("body").inner_text(), "crowdworks_paid_proposal_unavailable")
            matched = re.search(r"(?:応募日時|応募日)\s*[：:]?\s*(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", body)
            if matched is None:
                return None
            try:
                return datetime(*(int(value) for value in matched.groups())).date().isoformat()
            except ValueError:
                return None
        finally:
            proposal.close()

    def _receipt_application_date(self, title: str, proposal_id: str) -> str | None:
        """Use only one exact verified official Apply receipt as a proposal-date fallback."""
        matches = []
        try:
            lines = self.application_receipts_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return None
        except OSError:
            raise RuntimeError("crowdworks_paid_application_receipt_unavailable") from None
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                raise RuntimeError("crowdworks_paid_application_receipt_invalid") from None
            if not isinstance(row, Mapping):
                raise RuntimeError("crowdworks_paid_application_receipt_invalid")
            if (row.get("record_type") != "application_receipt" or row.get("platform") != "crowdworks"
                    or row.get("status") != "verified" or row.get("opportunity_title") != title
                    or row.get("application_external_id") != proposal_id):
                continue
            opportunity_id = row.get("opportunity_external_id")
            observed_at = row.get("observed_at")
            if (not isinstance(opportunity_id, str) or not re.fullmatch(r"\d+", opportunity_id)
                    or not isinstance(observed_at, str)):
                raise RuntimeError("crowdworks_paid_application_receipt_invalid")
            try:
                stamp = datetime.fromisoformat(observed_at)
                if stamp.tzinfo is None:
                    raise ValueError
            except ValueError:
                raise RuntimeError("crowdworks_paid_application_receipt_invalid") from None
            matches.append(stamp.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat())
        return matches[0] if len(matches) == 1 else None

    def _observation(self, item: Mapping[str, Any]) -> dict[str, str]:
        stable = {key: item.get(key) for key in ("work_id", "title", "client", "provider_state",
                                                  "milestone_id", "form_url", "form_urls", "proposal_id",
                                                  "application_date", "buyer_context", "message_thread_id",
                                                  "buyer_event_id", "buyer_event_at", "form_candidates",
                                                  "ignored_form_urls", "document_urls", "artifact_required",
                                                  "artifact_access", "artifact_content", "artifact_verified")}
        stable["completed_form_urls"] = sorted(item.get("completed_form_urls") or [])
        observed = {"provider": "crowdworks", "account_id": self.account_id,
                    "work_id": _text(item.get("work_id")), "latest_event_id": _digest(stable),
                    "provider_state": _text(item.get("provider_state")), "observed_at": _now()}
        for field in ("message_thread_id", "buyer_event_id", "buyer_event_at"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                observed[field] = value.strip()
        return observed

    def _cache_replace(self, items: list[Mapping[str, Any]]) -> None:
        snapshot = { _text(item.get("work_id")): self._with_form_progress(item) for item in items }
        with self._cache_lock:
            self._contract_cache = snapshot

    def _cache_update(self, item: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self._with_form_progress(item); work_id = _text(normalized.get("work_id"))
        with self._cache_lock:
            self._contract_cache[work_id] = normalized
        return dict(normalized)

    def _completed_form_urls(self, item: Mapping[str, Any]) -> list[str]:
        if self.state_path is None:
            return []
        urls = item.get("form_urls")
        if not isinstance(urls, list):
            url = item.get("form_url")
            urls = [url] if isinstance(url, str) else []
        completed = []
        for url in urls:
            if not isinstance(url, str) or not _google_form_url(url):
                continue
            try:
                digest = hashlib.sha256(url.encode()).hexdigest()
                if google_form.has_confirmed_bound_receipt(
                        self.state_path, self._form_binding(item, digest)):
                    completed.append(url)
            except RuntimeError as error:
                if str(error) == "google_form_submission_uncertain":
                    raise
            except Exception:
                continue
        return sorted(set(completed))

    def _with_form_progress(self, item: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        if normalized.get("form_urls") or normalized.get("form_url"):
            normalized["completed_form_urls"] = self._completed_form_urls(normalized)
        return normalized

    def _cached_item(self, work_id: str) -> dict[str, Any] | None:
        with self._cache_lock:
            value = self._contract_cache.get(work_id)
            return dict(value) if value is not None else None

    def _inventory_rows(self) -> list[dict[str, Any]]:
        if self.inventory_reader is None:
            return self._list_contracts()
        snapshot = self.inventory_reader()
        if (not isinstance(snapshot, Mapping) or snapshot.get("ok") is not True
                or snapshot.get("source_complete") is not True
                or not isinstance(snapshot.get("contract_candidates"), list)):
            raise RuntimeError("crowdworks_paid_inventory_unavailable")
        details = [self._row_from_list(row) for row in snapshot["contract_candidates"] if isinstance(row, Mapping)]
        if len(details) != len(snapshot["contract_candidates"]):
            raise RuntimeError("crowdworks_paid_inventory_unavailable")
        return details

    def _inventory(self) -> list[dict[str, Any]]:
        rows = self._inventory_rows()
        if self.inventory_reader is not None:
            details = rows
        else:
            details = []
            for row in rows:
                try:
                    details.append(self._detail(row))
                except CrowdWorksPaidContractTimeout:
                    details.append({**row, "detail_unavailable": True})
        self._cache_replace(details)
        return [self._observation(item) for item in details]

    def _targeted_detail(self, work_id: str) -> dict[str, Any]:
        """Refresh exactly one contract, reusing only immutable pure data as a hint."""
        basic = self._cached_item(work_id)
        if self.inventory_reader is not None:
            matches = [item for item in self._inventory_rows() if item["work_id"] == work_id]
            if len(matches) != 1:
                raise RuntimeError("crowdworks_paid_work_unavailable")
            return self._cache_update(matches[0])
        if basic is None:
            matches = [item for item in self._list_contracts() if item["work_id"] == work_id]
            if len(matches) != 1:
                raise RuntimeError("crowdworks_paid_work_unavailable")
            basic = matches[0]
        return self._cache_update(self._detail(basic))

    def observe_active(self) -> list[dict[str, Any]]:
        try:
            return self._inventory()
        finally:
            # Worker threads independently re-observe their work item; the
            # inventory thread never lends its CDP page to them.
            self.close()

    def observe_one(self, work_id: str) -> dict[str, Any]:
        try:
            if self.inventory_reader is None:
                cached = self._cached_item(work_id)
                if cached is not None:
                    return self._observation(cached)
            return self._observation(self._targeted_detail(work_id))
        finally:
            self.close()

    def refresh_one(self, work_id: str) -> dict[str, Any]:
        try:
            return self._observation(self._targeted_detail(work_id))
        finally:
            self.close()

    def _form_candidates(self, urls: list[str]) -> list[dict[str, str]]:
        if self.owned_context is None:
            return []
        candidates: list[dict[str, str]] = []
        for url in urls:
            page = self.owned_context.new_page()
            try:
                page.set_default_timeout(15_000)
                page.goto(url, wait_until="commit", timeout=20_000)
                body = _text(page.locator("body").inner_text(), "crowdworks_paid_form_unavailable")
                if len(body) > 12_000:
                    return []
                candidates.append({"url": url, "title": page.title(), "body": body})
            except Exception:
                return []
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        return candidates

    def _correction_ready(self, item: Mapping[str, Any], url: str) -> bool:
        if self.state_path is None:
            return False
        event_id = item.get("buyer_event_id")
        event_at = item.get("buyer_event_at")
        if (not isinstance(event_id, str) or not event_id.isdigit()
                or not isinstance(event_at, str)):
            return False
        try:
            event_stamp = datetime.fromisoformat(event_at)
            digest = hashlib.sha256(url.encode()).hexdigest()
            receipts = google_form.confirmed_bound_receipts(
                self.state_path, self._form_binding(item, digest))
        except (RuntimeError, ValueError, TypeError):
            return False
        if not receipts:
            return False
        latest = max(receipts, key=lambda receipt: str(receipt.get("observed_at") or ""))
        binding = latest.get("binding")
        previous_event = binding.get("revision_event_id") if isinstance(binding, Mapping) else None
        if not isinstance(previous_event, str):
            previous_event = binding.get("buyer_event_id") if isinstance(binding, Mapping) else None
        if isinstance(previous_event, str) and previous_event.isdigit():
            return int(event_id) > int(previous_event)
        try:
            observed_at = datetime.fromisoformat(str(latest.get("observed_at") or "").replace("Z", "+00:00"))
        except ValueError:
            return False
        return event_stamp > observed_at

    def _select_form_url(self, item: Mapping[str, Any]) -> str | None:
        raw_urls = item.get("form_urls")
        candidates = item.get("form_candidates")
        if (not isinstance(raw_urls, list) and isinstance(item.get("form_url"), str)):
            raw_urls = [item["form_url"]]
        if not isinstance(raw_urls, list):
            return None
        completed = set(item.get("completed_form_urls") or [])
        urls = [url for url in raw_urls if isinstance(url, str)
                and (url not in completed or self._correction_ready(item, url))]
        if not urls:
            return FORM_SELECTION_COMPLETE
        if not isinstance(candidates, list):
            return None
        candidates = [candidate for candidate in candidates
                      if isinstance(candidate, Mapping) and candidate.get("url") in raw_urls]
        if (not all(isinstance(url, str) and _google_form_url(url) for url in raw_urls)
                or len(candidates) != len(raw_urls)):
            return None
        if self.candidate_profile is None or self.provider_profile is None or self.state_path is None:
            return None
        try:
            grounding = grounding_module.build_reply_grounding(
                candidate_profile_path=self.candidate_profile,
                provider_profile=self.provider_profile,
            )
            source = "契約本文:\n" + str(item.get("buyer_context") or "")
            if completed:
                source += "\n\n既に確認済みのフォーム（買い手が不備を指摘した場合だけ再提出可能）:\n"
                source += "\n".join(sorted(completed))
            source += "\n\n" + "\n\n".join(
                f"URL: {candidate.get('url')}\nタイトル: {candidate.get('title')}\n本文:\n{candidate.get('body')}"
                for candidate in candidates if isinstance(candidate, Mapping)
            )
            value = composer.compose({
                "board": {"title": item.get("title", "")},
                "grounding": grounding,
                "conversation": [{"role": "buyer", "body": source}],
                "action_contract": {
                    "kind": "required_form_field",
                    "question": "契約の依頼内容に対して実施すべき公式GoogleフォームのURLを1つ選んでください。",
                    "allowed_choices": [*urls, FORM_SELECTION_COMPLETE],
                },
                "provider_rules": {"outside_contact_before_approval": "forbidden"},
            }, state_root=self.state_path / "compose", task_label="crowdworks-paid-form-selection")
        except Exception:
            return None
        selected = value.strip() if isinstance(value, str) else None
        if selected in completed:
            item["form_revision"] = True
        if selected == FORM_SELECTION_COMPLETE:
            item["ignored_form_urls"] = sorted(urls)
        return selected if selected in [*urls, FORM_SELECTION_COMPLETE] else None

    def _compose_answer(self, item: Mapping[str, Any]) -> str | None:
        buyer_context = item.get("buyer_context")
        if (not isinstance(buyer_context, str) or not buyer_context.strip()
                or self.candidate_profile is None or self.provider_profile is None
                or self.state_path is None):
            return None
        try:
            grounding = grounding_module.build_reply_grounding(
                candidate_profile_path=self.candidate_profile,
                provider_profile=self.provider_profile,
            )
            conversation = buyer_context
            if item.get("artifact_access") == "permission_required":
                conversation += (
                    "\n\n【リンクのアクセス結果】編集権限をリクエストする画面で閲覧できません。"
                    "権限付与または本文の貼付を依頼し、作業完了は主張しないでください。"
                )
            elif item.get("artifact_access") == "readable" and isinstance(item.get("artifact_content"), str):
                conversation += "\n\n【リンク先本文】\n" + item["artifact_content"]
            body = composer.compose({
                "board": {"title": item.get("title", "")},
                "grounding": grounding,
                "conversation": [{"role": "buyer", "body": conversation}],
                "action_contract": {
                    "kind": "contract_answer",
                    "question": (
                        "契約済みの買い手の依頼に対して、次に必要な回答を作成してください。"
                        "契約本文に編集権限の要求、アクセス不可、または本文不足がある場合は、"
                        "作業完了を主張せず、閲覧権限の付与または本文の貼付を依頼する回答だけを作成してください。"
                        "リンク先本文が読める場合は、その内容に基づく依頼されたフィードバックだけを作成し、"
                        "未実施の作業や未確認の成果を完了したと書かないでください。"
                    ),
                    "allowed_choices": [],
                },
                "provider_rules": {"outside_contact_before_approval": "forbidden"},
            }, state_root=self.state_path / "compose", task_label="crowdworks-paid-answer")
        except Exception:
            return None
        return body.strip() if isinstance(body, str) and body.strip() else None

    def _quality_check(self, item: Mapping[str, Any], body: str) -> str | None:
        """Ask a fresh model judgment whether the proposed answer fulfills the request."""
        buyer_context = item.get("buyer_context")
        if (not isinstance(buyer_context, str) or not buyer_context.strip()
                or self.candidate_profile is None or self.provider_profile is None
                or self.state_path is None):
            return None
        source = "買い手の会話全文:\n" + buyer_context
        artifact = item.get("artifact_content")
        if isinstance(artifact, str) and artifact.strip():
            source += "\n\nリンク先で読めた本文:\n" + artifact
        source += "\n\n送信予定の回答:\n" + body
        try:
            return self._compose_text(
                question=(
                    "この回答は買い手の依頼を実際に満たしているか判定してください。"
                    "依頼の具体的な要求への回答、リンク先の内容に基づく作業、"
                    "未実施の作業を完了と偽らないことを確認し、"
                    "quality_ok、quality_needs_rework、buyer_input_required のいずれか1語だけを返してください。"
                ),
                source=source,
                item=item,
                choices=["quality_ok", "quality_needs_rework", "buyer_input_required"],
            )
        except Exception:
            return None

    def context(self, work_id: str) -> dict[str, Any]:
        try:
            item = self._cached_item(work_id) or self._targeted_detail(work_id)
            urls = item.get("form_urls")
            if (not isinstance(urls, list) and isinstance(item.get("form_url"), str)):
                urls = [item["form_url"]]
                item = {**item, "form_urls": urls}
            if (isinstance(urls, list) and urls
                    and not isinstance(item.get("form_candidates"), list)):
                try:
                    if self.owned_context is None:
                        self._open()
                    candidates = self._form_candidates(urls)
                except Exception:
                    candidates = []
                if candidates:
                    item = self._cache_update({**item, "form_candidates": candidates})
            return {"contract": dict(item), "delivery": {
                "formal_delivery_authorized": item["provider_state"] == "funded",
                "form_required": bool(item.get("form_urls") or item.get("form_url")),
            }}
        finally:
            self.close()

    def _receipt_path(self, form_sha256: str) -> Path:
        if self.state_path is None:
            raise RuntimeError("crowdworks_paid_state_unavailable")
        return google_form.receipt_path(self.state_path, form_sha256)

    def _form_items(self, page: Any) -> list[dict[str, Any]]:
        raw = page.evaluate("window.FB_PUBLIC_LOAD_DATA_ && window.FB_PUBLIC_LOAD_DATA_[1][1]")
        if not isinstance(raw, list):
            raise RuntimeError("crowdworks_paid_form_metadata_invalid")
        items = []
        for value in raw:
            if not isinstance(value, list) or len(value) < 5 or not isinstance(value[1], str):
                continue
            entries = []
            for entry in value[4] if isinstance(value[4], list) else []:
                if not isinstance(entry, list) or not entry or not isinstance(entry[0], int):
                    continue
                choices = [choice[0] for choice in entry[1] if isinstance(choice, list) and choice and isinstance(choice[0], str)] if len(entry) > 1 and isinstance(entry[1], list) else []
                entries.append({"id": entry[0], "required": bool(entry[2]) if len(entry) > 2 else False, "choices": choices})
            if entries:
                items.append({"title": value[1].strip(), "type": value[3], "entries": entries})
        if not items:
            raise RuntimeError("crowdworks_paid_form_metadata_invalid")
        return items

    def _compose_text(self, *, question: str, source: str, item: Mapping[str, Any],
                      choices: list[str] | None = None) -> str:
        if self.candidate_profile is None or self.provider_profile is None or self.state_path is None:
            raise RuntimeError("crowdworks_paid_form_profile_unavailable")
        grounding = grounding_module.build_reply_grounding(candidate_profile_path=self.candidate_profile,
                                                           provider_profile=self.provider_profile)
        body = composer.compose({"board": {"title": item["title"]}, "grounding": grounding,
            "conversation": [{"role": "buyer", "body": "契約済み業務のGoogleフォームに記載する文章を作成してください。設問: " + question + "\n業務説明: " + source}],
            "action_contract": {"kind": "required_form_field", "question": question,
                                "allowed_choices": list(choices or [])},
            "provider_rules": {"outside_contact_before_approval": "forbidden"}},
            state_root=self.state_path / "compose", task_label="crowdworks-paid-form")
        if not isinstance(body, str) or not body.strip():
            raise RuntimeError("crowdworks_paid_form_composition_unavailable")
        value = body.strip()
        if choices and value not in choices:
            raise RuntimeError("crowdworks_paid_form_choice_invalid")
        return value

    def _form_fields(self, page: Any, item: Mapping[str, Any]) -> list[tuple[str, str]]:
        started = time.monotonic()
        source = _text(page.locator("body").inner_text(), "crowdworks_paid_form_unavailable")
        provider = self.provider_profile or {}
        result: list[tuple[str, str]] = []
        for question in self._form_items(page):
            entry = question["entries"][0]
            if not entry["required"]:
                continue
            title, choices = question["title"], entry["choices"]
            if choices:
                value = choices[0] if len(choices) == 1 else self._compose_text(
                    question=title, source=source, item=item, choices=choices)
            elif "登録名" in title:
                value = _text(provider.get("display_name"), "crowdworks_paid_form_profile_unavailable")
            elif "やり取り" in title and "リンク" in title:
                value = f"https://crowdworks.jp/contracts/{item['work_id']}"
            elif question["type"] == 9:
                try:
                    stamp = datetime.fromisoformat(_text(item.get("application_date"))).date()
                except ValueError:
                    raise RuntimeError("crowdworks_paid_form_date_unknown") from None
                result.extend([(f"entry.{entry['id']}_year", str(stamp.year)), (f"entry.{entry['id']}_month", str(stamp.month)), (f"entry.{entry['id']}_day", str(stamp.day))])
                continue
            elif "時間" in title and "分" in title:
                value = str(math.ceil((time.monotonic() - started) / 60))
            else:
                value = self._compose_text(question=title, source=source, item=item)
            result.append((f"entry.{entry['id']}", value))
        return result

    def _submit_form_once(self, item: Mapping[str, Any]) -> Mapping[str, Any]:
        form_url = _text(item.get("form_url")); form_sha256 = hashlib.sha256(form_url.encode()).hexdigest()
        if self.state_path is None:
            raise RuntimeError("crowdworks_paid_state_unavailable")
        return google_form.submit_once(
            context=self.owned_context, state_root=self.state_path, url=form_url, url_sha256=form_sha256,
            answer_fields=lambda page: self._form_fields(page, item),
            binding=self._form_binding(item, form_sha256, include_buyer_event=True),
        )

    def _form_binding(self, item: Mapping[str, Any], form_sha256: str,
                      *, include_buyer_event: bool = False) -> dict[str, str]:
        binding = {"provider": "crowdworks", "account_id": self.account_id,
                   "contract_id": _text(item.get("work_id")), "milestone_id": _text(item.get("milestone_id")),
                   "form_revision_sha256": form_sha256}
        if include_buyer_event:
            buyer_event = item.get("buyer_event_id")
            if isinstance(buyer_event, str) and buyer_event.strip():
                binding["buyer_event_id"] = buyer_event.strip()
        revision_event = item.get("form_revision_event_id")
        if isinstance(revision_event, str) and revision_event.strip():
            binding["revision_event_id"] = revision_event.strip()
        return binding

    def _fill_delivery_message(self, value: str, form: Any | None = None) -> None:
        """Prime CrowdWorks' duplicate message fields before enabling delivery submit."""
        areas = self.page.locator('textarea[name="message[body]"]')
        filled = False
        for index in range(areas.count()):
            try:
                area = areas.nth(index)
                visible = area.is_visible()
            except (AttributeError, TypeError):
                continue
            if visible:
                area.fill(value)
                for event in ("input", "change"):
                    try:
                        area.dispatch_event(event)
                    except AttributeError:
                        pass
                filled = True
        if not filled and form is not None:
            form.locator('textarea[name="message[body]"]').fill(value)

    def _complete_once(self, item: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        self._goto_contract(_text(item.get("work_id")))
        selector = f'form[action="/milestones/{_text(payload.get("milestone_id"))}/complete"]'
        def visible_forms():
            forms = self.page.locator(selector)
            return [forms.nth(index) for index in range(forms.count())
                    if forms.nth(index).locator('textarea[name="message[body]"]').is_visible()]

        visible = visible_forms()
        if not visible:
            dialog = self.page.locator(
                f'a[href="#message-dialog-completion-{_text(payload.get("milestone_id"))}"]:visible')
            if dialog.count() == 1:
                try:
                    dialog.click(no_wait_after=True)
                except TypeError:
                    dialog.click()
                self.page.locator(
                    f'{selector} textarea[name="message[body]"]:visible').wait_for(
                    state="visible", timeout=15_000)
                visible = visible_forms()
        if not visible:
            def visible_todo_tabs():
                tabs = self.page.get_by_text("やること", exact=True)
                return [tabs.nth(index) for index in range(tabs.count()) if tabs.nth(index).is_visible()]

            visible_tabs = visible_todo_tabs()
            if not visible_tabs:
                # Server-rendered mobile navigation depends on both the device
                # cookie and user agent.  Use an isolated cloned context so the
                # shared authenticated browser remains unchanged.
                self._switch_to_narrow_contract(_text(item.get("work_id")))
                visible = visible_forms()
                visible_tabs = visible_todo_tabs() if not visible else []
            if visible:
                pass
            elif len(visible_tabs) != 1:
                raise RuntimeError("crowdworks_paid_todo_surface_unavailable")
            else:
                visible_tabs[0].click()
                self.page.locator(f'{selector} textarea[name="message[body]"]:visible').wait_for(
                    state="visible", timeout=15_000)
                visible = visible_forms()
        if len(visible) != 1:
            raise RuntimeError("crowdworks_paid_milestone_unavailable")
        form = visible[0]
        self._fill_delivery_message(
            str(payload.get("message") or
                "Googleフォームへの回答を完了しました。ご確認のほどよろしくお願いいたします。"),
            form)
        # The official form has duplicate milestone forms in the DOM.  Fence the
        # effect to the selected milestone's named submit control, rather than a
        # same-looking generic submit input.
        submit = form.locator('input[name="commit"][type="submit"][value="納品完了報告をする"]')
        if submit.count() != 1 or submit.is_disabled():
            raise RuntimeError("crowdworks_paid_milestone_submit_unavailable")
        try:
            submit.click()
            self.page.wait_for_load_state("domcontentloaded", timeout=20_000)
        except PlaywrightTimeoutError:
            raise CrowdWorksPaidMilestoneTimeout() from None

    def mutate(self, intent: dict[str, Any]) -> None:
        try:
            if intent.get("action") == "answer":
                payload = intent.get("payload")
                if not isinstance(payload, Mapping):
                    raise RuntimeError("crowdworks_paid_answer_invalid")
                body = _text(payload.get("body"))
                work_id = _text(intent.get("work_id"))
                current = self._targeted_detail(work_id)
                if current.get("provider_state") != "funded":
                    raise RuntimeError("crowdworks_paid_context_changed")
                if (not isinstance(payload.get("buyer_event_id"), str)
                        or payload.get("buyer_event_id") != current.get("buyer_event_id")):
                    raise RuntimeError("crowdworks_paid_context_changed")
                if current.get("artifact_access") != "permission_required":
                    quality_sha256 = payload.get("quality_sha256")
                    if (payload.get("correct_work_verified") is not True
                            or payload.get("quality_verdict") != "quality_ok"
                            or not isinstance(quality_sha256, str)
                            or not re.fullmatch(r"[0-9a-f]{64}", quality_sha256)
                            or quality_sha256 != _digest({
                                "buyer_context": current.get("buyer_context"),
                                "artifact_content": current.get("artifact_content"),
                                "body": body,
                            })):
                        raise RuntimeError("crowdworks_paid_answer_quality_unverified")
                elif body != PERMISSION_REQUEST_BODY:
                    raise RuntimeError("crowdworks_paid_answer_quality_unverified")
                self._goto_contract(work_id)
                areas = self.page.locator('textarea[name="message[body]"]')
                visible = [areas.nth(index) for index in range(areas.count())
                           if areas.nth(index).is_visible()]
                if len(visible) != 1:
                    raise RuntimeError("crowdworks_paid_message_composer_unavailable")
                visible[0].fill(body)
                button = self.page.get_by_role("button", name="メッセージを投稿する", exact=True)
                if button.count() != 1 or not button.is_visible() or not button.is_enabled():
                    raise RuntimeError("crowdworks_paid_message_submit_unavailable")
                button.click()
                self.page.wait_for_timeout(2_000)
                return
            if intent.get("action") == "formal_delivery" and isinstance(intent.get("payload"), Mapping):
                payload = intent["payload"]
                work_id = _text(intent.get("work_id"))
                current = self._targeted_detail(work_id)
                if current.get("provider_state") != "funded":
                    raise RuntimeError("crowdworks_paid_context_changed")
                if (not isinstance(payload.get("buyer_event_id"), str)
                        or payload.get("buyer_event_id") != current.get("buyer_event_id")):
                    raise RuntimeError("crowdworks_paid_context_changed")
                form_urls = set(current.get("form_urls") or [])
                completed = set(payload.get("completed_form_urls") or [])
                ignored = set(payload.get("ignored_form_urls") or [])
                if payload.get("no_form") is True:
                    answer_body = payload.get("answer_body")
                    answer_effect_key = payload.get("answer_effect_key")
                    quality_sha256 = payload.get("quality_sha256")
                    marker = f"納品対象マイルストーン: {_text(payload.get('milestone_id'))}"
                    if (form_urls or not isinstance(answer_body, str) or not answer_body.strip()
                            or not isinstance(answer_effect_key, str) or not answer_effect_key.strip()
                            or not isinstance(payload.get("buyer_event_id"), str)
                            or not payload.get("buyer_event_id").isdigit()
                            or payload.get("correct_work_verified") is not True
                            or not isinstance(quality_sha256, str)
                            or not re.fullmatch(r"[0-9a-f]{64}", quality_sha256)
                            or marker not in str(payload.get("message") or "")
                            or quality_sha256 != _digest({
                                "buyer_context": current.get("buyer_context"),
                                "artifact_content": current.get("artifact_content"),
                                "body": answer_body.strip(),
                            })):
                        raise RuntimeError("crowdworks_paid_form_progress_changed")
                    self._goto_contract(work_id)
                    if not self._seller_message_contains(work_id, payload["buyer_event_id"], answer_body.strip()):
                        raise RuntimeError("crowdworks_paid_answer_readback_unavailable")
                    self._complete_once(current, payload)
                    return
                if (not form_urls or not completed
                        or not completed.issubset(set(current.get("completed_form_urls") or []))
                        or completed | ignored != form_urls
                        or f"納品対象マイルストーン: {_text(payload.get('milestone_id'))}" not in str(payload.get("message") or "")):
                    raise RuntimeError("crowdworks_paid_form_progress_changed")
                self._complete_once(current, payload)
                return
            if intent.get("action") != "submit" or not isinstance(intent.get("payload"), Mapping):
                raise RuntimeError("crowdworks_paid_effect_unsupported")
            payload = intent["payload"]
            work_id = _text(intent.get("work_id"))
            current = self._targeted_detail(work_id)
            url = payload.get("form_url")
            available = set(current.get("form_urls") or [])
            if isinstance(current.get("form_url"), str):
                available.add(current["form_url"])
            revision_event_id = payload.get("revision_event_id")
            is_revision = isinstance(revision_event_id, str) and bool(revision_event_id.strip())
            if (current.get("provider_state") != "funded" or payload.get("milestone_id") != current.get("milestone_id")
                    or not isinstance(url, str) or url not in available
                    or (not isinstance(payload.get("buyer_event_id"), str)
                        or payload.get("buyer_event_id") != current.get("buyer_event_id"))
                    or (url in set(current.get("completed_form_urls") or [])
                        and not is_revision)
                    or (is_revision and revision_event_id != current.get("buyer_event_id"))
                    or payload.get("form_sha256") != hashlib.sha256(url.encode()).hexdigest()):
                raise RuntimeError("crowdworks_paid_context_changed")
            self._submit_form_once({**current, "form_url": url,
                                    "form_revision_event_id": payload.get("revision_event_id")})
        finally:
            self.close()

    def readback(self, intent: dict[str, Any]) -> dict[str, Any]:
        try:
            if intent.get("action") == "answer":
                payload = intent.get("payload")
                if not isinstance(payload, Mapping):
                    return {"authoritative_absent": True}
                body = _text(payload.get("body")); work_id = _text(intent.get("work_id"))
                self._goto_contract(work_id)
                visible_body = _text(self.page.locator("body").inner_text(),
                                     "crowdworks_paid_contract_unavailable")
                if body in visible_body:
                    buyer_event_id = payload.get("buyer_event_id")
                    if isinstance(buyer_event_id, str) and buyer_event_id.isdigit():
                        try:
                            present = self._seller_message_contains(work_id, buyer_event_id, body)
                        except Exception:
                            raise
                        if not present:
                            return {"authoritative_absent": True}
                    return {"verified": True,
                            "provider_receipt_id": f"contract:{work_id}:answer:{_text(intent.get('effect_key'))}",
                            "observed_at": _now()}
                return {"authoritative_absent": True}
            if intent.get("action") == "formal_delivery" and isinstance(intent.get("payload"), Mapping):
                payload = intent["payload"]; work_id = _text(intent.get("work_id")); self._goto_contract(work_id)
                if (not isinstance(payload.get("buyer_event_id"), str)
                        or not payload.get("buyer_event_id").strip()):
                    return {"authoritative_absent": True}
                milestone_id = _text(payload.get("milestone_id"))
                delivery_message = payload.get("message")
                if not isinstance(delivery_message, str) or not delivery_message.strip():
                    return {"authoritative_absent": True}
                if f"納品対象マイルストーン: {milestone_id}" not in delivery_message:
                    return {"authoritative_absent": True}
                actions = self.page.locator('form[action^="/milestones/"][action$="/complete"]').evaluate_all(
                    "forms => forms.map(form => form.getAttribute('action'))")
                progress_steps = self.page.locator("ul.progress li").evaluate_all(
                    "nodes => nodes.map(node => ({label:(node.innerText || '').trim(), className: node.className || ''}))")
                body = _text(self.page.locator("body").inner_text(), "crowdworks_paid_contract_unavailable")
                completion_action = f"/milestones/{milestone_id}/complete"
                try:
                    dialogs = self.page.locator(f"#message-dialog-completion-{milestone_id}")
                    target_dialog_visible = any(
                        dialogs.nth(index).is_visible() for index in range(dialogs.count())
                    )
                except Exception:
                    return {"authoritative_absent": True}
                inspection_pending = ("クライアント（発注者）が検収を行っています" in body
                                      and "検収完了までしばらくお待ちください" in body)
                if any(action != completion_action for action in actions):
                    return {"authoritative_absent": True}
                delivered = completion_action not in actions and not target_dialog_visible
                delivery_step_done = any(
                    isinstance(step, Mapping)
                    and step.get("label") == "納品"
                    and "done" in str(step.get("className") or "").split()
                    for step in progress_steps
                )
                # The exact milestone action must be gone and the page must
                # expose a delivery/inspection status, not an unrelated word
                # such as 「検収」 elsewhere in the contract.
                delivery_status = delivered and delivery_step_done and (
                    inspection_pending
                    or (("納品済み" in body or "納品完了" in body) and "検収" in body)
                ) and delivery_message.strip() in body
                if delivery_status and not self._seller_message_contains(
                        work_id, payload["buyer_event_id"], delivery_message.strip()):
                    return {"authoritative_absent": True}
                if delivery_status:
                    return {"verified": True,
                            "provider_receipt_id": f"contract:{work_id}:milestone:{milestone_id}",
                            "observed_at": _now()}
                return {"authoritative_absent": True}
            if intent.get("action") != "submit" or not isinstance(intent.get("payload"), Mapping):
                return {"authoritative_absent": True}
            payload = intent["payload"]; work_id = _text(intent.get("work_id")); self._goto_contract(work_id)
            form_sha256 = _text(payload.get("form_sha256"))
            binding = {"provider": "crowdworks", "account_id": self.account_id, "contract_id": work_id,
                       "milestone_id": _text(payload.get("milestone_id")), "form_revision_sha256": form_sha256}
            revision_event_id = payload.get("revision_event_id")
            if isinstance(revision_event_id, str) and revision_event_id.strip():
                binding["revision_event_id"] = revision_event_id.strip()
            buyer_event_id = payload.get("buyer_event_id")
            if not isinstance(buyer_event_id, str) or not buyer_event_id.strip():
                return {"authoritative_absent": True}
            binding["buyer_event_id"] = buyer_event_id.strip()
            receipt = google_form.bound_receipt(self.state_path, binding)
            form_done = isinstance(receipt, Mapping) and receipt.get("url_sha256") == form_sha256 and bool(receipt.get("confirmation_sha256"))
            if form_done:
                return {"verified": True,
                        "provider_receipt_id": f"contract:{work_id}:form:{form_sha256}",
                        "observed_at": _now()}
            return {"authoritative_absent": True}
        finally:
            self.close()

    def close(self) -> None:
        if self.page is not None:
            try: self.page.close()
            except Exception: pass
        self.page = self.browser = None
        if self.owns_context and self.owned_context is not None:
            try: self.owned_context.close()
            except Exception: pass
        self.owned_context = None
        if self.runtime is not None:
            try: self.runtime.stop()
            except Exception: pass
        self.runtime = None


def read_only_inventory() -> dict[str, Any]:
    adapter = CrowdWorksPaidAdapter(account_id=ACCOUNT_ID)
    try:
        rows = adapter.observe_active()
        return {"ok": True, "source_complete": True, "contract_candidates": [
            {"provider_id": row["work_id"], "provider_state": row["provider_state"]} for row in rows], "observed_at": _now()}
    finally:
        adapter.close()


def decide(row: Mapping[str, Any], *, form_selector: Callable[[Mapping[str, Any]], str | None] | None = None,
           answer_selector: Callable[[Mapping[str, Any]], str | None] | None = None,
           quality_selector: Callable[[Mapping[str, Any], str], str | None] | None = None) -> dict[str, Any]:
    context = row.get("context"); contract = context.get("contract") if isinstance(context, Mapping) else None
    if not isinstance(contract, Mapping):
        raise RuntimeError("crowdworks_paid_context_unavailable")
    if contract.get("detail_unavailable") is True:
        return {"action": "wait", "reason": "contract_detail_timeout",
                "remaining_work": ["retry official CrowdWorks contract detail readback"]}
    if contract.get("provider_state") == "awaiting_escrow":
        return {"action": "wait", "reason": "awaiting_client_escrow", "remaining_work": ["wait for official CrowdWorks escrow completion before beginning work"]}
    if contract.get("provider_state") == "delivered":
        return {"action": "noop", "classification": "completed"}
    form_url, milestone_id = contract.get("form_url"), contract.get("milestone_id")
    form_urls = contract.get("form_urls")
    completed = set(contract.get("completed_form_urls") or [])
    has_form = ((isinstance(form_urls, list) and bool(form_urls))
                or isinstance(form_url, str))
    previous_intent = context.get("previous_intent") if isinstance(context, Mapping) else None
    previous_verified = (isinstance(context, Mapping)
                         and context.get("previous_effect_verified") is True)
    if (has_form
            and (not isinstance(contract.get("buyer_event_id"), str)
                 or not contract.get("buyer_event_id").strip())):
        return {"action": "wait", "reason": "buyer_event_required",
                "remaining_work": ["read and persist the latest buyer message before submitting a form"]}
    if (previous_verified and isinstance(previous_intent, Mapping)
            and previous_intent.get("action") == "formal_delivery"):
        return {"action": "wait", "reason": "awaiting_buyer_inspection",
                "remaining_work": ["read the official CrowdWorks inspection and acceptance state"]}
    if (previous_verified and isinstance(previous_intent, Mapping)
            and previous_intent.get("action") == "answer" and not has_form):
        buyer_event_id = contract.get("buyer_event_id")
        previous_payload = previous_intent.get("payload")
        if (not isinstance(buyer_event_id, str) or not buyer_event_id.strip()
                or not isinstance(previous_payload, Mapping)
                or previous_payload.get("buyer_event_id") != buyer_event_id):
            return {"action": "wait", "reason": "buyer_event_required",
                    "remaining_work": ["read and persist the latest buyer message before formal delivery"]}
        if contract.get("artifact_access") == "permission_required":
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["obtain and verify the buyer artifact before formal delivery"]}
        quality_sha256 = previous_payload.get("quality_sha256")
        if (previous_payload.get("correct_work_verified") is not True
                or not isinstance(quality_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", quality_sha256)
                or quality_sha256 != _digest({
                    "buyer_context": contract.get("buyer_context"),
                    "artifact_content": contract.get("artifact_content"),
                    "body": str(previous_payload.get("body") or "").strip(),
                })):
            return {"action": "wait", "reason": "work_quality_required",
                    "remaining_work": ["obtain an independent quality check for the requested work before formal delivery"]}
        artifact_ready = (
            contract.get("artifact_required") is not True
            or contract.get("artifact_verified") is True
            or (contract.get("artifact_access") == "readable"
                and isinstance(contract.get("artifact_content"), str)
                and bool(contract.get("artifact_content").strip()))
        )
        if not artifact_ready:
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["obtain and verify the buyer artifact before formal delivery"]}
        milestone = contract.get("milestone_id")
        answer_body = previous_payload.get("body")
        answer_effect_key = previous_intent.get("effect_key")
        if (not isinstance(milestone, str) or not milestone.strip()
                or not isinstance(answer_body, str) or not answer_body.strip()
                or not isinstance(answer_effect_key, str) or not answer_effect_key.strip()):
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["retain the verified answer and milestone identity before formal delivery"]}
        return {"action": "formal_delivery", "payload": {
            "milestone_id": milestone.strip(),
            "message": _delivery_message(milestone.strip(), form=False),
            "no_form": True,
            "answer_body": answer_body.strip(),
            "answer_effect_key": answer_effect_key.strip(),
            "buyer_event_id": buyer_event_id.strip(),
            "correct_work_verified": True,
            "quality_sha256": quality_sha256,
        }}
    if has_form:
        if form_url in completed and not contract.get("form_revision"):
            form_url = None
        selection_contract = contract
        if (not isinstance(selection_contract.get("form_urls"), list)
                and isinstance(selection_contract.get("form_url"), str)):
            selection_contract = {**selection_contract,
                                  "form_urls": [selection_contract["form_url"]]}
        selected = form_selector(selection_contract) if callable(form_selector) else None
        if selected == FORM_SELECTION_COMPLETE:
            candidate_urls = selection_contract.get("form_urls")
            if not isinstance(milestone_id, str) or not isinstance(candidate_urls, list):
                return {"action": "wait", "reason": "buyer_task_detail_required",
                        "remaining_work": ["read the official funded contract task before any delivery effect"]}
            ignored = set(contract.get("ignored_form_urls") or [])
            remaining = set(candidate_urls) - completed
            if not completed or remaining - ignored:
                return {"action": "wait", "reason": "form_selection_required",
                        "remaining_work": ["complete one official form and select or explicitly exclude every remaining form"]}
            return {"action": "formal_delivery", "payload": {
                "milestone_id": milestone_id,
                "message": _delivery_message(milestone_id, form=True),
                "completed_form_urls": sorted(completed),
                "ignored_form_urls": sorted(ignored),
                "buyer_event_id": contract["buyer_event_id"].strip(),
            }}
        form_url = selected
        if not isinstance(form_url, str) or not _google_form_url(form_url):
            return {"action": "wait", "reason": "form_selection_required",
                    "remaining_work": ["model must select one official form from the buyer context"]}
    if not form_url and not (isinstance(form_urls, list) and form_urls):
        if contract.get("provider_state") != "funded":
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["read the official funded contract task before any delivery effect"]}
        buyer_context = contract.get("buyer_context")
        if not isinstance(buyer_context, str) or not buyer_context.strip():
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["read the complete buyer instruction before answering"]}
        buyer_event_id = contract.get("buyer_event_id")
        if not isinstance(buyer_event_id, str) or not buyer_event_id.strip():
            return {"action": "wait", "reason": "buyer_event_required",
                    "remaining_work": ["read and persist the latest buyer message before answering"]}
        artifact_ready = (
            contract.get("artifact_verified") is True
            or contract.get("artifact_access") == "permission_required"
            or (contract.get("artifact_access") == "readable"
                and isinstance(contract.get("artifact_content"), str)
                and bool(contract.get("artifact_content").strip()))
        )
        if contract.get("artifact_required") is True and not artifact_ready:
            return {"action": "wait", "reason": "buyer_task_detail_required",
                    "remaining_work": ["open and verify the linked buyer artifact before answering"]}
        answer = (
            PERMISSION_REQUEST_BODY
            if contract.get("artifact_access") == "permission_required"
            else (answer_selector(contract)
                  if callable(answer_selector) and isinstance(buyer_context, str)
                  and buyer_context.strip() else None)
        )
        if isinstance(answer, str) and answer.strip():
            body = answer.strip()
            payload = {"body": body, "buyer_event_id": buyer_event_id.strip()}
            if contract.get("artifact_access") != "permission_required" and not callable(quality_selector):
                return {"action": "wait", "reason": "work_quality_required",
                        "remaining_work": ["obtain an independent quality check for the requested work before sending"]}
            if contract.get("artifact_access") != "permission_required" and callable(quality_selector):
                quality = quality_selector(contract, body)
                if quality != "quality_ok":
                    return {"action": "wait", "reason": "work_quality_required",
                            "remaining_work": ["review the buyer request and repair the proposed work before sending"]}
                payload.update({
                    "correct_work_verified": True,
                    "quality_verdict": quality,
                    "quality_sha256": _digest({
                        "buyer_context": contract.get("buyer_context"),
                        "artifact_content": contract.get("artifact_content"),
                        "body": body,
                    }),
                })
            return {"action": "answer", "payload": payload}
        return {"action": "wait", "reason": "buyer_task_detail_required",
                "remaining_work": ["read the complete buyer instruction and compose the required response"]}
    if contract.get("provider_state") != "funded" or not isinstance(form_url, str) or not _google_form_url(form_url) or not isinstance(milestone_id, str):
        return {"action": "wait", "reason": "buyer_task_detail_required", "remaining_work": ["read the official funded contract task before any delivery effect"]}
    if not isinstance(contract.get("application_date"), str):
        return {"action": "wait", "reason": "official_application_date_required",
                "remaining_work": ["locate a labeled official CrowdWorks proposal application date before form submission"]}
    payload = {"form_url": form_url,
               "form_sha256": hashlib.sha256(form_url.encode()).hexdigest(),
               "milestone_id": milestone_id}
    buyer_event_id = contract.get("buyer_event_id")
    if not isinstance(buyer_event_id, str) or not buyer_event_id.strip():
        return {"action": "wait", "reason": "buyer_event_required",
                "remaining_work": ["persist the buyer event before submitting the selected form"]}
    payload["buyer_event_id"] = buyer_event_id.strip()
    if contract.get("form_revision"):
        revision_event_id = contract.get("buyer_event_id")
        if not isinstance(revision_event_id, str) or not revision_event_id.strip():
            return {"action": "wait", "reason": "buyer_event_required",
                    "remaining_work": ["persist the buyer correction event before resubmitting the form"]}
        payload["revision_event_id"] = revision_event_id.strip()
    return {"action": "submit", "payload": payload}


def build(argv: list[str]):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True); parser.add_argument("--state-path", required=True, type=Path)
    parser.add_argument("--candidate-profile", type=Path, default=Path.home() / ".config/anicca/job-search/profile.json")
    parser.add_argument("--provider-profile", type=Path, default=Path.home() / ".config/anicca/crowdworks/public-profile.json")
    parser.add_argument("--application-receipts-path", type=Path, default=DEFAULT_APPLICATION_RECEIPTS)
    args = parser.parse_args(argv); provider = profile_module.load_config(args.provider_profile)
    adapter = CrowdWorksPaidAdapter(account_id=args.account_id, state_path=args.state_path.expanduser().resolve(), candidate_profile=args.candidate_profile.expanduser().resolve(), provider_profile=provider,
                                    application_receipts_path=args.application_receipts_path)
    return adapter, lambda row: decide(row, form_selector=adapter._select_form_url,
                                        answer_selector=adapter._compose_answer,
                                        quality_selector=adapter._quality_check)


__all__ = ["CrowdWorksPaidAdapter", "CrowdWorksPaidWait", "build", "decide", "read_only_inventory"]
