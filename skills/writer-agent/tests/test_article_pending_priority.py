import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "article_pending.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("article_pending_priority", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
article_pending = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(article_pending)


def test_latest_active_six_run_precedes_old_legacy_backlog_after_midnight() -> None:
    now = datetime.fromisoformat("2026-08-07T00:30:00+09:00")
    states = [
        {
            "run_id": "daily-2026-07-24",
            "created_at": "2026-07-24T06:00:00+09:00",
            "publication_contract": "legacy-exact8",
        },
        {
            "run_id": "20260802-000152",
            "created_at": "2026-08-02T00:01:52+09:00",
            "publication_contract": "active-six",
        },
        {
            "run_id": "20260806-084924",
            "created_at": "2026-08-06T08:49:24+09:00",
            "publication_contract": "active-six",
        },
    ]

    ordered = sorted(states, key=lambda state: article_pending.run_priority(state, now))

    assert [state["run_id"] for state in ordered] == [
        "20260806-084924",
        "20260802-000152",
        "daily-2026-07-24",
    ]


def test_open_note_circuit_removes_recovery_and_allows_sibling(monkeypatch, tmp_path: Path) -> None:
    """A repeated note failure freezes only note; the same run can ship Substack."""
    import publication_resume

    state_root = tmp_path / "state"
    run_dir = state_root / "runs" / "daily-2026-08-21"
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    state_path = gates / "publication-state.json"
    state = {
        "run_id": "daily-2026-08-21",
        "created_at": "2026-08-21T06:00:00+09:00",
        "publication_contract": "active-four",
        "run_dir": str(run_dir),
        "state_path": str(state_path),
        "ledger_path": str(state_root / "articles.jsonl"),
        "topic_id": "topic-test",
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    code_file = tmp_path / "note-publisher.py"
    code_file.write_text("publisher-v1\n", encoding="utf-8")
    code_context = article_pending._current_circuit_context(
        state, "note/ja", [str(code_file)]
    )
    assert code_context is not None
    circuit = gates / "resume-failure-circuit.json"
    circuit.write_text(
        json.dumps(
            {
                "version": 1,
                "pairs": {
                    "note/ja": {
                        "open": True,
                        "state_sha256": code_context["state_sha256"],
                        "code_sha256": code_context["code_sha256"],
                        "code_files": [str(code_file)],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeStore:
        def __init__(self, *_args: object) -> None:
            pass

        def worker_plan(self) -> dict:
            return {
                "resumable": True,
                "run_id": state["run_id"],
                "run_dir": state["run_dir"],
                "topic_id": state["topic_id"],
                "pending_pairs": ["substack/ja"],
                "recovery_pairs": ["note/ja"],
                "initialization_pairs": [],
                "existing_pairs": {},
            }

        def initialization_plan(self) -> dict:
            return {"initializable": False}

        def read(self) -> dict:
            return state

    monkeypatch.setattr(publication_resume, "PublicationStore", FakeStore)
    result = article_pending.plan_oldest(
        state_root, datetime.fromisoformat("2026-08-21T07:00:00+09:00")
    )

    assert result["status"] == "READY"
    assert result["eligible_pairs"] == ["substack/ja"]
    assert result["recovery_pairs"] == []
    assert result["blocked_pairs"] == ["note/ja"]
    assert result["schedule"]["note/ja"]["reason"] == "same-failure-circuit-open"

    code_file.write_text("publisher-v2\n", encoding="utf-8")
    rearmed = article_pending.plan_oldest(
        state_root, datetime.fromisoformat("2026-08-21T07:00:00+09:00")
    )
    assert rearmed["status"] == "READY"
    assert "note/ja" in rearmed["eligible_pairs"]


def test_open_circuit_rechecks_current_release_content_without_path_only_rearm(monkeypatch, tmp_path: Path) -> None:
    import resume_failure_circuit

    old_code = tmp_path / 'old' / 'skills/writer-agent/scripts/publisher.py'
    current_scripts = tmp_path / 'current' / 'skills/writer-agent/scripts'
    old_code.parent.mkdir(parents=True)
    current_scripts.mkdir(parents=True)
    current_code = current_scripts / 'publisher.py'
    old_code.write_text('publisher-v1')
    current_code.write_text('publisher-v1')
    run_dir = tmp_path / 'run'
    (run_dir / 'gates').mkdir(parents=True)
    state_path = run_dir / 'gates/publication-state.json'
    state = {'run_dir': str(run_dir), 'state_path': str(state_path), 'pairs': {'substack/ja': {'target': '123', 'status': 'intent'}}}
    state_path.write_text(json.dumps(state))
    context = resume_failure_circuit.context(state_path, [old_code], 'substack/ja')
    circuit = run_dir / 'gates/resume-failure-circuit.json'
    circuit.write_text(json.dumps({'version': 1, 'pairs': {'substack/ja': {**context, 'open': True, 'code_files': [str(old_code)]}}}))
    saved_circuit = circuit.read_text()
    monkeypatch.setattr(article_pending, 'SCRIPT_DIR', current_scripts)
    # A new immutable path with identical code does not unfreeze a failure.
    assert article_pending._open_resume_circuit_pairs(state) == ({'substack/ja'}, False)
    current_code.write_text('publisher-v2')
    assert article_pending._open_resume_circuit_pairs(state) == (set(), False)
    old_code.unlink()
    assert article_pending._open_resume_circuit_pairs(state) == (set(), False)
    assert circuit.read_text() == saved_circuit
