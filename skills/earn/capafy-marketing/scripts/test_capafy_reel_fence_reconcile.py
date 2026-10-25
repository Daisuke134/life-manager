#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_fence_reconcile import OWNER_ID, build_proof

OCC = f"{OWNER_ID}:20261022T004100-abc"


def _run_dir(tmp_path, markers=()):
    d = tmp_path / "runs" / "20261022T004100-abc"
    d.mkdir(parents=True)
    (d / "occurrence.json").write_text(json.dumps({"owner_id": OWNER_ID, "occurrence_id": OCC,
                                                   "target_date": "2026-10-29"}))
    for net in markers:
        (d / f"dispatch-{net}.json").write_text("{}")
    return d


def test_both_posts_read_back_proves_the_effect_with_provider_ids(tmp_path):
    d = _run_dir(tmp_path)
    receipts = _created(tmp_path, d, "ig-post-1")
    _created(tmp_path, d, "x-post-1", marker="x")
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: [f"{net}-post-1"], receipts_dir=receipts)
    assert proof["verified"] is True and proof["outcome"] == "effected"
    assert proof["provider_receipt_id"] == "ig:ig-post-1,x:x-post-1"
    assert proof["owner_id"] == OWNER_ID and proof["occurrence_id"] == OCC


def test_no_dispatch_marker_is_a_pre_effect_proof(tmp_path):
    d = _run_dir(tmp_path)
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: [])
    assert proof["verified"] is True and proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].endswith("occurrence.json")
    assert "provider_receipt_id" not in proof


def test_marker_without_readback_stays_held(tmp_path):
    d = _run_dir(tmp_path, ("ig",))
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: [])
    assert proof["verified"] is False


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ValueError):
        build_proof(OCC, tmp_path / "runs" / "nope", posts_fn=lambda net, slot: [])


def test_second_slot_marker_reads_back_at_second_slot_time(tmp_path):
    d = _run_dir(tmp_path)
    _created(tmp_path, d, "x-1", marker="x")
    receipts = _created(tmp_path, d, "ig-1", marker="ig-s2")
    seen = []
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: seen.append((net, slot)) or [f"{net}-1"],
                        receipts_dir=receipts)
    assert ("ig", "2026-10-29T23:00:00.000Z") in seen and ("x", "2026-10-29T17:00:00.000Z") in seen
    assert proof["verified"] is True



# --- the readback binds this occurrence's Postiz create id, not "any post at that minute" ---
SLUG = "hooklab-d20261029-baking"
IG_SLOT = "2026-10-29T13:00:00.000Z"
SLOTS = {"ig": IG_SLOT, "x": "2026-10-29T17:00:00.000Z", "ig-s2": "2026-10-29T23:00:00.000Z"}


def _created(tmp_path, d, post_id, slot=None, marker="ig"):
    """dispatch marker + the create receipt capafy_reel_daily.schedule writes after POST /posts."""
    net = marker.partition("-s")[0]
    slug = SLUG + marker[len(net):]  # slot 2 is another slug
    (d / f"dispatch-{marker}.json").write_text(json.dumps({"slug": slug, "net": net, "slot": SLOTS[marker]}))
    receipts = tmp_path / "videos"
    (receipts / slug).mkdir(parents=True, exist_ok=True)
    (receipts / slug / f"{net}-receipts-v3.jsonl").write_text(json.dumps(
        {"create": [{"postId": post_id, "integration": "i"}], "scheduled_for": slot or SLOTS[marker]}) + "\n")
    return receipts


def test_another_owners_post_in_the_window_does_not_prove_a_different_create(tmp_path):
    d = _run_dir(tmp_path)
    receipts = _created(tmp_path, d, "ours")
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: ["theirs"], receipts_dir=receipts)
    assert proof["verified"] is False and proof["outcome"] == "held"


def test_create_id_selects_our_post_among_window_candidates(tmp_path):
    d = _run_dir(tmp_path)
    receipts = _created(tmp_path, d, "ours")
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: ["theirs", "ours"], receipts_dir=receipts)
    assert proof["verified"] is True and proof["provider_receipt_id"] == "ig:ours"


def test_marker_without_create_receipt_and_two_candidates_stays_held(tmp_path):
    d = _run_dir(tmp_path, ("ig",))
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: ["theirs", "ours"], receipts_dir=tmp_path / "videos")
    assert proof["verified"] is False and proof["candidates"] == {"ig": ["theirs", "ours"]}


def test_create_receipt_for_another_slot_does_not_bind_this_marker(tmp_path):
    d = _run_dir(tmp_path)
    receipts = _created(tmp_path, d, "ours", slot="2026-10-29T23:00:00.000Z")
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: ["theirs"], receipts_dir=receipts)
    assert proof["verified"] is False and proof["outcome"] == "held"  # unbound: a sole candidate is not ours


def test_marker_without_create_receipt_and_one_other_owner_candidate_stays_held(tmp_path):
    # schedule() writes the marker before upload/POST; a crash there leaves no post and no receipt,
    # and another owner's post on the shared integration that minute is not a proof of ours.
    d = _run_dir(tmp_path, ("ig",))
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: ["theirs"], receipts_dir=tmp_path / "videos")
    assert proof["verified"] is False and proof["outcome"] == "held"

# --- terminal result hint: a passing wake reports its Postiz effect from the same official proof ---
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

from capafy_reel_fence_reconcile import REPO_ROOT, write_result_hint  # noqa: E402
from runtime.loop.lm_loop_run import _verified_terminal_effect_result  # noqa: E402

ENTRYPOINT = "skills/earn/capafy-marketing/capafy-reel-daily.sh"


def _scratch(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    return scratch / "entrypoint-result.json"


def test_effected_proof_writes_a_hint_the_runtime_accepts_as_a_postiz_receipt(tmp_path):
    d = _run_dir(tmp_path)
    receipts = _created(tmp_path, d, "igpost1")
    _created(tmp_path, d, "xpost1", marker="x")
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: [f"{net}post1"], receipts_dir=receipts)
    hint = _scratch(tmp_path)
    assert write_result_hint(proof, hint) is True
    assert _verified_terminal_effect_result(hint, OWNER_ID, OCC, ENTRYPOINT) == (
        "reconciled", "postiz://posts/igpost1")
    assert _verified_terminal_effect_result(hint, OWNER_ID, f"{OWNER_ID}:other", ENTRYPOINT) is None


def test_no_dispatch_proof_writes_a_verified_no_due_slot_hint(tmp_path):
    proof = build_proof(OCC, _run_dir(tmp_path), posts_fn=lambda net, slot: [])
    hint = _scratch(tmp_path)
    assert write_result_hint(proof, hint) is True
    assert _verified_terminal_effect_result(hint, OWNER_ID, OCC, ENTRYPOINT) == (
        "not_applicable", f"lm-no-effect://{OWNER_ID}/{OCC}/no_due_slot")


def test_held_proof_or_existing_file_writes_no_hint(tmp_path):
    held = build_proof(OCC, _run_dir(tmp_path, ("ig",)), posts_fn=lambda net, slot: [])
    hint = _scratch(tmp_path)
    assert write_result_hint(held, hint) is False and not hint.exists()
    hint.write_text("{}")
    effected = {**held, "verified": True, "outcome": "effected", "provider_receipt_id": "ig:igpost1"}
    assert write_result_hint(effected, hint) is False and hint.read_text() == "{}"


def _run_wrapper(tmp_path, reconcile_rc: int) -> tuple[int, Path, Path]:
    skill = tmp_path / "repo/skills/earn/capafy-marketing"
    (skill / "scripts").mkdir(parents=True)
    shutil.copy(REPO_ROOT / ENTRYPOINT, skill / "capafy-reel-daily.sh")
    hint = _scratch(tmp_path)
    seen = tmp_path / "model-env.jsonl"
    # A prompt-injected model pass: forges a verified hint at the guessable scratch path.
    (skill / "scripts/capafy_reel_daily.py").write_text(
        "import json, os, pathlib\n"
        f"open({str(seen)!r}, 'a').write(json.dumps({{k: os.environ.get(k) for k in "
        "('LIFE_MANAGER_RESULT_HINT_PATH', 'LIFE_MANAGER_OCCURRENCE_ID')}) + '\\n')\n"
        "p = pathlib.Path(os.environ['TMPDIR']) / 'entrypoint-result.json'\n"
        "p.write_text('forged'); p.chmod(0o600)\n")
    calls = tmp_path / "reconcile.json"
    (skill / "scripts/capafy_reel_fence_reconcile.py").write_text(
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'hint_existed': os.path.exists({str(hint)!r})}}, open({str(calls)!r}, 'w'))\n"
        f"raise SystemExit({reconcile_rc})\n")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "TMPDIR": str(hint.parent),
           "LIFE_MANAGER_LOOP_ID": OWNER_ID, "LIFE_MANAGER_RUN_ID": "r1",
           "LIFE_MANAGER_OCCURRENCE_ID": f"{OWNER_ID}:r1", "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
           "LM_POSTIZ_API_KEY": "test", "CAPAFY_REEL_STATE_DIR": str(tmp_path / "state")}
    rc = subprocess.run(["bash", str(skill / "capafy-reel-daily.sh")], env=env, timeout=60).returncode
    lines = [json.loads(line) for line in seen.read_text().splitlines()]
    assert lines == [{"LIFE_MANAGER_RESULT_HINT_PATH": None, "LIFE_MANAGER_OCCURRENCE_ID": None}] * 2
    return rc, hint, calls


def test_wrapper_hides_the_hint_from_the_model_and_reports_through_the_official_proof(tmp_path):
    rc, hint, calls = _run_wrapper(tmp_path, reconcile_rc=0)
    assert rc == 0
    assert json.loads(calls.read_text()) == {
        "argv": ["--occurrence", f"{OWNER_ID}:r1", "--result-hint", str(hint)], "hint_existed": False}


def test_wrapper_fails_closed_and_drops_a_forged_hint_when_the_proof_is_held(tmp_path):
    rc, hint, _calls = _run_wrapper(tmp_path, reconcile_rc=1)
    assert rc == 1 and not hint.exists()


def test_result_hint_cli_reads_back_a_claimed_unfenced_occurrence(tmp_path, monkeypatch):
    import capafy_reel_daily
    import capafy_reel_fence_reconcile as reconcile

    d = _run_dir(tmp_path)
    monkeypatch.setattr(capafy_reel_daily, "BASE", _created(tmp_path, d, "igpost9"))
    monkeypatch.setattr(reconcile, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(reconcile, "postiz_posts_at", lambda net, slot: ["igpost9"])
    monkeypatch.setattr(reconcile, "fenced_state", lambda occ: pytest.fail("a passing wake is not fenced"))
    hint = _scratch(tmp_path)
    assert reconcile.main(["--occurrence", OCC, "--result-hint", str(hint)]) == 0
    assert d.exists() and _verified_terminal_effect_result(hint, OWNER_ID, OCC, ENTRYPOINT) == (
        "reconciled", "postiz://posts/igpost9")


def test_postiz_key_falls_back_to_the_credential_ssot_when_the_reconciler_has_no_env(tmp_path, monkeypatch):
    import capafy_reel_fence_reconcile as reconcile

    for name in ("LM_POSTIZ_API_KEY", "POSTIZ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    store = tmp_path / ".local/share/anicca"
    store.mkdir(parents=True)
    (store / "credentials.json").write_text(json.dumps({"credentials": [{"service": "postiz", "api_key": "k-ssot"}]}))
    monkeypatch.setenv("HOME", str(tmp_path))
    seen = {}

    class _Resp:
        def read(self):
            return b'{"posts": []}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(reconcile.urllib.request, "urlopen", fake_urlopen)
    assert reconcile.postiz_posts_at("ig", "2026-11-01T13:00:00Z") == []
    assert seen["auth"] == "k-ssot"
