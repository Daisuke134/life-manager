"""Prove Mercor authentication before persisting provider session state."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import websockets

from .mercor_page_ready import _call


def classify_auth_snapshot(
    *,
    url: object,
    visible_text: object,
    login_form_visible: object = None,
    authenticated_navigation_visible: object = None,
    authenticated_api_status: object = None,
    firebase_token_expired: object = None,
    firebase_token_refreshed: object = None,
    firebase_token_refresh_failed: object = None,
    firebase_token_refresh_invalid: object = None,
    firebase_navigation_verified: object = None,
) -> str:
    if not isinstance(url, str) or not isinstance(visible_text, str):
        return "indeterminate"
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "work.mercor.com":
        return "indeterminate"
    text = visible_text.casefold()
    if authenticated_api_status == 403:
        # A forbidden endpoint can be a provider permission/CORS boundary, not
        # an expired Firebase session. Do not send a magic link on that signal.
        return "indeterminate"
    if authenticated_api_status == 401:
        return "logged_out"
    if login_form_visible is True:
        return "logged_out"
    if firebase_token_refresh_failed is True:
        return "indeterminate"
    if firebase_token_refresh_invalid is True:
        return "logged_out"
    if firebase_token_refreshed is True and firebase_navigation_verified is False:
        return "indeterminate"
    if authenticated_api_status == 200:
        # Some provider API edges accept an expired bearer and still return a
        # successful shell response. The Mercor SPA is authoritative here: an
        # expired Firebase record that was not refreshed cannot open Profile or
        # an application detail reliably.
        if firebase_token_expired is True and firebase_token_refreshed is not True:
            return "logged_out"
        return "authenticated"
    if firebase_token_expired is True and firebase_token_refreshed is not True:
        return "logged_out"
    # Navigation and content can render before Firebase hydration. Without an
    # authenticated API readback this wake must remain retryable, not logged out.
    if parsed.path.startswith("/jobs/apply/") and "application" in text and any(
        marker in text
        for marker in (
            "upload resume",
            "work authorization",
            "submit application",
            "your application has been submitted",
            "view application",
        )
    ):
        return "indeterminate"
    if "profile" in text and ("earnings" in text or "applications" in text or "explore" in text):
        return "indeterminate"
    return "indeterminate"


def auth_snapshot_expression() -> str:
    return """(async()=>{
      const visible=(element)=>{
        if(!element) return false;
        const style=getComputedStyle(element);
        const rect=element.getBoundingClientRect();
        return style.display!=='none' && style.visibility!=='hidden' &&
          style.opacity!=='0' && rect.width>0 && rect.height>0;
      };
      const email=[...document.querySelectorAll('input[type="email"],input[name="email"]')]
        .find(visible);
      const login=[...document.querySelectorAll('button,[role="button"]')]
        .find(button=>visible(button) && (button.innerText||'').trim()==='Login');
      const labels=new Set([...document.querySelectorAll('a,button,[role="link"],[role="button"]')]
        .filter(visible)
        .map(element=>(element.innerText||element.getAttribute('aria-label')||'').trim())
        .filter(label=>['Explore','Applications','Earnings','Profile'].includes(label)));
      const profile_surface_visible=location.pathname.startsWith('/profile') &&
        visible(document.querySelector('textarea#summary')) &&
        visible(document.querySelector('input[type="email"]')) &&
        document.querySelectorAll('[role="tab"]').length>=3;
      let firebase_user_present=false;
      let authenticated_api_status=null;
      let firebase_token_expired=false;
      let firebase_token_refreshed=false;
      let firebase_token_refresh_failed=false;
      let firebase_token_refresh_invalid=false;
      try {
        const request=indexedDB.open('firebaseLocalStorageDb');
        const db=await new Promise((resolve,reject)=>{
          request.onerror=()=>reject(request.error||new Error('firebase_idb_open_failed'));
          request.onsuccess=()=>resolve(request.result);
        });
        if(db.objectStoreNames.contains('firebaseLocalStorage')){
          const values=await new Promise((resolve,reject)=>{
            const get=db.transaction('firebaseLocalStorage','readonly')
              .objectStore('firebaseLocalStorage').getAll();
            get.onerror=()=>reject(get.error||new Error('firebase_idb_read_failed'));
            get.onsuccess=()=>resolve(get.result||[]);
          });
          const records=Array.isArray(values)?values:[];
          let token='';
          for(let index=0; index<records.length; index+=1){
            const entry=records[index];
            const candidate=entry?.value && typeof entry.value==='object' ? entry.value : entry;
            const manager=candidate?.stsTokenManager;
            const expiration=Number(manager?.expirationTime)||0;
            if(expiration>0 && expiration<=Date.now()) firebase_token_expired=true;
            const refreshDue=expiration>0 && expiration<=Date.now()+60000;
            if(refreshDue && manager?.refreshToken && candidate?.apiKey){
              try {
                const controller=new AbortController();
                const timer=setTimeout(()=>controller.abort(),5000);
                let response;
                try {
                  response=await fetch(
                    'https://securetoken.googleapis.com/v1/token?key='+encodeURIComponent(candidate.apiKey),
                    {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
                     body:new URLSearchParams({grant_type:'refresh_token',refresh_token:manager.refreshToken}),
                     credentials:'omit',signal:controller.signal}
                  );
                } finally { clearTimeout(timer); }
                let payload={};
                try { payload=await response.json(); } catch(error) { payload={}; }
                if(!response.ok){
                  const message=String(payload?.error?.message||'').toUpperCase();
                  if(['TOKEN_EXPIRED','INVALID_REFRESH_TOKEN','USER_DISABLED','USER_NOT_FOUND','INVALID_GRANT']
                    .some(marker=>message.includes(marker))) firebase_token_refresh_invalid=true;
                  throw new Error('firebase_refresh_http_'+response.status);
                }
                const accessToken=payload?.id_token||payload?.access_token||'';
                const expiresIn=Number(payload?.expires_in)||0;
                if(!accessToken || expiresIn<=0) throw new Error('firebase_refresh_response_invalid');
                const nextValue={...candidate,stsTokenManager:{...manager,
                  accessToken,refreshToken:payload?.refresh_token||manager.refreshToken,
                  expirationTime:Date.now()+expiresIn*1000}};
                const nextRecord=entry?.value && typeof entry.value==='object'
                  ? {...entry,value:nextValue} : nextValue;
                await new Promise((resolve,reject)=>{
                  let transaction;
                  try {
                    transaction=db.transaction('firebaseLocalStorage','readwrite');
                    transaction.objectStore('firebaseLocalStorage').put(nextRecord);
                  } catch(error) { reject(error); return; }
                  transaction.oncomplete=()=>resolve();
                  transaction.onerror=()=>reject(transaction.error||new Error('firebase_idb_write_failed'));
                  transaction.onabort=()=>reject(transaction.error||new Error('firebase_idb_write_aborted'));
                });
                records[index]=nextRecord;
                firebase_token_refreshed=true;
                firebase_token_expired=false;
              } catch(error) {
                if(!firebase_token_refresh_invalid) firebase_token_refresh_failed=true;
              }
            }
            if(firebase_token_refreshed) break;
          }
          const tokenFrom=value=>value?.stsTokenManager?.accessToken||
            value?.value?.stsTokenManager?.accessToken||value?.accessToken||
            value?.value?.accessToken||'';
          token=records.map(tokenFrom).find(Boolean)||'';
          firebase_user_present=!!token;
          if(token && (!firebase_token_expired || firebase_token_refreshed)){
            const controller=new AbortController();
            const timer=setTimeout(()=>controller.abort(),5000);
            try {
              const response=await fetch(
                'https://coil.mercor.com/v1/notifications?limit=1&filter=all',
                {headers:{Authorization:'Bearer '+token}, credentials:'omit', signal:controller.signal}
              );
              authenticated_api_status=response.status;
            } catch(error) { authenticated_api_status=null; }
            clearTimeout(timer);
          }
        }
        db.close();
      } catch(error) { /* hydration/API failure remains indeterminate */ }
      return JSON.stringify({
        url:location.href,
        text:(document.body?.innerText||'').slice(0,20000),
        login_form_visible:!!email && !!login,
        authenticated_navigation_visible:labels.size>=2,
        profile_surface_visible,
        firebase_user_present,
        authenticated_api_status,
        firebase_token_expired,
        firebase_token_refreshed,
        firebase_token_refresh_failed,
        firebase_token_refresh_invalid
      });
    })()"""


async def observe(ws_url: str) -> dict[str, object]:
    parsed = urlsplit(ws_url)
    if parsed.scheme not in {"ws", "wss"} or parsed.hostname not in {
        "127.0.0.1", "localhost", "::1",
    }:
        raise ValueError("leased_page_websocket_must_be_loopback")
    async with websockets.connect(
        ws_url, open_timeout=10, ping_interval=None, max_size=8 * 1024 * 1024
    ) as ws:
        async def evaluate(request_id: int) -> dict[str, object]:
            result = await _call(ws, request_id, "Runtime.evaluate", {
                "expression": auth_snapshot_expression(),
                "awaitPromise": True,
                "returnByValue": True,
            })
            return json.loads(result.get("result", {}).get("value") or "{}")

        value = await evaluate(1)
        # Writing IndexedDB restores the durable Firebase record but does not
        # update the SPA's in-memory currentUser. Reload only when this exact
        # readback refreshed the record. Then open Profile and return to the
        # original page; that route is the provider-backed proof that the SPA's
        # Firebase auth observer rehydrated, not just that IndexedDB and a
        # manually supplied bearer token look valid.
        original_url = value.get("url")
        original_parsed = urlsplit(original_url) if isinstance(original_url, str) else None
        if (
            value.get("firebase_token_refreshed") is True
            and value.get("login_form_visible") is not True
            and original_parsed is not None
            and original_parsed.scheme == "https"
            and original_parsed.hostname == "work.mercor.com"
        ):
            async def wait_for_page(request_id_start: int) -> None:
                for index in range(80):
                    state = await _call(ws, request_id_start + index, "Runtime.evaluate", {
                        "expression": "JSON.stringify({url:location.href,ready:document.readyState,hasBody:!!document.body})",
                        "returnByValue": True,
                    })
                    raw_state = state.get("result", {}).get("value")
                    state_value = json.loads(raw_state or "{}")
                    state_url = state_value.get("url")
                    state_parsed = urlsplit(state_url) if isinstance(state_url, str) else None
                    if (
                        state_parsed is not None
                        and state_parsed.scheme == "https"
                        and state_parsed.hostname == "work.mercor.com"
                        and state_value.get("ready") == "complete"
                        and state_value.get("hasBody") is True
                    ):
                        return
                    await asyncio.sleep(0.25)
                raise RuntimeError("mercor_auth_rehydrate_not_ready")

            try:
                await _call(ws, 2, "Page.reload", {"ignoreCache": True})
                await wait_for_page(10)
                await evaluate(200)
                await _call(ws, 300, "Page.navigate", {
                    "url": "https://work.mercor.com/profile?tab=resume",
                })
                await wait_for_page(310)
                profile = await evaluate(400)
                profile_url = profile.get("url")
                profile_parsed = urlsplit(profile_url) if isinstance(profile_url, str) else None
                profile_ok = (
                    profile_parsed is not None
                    and profile_parsed.scheme == "https"
                    and profile_parsed.hostname == "work.mercor.com"
                    and profile_parsed.path.startswith("/profile")
                    and profile.get("login_form_visible") is False
                    and profile.get("profile_surface_visible") is True
                    and profile.get("firebase_user_present") is True
                    and profile.get("authenticated_api_status") == 200
                )
                if not profile_ok:
                    profile["firebase_navigation_verified"] = False
                    profile["firebase_profile_readback_verified"] = False
                    profile["firebase_token_refresh_failed"] = True
                    value = profile
                else:
                    await _call(ws, 500, "Page.navigate", {"url": original_url})
                    await wait_for_page(510)
                    value = await evaluate(600)
                    value["firebase_navigation_verified"] = True
                    value["firebase_profile_readback_verified"] = True
            except Exception:
                value["firebase_token_refresh_failed"] = True
                value["firebase_navigation_verified"] = False
                value["firebase_profile_readback_verified"] = False
    url = value.get("url", "")
    return {
        "status": classify_auth_snapshot(
            url=url,
            visible_text=value.get("text"),
            login_form_visible=value.get("login_form_visible"),
            authenticated_navigation_visible=value.get("authenticated_navigation_visible"),
            authenticated_api_status=value.get("authenticated_api_status"),
            firebase_token_expired=value.get("firebase_token_expired"),
            firebase_token_refreshed=value.get("firebase_token_refreshed"),
            firebase_token_refresh_failed=value.get("firebase_token_refresh_failed"),
            firebase_token_refresh_invalid=value.get("firebase_token_refresh_invalid"),
            firebase_navigation_verified=value.get("firebase_navigation_verified"),
        ),
        "url": url,
        "login_form_visible": value.get("login_form_visible") is True,
        "authenticated_navigation_visible": value.get("authenticated_navigation_visible") is True,
        "profile_surface_visible": value.get("profile_surface_visible") is True,
        "firebase_user_present": value.get("firebase_user_present") is True,
        "authenticated_api_status": value.get("authenticated_api_status"),
        "firebase_token_expired": value.get("firebase_token_expired") is True,
        "firebase_token_refreshed": value.get("firebase_token_refreshed") is True,
        "firebase_token_refresh_failed": value.get("firebase_token_refresh_failed") is True,
        "firebase_token_refresh_invalid": value.get("firebase_token_refresh_invalid") is True,
        "firebase_navigation_verified": value.get("firebase_navigation_verified"),
        "firebase_profile_readback_verified": value.get("firebase_profile_readback_verified"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = asyncio.run(observe(args.ws))
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "authenticated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
