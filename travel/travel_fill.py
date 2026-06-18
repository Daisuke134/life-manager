#!/usr/bin/env python3
"""anicca-travel-fill — auto-insert 🚆 移動 blocks in gcal.

For each pair (prev, curr) of adjacent events whose locations differ, look up
the real Google Directions transit/driving time and insert a 移動 block in
the gap so lateness_check has explicit travel data.

Idempotent via state/travel_filled.json.
"""
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adapters"))
import transport as _t  # noqa: E402

JST = timezone(timedelta(hours=9))
STATE_FILE = C.data_path("travel_filled.json")
HORIZON_DAYS = int(os.environ.get("TRAVEL_FILL_HORIZON_DAYS", "7"))
MIN_DIST_M = int(os.environ.get("TRAVEL_FILL_MIN_DIST_M", "500"))
MIN_GAP_MIN = int(os.environ.get("TRAVEL_FILL_MIN_GAP_MIN", "10"))
LEAVE_LEAD_MIN = int(os.environ.get("TRAVEL_FILL_LEAVE_LEAD_MIN", "0"))

ROUTINE_AT_HOME_PATTERNS = (
    "sleep", "睡眠", "就寝", "寝る",
    "wake", "起床",
    "meditat", "瞑想", "座禅",
    "breakfast", "朝食", "朝ごはん",
    "lunch", "昼食", "昼ごはん",
    "dinner", "夕食", "晩ごはん",
    "meal", "食事",
    "running", "🏃", "jog",
)
TRAVEL_SUMMARY_PREFIX = ("🚆", "🚌", "🚶", "🚇", "移動")




def is_routine_at_home(summary):
    s = (summary or "").lower()
    return any(p in s for p in ROUTINE_AT_HOME_PATTERNS)


def is_travel(summary):
    s = (summary or "").strip()
    return any(s.startswith(p) for p in TRAVEL_SUMMARY_PREFIX)


ADDR_PATTERNS = (
    # 〒NNN-NNNN followed by Japanese address up to a delimiter
    re.compile(r"(〒\d{3}-\d{4}\s*[^,;()\n　]+)"),
    # 東京都/大阪府/北海道/京都府/etc + ward/city + ...
    re.compile(r"((?:北海道|東京都|京都府|大阪府|[^\s]{1,3}県)[^\s,;()\n　]{2,40})"),
    # NAIST / MUIT / specific named locations followed by address fragment
    re.compile(r"((?:NAIST|MUIT|MUFG)\s+〒?\d{0,3}-?\d{0,4}\s*[^\s,;()\n　]+)"),
    # standalone 〇〇駅 (avoid grabbing entire title)
    re.compile(r"([一-龯ぁ-んァ-ヶ]{2,8}駅)"),
)


def extract_address_from_text(text):
    if not text:
        return None
    for pat in ADDR_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def resolve_event_location(event):
    """Resolve where an event happens.
    Order:
      1) event.location  (= explicit)
      2) routine_at_home  → profile.home_address
      3) regex-extract a JP address from summary / description
      4) None / 'unknown'  → caller must defer (LLM not allowed to fabricate)
    """
    loc = (event or {}).get("location") or ""
    if loc.strip():
        return loc.strip(), "explicit"
    if is_routine_at_home(event.get("summary", "")):
        return C.home_address(), "home_routine"
    extracted = (
        extract_address_from_text(event.get("summary", ""))
        or extract_address_from_text(event.get("description", ""))
    )
    if extracted:
        return extracted, "summary_extracted"
    # web fallback: let Google geocode try the raw title (e.g. "NAIST", "スターバックス 渋谷")
    title = (event.get("summary") or "").strip()
    if title and geocode(title):
        return title, "geocoded"
    return None, "unknown"


CAL = _t.make_transport(
    account=C.google_account(),
    keyring=C.env("GOG_KEYRING_PASSWORD"),
).calendar


def fetch_events(days):
    to = (datetime.now(JST) + timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        items = CAL.list(frm="today", to=to, max=250)
    except Exception as e:
        print(f"[fill] gog failed: {e}", file=sys.stderr)
        return []
    rows = []
    for e in items:
        s = e.get("start", {})
        end = e.get("end", {})
        dt = s.get("dateTime")
        edt = end.get("dateTime")
        if not (dt and edt):
            continue  # skip all-day blocks
        rows.append({
            "id": e["id"],
            "summary": e.get("summary") or "",
            "location": e.get("location") or "",
            "start": datetime.fromisoformat(dt).astimezone(JST),
            "end": datetime.fromisoformat(edt).astimezone(JST),
            "description": e.get("description") or "",
        })
    rows.sort(key=lambda r: r["start"])
    return rows


def geocode(addr):
    key = C.env("GOOGLE_API_KEY")
    if not (addr and key):
        return None
    try:
        q = urllib.parse.urlencode({"address": addr, "key": key, "language": "ja"})
        with urllib.request.urlopen(
            f"https://maps.googleapis.com/maps/api/geocode/json?{q}", timeout=8
        ) as r:
            j = json.loads(r.read().decode())
        loc = j["results"][0]["geometry"]["location"]
        return (loc["lat"], loc["lng"])
    except Exception:
        return None


def haversine_m(p1, p2):
    if not (p1 and p2):
        return None
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6371000
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def directions_minutes(src_addr, dst_addr):
    key = C.env("GOOGLE_API_KEY")
    if not (key and src_addr and dst_addr):
        return None
    for mode in ("transit", "driving"):
        params = {
            "origin": src_addr,
            "destination": dst_addr,
            "mode": mode,
            "language": "ja",
            "key": key,
        }
        if mode == "transit":
            params["departure_time"] = "now"
        url = (
            "https://maps.googleapis.com/maps/api/directions/json?"
            + urllib.parse.urlencode(params)
        )
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                j = json.loads(r.read().decode())
            if j.get("status") != "OK":
                continue
            sec = j["routes"][0]["legs"][0]["duration"]["value"]
            mins = max(5, round(sec / 60))
            if mode == "driving":
                mins = round(mins * 1.4)  # Tokyo transit ≈ driving × 1.4 in JP
            return mins
        except Exception:
            continue
    return None


def short_name(addr):
    """Make a label like '中野駅' from a long address."""
    if not addr:
        return "?"
    # Common landmarks come first
    parts = re.split(r"[、,]", addr)
    if len(parts) == 1:
        parts = re.split(r"\s+", addr, maxsplit=2)
    cand = parts[0].strip()
    # If only a "区/市 + 番地" style street address, use the postal-friendly short
    m = re.search(r"(.+?[駅町区市])", cand)
    return m.group(1) if m else cand[:12]


def insert_travel_event(start_dt, end_dt, src, dst, dst_addr):
    summary = f"🚆 移動 {short_name(src)}→{short_name(dst)}"
    desc = "Auto-inserted by anicca-travel-fill. Adjust if route is wrong."
    try:
        return CAL.create(summary=summary, frm=start_dt.isoformat(), to=end_dt.isoformat(),
                          location=dst_addr, description=desc)
    except Exception as e:
        print(f"[fill] insert failed: {e}", file=sys.stderr)
        return None


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def existing_travel_in_gap(events, gap_start, gap_end):
    for e in events:
        if not is_travel(e["summary"]):
            continue
        if e["start"] >= gap_start and e["end"] <= gap_end:
            return e
    return None


ASK_QUEUE = C.data_path("life-ask-queue.jsonl")


def plan_action(kind, travel_min):
    """Decide what to do for a pair. Never guess a fixed time; never silently skip an unknown."""
    if kind == "unknown":
        return ("ask", "unknown_location")
    if travel_min is None:
        return ("ask", "no_route")
    return ("insert", travel_min)


def pair_decision(prev_addr, prev_kind, curr_addr, curr_kind):
    """Which event (if any) needs an ASK before we can route prev→curr.
    Asks about the ACTUALLY-unknown event (fixes asking about curr when prev was the unknown one)."""
    if not prev_addr or prev_kind == "unknown":
        return ("ask_prev", "unknown_location")
    if not curr_addr or curr_kind == "unknown":
        return ("ask_curr", "unknown_location")
    return ("ok", None)


def enqueue_ask(event, reason, queue_path=None):
    """Queue a question to the user (the ask subsystem mails it). Dedup by (eventId, reason)."""
    import time
    q = Path(queue_path) if queue_path else ASK_QUEUE
    q.parent.mkdir(parents=True, exist_ok=True)
    eid = (event or {}).get("id", "")
    if q.exists():
        for line in q.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("eventId") == eid and r.get("reason") == reason:
                return  # already queued
    row = {"eventId": eid, "summary": (event or {}).get("summary", ""),
           "reason": reason, "ts": int(time.time())}
    try:
        with q.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        print(f"[fill] enqueue_ask write failed: {e}", file=sys.stderr)


def main():
    state = load_state()
    events = fetch_events(HORIZON_DAYS)
    if not events:
        print(json.dumps({"action": "no-events"}))
        return
    summary = {"checked": 0, "inserted": 0, "skipped_existing": 0,
               "skipped_same_loc": 0, "skipped_no_gap": 0, "skipped_unknown": 0}
    inserted_log = []
    for i in range(len(events) - 1):
        prev, curr = events[i], events[i + 1]
        if is_travel(prev["summary"]) or is_travel(curr["summary"]):
            continue
        summary["checked"] += 1
        key = f"{prev['id']}|{curr['id']}"
        if key in state:
            summary["skipped_existing"] += 1
            continue
        prev_addr, prev_kind = resolve_event_location(prev)
        curr_addr, kind = resolve_event_location(curr)
        verdict, ask_reason = pair_decision(prev_addr, prev_kind, curr_addr, kind)
        if verdict != "ok":
            enqueue_ask(prev if verdict == "ask_prev" else curr, ask_reason)  # ask the RIGHT event
            state[key] = "asked"  # record so we don't re-geocode / re-ask every run (cleared on reply)
            summary["skipped_unknown"] += 1
            continue
        p_geo = geocode(prev_addr)
        c_geo = geocode(curr_addr)
        d = haversine_m(p_geo, c_geo) or 0
        if d < MIN_DIST_M:
            if kind == "geocoded":  # a coarse title-geocode near prev is not proof of co-location → ask
                enqueue_ask(curr, "uncertain_location")
                state[key] = "asked"
                summary["skipped_unknown"] += 1
            else:
                summary["skipped_same_loc"] += 1
            continue
        gap_min = (curr["start"] - prev["end"]).total_seconds() / 60
        if gap_min < MIN_GAP_MIN:
            summary["skipped_no_gap"] += 1
            continue
        existing = existing_travel_in_gap(events, prev["end"], curr["start"])
        if existing:
            state[key] = existing["id"]
            summary["skipped_existing"] += 1
            continue
        travel_min = directions_minutes(prev_addr, curr_addr)
        action, reason = plan_action(kind, travel_min)
        if action == "ask":
            enqueue_ask(curr, reason)  # route unknown → ASK, never guess a fixed 45 min
            state[key] = "asked"  # don't re-call Directions every run; cleared on reply
            summary["skipped_unknown"] += 1
            continue
        travel_min = min(travel_min, int(gap_min))
        start_dt = curr["start"] - timedelta(minutes=travel_min)
        if start_dt < prev["end"]:
            start_dt = prev["end"]
        end_dt = curr["start"]
        ins_id = insert_travel_event(start_dt, end_dt, prev_addr, curr_addr, curr_addr)
        if ins_id:
            state[key] = ins_id
            summary["inserted"] += 1
            inserted_log.append({
                "between": f"{prev['summary'][:30]} → {curr['summary'][:30]}",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "travel_min": travel_min,
            })
    save_state(state)
    print(json.dumps({"summary": summary, "inserted": inserted_log},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
