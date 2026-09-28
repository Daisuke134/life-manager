#!/usr/bin/env python3
"""
lint_listing.py — REJECTION-PROOF linter for a Capafy run_online listing.
Embeds the C4 rejection learning deterministically: a pure-LLM sandbox skill must
NOT advertise capabilities it can't deliver (live web/retrieval/posting/file-export/
guarantees). Fail-closed: exit 1 if any blocking issue, exit 0 if clean.

Usage: lint_listing.py <LISTING.md>
Checks:
  1. title <= 50 chars, shortDescription <= 500 chars (Capafy hard limits).
  2. OVERCLAIM phrases (browse/scrape/fetch/live/real-time/retrieval/posts/sends/
     .pptx/guaranteed/undetectable...) — FAIL unless the same line negates them
     (no/not/never/without/doesn't) i.e. a disclaimer is fine.
  3. A pricing table must exist and every plan's trial cell must be "No Free Trial" or
     "Free Trial <hours>h / <N> requests" (e.g. "Free Trial 24h / 3 requests").
Prints PASS / FAIL with the offending lines.
"""
import re, sys

NO_FREE_TRIAL = re.compile(r"no[\s_-]+free[\s_-]+trial", re.I)
FREE_TRIAL = re.compile(r"free[\s_-]+trial\s+(\d+)\s*h\s*/\s*(\d+)\s*requests?", re.I)

# Phrases a pure-LLM run_online skill cannot truthfully claim (the C4 trap family).
OVERCLAIM = [
    r"\blive (web|data|search|results?|sources?)\b", r"\breal[- ]time\b",
    r"\bup[- ]to[- ]date\b", r"\bbrowse(s|d)?\b", r"\bscrape(s|d|r)?\b",
    r"\bscraping\b", r"\bcrawl(s|ed|er)?\b", r"\bfetch(es|ed)?\b",
    r"\bretriev(e|es|al)\b", r"\bsearch(es)? the web\b", r"\bweb search\b",
    r"\bpulls? (data )?from\b", r"\bcompetitor(s'?)? (data|page|site)\b",
    r"\bposts? to\b", r"\bschedul(e|es|ing) (a |the )?(post|email|tweet)\b",
    r"\bsends? (the |an |your )?(email|message|dm)\b", r"\buploads? to\b",
    r"\b\.pptx\b", r"\bpowerpoint file\b", r"\bdownloadable file\b",
    r"\bguarantee(s|d)?\b", r"\bundetectable\b", r"\bbypass (the )?detect",
    r"\bX% (more|increase|conversion|reply)\b",
]
NEG = re.compile(r"\b(no|not|never|without|won'?t|doesn'?t|don'?t|cannot|can'?t|isn'?t|aren'?t)\b", re.I)


def section(md, name, nxt):
    m = re.search(rf"## {re.escape(name)}\n(.+?)\n## {re.escape(nxt)}", md, re.S)
    return m.group(1).strip() if m else ""


def main():
    if len(sys.argv) < 2:
        print("usage: lint_listing.py <LISTING.md>"); sys.exit(2)
    md = open(sys.argv[1], encoding="utf-8").read()
    fails, warns = [], []

    title_m = re.search(r"## Title\n(.+)", md)
    title = title_m.group(1).strip() if title_m else ""
    short = section(md, "shortDescription", "welcomeMessage")
    welcome = section(md, "welcomeMessage", "detailedDescription")
    # detailed = everything after the detailedDescription header
    det_m = re.split(r"\n## detailedDescription[^\n]*\n", md)
    detailed = det_m[-1].strip() if len(det_m) > 1 else ""

    # 1. field limits
    if not title:
        fails.append("Title section missing")
    elif len(title) > 50:
        fails.append(f"title {len(title)} > 50 chars: {title!r}")
    if not short:
        fails.append("shortDescription section missing")
    elif len(short) > 500:
        fails.append(f"shortDescription {len(short)} > 500 chars")
    else:
        if len(short) > 495:
            warns.append(f"shortDescription {len(short)} chars — tight margin (≤495 safer)")

    # 2. overclaim scan over buyer-facing text (title/short/welcome/detailed)
    buyer_text = "\n".join([title, short, welcome, detailed])
    for ln in buyer_text.splitlines():
        line = ln.strip()
        if not line:
            continue
        for pat in OVERCLAIM:
            m = re.search(pat, line, re.I)
            if m:
                # allow if the line negates it (a disclaimer like "no live data")
                if NEG.search(line):
                    continue
                fails.append(f"OVERCLAIM '{m.group(0)}' (pure-LLM can't deliver) → {line[:90]!r}")

    # 3. pricing table present — either a subscription day/week/month table, or a
    # single "download" row (one-time fee, no cap/trial/hosted model — CP2 is
    # skipped for Capafy Download-mode agents).
    is_download = re.search(r"\|\s*download\s*\|\s*\$?[0-9.]+\s*\|", md, re.I)
    if not is_download:
        pricing_rows = re.findall(
            r"\|\s*(day|week|month)\s*\|\s*\$?[0-9.]+\s*\|\s*[0-9]+\s*\|\s*([^|]+)\|",
            md,
            re.I,
        )
        if not re.search(r"\|\s*cycle\s*\|\s*price\s*\|", md, re.I):
            fails.append("no pricing table (| cycle | price | cap | trial |) found")
        for cycle, trial in pricing_rows:
            trial = trial.strip()
            if not (NO_FREE_TRIAL.fullmatch(trial) or FREE_TRIAL.fullmatch(trial)):
                fails.append(
                    f"{cycle} plan trial must be 'No Free Trial' or 'Free Trial <hours>h / <N> requests': {trial!r}"
                )

    print("=== lint_listing.py ===")
    print(f"title={len(title)}/50  short={len(short)}/500")
    for w in warns:
        print("  ⚠️  WARN:", w)
    if fails:
        print(f"  ❌ FAIL ({len(fails)}):")
        for f in fails:
            print("   -", f)
        print("RESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS (rejection-proof checks clean)")
    sys.exit(0)


if __name__ == "__main__":
    main()
