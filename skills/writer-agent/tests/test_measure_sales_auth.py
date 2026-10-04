from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure-sales.py"
SPEC = importlib.util.spec_from_file_location("writer_measure_sales", SCRIPT)
measure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(measure)


def completed(payload: dict) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return subprocess.CompletedProcess([], 0, stdout=f"PAYLOAD_B64:{encoded}\n", stderr="")


def test_note_driver_recovers_the_ordinary_login_form(monkeypatch):
    captured = {}

    def fake(script: str, timeout: int = 90):
        captured["script"] = script
        return completed({
            "sales_url": "https://note.com/dashboard/salesmanage",
            "sales_body": "今月の売上\n総額\n¥0",
            "purchases_url": "https://note.com/dashboard/sales",
            "purchases_body": "2026年10月は購入者がいません",
            "stats_url": "https://note.com/sitesettings/stats",
            "stats_pages": [],
        })

    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_note_pages(9222)
    assert 'input[name="login"]' in captured["script"]
    assert 'input[name="password"]' in captured["script"]
    assert "NOTE_EMAIL" in captured["script"]
    assert "'ログイン'" in captured["script"]


def test_substack_driver_injects_the_existing_session_cookie(monkeypatch):
    captured = {}

    def fake(script: str, timeout: int = 90):
        captured["script"] = script
        return completed({
            "home_url": "https://aniccabuddha.substack.com/publish/home",
            "home_body": "有料登録者\n-\n0から",
            "earnings_url": "https://aniccabuddha.substack.com/publish/stats/earnings",
            "earnings_body": "-\n支払いを受け取るようになると、収益がここに表示されます",
        })

    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_substack_pages(9222)
    assert "SUBSTACK_SESSION_COOKIE" in captured["script"]
    assert "ctx.add_cookies(cookies)" in captured["script"]
