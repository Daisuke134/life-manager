from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from money_sync import sync_state

spec = importlib.util.spec_from_file_location("sales_provenance", SCRIPTS / "measure-sales.py")
measure = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(measure)


def test_natural_observations_join_runtime_and_money_receipt_without_revenue(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "natural-run-1")
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "writer-sales-measure")
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "writer-sales-measure:claim-1")
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", "a" * 40)
    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    # Browser transport is external; parsing, append, import and DB replay are real.
    monkeypatch.setattr(measure, "measure_note_pages", lambda _: {"payload": {
        "sales_url": "https://note.com/dashboard/salesmanage",
        "sales_body": "今月の売上\n総額\n¥0",
        "purchases_url": "https://note.com/dashboard/sales",
        "purchases_body": "2026年10月は購入者がいません",
        "stats_pages": [{"last_page": True, "last_calculate_at": "2026/10/03 14:00",
                         "start_date": "2026/10/01", "end_date": "2026/10/03", "note_stats": []}],
    }})
    monkeypatch.setattr(measure, "measure_substack_pages", lambda _: {"payload": {
        "home_url": "https://aniccabuddha.substack.com/publish/home",
        "home_body": "有料登録者\n-\n0から",
        "earnings_url": "https://aniccabuddha.substack.com/publish/stats/earnings",
        "earnings_body": "MRR\n-\n累計収益\n-\n支払いが処理されると表示します",
    }})
    out = tmp_path / "sales-ledger.jsonl"
    assert measure.main(["--out", str(out), "--articles", str(tmp_path / "articles.jsonl")]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 5
    for row in rows:
        assert row["measurement_run_id"] == "natural-run-1"
        assert row["owner_id"] == "writer-sales-measure"
        assert row["occurrence_id"] == "writer-sales-measure:claim-1"
        assert row["release_sha"] == "a" * 40
    assert [row["value"] for row in rows] == [0, 0, None, None, None]
    db = tmp_path / "money.sqlite3"
    first = sync_state(state_dir=tmp_path, db_path=db)
    replay = sync_state(state_dir=tmp_path, db_path=db)
    assert first["metrics"]["inserted"] == 5
    assert replay["metrics"]["inserted"] == 0
    with sqlite3.connect(db) as conn:
        receipts = {row[0] for row in conn.execute("SELECT receipt_sha256 FROM metric_observations")}
        for row in rows:
            encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            assert hashlib.sha256(encoded).hexdigest() in receipts
        assert conn.execute("SELECT COUNT(*) FROM metric_observations WHERE status='unknown' AND value IS NULL").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM money_events").fetchone()[0] == 0


def test_manual_observation_does_not_invent_runtime_identity(tmp_path, monkeypatch):
    for key in ("LIFE_MANAGER_RUN_ID", "LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RELEASE_SHA"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(measure, "measure_note_pages", lambda _: {"error": "auth unavailable"})
    monkeypatch.setattr(measure, "measure_substack_pages", lambda _: {"error": "auth unavailable"})
    out = tmp_path / "sales-ledger.jsonl"
    assert measure.main(["--out", str(out), "--articles", str(tmp_path / "articles.jsonl")]) == 0
    for row in map(json.loads, out.read_text().splitlines()):
        assert "run_id" not in row
        assert "measurement_run_id" not in row
        assert "release_sha" not in row
        assert row["value"] is None
