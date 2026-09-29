"""Order 3: a failed revenue-set intent must become exactly one durable incident.

The fixture uses the persisted "active-four" contract label: three
revenue-set pairs and five dormant skip receipts (x-article/ja moved from
active/non-blocking-distribution to dormant 2026-09-29). The open
``resume-failure-circuit.json`` rows carry the observed publisher signatures.
"""

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
BRIDGE = ROOT / "scripts" / "writer_unavailable_incident_bridge.py"

NOTE_SIGNATURE = (
    'NoteNativePublishError: Note native publish HTTP 422: '
    '{"error":{"code":"invalid","message":"本文に利用できない内容が含まれています。"}}'
)
X_ARTICLE_SIGNATURE = (
    "XArticlePublishError: X Article publish HTTP 503 upstream unavailable"
)


def _load_bridge():
    spec = importlib.util.spec_from_file_location(
        "writer_unavailable_incident_bridge", BRIDGE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path: Path) -> Path:
    """Build a state root shaped like the current active-four run."""
    state_root = tmp_path / "state"
    run_dir = state_root / "runs" / "daily-2026-08-07"
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    (gates / "generation-state.json").write_text(
        json.dumps({"run_id": "daily-2026-08-07", "status": "complete"}),
        encoding="utf-8",
    )
    (gates / "quality-self-heal.json").write_text(
        json.dumps({"run_id": "daily-2026-08-07", "action": "ready_to_freeze"}),
        encoding="utf-8",
    )
    (gates / "publication-state.json").write_text(
        json.dumps({
            "version": 1,
            "publication_contract": "active-four",
            "run_id": "daily-2026-08-07",
            "run_dir": str(run_dir),
            "pairs": {
                "x-article/en": {
                    "platform": "x-article", "lang": "en", "status": "skipped",
                    "skip_receipt": {"type": "dormant-destination",
                                     "reason": "dormant-destination"},
                },
                "x-post/ja": {
                    "platform": "x-post", "lang": "ja", "status": "skipped",
                    "skip_receipt": {"type": "dormant-destination",
                                     "reason": "dormant-destination"},
                },
                "zenn-article/ja": {
                    "platform": "zenn-article", "lang": "ja", "status": "skipped",
                    "skip_receipt": {"type": "dormant-destination",
                                     "reason": "dormant-destination"},
                },
                "note/ja": {
                    "platform": "note", "lang": "ja", "status": "intent",
                    "target_kind": "note-key", "target": "n47735d9811e8",
                },
                "substack/ja": {
                    "platform": "substack", "lang": "ja", "status": "intent",
                    "target_kind": "substack-draft-id", "target": "210098888",
                },
                "substack/en": {
                    "platform": "substack", "lang": "en", "status": "intent",
                    "target_kind": "substack-draft-id", "target": "210098890",
                },
                "devto/en": {
                    "platform": "devto", "lang": "en", "status": "skipped",
                    "skip_receipt": {"type": "dormant-destination",
                                     "reason": "dormant-destination"},
                },
                "x-article/ja": {
                    "platform": "x-article", "lang": "ja", "status": "intent",
                    "target": "https://x.com/compose/articles/edit/2085407378015764614",
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (gates / "resume-failure-circuit.json").write_text(
        json.dumps({
            "version": 1,
            "pairs": {
                "note/ja": {
                    "state_sha256": "5f4eb592", "code_sha256": "64a6fcec",
                    "count": 2, "notified": True, "open": True,
                    "signature": NOTE_SIGNATURE,
                },
                "x-article/ja": {
                    "state_sha256": "5f4eb592", "code_sha256": "64a6fcec",
                    "count": 2, "notified": True, "open": True,
                    "signature": X_ARTICLE_SIGNATURE,
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return state_root


def _incidents(state_root: Path) -> dict:
    queue = json.loads(
        (state_root / "self-heal" / "incident-queue.json").read_text(encoding="utf-8")
    )
    return {
        item.get("destination"): item
        for item in queue["items"].values()
    }


def test_open_circuit_on_revenue_intent_becomes_one_keyed_incident(tmp_path: Path) -> None:
    module = _load_bridge()
    state_root = _fixture(tmp_path)

    result = module.bridge(
        state_root=state_root,
        run_id="daily-2026-08-07",
        observed_at="2026-08-07T14:10:00+09:00",
    )

    by_destination = _incidents(state_root)
    assert result["enqueued"] == 2, (
        "the open note/ja and x-article/ja circuits are the only observed "
        "destination "
        f"failures; got {result}"
    )
    assert set(by_destination) == {"note/ja", "x-article/ja"}

    note = by_destination["note/ja"]
    assert note["run_id"] == "daily-2026-08-07"
    assert note["artifact_id"] == "daily-2026-08-07__note__ja"
    assert note["destination"] == "note/ja"
    assert note["revenue_role"] == "revenue-set"
    assert note["blocking"] is True
    assert note["failure_class"]
    assert note["error_signature"] == NOTE_SIGNATURE
    assert note["state"] == "OPEN"
    assert note["next_action"] == "CLAIM"
    assert note["occurrence_count"] == 1
    assert note["occurrences"][0]["error_signature"] == NOTE_SIGNATURE


def test_incident_identity_is_run_artifact_destination_failure_class(tmp_path: Path) -> None:
    module = _load_bridge()
    state_root = _fixture(tmp_path)
    module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                  observed_at="2026-08-07T14:10:00+09:00")

    import hashlib
    note = _incidents(state_root)["note/ja"]
    expected = hashlib.sha256(json.dumps({
        "artifact_id": "daily-2026-08-07__note__ja",
        "destination": "note/ja",
        "failure_class": note["failure_class"],
        "run_id": "daily-2026-08-07",
        "scheme": "run+artifact+destination+failure_class",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert note["fingerprint"] == expected, (
        "incident identity must be run_id + artifact_id + destination + failure_class, "
        "and must not fold in the volatile error signature"
    )


def test_rerunning_the_bridge_reuses_the_same_incident(tmp_path: Path) -> None:
    module = _load_bridge()
    state_root = _fixture(tmp_path)

    first = module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                          observed_at="2026-08-07T14:10:00+09:00")
    before = _incidents(state_root)
    second = module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                           observed_at="2026-08-07T14:15:00+09:00")
    after = _incidents(state_root)

    assert first["enqueued"] == second["enqueued"] == 2
    assert set(before) == set(after)
    assert {row["fingerprint"] for row in before.values()} == {
        row["fingerprint"] for row in after.values()
    }
    for destination, item in after.items():
        assert item["occurrence_count"] == before[destination]["occurrence_count"] == 1, (
            f"{destination} duplicated its occurrence on an unchanged state tree"
        )
        assert item["first_seen_at"] == "2026-08-07T14:10:00+09:00"
        assert item["last_seen_at"] == "2026-08-07T14:15:00+09:00"


def test_dormant_pair_failure_is_recorded_but_distinguishable(
    tmp_path: Path,
) -> None:
    """x-article/ja moved from non-blocking-distribution to dormant (Dais
    2026-09-29: the X Articles editor is permanently unreachable for our
    account; X distribution now goes through Postiz link posts). A historical
    fixture that still carries an open circuit for it must classify as
    dormant, not blocking — a dormant pair was never a blocking one and
    still is not."""
    module = _load_bridge()
    state_root = _fixture(tmp_path)
    module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                  observed_at="2026-08-07T14:10:00+09:00")

    x_article = _incidents(state_root)["x-article/ja"]
    assert x_article["revenue_role"] == "dormant"
    assert x_article["blocking"] is False
    assert x_article["error_signature"] == X_ARTICLE_SIGNATURE
    assert x_article["artifact_id"] == "daily-2026-08-07__x-article__ja"


def test_incident_recorded_before_destination_identity_is_adopted_not_duplicated(
    tmp_path: Path,
) -> None:
    """The live queue already holds six pre-identity incidents; re-keying must
    adopt them in place rather than open a second incident beside each one."""
    module = _load_bridge()
    state_root = _fixture(tmp_path)

    # First pass under the new key, then rewrite that incident back to the old
    # phase/reason/source key with a claimed lease, as the live queue holds it.
    module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                  observed_at="2026-08-07T14:10:00+09:00")
    queue_path = state_root / "self-heal" / "incident-queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    note = next(row for row in queue["items"].values()
                if row["destination"] == "note/ja")
    incident_queue = importlib.util.spec_from_file_location(
        "writer_incident_queue", ROOT / "scripts" / "writer_incident_queue.py"
    )
    queue_module = importlib.util.module_from_spec(incident_queue)
    assert incident_queue.loader is not None
    incident_queue.loader.exec_module(queue_module)
    # The legacy key was built from the SLO work row, whose source_receipt the
    # incident only kept per occurrence.
    legacy_key = queue_module._legacy_fingerprint({
        "phase": note["phase"],
        "reason": note["reason"],
        "source_receipt": note["occurrences"][0]["source_receipt"],
    })
    legacy = {key: value for key, value in note.items()
              if key not in {"run_id", "artifact_id", "destination",
                             "revenue_role", "blocking", "failure_class"}}
    legacy["fingerprint"] = legacy_key
    legacy["state"] = "CLAIMED"
    legacy["lease_id"] = "production-repair-lease"
    legacy["attempt_count"] = 3
    queue["items"] = {legacy_key: legacy}
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                  observed_at="2026-08-07T14:20:00+09:00")

    after = json.loads(queue_path.read_text(encoding="utf-8"))["items"]
    assert len(after) == 2, (
        "the adopted note incident plus the rebuilt X Article incident, and no "
        f"duplicate beside the old key; got {sorted(after)}"
    )
    assert legacy_key not in after
    adopted = after[note["fingerprint"]]
    assert adopted["previous_fingerprint"] == legacy_key
    assert adopted["state"] == "CLAIMED"
    assert adopted["lease_id"] == "production-repair-lease"
    assert adopted["attempt_count"] == 3
    assert adopted["destination"] == "note/ja"
    assert adopted["artifact_id"] == "daily-2026-08-07__note__ja"


def test_dormant_skips_and_unfailed_pairs_never_become_incidents(tmp_path: Path) -> None:
    module = _load_bridge()
    state_root = _fixture(tmp_path)
    module.bridge(state_root=state_root, run_id="daily-2026-08-07",
                  observed_at="2026-08-07T14:10:00+09:00")

    destinations = set(_incidents(state_root))
    assert "x-article/en" not in destinations
    assert "x-post/ja" not in destinations
    assert "zenn-article/ja" not in destinations
    assert "devto/en" not in destinations
    assert "substack/ja" not in destinations, (
        "an intent with no observed failure evidence is still owned by the "
        "deterministic retry loop, not by the agent incident queue"
    )
    assert "substack/en" not in destinations
