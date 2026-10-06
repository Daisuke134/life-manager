#!/usr/bin/env python3
"""Collect the buyer's direct-message thread into the project. Nobody wrote this before.

``reply_outcomes.py`` says it plainly: "The bridge is already on disk. A purchased project
keeps the DM thread it grew out of, at ``projects/<project>/source/dm/thread-<DM_ID>-*``".
It was on disk because a human put it there. There has never been a writer.

Order 91000002, 2026-08-07: the buyer sent two PNGs -- 2,433,925 and 2,784,148 bytes -- in
a direct message. Those two files were the material for the whole job. The talkroom
collector never looks at direct messages, so the builder worked for a day without them,
and a human had to capture them by hand.

This mechanises exactly the path that worked by hand:

1. find the buyer's thread (the inbox lists them; the thread page names its participants)
2. read the thread with the collector's own ``DefaultTab`` -- no second browser route
3. ★fetch each attachment in-page with ``credentials: 'include'``★ so the download
   inherits the authenticated session instead of arriving as a login page
4. write the body and the attachment bytes under ``source/dm/``

Everything above the browser boundary is a pure function over a DOM dict, so the shapes
are tested without a browser; ``collect`` is the only part that needs one.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from gig_paths import BROWSER_DIR  # noqa: E402


COLLECTOR_PATH = Path(__file__).with_name("coconala_queue_snapshot.py")
_COLLECTOR = None

INBOX_URL = "https://coconala.com/message"
THREAD_URL = "https://coconala.com/mypage/direct_message/{thread_id}"
THREAD_ID = re.compile(r"^[0-9]{1,32}$")
THREAD_FILENAME = re.compile(r"^thread-([0-9]+)-full\.json$")
MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024
MAX_ATTACHMENTS = 40
MAX_BODY_CHARS = 20000
# What ``skills/_shared/buyer-attachments`` leaves behind when it moves a credential out
# of a project. Seeing one means this file has been redacted on purpose.
VAULT_POINTER = "{{VAULT:"

# Same rows as DIRECT_MESSAGE_EXPRESSION, plus what that one leaves behind: the files.
# Avatars live in .threadUser and are excluded; everything else inside the message body
# that points at a file is a candidate, and the fetch below reports the status of each.
DM_THREAD_EXPRESSION = r'''(()=>{
  const title=document.title;
  const container=document.querySelector('.js_thread-wrapper');
  const rows=container?[...container.querySelectorAll('.threadColomun')].filter(row=>row.querySelector('.threadMessage')):[];
  const own=document.querySelector('.sidebar-profile a[href*="/users/"]');
  const path=a=>a?new URL(a.href,location.origin).pathname:null;
  const absolute=value=>{try{return new URL(value,location.origin).href}catch(e){return null}};
  const messages=rows.map(row=>{
    const author=row.querySelector('.threadUser a[href*="/users/"]');
    const time=row.querySelector('.threadPostTime');
    const body=row.querySelector('.js-translateMessageOriginalMessage')||row.querySelector('.threadMessage');
    const scope=row.querySelector('.threadMessage')||row;
    const attachments=[];
    const push=(url,filename)=>{
      if(!url)return;
      if(attachments.some(item=>item.url===url))return;
      attachments.push({url:url,filename:(filename||'').trim()||null});
    };
    [...scope.querySelectorAll('a[href]')].forEach(anchor=>{
      if(anchor.closest('.threadUser'))return;
      const href=absolute(anchor.getAttribute('href'));
      if(!href)return;
      if(/^(mailto:|javascript:)/i.test(anchor.getAttribute('href')||''))return;
      if(/\/users\//.test(href))return;
      const looksLikeFile=/(attachment|download|file|\.png|\.jpe?g|\.gif|\.pdf|\.zip|\.xlsx?|\.docx?|\.pptx?|\.csv|\.txt|\.psd|\.ai|\.svg|\.mp4|\.mov)/i.test(href)
        ||!!anchor.getAttribute('download');
      if(!looksLikeFile)return;
      push(href,anchor.getAttribute('download')||anchor.innerText);
    });
    [...scope.querySelectorAll('img[src]')].forEach(image=>{
      if(image.closest('.threadUser'))return;
      const source=absolute(image.getAttribute('src'));
      if(!source)return;
      if(/coconala_profile|\/icon|avatar|emoji|blank\.(gif|png)/i.test(source))return;
      push(source,image.getAttribute('alt'));
    });
    return {
      message_id:row.getAttribute('data-message-id')||row.id||null,
      author_path:path(author),
      author_name:((author&&author.innerText||'').trim()
        ||(author&&author.querySelector('img')&&author.querySelector('img').getAttribute('alt')||'').trim())||null,
      sent_at:(time&&time.innerText||'').trim()||null,
      body:(body&&body.innerText)||'',
      attachments:attachments
    };
  });
  return JSON.stringify({
    url:location.href,
    title,
    container_present:!!container,
    not_found_present:/404|ページが見つかりません|お探しのページ/.test(title)||!!document.querySelector('[class*="not-found"],[class*="notFound"]'),
    error_present:/エラー|error|メンテナンス/i.test(title)||!!document.querySelector('[class*="error-page"],[class*="errorPage"]'),
    own_user_path:path(own),
    messages
  });
})()'''

# Coconala's smartphone DM page uses ``.bl_messages-list``/``.bl_message`` and
# ``/smartphone/direct_messages/<id>``.  Keep the legacy expression above for
# old pages, but make the collector prefer the same canonical message shape on
# the current page as well.
DM_THREAD_EXPRESSION = r'''(()=>{
  const title=document.title;
  const modern=!!document.querySelector('.bl_messages-list');
  const container=document.querySelector('.js_thread-wrapper')||document.querySelector('.bl_messages-list');
  const legacyRows=!modern&&container?[...container.querySelectorAll('.threadColomun')].filter(row=>row.querySelector('.threadMessage')):[];
  const rows=modern?[...container.querySelectorAll('.bl_message')]:legacyRows;
  const path=a=>{try{const u=new URL(a.href,location.origin),m=u.pathname.match(/^\/(?:users|smartphone\/users)\/([A-Za-z0-9_-]+)\/?$/);return u.origin==='https://coconala.com'&&m?`/users/${m[1]}`:null}catch(_){return null}};
  const absolute=value=>{try{return new URL(value,location.origin).href}catch(_){return null}};
  const ownLegacy=document.querySelector('.sidebar-profile a[href*="/users/"]');
  const own=path(ownLegacy)||'/users/0';
  const counterpart=((document.querySelector('.bl_direct-message-fixed-header')?.innerText||'').split('\n')[0]||'').trim()||null;
  const messages=rows.map(row=>{
    const mine=modern&&row.classList.contains('modi_my-message');
    const author=modern?row.querySelector('.user-icon[href*="/users/"],a[href*="/smartphone/users/"]'):row.querySelector('.threadUser a[href*="/users/"]');
    const time=modern?row.querySelector('.message-created'):row.querySelector('.threadPostTime');
    const body=row.querySelector('.js-translateMessageOriginalMessage')||(modern?row.querySelector('.message'):row.querySelector('.threadMessage'));
    const scope=modern?(row.querySelector('.comment-detail')||row):(row.querySelector('.threadMessage')||row);
    const attachments=[];
    const push=(url,filename)=>{if(!url||attachments.some(item=>item.url===url))return;attachments.push({url,filename:(filename||'').trim()||null});};
    [...scope.querySelectorAll('a[href]')].forEach(anchor=>{
      if(anchor.closest('.threadUser,.user-icon'))return;
      const href=absolute(anchor.getAttribute('href'));if(!href||/^(mailto:|javascript:)/i.test(anchor.getAttribute('href')||''))return;
      if(/\/users\//.test(href))return;
      if(/(?:uploaded_files|attachment|download|file|\.(?:png|jpe?g|gif|pdf|zip|xlsx?|docx?|pptx?|csv|txt|psd|ai|svg|mp4|mov))(?:[/?#]|$)/i.test(href)||!!anchor.getAttribute('download'))push(href,anchor.getAttribute('download')||anchor.innerText);
    });
    [...scope.querySelectorAll('img[src]')].forEach(image=>{if(image.closest('.threadUser,.user-icon'))return;const source=absolute(image.getAttribute('src'));if(source&&!/(?:coconala_profile|\/icon|avatar|emoji|blank\.(?:gif|png))/i.test(source))push(source,image.getAttribute('alt'));});
    return {message_id:row.getAttribute('data-message-id')||row.id||null,author_path:path(author)||(mine?own:null),author_name:((author&&author.innerText||'').trim()||(!mine?counterpart:'')||null),sent_at:(time&&time.innerText||'').trim()||null,body:(body&&body.innerText)||'',attachments};
  }).filter(row=>row.author_path);
  return JSON.stringify({url:location.href,title,container_present:!!container,not_found_present:/404|ページが見つかりません|お探しのページ/.test(title)||!!document.querySelector('[class*="not-found"],[class*="notFound"]'),error_present:/エラー|error|メンテナンス/i.test(title)||!!document.querySelector('[class*="error-page"],[class*="errorPage"]'),own_user_path:own,messages});
})()'''


class DmCollectError(ValueError):
    """The direct message could not be collected in a form we can trust."""


def collector_module():
    """The queue collector, loaded once: DefaultTab and inspect_message_page live there."""
    global _COLLECTOR
    if _COLLECTOR is None:
        spec = importlib.util.spec_from_file_location("coconala_queue_snapshot", COLLECTOR_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load coconala_queue_snapshot")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _COLLECTOR = module
    return _COLLECTOR


def canonical_thread_id(value: Any) -> str:
    text = str(value or "").strip()
    if not THREAD_ID.fullmatch(text):
        raise DmCollectError(f"invalid_thread_id:{text[:32]}")
    return text


def attachment_fetch_expression(urls: list[str]) -> str:
    """Fetch each attachment from inside the authenticated page.

    ``credentials: 'include'`` is the whole trick. A download driven from outside the
    page arrives without the session and Coconala answers with a login page, which is
    how "we captured the attachment" turns into a 4 KB HTML file that looks like a
    success. Here the bytes come back with their status and length, and the caller
    refuses anything that is not a 200.
    """
    if len(urls) > MAX_ATTACHMENTS:
        raise DmCollectError(f"too_many_attachments:{len(urls)}")
    payload = json.dumps(list(urls), ensure_ascii=False)
    return (
        "(async()=>{const urls=" + payload + ";const out=[];"
        "const encode=buffer=>{const bytes=new Uint8Array(buffer);let binary='';"
        "for(let index=0;index<bytes.length;index+=0x8000){"
        "binary+=String.fromCharCode.apply(null,bytes.subarray(index,index+0x8000));}"
        "return btoa(binary);};"
        "for(const url of urls){try{"
        "const response=await fetch(url,{credentials:'include',redirect:'follow'});"
        "const buffer=await response.arrayBuffer();"
        "out.push({url:url,status:response.status,final_url:response.url,"
        "content_type:response.headers.get('content-type'),bytes:buffer.byteLength,"
        f"data_base64:buffer.byteLength<={MAX_ATTACHMENT_BYTES}?encode(buffer):null}});"
        "}catch(error){out.push({url:url,error:String(error).slice(0,200)});}}"
        "return JSON.stringify(out);})()"
    )


def safe_filename(value: Any, url: str = "") -> str:
    """A filename that cannot escape ``source/dm``."""
    text = str(value or "").strip()
    if not text or text in {".", ".."}:
        text = os.path.basename(str(url or "").split("?", 1)[0].rstrip("/"))
    text = re.sub(r"[/\\\x00-\x1f]", "_", text).strip() or "attachment"
    if text in {".", ".."}:
        text = "attachment"
    return text[:120]


def thread_participants(dom: dict[str, Any]) -> list[dict[str, str]]:
    """Everyone in the thread who is not us."""
    own = str(dom.get("own_user_path") or "")
    seen: dict[str, dict[str, str]] = {}
    for message in dom.get("messages") or []:
        if not isinstance(message, dict):
            continue
        path = str(message.get("author_path") or "")
        if not path or path == own:
            continue
        seen.setdefault(path, {"user_path": path, "name": str(message.get("author_name") or "")})
    return list(seen.values())


def thread_matches_buyer(dom: dict[str, Any], buyer: str) -> bool:
    """Is this the thread with the buyer of the order we are working on?

    The order's ``buyer`` is the marketplace's own handle for the account, so the match
    is against the participant's ``/users/<handle>`` path and their displayed name --
    never against message text, which would match any thread that mentions them.
    """
    wanted = str(buyer or "").strip().casefold()
    if not wanted:
        return False
    for participant in thread_participants(dom):
        path = participant["user_path"].casefold().rstrip("/")
        if path.rsplit("/", 1)[-1] == wanted:
            return True
        if participant["name"].strip().casefold() == wanted:
            return True
    return False


def dm_thread_document(
    dom: dict[str, Any], thread_id: str, observed_at: str,
) -> dict[str, Any]:
    """Normalize one DM thread into the file the builder and the judge can read."""
    identity = canonical_thread_id(thread_id)
    if dom.get("not_found_present") or dom.get("error_present"):
        raise DmCollectError("dm_thread_unavailable")
    if not dom.get("container_present"):
        raise DmCollectError("dm_thread_container_missing")
    own = str(dom.get("own_user_path") or "")
    if not own:
        raise DmCollectError("dm_thread_identity_missing")
    messages: list[dict[str, Any]] = []
    for index, message in enumerate(dom.get("messages") or []):
        if not isinstance(message, dict):
            continue
        author = str(message.get("author_path") or "")
        if not author:
            raise DmCollectError("dm_message_author_missing")
        body = str(message.get("body") or "")[:MAX_BODY_CHARS]
        attachments: list[dict[str, Any]] = []
        for attachment in message.get("attachments") or []:
            if not isinstance(attachment, dict):
                continue
            url = str(attachment.get("url") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue
            attachments.append({
                "url": url,
                "filename": safe_filename(attachment.get("filename"), url),
            })
        messages.append({
            "index": index,
            "message_id": str(message.get("message_id") or "") or None,
            "side": "seller" if author == own else "buyer",
            "author_path": author,
            "author_name": str(message.get("author_name") or "") or None,
            "sent_at": str(message.get("sent_at") or "") or None,
            "text": body,
            "attachments": attachments,
        })
    if not messages:
        raise DmCollectError("dm_thread_empty")
    return {
        "version": 1,
        "source": "coconala_direct_message_dom",
        "thread_id": identity,
        "url": THREAD_URL.format(thread_id=identity),
        "observed_at": str(observed_at or ""),
        "own_user_path": own,
        "participants": thread_participants(dom),
        "message_count": len(messages),
        "messages": messages,
    }


def attachment_requests(document: dict[str, Any]) -> list[dict[str, str]]:
    """Every distinct attachment in the thread, in the order the buyer sent them."""
    requests: list[dict[str, str]] = []
    seen: set[str] = set()
    for message in document["messages"]:
        for attachment in message["attachments"]:
            if attachment["url"] in seen:
                continue
            seen.add(attachment["url"])
            requests.append({
                "url": attachment["url"],
                "filename": attachment["filename"],
                "side": message["side"],
            })
    return requests


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def store_attachments(
    project_root: Path, results: list[dict[str, Any]], requests: list[dict[str, str]],
    carried: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Write fetched bytes to ``source/dm/attachments`` and index what happened.

    A non-200, an empty body or an oversize file is recorded as an error rather than
    written: a login page saved under the buyer's filename is worse than no file, because
    the builder would read it as material. ``carried`` rows are files this project already
    holds; they keep their place in the index without being fetched again.
    """
    by_url = {str(request["url"]): request for request in requests}
    directory = Path(project_root).expanduser() / "source" / "dm" / "attachments"
    index: list[dict[str, Any]] = []
    fetched = {str(row.get("url") or ""): row for row in results if isinstance(row, dict)}
    # The index follows the thread, not the fetch: the builder reads it beside the
    # messages, so a carried file and a new one keep the order the buyer sent them in.
    for url in list(by_url) + [key for key in fetched if key not in by_url]:
        if carried and url in carried:
            index.append(carried[url])
            continue
        result = fetched.get(url)
        if result is None:
            # Requested, neither carried nor fetched. Saying so is the difference between
            # "the buyer sent nothing else" and "we stopped looking".
            index.append({
                "url": url, "filename": by_url[url]["filename"],
                "side": by_url[url].get("side", "unknown"), "error": "not_fetched",
            })
            continue
        request = by_url.get(url, {"filename": safe_filename(None, url), "side": "unknown"})
        row: dict[str, Any] = {
            "url": url,
            "filename": request["filename"],
            "side": request.get("side", "unknown"),
            "status": result.get("status"),
            "response_bytes": result.get("bytes"),
            "content_type": (str(result.get("content_type"))[:100] if result.get("content_type") else None),
        }
        encoded = result.get("data_base64")
        if result.get("error") or result.get("status") != 200 or not isinstance(encoded, str) or not encoded:
            response_bytes = result.get("bytes")
            if (
                result.get("status") == 200
                and not encoded
                and type(response_bytes) is int
                and response_bytes > MAX_ATTACHMENT_BYTES
            ):
                row["error"] = f"attachment_size_refused:{response_bytes}"
            else:
                row["error"] = str(result.get("error") or f"http_{result.get('status')}")
            index.append(row)
            continue
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            row["error"] = "attachment_decode_failed"
            index.append(row)
            continue
        if not payload or len(payload) > MAX_ATTACHMENT_BYTES:
            row["error"] = f"attachment_size_refused:{len(payload)}"
            index.append(row)
            continue
        digest = hashlib.sha256(payload).hexdigest()
        path = directory / f"{digest[:12]}-{request['filename']}"
        if not path.is_file() or path.stat().st_size != len(payload):
            _atomic_bytes(path, payload)
        row.update({"bytes": len(payload), "sha256": digest, "path": str(path)})
        index.append(row)
    return index


def persist_thread(
    project_root: Path, document: dict[str, Any], attachment_index: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write the thread body plus its attachment index; unchanged threads rewrite nothing."""
    root = Path(project_root).expanduser()
    if not root.is_dir():
        raise DmCollectError(f"project_root_missing:{root}")
    payload = {**document, "attachment_index": attachment_index}
    body = payload.copy()
    body.pop("observed_at", None)
    content_sha = hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    payload["content_sha256"] = content_sha
    path = root / "source" / "dm" / f"thread-{document['thread_id']}-full.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raw = ""
    if VAULT_POINTER in raw:
        # ``buyer-attachments`` has taken a credential out of this file and left a
        # pointer. Re-writing it from the live page would put the plaintext back into a
        # paying customer's project, which is the defect that skill exists to remove.
        return {
            "path": str(path), "written": False, "refused": "vaulted_document_present",
            "thread_id": document["thread_id"], "message_count": document["message_count"],
            "attachments_stored": sum(1 for row in attachment_index if row.get("sha256")),
            "attachment_errors": [row for row in attachment_index if row.get("error")],
            "content_sha256": content_sha,
        }
    try:
        existing = json.loads(raw) if raw else {}
    except ValueError:
        existing = {}
    written = not (isinstance(existing, dict) and existing.get("content_sha256") == content_sha)
    if written:
        if raw and not (isinstance(existing, dict) and isinstance(existing.get("messages"), list)):
            # A hand-made capture in some other shape. Keep it: it is the only record of
            # what a human saw, and this writer did not exist when it was made.
            path.replace(path.with_name(f"{path.stem}.legacy.json"))
        _atomic_json(path, payload)
    return {
        "path": str(path),
        "written": written,
        "thread_id": document["thread_id"],
        "message_count": document["message_count"],
        "attachments_stored": sum(1 for row in attachment_index if row.get("sha256")),
        "attachment_errors": [row for row in attachment_index if row.get("error")],
        "content_sha256": content_sha,
    }


def known_thread_id(project_root: Path) -> str | None:
    """The thread this project already collected, so discovery runs once per order."""
    directory = Path(project_root).expanduser() / "source" / "dm"
    try:
        names = sorted(entry.name for entry in directory.iterdir())
    except OSError:
        return None
    for name in names:
        matched = THREAD_FILENAME.match(name)
        if matched:
            return matched.group(1)
    return None


def inbox_thread_ids(dom: dict[str, Any]) -> list[str]:
    """Direct-message threads in the inbox, newest first, via the collector's normalizer."""
    rows = collector_module().inquiries_from_dom(dom)
    return [str(row["talkroom_id"]) for row in rows if THREAD_ID.fullmatch(str(row["talkroom_id"]))]


def _read_dom(helper: Path, url: str, expression: str, owner: str | None) -> Any:
    """One page, one expression, through the collector's own authenticated tab."""
    collector = collector_module()
    with collector.DefaultTab(helper, url, hidden=False, owner=owner) as tab:
        return asyncio.run(collector.inspect_message_page(tab.ws, expression, url))


def already_stored(project_root: Path, thread_id: str) -> dict[str, dict[str, Any]]:
    """Attachments this project already holds, by URL.

    Every pass re-reads the thread; re-downloading five megabytes of PNGs it already has
    would be the expensive way to learn nothing. Presence is checked on disk, not only in
    the index, so a deleted file is fetched again.
    """
    path = Path(project_root).expanduser() / "source" / "dm" / f"thread-{thread_id}-full.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    stored: dict[str, dict[str, Any]] = {}
    for row in (document.get("attachment_index") or []) if isinstance(document, dict) else []:
        if not isinstance(row, dict) or not row.get("sha256") or not row.get("path"):
            continue
        if Path(str(row["path"])).is_file():
            stored[str(row.get("url") or "")] = row
    return stored


def _read_thread(
    helper: Path, url: str, owner: str | None, fetch: bool, project_root: Path,
) -> tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Read the thread and fetch its new attachments inside one tab lifetime.

    Two visits would be two different moments: a message that arrives between them would
    appear in the index and not in the body, or the reverse.
    """
    collector = collector_module()
    thread_id = _thread_id_of(url)
    stored = already_stored(project_root, thread_id)
    with collector.DefaultTab(helper, url, hidden=False, owner=owner) as tab:
        dom = asyncio.run(collector.inspect_message_page(tab.ws, DM_THREAD_EXPRESSION, url))
        wanted = [
            row for row in attachment_requests(dm_thread_document(dom, thread_id, ""))
            if row["url"] not in stored
        ][:MAX_ATTACHMENTS]  # the overflow is indexed as not_fetched, never dropped silently
        if not fetch or not wanted:
            return dom, [], stored
        results = asyncio.run(collector.inspect_message_page(
            tab.ws, attachment_fetch_expression([row["url"] for row in wanted]), url,
        ))
    if not isinstance(results, list):
        raise DmCollectError("attachment_fetch_unparsable")
    return dom, results, stored


def _thread_id_of(url: str) -> str:
    return canonical_thread_id(str(url).rstrip("/").rsplit("/", 1)[-1])


def collect(
    *, helper: Path, project_root: Path, buyer: str, thread_id: str | None,
    observed_at: str, owner: str | None = None, fetch_attachments: bool = True,
    require_known_thread: bool = False,
) -> dict[str, Any]:
    """Find, read and store the buyer's DM thread for one project."""
    root = Path(project_root).expanduser()
    identity = thread_id or known_thread_id(root)
    inspected: list[str] = []
    if identity is None and require_known_thread:
        # Discovery opens every thread in the inbox, once per pass, forever, for an order
        # that may simply have no DM. The hourly loop asks for the cheap path: refresh a
        # thread we have already identified, and leave finding a new one to an explicit
        # run with --buyer or --thread-id.
        return {"ok": False, "error": "dm_thread_unknown", "discovery": "skipped"}
    if identity is None:
        inbox = _read_dom(helper, INBOX_URL, collector_module().MESSAGES_EXPRESSION, owner)
        for candidate in inbox_thread_ids(inbox):
            inspected.append(candidate)
            dom = _read_dom(
                helper, THREAD_URL.format(thread_id=candidate), DM_THREAD_EXPRESSION, owner,
            )
            if thread_matches_buyer(dom, buyer):
                identity = candidate
                break
        if identity is None:
            # Zero is a claim, not a value: say how we looked, so "no thread" and "the
            # inbox enumerator broke" cannot be told apart only by their silence.
            return {
                "ok": False, "error": "dm_thread_not_found", "buyer": buyer,
                "threads_inspected": inspected,
            }
    identity = canonical_thread_id(identity)
    url = THREAD_URL.format(thread_id=identity)
    dom, results, carried = _read_thread(helper, url, owner, fetch_attachments, root)
    document = dm_thread_document(dom, identity, observed_at)
    index = store_attachments(root, results, attachment_requests(document), carried)
    return {"ok": True, **persist_thread(root, document, index)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--buyer", default="")
    parser.add_argument("--thread-id")
    parser.add_argument("--observed-at", default="")
    parser.add_argument("--cdp-helper", type=Path,
                        default=BROWSER_DIR / "scripts" / "cdp_default_tab.py")
    parser.add_argument("--owner", default=os.environ.get("CLOAK_BROWSER_OWNER") or None)
    parser.add_argument("--no-attachments", action="store_true")
    parser.add_argument(
        "--require-known-thread", action="store_true",
        help="refresh an already identified thread only; never walk the inbox",
    )
    parser.add_argument("--evidence-output", type=Path)
    args = parser.parse_args(argv)
    if not args.buyer and not args.thread_id and not args.require_known_thread:
        raise SystemExit("either --buyer or --thread-id is required")
    result = collect(
        helper=args.cdp_helper,
        project_root=args.project_root,
        buyer=args.buyer,
        thread_id=args.thread_id,
        observed_at=args.observed_at,
        owner=args.owner,
        fetch_attachments=not args.no_attachments,
        require_known_thread=args.require_known_thread,
    )
    if args.evidence_output is not None:
        _atomic_json(args.evidence_output, result)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
