from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provider = _load(
    SCRIPTS / "providers" / "freelancer_platform_provider.py",
    "freelancer_platform_provider_test",
)


@dataclass(frozen=True)
class _Inventory:
    account_id: str = "94117802"
    source_complete: bool = True
    observed_at: str = "2026-09-30T05:00:00Z"


@dataclass(frozen=True)
class _Observation:
    inventory: _Inventory = _Inventory()
    evidence_sha256: dict[str, str] = None  # type: ignore[assignment]
    profile_sha256: str = "f" * 64

    def __post_init__(self):
        if self.evidence_sha256 is None:
            object.__setattr__(self, "evidence_sha256", {
                "identity": "a" * 64,
                "projects": "b" * 64,
                "payments": "c" * 64,
                "payouts": "d" * 64,
            })


class _Transport:
    account = "94117802"

    def __init__(self):
        self.calls = []

    def read_inventory_observation(self, receipts, **kwargs):
        self.calls.append((tuple(receipts), kwargs))
        return _Observation()


def test_authenticated_caller_projects_readback_into_shared_manifest(monkeypatch, tmp_path):
    transport = _Transport()
    calls = []

    def bridge(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "inspected": 1, "held": 1, "promoted": 0}

    monkeypatch.setattr(provider, "run_freelancer_platform_manifest_wake", bridge)
    result = provider.record_freelancer_platform_manifest_wake(
        transport=transport,
        receipts=("receipt-inspect", "receipt-payments", "receipt-payouts"),
        account_id="94117802",
        project_ids=("123",),
        fetch=lambda *_args: {"unused": True},
        run_id="freelancer-authenticated-manifest-test",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        currency_minor_units={"USD": 2},
    )

    assert result["status"] == "ok"
    assert len(calls) == 1
    assert transport.calls[0][0] == (
        "receipt-inspect", "receipt-payments", "receipt-payouts",
    )
    kwargs = transport.calls[0][1]
    assert kwargs["account_id"] == "94117802"
    assert kwargs["project_ids"] == ("123",)
    snapshot = calls[0]["snapshot"]
    assert snapshot["authenticated"] is True
    assert snapshot["source_complete"] is True
    assert snapshot["account_id_sha256"] != "freelancer-owner"
    assert "94117802" not in repr(snapshot)
    assert set(snapshot["inventory_evidence_sha256"]) == {
        "identity", "projects", "payments", "payouts",
    }


def test_authenticated_caller_rejects_account_mismatch_before_bridge(monkeypatch, tmp_path):
    transport = _Transport()
    transport.account = "other-account"
    monkeypatch.setattr(
        provider, "run_freelancer_platform_manifest_wake",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("bridge called")),
    )

    try:
        provider.record_freelancer_platform_manifest_wake(
            transport=transport,
            receipts=(), account_id="94117802", project_ids=(),
            fetch=lambda *_args: {}, run_id="mismatch",
            candidate_root=tmp_path / "candidates", run_root=tmp_path / "runs",
            currency_minor_units={"USD": 2},
        )
    except ValueError as error:
        assert str(error) == "freelancer_account_mismatch"
    else:
        raise AssertionError("account mismatch was accepted")
