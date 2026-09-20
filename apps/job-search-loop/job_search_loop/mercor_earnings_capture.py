from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets


TOTAL_RE = re.compile(r"total earnings to date are\s*\$([0-9,]+(?:\.[0-9]{2})?)", re.I)


def earnings_surface_ready(text: str) -> bool:
    value = text.casefold()
    return TOTAL_RE.search(text) is not None and (
        "no payment history yet" in value
        or all(label in value for label in ("payments", "payout date", "earned"))
    )


def parse_earnings_text(text: str, *, observed_at: str, page_url: str) -> dict[str, Any]:
    parsed_url = urlsplit(page_url)
    if parsed_url.path.rstrip("/") != "/earnings" or re.search(r"\b(sign in|log in)\b", text, re.I):
        return {
            "status": "blocked",
            "reason": "earnings_surface_auth_unavailable",
            "page_url": page_url,
            "observed_at": observed_at,
        }
    total_match = TOTAL_RE.search(text)
    total = (total_match.group(1) if total_match else "0.00").replace(",", "")
    if "no payment history yet" in text.casefold():
        return {
            "provider": "mercor",
            "page_url": page_url,
            "observed_at": observed_at,
            "total_earnings_usd": total,
            "payment_history_status": "empty",
            "rows": [],
        }
    return {
        "status": "blocked",
        "reason": "payment_rows_require_structured_extraction",
        "page_url": page_url,
        "observed_at": observed_at,
    }


async def _call(ws: Any, counter: list[int], method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    counter[0] += 1
    request_id = counter[0]
    await ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        value = json.loads(await asyncio.wait_for(ws.recv(), 20))
        if value.get("id") == request_id:
            if "error" in value:
                raise RuntimeError(f"CDP {method} failed")
            return value.get("result", {})


async def capture(*, cdp_url: str, evidence_dir: Path, output: Path) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    evidence_dir.chmod(0o700)
    targets = json.loads(urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=10).read())
    page = next((item for item in targets if item.get("type") == "page" and "work.mercor.com" in item.get("url", "")), None)
    if not isinstance(page, dict) or not page.get("webSocketDebuggerUrl"):
        raise RuntimeError("owned Mercor page not found")
    async with websockets.connect(page["webSocketDebuggerUrl"], ping_interval=None, open_timeout=10, max_size=64 * 1024 * 1024) as ws:
        counter = [0]
        await _call(ws, counter, "Page.enable")
        await _call(ws, counter, "Page.navigate", {"url": "https://work.mercor.com/earnings"})
        for _ in range(240):
            state = await _call(ws, counter, "Runtime.evaluate", {"expression": "location.pathname === '/earnings' && document.readyState === 'complete'", "returnByValue": True})
            if state.get("result", {}).get("value") is True:
                break
            await asyncio.sleep(0.25)
        for _ in range(80):
            surface = await _call(
                ws,
                counter,
                "Runtime.evaluate",
                {"expression": "(document.body&&document.body.innerText)||''", "returnByValue": True},
            )
            if earnings_surface_ready(str(surface.get("result", {}).get("value", ""))):
                break
            await asyncio.sleep(0.25)
        observed_at = datetime.now(timezone.utc).isoformat()
        data = await _call(
            ws,
            counter,
            "Runtime.evaluate",
            {"expression": "({url:location.href,text:(document.body&&document.body.innerText)||'',html:document.documentElement.outerHTML})", "returnByValue": True},
        )
        value = data.get("result", {}).get("value", {})
        text = str(value.get("text", ""))
        page_url = str(value.get("url", "https://work.mercor.com/earnings"))
        (evidence_dir / "earnings-readback.txt").write_text(text + "\n", encoding="utf-8")
        (evidence_dir / "earnings-readback.html").write_text(str(value.get("html", "")), encoding="utf-8")
        shot = await _call(ws, counter, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (evidence_dir / "earnings-readback.png").write_bytes(base64.b64decode(shot["data"]))
    for path in evidence_dir.iterdir():
        path.chmod(0o600)
    snapshot = parse_earnings_text(text, observed_at=observed_at, page_url=page_url)
    snapshot.update(
        {
            "evidence_text": str(evidence_dir / "earnings-readback.txt"),
            "evidence_dom": str(evidence_dir / "earnings-readback.html"),
            "evidence_screenshot": str(evidence_dir / "earnings-readback.png"),
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9334")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    value = asyncio.run(capture(cdp_url=args.cdp, evidence_dir=args.evidence_dir, output=args.output))
    print(json.dumps({"status": value.get("status", value.get("payment_history_status")), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
