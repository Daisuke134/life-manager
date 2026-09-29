#!/usr/bin/env python3
"""
drive_cp1.py — automated Capafy CP1 (Agent Card) for a NEW run_online subscription
listing, with EVERY gotcha cracked on O1 (2026-06-26) baked in.

THE GOTCHAS (all handled below):
 1. RHF staleness  -> use Playwright element.fill()/.type(), NEVER evaluate native value-setters.
 2. React synthetic-click ignored -> real page.mouse.click(coords) for tabs/cards.
 3. duplicate title -> 提出を確認 silently no-ops. Caller MUST pass a UNIQUE title.
 4. 下書きを保存 persists fields w/o full validation (we save-draft before final submit).
 5. 収益化モデル: click "Capafy で実行" heading text (left+20), not the card div.
 6. Subscription billing card is BELOW Hourly -> scrollIntoView first.
 7. AI service provider field (placeholder 例: OpenAI、Anthropic…) is REQUIRED.
 8. On-Demand container mode select.
 9. EVERY plan needs a trial choice (Enable/No). Unselected = price-tab red ✗ = no-op.
10. validate price tab via its <svg> color: green rgb(61,220,132)=ok, red rgb(229,83,75)=bad.
11. success = toast "カードを保存しました" or url=card-done.

Usage: drive_cp1.py <config.json>
config.json: {
  "edit_url": "...&page=edit",      # from publish-refresh-url --step init token
  "title","short","welcome","detailed","privacy_url","support_email",
  "tags": [...], "category": "ライティング", "icon": "/path.png", "model": "Claude Sonnet 4.6",
  "test_input": "...", "provider": "openrouter.ai",
  "plans": [ {"cycle":"day","price":"2.99","cap":"15","trial":null},
             {"cycle":"week","price":"5.99","cap":"45","trial":24},
             {"cycle":"month","price":"19.99","cap":"120","trial":72} ]
}
Prints SAVED on success (card-done), else NOT-SAVED + the price-tab svg color.
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

CDP = "http://localhost:9222"


def coords(pg, text, exact=True, top_max=900):
    return pg.evaluate(
        """(a)=>{const[t,ex,tm]=a;const e=[...document.querySelectorAll('*')].find(x=>{const s=(x.textContent||'').trim();return (ex?s===t:s.startsWith(t))&&x.getBoundingClientRect().height<46&&x.getBoundingClientRect().top<tm;});if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:Math.round(r.left+20),y:Math.round(r.top+r.height/2)};}""",
        [text, exact, top_max])


def click_text(pg, text, exact=True):
    c = coords(pg, text, exact)
    if c:
        pg.mouse.click(c["x"], c["y"]); return True
    return False


def tab_click(pg, name):
    """Switch a top tab via Playwright locator — this real click is what MOUNTS
    the lazy React form (evaluate/coords clicks do NOT trigger the render)."""
    try:
        pg.get_by_text(name, exact=True).first.click(); return True
    except Exception:
        return click_text(pg, name)


def price_svg_green(pg):
    return "61, 220, 132" in (pg.evaluate(
        """()=>{const el=[...document.querySelectorAll('button')].find(e=>(e.textContent||'').trim()==='価格設定');return el?[...el.querySelectorAll('svg')].map(s=>getComputedStyle(s).color).join(','):'';}""") or "")


def main():
    cfg = json.load(open(sys.argv[1]))
    pw = sync_playwright().start()
    br = pw.chromium.connect_over_cdp(CDP)
    ctx = br.contexts[0]
    pg = ctx.new_page()
    pg.goto(cfg["edit_url"], wait_until="domcontentloaded", timeout=55000); time.sleep(6)

    # ---- 基本情報 (RHF element.fill / .type) ----
    # ★ The form fields lazy-mount ONLY after a Playwright locator click on the
    #   基本情報 tab (evaluate/coords clicks don't trigger the React render). ★
    ti = None
    for i in range(8):
        tab_click(pg, "基本情報"); time.sleep(2.5)
        ti = pg.query_selector("input[placeholder*='Agent']")
        if ti:
            break
    if not ti:
        print("ERR: title input not found (form did not mount)"); sys.exit(1)
    ti.click(); ti.fill(""); ti.type(cfg["title"], delay=8)
    tas = pg.query_selector_all("textarea")
    tas[0].click(); tas[0].fill(cfg["short"])
    tas[1].click(); tas[1].fill(cfg["detailed"])
    pu = pg.query_selector("input[type=url]")
    if pu: pu.click(); pu.fill(cfg.get("privacy_url", "https://aniccaai.com/privacy"))
    em = pg.query_selector("input[type=email]")
    if em and not (em.input_value() or ""): em.click(); em.fill(cfg.get("support_email", "contact@aniccaai.com"))
    th = pg.query_selector("input[placeholder*='Enter'], input[placeholder*='追加']")
    if th:
        for tg in cfg.get("tags", []):
            th.click(); th.fill(tg); th.press("Enter"); time.sleep(0.2)
    # category
    pg.evaluate("""()=>{const l=[...document.querySelectorAll('*')].find(e=>(e.textContent||'').trim()==='メインカテゴリ');if(l)l.scrollIntoView({block:'center'});}"""); time.sleep(0.4)
    cc = pg.evaluate("""()=>{const lbl=[...document.querySelectorAll('*')].find(e=>(e.textContent||'').trim()==='メインカテゴリ');if(!lbl)return null;const ly=lbl.getBoundingClientRect().bottom;const c=[...document.querySelectorAll('div,button,span')].filter(e=>{const t=(e.textContent||'').trim();const r=e.getBoundingClientRect();return t.length<14&&t.length>1&&r.width>90&&r.width<360&&r.height>24&&r.height<56&&r.top>ly-5&&r.top<ly+70&&r.left<560;});if(!c.length)return null;const r=c[0].getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}""")
    if cc:
        pg.mouse.click(cc["x"], cc["y"]); time.sleep(0.9)
        o = pg.evaluate("""(cat)=>{const e=[...document.querySelectorAll('[role=option],li,div,span')].find(x=>(x.textContent||'').trim()===cat&&x.getBoundingClientRect().height<50);if(e){e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}return null;}""", cfg["category"])
        if o: pg.mouse.click(o["x"], o["y"]); time.sleep(0.6)
    # icon
    if cfg.get("icon"):
        fis = pg.query_selector_all("input[type=file]")
        if fis:
            fis[0].set_input_files(cfg["icon"]); time.sleep(4)
            cb = pg.evaluate("""()=>{const b=[...document.querySelectorAll('button')].find(e=>(e.textContent||'').trim()==='保存'&&e.getBoundingClientRect().width<200);if(b){const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}return null;}""")
            if cb: pg.mouse.click(cb["x"], cb["y"]); time.sleep(3)
    # bank basic info
    click_text(pg, "下書きを保存"); time.sleep(3)

    # ---- 価格設定 ----
    tab_click(pg, "価格設定"); time.sleep(2.5)
    pg.evaluate("window.scrollTo(0,150)"); time.sleep(0.4)
    click_text(pg, "Capafy で実行"); time.sleep(1.5)            # monetization
    click_text(pg, "On-Demand"); time.sleep(1)                  # container mode
    # Subscription billing (below Hourly -> scroll)
    pg.evaluate("""()=>{const e=[...document.querySelectorAll('*')].find(x=>(x.textContent||'').trim()==='Subscription'&&x.getBoundingClientRect().height<40);if(e)e.scrollIntoView({block:'center'});}"""); time.sleep(0.8)
    click_text(pg, "Subscription"); time.sleep(2)

    # ★ GOTCHA 12 (found 2026-07-05): the "Period" dropdown is a CUSTOM button
    #   (button.pricingConfigDropdownButton opening a text-option listbox), NOT a
    #   native <select>. Every plan card defaults to "Monthly" -> if left alone,
    #   2+ plans silently collide on "Monthly" (site shows "重複するプランは追加
    #   できません") and price-tab stays red forever. Detect plan CARDS via the
    #   '無料トライアル' trial-section anchor. Card POSITION/ORDER in the DOM is
    #   NOT stable across a period change (the form appears to re-sort/re-render
    #   plan cards), so array-index bookkeeping across separate passes silently
    #   mismatches price<->period. Fix: process one card fully (period -> price ->
    #   cap -> trial, all in one go) before touching the next, and always locate
    #   the target card by its CURRENT period-button text (unique at each step),
    #   never by array position held across a mutating click. ★
    plans = cfg["plans"]
    CYCLE_LABEL = {"day": "Daily", "week": "Weekly", "month": "Monthly", "year": "Yearly"}

    # A height range is unreliable (a card grows once "Enable Free Trial" reveals
    # extra fields), and the smallest text-matching element is just a label span
    # (doesn't contain the period button). The real per-card anchor: the MINIMAL
    # element that contains BOTH a period dropdown button AND the trial-section
    # text — exactly one such element per real plan card, any size.
    CARDS_JS = "[...document.querySelectorAll('*')].filter(e=>e.querySelector('button.pricingConfigDropdownButton')&&(e.textContent||'').includes('無料トライアル'))"

    def plan_block_count():
        return pg.evaluate(f"()=>{{const c={CARDS_JS};return c.filter(e=>!c.some(o=>o!==e&&e.contains(o))).length;}}")

    def find_block_by_period(period_text):
        h = pg.evaluate_handle(
            "(w)=>{const c=" + CARDS_JS + ";const blocks=c.filter(e=>!c.some(o=>o!==e&&e.contains(o)));for(const b of blocks){const btn=b.querySelector('button.pricingConfigDropdownButton');if(btn&&btn.textContent.trim()===w)return b;}return null;}",
            period_text)
        return h.as_element()

    def fill_plan_fields(block, p):
        inputs = block.query_selector_all("input")
        if len(inputs) >= 1: inputs[0].click(); inputs[0].fill(str(p["price"]))
        if len(inputs) >= 2: inputs[1].click(); inputs[1].fill(str(p["cap"]))
        label = "Enable Free Trial" if p.get("trial") else "No Free Trial"
        loc = pg.evaluate(
            """(a)=>{const[blk,label]=a;const e=[...blk.querySelectorAll('*')].find(x=>(x.textContent||'').trim()===label&&x.getBoundingClientRect().height<70);if(e){e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}return null;}""",
            [block, label])
        if loc: pg.mouse.click(loc["x"], loc["y"]); time.sleep(0.5)

    t = 0
    while plan_block_count() < len(plans) and t < 6:
        # anchored match — "Add Plan (1/3)" etc; a loose match hits a huge container.
        c = pg.evaluate("""()=>{const cands=[...document.querySelectorAll('button,div,span,a')].filter(e=>{const x=(e.textContent||'').trim();return /^Add Plan|^\\+ ?Add|プランを追加|プラン追加/i.test(x)&&x.length<22;});if(cands.length){const b=cands[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}return null;}""")
        if c: pg.mouse.click(c["x"], c["y"])
        time.sleep(1.1); t += 1

    # non-"month" plans first: convert ONE still-"Monthly" card at a time, then
    # immediately fill it (price/cap/trial) before converting the next one.
    non_month = [p for p in plans if p["cycle"] != "month"]
    month_plans = [p for p in plans if p["cycle"] == "month"]
    for p in non_month:
        blk = find_block_by_period("Monthly")
        if not blk: continue
        btn = blk.query_selector("button.pricingConfigDropdownButton")
        want = CYCLE_LABEL[p["cycle"]]
        btn.scroll_into_view_if_needed(); btn.click(); time.sleep(0.6)
        opt = pg.evaluate(
            """(w)=>{const e=[...document.querySelectorAll('*')].find(x=>x.children.length===0&&(x.textContent||'').trim()===w&&x.getBoundingClientRect().height<40&&x.getBoundingClientRect().height>5);if(e){const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};}return null;}""",
            want)
        if opt: pg.mouse.click(opt["x"], opt["y"]); time.sleep(0.6)
        blk2 = find_block_by_period(want)
        if blk2: fill_plan_fields(blk2, p)
        time.sleep(0.3)

    # remaining "month" card(s) — whichever is still "Monthly" now (period unchanged)
    for p in month_plans:
        blk = find_block_by_period("Monthly")
        if blk: fill_plan_fields(blk, p)
        time.sleep(0.3)
    # model
    mf = pg.query_selector("input[placeholder*='モデル']")
    if mf:
        mf.click(); mf.fill(cfg["model"].split()[-1] if "Sonnet" in cfg["model"] else cfg["model"]); time.sleep(1.5)
        pg.evaluate("""(m)=>{const o=[...document.querySelectorAll('[role=option],li,div,span,button')].find(e=>(e.textContent||'').trim()===m&&e.children.length===0);if(o)o.click();}""", cfg["model"]); time.sleep(0.6)
    # welcome + test (RHF fill)
    for ta in pg.query_selector_all("textarea"):
        ph = ta.get_attribute("placeholder") or ""
        if "初回実行前" in ph and not ta.input_value(): ta.click(); ta.fill(cfg["welcome"])
        if ("たくさん買って" in ph or "韻を踏んだ" in ph) and not ta.input_value(): ta.click(); ta.fill(cfg.get("test_input", "test"))
    # provider field (REQUIRED)
    for i in pg.query_selector_all("input"):
        ph = i.get_attribute("placeholder") or ""
        if ("OpenAI" in ph and "Anthropic" in ph) or "MiniMax" in ph:
            if not (i.input_value() or ""): i.click(); i.type(cfg.get("provider", "openrouter.ai"), delay=30); i.press("Enter")
            break
    # per-plan trial choice already applied inside fill_plan_fields() above.
    for y in [400, 700, 1000, 1300, 1600, 1900]:
        pg.evaluate(f"window.scrollTo(0,{y})"); time.sleep(0.15)
    # fill any empty trial number (free request limit) with the plan cap
    pg.evaluate("""()=>{document.querySelectorAll('input[type=number]').forEach(e=>{if(!(e.value||'')){const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(e,'10');e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}});}"""); time.sleep(0.4)
    # ★ DPA (data processing agreement) checkbox — REQUIRED, red if unchecked ★
    pg.evaluate("""()=>{const cbs=[...document.querySelectorAll('input[type=checkbox]')];for(const c of cbs){const ctx=((c.closest('label')||c.parentElement||{}).textContent||'')+((c.parentElement?c.parentElement.textContent:'')||'');if(/データ処理契約|準拠していることを確認|Capafy の|Data Processing|privacy/i.test(ctx)){if(!c.checked)c.click();}}}"""); time.sleep(0.5)
    # bank pricing
    click_text(pg, "下書きを保存"); time.sleep(3)

    green = price_svg_green(pg)
    print("price tab green:", green)
    # ---- final submit ----
    btn = pg.query_selector("xpath=//button[normalize-space(.)='提出を確認']")
    if btn: btn.scroll_into_view_if_needed(); btn.click()
    res = "NOT-SAVED"
    for _ in range(10):
        time.sleep(2)
        if pg.evaluate("""()=>[...document.querySelectorAll('*')].some(e=>/カードを保存しました/.test((e.textContent||'')))""") or "card-done" in pg.url or "credential" in pg.url:
            res = "SAVED"; break
    print(res, "| price-green:", green, "| url:", pg.url.split("page=")[-1])
    sys.exit(0 if res == "SAVED" else 1)


if __name__ == "__main__":
    main()
