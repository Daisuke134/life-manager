#!/usr/bin/env python3
"""Local stdio MCP proxy that gates Treg calls before they can spend team balance."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from treg_credentials import load_treg_agent_token


TREG_MCP_URL = "https://treg.to/mcp/"
TREG_TOOLS = {"catalog_search", "catalog_get", "call", "balance"}
MAX_ROUTE_MICRO = 3_000
MAX_TOTAL_MICRO = 54_000
MAX_ROUTES = 18
MIN_BALANCE_MICRO = 50_000
MAX_QUOTE_AGE = dt.timedelta(minutes=30)
OCCURRENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CALL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
MAX_LEDGER_BYTES = 2 * 1024 * 1024


class GateRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RemoteMCPError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value: dt.datetime | None = None) -> str:
    return (value or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise GateRejected("budget_state_directory_invalid")
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise GateRejected("budget_state_directory_mode_invalid")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError:
        raise GateRejected("budget_ledger_unreadable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > MAX_LEDGER_BYTES
        ):
            raise GateRejected("budget_ledger_invalid")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            value = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise GateRejected("budget_ledger_invalid") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise GateRejected("budget_ledger_invalid")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        raise GateRejected("budget_ledger_write_failed") from None
    finally:
        temporary_path.unlink(missing_ok=True)


@contextmanager
def _locked(daily_path: Path) -> Iterator[None]:
    _private_dir(daily_path.parent)
    lock_path = daily_path.parent / "treg-budget.lock"
    descriptor = os.open(
        lock_path,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise GateRejected("budget_lock_invalid")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _walk(value: Any, depth: int = 0) -> Iterator[Any]:
    if depth > 10:
        return
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, depth + 1)
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return
        if decoded != value:
            yield from _walk(decoded, depth + 1)


def _values(value: Any, names: set[str]) -> list[Any]:
    found: list[Any] = []
    for node in _walk(value):
        if isinstance(node, dict):
            found.extend(node[name] for name in names if name in node)
    unique: list[Any] = []
    for item in found:
        if not any(item == existing for existing in unique):
            unique.append(item)
    return unique


def _micro(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise GateRejected("budget_amount_invalid")
    try:
        amount = Decimal(str(value))
        micro = amount * Decimal(1_000_000)
    except (InvalidOperation, ValueError):
        raise GateRejected("budget_amount_invalid") from None
    if not amount.is_finite() or amount < 0 or micro != micro.to_integral_value():
        raise GateRejected("budget_amount_invalid")
    return int(micro)


def _tool_result_error(value: Any) -> bool:
    return any(
        isinstance(node, dict)
        and (node.get("isError") is True or node.get("error") not in (None, "", False))
        for node in _walk(value)
    )


def _balance_micro(value: Any) -> int:
    balances = _values(value, {"balance_micro"})
    holds = _values(value, {"holds_micro"})
    if len(balances) != 1 or len(holds) > 1 or _tool_result_error(value):
        raise GateRejected("balance_readback_invalid")
    balance = balances[0]
    if type(balance) is not int or balance < 0:
        raise GateRejected("balance_readback_invalid")
    hold = holds[0] if holds and holds[0] is not None else 0
    if type(hold) is not int or hold < 0 or hold > balance:
        raise GateRejected("balance_readback_invalid")
    return balance - hold


def _call_receipt(value: Any) -> tuple[str, int] | None:
    ids = _values(value, {"call_id"})
    micro_values = _values(value, {"charged_micro"})
    costs = micro_values or _values(value, {"cost_usd"})
    if len(ids) != 1 or len(costs) != 1:
        return None
    call_id = ids[0]
    if not isinstance(call_id, str) or not CALL_ID_RE.fullmatch(call_id):
        return None
    try:
        cost = costs[0] if micro_values else _micro(costs[0])
    except GateRejected:
        return None
    if type(cost) is not int or cost < 0:
        return None
    return call_id, cost


def _default_daily() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "route_count": 0,
        "reserved_micro": 0,
        "charged_micro": 0,
        "unresolved_micro": 0,
        "calls": [],
    }


def _default_pending() -> dict[str, Any]:
    return {"schema_version": 1, "unresolved_micro": 0, "calls": []}


def _default_occurrence(occurrence_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "occurrence_id": occurrence_id,
        "quotes": {},
        "calls": [],
        "route_count": 0,
        "reserved_micro": 0,
        "charged_micro": 0,
        "unresolved_micro": 0,
        "halted": False,
        "halt_reason": None,
        "blocked_attempt_count": 0,
        "blocked_attempts": [],
    }


class TregBudgetGate:
    def __init__(self, *, daily_ledger: Path, occurrence_ledger: Path, occurrence_id: str) -> None:
        if not OCCURRENCE_RE.fullmatch(occurrence_id):
            raise GateRejected("budget_occurrence_invalid")
        self.daily_ledger = Path(daily_ledger)
        self.occurrence_ledger = Path(occurrence_ledger)
        self.pending_ledger = self.daily_ledger.parent / "treg-budget-pending.json"
        self.occurrence_id = occurrence_id

    def _current_daily_ledger(self) -> Path:
        prefix = "treg-budget-daily-"
        if re.fullmatch(r"treg-budget-daily-\d{4}-\d{2}-\d{2}\.json", self.daily_ledger.name):
            return self.daily_ledger.with_name(
                f"{prefix}{_now().date().isoformat()}.json"
            )
        return self.daily_ledger

    def _daily(self, daily_path: Path) -> dict[str, Any]:
        value = _read_json(daily_path)
        if value is None:
            return _default_daily()
        if (
            set(value) != set(_default_daily())
            or value.get("schema_version") != 1
            or type(value.get("route_count")) is not int
            or type(value.get("reserved_micro")) is not int
            or type(value.get("charged_micro")) is not int
            or type(value.get("unresolved_micro")) is not int
            or not isinstance(value.get("calls"), list)
        ):
            raise GateRejected("budget_daily_ledger_invalid")
        if (
            value["route_count"] < 0
            or value["reserved_micro"] < 0
            or value["charged_micro"] < 0
            or value["unresolved_micro"] < 0
            or value["route_count"] != len(value["calls"])
            or value["reserved_micro"] != value["route_count"] * MAX_ROUTE_MICRO
            or value["unresolved_micro"] > value["reserved_micro"]
        ):
            raise GateRejected("budget_daily_ledger_invalid")
        return value

    def _pending(self) -> dict[str, Any]:
        value = _read_json(self.pending_ledger)
        if value is None:
            return _default_pending()
        if (
            set(value) != set(_default_pending())
            or value.get("schema_version") != 1
            or type(value.get("unresolved_micro")) is not int
            or value["unresolved_micro"] < 0
            or not isinstance(value.get("calls"), list)
            or any(
                not isinstance(row, dict)
                or row.get("status") != "unknown"
                or type(row.get("reserved_micro")) is not int
                or row["reserved_micro"] != MAX_ROUTE_MICRO
                for row in value["calls"]
            )
            or value["unresolved_micro"] != sum(row["reserved_micro"] for row in value["calls"])
        ):
            raise GateRejected("budget_pending_ledger_invalid")
        return value

    def _occurrence(self) -> dict[str, Any]:
        value = _read_json(self.occurrence_ledger)
        if value is None:
            return _default_occurrence(self.occurrence_id)
        if (
            value.get("schema_version") != 1
            or value.get("occurrence_id") != self.occurrence_id
            or not isinstance(value.get("quotes"), dict)
            or not isinstance(value.get("calls"), list)
            or type(value.get("route_count")) is not int
            or type(value.get("reserved_micro")) is not int
            or type(value.get("charged_micro")) is not int
            or type(value.get("unresolved_micro")) is not int
            or type(value.get("halted")) is not bool
            or (value.get("halt_reason") is not None and not isinstance(value.get("halt_reason"), str))
            or type(value.get("blocked_attempt_count")) is not int
            or not isinstance(value.get("blocked_attempts"), list)
        ):
            raise GateRejected("budget_occurrence_ledger_invalid")
        if (
            value["route_count"] < 0
            or value["reserved_micro"] < 0
            or value["charged_micro"] < 0
            or value["unresolved_micro"] < 0
            or value["blocked_attempt_count"] < len(value["blocked_attempts"])
            or value["route_count"] != len(value["calls"])
            or value["reserved_micro"] != value["route_count"] * MAX_ROUTE_MICRO
            or value["unresolved_micro"] > value["reserved_micro"]
        ):
            raise GateRejected("budget_occurrence_ledger_invalid")
        return value

    def record_quote(self, endpoint_id: str, quote_micro: int, *, unsafe: bool = False) -> None:
        if not isinstance(endpoint_id, str) or not endpoint_id or type(quote_micro) is not int or quote_micro < 0:
            raise GateRejected("catalog_quote_invalid")
        with _locked(self.daily_ledger):
            occurrence = self._occurrence()
            occurrence["quotes"][endpoint_id] = {
                "quote_micro": quote_micro,
                "unsafe": bool(unsafe or quote_micro > MAX_ROUTE_MICRO),
                "observed_at": _timestamp(),
            }
            _write_json(self.occurrence_ledger, occurrence)

    def record_catalog_result(self, endpoint_id: str, result: Any) -> None:
        prices = _values(result, {"usd_per_call"})
        overflow_prices = _values(result, {"overflow_price_usd"})
        overflow_units = _values(result, {"overflow_price_unit"})
        safe = not _tool_result_error(result) and len(prices) == 1
        quote_micro: int | None = None
        try:
            quote_micro = _micro(prices[0]) if safe else None
            if overflow_prices and overflow_prices[0] is not None:
                if len(overflow_prices) != 1 or overflow_units != ["call"]:
                    safe = False
                else:
                    quote_micro = max(quote_micro or 0, _micro(overflow_prices[0]))
        except GateRejected:
            safe = False
        if quote_micro is None:
            quote_micro = MAX_ROUTE_MICRO + 1
        self.record_quote(endpoint_id, quote_micro, unsafe=not safe)

    def _block(self, occurrence: dict[str, Any], endpoint_id: str, code: str) -> None:
        occurrence["blocked_attempt_count"] += 1
        if len(occurrence["blocked_attempts"]) < 20:
            occurrence["blocked_attempts"].append({
                "endpoint_id": endpoint_id,
                "error_class": code,
                "created_at": _timestamp(),
            })
        _write_json(self.occurrence_ledger, occurrence)
        raise GateRejected(code)

    def call_paid(
        self,
        arguments: dict[str, Any],
        forward_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        endpoint_id = arguments.get("endpoint_id")
        if not isinstance(endpoint_id, str) or not endpoint_id:
            raise GateRejected("budget_endpoint_invalid")
        headers = arguments.get("headers")
        matching = [
            value for key, value in headers.items()
            if isinstance(key, str) and key.lower() == "x-treg-route-max-cost"
        ] if isinstance(headers, dict) else []
        with _locked(self.daily_ledger):
            # A gate process can outlive the UTC day in its startup path.
            # Select the active ledger only after taking the shared lock.
            daily_path = self._current_daily_ledger()
            daily = self._daily(daily_path)
            occurrence = self._occurrence()
            pending = self._pending()
            if occurrence["halted"] or any(
                row.get("status") != "settled" for row in occurrence["calls"]
            ):
                self._block(occurrence, endpoint_id, "treg_budget_previous_call_uncertain")
            quote = occurrence["quotes"].get(endpoint_id)
            if len(matching) != 1 or str(matching[0]) != "0.003":
                self._block(occurrence, endpoint_id, "treg_budget_route_cap_header_invalid")
            if (
                not isinstance(quote, dict)
                or quote.get("unsafe") is not False
                or type(quote.get("quote_micro")) is not int
                or quote["quote_micro"] > MAX_ROUTE_MICRO
            ):
                self._block(occurrence, endpoint_id, "treg_budget_quote_invalid")
            try:
                quote_time = dt.datetime.fromisoformat(quote["observed_at"].replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                self._block(occurrence, endpoint_id, "treg_budget_quote_invalid")
            if quote_time.tzinfo is None or _now() - quote_time > MAX_QUOTE_AGE or quote_time > _now() + dt.timedelta(minutes=1):
                self._block(occurrence, endpoint_id, "treg_budget_quote_stale")
            if (
                occurrence["route_count"] >= MAX_ROUTES
                or occurrence["reserved_micro"] + MAX_ROUTE_MICRO > MAX_TOTAL_MICRO
                or occurrence["charged_micro"] + occurrence["unresolved_micro"] + MAX_ROUTE_MICRO > MAX_TOTAL_MICRO
                or daily["route_count"] >= MAX_ROUTES
                or daily["reserved_micro"] + MAX_ROUTE_MICRO > MAX_TOTAL_MICRO
                or daily["charged_micro"] + daily["unresolved_micro"] + MAX_ROUTE_MICRO > MAX_TOTAL_MICRO
            ):
                self._block(occurrence, endpoint_id, "treg_budget_route_cap_reached")
            try:
                balance = _balance_micro(forward_tool("balance", {}))
            except Exception:
                self._block(occurrence, endpoint_id, "treg_budget_balance_readback_invalid")
            if balance - pending["unresolved_micro"] - MAX_ROUTE_MICRO < MIN_BALANCE_MICRO:
                self._block(occurrence, endpoint_id, "treg_budget_balance_floor_reached")

            reservation = {
                "reservation_id": uuid.uuid4().hex,
                "occurrence_id": self.occurrence_id,
                "endpoint_id": endpoint_id,
                "reserved_micro": MAX_ROUTE_MICRO,
                "status": "reserved",
                "created_at": _timestamp(),
            }
            daily["route_count"] += 1
            daily["reserved_micro"] += MAX_ROUTE_MICRO
            daily["unresolved_micro"] += MAX_ROUTE_MICRO
            daily["calls"].append(reservation.copy())
            occurrence["route_count"] += 1
            occurrence["reserved_micro"] += MAX_ROUTE_MICRO
            occurrence["unresolved_micro"] += MAX_ROUTE_MICRO
            occurrence["calls"].append(reservation.copy())
            pending["unresolved_micro"] += MAX_ROUTE_MICRO
            pending["calls"].append({
                "reservation_id": reservation["reservation_id"],
                "occurrence_id": self.occurrence_id,
                "reserved_micro": MAX_ROUTE_MICRO,
                "status": "unknown",
                "created_at": reservation["created_at"],
            })
            _write_json(daily_path, daily)
            _write_json(self.occurrence_ledger, occurrence)
            _write_json(self.pending_ledger, pending)

            try:
                result = forward_tool("call", arguments)
            except Exception:
                self._settle(daily_path, daily, occurrence, pending, reservation, None, halt_reason="treg_call_effect_unknown")
                raise GateRejected("treg_call_effect_unknown") from None
            receipt = _call_receipt(result)
            tool_error = _tool_result_error(result)
            self._settle(
                daily_path,
                daily,
                occurrence,
                pending,
                reservation,
                receipt,
                halt_reason="treg_call_receipt_invalid" if receipt is None else (
                    "treg_call_over_cap" if receipt[1] > MAX_ROUTE_MICRO else (
                        "treg_call_upstream_error" if tool_error else None
                    )
                ),
            )
            return result

    def _settle(
        self,
        daily_path: Path,
        daily: dict[str, Any],
        occurrence: dict[str, Any],
        pending: dict[str, Any],
        reservation: dict[str, Any],
        receipt: tuple[str, int] | None,
        *,
        halt_reason: str | None,
    ) -> None:
        for ledger in (daily, occurrence):
            row = next(
                item for item in reversed(ledger["calls"])
                if item.get("reservation_id") == reservation["reservation_id"]
                and item.get("status") == "reserved"
            )
            if receipt is None or receipt[1] > MAX_ROUTE_MICRO:
                row["status"] = "unknown" if receipt is None else "over_cap"
                if ledger is occurrence:
                    occurrence["halted"] = True
                    occurrence["halt_reason"] = halt_reason
                if receipt is not None:
                    row["call_id"], row["charged_micro"] = receipt
                    ledger["charged_micro"] += receipt[1]
                continue
            row["status"] = "provider_error" if halt_reason else "settled"
            row["call_id"], row["charged_micro"] = receipt
            ledger["charged_micro"] += receipt[1]
            ledger["unresolved_micro"] -= MAX_ROUTE_MICRO
            if ledger is occurrence and halt_reason:
                occurrence["halted"] = True
                occurrence["halt_reason"] = halt_reason
        if receipt is None:
            pending_row = next(
                item for item in pending["calls"]
                if item.get("reservation_id") == reservation["reservation_id"]
            )
            pending_row["status"] = "unknown"
        else:
            pending["calls"] = [
                item for item in pending["calls"]
                if item.get("reservation_id") != reservation["reservation_id"]
            ]
            pending["unresolved_micro"] -= MAX_ROUTE_MICRO
        _write_json(daily_path, daily)
        _write_json(self.occurrence_ledger, occurrence)
        _write_json(self.pending_ledger, pending)


class TregRemoteMCP:
    def __init__(self, token: str, *, url: str = TREG_MCP_URL) -> None:
        if not isinstance(token, str) or not token.strip():
            raise RemoteMCPError("treg_token_missing")
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token.strip()}",
            "Content-Type": "application/json",
        }
        self.opener = urllib.request.build_opener(_NoRedirect())
        self.url = url
        self.request_id = 0

    def close(self) -> None:
        pass

    def _send(self, message: dict[str, Any]) -> bytes:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=180.0) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RemoteMCPError("treg_mcp_upstream_unavailable") from None

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_id += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        try:
            value = json.loads(self._send(message).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RemoteMCPError("treg_mcp_upstream_response_invalid") from None
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise RemoteMCPError("treg_mcp_upstream_response_invalid")
        if "error" in value:
            raise RemoteMCPError("treg_mcp_upstream_request_failed")
        result = value.get("result")
        if not isinstance(result, dict):
            raise RemoteMCPError("treg_mcp_upstream_result_invalid")
        return result

    def initialize(self, protocol_version: str) -> dict[str, Any]:
        return self.request("initialize", {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "life-manager-treg-budget-gate", "version": "1"},
        })

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def list_tools(self) -> dict[str, Any]:
        result = self.request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RemoteMCPError("treg_mcp_tools_invalid")
        allowed = [tool for tool in tools if isinstance(tool, dict) and tool.get("name") in TREG_TOOLS]
        names = {tool["name"] for tool in allowed}
        if names != TREG_TOOLS:
            raise RemoteMCPError("treg_mcp_tools_incomplete")
        return {"tools": allowed}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def _tool_error(code: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"treg_budget_gate:{code}"}], "isError": True}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def run_stdio(remote: TregRemoteMCP, gate: TregBudgetGate) -> int:
    initialized = False
    tools: dict[str, Any] | None = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps(_rpc_error(None, -32700, "parse error")), flush=True)
            continue
        if not isinstance(request, dict):
            print(json.dumps(_rpc_error(None, -32600, "invalid request")), flush=True)
            continue
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        if not isinstance(method, str):
            if "id" in request:
                print(json.dumps(_rpc_error(request_id, -32600, "invalid request")), flush=True)
            continue
        if method.startswith("notifications/"):
            if method == "notifications/exit":
                return 0
            if initialized and method in {"notifications/initialized", "notifications/cancelled"}:
                try:
                    remote.notify(method)
                except RemoteMCPError:
                    if method == "notifications/initialized":
                        return 2
            continue
        try:
            if method == "initialize":
                protocol_version = params.get("protocolVersion")
                if not isinstance(protocol_version, str):
                    raise RemoteMCPError("mcp_protocol_version_missing")
                upstream = remote.initialize(protocol_version)
                negotiated = upstream.get("protocolVersion", protocol_version)
                result = {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "treg-budget-gate", "version": "1"},
                }
                initialized = True
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                if not initialized:
                    raise RemoteMCPError("mcp_not_initialized")
                tools = tools or remote.list_tools()
                result = tools
            elif method == "tools/call":
                if not initialized:
                    raise RemoteMCPError("mcp_not_initialized")
                name, arguments = params.get("name"), params.get("arguments", {})
                if name not in TREG_TOOLS or not isinstance(arguments, dict):
                    result = _tool_error("tool_not_allowed")
                elif name == "call":
                    try:
                        result = gate.call_paid(arguments, remote.call_tool)
                    except GateRejected as error:
                        result = _tool_error(error.code)
                else:
                    result = remote.call_tool(name, arguments)
                    if name == "catalog_get":
                        endpoint_id = arguments.get("endpoint_id")
                        if isinstance(endpoint_id, str) and endpoint_id:
                            gate.record_catalog_result(endpoint_id, result)
            elif method == "shutdown":
                result = {}
            else:
                if "id" in request:
                    print(json.dumps(_rpc_error(request_id, -32601, "method not found")), flush=True)
                continue
            print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False), flush=True)
        except RemoteMCPError as error:
            if method == "tools/call":
                response = {"jsonrpc": "2.0", "id": request_id, "result": _tool_error(str(error))}
            else:
                response = _rpc_error(request_id, -32603, str(error))
            print(json.dumps(response, ensure_ascii=False), flush=True)
        except Exception:
            print(json.dumps(_rpc_error(request_id, -32603, "treg_budget_gate_internal_error")), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-ledger", type=Path, required=True)
    parser.add_argument("--occurrence-ledger", type=Path, required=True)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--credentials-path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        token = load_treg_agent_token(args.credentials_path)
        if not token:
            raise RemoteMCPError("treg_token_missing")
        gate = TregBudgetGate(
            daily_ledger=args.daily_ledger,
            occurrence_ledger=args.occurrence_ledger,
            occurrence_id=args.occurrence_id,
        )
        remote = TregRemoteMCP(token)
    except (GateRejected, RemoteMCPError, ValueError):
        return 2
    try:
        return run_stdio(remote, gate)
    finally:
        remote.close()


if __name__ == "__main__":
    raise SystemExit(main())
