#!/usr/bin/env python3
"""Small authenticated CDP port for the Coconala direct-offer form."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from gig_paths import BROWSER_DIR  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    import coconala_queue_snapshot as collector
except ModuleNotFoundError:
    collector = _load("coconala_queue_snapshot")
try:
    import requested_estimate as estimate
except ModuleNotFoundError:
    estimate = _load("requested_estimate")


FINAL_LABEL = "提案を送る"

CATEGORY_TYPE_CONTRACT_JS = r'''const categoryTypeContract=()=>{const sub=document.querySelector('[name="RequestSubCategory"]')||document.getElementById("RequestSubCategory"),type=document.querySelector('[name="RequestMasterCategoryTypeId"]')||document.getElementById("RequestMasterCategoryTypeId"),row=type?.closest('.js_category-type-row')||null,data=document.querySelector('.js_data-master-category-types');let mapping=null;try{mapping=JSON.parse(data?.getAttribute('data-master-category-types')||'')}catch(_e){}const loaded=!!mapping&&typeof mapping==='object'&&!Array.isArray(mapping),subValue=sub?.value||'',hasSub=loaded&&Object.prototype.hasOwnProperty.call(mapping,subValue),mapped=hasSub?mapping[subValue]:null,count=hasSub?(Array.isArray(mapped)?mapped.length:(mapped&&typeof mapped==='object'?Object.keys(mapped).length:null)):(loaded?0:null),enabled=type?[...type.options].filter(o=>o.value&&!o.disabled).length:null;return{mapping_loaded:loaded,sub_value:subValue,mapping_has_sub:hasSub,mapped_option_count:count,control_disabled:!!type?.disabled,row_present:!!row,row_hidden:!!row&&(row.hidden||row.classList.contains('hidden')||getComputedStyle(row).display==='none'),enabled_option_count:enabled}};'''
RELATED_SERVICE_JS = r'''const relatedService=()=>{const input=document.querySelector('[name="data[Request][related_service_id]"]'),id=input?.value||"",scope=input?.closest("form")||document,links=id?[...scope.querySelectorAll('a[href*="/services/"]')].filter(x=>new URL(x.getAttribute("href"),location.origin).pathname==="/services/"+id):[],link=links.length===1?links[0]:null,parent=document.querySelector('.js_base-service-selected .js_base-parent-category-name'),category=document.querySelector('.js_base-service-selected .js_base-category-name'),type=document.querySelector('.js_base-service-selected .js_base-category-type-name');return{id,service_name:(link?.textContent||"").trim(),service_url:link?new URL(link.getAttribute("href"),location.origin).pathname:"",master_category_label:(parent?.textContent||"").trim(),sub_category_label:(category?.textContent||"").trim(),category_type_label:(type?.textContent||"").trim()||null}};'''


def final_submit_count(labels: list[str]) -> int:
    normalized = [str(label or "").strip() for label in labels]
    return 1 if normalized.count(FINAL_LABEL) == 1 else 0


def _by(name: str) -> str:
    return "document.querySelector('[name=\"'+CSS.escape("+json.dumps(name)+")+'\"]')||document.getElementById("+json.dumps(name)+")"


def form_expression() -> str:
    return r'''(()=>{__CATEGORY_TYPE_CONTRACT____RELATED_SERVICE__const names=["RequestMasterCategory","RequestSubCategory","RequestMasterCategoryTypeId","RequestTitle","OfferContent","OfferIsSubscription0","OfferIsSubscription1","OfferPrice","OfferExpireDate","data[Offer][expire_date]","OfferUnitTime","source_talkroom_id"];const byName=name=>document.querySelector('[name="'+CSS.escape(name)+'"]')||document.getElementById(name);const options=select=>select?[...select.options].map(o=>({label:(o.textContent||"").trim(),value:o.value||"",id:o.id||null,disabled:!!o.disabled,selected:!!o.selected})).filter(o=>o.label):[];const master=byName("RequestMasterCategory"),sub=byName("RequestSubCategory"),type=byName("RequestMasterCategoryTypeId"),completion=byName("OfferExpireDate");const form=document.querySelector("form"),files=[...document.querySelectorAll('input[type="file"]')];const allNames=[...document.querySelectorAll("[name]")].map(x=>x.name);const completionLabel=document.querySelector('label[for="OfferExpireDate"]')?.innerText||[...document.querySelectorAll('label')].find(x=>(x.innerText||'').includes('完了予定日'))?.innerText||null;return JSON.stringify({url:location.href,origin:location.origin,path:location.pathname,title:(document.querySelector("h1")?.innerText||document.title||"").replace(/\s+/g," ").trim(),method:(form?.method||"").toUpperCase(),action:form?.action||"",controls:names.filter(name=>!!byName(name)).concat(allNames.filter(name=>name.startsWith("OfferSubscription"))),submit_text:[...document.querySelectorAll("button,input[type=submit]")].map(x=>(x.innerText||x.value||"").trim()).filter(Boolean),categories:{master:options(master),sub:options(sub),type:options(type)},category_type_contract:categoryTypeContract(),related_service:relatedService(),completion_control_label:completionLabel,completion_date:completion?.value||"",attachment_count:files.length,selected_file_count:files.filter(x=>x.files&&x.files.length>0).length,form_count:document.querySelectorAll("form").length})})()'''.replace("__CATEGORY_TYPE_CONTRACT__", CATEGORY_TYPE_CONTRACT_JS).replace("__RELATED_SERVICE__", RELATED_SERVICE_JS)


def confirmation_expression() -> str:
    return r'''(()=>{__RELATED_SERVICE__const text=(document.body.innerText||"").replace(/\s+/g," ").trim();const title=document.querySelector("#RequestTitle")?.value||document.querySelector('[name="data[Request][title]"]')?.value||"";const content=document.querySelector("#OfferContent")?.value||document.querySelector('[name="data[Offer][content]"]')?.value||"";const price=Number((document.querySelector("#OfferPrice")?.value||document.querySelector('[name="data[Offer][price]"]')?.value||"").replace(/,/g,""));const single=!!document.querySelector("#OfferIsSubscription0:checked");const subscription=!!document.querySelector("#OfferIsSubscription1:checked");const plan=subscription?"subscription":single?"single":/定期購入/.test(text)?"subscription":/単発購入/.test(text)?"single":"";const completion=document.querySelector("#OfferExpireDate")?.value||document.querySelector('[name="data[Offer][expire_date]"]')?.value||"";const labels=[...document.querySelectorAll("button,input[type=submit]")].map(x=>(x.innerText||x.value||"").trim()).filter(Boolean);const match=text.match(/(?:完了予定日|納品予定日|納期)\s*[:：]?\s*(20\d{2}[/-]\d{1,2}[/-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)/);return{title:(document.querySelector("h1")?.innerText||document.title||"").replace(/\s+/g," ").trim(),title_value:title,content,price_jpy:price,purchase_plan:plan,completion_date:(completion||(match&&match[1])||"").replace(/[年月]/g,"-").replace("日","").replace(/\//g,"-"),related_service:relatedService(),final_submit_labels:labels,text_sha256:null}})()'''.replace("__RELATED_SERVICE__", RELATED_SERVICE_JS)


def select_related_service_expression(service_id: str) -> str:
    if not re.fullmatch(r"[1-9]\d*", service_id):
        raise ValueError("related_service_id_invalid")
    return r'''(async()=>{__RELATED_SERVICE__const id=__ID__,open=document.querySelector('a.js_components-modal-show[data-modal="base_service"]');if(!open)return{ok:false,error:"related_service_selector_missing"};open.click();const options=[...document.querySelectorAll('a.js_base-service[data-service-id]')].filter(x=>x.dataset.serviceId===id);if(options.length!==1)return{ok:false,error:"related_service_missing_or_ambiguous"};options[0].click();const end=Date.now()+3000;while(Date.now()<end){const selected=relatedService();if(selected.id===id&&selected.service_url==="/services/"+id&&selected.service_name)return{ok:true,related_service:selected};await new Promise(r=>setTimeout(r,50))}return{ok:false,error:"related_service_readback_mismatch"}})()'''.replace("__RELATED_SERVICE__", RELATED_SERVICE_JS).replace("__ID__", json.dumps(service_id))


def select_master_expression(label: str) -> str:
    encoded = json.dumps(label, ensure_ascii=False)
    return f'''(async()=>{{const label={encoded},e=document.querySelector('[name="RequestMasterCategory"]')||document.getElementById("RequestMasterCategory");if(!e)return{{ok:false,error:"master_category_control_missing"}};const options=[...e.options].filter(o=>(o.textContent||"").trim()===label&&!o.disabled);if(options.length!==1)return{{ok:false,error:"master_category_option_missing_or_ambiguous"}};const p=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value");p.set.call(e,options[0].value);e.dispatchEvent(new Event("input",{{bubbles:true}}));e.dispatchEvent(new Event("change",{{bubbles:true}}));const end=Date.now()+5000;while(Date.now()<end){{const sub=document.querySelector('[name="RequestSubCategory"]')||document.getElementById("RequestSubCategory");if(sub&&!sub.disabled&&[...sub.options].some(o=>o.value&&!o.disabled))return{{ok:true}};await new Promise(r=>setTimeout(r,100))}}return{{ok:false,error:"dependent_categories_not_loaded"}}}})()'''


def select_sub_expression(label: str) -> str:
    encoded = json.dumps(label, ensure_ascii=False)
    return r'''(async()=>{__CATEGORY_TYPE_CONTRACT__const label=__LABEL__,e=document.querySelector('[name="RequestSubCategory"]')||document.getElementById("RequestSubCategory");if(!e)return{ok:false,error:"sub_category_control_missing"};const options=[...e.options].filter(o=>(o.textContent||"").trim()===label&&!o.disabled&&o.value);if(options.length!==1)return{ok:false,error:"sub_category_option_missing_or_ambiguous"};const p=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value");p.set.call(e,options[0].value);e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));const end=Date.now()+5000;while(Date.now()<end){const state=categoryTypeContract(),optional=state.mapping_loaded&&state.sub_value===options[0].value&&state.control_disabled&&state.row_hidden&&state.enabled_option_count===0,required=state.mapping_loaded&&state.sub_value===options[0].value&&state.row_present&&!state.control_disabled&&!state.row_hidden&&state.enabled_option_count>0;if(optional||required)return{ok:true,category_type_required:required,category_type_contract:state};await new Promise(r=>setTimeout(r,100))}return{ok:false,error:"dependent_category_types_not_loaded",category_type_contract:categoryTypeContract(),category_type_options:(()=>{const t=document.querySelector('[name="RequestMasterCategoryTypeId"]')||document.getElementById("RequestMasterCategoryTypeId");return t?[...t.options].map(o=>({value:o.value||"",label:(o.textContent||"").trim().slice(0,40),disabled:!!o.disabled})):null})()}})()'''.replace("__CATEGORY_TYPE_CONTRACT__", CATEGORY_TYPE_CONTRACT_JS).replace("__LABEL__", encoded)


def fill_expression(terms: dict[str, Any], expire_date: str) -> str:
    encoded = json.dumps(terms, ensure_ascii=False, separators=(",", ":"))
    encoded_date = json.dumps(expire_date)
    return r'''(async()=>{__CATEGORY_TYPE_CONTRACT__const t=__TERMS__,d=__DATE__;const sleep=ms=>new Promise(r=>setTimeout(r,ms));const by=n=>document.querySelector('[name="'+CSS.escape(n)+'"]')||document.getElementById(n);const set=(e,v)=>{if(!e)return false;const p=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e),"value");if(!p?.set)return false;p.set.call(e,String(v));e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return e.value===String(v)};const wait=async fn=>{const end=Date.now()+5000;while(Date.now()<end){const out=fn();if(out)return out;await sleep(100)}return null};const select=async(n,label)=>{const e=by(n);if(!e)return null;const found=await wait(()=>{if(e.disabled)return null;const options=[...e.options].filter(o=>(o.textContent||"").trim()===label&&!o.disabled&&o.value);return options.length===1?options[0]:null});if(!found)return null;const p=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value");if(!p?.set)return null;p.set.call(e,found.value);e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));const selected=await wait(()=>{const o=[...e.options].find(x=>x.value===found.value);return o&&o.selected&&((o.textContent||"").trim()===label)?o:null});return selected?{label:(selected.textContent||"").trim(),value:selected.value||"",id:selected.id||null}:null};const files=[...document.querySelectorAll('input[type="file"]')];if(files.some(x=>x.files&&x.files.length>0))return{ok:false,error:"attachments_forbidden"};const master=await select("RequestMasterCategory",t.master_category_label);if(!master)return{ok:false,error:"master_category_option_missing_or_ambiguous"};const sub=await select("RequestSubCategory",t.sub_category_label);if(!sub)return{ok:false,error:"sub_category_option_missing_or_ambiguous"};const contract=await wait(()=>{const state=categoryTypeContract(),optional=state.mapping_loaded&&state.sub_value===sub.value&&state.control_disabled&&state.row_hidden&&state.enabled_option_count===0,required=state.mapping_loaded&&state.sub_value===sub.value&&state.row_present&&!state.control_disabled&&!state.row_hidden&&state.enabled_option_count>0;return optional||required?{...state,required}:null});if(!contract)return{ok:false,error:"dependent_category_types_not_loaded",category_type_contract:categoryTypeContract(),category_type_options:(()=>{const t=document.querySelector('[name="RequestMasterCategoryTypeId"]')||document.getElementById("RequestMasterCategoryTypeId");return t?[...t.options].map(o=>({value:o.value||"",label:(o.textContent||"").trim().slice(0,40),disabled:!!o.disabled})):null})()};let type=null;if(contract.required){if(typeof t.category_type_label!=="string"||!t.category_type_label)return{ok:false,error:"category_type_terms_missing"};type=await select("RequestMasterCategoryTypeId",t.category_type_label);if(!type)return{ok:false,error:"category_type_option_missing_or_ambiguous"}}else if(t.category_type_label!==null)return{ok:false,error:"optional_category_type_terms_mismatch"};if(!set(by("RequestTitle"),t.title)||!set(by("OfferContent"),t.content)||!set(by("OfferPrice"),t.price_jpy))return{ok:false,error:"required_control_missing"};const radio=by(t.purchase_plan==="single"?"OfferIsSubscription0":"OfferIsSubscription1");if(!radio)return{ok:false,error:"purchase_plan_control_missing"};radio.checked=true;radio.dispatchEvent(new Event("input",{bubbles:true}));radio.dispatchEvent(new Event("change",{bubbles:true}));if(!set(by("OfferExpireDate"),d)||!set(by("data[Offer][expire_date]"),d))return{ok:false,error:"expire_date_control_missing"};return{ok:true,selected_categories:{master,sub,type},category_type_contract:contract,selected_file_count:files.filter(x=>x.files&&x.files.length>0).length}})()'''.replace("__CATEGORY_TYPE_CONTRACT__", CATEGORY_TYPE_CONTRACT_JS).replace("__TERMS__", encoded).replace("__DATE__", encoded_date)


async def _eval(ws: Any, expression: str) -> Any:
    """Evaluate against the tab's websocket URL after the document is usable.

    ``DefaultTab.ws`` is a CDP endpoint URL, not an already-open websocket.  Keep
    the connection for the bounded readiness probe and the actual expression so
    request ids remain unique and no form read/fill races an in-flight navigation.
    """
    async with websockets.connect(
        str(ws), ping_interval=None, open_timeout=15,
        max_size=50 * 1024 * 1024,
    ) as socket:
        request_id = 1
        for _ in range(40):
            state_result = await collector.call(socket, request_id, "Runtime.evaluate", {
                "expression": "JSON.stringify({url:location.href,ready:document.readyState})",
                "returnByValue": True,
            })
            request_id += 1
            state_value = state_result.get("result", {}).get("value")
            if isinstance(state_value, str):
                try:
                    state_value = json.loads(state_value)
                except json.JSONDecodeError:
                    state_value = None
            if isinstance(state_value, dict) and collector.navigation_state_ready(state_value):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("authenticated tab did not finish navigation")

        result = await collector.call(socket, request_id, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        value = result.get("result", {}).get("value")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


class EstimateFormRefused(RuntimeError):
    """The estimate form JS reported ok:false; the readback rides along.

    ``str(exc)`` stays the bare durable error token (e.g.
    ``dependent_category_types_not_loaded``) because
    ``requested_estimate.py:_error_code()`` truncates any exception message to
    its first token and must keep working untouched. The category-type
    contract (booleans/counts: mapping_loaded, sub_value, mapped_option_count,
    control_disabled, row_hidden, enabled_option_count) is pure machine state,
    not customer/offer text, so it travels as ``.contract`` instead of being
    folded into the message.
    """

    def __init__(self, code: str, contract: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.contract = contract


class CoconalaEstimateBrowser:
    """One tab held from fresh thread read through final submit/readback."""

    def __init__(
        self, helper: Path | None, thread_url: str, estimate_url: str, *,
        hidden: bool = False, owner: str | None = None,
    ):
        default_helper = BROWSER_DIR / "scripts" / "cdp_default_tab.py"
        self.helper, self.thread_url, self.estimate_url = Path(helper or os.environ.get("GIG_CDP_HELPER", default_helper)), thread_url, estimate_url
        self.hidden = hidden
        self.owner = owner
        self.tab: Any = None
        self.final_clicks = 0
        self.network: list[dict[str, Any]] = []
        self.semantic_context_required = False

    def __enter__(self):
        self.tab = collector.DefaultTab(
            self.helper, self.thread_url, hidden=self.hidden,
            background=not self.hidden, owner=self.owner,
        )
        self.tab.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        if self.tab is not None:
            self.tab.__exit__(*args)

    def _navigate(self, url: str) -> None:
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        allowed_path = (
            estimate.ESTIMATE_URL_RE.fullmatch(parsed.path) is not None
            or re.fullmatch(r"/mypage/direct_message/[A-Za-z0-9_-]+", parsed.path) is not None
        )
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"coconala.com", "www.coconala.com"}
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.query
            or parsed.fragment
            or not allowed_path
        ):
            raise ValueError("unsafe Coconala navigation")
        async def go():
            import websockets
            async with websockets.connect(self.tab.ws, ping_interval=None, open_timeout=15) as ws:
                events: list[dict[str, Any]] = []
                await collector.call(ws, 1, "Page.navigate", {"url": url}, event_sink=events)
                self.network.extend(collector.allowlisted_cdp_events(events))
        asyncio.run(go())
        time.sleep(0.25)

    def read_thread_context(self) -> tuple[dict[str, Any], dict[str, Any]]:
        raw = asyncio.run(collector.inspect_message_page(self.tab.ws, collector.DIRECT_MESSAGE_EXPRESSION, self.thread_url))
        rows = raw.get("messages") if isinstance(raw.get("messages"), list) else []
        head = collector.direct_thread_head_projection(
            raw, self.thread_url, talkroom_id=self.thread_url.rstrip("/").rsplit("/", 1)[-1],
        )
        if self.semantic_context_required:
            conversation = estimate.semantic_conversation(raw)
            context = {
                "conversation": conversation,
                "buyer_messages": [dict(row, side="buyer") for row in conversation if row["role"] == "buyer"],
                "seller_messages": [dict(row, side="seller") for row in conversation if row["role"] == "seller"],
            }
        else:
            context = {
                "buyer_messages": [dict(row, side="buyer") for row in rows if isinstance(row, dict) and row.get("author_path") != raw.get("own_user_path")],
                "seller_messages": [dict(row, side="seller") for row in rows if isinstance(row, dict) and row.get("author_path") == raw.get("own_user_path")],
            }
        context["last_message_identity_sha256"] = head.get("last_message_identity_sha256")
        return context, {"structured_offers": raw.get("structured_offers") or [], "estimate_url": raw.get("estimate_url"), "own_user_path": raw.get("own_user_path")}

    def fresh_thread_context(self, expected_own_user_path: str) -> dict[str, Any]:
        """Re-read the thread in a separate tab without disturbing confirmation."""
        with collector.DefaultTab(
            self.helper, self.thread_url, hidden=True, background=True,
            owner=self.owner,
        ) as tab:
            raw = asyncio.run(collector.inspect_message_page(
                tab.ws, collector.DIRECT_MESSAGE_EXPRESSION, self.thread_url,
            ))
        collector.validate_page_identity(
            raw, expected_url=self.thread_url, expected_title="メッセージ詳細",
        )
        own = str(raw.get("own_user_path") or "").strip()
        if not own or own != expected_own_user_path:
            raise collector.CollectorUnhealthy("sender_identity_changed")
        head = collector.direct_thread_head_projection(
            raw, self.thread_url, talkroom_id=self.thread_url.rstrip("/").rsplit("/", 1)[-1],
        )
        rows = raw.get("messages") if isinstance(raw.get("messages"), list) else []
        if not self.semantic_context_required:
            if any(not str(row.get("author_path") or "").strip() for row in rows if isinstance(row, dict)):
                raise collector.CollectorUnhealthy("missing_sender_identity")
            return {"own_user_path": own,
                    "last_message_identity_sha256": head.get("last_message_identity_sha256"),
                    "buyer_messages": [
                dict(row, side="buyer") for row in rows
                if isinstance(row, dict) and row.get("author_path") != own
            ]}
        conversation = estimate.semantic_conversation(raw)
        return {"own_user_path": own, "conversation": conversation,
                "last_message_identity_sha256": head.get("last_message_identity_sha256"),
                "buyer_messages": [
            dict(row, side="buyer") for row in conversation if row["role"] == "buyer"
        ]}

    def read_form(self) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, form_expression()))
        if not isinstance(value, dict):
            raise RuntimeError("estimate form observation missing")
        return value

    def open_form(self) -> dict[str, Any]:
        self._navigate(self.estimate_url)
        return self.read_form()

    def select_master(self, label: str) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, select_master_expression(label)))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RuntimeError(str((value or {}).get("error") if isinstance(value, dict) else "master_category_select_failed"))
        return self.read_form()

    @staticmethod
    def _refused(value: Any, fallback: str) -> "EstimateFormRefused":
        """Say what the page looked like, not only what we concluded about it.

        The category-type wait used to give up with a bare
        ``dependent_category_types_not_loaded``, which reads as a slow page and is
        not: the same thread fails every pass while its siblings submit, so the
        form is settling into a state the contract admits neither as optional nor
        as required. Which state that is was thrown away here and in the browser,
        so nobody could tell. Carry the readback out as the exception's
        ``.contract`` (not folded into the message — ``_error_code()`` in
        requested_estimate.py truncates the message to a durable first token).
        """
        if not isinstance(value, dict):
            return EstimateFormRefused(fallback)
        error = str(value.get("error") or fallback)
        contract = value.get("category_type_contract")
        contract = dict(contract) if isinstance(contract, dict) else None
        # Counts alone said six offered against three mapped and could not say which
        # three were extra. The option list is Coconala's own taxonomy -- values and
        # category labels, no customer or offer text -- so it rides along too.
        options = value.get("category_type_options")
        if contract is not None and isinstance(options, list):
            contract["options"] = options[:20]
        return EstimateFormRefused(error, contract)

    def select_sub(self, label: str) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, select_sub_expression(label)))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise self._refused(value, "sub_category_select_failed")
        return self.read_form()

    def fill(self, terms: dict[str, Any], completion_date: str) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, fill_expression(terms, completion_date)))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise self._refused(value, "estimate_fill_failed")
        return value

    def select_related_service(self, service_id: str) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, select_related_service_expression(service_id)))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RuntimeError(str((value or {}).get("error") if isinstance(value, dict) else "related_service_select_failed"))
        return value["related_service"]

    def first_submit(self) -> None:
        value = asyncio.run(_eval(self.tab.ws, r'''(()=>{const buttons=[...document.querySelectorAll("button,input[type=submit]")].filter(x=>(x.innerText||x.value||"").trim()==="提案内容を確認する");if(buttons.length!==1)return{ok:false};buttons[0].click();return{ok:true}})()'''))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RuntimeError("confirmation_submit_missing")
        parsed = urlsplit(self.estimate_url)
        self.network.append({"method": "POST", "path": parsed.path, "status": "submitted", "phase": "confirmation"})
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            observed = asyncio.run(_eval(self.tab.ws, confirmation_expression()))
            if (
                isinstance(observed, dict)
                and observed.get("title") == "提案内容を確認する"
                and final_submit_count(observed.get("final_submit_labels") or []) == 1
            ):
                return
            time.sleep(0.25)
        raise RuntimeError("confirmation_transition_unconfirmed")

    def read_confirmation(self) -> dict[str, Any]:
        value = asyncio.run(_eval(self.tab.ws, confirmation_expression()))
        if not isinstance(value, dict):
            raise RuntimeError("confirmation_observation_missing")
        return value

    def final_submit(self, confirmation: dict[str, Any], terms: dict[str, Any], *, today: Any = None) -> None:
        if final_submit_count(confirmation.get("final_submit_labels") or []) != 1 or not estimate.validate_confirmation(confirmation, terms, today=today):
            raise RuntimeError("confirmation_terms_mismatch")
        value = asyncio.run(_eval(self.tab.ws, r'''(()=>{const buttons=[...document.querySelectorAll("button,input[type=submit]")].filter(x=>(x.innerText||x.value||"").trim()==="提案を送る");if(buttons.length!==1)return{ok:false};buttons[0].click();return{ok:true}})()'''))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RuntimeError("final_submit_missing")
        self.final_clicks += 1
        parsed = urlsplit(self.estimate_url)
        self.network.append({"method": "POST", "path": parsed.path, "status": "submitted", "phase": "final"})
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            state = asyncio.run(_eval(
                self.tab.ws,
                r'''(()=>({url:location.href,ready:document.readyState}))()''',
            ))
            if isinstance(state, dict):
                current = urlsplit(str(state.get("url") or ""))
                if state.get("ready") == "complete" and current.path != parsed.path:
                    return
            time.sleep(0.25)
        raise RuntimeError("final_submit_transition_unconfirmed")

    def read_after(self) -> dict[str, Any]:
        self._navigate(self.thread_url)
        return asyncio.run(collector.inspect_message_page(self.tab.ws, collector.DIRECT_MESSAGE_EXPRESSION, self.thread_url))


__all__ = ["CoconalaEstimateBrowser", "form_expression", "confirmation_expression", "select_master_expression", "select_related_service_expression", "fill_expression", "final_submit_count"]
