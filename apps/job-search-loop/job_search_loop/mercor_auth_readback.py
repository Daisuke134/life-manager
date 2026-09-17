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
    if authenticated_api_status == 200:
        # Some provider API edges accept an expired bearer and still return a
        # successful shell response. The Mercor SPA is authoritative here: an
        # expired Firebase record that was not refreshed cannot open Profile or
        # an application detail reliably.
        if firebase_token_expired is True and firebase_token_refreshed is not True:
            return "logged_out"
        if firebase_token_refresh_failed is True:
            return "indeterminate"
        return "authenticated"
    if firebase_token_expired is True:
        return "logged_out"
    if firebase_token_refresh_failed is True:
        return "indeterminate"
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
      let firebase_user_present=false;
      let authenticated_api_status=null;
      let firebase_token_expired=false;
      let firebase_token_refreshed=false;
      let firebase_token_refresh_failed=false;
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
                if(!response.ok) throw new Error('firebase_refresh_http_'+response.status);
                const payload=await response.json();
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
                firebase_token_refresh_failed=true;
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
        firebase_user_present,
        authenticated_api_status,
        firebase_token_expired,
        firebase_token_refreshed,
        firebase_token_refresh_failed
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
        result = await _call(ws, 1, "Runtime.evaluate", {
            "expression": auth_snapshot_expression(),
            "awaitPromise": True,
            "returnByValue": True,
        })
    value = json.loads(result.get("result", {}).get("value") or "{}")
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
        ),
        "url": url,
        "login_form_visible": value.get("login_form_visible") is True,
        "authenticated_navigation_visible": value.get("authenticated_navigation_visible") is True,
        "firebase_user_present": value.get("firebase_user_present") is True,
        "authenticated_api_status": value.get("authenticated_api_status"),
        "firebase_token_expired": value.get("firebase_token_expired") is True,
        "firebase_token_refreshed": value.get("firebase_token_refreshed") is True,
        "firebase_token_refresh_failed": value.get("firebase_token_refresh_failed") is True,
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
