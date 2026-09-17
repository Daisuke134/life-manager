from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from urllib.parse import urlparse


_MISSING = object()


class DirectCDPPage:
    """A bounded, single-target CDP page from the shared Daily Driver lease."""

    def __init__(self, ws_url: str, target_id: str) -> None:
        self.ws_url = ws_url
        self.target_id = target_id
        self.url = "about:blank"
        self._ws: Any = None
        self._call_id = 0
        self._lock = asyncio.Lock()
        self._events: list[dict[str, Any]] = []
        self._closed = False

    async def connect(self) -> None:
        import websockets

        self._ws = await websockets.connect(
            self.ws_url,
            open_timeout=10,
            ping_interval=None,
            max_size=64 * 1024 * 1024,
        )
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        await self.call("DOM.enable")
        await self._ensure_viewport()
        self.url = str(await self.evaluate("() => location.href") or "about:blank")

    async def _ensure_viewport(self) -> None:
        await self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

    async def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 20
    ) -> dict[str, Any]:
        if self._ws is None or self._closed:
            raise RuntimeError("leased CDP page is not connected")
        async with self._lock:
            self._call_id += 1
            call_id = self._call_id
            await self._ws.send(
                json.dumps({"id": call_id, "method": method, "params": params or {}})
            )
            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError(f"CDP {method} did not answer within {timeout}s")
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
                message = json.loads(raw)
                if message.get("id") != call_id:
                    if isinstance(message.get("method"), str):
                        self._events.append(message)
                    continue
                if "error" in message:
                    raise RuntimeError(f"CDP {method}: {message['error']}")
                result = message.get("result")
                return result if isinstance(result, dict) else {}

    async def event(self, method: str, timeout: float = 20) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            for index, message in enumerate(self._events):
                if message.get("method") == method:
                    return self._events.pop(index).get("params") or {}
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"CDP event {method} did not arrive within {timeout}s")
            message = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=remaining))
            if message.get("method") == method:
                return message.get("params") or {}
            if isinstance(message.get("method"), str):
                self._events.append(message)

    async def evaluate(self, expression: str, arg: Any = _MISSING) -> Any:
        callable_expression = "=>" in expression or expression.lstrip().startswith(
            ("function", "async function")
        )
        if arg is _MISSING:
            source = f"({expression})()" if callable_expression else expression
        else:
            source = f"({expression})({json.dumps(arg)})"
        result = await self.call(
            "Runtime.evaluate",
            {
                "expression": source,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": False,
            },
        )
        remote = result.get("result") or {}
        if remote.get("subtype") == "error":
            raise RuntimeError(str(remote.get("description") or "page evaluation failed"))
        return remote.get("value")

    async def title(self) -> str:
        return str(await self.evaluate("() => document.title") or "")

    async def screenshot(self, **_: Any) -> bytes:
        await self._ensure_viewport()
        result = await self.call(
            "Page.captureScreenshot",
            {"format": "jpeg", "quality": 65, "captureBeyondViewport": False},
            timeout=30,
        )
        data = result.get("data")
        if not isinstance(data, str) or not data:
            raise RuntimeError("CDP screenshot is empty")
        return base64.b64decode(data)

    async def goto(self, url: str, **_: Any) -> None:
        await self.call("Page.navigate", {"url": url}, timeout=20)
        await self.wait_ready(require_https=True)

    async def wait_ready(self, timeout: float = 25, *, require_https: bool = False) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            state = await self.evaluate("() => document.readyState")
            current_url = str(await self.evaluate("() => location.href") or self.url)
            self.url = current_url
            parsed = urlparse(current_url)
            if (
                state in {"interactive", "complete"}
                and (not require_https or (parsed.scheme == "https" and bool(parsed.hostname)))
            ):
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("leased page navigation did not become ready")
            await asyncio.sleep(0.25)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        await asyncio.sleep(milliseconds / 1000)
        previous_url = self.url
        current_url = str(await self.evaluate("() => location.href") or previous_url)
        previous = urlparse(previous_url)
        if (
            current_url in {"", "about:blank"}
            and previous.scheme == "https"
            and bool(previous.hostname)
        ):
            await self.goto(previous_url)
            return
        self.url = current_url

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        if self._closed:
            return
        try:
            await self.call("Page.close", timeout=5)
        finally:
            self._closed = True
            if self._ws is not None:
                await self._ws.close()

    @staticmethod
    def _target_script(target: dict[str, Any], scroll: bool = False) -> str:
        target_json = json.dumps(target, ensure_ascii=False)
        scroll_source = "el.scrollIntoView({block:'center',inline:'center'});" if scroll else ""
        return f"""() => {{
          const target = {target_json};
          const visible = el => {{
            const s=getComputedStyle(el),r=el.getBoundingClientRect();
            return s.visibility!=='hidden' && s.display!=='none' && r.width>0 && r.height>0;
          }};
          const label = el => {{
            const own=el.getAttribute('aria-label')||el.getAttribute('title')||'';
            const linked=el.labels&&el.labels.length?Array.from(el.labels).map(x=>x.innerText).join(' '):'';
            const labelledBy=(el.getAttribute('aria-labelledby')||'').split(/\\s+/).filter(Boolean).map(id=>document.getElementById(id)?.innerText||'').join(' ');
            const relatedInput=el.closest('[data-automation-id="multiselectInputContainer"]')?.querySelector('input');
            const related=relatedInput&&relatedInput!==el?`${{label(relatedInput)}} options`:'';
            const fieldset=el.closest('fieldset');
            const fieldsetControls=fieldset
              ?Array.from(fieldset.querySelectorAll('input,select,textarea,button')).filter(visible)
              :[];
            const legend=fieldset?.querySelector(':scope > legend');
            const fieldsetLabel=fieldsetControls.length===1
              ?legend?.innerText?.trim()||(fieldset?.innerText||'')
                .split(/\\r?\\n/).map(line=>line.trim())
                .find(line=>line&&!/^error\\b/i.test(line))||''
              :'';
            return (own||linked||labelledBy||fieldsetLabel||el.getAttribute('placeholder')||el.innerText||related||'').trim();
          }};
          const semanticLabel = value => String(value || '').trim()
            .replace(/\\s+not checked$/i, '')
            .replace(/\\s+checked$/i, '')
            .replace(/,\\s*press delete to clear value\\.$/i, '');
          const role = el => el.getAttribute('role') || ({{A:'link',BUTTON:'button',SELECT:'combobox',TEXTAREA:'textbox'}}[el.tagName] || (el.tagName==='INPUT' ? (['checkbox','radio','button','submit'].includes(el.type)?el.type.replace('submit','button'):'textbox') : (getComputedStyle(el).cursor==='pointer'?'button':'')));
          let nodes=[];
          if (target.stable_id) {{
            const [kind,...rest]=target.stable_id.split(':');
            const attr={{automation:'data-automation-id',id:'id',ref:'data-anicca-ref'}}[kind];
            const value=rest.join(':');
            if (attr) nodes=Array.from(document.querySelectorAll(`[${{attr}}]`)).filter(el=>el.getAttribute(attr)===value);
          }}
          nodes=nodes.filter(el=>visible(el)&&!el.disabled&&el.getAttribute('aria-disabled')!=='true')
            .filter(el=>!target.role||role(el)===target.role);
          const resolvedByStableId=nodes.length===1;
          if (!resolvedByStableId) {{
            nodes=Array.from(document.querySelectorAll('input,button,select,textarea,a,[role],[data-automation-id]'));
          }}
          nodes=nodes.filter(el=>visible(el)&&!el.disabled&&el.getAttribute('aria-disabled')!=='true')
            .filter(el=>!target.role||role(el)===target.role)
            .filter(el=>{{
              if (resolvedByStableId) return true;
              const actual=semanticLabel(label(el)), wanted=semanticLabel(target.label);
              return target.exact?actual===wanted:actual.includes(wanted);
            }});
          const index=target.ordinal==null?0:target.ordinal-1;
          if ((target.ordinal==null&&nodes.length!==1)||index<0||index>=nodes.length) return {{ok:false,count:nodes.length}};
          const el=nodes[index]; {scroll_source}
          const r=el.getBoundingClientRect();
          return {{ok:true,count:nodes.length,x:r.left+r.width/2,y:r.top+r.height/2,tag:el.tagName,type:el.type||'',option_index:el.tagName==='SELECT'?Array.from(el.options).findIndex(o=>o.textContent.trim()===target.option_label):-1}};
        }}"""

    async def resolve_target(
        self, target: dict[str, Any], *, scroll: bool = False, option_label: str | None = None
    ) -> dict[str, Any]:
        value = dict(target)
        value["option_label"] = option_label
        result = await self.evaluate(self._target_script(value, scroll=scroll))
        if not isinstance(result, dict) or not result.get("ok"):
            count = result.get("count") if isinstance(result, dict) else None
            raise RuntimeError(f"action target must resolve to exactly one visible enabled control (count={count})")
        return result

    async def click_target(self, target: dict[str, Any]) -> None:
        before_url = self.url
        resolved = await self.resolve_target(target, scroll=True)
        x, y = float(resolved["x"]), float(resolved["y"])
        await self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await self.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        try:
            await self.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        except TimeoutError:
            # The input event is already on the wire. Retrying could advance an
            # SPA twice, so preserve at-most-once delivery and observe instead.
            pass
        # Provider SPAs often validate and rerender the next step well after the
        # mouse event returns.  Capture the post-action state only after that
        # bounded transition window, otherwise the model receives stale controls.
        await asyncio.sleep(1.5)
        self.url = str(await self.evaluate("() => location.href") or self.url)
        if self.url != before_url:
            await self.wait_ready()
            await self._ensure_viewport()
            await asyncio.sleep(0.25)

    async def type_target(self, target: dict[str, Any], text: str) -> None:
        resolved = await self.resolve_target(target, scroll=True)
        x, y = float(resolved["x"]), float(resolved["y"])
        await self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await self.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await self.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        selected = await self.evaluate("""() => {
          const el = document.activeElement;
          if (!el || !['INPUT', 'TEXTAREA'].includes(el.tagName)) return false;
          if (el.value.length === 0) return document.activeElement === el;
          if (typeof el.select !== 'function') return false;
          el.select();
          return el.selectionStart === 0 && el.selectionEnd === el.value.length;
        }""")
        if not selected:
            raise RuntimeError("visible text target did not accept whole-value selection")
        modifiers = 4  # Meta on macOS Chromium.
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Meta", "code": "MetaLeft", "modifiers": modifiers})
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": modifiers})
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": modifiers})
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Meta", "code": "MetaLeft"})
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace"})
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace"})
        await self.call("Input.insertText", {"text": text})
        # Controlled inputs and async pickers commonly render their option
        # surface on the next task after the input event.  Let that ordinary
        # UI work settle before the post-action observation is captured.
        await asyncio.sleep(0.75)

    async def select_target(self, target: dict[str, Any], label: str) -> None:
        resolved = await self.resolve_target(target, scroll=True, option_label=label)
        option_index = int(resolved.get("option_index", -1))
        if option_index < 0:
            raise RuntimeError("visible select does not contain the requested option")
        await self.click_target(target)
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Home", "code": "Home"})
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Home", "code": "Home"})
        for _ in range(option_index):
            await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowDown", "code": "ArrowDown"})
            await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowDown", "code": "ArrowDown"})
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter"})
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter"})

    async def upload_target(self, target: dict[str, Any], file_path: str) -> None:
        await self.call("Page.setInterceptFileChooserDialog", {"enabled": True})
        await self.click_target(target)
        chooser = await self.event("Page.fileChooserOpened", timeout=20)
        backend_node_id = chooser.get("backendNodeId")
        if not isinstance(backend_node_id, int):
            raise RuntimeError("file chooser did not expose a backend node")
        await self.call("DOM.setFileInputFiles", {"files": [file_path], "backendNodeId": backend_node_id})
        await self.call("Page.setInterceptFileChooserDialog", {"enabled": False})

    async def scroll(self, delta_y: int) -> None:
        await self.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 1, "y": 1, "deltaX": 0, "deltaY": delta_y})
