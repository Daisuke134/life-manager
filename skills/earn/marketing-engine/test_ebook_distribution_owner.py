from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import threading
import time

import pytest

import ebook_distribute_daily
import ebook_runner


def test_heygen_account_lock_is_shared_by_language_for_heygen_packs(tmp_path, monkeypatch):
    packs = {product: {"product_id": product, "renderer_id": "heygen-avatar-iv",
                       "slots_jst": [slot]} for product, slot in [("ebook-en", "08:00"), ("ebook-ja", "07:00")]}
    monkeypatch.setattr(ebook_distribute_daily, "load_ebook_packs", lambda _engine: packs)
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    products = []

    def run(**kwargs):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            products.append(kwargs["product"])
        time.sleep(0.1)
        with lock:
            active -= 1
        return {"state": "rendered"}

    monkeypatch.setattr(ebook_distribute_daily, "run_ebook", run)
    state_root = tmp_path / "ebook-state"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ebook_distribute_daily.render_slot, product=product, slot_at=slot,
                               state_root=state_root) for product, slot in [
            ("ebook-en", "2026-10-07T08:00:00+09:00"), ("ebook-ja", "2026-10-07T07:00:00+09:00")]]
        assert all(future.result()["receipt"]["state"] == "rendered" for future in futures)
    assert sorted(products) == ["ebook-en", "ebook-ja"]
    assert maximum_active == 1


def test_same_product_slot_renders_once_across_account_owners(tmp_path, monkeypatch):
    renders = 0
    monkeypatch.setattr(ebook_runner, "render_watercolor", lambda **_kwargs: pytest.fail("JA owner must use the HeyGen pack"))
    def render(*, script, language, output, intent_path, environment):
        nonlocal renders
        assert language == "ja"
        assert environment["LM_EBOOK_EN_HEYGEN_AVATAR_ID"] == "ce6ef33ff2d0484dabf8a13ce059bbe8"
        assert environment["LM_EBOOK_EN_HEYGEN_VOICE_ID"] == "662e1397965c484e8f65fa58c77effde"
        renders += 1
        time.sleep(0.05)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"same Japanese eBook render")
        return {
            "renderer_id": "heygen-avatar-iv", "state": "rendered",
            "video_id": "video_japanese_fixture", "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "wallet_cost": {"currency": "usd", "cost_usd": "0.3"},
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_heygen", render)
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
    assert first["receipt"]["renderer_id"] == "heygen-avatar-iv"
    assert first["receipt"]["render"]["video_id"] == "video_japanese_fixture"
    assert renders == 1


def test_english_slot_uses_the_heygen_pack_and_english_campaign_token(tmp_path, monkeypatch):
    def render(*, script, language, output, intent_path, environment):
        output.parent.mkdir(parents=True, exist_ok=True)
        assert language == "en"
        output.write_bytes(b"English HeyGen preview fixture")
        assert environment["LM_EBOOK_EN_HEYGEN_AVATAR_ID"] == "ce6ef33ff2d0484dabf8a13ce059bbe8"
        assert environment["LM_EBOOK_EN_HEYGEN_VOICE_ID"] == "8be9884ebd16499fbe0efb274e769ed5"
        return {
            "renderer_id": "heygen-avatar-iv",
            "state": "rendered",
            "video_id": "video_english_fixture",
            "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "wallet_cost": None,
            "cost_reconciliation_required": True,
            "external_effects": [],
        }

    monkeypatch.setattr(ebook_runner, "render_heygen", render)
    result = ebook_distribute_daily.render_slot(
        product="ebook-en",
        slot_at="2026-10-06T21:00:00+09:00",
        state_root=tmp_path / "ebook-state",
    )

    assert result["receipt"]["state"] == "rendered"
    assert result["script"]["product_id"] == "ebook-en"
    assert result["script"]["language"] == "en"
    assert result["receipt"]["renderer_id"] == "heygen-avatar-iv"
    assert result["receipt"]["render"]["wallet_cost"] is None
    assert result["receipt"]["render"]["cost_reconciliation_required"] is True
    assert result["attribution_token"].startswith("ee_")


@pytest.mark.parametrize("product", ["ebook-en", "ebook-ja"])
def test_new_slot_waits_for_an_unresolved_prior_heygen_cost(tmp_path, monkeypatch, product):
    state_root = tmp_path / "ebook-state"
    runs = state_root / "runs"
    runs.mkdir(parents=True)
    (runs / "ebook-run.previous-slot.heygen-effect.json").write_text(
        '{"schema_version":"marketing.heygen-effect.v1",'
        '"state":"cost_reconciliation_required","video_id":"video_pending"}\n',
        encoding="utf-8",
    )
    render_calls = []

    def render(*, script, language, output, intent_path, environment):
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
        product=product, slot_at=("2026-10-07T08:00:00+09:00" if product == "ebook-en" else "2026-10-07T07:00:00+09:00"), state_root=state_root,
    )

    assert result["receipt"]["state"] == "setup_required"
    assert result["receipt"]["setup"]["reason"] == "prior_heygen_effect_unresolved"
    assert render_calls == []


@pytest.mark.parametrize("products", [("ebook-en", "ebook-en"), ("ebook-en", "ebook-ja")])
def test_slots_serialize_shared_heygen_wallet_reads_and_creates(tmp_path, monkeypatch, products):
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    renders = 0

    def render(*, script, language, output, intent_path, environment):
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
    slots = ("2026-10-07T08:00:00+09:00", "2026-10-07T21:00:00+09:00" if products[1] == "ebook-en" else "2026-10-07T07:00:00+09:00")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: ebook_distribute_daily.render_slot(
            product=item[0], slot_at=item[1], state_root=state_root,
        ), zip(products, slots)))

    assert all(item["receipt"]["state"] == "rendered" for item in results)
    assert renders == 2
    assert maximum_active == 1
