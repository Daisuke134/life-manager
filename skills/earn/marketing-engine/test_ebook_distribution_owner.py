from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import threading
import time

import ebook_distribute_daily
import ebook_runner


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


def test_english_slot_uses_the_heygen_pack_and_english_campaign_token(tmp_path, monkeypatch):
    def render(*, script, output, intent_path, environment):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"English HeyGen preview fixture")
        assert environment["LM_EBOOK_EN_HEYGEN_AVATAR_ID"] == "ce6ef33ff2d0484dabf8a13ce059bbe8"
        assert environment["LM_EBOOK_EN_HEYGEN_VOICE_ID"] == "8be9884ebd16499fbe0efb274e769ed5"
        return {
            "renderer_id": "heygen-avatar-iv",
            "state": "rendered",
            "video_id": "video_english_fixture",
            "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_heygen", render)
    result = ebook_distribute_daily.render_slot(
        product="ebook-en",
        slot_at="2026-10-06T14:00:00+09:00",
        state_root=tmp_path / "ebook-state",
    )

    assert result["receipt"]["state"] == "rendered"
    assert result["script"]["product_id"] == "ebook-en"
    assert result["script"]["language"] == "en"
    assert result["receipt"]["renderer_id"] == "heygen-avatar-iv"
    assert result["attribution_token"].startswith("ee_")


def test_new_english_slot_waits_for_an_unresolved_prior_heygen_cost(tmp_path, monkeypatch):
    state_root = tmp_path / "ebook-state"
    runs = state_root / "runs"
    runs.mkdir(parents=True)
    (runs / "ebook-run.previous-slot.heygen-effect.json").write_text(
        '{"schema_version":"marketing.heygen-effect.v1",'
        '"state":"cost_reconciliation_required","video_id":"video_pending"}\n',
        encoding="utf-8",
    )
    render_calls = []

    def render(*, script, output, intent_path, environment):
        render_calls.append(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"must not render while prior charge is unresolved")
        return {
            "renderer_id": "heygen-avatar-iv", "state": "rendered",
            "video_id": "video_new", "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "wallet_cost": {"currency": "usd", "cost_usd": "0.3"},
            "external_effects": ["heygen_video_created"],
        }

    monkeypatch.setattr(ebook_runner, "render_heygen", render)
    result = ebook_distribute_daily.render_slot(
        product="ebook-en", slot_at="2026-10-07T08:00:00+09:00", state_root=state_root,
    )

    assert result["receipt"]["state"] == "setup_required"
    assert result["receipt"]["setup"]["reason"] == "prior_heygen_effect_unresolved"
    assert render_calls == []


def test_english_slots_serialize_shared_heygen_wallet_reads_and_creates(tmp_path, monkeypatch):
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    renders = 0

    def render(*, script, output, intent_path, environment):
        nonlocal active, maximum_active, renders
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            renders += 1
        time.sleep(0.05)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"HeyGen render {renders}".encode())
        with lock:
            active -= 1
        return {
            "renderer_id": "heygen-avatar-iv", "state": "rendered",
            "video_id": f"video_{renders:08d}", "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "wallet_cost": {"currency": "usd", "cost_usd": "0.3"},
            "external_effects": ["heygen_video_created"],
        }

    monkeypatch.setattr(ebook_runner, "render_heygen", render)
    state_root = tmp_path / "ebook-state"
    slots = ("2026-10-07T08:00:00+09:00", "2026-10-07T14:00:00+09:00")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda slot: ebook_distribute_daily.render_slot(
            product="ebook-en", slot_at=slot, state_root=state_root,
        ), slots))

    assert all(item["receipt"]["state"] == "rendered" for item in results)
    assert renders == 2
    assert maximum_active == 1
