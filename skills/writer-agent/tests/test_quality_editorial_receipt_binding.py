import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/writer-agent/scripts/quality_self_heal.py"
spec = importlib.util.spec_from_file_location("quality_receipt_binding", SCRIPT)
assert spec and spec.loader
QUALITY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QUALITY)


def test_rebinds_unbound_editorial_recheck_to_current_draft(tmp_path):
    run = tmp_path / "run"
    gates = run / "gates"
    gates.mkdir(parents=True)
    draft = run / "article-en.md"
    draft.write_text("# draft\n", encoding="utf-8")
    raw = {
        "verdict": "FAIL",
        "fixes": ["add evidence"],
        "strengths": ["clear reader job"],
    }
    (gates / "editorial-en.json").write_text(
        json.dumps(raw), encoding="utf-8"
    )

    repaired = QUALITY._repair_unbound_editorial_receipt(run, "en", draft)

    digest = hashlib.sha256(draft.read_bytes()).hexdigest()
    assert repaired["article_sha256"] == digest
    assert repaired["verdict"] == "FAIL"
    assert repaired["receipt_rebound_from_unbound"] is True
    canonical = json.loads((gates / "editorial-en.json").read_text())
    assert canonical == repaired
    archive = list((gates / "editorial-unbound").glob("editorial-en-*.json"))
    assert len(archive) == 1
    assert json.loads(archive[0].read_text()) == raw


def test_normalizes_existing_force_receipt_to_continuous_policy(tmp_path):
    run = tmp_path / "run"
    gates = run / "gates"
    gates.mkdir(parents=True)
    (gates / "topic-route.json").write_text(
        json.dumps({"editorial_form": "explainer"}), encoding="utf-8"
    )
    drafts = {}
    quality = {}
    snapshots = {}
    for lang in ("ja", "en"):
        draft = run / f"article-{lang}.md"
        draft.write_text(f"# {lang}\n", encoding="utf-8")
        drafts[lang] = draft
        digest = hashlib.sha256(draft.read_bytes()).hexdigest()
        editorial = {"verdict": "FAIL", "article_sha256": digest, "fixes": []}
        reader = {
            "status": "pass", "exit_code": 0, "article_sha256": digest,
            "payload": {"verdict": "PASS"},
        }
        identity = {"verdict": "PASS", "article_sha256": digest}
        (gates / f"editorial-{lang}.json").write_text(json.dumps(editorial), encoding="utf-8")
        (gates / f"reader-testing-gate-{lang}.terminal.json").write_text(json.dumps(reader), encoding="utf-8")
        (gates / f"identity-{lang}.json").write_text(json.dumps(identity), encoding="utf-8")
        snapshot = gates / "quality-attempt-1"
        snapshot.mkdir(exist_ok=True)
        for name, value in ((f"editorial-{lang}.json", editorial),
                            (f"reader-testing-gate-{lang}.terminal.json", reader),
                            (f"identity-{lang}.json", identity)):
            (snapshot / name).write_text(json.dumps(value), encoding="utf-8")
        quality[lang] = {
            "lang": lang, "article_sha256": digest, "editorial": "FAIL",
            "identity": "PASS", "reader": "PASS",
        }
        snapshots[lang] = {
            "editorial": hashlib.sha256((snapshot / f"editorial-{lang}.json").read_bytes()).hexdigest(),
            "reader": hashlib.sha256((snapshot / f"reader-testing-gate-{lang}.terminal.json").read_bytes()).hexdigest(),
            "identity": hashlib.sha256((snapshot / f"identity-{lang}.json").read_bytes()).hexdigest(),
        }
    decision = {
        "version": 2, "run_id": run.name, "attempt": 1,
        "action": "force_publish_advisory", "fingerprint": "f" * 64,
        "quality": quality, "receipt_snapshots": snapshots,
        "publication_policy": "strict", "force_publish_after_iterations": 1,
        "quality_advisory": True,
    }
    decision["receipt_sha256"] = QUALITY._receipt_hash(decision)
    (gates / "quality-self-heal-attempt-1.json").write_text(json.dumps(decision), encoding="utf-8")
    (gates / "quality-self-heal.json").write_text(json.dumps(decision), encoding="utf-8")
    (gates / "quality-self-heal-blocker.json").write_text(
        json.dumps({"reason": "quality receipt snapshot hash binding failed"}), encoding="utf-8"
    )

    normalized = QUALITY.repair_unbound_force_receipt(run, drafts)

    assert normalized["publication_policy"] == "continuous"
    assert QUALITY.validate_force_receipt(run, drafts)
    assert (gates / "quality-self-heal-policy-rebind-before.json").is_file()
