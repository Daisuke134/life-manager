#!/usr/bin/env python3
"""Build a durable same-Agent repair queue from rejected Capafy versions."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
PUBLISHER = AUTO / "vendor/capafy-publisher"
DEFAULT_QUEUE = Path.home() / ".local/state/life-manager/state/capafy-rejection-repair-queue.json"
CREDENTIALS = Path.home() / ".local/share/anicca/credentials.json"
REASON_KEYS = {
    "rejectreason",
    "rejectionreason",
    "auditreason",
    "auditremark",
    "reviewreason",
    "reviewremark",
    "rejectmessage",
}
TERMINAL_STATES = {"resubmitted", "listed", "abandoned"}


def _reason(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in REASON_KEYS and isinstance(child, str) and child.strip():
                return child.strip()
        for child in value.values():
            found = _reason(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _reason(child)
            if found:
                return found
    return None


def _new_item(agent: dict, detail: dict, observed_at: str) -> dict:
    latest = detail.get("latest_version") if isinstance(detail, dict) else None
    latest = latest if isinstance(latest, dict) else {}
    agent_id = str(agent["agent_id"])
    version_id = str(latest.get("agentVersionId") or agent.get("latest_version_id") or "unknown-version")
    reason = _reason(latest)
    version_no = latest.get("versionNo")
    target_version = version_no + 1 if isinstance(version_no, int) and not isinstance(version_no, bool) else None
    return {
        "repair_id": f"{agent_id}:{version_id}",
        "agent_id": agent_id,
        "name": str(agent.get("name") or latest.get("title") or ""),
        "operation": "update_existing_agent",
        "source_version_id": version_id,
        "source_version_no": version_no,
        "source_version_name": latest.get("versionName") or agent.get("latest_version_name"),
        "target_version_no": target_version,
        "remote_status": agent.get("remote_status"),
        "numeric_status": latest.get("status"),
        "audit_status": latest.get("auditStatus"),
        "skills_confirmed": latest.get("isConfirmedSkills"),
        "config_confirmed": latest.get("isConfirmedConfigKeys"),
        "rejection_reason": reason or "platform_reason_unavailable",
        "reason_status": "observed" if reason else "unknown",
        "state": "queued" if reason else "needs_diagnosis",
        "first_observed_at": observed_at,
        "last_observed_at": observed_at,
    }


def parse_rejection_mail(text: str) -> dict | None:
    """Parse a Capafy rejection-notice mail body into {agent_id, version, reason}."""
    agent_id_match = re.search(r"Agent ID\s+(\d+)", text)
    if not agent_id_match:
        return None
    version_match = re.search(r"Version\s+(\S+)", text)
    reason_match = re.search(r"Reason\s+\[([^\]]+)\]", text)
    if not reason_match:
        reason_match = re.search(r"Reason\s+(.+?)(?:\n|$)", text)
    reason = reason_match.group(1).strip() if reason_match else None
    if not reason:
        return None
    return {
        "agent_id": agent_id_match.group(1),
        "version": version_match.group(1).strip() if version_match else None,
        "reason": reason,
    }


def _normalize_version(value: Any) -> str:
    text = str(value or "").strip()
    if text[:1].lower() == "v":
        text = text[1:]
    return text


def _capafy_publisher_email() -> str | None:
    try:
        document = json.loads(CREDENTIALS.read_text())
        matches = [row for row in document.get("credentials", []) if row.get("service") == "capafy-publisher"]
        if len(matches) != 1:
            return None
        email = matches[0].get("email") or matches[0].get("username")
        return str(email) if email else None
    except (OSError, ValueError, json.JSONDecodeError, AttributeError, KeyError):
        return None


class _HTMLToText(HTMLParser):
    """Minimal HTML -> markdown-ish text: <a href=X>text</a> becomes [text](X)."""

    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            self._link_href = dict(attrs).get("href")
            self._link_text = []
        elif tag in ("div", "p", "br", "tr", "td", "span", "li"):
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            text = "".join(self._link_text).strip()
            if self._link_href and text:
                self.chunks.append(f"[{text}]({self._link_href})")
            else:
                self.chunks.append(text)
            self._link_href = None
            self._link_text = []

    def handle_data(self, data: str) -> None:
        (self._link_text if self._link_href is not None else self.chunks).append(data)


def _html_to_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    return "".join(parser.chunks)


def _plaintext_body(payload: dict) -> str:
    bodies: list[str] = []

    def collect(part: dict) -> None:
        mime = part.get("mimeType") or ""
        data = (part.get("body") or {}).get("data")
        if data and (not mime or mime.startswith("text/")):
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            except (ValueError, TypeError):
                decoded = ""
            bodies.append(_html_to_text(decoded) if mime == "text/html" else decoded)
        for child in part.get("parts") or []:
            collect(child)

    collect(payload)
    return "\n".join(bodies)


def gmail_rejection_reasons(days: int = 45) -> dict[str, dict]:
    """Latest Capafy rejection reason per agent_id, parsed from Gmail. Never raises; [] on any gog failure."""
    email = _capafy_publisher_email()
    if not email:
        return {}
    try:
        env = dict(os.environ)
        raw = subprocess.run(
            ["gog", "gmail", "search",
             f'newer_than:{int(days)}d from:notify@notify.capafy.ai subject:"Action Required"',
             "--account", email, "--json", "--results-only", "--no-input"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        if raw.returncode != 0:
            return {}
        threads = json.loads(raw.stdout)
        if not isinstance(threads, list):
            return {}
        result: dict[str, dict] = {}
        observed_at: dict[str, int] = {}
        for thread_row in threads:
            thread_id = thread_row.get("id") if isinstance(thread_row, dict) else None
            if not thread_id:
                continue
            got = subprocess.run(
                ["gog", "gmail", "thread", "get", str(thread_id), "--account", email,
                 "--json", "--full", "--no-input"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            if got.returncode != 0:
                continue
            thread = json.loads(got.stdout).get("thread", {})
            for message in thread.get("messages", []):
                parsed = parse_rejection_mail(_plaintext_body(message.get("payload", {})))
                if not parsed:
                    continue
                internal_date = int(message.get("internalDate") or 0)
                agent_id = parsed["agent_id"]
                if agent_id in observed_at and observed_at[agent_id] >= internal_date:
                    continue
                observed_at[agent_id] = internal_date
                result[agent_id] = {
                    "version": parsed["version"],
                    "reason": parsed["reason"],
                    "observed_mail_at": dt.datetime.fromtimestamp(
                        internal_date / 1000, tz=dt.timezone.utc
                    ).isoformat(timespec="seconds").replace("+00:00", "Z"),
                }
        return result
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError, KeyError, AttributeError):
        return {}


def _merge_gmail_reasons(details: dict[str, dict], agents: list[dict], gmail_reasons: dict[str, dict]) -> None:
    """Fill details[agent_id]['latest_version']['rejectReason'] from gmail when the platform gave none."""
    for agent in agents:
        agent_id = str(agent.get("agent_id") or "")
        gmail = gmail_reasons.get(agent_id)
        if not gmail or not gmail.get("reason"):
            continue
        detail = details.get(agent_id)
        if not isinstance(detail, dict):
            continue
        latest = detail.get("latest_version")
        if not isinstance(latest, dict) or _reason(latest):
            continue
        gmail_version = gmail.get("version")
        latest_version_name = agent.get("latest_version_name")
        if (
            gmail_version is None
            or latest_version_name is None
            or _normalize_version(gmail_version) == _normalize_version(latest_version_name)
        ):
            latest["rejectReason"] = gmail["reason"]


def build_queue(
    existing: dict,
    agents: list[dict],
    details: dict[str, dict],
    observed_at: str,
    all_agents: list[dict] | None = None,
) -> dict:
    prior_items = existing.get("items") if isinstance(existing, dict) else None
    prior_items = prior_items if isinstance(prior_items, list) else []
    by_id = {
        item.get("repair_id"): dict(item)
        for item in prior_items
        if isinstance(item, dict) and isinstance(item.get("repair_id"), str)
    }
    order = [item["repair_id"] for item in prior_items if isinstance(item, dict) and item.get("repair_id") in by_id]
    for agent in sorted(agents, key=lambda row: str(row.get("agent_id") or "")):
        if agent.get("remote_status") != "review_rejected" or not agent.get("agent_id"):
            continue
        candidate = _new_item(agent, details.get(str(agent["agent_id"]), {}), observed_at)
        repair_id = candidate["repair_id"]
        if repair_id in by_id:
            prior = by_id[repair_id]
            prior["last_observed_at"] = observed_at
            if prior.get("reason_status") == "unknown" and candidate["reason_status"] == "observed":
                prior["rejection_reason"] = candidate["rejection_reason"]
                prior["reason_status"] = "observed"
                if prior.get("state") == "needs_diagnosis":
                    prior["state"] = "queued"
            by_id[repair_id] = prior
        else:
            by_id[repair_id] = candidate
            order.append(repair_id)
    if all_agents:
        lifecycle_by_id = {
            str(row.get("agent_id")): row.get("lifecycle")
            for row in all_agents
            if isinstance(row, dict) and row.get("agent_id")
        }
        for repair_id in order:
            item = by_id[repair_id]
            if item.get("state") not in TERMINAL_STATES and lifecycle_by_id.get(item.get("agent_id")) == "listed":
                item["state"] = "listed"
    items = [by_id[repair_id] for repair_id in order]
    return {
        "schema_version": 1,
        "updated_at": observed_at,
        "items": items,
        "counts": {
            "total": len(items),
            "active": sum(item.get("state") not in TERMINAL_STATES for item in items),
            "needs_diagnosis": sum(item.get("state") == "needs_diagnosis" for item in items),
            "ready": sum(item.get("state") == "queued" for item in items),
        },
    }


def _remote_detail(agent_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, "packager.py", "publish-remote-status", "--agent-id", agent_id],
        cwd=PUBLISHER,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        return {"_error": f"remote_status_rc_{result.returncode}"}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"_error": "remote_status_invalid_json"}
    return value if isinstance(value, dict) else {"_error": "remote_status_not_object"}


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--inventory-json", type=Path)
    parser.add_argument("--observed-at")
    parser.add_argument("--no-gmail", action="store_true", help="skip Gmail rejection-reason lookup (tests/offline)")
    args = parser.parse_args(argv)
    observed_at = args.observed_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    if args.inventory_json:
        inventory = json.loads(args.inventory_json.read_text())
    else:
        from inventory_status import normalize_agents, server_agents

        raw_agents = server_agents()
        if raw_agents is None:
            print(json.dumps({"ok": False, "reason": "inventory_unreadable"}))
            return 1
        inventory = normalize_agents(raw_agents)
    agents = inventory.get("agents") if isinstance(inventory, dict) else None
    if not isinstance(agents, list):
        print(json.dumps({"ok": False, "reason": "inventory_rows_missing"}))
        return 1
    rejected = [agent for agent in agents if isinstance(agent, dict) and agent.get("remote_status") == "review_rejected"]
    details = {str(agent["agent_id"]): _remote_detail(str(agent["agent_id"])) for agent in rejected}
    if not args.no_gmail:
        _merge_gmail_reasons(details, rejected, gmail_rejection_reasons())
    try:
        existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"ok": False, "reason": "existing_queue_invalid"}))
        return 1
    queue = build_queue(existing, rejected, details, observed_at, all_agents=agents)
    _atomic_write(args.output, queue)
    print(json.dumps({"ok": True, "path": str(args.output), **queue["counts"]}, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
