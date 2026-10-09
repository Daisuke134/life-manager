import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/writer-agent/scripts"))
import article_daily_start_control as START
import article_generation_state as GENERATION

SCRIPT = ROOT / "skills/writer-agent/article-daily.sh"
SOURCE = SCRIPT.read_text(encoding="utf-8")
MARKER = 'python3 - "$RUN_DIR" "$STATE_DIR" "$RUN_TS" >>"$LOG" <<\'PYEOF\'\n'
PYTHON = SOURCE.split(MARKER, 1)[1].split("\nPYEOF", 1)[0]


def run_resume(
    tmp_path: Path,
    route: dict | None,
    card_topic: str | None,
    *,
    empty=True,
    ledger_text="",
    ledger_symlink=False,
    generation_symlink=False,
    route_symlink=False,
    generation_status="interrupted-safe",
    generation_return_code=0,
    generation_state=True,
    uninitialized_pre_topic=False,
    uninitialized_marker=None,
    adoption_receipt=False,
    topic_card_receipt=True,
    card_stage="queue",
):
    run_id = "20260821-054500"
    run = tmp_path / "runs" / run_id
    gates = run / "gates"
    queue = tmp_path / "topics" / "queue"
    in_progress = tmp_path / "topics" / "in-progress"
    gates.mkdir(parents=True)
    queue.mkdir(parents=True)
    in_progress.mkdir(parents=True)
    ledger = tmp_path / "articles.jsonl"
    ledger.write_text(ledger_text, encoding="utf-8")
    if ledger_symlink:
        target = tmp_path / "ledger-target.jsonl"
        target.write_text(ledger_text, encoding="utf-8")
        ledger.unlink()
        ledger.symlink_to(target)
    generation = gates / "generation-state.json"
    if generation_state:
        attempt = {"status": generation_status}
        if generation_status == "provider-returned":
            attempt.update({
                "return_code": generation_return_code,
                "boundary": "prepublication-empty",
            })
        else:
            attempt.update({
                "boundary": "archived-prepublication-artifacts",
                "archive_manifest": [] if empty else [{"path": "article-ja.md"}],
            })
        generation.write_text(
            json.dumps({
                "version": 1,
                "run_id": run_id,
                "status": generation_status,
                "attempts": [attempt],
            }),
            encoding="utf-8",
        )
    if uninitialized_pre_topic:
        (run / "article-daily-prompt.txt").write_text(
            f"Use {tmp_path}/loops/releases/old/skills/writer-agent/scripts/run.sh\n",
            encoding="utf-8",
        )
        (run / "git-hash.txt").write_text("harness_git_hash=test\n", encoding="utf-8")
        (gates / "product-selection.json").write_text('{"product_id":"anicca"}\n', encoding="utf-8")
        (gates / "strategy-consumption.json").write_text(
            json.dumps({"run_id": run_id, "status": "baseline", "versions": []}) + "\n",
            encoding="utf-8",
        )
        (gates / ".generation-state.json.lock").touch()
        broker = gates / "judge-broker"
        broker.mkdir()
        (broker / "heartbeat").touch()
        for name in ("requests", "responses", "done"):
            (broker / name).mkdir()
        (gates / "topic-card-resume.json").write_text(
            json.dumps({
                "version": 1,
                "run_id": run_id,
                "action": "blocked",
                "reason": "generation-state-missing-or-symlink",
            }) + "\n",
            encoding="utf-8",
        )
    if uninitialized_marker:
        marker = run / uninitialized_marker
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("dispatch marker\n", encoding="utf-8")
    if adoption_receipt:
        (gates / "prepublication-adoption.json").write_text(
            json.dumps({
                "schema": "writer.prepublication-adoption",
                "version": 1,
                "run_id": run_id,
                "to_status": "quality-repair-ready",
            }),
            encoding="utf-8",
        )
        if topic_card_receipt:
            (gates / "topic-card-resume.json").write_text(
                json.dumps({"action": "existing", "run_id": run_id}),
                encoding="utf-8",
            )
    if generation_symlink:
        target = tmp_path / "generation-target.json"
        target.write_text(generation.read_text(encoding="utf-8"), encoding="utf-8")
        generation.unlink()
        generation.symlink_to(target)
    if route is not None:
        route_path = gates / "topic-route-input.json"
        route_path.write_text(json.dumps(route), encoding="utf-8")
        if route_symlink:
            target = tmp_path / "route-target.json"
            target.write_text(route_path.read_text(encoding="utf-8"), encoding="utf-8")
            route_path.unlink()
            route_path.symlink_to(target)
    if card_topic is not None:
        card_dir = queue if card_stage == "queue" else in_progress
        (card_dir / "card.md").write_text(f"topic_id: {card_topic}\n", encoding="utf-8")
    result = subprocess.run(
        ["python3", "-", str(run), str(tmp_path), run_id],
        input=PYTHON,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "ARTICLE_ROOT": str(ROOT / "skills/writer-agent")},
    )
    receipt = json.loads(
        (gates / "topic-card-resume.json").read_text(encoding="utf-8")
    )
    return result, receipt


def test_empty_pre_topic_interruption_skips_card_recovery(tmp_path):
    result, receipt = run_resume(
        tmp_path, route=None, card_topic="paid-demand:unused"
    )
    assert result.returncode == 0
    assert receipt["action"] == "skip-pre-topic-recovery"
    assert receipt["reason"] == "empty-pre-topic-interruption"


def test_empty_provider_return_skips_card_recovery(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic="paid-demand:unused",
        generation_status="provider-returned",
    )
    assert result.returncode == 0
    assert receipt["action"] == "skip-pre-topic-recovery"
    assert receipt["reason"] == "empty-pre-topic-interruption"


def test_false_provider_return_code_does_not_skip_card_recovery(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic="paid-demand:unused",
        generation_status="provider-returned",
        generation_return_code=False,
    )
    assert result.returncode != 0
    assert receipt["reason"] == "topic-route-input-missing"


def test_uninitialized_pre_topic_run_skips_card_recovery_and_rebinds_same_prompt(tmp_path):
    run_id = "20260821-054500"
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic="paid-demand:unused",
        generation_state=False,
        uninitialized_pre_topic=True,
    )
    assert result.returncode == 0, result.stderr
    assert receipt["action"] == "skip-pre-topic-recovery"
    assert receipt["reason"] == "uninitialized-pre-topic-empty"

    run = tmp_path / "runs" / run_id
    current_root = tmp_path / "loops/releases/current/skills/writer-agent"
    current_root.mkdir(parents=True)
    rebound = GENERATION.rebind_release(
        run,
        run_id,
        run / "article-daily-prompt.txt",
        tmp_path / "articles.jsonl",
        current_root,
    )
    assert rebound["action"] == "rebound"
    state = json.loads((run / "gates/generation-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "prepared"
    assert state["attempts"] == []
    assert str(current_root) in (run / "article-daily-prompt.txt").read_text(encoding="utf-8")
    decision = START.decide(tmp_path, "2026-08-21")
    assert decision["action"] == "resume-generation"
    assert decision["run_id"] == run_id


def test_uninitialized_pre_topic_run_with_dispatch_marker_stays_blocked(tmp_path):
    for name, route, marker, ledger_text, reason in (
        (
            "route",
            {"topic_id": "paid-demand:unused"},
            None,
            "",
            "generation-state-missing-with-topic-route",
        ),
        ("model", None, "gates/model-stdout.log", "", "uninitialized-pre-topic-dispatch-marker"),
        ("model-root", None, "model-stdout.log", "", "uninitialized-pre-topic-dispatch-marker"),
        (
            "broker",
            None,
            "gates/judge-broker/requests/request.json",
            "",
            "uninitialized-pre-topic-judge-broker-dispatch-marker",
        ),
        ("ledger", None, None, "{malformed\\n", "uninitialized-pre-topic-unreadable"),
    ):
        result, receipt = run_resume(
            tmp_path / name,
            route=route,
            card_topic="paid-demand:unused",
            generation_state=False,
            uninitialized_pre_topic=True,
            uninitialized_marker=marker,
            ledger_text=ledger_text,
        )
        assert result.returncode != 0
        assert receipt["action"] == "blocked"
        assert receipt["reason"] == reason


def test_adopted_prepublication_does_not_rewrite_topic_card_receipt(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:unused"},
        card_topic="paid-demand:unused",
        generation_status="quality-repair-ready",
        adoption_receipt=True,
    )
    assert result.returncode == 0
    assert receipt == {"action": "existing", "run_id": "20260821-054500"}


def test_adopted_prepublication_creates_allowlisted_skip_receipt_when_missing(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:unused"},
        card_topic="paid-demand:unused",
        generation_status="quality-repair-ready",
        adoption_receipt=True,
        topic_card_receipt=False,
    )
    assert result.returncode == 0
    assert receipt["action"] == "skip-adopted-prepublication"
    assert receipt["reason"] == "quality-repair-ready-adoption"


def test_adopted_route_malformed_ledger_fails_before_card_move(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:abc",
        card_stage="in_progress",
        adoption_receipt=True,
        ledger_text="{malformed\n",
    )
    assert result.returncode != 0
    assert receipt["reason"] == "ledger-invalid"
    assert (tmp_path / "topics/in-progress/card.md").is_file()
    assert not (tmp_path / "topics/queue/card.md").exists()


def test_adopted_route_ledger_symlink_fails_before_card_move(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:abc",
        card_stage="in_progress",
        adoption_receipt=True,
        ledger_symlink=True,
    )
    assert result.returncode != 0
    assert receipt["reason"] == "ledger-missing-or-symlink"
    assert (tmp_path / "topics/in-progress/card.md").is_file()
    assert not (tmp_path / "topics/queue/card.md").exists()


def test_adopted_route_public_ledger_row_fails_before_card_move(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:abc",
        card_stage="in_progress",
        adoption_receipt=True,
        ledger_text=json.dumps({"run_id": "20260821-054500", "published": True}) + "\n",
    )
    assert result.returncode != 0
    assert receipt["reason"] == "public-ledger-effect"
    assert (tmp_path / "topics/in-progress/card.md").is_file()
    assert not (tmp_path / "topics/queue/card.md").exists()


def test_existing_route_restores_exact_matching_card(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:abc",
    )
    assert result.returncode == 0
    assert receipt["action"] == "already-queued"
    assert receipt["topic_id"] == "paid-demand:abc"


def test_existing_route_card_mismatch_fails_closed(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:def",
    )
    assert result.returncode != 0
    assert receipt["action"] == "blocked"
    assert receipt["reason"] == "matching-card-not-found"


def test_public_ledger_row_blocks_empty_skip(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic=None,
        ledger_text=json.dumps({"run_id": "20260821-054500", "published": True}) + "\n",
    )
    assert result.returncode != 0
    assert receipt["reason"] == "topic-route-input-missing"


def test_malformed_ledger_after_public_row_blocks_empty_skip(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic=None,
        ledger_text=(
            json.dumps({"run_id": "20260821-054500", "published": True})
            + "\n{malformed\n"
        ),
    )
    assert result.returncode != 0
    assert receipt["reason"] == "ledger-invalid"


def test_ledger_symlink_blocks_empty_skip(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route=None,
        card_topic=None,
        ledger_symlink=True,
        ledger_text=json.dumps({"run_id": "20260821-054500", "published": True}) + "\n",
    )
    assert result.returncode != 0
    assert receipt["reason"] == "ledger-missing-or-symlink"


def test_malformed_ledger_blocks_empty_skip(tmp_path):
    result, receipt = run_resume(
        tmp_path, route=None, card_topic=None, ledger_text="{malformed\n"
    )
    assert result.returncode != 0
    assert receipt["reason"] == "ledger-invalid"


def test_generation_state_symlink_blocks_empty_skip(tmp_path):
    result, receipt = run_resume(
        tmp_path, route=None, card_topic=None, generation_symlink=True
    )
    assert result.returncode != 0
    assert receipt["reason"] == "generation-state-missing-or-symlink"


def test_route_input_symlink_blocks_resume(tmp_path):
    result, receipt = run_resume(
        tmp_path,
        route={"topic_id": "paid-demand:abc"},
        card_topic="paid-demand:abc",
        route_symlink=True,
    )
    assert result.returncode != 0
    assert receipt["reason"] == "topic-route-input-symlink"
