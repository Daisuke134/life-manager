import importlib.util
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "treg_budget_mcp.py"
RUNNER_DIR = MODULE_PATH.parent
sys.path.insert(0, str(RUNNER_DIR))
import agent_runner  # noqa: E402


def load_gate_module(test: unittest.TestCase):
    if not MODULE_PATH.is_file():
        test.fail("local Treg pre-call budget gate is missing")
        return None
    spec = importlib.util.spec_from_file_location("treg_budget_mcp_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        test.fail("local Treg pre-call budget gate cannot be loaded")
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTreg:
    def __init__(self, balance_micro=1_000_000):
        self.balance_micro = balance_micro
        self.paid_calls = 0
        self.observed_reservations = []
        self.daily_ledger = None
        self.call_result_override = None

    def __call__(self, tool, arguments):
        if tool == "balance":
            return {"structuredContent": {"balance_micro": self.balance_micro}}
        if tool == "call":
            self.paid_calls += 1
            state = json.loads(self.daily_ledger.read_text(encoding="utf-8"))
            self.observed_reservations.append(state["route_count"])
            if self.call_result_override is not None:
                return self.call_result_override
            return {"structuredContent": {
                "call_id": f"test-call-{self.paid_calls}",
                "cost_usd": "0.003",
            }}
        raise AssertionError(f"unexpected fake Treg tool: {tool}")


class TregBudgetGateTests(unittest.TestCase):
    def setUp(self):
        self.gate_module = load_gate_module(self)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        self.daily_path = self.root / "daily.json"
        self.occurrence_path = self.root / "occurrence.json"
        self.fake = FakeTreg()
        self.fake.daily_ledger = self.daily_path
        self.gate = self.gate_module.TregBudgetGate(
            daily_ledger=self.daily_path,
            occurrence_ledger=self.occurrence_path,
            occurrence_id="treg-monitor:test-occurrence",
        )
        self.gate.record_quote("x.search", 3_000)

    @staticmethod
    def arguments():
        return {
            "endpoint_id": "x.search",
            "params": {"query": "public intent"},
            "headers": {"X-Treg-Route-Max-Cost": "0.003"},
        }

    def test_remote_mcp_auth_uses_bearer_header(self):
        remote = self.gate_module.TregRemoteMCP("test-token")
        try:
            headers = getattr(remote, "headers", None)
            self.assertIsInstance(headers, dict, "remote MCP transport must expose its explicit headers")
            if not isinstance(headers, dict):
                return
            self.assertEqual(headers.get("Authorization"), "Bearer test-token")
            self.assertNotIn("X-Treg-Token", headers)
        finally:
            remote.close()

    def test_balance_readback_treats_null_holds_as_zero(self):
        result = {"structuredContent": {"balance_micro": 53_000, "holds_micro": None}}

        self.assertEqual(self.gate_module._balance_micro(result), 53_000)

    def test_gate_loads_dedicated_token_from_private_ssot(self):
        loader = getattr(self.gate_module, "load_treg_agent_token", None)
        self.assertTrue(callable(loader), "Treg gate has no SSOT credential loader")
        if not callable(loader):
            return
        with tempfile.TemporaryDirectory() as temporary:
            credentials_path = Path(temporary) / "credentials.json"
            credentials_path.write_text(json.dumps({"credentials": [
                {"service": "other", "token": "ignore-me"},
                {"service": "treg_agent:life-manager-product-growth", "token": "test-token"},
            ]}), encoding="utf-8")
            credentials_path.chmod(0o600)

            self.assertEqual(loader(credentials_path), "test-token")

    def test_reservation_is_persisted_before_route_forward(self):
        self.gate.call_paid(self.arguments(), self.fake)

        self.assertEqual(self.fake.paid_calls, 1)
        self.assertEqual(self.fake.observed_reservations, [1])

    def test_nineteenth_route_is_rejected_before_paid_forward(self):
        for _ in range(18):
            self.gate.call_paid(self.arguments(), self.fake)

        with self.assertRaisesRegex(self.gate_module.GateRejected, "route_cap"):
            self.gate.call_paid(self.arguments(), self.fake)

        self.assertEqual(self.fake.paid_calls, 18)

    def test_daily_cap_is_shared_across_occurrences(self):
        for _ in range(18):
            self.gate.call_paid(self.arguments(), self.fake)

        other = self.gate_module.TregBudgetGate(
            daily_ledger=self.daily_path,
            occurrence_ledger=self.root / "other-occurrence.json",
            occurrence_id="treg-monitor:other-occurrence",
        )
        other.record_quote("x.search", 3_000)
        other_fake = FakeTreg()
        other_fake.daily_ledger = self.daily_path
        with self.assertRaisesRegex(self.gate_module.GateRejected, "route_cap"):
            other.call_paid(self.arguments(), other_fake)

        self.assertEqual(other_fake.paid_calls, 0)

    def test_low_balance_or_unresolved_reservation_blocks_before_paid_forward(self):
        self.fake.balance_micro = 52_999

        with self.assertRaisesRegex(self.gate_module.GateRejected, "balance_floor"):
            self.gate.call_paid(self.arguments(), self.fake)

        self.assertEqual(self.fake.paid_calls, 0)

    def test_missing_receipt_keeps_reservation_and_halts_occurrence(self):
        self.fake.balance_micro = 1_000_000
        self.fake.call_result_override = {"isError": True, "content": [{"type": "text", "text": "timeout"}]}

        self.gate.call_paid(self.arguments(), self.fake)
        state = json.loads(self.daily_path.read_text(encoding="utf-8"))
        occurrence = json.loads(self.occurrence_path.read_text(encoding="utf-8"))
        self.assertEqual(state["unresolved_micro"], 3_000)
        self.assertEqual(state["calls"][0]["status"], "unknown")
        self.assertTrue(occurrence["halted"])

        with self.assertRaisesRegex(self.gate_module.GateRejected, "previous_call_uncertain"):
            self.gate.call_paid(self.arguments(), self.fake)

        self.assertEqual(self.fake.paid_calls, 1)

    def test_unresolved_reservation_carries_across_daily_ledger_rotation(self):
        self.fake.balance_micro = 54_000
        self.fake.call_result_override = {"isError": True, "content": [{"type": "text", "text": "timeout"}]}
        self.gate.call_paid(self.arguments(), self.fake)

        next_day = self.gate_module.TregBudgetGate(
            daily_ledger=self.root / "next-day.json",
            occurrence_ledger=self.root / "next-occurrence.json",
            occurrence_id="treg-monitor:next-day",
        )
        next_day.record_quote("x.search", 3_000)
        next_fake = FakeTreg(balance_micro=54_000)
        next_fake.daily_ledger = self.root / "next-day.json"

        with self.assertRaisesRegex(self.gate_module.GateRejected, "balance_floor"):
            next_day.call_paid(self.arguments(), next_fake)

        self.assertEqual(next_fake.paid_calls, 0)

    def test_occurrence_route_cap_survives_daily_ledger_rotation(self):
        for _ in range(18):
            self.gate.call_paid(self.arguments(), self.fake)

        next_day = self.gate_module.TregBudgetGate(
            daily_ledger=self.root / "next-day.json",
            occurrence_ledger=self.occurrence_path,
            occurrence_id="treg-monitor:test-occurrence",
        )
        next_day.record_quote("x.search", 3_000)
        next_fake = FakeTreg()
        next_fake.daily_ledger = self.root / "next-day.json"

        with self.assertRaisesRegex(self.gate_module.GateRejected, "route_cap"):
            next_day.call_paid(self.arguments(), next_fake)

        self.assertEqual(next_fake.paid_calls, 0)

    def test_unsafe_quote_and_missing_header_block_before_paid_forward(self):
        self.gate.record_quote("x.search", 3_001)
        with self.assertRaisesRegex(self.gate_module.GateRejected, "quote_invalid"):
            self.gate.call_paid(self.arguments(), self.fake)

        self.gate.record_quote("x.search", 3_000)
        arguments = self.arguments()
        arguments["headers"] = {}
        with self.assertRaisesRegex(self.gate_module.GateRejected, "route_cap_header"):
            self.gate.call_paid(arguments, self.fake)

        self.assertEqual(self.fake.paid_calls, 0)


class TregMCPCommandTests(unittest.TestCase):
    def test_general_codex_task_uses_local_gate_without_token_environment_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            evidence.chmod(0o700)
            result_path = evidence / "result.json"
            args = argparse.Namespace(
                task_class="diagnostic-agent",
                evidence_dir=evidence,
                workdir=evidence,
                image=[],
            )
            candidate = {"model": "gpt-6.1-sol", "effort": "medium"}
            budget_root = Path.home() / ".local" / "state" / "life-manager" / "treg-budget"
            with patch.object(agent_runner, "_load_treg_agent_token", return_value="limited-test-token"):
                with patch.dict(os.environ, {"LIFE_MANAGER_OCCURRENCE_ID": "agent:command-test"}):
                    command = agent_runner.command_for(
                        "codex", "/fake/codex", {}, candidate, args, "bounded prompt", {}, result_path
                    )

        overrides = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-c"]
        self.assertTrue(any(value.startswith("mcp_servers.treg.command=") for value in overrides))
        self.assertTrue(any("mcp_servers.treg.args=" in value and "--daily-ledger" in value for value in overrides))
        self.assertTrue(any("--credentials-path" in value for value in overrides))
        self.assertTrue(any(str(budget_root) in value for value in overrides))
        self.assertFalse(any("TREG_TOKEN" in value for value in overrides))
        self.assertFalse(any("mcp_servers.treg.url=" in value for value in overrides))
        self.assertFalse(any("env_http_headers" in value for value in overrides))

    def test_signal_monitor_requires_gated_mcp_and_keeps_shell_disabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            evidence.chmod(0o700)
            args = argparse.Namespace(
                task_class=agent_runner.TREG_SIGNAL_TASK_CLASS,
                evidence_dir=evidence,
                workdir=evidence,
                image=[],
            )
            candidate = {"model": "gpt-6.1-sol", "effort": "medium"}
            with patch.dict(os.environ, {"LIFE_MANAGER_OCCURRENCE_ID": "treg-monitor:test-occurrence"}):
                command = agent_runner.command_for(
                    "codex", "/fake/codex", {}, candidate, args, "bounded prompt", {}, evidence / "result.json"
                )

        overrides = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-c"]
        self.assertTrue(any('mcp_servers.treg.required=true' in value for value in overrides))
        self.assertTrue(any('mcp_servers.treg.default_tools_approval_mode="approve"' in value for value in overrides))
        self.assertTrue(any(value == "shell_tool" for value in command))
        self.assertFalse(any("TREG_TOKEN" in value for value in overrides))

    def test_provider_environment_keeps_token_out_of_general_tasks(self):
        with patch.object(agent_runner, "_load_treg_agent_token", return_value="limited-test-token"):
            with patch.object(agent_runner, "_load_clipproxy_api_key"):
                env = agent_runner.provider_process_env(
                    "codex",
                    {},
                    environ={"PATH": "/usr/bin:/bin", "TREG_TOKEN": "inherited-test-token"},
                    task_class="diagnostic-agent",
                )

        self.assertNotIn("TREG_TOKEN", env)
        self.assertNotIn("LIFE_MANAGER_TREG_ENABLED", env)

    def test_stdio_handshake_lists_only_allowed_tools_and_forwards_free_balance(self):
        gate_module = load_gate_module(self)
        if gate_module is None:
            return

        class FakeRemote:
            def __init__(self):
                self.notifications = []
                self.calls = []

            def initialize(self, protocol_version):
                return {"protocolVersion": protocol_version}

            def notify(self, method):
                self.notifications.append(method)

            def list_tools(self):
                names = ("catalog_search", "catalog_get", "call", "balance")
                return {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in names]}

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return {"structuredContent": {"balance_micro": 1_000_000}}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            gate = gate_module.TregBudgetGate(
                daily_ledger=root / "daily.json",
                occurrence_ledger=root / "occurrence.json",
                occurrence_id="treg-monitor:stdio-test",
            )
            remote = FakeRemote()
            inputs = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "balance", "arguments": {}}},
            ]
            with patch("sys.stdin", io.StringIO("\n".join(json.dumps(row) for row in inputs) + "\n")):
                with patch("sys.stdout", io.StringIO()) as output:
                    status = gate_module.run_stdio(remote, gate)
                    responses = [json.loads(line) for line in output.getvalue().splitlines()]

        self.assertEqual(status, 0)
        self.assertEqual(remote.notifications, ["notifications/initialized"])
        self.assertEqual([call[0] for call in remote.calls], ["balance"])
        self.assertEqual([tool["name"] for tool in responses[1]["result"]["tools"]], [
            "catalog_search", "catalog_get", "call", "balance",
        ])
        self.assertEqual(responses[2]["result"]["structuredContent"]["balance_micro"], 1_000_000)

if __name__ == "__main__":
    unittest.main()
