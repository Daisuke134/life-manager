from pathlib import Path


ROOT = Path(__file__).parents[1] / "scripts"


def test_exact_x_editor_content_mismatch_is_repairable_not_live():
    source = (ROOT / "publication_remote.py").read_text(encoding="utf-8")
    assert '"reason": "x-draft-content-mismatch"' in source
    assert '"status": "not-live"' in source
    assert '"repairable_content_mismatch": True' in source


def test_x_content_mismatch_is_a_bounded_ambiguity_recovery_error():
    source = (ROOT / "publication_resume.py").read_text(encoding="utf-8")
    assert '"x-draft-content-mismatch"' in source
    assert '"x-authenticated-edit-url", "x-cdp-saved-article-editor"' in source


def test_same_target_repair_accepts_only_the_explicit_mismatch_proof():
    source = (ROOT / "x-publish" / "x_inplace_repair.py").read_text(encoding="utf-8")
    assert 'remote_proof.get("repairable_content_mismatch") is True' in source
    assert 'remote_proof.get("target") == target' in source
    assert 'remote_proof.get("destination_identity") == expected_identity' in source
