"""Verify Substack preview images in one registered, owned CDP context.

Usage: verify-preview.py <post_id> [max_on_screen_h=950]
The existing browser guard owns the endpoint; every opened tab/context is reclaimed.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from writer_runtime_paths import note_work_dir

PUB = os.environ.get("SUBSTACK_PUBLICATION", "").strip().rstrip("/")
if not PUB:
    raise SystemExit("SUBSTACK_PUBLICATION is required")
W = str(note_work_dir())
BROWSER_ROOT = Path(__file__).resolve().parents[3] / "browser"


def verify_once(post_id: str, max_h: int) -> int:
    if not os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY") or not os.environ.get("CDP"):
        raise RuntimeError("registered browser lease is required")
    cookie_header = os.environ.get("SUBSTACK_SESSION_COOKIE", "")
    cookies = []
    for item in cookie_header.split(";"):
        name, separator, value = item.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".substack.com", "path": "/"})
    if not cookies:
        raise RuntimeError("SUBSTACK_SESSION_COOKIE is required")
    sys.path.insert(0, str(BROWSER_ROOT / "scripts"))
    import cdp
    import cdp_context_lease

    owner = f"writer-substack-preview-{os.getpid()}"
    lease = cdp_context_lease.acquire(owner, no_seed=True, create_target=False)
    if not lease.get("ok") or not lease.get("context_id"):
        raise RuntimeError("owned browser context unavailable")
    previous_context = os.environ.get("CLOAK_BROWSER_CONTEXT_ID")
    os.environ["CLOAK_BROWSER_CONTEXT_ID"] = lease["context_id"]
    target = None
    try:
        cdp._browser_call("Storage.setCookies", {"cookies": cookies, "browserContextId": lease["context_id"]})
        target = cdp.new_target("about:blank", owner=owner)
        socket = cdp._page(target)
        try:
            cdp._rpc(socket, 1, "Emulation.setDeviceMetricsOverride", {"width": 1000, "height": 1500, "deviceScaleFactor": 1, "mobile": False})
        finally:
            socket.close()
        cdp.navigate(target, f"https://{PUB}/publish/post/{post_id}")
        time.sleep(11)
        body = cdp.evaluate(target, "document.body.innerText")
        if not isinstance(body, str) or len(body) < 200:
            raise RuntimeError("Substack editor did not load")
        opened = cdp.evaluate(target, """(()=>{const b=[...document.querySelectorAll('button,a,span,div')].find(x=>['プレビュー','Preview'].includes((x.textContent||'').trim()));if(!b)return false;b.click();return true;})()""")
        if opened is not True:
            raise RuntimeError("Substack preview could not be opened")
        time.sleep(6)
        cdp.evaluate(target, """(()=>{const b=[...document.querySelectorAll('button,span,div,a')].find(x=>['デスクトップ','Desktop'].includes((x.textContent||'').trim()));if(b)b.click();})()""")
        time.sleep(4)
        sizes = cdp.evaluate(target, """(()=>{const r=[];document.querySelectorAll('img').forEach(im=>{const b=im.getBoundingClientRect();if(b.height>60)r.push([Math.round(b.width),Math.round(b.height)]);});return r;})()""")
        if not isinstance(sizes, list) or not sizes:
            raise RuntimeError("Substack preview images were not measured")
        tall = [(width, height) for width, height in sizes if height > max_h]
        cdp.screenshot(target, str(Path(W) / f"preview-{post_id}.png"))
        print(f"preview post={post_id} images={len(sizes)} tallest={max(height for _, height in sizes)}px limit={max_h}px")
        return 1 if tall else 0
    finally:
        try:
            if target is not None:
                cdp.close_target(target, owner=owner)
        finally:
            cdp_context_lease.release(owner, token=lease["token"], generation=lease["generation"])
            if previous_context is None:
                os.environ.pop("CLOAK_BROWSER_CONTEXT_ID", None)
            else:
                os.environ["CLOAK_BROWSER_CONTEXT_ID"] = previous_context


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: verify-preview.py <post_id> [max_on_screen_h=950]", file=sys.stderr)
        return 2
    if not os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY"):
        # Same registered identity as the existing Writer sales owner. BUSY defers;
        # it never starts another browser or attaches to an unverified localhost alias.
        return subprocess.run([
            "bash", str(BROWSER_ROOT / "with-browser.sh"), "interactive:dais", "--",
            sys.executable, str(Path(__file__).resolve()), *args,
        ], env={**os.environ, "BROWSER_WAIT_SECONDS": "0"}, check=False).returncode
    try:
        return verify_once(args[0], int(args[1]) if len(args) > 1 else 950)
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"preview unavailable: {type(error).__name__}: {error}", file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
