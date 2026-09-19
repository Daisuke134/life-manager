import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/writer-agent/scripts/publication_resume.py"
spec = importlib.util.spec_from_file_location("publication_resume_preflight", SCRIPT)
assert spec and spec.loader
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def test_hashless_quality_init_row_is_effect_free_preflight_only():
    state = {
        "run_id": "20260918-225940",
        "topic_id": "paid-demand:test",
        "pairs": {},
    }
    row = {
        "ts": "2026-09-18T23:13:55Z",
        "run_id": "20260918-225940",
        "topic_id": "paid-demand:test",
        "topic": "test",
        "topic_source": "paid-demand",
        "editorial_form": "explainer",
        "platform": "note",
        "lang": "ja",
        "draft_url": None,
        "state": "pending:publication-init-quality-receipt-unbound",
        "published": False,
        "verified_logged_in": False,
        "live_url": None,
        "public_id": None,
        "receipt": None,
        "published_at": None,
        "reality_gate": None,
        "failure_reason": "publication_resume init refused: editorial receipt hash binding failed",
    }
    assert MODULE._is_nonpublication_preflight_row(row, state) is True
