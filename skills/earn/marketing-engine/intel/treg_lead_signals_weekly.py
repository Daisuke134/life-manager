#!/usr/bin/env python3
"""Run one cost-bounded, private Treg signal pass for all current products."""

from __future__ import annotations

import csv
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[4]
INTEL = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OWNER_ID = "marketing-treg-lead-signals-weekly"
TASK_CLASS = "treg-lead-signals-agent"
TREG_ESCALATION_REASON = (
    "User-authorized public product-signal research through the shared Treg budget gate."
)
ENTRYPOINT = "skills/earn/marketing-engine/intel/treg-lead-signals-weekly"
MAX_ROUTE_MICRO = 3_000
MAX_TOTAL_MICRO = 54_000
MIN_BALANCE = Decimal("0.05")
MAX_ROUTES = 18
MAX_CAPTURE_BYTES = 24 * 1024 * 1024
OCCURRENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CALL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
CSV_FIELDS = (
    "product_id", "platform", "person_url", "signal", "source_url",
    "observed_at", "why_now",
)
X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com", "redd.it", "www.redd.it"}
CANONICAL_NAMES = {
    "anicca-ios": "Anicca iOS (AIセルフケア・コンパニオン)",
    "honne-ai": "Honne AI",
    "ebook-en": "The Anicca Reset (EN)",
    "ebook-ja": "アニッチャ・リセット (JA)",
    "life-manager-cloud": "Life Manager Cloud",
}


class MonitorError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value: dt.datetime | None = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decimal(value: object, code: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise MonitorError(code)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise MonitorError(code) from None
    if not result.is_finite() or result < 0:
        raise MonitorError(code)
    return result


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise MonitorError("private_directory_invalid")
    os.chmod(path, 0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise MonitorError("private_directory_mode_invalid")


def _assert_outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return resolved
    raise MonitorError("private_state_inside_repository")


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    _ensure_private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temp_path, path)
            temp_path.unlink()
        else:
            os.replace(temp_path, path)
        _fsync_dir(path.parent)
    except FileExistsError:
        raise MonitorError("occurrence_already_recorded") from None
    finally:
        temp_path.unlink(missing_ok=True)


def _read_private(path: Path, *, max_bytes: int = MAX_CAPTURE_BYTES) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > max_bytes
        ):
            raise MonitorError("private_file_invalid")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            data = stream.read(max_bytes + 1)
    except OSError as error:
        raise MonitorError("private_file_unreadable") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > max_bytes:
        raise MonitorError("private_file_too_large")
    return data


def _read_json(path: Path, *, max_bytes: int = MAX_CAPTURE_BYTES) -> dict[str, Any]:
    try:
        value = json.loads(_read_private(path, max_bytes=max_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MonitorError("private_json_invalid") from None
    if not isinstance(value, dict):
        raise MonitorError("private_json_invalid")
    return value


def _occurrence_id(value: str | None) -> str:
    if not isinstance(value, str) or not OCCURRENCE_RE.fullmatch(value):
        raise MonitorError("occurrence_id_missing_or_invalid")
    if not value.startswith(f"{OWNER_ID}:"):
        raise MonitorError("occurrence_owner_mismatch")
    return value


def _occurrence_key(occurrence_id: str) -> str:
    return hashlib.sha256(occurrence_id.encode("utf-8")).hexdigest()


def _release_sha() -> str | None:
    direct = os.environ.get("LIFE_MANAGER_RELEASE_SHA")
    if isinstance(direct, str) and SHA_RE.fullmatch(direct):
        return direct
    release_root = Path(os.environ.get("LIFE_MANAGER_RELEASE_ROOT", ROOT))
    try:
        value = json.loads((release_root / "RELEASE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sha = value.get("sha") if isinstance(value, dict) else None
    return sha if isinstance(sha, str) and SHA_RE.fullmatch(sha) else None


def _state_paths(state_root: Path, evidence_root: Path, occurrence_id: str) -> tuple[Path, Path]:
    state_root = _assert_outside_repo(state_root)
    evidence_root = _assert_outside_repo(evidence_root)
    for directory in (state_root, state_root / "outbox", evidence_root):
        _ensure_private_dir(directory)
    key = _occurrence_key(occurrence_id)
    return state_root / "outbox" / f"{key}.json", evidence_root / key


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise MonitorError("product_profile_invalid") from None


def load_product_profiles(registry_dir: Path, extras_file: Path) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for path in sorted(registry_dir.glob("*.json")):
        source = _load_json(path)
        product_id = source.get("product_id")
        if not isinstance(product_id, str) or not product_id or path.stem != product_id:
            raise MonitorError("canonical_product_id_invalid")
        audiences = source.get("audiences", [])
        claims = source.get("approved_claims", [])
        if not isinstance(audiences, list) or not all(isinstance(item, str) for item in audiences):
            raise MonitorError("canonical_audience_invalid")
        if not isinstance(claims, list) or not all(isinstance(item, str) for item in claims):
            raise MonitorError("canonical_claims_invalid")
        listing_url = source.get("destination_url", "")
        if listing_url and (not isinstance(listing_url, str) or not listing_url.startswith("https://")):
            raise MonitorError("canonical_listing_url_invalid")
        profile = {
            "product_id": product_id,
            "display_name": CANONICAL_NAMES.get(product_id, product_id.replace("-", " ").title()),
            "type": source.get("type", "product"),
            "buyer_profile": " ".join([*audiences, *claims]),
            "listing_url": listing_url,
        }
        if product_id == "anicca-ios":
            profile["display_name"] = "Anicca iOS"
            profile["buyer_profile"] += (
                " Anicca is an AI self-care companion for timely affirmations around "
                "self-doubt, anxiety, and self-criticism."
            )
        canonical.append(profile)

    extras = _load_json(extras_file)
    extra_rows = extras.get("products") if isinstance(extras, dict) else None
    if not isinstance(extra_rows, list):
        raise MonitorError("supplemental_products_invalid")
    supplemental: list[dict[str, Any]] = []
    for source in extra_rows:
        if not isinstance(source, dict):
            raise MonitorError("supplemental_product_invalid")
        product_id = source.get("product_id")
        audience = source.get("audience")
        listing_url = source.get("app_store_url")
        if not all(isinstance(item, str) and item for item in (product_id, audience, listing_url)):
            raise MonitorError("supplemental_product_invalid")
        if not listing_url.startswith("https://"):
            raise MonitorError("supplemental_listing_url_invalid")
        supplemental.append({
            "product_id": product_id,
            "display_name": source.get("display_name", product_id),
            "type": source.get("type", "ios_app"),
            "buyer_profile": audience,
            "listing_url": listing_url,
        })

    products = canonical + supplemental
    ids = [row["product_id"] for row in products]
    if not ids or len(ids) != len(set(ids)):
        raise MonitorError("product_ids_missing_or_duplicate")
    ordered = [row for row in products if row["product_id"] == "anicca-ios"]
    if len(ordered) != 1:
        raise MonitorError("anicca_product_missing")
    return ordered + [row for row in products if row["product_id"] != "anicca-ios"]


def _agent_schema(schema_template: Path, products: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    schema = _load_json(schema_template)
    ids = [row["product_id"] for row in products]
    try:
        call_item = schema["properties"]["treg_calls"]["items"]
        signal_item = schema["properties"]["signals"]["items"]
        call_item["properties"]["product_id"]["enum"] = ids
        signal_item["properties"]["product_id"]["enum"] = ids
        schema["properties"]["treg_calls"]["maxItems"] = min(MAX_ROUTES, 2 * len(ids))
        schema["properties"]["signals"]["maxItems"] = len(ids)
    except (KeyError, TypeError):
        raise MonitorError("output_schema_template_invalid") from None
    _atomic_json(output_path, schema)
    return schema


def _build_prompt(
    products: list[dict[str, Any]],
    now: dt.datetime,
    recent_seen_keys: list[dict[str, str]],
) -> str:
    profiles = json.dumps(products, ensure_ascii=False, indent=2)
    seen = json.dumps(recent_seen_keys, ensure_ascii=False, indent=2)
    start = _timestamp(now - dt.timedelta(days=7))
    end = _timestamp(now)
    return f"""You are Life Manager's read-only public demand-signal monitor.

Observation window: {start} through {end} (UTC), inclusive. Review every supplied product profile in order; Anicca iOS is first.

Products and buyer profiles:
{profiles}

Exact signal keys already recorded by the host from this same seven-day window; do not return these as new:
{seen}

Use only public X and Reddit posts from this seven-day window. First read the Treg balance. Search the Treg catalog exactly once for a public X post-search route and once for a public Reddit post-search route; inspect the current endpoint and price for each with catalog_get. Return those two route checks. Use only those selected routes.

For every billed `call` tool input, set the `headers` argument's `X-Treg-Route-Max-Cost` value to `0.003`; Treg forwards that tool argument to the upstream route. The local gate independently enforces the route, total, and balance limits before forwarding. Make at most one X and one Reddit route call per product, at most 18 billed routes total. Before each paid call, preserve at least $0.05 after subtracting prior charges and unresolved reservations. If the balance funds only part of the scan, work in profile order, X then Reddit for each product, and stop at the first route whose quoted cost would cross the floor; do not skip ahead. If a Treg call is refused, errors, or returns without an exact receipt, stop paid calls for this occurrence and do not retry. Never top up or substitute a more expensive route. Check that each search is limited to the observation window.

Keep a signal only when a public post shows first-person pain or clear intent that the named product can address. Omit generic discussion, promotion, vendors, recruiters, uncertain fits, and duplicates. Return at most one strongest new signal for each product across both platforms. For every signal, copy the exact post URL and author/profile URL from that call's result, use its call_id, report the observed date, and explain briefly in Japanese why the timing is relevant. Do not invent, shorten, or normalize URLs.

Return every actual billed route in call order with its product, platform, endpoint_id, exact call_id, exact charged cost converted to integer micro-dollars, and result status. Do not report catalog or balance calls as billed routes. Do not perform email/phone lookup, contact enrichment, outreach, publishing, advertising, file writes, or other provider calls. Empty results are valid.
"""


def _default_agent_runner(
    prompt: str,
    schema_path: Path,
    evidence_dir: Path,
    occurrence_id: str,
) -> subprocess.CompletedProcess[str]:
    run_id = occurrence_id.split(":", 1)[1]
    label = f"treg-lead-signals-{hashlib.sha256(run_id.encode()).hexdigest()[:12]}"
    command = [
        str(ROOT / "skills/earn/marketing-engine/run_agent.sh"),
        "--task-class", TASK_CLASS,
        "--escalation-reason", TREG_ESCALATION_REASON,
        "--task-label", label,
        "--loop", OWNER_ID,
        "--schema", str(schema_path),
        "--evidence-dir", str(evidence_dir),
        "--workdir", str(ROOT),
        "--print-result",
    ]
    previous_mask = os.umask(0o077)
    try:
        child_env = os.environ.copy()
        child_env["LIFE_MANAGER_OCCURRENCE_ID"] = occurrence_id
        return subprocess.run(
            command, input=prompt, text=True, capture_output=True,
            timeout=1_900, cwd=ROOT, env=child_env, check=False,
        )
    finally:
        os.umask(previous_mask)


def _walk(value: Any, depth: int = 0):
    if depth > 8:
        return
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item, depth + 1)
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(decoded, str) or decoded != value:
            yield from _walk(decoded, depth + 1)


def _named_values(value: Any, names: set[str]) -> list[Any]:
    found: list[Any] = []
    for node in _walk(value):
        if isinstance(node, dict):
            for key in names:
                if key in node:
                    found.append(node[key])
    unique: list[Any] = []
    for item in found:
        if not any(item == prior for prior in unique):
            unique.append(item)
    return unique


def _text_tree(value: Any) -> str:
    parts = [str(node) for node in _walk(value) if isinstance(node, (str, int, float)) and not isinstance(node, bool)]
    return "\n".join(dict.fromkeys(parts))


def _mcp_events(evidence_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    logs = sorted(evidence_dir.glob("attempt-*.stdout.log"))
    if not logs:
        raise MonitorError("codex_mcp_trace_missing")
    for path in logs:
        try:
            lines = _read_private(path, max_bytes=MAX_CAPTURE_BYTES).decode("utf-8").splitlines()
        except UnicodeDecodeError:
            raise MonitorError("codex_mcp_trace_invalid") from None
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            details = item.get("details") if isinstance(item.get("details"), dict) else item
            if details.get("type") != "mcp_tool_call" or details.get("server") != "treg":
                continue
            result = details.get("result")
            result_errors = _named_values(result, {"error"})
            tool_error = bool(details.get("error")) or details.get("status") == "error" or any(
                value is True for value in _named_values(result, {"isError"})
            ) or any(value not in (None, "", False) for value in result_errors)
            events.append({
                "tool": details.get("tool"),
                "arguments": details.get("arguments", {}),
                "result": result,
                "error": tool_error,
                "status": details.get("status"),
            })
    return events


def _validate_gate_ledger(
    path: Path,
    occurrence_id: str,
    trace_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        raw = _read_private(path, max_bytes=2 * 1024 * 1024)
        ledger = json.loads(raw.decode("utf-8"))
    except MonitorError as error:
        code = "treg_gate_ledger_missing" if error.code == "private_file_unreadable" and not path.exists() else "treg_gate_ledger_invalid"
        raise MonitorError(code) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MonitorError("treg_gate_ledger_invalid") from None
    required = {
        "schema_version", "occurrence_id", "quotes", "calls", "route_count",
        "reserved_micro", "charged_micro", "unresolved_micro",
        "halted", "halt_reason", "blocked_attempt_count", "blocked_attempts",
    }
    if (
        not isinstance(ledger, dict)
        or set(ledger) != required
        or ledger.get("schema_version") != 1
        or ledger.get("occurrence_id") != occurrence_id
        or not isinstance(ledger.get("quotes"), dict)
        or not isinstance(ledger.get("calls"), list)
        or not isinstance(ledger.get("blocked_attempts"), list)
        or type(ledger.get("route_count")) is not int
        or type(ledger.get("reserved_micro")) is not int
        or type(ledger.get("charged_micro")) is not int
        or type(ledger.get("unresolved_micro")) is not int
        or type(ledger.get("halted")) is not bool
        or (ledger.get("halt_reason") is not None and not isinstance(ledger.get("halt_reason"), str))
        or type(ledger.get("blocked_attempt_count")) is not int
    ):
        raise MonitorError("treg_gate_ledger_invalid")
    calls = ledger["calls"]
    if (
        ledger["blocked_attempt_count"] != 0
        or ledger["halted"]
        or ledger["halt_reason"] is not None
        or ledger["route_count"] != len(calls)
        or ledger["route_count"] != len(trace_receipts)
        or ledger["route_count"] > MAX_ROUTES
        or ledger["reserved_micro"] != ledger["route_count"] * MAX_ROUTE_MICRO
        or ledger["reserved_micro"] > MAX_TOTAL_MICRO
        or ledger["unresolved_micro"] != 0
    ):
        raise MonitorError("treg_gate_route_ledger_mismatch")
    charged = 0
    for gate_call, receipt in zip(calls, trace_receipts, strict=True):
        if (
            not isinstance(gate_call, dict)
            or gate_call.get("occurrence_id") != occurrence_id
            or gate_call.get("reserved_micro") != MAX_ROUTE_MICRO
            or gate_call.get("status") != "settled"
            or gate_call.get("endpoint_id") != receipt.get("endpoint_id")
            or gate_call.get("call_id") != receipt.get("call_id")
            or gate_call.get("charged_micro") != receipt.get("charged_micro")
            or receipt.get("error")
            or receipt.get("call_id") is None
            or receipt.get("charged_micro") is None
        ):
            raise MonitorError("treg_gate_receipt_mismatch")
        charged += receipt["charged_micro"]
    if charged != ledger["charged_micro"] or charged > MAX_TOTAL_MICRO:
        raise MonitorError("treg_gate_receipt_mismatch")
    return ledger


def _one_event(events: list[dict[str, Any]], tool: str) -> dict[str, Any]:
    matches = [event for event in events if event.get("tool") == tool]
    if len(matches) != 1:
        raise MonitorError(f"treg_{tool}_call_count_invalid")
    if matches[0].get("error"):
        raise MonitorError(f"treg_{tool}_failed")
    return matches[0]


def _event_value_text(event: Mapping[str, Any], key: str) -> str:
    return _text_tree(event.get(key))


def _trace_call_receipts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_events = [event for event in events if event.get("tool") == "call"]
    receipts: list[dict[str, Any]] = []
    for event in route_events:
        result = event.get("result")
        call_ids = _named_values(result, {"call_id"})
        micro_values = _named_values(result, {"charged_micro"})
        cost_values = micro_values or _named_values(result, {"cost_usd"})
        call_id = call_ids[0] if len(call_ids) == 1 else None
        charged_micro: int | None = None
        if len(cost_values) == 1:
            cost = cost_values[0]
            if not isinstance(cost, bool) and micro_values and isinstance(cost, int):
                charged_micro = cost
            elif not isinstance(cost, bool):
                try:
                    amount = Decimal(str(cost))
                    if micro_values:
                        if amount == amount.to_integral_value():
                            charged_micro = int(amount)
                    else:
                        micro = amount * Decimal(1_000_000)
                        if micro == micro.to_integral_value():
                            charged_micro = int(micro)
                except (InvalidOperation, ValueError, TypeError):
                    charged_micro = None
        if not isinstance(call_id, str) or not CALL_ID_RE.fullmatch(call_id):
            call_id = None
        args = event.get("arguments")
        endpoint_values = _named_values(args, {"endpoint_id", "endpoint", "route_id"})
        endpoint_id = next((value for value in endpoint_values if isinstance(value, str)), None)
        header_values = _named_values(args, {"headers"})
        headers = header_values[0] if len(header_values) == 1 and isinstance(header_values[0], dict) else {}
        route_cap_header = any(
            isinstance(key, str) and key.lower() == "x-treg-route-max-cost" and str(value) == "0.003"
            for key, value in headers.items()
        )
        receipts.append({
            "call_id": call_id,
            "charged_micro": charged_micro,
            "endpoint_id": endpoint_id,
            "route_cap_header": route_cap_header,
            "arguments_text": _event_value_text(event, "arguments"),
            "result_text": _event_value_text(event, "result"),
            "error": bool(event.get("error")),
        })
    return receipts


def _validate_output(
    output: Any,
    products: list[dict[str, Any]],
    events: list[dict[str, Any]],
    now: dt.datetime,
) -> dict[str, Any]:
    required = {"schema_version", "balance_before_usd", "route_checks", "treg_calls", "signals"}
    if not isinstance(output, dict) or set(output) != required:
        raise MonitorError("agent_output_shape_invalid")
    if output.get("schema_version") != "life-manager.treg-lead-signals.v1":
        raise MonitorError("agent_output_version_invalid")
    product_ids = {row["product_id"] for row in products}
    balance = _decimal(output.get("balance_before_usd"), "balance_invalid")
    route_checks = output.get("route_checks")
    calls = output.get("treg_calls")
    signals = output.get("signals")
    if not isinstance(route_checks, list) or len(route_checks) != 2:
        raise MonitorError("route_checks_invalid")
    if not isinstance(calls, list) or not isinstance(signals, list):
        raise MonitorError("agent_rows_invalid")
    if len(signals) > len(products):
        raise MonitorError("signal_product_limit_exceeded")
    route_by_platform: dict[str, dict[str, Any]] = {}
    for row in route_checks:
        if not isinstance(row, dict):
            raise MonitorError("route_check_invalid")
        platform = row.get("platform")
        endpoint = row.get("endpoint_id")
        price = _decimal(row.get("price_usd"), "route_price_invalid")
        if platform not in {"x", "reddit"} or not isinstance(endpoint, str) or not endpoint:
            raise MonitorError("route_check_invalid")
        if platform in route_by_platform or price > Decimal("0.003"):
            raise MonitorError("route_check_invalid")
        route_by_platform[platform] = {"endpoint_id": endpoint, "price": price}
    if set(route_by_platform) != {"x", "reddit"}:
        raise MonitorError("route_platform_coverage_invalid")

    searches = [event for event in events if event.get("tool") == "catalog_search"]
    gets = [event for event in events if event.get("tool") == "catalog_get"]
    balance_event = _one_event(events, "balance")
    if len(searches) != 2 or len(gets) != 2:
        raise MonitorError("treg_catalog_call_count_invalid")
    if any(event.get("error") for event in searches + gets):
        raise MonitorError("treg_catalog_call_failed")
    balance_text = _event_value_text(balance_event, "result")
    if _decimal_text(balance) not in balance_text:
        raise MonitorError("balance_not_in_captured_result")
    for platform, route in route_by_platform.items():
        matches = [event for event in gets if route["endpoint_id"] in _event_value_text(event, "result")]
        if len(matches) != 1 or _decimal_text(route["price"]) not in _event_value_text(matches[0], "result"):
            raise MonitorError("catalog_price_not_in_captured_result")

    trace_receipts = _trace_call_receipts(events)
    if any(item["error"] or item["call_id"] is None or item["charged_micro"] is None for item in trace_receipts):
        raise MonitorError("treg_call_receipt_incomplete")
    if any(not item["route_cap_header"] for item in trace_receipts):
        raise MonitorError("treg_route_cost_header_missing")
    if len(trace_receipts) != len(calls) or len(trace_receipts) > min(MAX_ROUTES, 2 * len(products)):
        raise MonitorError("treg_route_count_invalid")
    trace_by_id = {item["call_id"]: item for item in trace_receipts}
    if len(trace_by_id) != len(trace_receipts):
        raise MonitorError("treg_call_id_duplicate")

    clean_calls: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, str]] = set()
    total_micro = 0
    for row in calls:
        if not isinstance(row, dict):
            raise MonitorError("treg_call_row_invalid")
        product_id, platform, endpoint_id, call_id = (
            row.get("product_id"), row.get("platform"), row.get("endpoint_id"), row.get("call_id")
        )
        if product_id not in product_ids or platform not in {"x", "reddit"}:
            raise MonitorError("treg_call_scope_invalid")
        if not isinstance(endpoint_id, str) or endpoint_id != route_by_platform[platform]["endpoint_id"]:
            raise MonitorError("treg_call_endpoint_mismatch")
        if not isinstance(call_id, str) or call_id not in trace_by_id:
            raise MonitorError("treg_call_id_not_captured")
        charged_micro = row.get("charged_micro")
        captured = trace_by_id[call_id]
        if type(charged_micro) is not int or charged_micro != captured["charged_micro"]:
            raise MonitorError("treg_call_cost_mismatch")
        if charged_micro < 0 or charged_micro > MAX_ROUTE_MICRO:
            raise MonitorError("treg_route_cost_limit_exceeded")
        if captured["endpoint_id"] is not None:
            endpoint_captured = endpoint_id == captured["endpoint_id"]
        else:
            endpoint_captured = endpoint_id in captured["arguments_text"] or endpoint_id in captured["result_text"]
        if not endpoint_captured:
            raise MonitorError("treg_call_endpoint_not_captured")
        if row.get("result_status") not in {"success", "empty", "failed"}:
            raise MonitorError("treg_call_status_invalid")
        route_key = (product_id, platform)
        if route_key in seen_routes:
            raise MonitorError("duplicate_product_platform_route")
        seen_routes.add(route_key)
        total_micro += charged_micro
        clean_calls.append({
            "product_id": product_id,
            "platform": platform,
            "endpoint_id": endpoint_id,
            "call_id": call_id,
            "charged_micro": charged_micro,
            "result_status": row["result_status"],
        })
    if [row["call_id"] for row in clean_calls] != [row["call_id"] for row in trace_receipts]:
        raise MonitorError("treg_call_order_mismatch")
    if total_micro > MAX_TOTAL_MICRO:
        raise MonitorError("weekly_route_budget_exceeded")

    clean_signals: list[dict[str, Any]] = []
    signal_products: set[str] = set()
    for row in signals:
        if not isinstance(row, dict):
            raise MonitorError("signal_row_invalid")
        product_id = row.get("product_id")
        platform = row.get("platform")
        person_url = row.get("person_url")
        source_url = row.get("source_url")
        signal = row.get("signal")
        call_id = row.get("call_id")
        why_now = row.get("why_now")
        if product_id not in product_ids or product_id in signal_products:
            raise MonitorError("signal_product_duplicate_or_unknown")
        if platform not in {"x", "reddit"} or not isinstance(call_id, str) or call_id not in trace_by_id:
            raise MonitorError("signal_route_invalid")
        call = next(item for item in clean_calls if item["call_id"] == call_id)
        if call["product_id"] != product_id or call["platform"] != platform or call["result_status"] == "failed":
            raise MonitorError("signal_route_mismatch")
        if not isinstance(person_url, str) or not isinstance(source_url, str):
            raise MonitorError("signal_url_invalid")
        _validate_public_url(person_url, platform)
        _validate_public_url(source_url, platform)
        captured_text = trace_by_id[call_id]["result_text"]
        if source_url not in captured_text or person_url not in captured_text:
            raise MonitorError("signal_url_not_in_captured_result")
        if signal not in {"pain", "explicit_intent", "competitor_complaint"}:
            raise MonitorError("signal_type_invalid")
        if not isinstance(why_now, str) or not why_now.strip() or len(why_now) > 240:
            raise MonitorError("signal_reason_invalid")
        observed = row.get("observed_at")
        if not isinstance(observed, str):
            raise MonitorError("signal_timestamp_invalid")
        try:
            observed_at = dt.datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError:
            raise MonitorError("signal_timestamp_invalid") from None
        if observed_at.tzinfo is None or observed_at < now - dt.timedelta(days=7) or observed_at > now + dt.timedelta(minutes=5):
            raise MonitorError("signal_outside_observation_window")
        if observed_at.date().isoformat() not in captured_text:
            raise MonitorError("signal_timestamp_not_in_captured_result")
        clean_signals.append({
            "product_id": product_id,
            "platform": platform,
            "person_url": person_url,
            "signal": signal,
            "source_url": source_url,
            "observed_at": observed,
            "why_now": why_now.strip(),
            "call_id": call_id,
        })
        signal_products.add(product_id)
    if balance <= MIN_BALANCE:
        if clean_calls or clean_signals:
            raise MonitorError("balance_floor_call_was_made")
    elif balance - Decimal(total_micro) / Decimal(1_000_000) < MIN_BALANCE:
        raise MonitorError("balance_floor_would_be_crossed")

    available = balance - MIN_BALANCE
    expected_prefix: list[tuple[str, str]] = []
    for product in products:
        for platform in ("x", "reddit"):
            price = route_by_platform[platform]["price"]
            if price > available:
                break
            expected_prefix.append((product["product_id"], platform))
            available -= price
        else:
            continue
        break
    actual_pairs = [(row["product_id"], row["platform"]) for row in clean_calls]
    if actual_pairs != expected_prefix:
        raise MonitorError("product_route_priority_or_coverage_invalid")
    return {
        "balance_before_usd": _decimal_text(balance),
        "route_checks": [
            {"platform": platform, "endpoint_id": route["endpoint_id"], "price_usd": _decimal_text(route["price"])}
            for platform, route in sorted(route_by_platform.items())
        ],
        "treg_calls": clean_calls,
        "signals": clean_signals,
        "charged_micro": total_micro,
        "route_budget_exhausted": not expected_prefix,
    }


def _validate_public_url(value: str, platform: str) -> None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise MonitorError("signal_url_invalid") from None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MonitorError("signal_url_invalid")
    host = parsed.hostname.lower()
    allowed = X_HOSTS if platform == "x" else REDDIT_HOSTS
    if host not in allowed:
        raise MonitorError("signal_url_platform_mismatch")


def _signal_key(row: Mapping[str, str]) -> tuple[str, str, str, str]:
    return (row["product_id"], row["person_url"], row["signal"], row["source_url"])


def _recent_seen_keys(rows: list[dict[str, str]], now: dt.datetime) -> list[dict[str, str]]:
    cutoff = now - dt.timedelta(days=7)
    result = []
    for row in rows:
        try:
            observed = dt.datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            raise MonitorError("signals_csv_timestamp_invalid") from None
        if observed.tzinfo is None or observed > now + dt.timedelta(minutes=5):
            raise MonitorError("signals_csv_timestamp_invalid")
        if observed >= cutoff:
            result.append({field: row[field] for field in ("product_id", "person_url", "signal", "source_url")})
    result.sort(key=lambda row: tuple(row[field] for field in ("product_id", "person_url", "signal", "source_url")))
    return result


def _read_signals(path: Path) -> list[dict[str, str]] | None:
    try:
        raw = _read_private(path, max_bytes=8 * 1024 * 1024)
    except MonitorError as error:
        if error.code == "private_file_unreadable" and not path.exists() and not path.is_symlink():
            marker = path.with_name("signals.baseline.json")
            if marker.exists() or marker.is_symlink():
                raise MonitorError("signals_csv_missing_after_baseline") from None
            return None
        raise
    try:
        text = raw.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise MonitorError("signals_csv_header_invalid")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise MonitorError("signals_csv_invalid") from None
    keys = [_signal_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise MonitorError("signals_csv_duplicate_key")
    for row in rows:
        if set(row) != set(CSV_FIELDS) or any(not isinstance(row[field], str) for field in CSV_FIELDS):
            raise MonitorError("signals_csv_row_invalid")
    marker_path = path.with_name("signals.baseline.json")
    try:
        marker = json.loads(_read_private(marker_path, max_bytes=4096).decode("utf-8"))
    except MonitorError as error:
        code = "signals_csv_baseline_missing" if error.code == "private_file_unreadable" else "signals_csv_baseline_invalid"
        raise MonitorError(code) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MonitorError("signals_csv_baseline_invalid") from None
    if (
        not isinstance(marker, dict)
        or set(marker) != {"schema_version", "signals_sha256", "row_count"}
        or marker.get("schema_version") != 1
        or marker.get("signals_sha256") != hashlib.sha256(raw).hexdigest()
        or marker.get("row_count") != len(rows)
    ):
        raise MonitorError("signals_csv_baseline_mismatch")
    return rows


def _write_signals(path: Path, rows: list[dict[str, str]], product_order: Mapping[str, int]) -> None:
    unique = {
        _signal_key(row): {field: row[field] for field in CSV_FIELDS}
        for row in rows
    }
    ordered = sorted(unique.values(), key=lambda row: (product_order.get(row["product_id"], 999), row["observed_at"], row["source_url"]))
    _ensure_private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(ordered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        _fsync_dir(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)
    raw = _read_private(path, max_bytes=8 * 1024 * 1024)
    _atomic_json(path.with_name("signals.baseline.json"), {
        "schema_version": 1,
        "signals_sha256": hashlib.sha256(raw).hexdigest(),
        "row_count": len(ordered),
    })


def _validate_result_hint_path(path_value: str | None) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise MonitorError("life_manager_result_hint_missing")
    path = Path(path_value)
    if path.name != "entrypoint-result.json" or not path.is_absolute() or not path.parent.is_dir() or path.parent.is_symlink():
        raise MonitorError("life_manager_result_hint_path_invalid")
    parent_info = path.parent.stat()
    if parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) != 0o700:
        raise MonitorError("life_manager_result_hint_parent_not_private")
    return path


def _write_result_hint(path_value: str | None, occurrence_id: str, *, receipt_id: str | None = None, reason: str | None = None) -> None:
    path = _validate_result_hint_path(path_value)
    base = {
        "schema_version": 1,
        "kind": "life_manager_effect_result" if receipt_id else "life_manager_no_effect_result",
        "status": "verified_effect" if receipt_id else "verified_no_effect",
        "effect": 1 if receipt_id else 0,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
    }
    if receipt_id:
        base.update({
            "provider": "telegram",
            "provider_receipt_id": receipt_id,
            "effect_status": "verified",
        })
    else:
        if reason not in {"baseline_established", "no_new_signals", "balance_floor"}:
            raise MonitorError("no_effect_reason_invalid")
        base["reason"] = reason
    _atomic_json(path, base)


def _report_text(signals: list[dict[str, Any]], products: list[dict[str, Any]], now: dt.datetime) -> str:
    names = {row["product_id"]: row["display_name"] for row in products}
    lines = [f"今週の新しい公開シグナル（{(now - dt.timedelta(days=7)).date()}〜{now.date()}）"]
    for row in signals:
        platform = "X" if row["platform"] == "x" else "Reddit"
        lines.extend([
            f"\n・{names[row['product_id']]} / {platform}",
            row["why_now"],
            row["source_url"],
        ])
    return "\n".join(lines)


def _capture_partial(receipts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int | None]:
    rows = []
    total = 0
    known = True
    for item in receipts:
        if item.get("call_id") and item.get("charged_micro") is not None:
            rows.append({"call_id": item["call_id"], "charged_micro": item["charged_micro"]})
            total += item["charged_micro"]
        else:
            known = False
    return rows, total if known else None


def _agent_output(completed: subprocess.CompletedProcess[str]) -> Any:
    if completed.returncode != 0:
        raise MonitorError("agent_run_failed")
    try:
        return json.loads(completed.stdout, parse_float=Decimal)
    except (json.JSONDecodeError, TypeError):
        raise MonitorError("agent_output_not_json") from None


def run_weekly_monitor(
    *,
    state_root: Path,
    evidence_root: Path,
    agent_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    occurrence_id = _occurrence_id(os.environ.get("LIFE_MANAGER_OCCURRENCE_ID"))
    hint_path = os.environ.get("LIFE_MANAGER_RESULT_HINT_PATH")
    _validate_result_hint_path(hint_path)
    state_path, evidence_dir = _state_paths(Path(state_root), Path(evidence_root), occurrence_id)
    record: dict[str, Any] = {
        "schema_version": 1,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "run_id": os.environ.get("LIFE_MANAGER_RUN_ID", occurrence_id.split(":", 1)[1]),
        "release_sha": _release_sha(),
        "phase": "preflight",
        "command": "run_agent.sh --task-class treg-lead-signals-agent",
        "status": "started",
        "exit_code": None,
        "effect": "not_attempted",
        "readback": "not_required",
        "provider_receipt_id": None,
        "evidence_refs": [str(evidence_dir)],
        "billing_status": "not_started",
        "charged_micro": 0,
        "error_class": None,
        "retryable": False,
        "next_action": "run_bounded_public_signal_pass",
        "telegram_dispatch_started": False,
        "created_at": _timestamp(),
    }
    _atomic_json(state_path, record, exclusive=True)
    try:
        existing = _read_signals(Path(state_root) / "signals.csv")
        products = load_product_profiles(
            INTEL.parent / "registry" / "products",
            INTEL / "lead-signals-products-extra.json",
        )
        if 2 * len(products) > MAX_ROUTES:
            raise MonitorError("all_products_exceed_weekly_route_budget")
        now = _utc_now()
        schema_path = evidence_dir / "lead-signals-output.schema.json"
        _agent_schema(INTEL / "lead-signals-output.schema.json", products, schema_path)
        prompt = _build_prompt(products, now, _recent_seen_keys(existing or [], now))
        record.update({"phase": "agent", "status": "agent_running", "billing_status": "pending", "charged_micro": None, "next_action": "validate_treg_tool_results"})
        _atomic_json(state_path, record)
        if agent_runner is None:
            completed = _default_agent_runner(
                prompt,
                schema_path,
                evidence_dir,
                occurrence_id,
            )
        else:
            completed = agent_runner(prompt, schema_path, evidence_dir, occurrence_id)
        events = _mcp_events(evidence_dir)
        trace_receipts = _trace_call_receipts([event for event in events if event.get("tool") == "call"])
        partial, partial_total = _capture_partial(trace_receipts)
        record.update({
            "treg_calls": partial,
            "charged_micro": partial_total,
            "partial_charged_micro": partial_total,
            "billing_status": "incomplete",
        })
        _atomic_json(state_path, record)
        if completed.returncode != 0:
            record.update({
                "status": "agent_failed",
                "exit_code": completed.returncode,
            "error_class": "agent_run_failed",
            "retryable": False,
            "next_action": "reconcile_no_telegram_dispatch",
            })
            _atomic_json(state_path, record)
            raise MonitorError("agent_run_failed")
        gate_ledger = _validate_gate_ledger(
            evidence_dir / "treg-budget-occurrence.json",
            occurrence_id,
            trace_receipts,
        )
        record.update({
            "treg_gate_route_count": gate_ledger["route_count"],
            "treg_gate_reserved_micro": gate_ledger["reserved_micro"],
            "treg_gate_charged_micro": gate_ledger["charged_micro"],
            "billing_status": "verified" if partial_total is not None else "incomplete",
        })
        _atomic_json(state_path, record)
        output = _agent_output(completed)
        normalized = _validate_output(output, products, events, now)
        record.update({
            "phase": "qualified",
            "status": "validated",
            "treg_calls": normalized["treg_calls"],
            "treg_call_ids": [row["call_id"] for row in normalized["treg_calls"]],
            "charged_micro": normalized["charged_micro"],
            "billing_status": "verified",
            "balance_before_usd": normalized["balance_before_usd"],
            "signal_rows": [
                {field: row[field] for field in CSV_FIELDS}
                for row in normalized["signals"]
            ],
            "qualified_count": len(normalized["signals"]),
            "observed_at": _timestamp(now),
        })

        if normalized["route_budget_exhausted"] and not normalized["treg_calls"] and not normalized["signals"]:
            record.update({"status": "balance_floor", "phase": "decision", "effect": "not_applicable", "exit_code": 0})
            _atomic_json(state_path, record)
            _write_result_hint(hint_path, occurrence_id, reason="balance_floor")
            return _summary(record, baseline_count=0, new_count=0)

        prior_rows = existing or []
        if existing is None:
            record.update({"status": "baseline_established", "phase": "decision", "effect": "not_applicable", "exit_code": 0})
            _atomic_json(state_path, record)
            _write_signals(
                Path(state_root) / "signals.csv",
                record["signal_rows"],
                {row["product_id"]: index for index, row in enumerate(products)},
            )
            _write_result_hint(hint_path, occurrence_id, reason="baseline_established")
            return _summary(record, baseline_count=len(record["signal_rows"]), new_count=0)

        seen = {_signal_key(row) for row in prior_rows}
        new_rows = [row for row in record["signal_rows"] if _signal_key(row) not in seen]
        if not new_rows:
            record.update({"status": "no_new_signals", "phase": "decision", "effect": "not_applicable", "exit_code": 0})
            _atomic_json(state_path, record)
            _write_result_hint(hint_path, occurrence_id, reason="no_new_signals")
            return _summary(record, baseline_count=0, new_count=0)

        product_order = {row["product_id"]: index for index, row in enumerate(products)}
        new_rows.sort(key=lambda row: (product_order.get(row["product_id"], 999), row["observed_at"]))
        body = _report_text(new_rows, products, now)
        try:
            from skills._shared.telegram import TelegramClient, TelegramDeliveryUnknown

            telegram_client = TelegramClient.from_env()
        except Exception:
            record.update({
                "status": "telegram_preflight_failed",
                "phase": "preflight",
                "error_class": "telegram_configuration_unavailable",
                "exit_code": 1,
                "retryable": False,
                "next_action": "reconcile_no_telegram_dispatch",
            })
            _atomic_json(state_path, record)
            raise MonitorError("telegram_configuration_unavailable") from None
        record.update({
            "status": "send_started",
            "phase": "telegram_send",
            "effect": "unknown",
            "telegram_dispatch_started": True,
            "dispatch_started_at": _timestamp(),
            "report_body": body,
            "report_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "new_signal_rows": new_rows,
            "new_count": len(new_rows),
            "readback": "pending",
            "next_action": "telegram_receipt_or_official_history_readback",
        })
        _atomic_json(state_path, record)
        try:
            telegram_receipt = telegram_client.send_text(body)
        except Exception as error:
            record.update({
                "status": "send_unknown",
                "error_class": "telegram_delivery_unknown" if isinstance(error, TelegramDeliveryUnknown) else "telegram_send_failed",
                "exit_code": 1,
                "retryable": False,
                "readback": "pending",
                "next_action": "read_exact_telegram_message_without_resend",
            })
            _atomic_json(state_path, record)
            raise MonitorError(record["error_class"]) from None
        message_ids = telegram_receipt.get("message_ids") if isinstance(telegram_receipt, dict) else None
        if (
            not isinstance(message_ids, list)
            or not message_ids
            or any(type(message_id) is not int or message_id <= 0 for message_id in message_ids)
            or telegram_receipt.get("status") != "delivered"
        ):
            record.update({"status": "send_unknown", "error_class": "telegram_receipt_invalid", "exit_code": 1, "next_action": "read_exact_telegram_message_without_resend"})
            _atomic_json(state_path, record)
            raise MonitorError("telegram_receipt_invalid")
        primary_id = str(message_ids[0])
        record.update({
            "status": "delivered",
            "phase": "receipt_persisted",
            "effect": "verified",
            "exit_code": 0,
            "provider_receipt_id": primary_id,
            "telegram_receipt": telegram_receipt,
            "readback": "send_api_receipt",
            "retryable": False,
            "next_action": "await_next_weekly_occurrence",
        })
        _atomic_json(state_path, record)
        _write_signals(Path(state_root) / "signals.csv", prior_rows + new_rows, product_order)
        _write_result_hint(hint_path, occurrence_id, receipt_id=primary_id)
        return _summary(record, baseline_count=0, new_count=len(new_rows))
    except MonitorError as error:
        if record.get("status") not in {"agent_failed", "send_unknown", "delivered", "baseline_established", "no_new_signals", "balance_floor", "telegram_preflight_failed"}:
            record.update({
                "status": "failed_before_telegram",
                "error_class": error.code,
                "exit_code": 1,
                "retryable": False,
                "next_action": "reconcile_no_telegram_dispatch",
            })
            try:
                _atomic_json(state_path, record)
            except Exception:
                pass
        raise
    except Exception as error:
        record.update({
            "status": "failed_before_telegram" if not record.get("telegram_dispatch_started") else "send_unknown",
            "error_class": type(error).__name__,
            "exit_code": 1,
            "retryable": False,
            "next_action": "reconcile_no_telegram_dispatch" if not record.get("telegram_dispatch_started") else "read_exact_telegram_message_without_resend",
        })
        try:
            _atomic_json(state_path, record)
        except Exception:
            pass
        raise MonitorError("weekly_monitor_failed") from None


def _summary(record: Mapping[str, Any], *, baseline_count: int, new_count: int) -> dict[str, Any]:
    return {
        "status": "pass",
        "owner_id": OWNER_ID,
        "occurrence_id": record["occurrence_id"],
        "treg_call_ids": record.get("treg_call_ids", []),
        "charged_micro": record.get("charged_micro", 0),
        "baseline_count": baseline_count,
        "new_count": new_count,
        "provider_receipt_id": record.get("provider_receipt_id"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_state_root = Path(os.path.expanduser("~/.local/state/life-manager/marketing-treg-lead-signals"))
    parser.add_argument("--state-root", type=Path, default=Path(os.environ.get("LIFE_MANAGER_STATE_ROOT", default_state_root)))
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser()
    evidence_root = (args.evidence_root or state_root / "evidence").expanduser()
    try:
        result = run_weekly_monitor(state_root=state_root, evidence_root=evidence_root)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except MonitorError as error:
        print(json.dumps({"status": "failed", "owner_id": OWNER_ID, "error_class": error.code}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as error:
        print(json.dumps({"status": "failed", "owner_id": OWNER_ID, "error_class": type(error).__name__}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
