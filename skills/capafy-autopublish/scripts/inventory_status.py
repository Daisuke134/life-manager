#!/usr/bin/env python3
"""
inventory_status.py — deterministic answer to "does the drain-only loop have ANY real
work to do right now?", so the daily loop (and the health signal) can tell three states
apart that the old "did published.jsonl grow?" proxy could NOT:

  PUBLISHABLE  — there is one bounded external transition to execute: recover an offline
                 Agent in place, resume/retry an existing version, or publish ready inventory.
  DRAINED      — every ready inventory title is already online. Nothing to publish. This is
                 HEALTHY IDLE, not a failure — do not alarm, do not burn a self-fix.
  CAP_FULL     — >=5 unlisted (draft/under_review) agents already occupy the publish cap.
                 Wait for review to clear. Healthy idle.
  SERVER_UNREADABLE — publish-list could not be read (auth/network). Report, do not guess.

WHY THIS EXISTS (self-fix-capafy-loop, 2026-07-08):
  The capafy healthcheck escalated an Opus self-fix whenever state/published.jsonl went 30h
  without growing, on the theory "loop alive but produces no skill => CP1 broken". But this
  loop is DRAIN-ONLY over a FINITE, hand-built inventory (c1-c5, o1-o10). Once every built
  listing is online (the real state on 2026-07-08: 20 online, 0 publishable), published.jsonl
  CANNOT grow, so the 30h alarm fires forever and spawns an expensive Opus fixer for a NON-bug.
  The pipeline (agentic cp1_agent.py -> CP2 -> CP3) was never broken; the loop just correctly
  stops at "inventory empty". The health proxy was wrong. This tool gives the loop a truthful
  verdict so the marker it writes distinguishes "healthy idle" from "genuinely stuck".

Server truth only (never the local ledger). Exit 0 always; verdict is on stdout as JSON and
as a VERDICT=<state> line for cheap bash grepping.
"""
import json, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import duplicate_gate  # noqa: E402 — Capafy 4.2 near-duplicate gate (model-judged, cached)

REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
STATE_HOME = Path(os.environ.get(
    "LIFE_MANAGER_STATE_HOME",
    Path.home() / ".local/state/life-manager",
)).expanduser()
AUTO = os.environ.get("CAPAFY_AUTO") or str(REPO_ROOT / "skills/capafy-autopublish")
PUB = os.path.join(AUTO, "vendor", "capafy-publisher")
ICONS = os.environ.get("CAPAFY_ICONS_DIR") or str(STATE_HOME / "assets/capafy/icons")
FEATURES = os.environ.get("CAPAFY_FEATURES_DIR") or str(STATE_HOME / "features")
SKILLS = os.environ.get("CAPAFY_SKILLS_ROOT") or str(REPO_ROOT / "skills")
CATALOG = os.environ.get("CAPAFY_CATALOG_DIR") or str(REPO_ROOT / "skills/capafy/catalog")
RETIRED = os.environ.get("CAPAFY_RETIRED_PATH") or str(REPO_ROOT / "skills/capafy/RETIRED.json")
ANALYTICS_PATH = os.environ.get("CAPAFY_ANALYTICS_PATH") or str(STATE_HOME / "state/capafy-skill-analytics.json")

ONLINE = {"online"}
READY_TO_PUBLISH = {"approved", "pending_online", "audit_passed_pending_online"}
# Capafy's create endpoint counts rejected agents toward its five-unlisted-agent
# limit as well as drafts and submissions under review.  Treating a rejection as
# a free slot made the drainer select a fresh catalog item that publish-init could
# never create, then report a successful runner pass while the outer loop stayed
# PUBLISHABLE forever.  Keep the retry classification below, but include it in
# capacity accounting so the handoff mirrors the server's actual admission rule.
UNLISTED = {"draft", "under_review", "review_rejected"}
REJECTED = {"review_rejected", "banned"}
RECOVERABLE = {"offline", "user_offline", "user_delisted", "taken_down"}
# Capafy states no limit on unlisted Agents (publisher docs, web, 2026-10-08) and held
# 9 at once, so we do not self-limit (Dais 2026-10-08: submit as many as Capafy
# accepts). A server refusal on create in the factory log is the only reason to cap.
CAP = 1_000_000

# Capafy's AI-generator stamps this exact suffix on the stub draft it creates
# before any repo content is supplied. Must match select_publish_agent.py's
# PLACEHOLDER_SUFFIX byte-for-byte (including the em dash) or the retry below
# and that selector's --reuse-agent-id title check would silently diverge.
PLACEHOLDER_SUFFIX = " (LM generated — please review and edit before saving)"

# P-14 (2026-09-27): the seller list field `agentStatus` can go stale after Capafy
# approves the latest version -- 5 agents sat at list agentStatus=under_review for
# 12 days while their authoritative per-Agent detail already read status=3 (review
# passed/pending listing) and auditStatus=4 (passed), per api-docs 00_overview.md
# section 6.2. Treating the stale list value as still-occupying a slot produced a
# false CAP_FULL forever. `status` 3 or 4 with `auditStatus` 4 is authoritative
# "approved" and must not occupy a new-agent slot even when the list disagrees.
DETAIL_APPROVED_STATUS = {3, 4}
DETAIL_APPROVED_AUDIT_STATUS = 4
DETAIL_LISTED_STATUS = 4
# Bound authoritative-detail reads per pass; only draft/under_review rows (never
# review_rejected, which is already classified as retryable) are ever fetched.
DETAIL_FETCH_CAP = 10


def is_approved_detail(detail):
    """detail is (status, audit_status) from fetch_agent_detail, or None on read failure."""
    if not detail:
        return False
    status, audit_status = detail
    return status in DETAIL_APPROVED_STATUS and audit_status == DETAIL_APPROVED_AUDIT_STATUS


def fetch_agent_detail(agent_id):
    """Read-only GET /agent/agents/{agentId} via the existing `publish-remote-status`
    CLI (capafy_platform.api.get_latest_version_raw). Returns (status, audit_status)
    ints from the authoritative latest-version detail, or None on any read failure --
    callers keep the conservative (occupied) classification when detail is unavailable.
    """
    try:
        result = subprocess.run(
            [sys.executable, "packager.py", "publish-remote-status", "--agent-id", str(agent_id)],
            cwd=PUB, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout, strict=False)
        latest = payload.get("latest_version") if isinstance(payload, dict) else None
        if not isinstance(latest, dict):
            return None
        status = latest.get("platform_status")
        audit_status = latest.get("audit_status")
        if isinstance(status, bool) or not isinstance(status, int):
            return None
        if isinstance(audit_status, bool) or not isinstance(audit_status, int):
            return None
        return status, audit_status
    except Exception as e:
        print(f"[inventory_status] agent detail read FAILED for {agent_id}: {e}", file=sys.stderr)
        return None


def normalize_agents(agents, detail_fetcher=None, detail_fetch_cap=DETAIL_FETCH_CAP):
    """Return sanitized rows and deterministic five-slot counts from server truth.

    detail_fetcher, when given, is called with an agent_id for draft/under_review
    rows (bounded by detail_fetch_cap) to resolve a stale list agentStatus against
    the authoritative per-Agent detail. Omit it to keep the pre-P-14 behavior.
    """
    normalized = []
    counts = {"total": len(agents), "listed": 0, "occupied": 0, "free": None,
              "retry": 0, "recover": 0, "ready_publish": 0, "blocked": 0, "unknown": 0}
    structurally_valid = True
    detail_fetches_used = 0
    for agent in agents:
        if not isinstance(agent, dict):
            structurally_valid = False
            counts["unknown"] += 1
            continue
        agent_id = str(agent.get("agentId") or "").strip()
        status = agent.get("agentStatus")
        if not agent_id or not isinstance(status, str) or not status:
            structurally_valid = False
            counts["unknown"] += 1
            continue
        if status in ONLINE:
            lifecycle = "listed"
            counts["listed"] += 1
        elif status in READY_TO_PUBLISH:
            lifecycle = "ready_publish"
            counts["ready_publish"] += 1
        elif status == "review_rejected":
            # A rejected agent is still retryable, but it also consumes one of
            # the platform's unlisted slots until Capafy releases it. Never spend
            # a detail fetch here -- it is already correctly classified.
            lifecycle = "retry"
            counts["occupied"] += 1
            counts["retry"] += 1
        elif status in UNLISTED:
            detail = None
            if detail_fetcher is not None and detail_fetches_used < detail_fetch_cap:
                detail_fetches_used += 1
                detail = detail_fetcher(agent_id)
            if is_approved_detail(detail) and detail[0] == DETAIL_LISTED_STATUS:
                lifecycle = "listed"
                counts["listed"] += 1
            elif is_approved_detail(detail):
                # status 3 = approved but NOT yet listed. It frees the new-Agent
                # slot but still needs Test Run + manual publish, so it belongs in
                # ready_publish, never in listed (2026-10-01 fix).
                lifecycle = "ready_publish"
                counts["ready_publish"] += 1
            else:
                lifecycle = "occupied"
                counts["occupied"] += 1
        elif status == "banned":
            lifecycle = "blocked"
            counts["blocked"] += 1
        elif status in RECOVERABLE:
            # A delisted Agent keeps its identity, sales, card, package and keys.
            # Capafy restores it through Creator Workspace -> Create New Version;
            # this does not consume a new-Agent slot and must not poison the
            # entire inventory as SERVER_UNREADABLE.
            lifecycle = "recover"
            counts["recover"] += 1
        else:
            lifecycle = "unknown"
            structurally_valid = False
            counts["unknown"] += 1
        normalized.append({
            "agent_id": agent_id,
            "name": str(agent.get("name") or ""),
            "latest_version_id": agent.get("latestAgentVersionId"),
            "latest_version_name": agent.get("latestVersionName"),
            "remote_status": status,
            "lifecycle": lifecycle,
            "agent_type": agent.get("agentType"),
            "sales": agent.get("sales"),
            "recent_sales": agent.get("recentSales"),
        })
    if structurally_valid:
        counts["free"] = max(0, CAP - counts["occupied"])
    else:
        counts["occupied"] = None
    return {"readable": structurally_valid, "counts": counts, "agents": normalized}


def load_revenue_by_agent(path=None):
    """Best-effort {agent_id: 30d-revenue-usd} from the analytics snapshot, so
    allocate_action can order same-Agent updates by demand instead of agent_id
    string order. Missing/unreadable file or malformed rows just yield {} --
    the caller's tie-break on agent_id keeps working with no revenue data.
    """
    try:
        rows = json.load(open(path or ANALYTICS_PATH, encoding="utf-8")).get("per_skill_rows")
        if not isinstance(rows, list):
            return {}
        out = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            agent_id = str(row.get("agent_id") or "").strip()
            if not agent_id:
                continue
            try:
                out[agent_id] = float(row.get("stats_30d_revenue_usd") or 0.0)
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


FROZEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "capafy", "FROZEN.json")


def load_frozen_ids(path=None):
    """Agent ids Dais froze (skills/capafy/FROZEN.json). Unreadable file = none frozen
    beyond the profit guard; the file is in-repo and lint-checked by tests."""
    try:
        return {str(a).strip() for a in json.load(open(path or FROZEN_PATH, encoding="utf-8")).get("agent_ids") or []}
    except Exception:
        return set()


MAX_DRAFT_ATTEMPTS = 3


def _draft_attempts_path():
    return os.environ.get("CAPAFY_DRAFT_ATTEMPTS_PATH") or os.path.join(
        os.path.expanduser("~/.local/state/life-manager/state/capafy-autopublish"), "draft-attempts.json")


def load_draft_attempts():
    try:
        data = json.load(open(_draft_attempts_path(), encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, int)} if isinstance(data, dict) else {}


def record_draft_attempt(agent_id, attempts):
    """Count one selection of an unfinished draft; after MAX_DRAFT_ATTEMPTS it is left alone."""
    if not agent_id:
        return
    attempts[agent_id] = attempts.get(agent_id, 0) + 1
    path = _draft_attempts_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(attempts, handle, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass


def drop_profitable_updates(updates, path=None, frozen_path=None):
    """Dais 2026-10-07: never ship a new version of an Agent that is selling at a
    profit (30d orders > 0 and actual 30d profit > 0). The 9/29 and 10/06 version
    updates to Hook Lab preceded its paid orders stopping. Updates that stop a
    loss (profit <= 0) still ship. Unreadable analytics keeps every update out:
    an unknown profit is not permission to touch a seller."""
    try:
        rows = json.load(open(path or ANALYTICS_PATH, encoding="utf-8")).get("per_skill_rows") or []
    except Exception:
        return []
    protected = set(load_frozen_ids(frozen_path))
    for row in rows:
        try:
            if float(row.get("stats_30d_orders") or 0) > 0 and float(row.get("profit_30d_actual_usd") or 0) > 0:
                protected.add(str(row.get("agent_id") or "").strip())
        except (TypeError, ValueError, AttributeError):
            continue
    # A Dais-approved one-off (2026-10-07: strip test/ from Hook Lab to clear the
    # buyer-facing security-scan warning, same price and model) is the only bypass.
    # Dais 2026-10-07 (second ruling): no automated change to ANY published Agent,
    # selling or not -- price raises on Agents with zero sales for a week made no
    # sense. The factory ships new Agents instead. Only an UPDATE.json carrying
    # dais_approved_exception (an explicit Dais request) may ship.
    del protected
    return [u for u in updates if (u.get("update_request") or {}).get("dais_approved_exception")]


def update_priority_key(revenue_by_agent):
    """Order queued same-Agent updates by 30d revenue descending (highest-demand
    update ships first when a review slot is free), agent_id ascending to break
    ties deterministically."""
    def key(row):
        agent_id = str(row.get("agent_id") or "")
        return (-revenue_by_agent.get(agent_id, 0.0), agent_id)
    return key


def allocate_action(normalized, retries, publishable, resumable_drafts=None, recoveries=None,
                    ready_to_publish=None, updates=None, stub_retries=None, revenue_by_agent=None):
    """Choose at most one stable action without performing any platform write.

    An exact-title repository draft can be resumed in place even when all five
    submission slots are occupied: finishing that existing Agent does not create
    a sixth Agent.  The optional argument keeps the pre-resume call contract
    compatible for callers that only provide retry/fresh candidates.

    stub_retries carries Capafy AI-generator stub drafts (name = "<title> (LM
    generated ...)") whose stripped title matches a ready repo_catalog listing.
    Like resumable_drafts/recoveries, this reuses an EXISTING occupied Agent id
    (via publish_prepare.sh's --reuse-agent-id), so it must proceed even at
    occupied=5 -- it frees no new slot and needs none.
    """
    resumable_drafts = resumable_drafts or []
    recoveries = recoveries or []
    ready_to_publish = ready_to_publish or []
    updates = updates or []
    stub_retries = stub_retries or []
    if not normalized.get("readable"):
        return {"verdict": "SERVER_UNREADABLE"}
    occupied = (normalized.get("counts") or {}).get("occupied")
    if not isinstance(occupied, int) or isinstance(occupied, bool) or occupied < 0:
        return {"verdict": "SERVER_UNREADABLE"}
    # A same-Agent update whose first pass already publish-init'd a new draft
    # version must be RESUMED to completion before any other action -- including
    # starting a DIFFERENT queued update. Without this, each pass's "updates"
    # check below only matches a target still online on from_version_id; once
    # publish_prepare.sh flips that target to draft, it drops out of `updates`
    # and the highest-revenue check picks the NEXT queued update instead, which
    # itself becomes an abandoned draft next pass. 2026-09-29: Hook Lab ->
    # Slide Maker -> TikTok Script Pro, three orphan update drafts in 40
    # minutes, none finished, none reaching review. `resumable_drafts` already
    # contains this row (same repo_catalog title, agentStatus=draft); only its
    # priority relative to `updates` needed to change. Never create a second
    # draft for the same UPDATE.json.
    update_in_progress = [row for row in resumable_drafts if row.get("update_request")]
    if update_in_progress:
        item = min(update_in_progress, key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")))
        return {
            "verdict": "PUBLISHABLE",
            "reason": "resume in-progress same-Agent update draft before starting another",
            "action": "resume_draft",
            "action_key": f"resume:{item['agent_id']}",
            "item": item,
        }
    # A profit-fixing update of a paid Agent outranks resuming a draft whenever a
    # review slot is free: on 2026-09-28 one draft whose CP2 kept failing was
    # re-selected every wake while three slots sat empty and Hook Lab's
    # DeepSeek update (cost > revenue on Sonnet) waited behind it.
    #
    # Among several queued updates, highest 30d revenue ships first (2026-09-29:
    # four Sonnet->DeepSeek repricing updates queued at once; agent_id-string
    # order picked an arbitrary one instead of the highest-demand agent).
    # A same-Agent update of an ONLINE agent is not capped: on 2026-10-05 Capafy
    # accepted publish-init for Hook Lab (8123079349) with 5 (then 6) unlisted
    # agents. The five-unlisted cap only blocks creating new agents.
    if updates:
        item = min(updates, key=update_priority_key(revenue_by_agent or {}))
        request = item["update_request"]
        return {
            "verdict": "PUBLISHABLE",
            "reason": "paid existing Agent has an explicit version update request",
            "action": "update_existing",
            "action_key": f"update:{item['agent_id']}:{request['from_version_id']}",
            "item": item,
        }
    # Finish what is already in flight before creating something new. The old rule (fresh
    # outranks draft while a slot is free) existed because one broken draft was re-selected wake
    # after wake (2026-09-28, Shorts Hook Lab); main() now caps every draft at
    # MAX_DRAFT_ATTEMPTS selections, so a draft cannot starve the queue. With the unlisted cap
    # gone "a slot is free" is always true, so the old rule meant drafts that had already passed
    # CP1/CP2 were never resumed and every pass started a new one from scratch (2026-10-08).
    if resumable_drafts:
        item = min(
            resumable_drafts,
            key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")),
        )
        return {
            "verdict": "PUBLISHABLE",
            "reason": "resume exact-title repository draft",
            "action": "resume_draft",
            "action_key": f"resume:{item['agent_id']}",
            "item": item,
        }
    if stub_retries:
        item = min(
            stub_retries,
            key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")),
        )
        return {
            "verdict": "PUBLISHABLE",
            "reason": "retry Capafy AI-generator stub draft on the same agent_id",
            "action": "retry_existing",
            "action_key": f"retry:{item['agent_id']}",
            "item": item,
        }
    if publishable and occupied < CAP and not ready_to_publish and not recoveries and not retries:
        item = min(publishable, key=lambda row: (
            row.get("demand_rank", UNRANKED_DEMAND), str(row.get("feature") or ""), str(row.get("title") or "")))
        identity = item.get("feature") or item.get("title")
        return {
            "verdict": "PUBLISHABLE",
            "action": "create_fresh",
            "action_key": f"create:{identity}",
            "item": item,
        }
    if resumable_drafts:
        item = min(
            resumable_drafts,
            key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")),
        )
        return {
            "verdict": "PUBLISHABLE",
            "reason": "resume exact-title repository draft",
            "action": "resume_draft",
            "action_key": f"resume:{item['agent_id']}",
            "item": item,
        }
    if stub_retries:
        item = min(
            stub_retries,
            key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")),
        )
        return {
            "verdict": "PUBLISHABLE",
            "reason": "retry Capafy AI-generator stub draft on the same agent_id",
            "action": "retry_existing",
            "action_key": f"retry:{item['agent_id']}",
            "item": item,
        }
    if ready_to_publish:
        item = min(ready_to_publish, key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")))
        return {
            "verdict": "PUBLISHABLE",
            "reason": "approved manual version needs Test Run and publish",
            "action": "test_and_publish",
            "action_key": f"publish:{item['agent_id']}",
            "item": item,
        }
    # Recovery creates a copied version under the same Agent ID, so it remains
    # valid even when the five slots for new Agents are full.
    if recoveries:
        item = min(recoveries, key=lambda row: (str(row.get("agent_id") or ""), str(row.get("title") or "")))
        return {
            "verdict": "PUBLISHABLE",
            "reason": "offline Agent needs copied replacement version",
            "action": "recover_delisted",
            "action_key": f"recover:{item['agent_id']}",
            "item": item,
        }
    # Capafy permits at most five simultaneous draft/under-review submissions.
    # A rejected agent becomes retryable only after that rejection has freed a slot;
    # retrying an old agent does not create a sixth submission exception.
    if occupied >= CAP:
        return {"verdict": "CAP_FULL", "occupied": occupied}
    if retries:
        # Highest 30d revenue retries first, same rule as queued updates above
        # (2026-10-04: agent_id-string order picked a $0-revenue retry ahead
        # of a $11.18/30d one while a slot was free).
        item = min(retries, key=update_priority_key(revenue_by_agent or {}))
        return {
            "verdict": "PUBLISHABLE",
            "reason": "review_rejected retry",
            "action": "retry_existing",
            "action_key": f"retry:{item['agent_id']}",
            "item": item,
        }
    if updates:
        item = min(updates, key=update_priority_key(revenue_by_agent or {}))
        request = item["update_request"]
        return {
            "verdict": "PUBLISHABLE",
            "reason": "paid existing Agent has an explicit version update request",
            "action": "update_existing",
            "action_key": f"update:{item['agent_id']}:{request['from_version_id']}",
            "item": item,
        }
    if publishable:
        item = min(publishable, key=lambda row: (
            row.get("demand_rank", UNRANKED_DEMAND), str(row.get("feature") or ""), str(row.get("title") or "")))
        identity = item.get("feature") or item.get("title")
        return {
            "verdict": "PUBLISHABLE",
            "action": "create_fresh",
            "action_key": f"create:{identity}",
            "item": item,
        }
    return {"verdict": "DRAINED"}


def server_agents():
    """Return list of server agents, or None on read failure."""
    try:
        result = subprocess.run(
            [sys.executable, "packager.py", "publish-list"],
            cwd=PUB, capture_output=True, text=True, timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError(f"publish-list exited with {result.returncode}")
        payload = json.loads(result.stdout, strict=False)
        if not isinstance(payload, dict) or not isinstance(payload.get("agents"), list):
            raise ValueError("publish-list response has no top-level agents list")
        rows = []
        for index, agent in enumerate(payload["agents"]):
            if not isinstance(agent, dict):
                raise ValueError(f"publish-list agents[{index}] is not an object")
            rows.append({
                "agentId": agent.get("agent_id"),
                "name": agent.get("name"),
                "description": agent.get("description"),
                "agentType": agent.get("agent_type"),
                "agentStatus": agent.get("agent_status"),
                "latestAgentVersionId": agent.get("latest_agent_version_id"),
                "updatedAt": agent.get("updated_at"),
            })
        return rows
    except Exception as e:
        print(f"[inventory_status] server read FAILED: {e}", file=sys.stderr)
        return None


def load_retired(path=None):
    """Return (retired_ids, retired_titles) for agents we deliberately unpublished
    (C4, 2026-10-04: near-duplicate zero-sale agents -- see skills/capafy/RETIRED.json).
    A missing file means nothing is retired (empty sets). A PRESENT but malformed
    file fails CLOSED (returns None) -- never silently treated as "nothing retired",
    or the loop could auto-republish an agent we deliberately took down."""
    p = path or RETIRED
    if not os.path.isfile(p):
        return set(), set()
    try:
        data = json.load(open(p, encoding="utf-8"))
        agents = data["agents"]
        if not isinstance(agents, list):
            raise ValueError("RETIRED.json 'agents' is not a list")
        ids, titles = set(), set()
        for a in agents:
            ids.add(str(a["agent_id"]))
            titles.add(str(a["title"]))
        return ids, titles
    except Exception:
        return None


def listing_title(path):
    """Extract the '## Title' value from a LISTING.md (same rule publish_prepare.sh uses)."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except Exception:
        return None
    for i, ln in enumerate(lines):
        if ln.strip() == "## Title" and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


UNRANKED_DEMAND = 999


def listing_demand_rank(path):
    """Extract an optional 'Demand rank: <int>' line from a LISTING.md.

    Lower = publish first. Missing/unparsable = UNRANKED_DEMAND (published last,
    ordered alphabetically among themselves as before)."""
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return UNRANKED_DEMAND
    m = re.search(r"^Demand rank:\s*(\d+)\s*$", text, re.M)
    return int(m.group(1)) if m else UNRANKED_DEMAND


def ready_inventory():
    """Return complete legacy candidates plus repository-owned canonical catalog items."""
    items = []
    if os.path.isdir(FEATURES):
        for name in sorted(os.listdir(FEATURES)):
            if not name.startswith("capafy-"):
                continue
            d = os.path.join(FEATURES, name)
            listing = os.path.join(d, "LISTING.md")
            title = listing_title(listing) if os.path.isfile(listing) else None
            m = re.match(r"^capafy-([a-z][0-9]+)-", name)
            icon = os.path.join(ICONS, m.group(1) + ".png") if m else ""
            skill = os.path.join(d, "SKILL.md")
            if title and os.path.isfile(icon) and os.path.isfile(skill):
                items.append({"feature": name, "title": title, "icon": icon,
                              "listing": listing, "skill": skill, "source": "legacy_state",
                              "demand_rank": listing_demand_rank(listing)})

    if os.path.isdir(CATALOG):
        for name in sorted(os.listdir(CATALOG)):
            d = os.path.join(CATALOG, name)
            if not os.path.isdir(d):
                continue
            listing = os.path.join(d, "LISTING.md")
            skill = os.path.join(d, "SKILL.md")
            # SVG is source artwork; CP1 only accepts PNG/JPG/WebP. Prefer a
            # listing-ready raster asset so a resumed draft can save Basic Info.
            icon = next((os.path.join(d, candidate) for candidate in ("icon.png", "icon.jpg", "icon.webp", "icon.svg")
                         if os.path.isfile(os.path.join(d, candidate))), None)
            title = listing_title(listing) if os.path.isfile(listing) else None
            update_file = os.path.join(d, "UPDATE.json")
            update_request = None
            if os.path.isfile(update_file):
                request = json.load(open(update_file, encoding="utf-8"))
                target_model = str(request.get("target_model_id") or "").strip()
                # target_one_time_fee updates the Download-mode Pricing card only
                # (a price-only same-Agent update — no hosted model, no CP2, no
                # package re-upload); target_model_id updates the hosted LLM.
                # Exactly one target kind is required.
                target_fee = str(request.get("target_one_time_fee") or "").strip()
                if (not isinstance(request, dict)
                        or not all(str(request.get(key) or "").isdigit()
                                   for key in ("agent_id", "from_version_id"))
                        or not (target_model or target_fee)):
                    raise ValueError(f"invalid same-Agent update request: {name}")
                update_request = request
            if title and icon and os.path.isfile(skill):
                item = {"feature": f"catalog:{name}", "title": title, "icon": icon,
                        "listing": listing, "skill": skill, "source": "repo_catalog",
                        "demand_rank": listing_demand_rank(listing)}
                if update_request:
                    item["update_request"] = update_request
                items.append(item)

    # The repository catalog is authoritative when a legacy candidate has the same title.
    by_title = {}
    for item in items:
        if item["title"] not in by_title or item["source"] == "repo_catalog":
            by_title[item["title"]] = item
    return [by_title[title] for title in sorted(by_title)]


def _not_near_duplicate(item):
    """Capafy 4.2 gate (self-fix-capafy-loop, 2026-10-04): the account already carries
    ~16 near-identical academic Humanizer agents and 5-6 Hook Lab variants, all $0
    sales — the exact pattern capafy.ai/developer/doc/4.2 calls cheating. Before an
    item counts as publishable, duplicate_gate's model-judged cache must hold a fresh
    'distinct' verdict for it. A missing entry, a stale sha (LISTING.md changed since
    judged), or any other verdict (near_duplicate / unknown) fails CLOSED: the item is
    excluded this wake and retried once candidate_backlog.py's refresh judges it."""
    return duplicate_gate.is_allowed(item["feature"], item["listing"])


def main():
    agents = server_agents()
    if agents is None:
        verdict = {"verdict": "SERVER_UNREADABLE"}
        print("VERDICT=SERVER_UNREADABLE")
        print(json.dumps(verdict, ensure_ascii=False))
        return 0

    normalized = normalize_agents(agents, detail_fetcher=fetch_agent_detail)
    if not normalized["readable"]:
        verdict = {"verdict": "SERVER_UNREADABLE", **normalized}
        print("VERDICT=SERVER_UNREADABLE")
        print(json.dumps(verdict, ensure_ascii=False))
        return 0

    retired = load_retired()
    if retired is None:
        verdict = {"verdict": "SERVER_UNREADABLE", "reason": "RETIRED.json is malformed"}
        print("VERDICT=SERVER_UNREADABLE")
        print(json.dumps(verdict, ensure_ascii=False))
        return 0
    retired_ids, retired_titles = retired
    # Dais 2026-10-08: a FROZEN.json Agent (a seller) is handled exactly like a retired
    # one -- no update, no draft resume, no recovery -- whatever UPDATE.json says.
    retired_ids = set(retired_ids) | set(load_frozen_ids())

    online_titles = {(a.get("name") or "").strip() for a in agents if a.get("agentStatus") in ONLINE}
    unlisted = [a for a in agents if a.get("agentStatus") in UNLISTED]
    rejected = [a for a in agents if a.get("agentStatus") in REJECTED]
    recoverable = [a for a in agents if a.get("agentStatus") in RECOVERABLE
                   and str(a.get("agentId") or "").strip() not in retired_ids]
    detail_ready_ids = {row["agent_id"] for row in normalized["agents"] if row["lifecycle"] == "ready_publish"}
    ready_to_publish = [a for a in agents
                        if a.get("agentStatus") in READY_TO_PUBLISH
                        or str(a.get("agentId") or "").strip() in detail_ready_ids]

    # In-flight titles = agents already submitted and awaiting review, or a half-saved draft
    # (draft/under_review). An inventory item whose title is already in-flight must NOT count as
    # publishable — it is done from the loop's side (the resume-guard would just re-open an already
    # status=1 agent, the loop would forever log "PUBLISHABLE" and never reach DRAINED, and the
    # healthcheck's healthy-pass marker would go stale → a FALSE self-fix escalation). Publishable =
    # ready inventory that is NOT online AND NOT already in-flight on the server. (self-fix, 2026-07-08)
    inflight_titles = {(a.get("name") or "").strip() for a in unlisted}

    items = ready_inventory()
    update_items = []
    for item in items:
        request = item.get("update_request")
        if request is None:
            continue
        if str(request["agent_id"]).strip() in retired_ids:
            continue
        matches = [agent for agent in agents
                   if str(agent.get("agentId") or "") == str(request["agent_id"])]
        if len(matches) != 1 or (matches[0].get("name") or "").strip() != item["title"]:
            print("VERDICT=SERVER_UNREADABLE")
            print(json.dumps({"verdict": "SERVER_UNREADABLE",
                              "reason": "same-Agent update target is missing or changed"}))
            return 0
        target = matches[0]
        if (target.get("agentStatus") == "online"
                and str(target.get("latestAgentVersionId") or "") == str(request["from_version_id"])):
            update_items.append({"agent_id": str(request["agent_id"]), **item})
    rejected_titles = {(a.get("name") or "").strip() for a in rejected}
    publishable = [it for it in items if not it.get("update_request")
                   and it["title"] not in online_titles
                   and it["title"] not in inflight_titles
                   and it["title"] not in rejected_titles
                   and it["title"] not in retired_titles
                   and _not_near_duplicate(it)]

    # A rejected agent is only retryable if its title still matches a CURRENT
    # ready_inventory LISTING.md. If the LISTING.md title has since drifted (edited,
    # or the skill was successfully republished under a new agent_id/title), the
    # rejected agent is an ORPHAN: no local content matches it, retrying is a no-op
    # that just creates a duplicate draft (publish_prepare.sh's exact-title RESUME
    # GUARD can never find it). An orphan must NOT block DRAINED forever.
    # (self-fix-capafy-loop, 2026-07-17: found agent 2485008254 stuck exactly this
    # way — review_rejected under an old title "...Built for Retention" while
    # o9's LISTING.md now reads "...Keep Viewers Watching", already online as a
    # different agent_id 7686597754.)
    ready_titles = {it["title"] for it in items}
    retryable_rejected = [a for a in rejected if (a.get("name") or "").strip() in ready_titles
                          and str(a.get("agentId") or "").strip() not in retired_ids]

    ready_by_title = {item["title"]: item for item in items}
    resumable_drafts = []
    for agent in agents:
        if agent.get("agentStatus") != "draft":
            continue
        # Retired agents get no further factory work, including draft resumes
        # (2026-10-05: retired Shorts Hook Lab draft was resumed every pass).
        if str(agent.get("agentId") or "").strip() in retired_ids:
            continue
        title = (agent.get("name") or "").strip()
        item = ready_by_title.get(title)
        if not item or item.get("source") != "repo_catalog":
            continue
        resumable_drafts.append({"agent_id": str(agent.get("agentId")), **item})

    retry_items = []
    for agent in retryable_rejected:
        title = (agent.get("name") or "").strip()
        retry_items.append({"agent_id": str(agent.get("agentId")), "title": title,
                            **ready_by_title[title]})

    # Capafy's AI-generator drops a stub draft named "<title> (LM generated —
    # please review and edit before saving)" (e.g. draft 4973250899 measured
    # 2026-09-29). No stage title-matched that suffix, so the stub occupied a
    # slot forever (CAP_FULL) while ready catalog items queued behind it. Strip
    # the suffix; if what's left matches a ready repo_catalog title, retry it
    # through the SAME path as a review_rejected repair (publish_prepare.sh's
    # --reuse-agent-id, which select_publish_agent.py already accepts for a
    # draft named title+PLACEHOLDER_SUFFIX) so CP1 gets re-driven from the repo
    # LISTING.md on the same agent_id instead of leaking the slot. A stub whose
    # stripped name has no ready repo_catalog title stays untouched (occupied).
    # This reuses an already-occupied Agent id, so -- like resumable_drafts and
    # recover_delisted -- it must proceed even at occupied=5 (stub_retries is
    # passed to allocate_action separately from the cap-gated `retries` list).
    stub_titles_seen = set()
    stub_retry_items = []
    for a in agents:
        if a.get("agentStatus") != "draft":
            continue
        name = (a.get("name") or "").strip()
        if not name.endswith(PLACEHOLDER_SUFFIX):
            continue
        title = name[: -len(PLACEHOLDER_SUFFIX)].strip()
        item = ready_by_title.get(title)
        if not item or item.get("source") != "repo_catalog" or title in stub_titles_seen:
            continue
        stub_titles_seen.add(title)
        stub_retry_items.append({"agent_id": str(a.get("agentId")), "title": title, **item})
    fresh_items = [
        {key: item[key] for key in ("feature", "title", "icon", "listing", "skill", "source", "demand_rank")}
        for item in publishable
    ]
    recovery_items = [
        {"agent_id": str(agent.get("agentId")), "title": (agent.get("name") or "").strip()}
        for agent in recoverable
    ]
    ready_publish_items = [
        {"agent_id": str(agent.get("agentId")), "title": (agent.get("name") or "").strip()}
        for agent in ready_to_publish
    ]
    # Dais 2026-10-08: the factory ships NEW Agents only. Agents already submitted --
    # selling or not, rejected or delisted -- are never updated, retried or recovered.
    # Kept: fresh creates, never-submitted drafts, and approved-but-not-yet-online publishes.
    attempts = load_draft_attempts()
    resumable_drafts = [d for d in resumable_drafts if attempts.get(str(d["agent_id"]), 0) < MAX_DRAFT_ATTEMPTS]
    stub_retry_items = [d for d in stub_retry_items if attempts.get(str(d["agent_id"]), 0) < MAX_DRAFT_ATTEMPTS]
    v = allocate_action(
        normalized, [], fresh_items, resumable_drafts, [], ready_publish_items,
        updates=[], stub_retries=stub_retry_items, revenue_by_agent=load_revenue_by_agent(),
    )
    if v.get("action") in ("resume_draft", "retry_existing"):
        record_draft_attempt(str((v.get("item") or {}).get("agent_id") or ""), attempts)

    v.update({
        "online_count": len(online_titles),
        "unlisted_count": len(unlisted),
        "rejected_count": len(rejected),
        "ready_inventory": len(items),
        "publishable_count": len(publishable),
        **normalized,
    })
    print("VERDICT=" + v["verdict"])
    print(json.dumps(v, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
