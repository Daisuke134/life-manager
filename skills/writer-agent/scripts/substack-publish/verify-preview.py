"""Verify Substack preview images in an ephemeral headless CloakBrowser context.

Usage: verify-preview.py <post_id> [max_on_screen_h=950] [audience=only_paid|everyone]
The context is launched here, seeded with the publication session cookie the managed
wrapper exports (SUBSTACK_SESSION_COOKIE), and closed on every path: no shared or personal
browser is attached (measure-sales.py / note-publish/publish-paid.py precedent).
A free (everyone) post has no paid-subscriber view, so only only_paid requires it.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from writer_runtime_paths import note_work_dir
from substack_paid_payload import AUDIENCES

PUB = os.environ.get("SUBSTACK_PUBLICATION", "").strip().rstrip("/")
if not PUB:
    raise SystemExit("SUBSTACK_PUBLICATION is required")
W = str(note_work_dir())


def verify_once(post_id: str, max_h: int, audience: str = "only_paid") -> int:
    paid = audience == "only_paid"
    cookie_header = os.environ.get("SUBSTACK_SESSION_COOKIE", "")
    cookies = []
    for item in cookie_header.split(";"):
        name, separator, value = item.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".substack.com", "path": "/"})
    if not cookies:
        raise RuntimeError("SUBSTACK_SESSION_COOKIE is required")
    from cloakbrowser import launch_context

    ctx = launch_context(headless=True, humanize=False, viewport={"width": 1000, "height": 1500})
    try:
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(f"https://{PUB}/publish/post/{post_id}", wait_until="domcontentloaded", timeout=40000)
        time.sleep(11)
        body = page.evaluate("document.body.innerText")
        if not isinstance(body, str) or len(body) < 200:
            raise RuntimeError("Substack editor did not load")
        opened = page.evaluate("""(()=>{const b=[...document.querySelectorAll('button,a,span,div')].find(x=>['プレビュー','Preview'].includes((x.textContent||'').trim()));if(!b)return false;b.click();return true;})()""")
        if opened is not True:
            raise RuntimeError("Substack preview could not be opened")
        time.sleep(6)
        page.evaluate("""(()=>{const m=document.querySelector('[data-testid=preview-modal]');const b=m&&[...m.querySelectorAll('button')].find(x=>['デスクトップ','Desktop'].includes(x.innerText.trim()));if(b&&!b.disabled)b.click();})()""")
        time.sleep(3)
        point = paid and page.evaluate("""(()=>{const b=document.querySelector('[data-testid=preview-modal] [data-testid=preview-sub-free]');if(!b||b.disabled)return null;const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
        if point:
            page.mouse.click(point['x'], point['y'])
            time.sleep(1)
            point = page.evaluate("""(()=>{const b=[...document.querySelectorAll('[role=menuitem]')].find(e=>/有料登録者|paid subscriber/i.test(e.innerText));if(!b)return null;const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
            if not point:
                raise RuntimeError("paid Substack preview unavailable")
            page.mouse.click(point['x'], point['y'])
        layout = None
        for _ in range(10):
            time.sleep(1)
            layout = page.evaluate("""(()=>{const m=document.querySelector('[data-testid=preview-modal]');const f=m?.querySelector('[data-testid=preview-iframe]');const d=f?.contentDocument;const desktop=m&&[...m.querySelectorAll('button')].find(e=>['Desktop','デスクトップ'].includes(e.innerText.trim()));if(!m||m.getBoundingClientRect().height<=0||!f||f.getBoundingClientRect().width<700||desktop?.dataset.state!=='active'""" + ("""||!m.querySelector('[data-testid=preview-sub-paid]')""" if paid else "") + """||!d||d.readyState!=='complete'||f.contentWindow.location.origin!==location.origin)return {ok:false};const imgs=[...d.querySelectorAll('img')];imgs.forEach(e=>e.loading='eager');if(imgs.some(e=>!e.complete||e.naturalWidth===0))return {ok:false};return {ok:true,sizes:imgs.map(e=>{const b=e.getBoundingClientRect();return [Math.round(b.width),Math.round(b.height)]}).filter(b=>b[1]>60)}})()""")
            if isinstance(layout, dict) and layout.get('ok') is True and layout.get('sizes'):
                break
        if not isinstance(layout, dict) or layout.get('ok') is not True:
            raise RuntimeError(f"{audience} desktop Substack preview unavailable")
        sizes = layout.get('sizes')
        if not isinstance(sizes, list) or not sizes:
            raise RuntimeError("Substack preview images were not measured")
        tall = [(width, height) for width, height in sizes if height > max_h]
        page.screenshot(path=str(Path(W) / f"preview-{post_id}.png"))
        print(f"preview post={post_id} images={len(sizes)} tallest={max(height for _, height in sizes)}px limit={max_h}px")
        return 1 if tall else 0
    finally:
        ctx.close()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: verify-preview.py <post_id> [max_on_screen_h=950] [audience]", file=sys.stderr)
        return 2
    audience = args[2] if len(args) > 2 else "only_paid"
    if audience not in AUDIENCES:
        print(f"verify-preview: unsupported audience {audience!r}", file=sys.stderr)
        return 2
    try:
        return verify_once(args[0], int(args[1]) if len(args) > 1 else 950, audience)
    except Exception as error:  # Playwright errors are not RuntimeError; every failure fails closed.
        print(f"preview unavailable: {type(error).__name__}: {error}", file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
