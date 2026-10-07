from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_history_retention_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def test_context_read_receipt_aggregates_many_refs_and_trajectory_reads(tmp_path, monkeypatch):
    compiler = load("project_context_compiler")
    root = tmp_path / "project"
    write_json(root / "state.json", {"request_id": "req-1", "talkroom_id": "room-1"})
    live = tmp_path / "live-talkroom.json"
    live.write_bytes(b"exact live talkroom capture")

    for resource, directory in (
        ("posting", "source/posting"),
        ("dm", "source/dm"),
        ("talkroom", "source/talkroom"),
        ("project", "delivery"),
    ):
        for index in range(75):
            path = root / directory / f"ref-{index:03d}.json"
            write_json(path, {"resource": resource, "index": index})

    queue = {
        "request_id": "req-1",
        "talkroom_id": "room-1",
        "talkroom_evidence_file": str(live),
        "talkroom_observed_at": "2026-08-26T00:00:00+00:00",
    }
    compiled = compiler.compile_context(root, queue)
    receipt = compiler.append_context_read_receipt(root, compiled, queue)
    events: list[dict] = []
    monkeypatch.setattr(compiler, "record_trajectory", lambda **event: events.append(event))
    compiler.record_source_reads(compiled, receipt)

    assert len(compiled["source_refs"]) >= 300
    assert receipt["source_count"] == len(compiled["source_refs"])
    assert [row["resource_key"] for row in receipt["sources_read"]] == [
        "dm:req-1", "posting:req-1", "project:req-1", "talkroom:room-1",
    ]
    assert all(row["source_count"] > 1 for row in receipt["sources_read"])
    assert len(receipt["sources_read"]) == 4
    assert receipt["live_talkroom"]["path"] == str(live.resolve())
    assert receipt["live_talkroom"]["sha256"] == hashlib.sha256(live.read_bytes()).hexdigest()
    assert len(events) == 4
    assert {event["resource_key"] for event in events} == {
        "posting:req-1", "dm:req-1", "talkroom:room-1", "project:req-1",
    }
    assert all(len(event["artifact_sha256"]) == 64 for event in events)

    repeat = compiler.append_context_read_receipt(root, compiled, queue)
    assert repeat["receipt_sha256"] == receipt["receipt_sha256"]


def test_refs_skip_external_venv_python_symlinks_without_dropping_internal_sources(tmp_path, monkeypatch):
    compiler = load("project_context_compiler")
    root = tmp_path / "project"
    root.mkdir()
    write_json(root / "state.json", {"request_id": "req-1", "talkroom_id": "room-1"})
    internal = root / "delivery" / "source.json"
    write_json(internal, {"source": "inside project"})
    internal_link = root / "delivery" / "internal-link.json"
    internal_link.symlink_to(internal)
    external = tmp_path / "system" / "python3.14"
    external.parent.mkdir()
    external.write_bytes(b"runtime executable")
    external.chmod(0o755)
    external_link = root / "delivery" / "runtime" / "owner" / ".venv" / "bin" / "python3.14"
    external_link.parent.mkdir(parents=True)
    external_link.symlink_to(external)

    bytes_sha = compiler._bytes_sha

    def assert_project_local_before_read(path):
        assert path.resolve().is_relative_to(root.resolve())
        return bytes_sha(path)

    monkeypatch.setattr(compiler, "_bytes_sha", assert_project_local_before_read)
    refs = compiler._refs(root)
    paths = {row["path"] for row in refs}

    assert "state.json" in paths
    assert "delivery/source.json" in paths
    assert "delivery/internal-link.json" in paths
    assert "delivery/runtime/owner/.venv/bin/python3.14" not in paths


def test_refs_fail_closed_on_external_customer_source_symlink(tmp_path, monkeypatch):
    compiler = load("project_context_compiler")
    root = tmp_path / "project"
    root.mkdir()
    write_json(root / "state.json", {"request_id": "req-1", "talkroom_id": "room-1"})
    external = tmp_path / "private" / "live-buyer-reply.json"
    write_json(external, {"buyer_reply": "must not be silently omitted"})
    (root / "requirements").mkdir()
    (root / "requirements" / "live-buyer-reply.json").symlink_to(external)

    bytes_sha = compiler._bytes_sha

    def assert_project_local_before_read(path):
        assert path.resolve().is_relative_to(root.resolve())
        return bytes_sha(path)

    monkeypatch.setattr(compiler, "_bytes_sha", assert_project_local_before_read)
    with pytest.raises(ValueError, match="source reference escapes project"):
        compiler._refs(root)


def test_paid_context_snapshot_rejects_external_read_first_path(tmp_path):
    paid = load("paid_direct")
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "private" / "buyer-reply.json"
    write_json(outside, {"buyer_reply": "must stay outside project"})
    context = root / "current.json"
    write_json(context, {
        "source_refs": [],
        "combined_context": {"read_these_first": ["../private/buyer-reply.json"]},
    })

    with pytest.raises(ValueError, match="compiled read path escapes project"):
        paid._context_input_snapshot(root, context)


@pytest.mark.parametrize("marker", [
    "delivery/paid-tool-requests.json",
    "context/paid-tool-results.json",
])
def test_failed_project_workspace_is_removed_unless_resume_marker_exists(tmp_path, marker):
    paid = load("paid_direct")
    root = tmp_path / "projects" / "room-1"
    root.mkdir(parents=True)

    with pytest.raises(RuntimeError):
        with paid._project_workspace(root, "owner-") as workspace:
            Path(workspace, "failed.txt").write_text("discard", encoding="utf-8")
            raise RuntimeError("worker failed")
    runtime = root.parent.parent / "runtime" / root.name
    assert not list(runtime.glob("owner-*"))

    with pytest.raises(RuntimeError):
        with paid._project_workspace(root, "owner-") as workspace:
            marker_path = Path(workspace) / marker
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            if marker.endswith("requests.json"):
                write_json(marker_path, {"version": 1, "requests": [{"capability": "pending"}]})
            else:
                write_json(marker_path, {"version": 1, "status": "failed", "results": []})
            raise RuntimeError("worker failed")
    retained = list(runtime.glob("owner-*"))
    assert len(retained) == 1
    assert (retained[0] / marker).is_file()
