"""Agentic location resolver — generalizes to ANY user's phrasing (no fixed lists/regex).
Uses Gemini (existing GEMINI_API_KEY) to map an event to a known place or craft a question.
Self-contained: stdlib + GEMINI_API_KEY only. Runs local AND cloud."""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C  # noqa: E402

GEMINI_MODEL = os.environ.get("LIFE_RESOLVE_MODEL", "gemini-2.5-flash")


def _gemini(prompt):
    key = C.env("GEMINI_API_KEY")
    if not key:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={key}")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        txt = d["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)
    except Exception:
        return None


def agentic_resolve(event, known):
    """known = {home, work, history:[{summary,location}]}.
    Returns {location: <str|None>, question: <str|None>}. Never fabricates: if not
    confident, location=None and a natural user-language question is returned."""
    home = known.get("home") or "?"
    work = known.get("work") or "?"
    prompt = (
        "You place a calendar event at a PHYSICAL location for a travel-time calculator.\n"
        f"Known places: home={home}; work={work}.\n"
        f"Recently resolved events: {json.dumps((known.get('history') or [])[:8], ensure_ascii=False)}\n"
        f"Event summary: {json.dumps(event.get('summary', ''), ensure_ascii=False)}\n"
        f"Event description: {json.dumps((event.get('description') or '')[:200], ensure_ascii=False)}\n\n"
        "Decide where this event physically happens. Be decisive — only ask when truly indeterminate.\n"
        "Rules:\n"
        "- At-home activities (sleep, wake, meditation, meals/breakfast/lunch/dinner, getting ready) "
        "→ return home if home is known.\n"
        "- Work / office / commute / standups / team syncs / 1-on-1s with no other place "
        "→ return work if work is known.\n"
        "- A named public place, venue, landmark, station, shop, or address (e.g. '六本木ヒルズ', "
        "'スターバックス 渋谷', 'NAIST', '〇〇駅') → return it verbatim; a maps geocoder will find it.\n"
        "- ONLY when the place is genuinely indeterminate (a generic 'gym'/'cafe' with no name, a "
        "'running'/'walk' route, an unnamed appointment) → ask.\n\n"
        "Return {\"location\": \"<place or address>\"} when you can decide, otherwise "
        "{\"location\": null, \"question\": \"<one short, natural question in the user's language "
        "asking exactly where this event takes place>\"}. NEVER fabricate a specific address."
    )
    out = _gemini(prompt) or {}
    loc = out.get("location")
    loc = loc.strip() if isinstance(loc, str) and loc.strip() else None
    q = out.get("question")
    q = q.strip() if isinstance(q, str) and q.strip() else None
    return {"location": loc, "question": q}
