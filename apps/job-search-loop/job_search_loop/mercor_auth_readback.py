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
) -> str:
    if not isinstance(url, str) or not isinstance(visible_text, str):
        return "indeterminate"
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "work.mercor.com":
        return "indeterminate"
    text = visible_text.casefold()
    if login_form_visible is True:
        return "logged_out"
    if authenticated_api_status == 401:
        return "logged_out"
    if authenticated_api_status == 403:
        # A forbidden endpoint can be a provider permission/CORS boundary, not
        # an expired Firebase session. Do not send a magic link on that signal.
        return "indeterminate"
    if authenticated_api_status == 200:
        return "authenticated"
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
          const tokenFrom=value=>value?.stsTokenManager?.accessToken||
            value?.value?.stsTokenManager?.accessToken||value?.accessToken||
            value?.value?.accessToken||'';
          const token=(Array.isArray(values)?values:[]).map(tokenFrom).find(Boolean)||'';
          firebase_user_present=!!token;
          if(token){
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
        authenticated_api_status
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
        ),
        "url": url,
        "login_form_visible": value.get("login_form_visible") is True,
        "authenticated_navigation_visible": value.get("authenticated_navigation_visible") is True,
        "firebase_user_present": value.get("firebase_user_present") is True,
        "authenticated_api_status": value.get("authenticated_api_status"),
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
