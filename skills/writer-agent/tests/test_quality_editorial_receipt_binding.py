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
