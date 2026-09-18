import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
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
    adoption_receipt=False,
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
        (queue / "card.md").write_text(f"topic_id: {card_topic}\n", encoding="utf-8")
    result = subprocess.run(
        ["python3", "-", str(run), str(tmp_path), run_id],
        input=PYTHON,
        text=True,
        capture_output=True,
        check=False,
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
