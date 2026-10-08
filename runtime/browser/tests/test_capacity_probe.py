import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]


def test_capacity_probe_reads_registered_browser_without_launching_chromium(
        monkeypatch, capsys):
    import runtime.browser.capacity_probe as capacity_probe

    endpoint = "http://127.0.0.1:9222"
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if any("resolve_cdp_endpoint.py" in part for part in argv):
            assert argv[argv.index("--identity") + 1] == "interactive:dais"
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"identity": "interactive:dais", "endpoint": endpoint}),
                stderr="",
            )
        if any("cdp_context_lease.py" in part for part in argv) and argv[-1] == "audit":
            assert kwargs["env"]["CLOAK_CDP_BASE_URL"] == endpoint
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "ok": True,
                    "context_count": 3,
                    "leased_context_ids": ["private-context-id"],
                    "unknown_owner_contexts": [{"context_id": "unowned-context-id"}],
                }),
                stderr="",
            )
        raise AssertionError("unexpected subprocess")

    monkeypatch.setattr(capacity_probe.subprocess, "run", fake_run)
    result = capacity_probe.main()

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert result == 0
    assert payload == {
        "status": "ok",
        "reason": "cdp_ready",
        "effect": 0,
        "context_count": 3,
        "leased_context_count": 1,
        "unknown_owner_context_count": 1,
    }
    assert len(calls) == 2
    assert "private-context-id" not in output
    assert "unowned-context-id" not in output


def test_probe_rejects_non_loopback_endpoint_without_network():
    from runtime.browser.capacity_probe import run_probe

    result = run_probe(
        "http://example.com:9222",
        {
            "ok": True,
            "context_count": 0,
            "leased_context_ids": [],
            "unknown_owner_contexts": [],
        },
    )

    assert result == {
        "ok": False,
        "reason": "browser_endpoint_invalid",
        "effect": 0,
    }


def test_browser_capacity_probe_has_owned_registry_row():
    loops = json.loads((ROOT / "config/loop-registry.json").read_text())["loops"]
    row = loops["life-manager-browser-capacity-probe"]
    assert row["resource_class"] == "browser"
    assert row["effect_class"] == "none"
    assert row["provider_route"] == "deterministic"
    assert row["entrypoint"] == "runtime/browser/capacity_probe.py"
    assert row["cadence"] == {"start_interval_seconds": 300}
    assert row["state_root"] != loops["life-manager-connector-native"]["state_root"]
