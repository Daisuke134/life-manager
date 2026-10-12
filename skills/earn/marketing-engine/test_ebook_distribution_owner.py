from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import threading
import time

import ebook_distribute_daily
import ebook_runner
from baseline_queue import EN, row
from script_ledger import semantic_signature


def test_english_baseline_uses_slideshow_and_versions_renderer_identity():
    script = row("ebook-en", 1, 1, EN[0])

    assert script["renderer_id"] == "slideshow"
    heygen_script = {**script, "renderer_id": "heygen-avatar-iv"}
    assert semantic_signature(script) != semantic_signature(heygen_script)


def test_same_product_slot_renders_once_across_account_owners(tmp_path, monkeypatch):
    renders = 0
    expected_clips = [
        Path(f"/verified/watercolor-monk/clips/scene-{scene_id}.mp4")
        for scene_id in ("02", "03", "04", "05", "06", "07", "08", "09", "10", "12", "13")
    ]

    def render(*, script, output, clips):
        nonlocal renders
        assert clips == expected_clips
        renders += 1
        time.sleep(0.05)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"same Japanese eBook render")
        return {
            "renderer_id": "watercolor-monk",
            "state": "rendered",
            "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "verify_watercolor_mark_factory_pack", lambda _root: {
        "state": "verified", "pack_id": "watercolor-mark-factory-v1",
        "manifest_sha256": "a" * 64, "clips": [str(path) for path in expected_clips],
        "external_effects": [],
    })
    monkeypatch.setattr(ebook_runner, "render_watercolor", render)
    args = {
        "product": "ebook-ja",
        "slot_at": "2026-10-06T07:00:00+09:00",
        "state_root": tmp_path / "ebook-state",
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        instagram = pool.submit(ebook_distribute_daily.render_slot, **args)
        tiktok = pool.submit(ebook_distribute_daily.render_slot, **args)
        first, second = instagram.result(), tiktok.result()

    assert first["receipt"]["state"] == "rendered"
    assert second["receipt"]["state"] == "rendered"
    assert first["receipt"]["run_id"] == second["receipt"]["run_id"]
    assert first["script"]["script_id"] == second["script"]["script_id"]
    assert first["attribution_token"] == second["attribution_token"]
    assert first["receipt"]["render"]["asset_pack_id"] == "watercolor-mark-factory-v1"
    assert first["receipt"]["render"]["asset_manifest_sha256"] == "a" * 64
    assert renders == 1


def test_english_slot_uses_local_slideshow_and_english_campaign_token(tmp_path, monkeypatch):
    def render(*, script, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"English local slideshow fixture")
        return {
            "renderer_id": "slideshow",
            "state": "rendered",
            "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_slideshow", render, raising=False)
    monkeypatch.setattr(
        ebook_runner, "render_heygen",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("HeyGen renderer was called")),
        raising=False,
    )
    result = ebook_distribute_daily.render_slot(
        product="ebook-en",
        slot_at="2026-10-06T21:00:00+09:00",
        state_root=tmp_path / "ebook-state",
    )

    assert result["receipt"]["state"] == "rendered"
    assert result["script"]["product_id"] == "ebook-en"
    assert result["script"]["language"] == "en"
    assert result["receipt"]["renderer_id"] == "slideshow"
    assert result["attribution_token"].startswith("ee_")


def test_new_english_slot_preserves_prior_heygen_unknown_and_renders_locally(tmp_path, monkeypatch):
    state_root = tmp_path / "ebook-state"
    runs = state_root / "runs"
    runs.mkdir(parents=True)
    sidecar = runs / "ebook-run.previous-slot.heygen-effect.json"
    original = (
        '{"schema_version":"marketing.heygen-effect.v1",'
        '"state":"cost_reconciliation_required","video_id":"video_pending"}\n'
    )
    sidecar.write_text(original, encoding="utf-8")
    render_calls = []

    def render(*, script, output):
        render_calls.append(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"new local slideshow")
        return {
            "renderer_id": "slideshow", "state": "rendered", "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_slideshow", render, raising=False)
    monkeypatch.setattr(
        ebook_runner, "render_heygen",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("HeyGen renderer was called")),
        raising=False,
    )
    result = ebook_distribute_daily.render_slot(
        product="ebook-en", slot_at="2026-10-07T08:00:00+09:00", state_root=state_root,
    )

    assert result["receipt"]["state"] == "rendered"
    assert render_calls
    assert sidecar.read_text(encoding="utf-8") == original


def test_english_slots_use_local_slideshow_without_heygen_effects(tmp_path, monkeypatch):
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    renders = 0

    def render(*, script, output):
        nonlocal active, maximum_active, renders
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            renders += 1
        time.sleep(0.05)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"Local slideshow render {renders}".encode())
        with lock:
            active -= 1
        return {
            "renderer_id": "slideshow", "state": "rendered", "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_slideshow", render, raising=False)
    monkeypatch.setattr(
        ebook_runner, "render_heygen",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("HeyGen renderer was called")),
        raising=False,
    )
    state_root = tmp_path / "ebook-state"
    slots = ("2026-10-07T08:00:00+09:00", "2026-10-07T21:00:00+09:00")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda slot: ebook_distribute_daily.render_slot(
            product="ebook-en", slot_at=slot, state_root=state_root,
        ), slots))

    assert all(item["receipt"]["state"] == "rendered" for item in results)
    assert renders == 2
    assert maximum_active == 1
