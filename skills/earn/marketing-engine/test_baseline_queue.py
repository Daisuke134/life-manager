import hashlib
import json
from pathlib import Path

from baseline_queue import materialize
from script_ledger import ScriptLedger


LEGACY_JA = Path(__file__).parent / "brain/fixtures/ebook-ja-watercolor-baseline-v1.json"


def stored_payloads(ledger):
    with ledger.connect() as db:
        return dict(db.execute("SELECT script_id,payload_json FROM scripts"))


def test_japanese_avatar_baselines_preserve_legacy_scripts_and_replay(tmp_path):
    ledger = ScriptLedger(tmp_path / "scripts.sqlite3")
    legacy = json.loads(LEGACY_JA.read_text())
    assert len(legacy) == 21
    for script in legacy:
        ledger.register(script)
    before = stored_payloads(ledger)

    scripts = materialize(ledger, "ebook-ja")

    assert len(scripts) == 21
    assert len(stored_payloads(ledger)) == 42
    assert {row["renderer_id"] for row in scripts} == {"heygen-avatar-iv"}
    assert {row["version"] for row in scripts} == {"2"}
    assert {row["language"] for row in scripts} == {"ja"}
    assert {row["cta"] for row in scripts} == {"アニッチャ・リセットを読む"}
    assert [row["campaign_id"] for row in scripts] == [
        f"baseline.ebook-ja.avatar-v2.d{day}.s{slot}"
        for day in range(1, 8) for slot in range(1, 4)
    ]
    assert [row["creative_id"] for row in scripts] == [row["campaign_id"] for row in scripts]
    assert [row["source_mechanism_ids"] for row in scripts] == [
        [f"baseline.owner-authored.ebook-ja.avatar-v2.{day}.{slot}"]
        for day in range(1, 8) for slot in range(1, 4)
    ]
    assert len({row["semantic_signature"] for row in scripts}) == 21
    assert set(before).isdisjoint(row["script_id"] for row in scripts)
    assert materialize(ledger, "ebook-ja") == scripts
    after = stored_payloads(ledger)
    assert len(after) == 42
    assert {identifier: after[identifier] for identifier in before} == before


def test_english_baseline_payloads_and_ids_remain_unchanged(tmp_path):
    ledger = ScriptLedger(tmp_path / "scripts.sqlite3")
    scripts = materialize(ledger, "ebook-en")
    payload = json.dumps(scripts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(payload.encode()).hexdigest() == (
        "bb5932bbd80fc9484051c1aa454a6de59d713fe3a5444bab1541863f39f297db"
    )
    assert materialize(ledger, "ebook-en") == scripts
    assert len(stored_payloads(ledger)) == 21
