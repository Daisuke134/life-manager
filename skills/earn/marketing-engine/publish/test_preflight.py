import json
import pathlib
import shutil
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))

from intent_store import build_intent
from preflight import validate_media, validate_preflight


def make_intent(asset):
    account = json.loads((ENGINE / "registry/accounts/tiktok.obou_anicca.json").read_text())
    return build_intent(
        experiment_id="experiment.preview", creative_id="creative.preview",
        product_id="ebook-ja", account_id="tiktok.obou_anicca",
        hook_id="hook.tiktok.7468922143619812626.002",
        renderer_id="watercolor-monk", adapter="postiz", asset_path=asset,
        caption="距離を変えるとき。『アニッチャ・リセット』を読む https://aniccaai.com/go/ej_preview ej_preview",
        attribution_token="ej_preview", scheduled_at="2026-08-02T01:00:00Z",
        integration_id="cmo5s4edx00vgn10ygnu34a0n", platform="tiktok",
        native_handle="obou_anicca",
        provider_settings=account["publisher_settings"],
        visual_approval_id="visual.accepted.preview",
    )


def test_current_active_account_still_requires_visual_approval(tmp_path):
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"test-video")
    with pytest.raises(ValueError, match="accepted visual approval missing"):
        validate_preflight(make_intent(asset), engine=ENGINE,
                           approvals_path=tmp_path / "missing.jsonl",
                           media_probe=lambda _: valid_probe())


def test_active_account_requires_exact_visual_asset_approval(tmp_path):
    engine = tmp_path / "engine"
    shutil.copytree(ENGINE / "registry", engine / "registry")
    account_path = engine / "registry/accounts/tiktok.obou_anicca.json"
    account = json.loads(account_path.read_text())
    account["status"] = "approved_active"
    account_path.write_text(json.dumps(account))
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"test-video")
    intent = make_intent(asset)
    approvals = tmp_path / "approvals.jsonl"
    with pytest.raises(ValueError, match="accepted visual approval missing"):
        validate_preflight(intent, engine=engine, approvals_path=approvals,
                           media_probe=lambda _: valid_probe())
    approval = {"approval_id": intent["visual_approval_id"], "status": "accepted",
                "asset_sha256": intent["asset_sha256"], "product_id": "ebook-ja",
                "account_id": "tiktok.obou_anicca"}
    approvals.write_text(json.dumps(approval) + "\n")
    result = validate_preflight(intent, engine=engine, approvals_path=approvals,
                                media_probe=lambda _: valid_probe())
    assert result["status"] == "dispatchable"
    assert result["media"]["video_codec"] == "h264"


def test_approval_for_different_asset_fails(tmp_path):
    engine = tmp_path / "engine"
    shutil.copytree(ENGINE / "registry", engine / "registry")
    path = engine / "registry/accounts/tiktok.obou_anicca.json"
    account = json.loads(path.read_text()) | {"status": "approved_active"}
    path.write_text(json.dumps(account))
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"test-video")
    intent = make_intent(asset)
    approvals = tmp_path / "approvals.jsonl"
    approvals.write_text(json.dumps({"approval_id": intent["visual_approval_id"],
        "status": "accepted", "asset_sha256": "0" * 64, "product_id": "ebook-ja",
        "account_id": "tiktok.obou_anicca"}) + "\n")
    with pytest.raises(ValueError, match="visual approval asset mismatch"):
        validate_preflight(intent, engine=engine, approvals_path=approvals,
                           media_probe=lambda _: valid_probe())


def valid_probe():
    return {"duration_seconds": 17.4, "format_names": ["mov", "mp4"],
            "video_codec": "h264", "audio_codec": "aac",
            "width": 720, "height": 1280}


def test_media_contract_accepts_vertical_h264_aac_mp4():
    assert validate_media(valid_probe())["duration_seconds"] == 17.4


@pytest.mark.parametrize("changed,error", [
    ({"video_codec": "hevc"}, "H.264"),
    ({"audio_codec": "mp3"}, "AAC"),
    ({"format_names": ["matroska"]}, "MP4"),
    ({"width": 1280, "height": 720}, "9:16"),
    ({"width": 360, "height": 640}, "720x1280"),
    ({"duration_seconds": 0.2}, "duration"),
])
def test_media_contract_rejects_nonproduction_asset(changed, error):
    with pytest.raises(ValueError, match=error):
        validate_media(valid_probe() | changed)
