import json
import pathlib
import sys
from types import ModuleType, SimpleNamespace

import jsonschema
import pytest

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))

from publish_cli import run_create_intent


def _install_hook_lab_test_route(monkeypatch):
    product = json.loads((ENGINE / "registry/products/hook-lab.json").read_text())
    account = {
        "product_id": "hook-lab",
        "allowed_renderer_ids": ["watercolor-monk"],
        "publisher_integration_id": "test-hooklab-integration",
        "publisher_settings": {"__type": "instagram"},
        "platform": "instagram",
        "native_handle": "capafy.hooklab",
    }
    router = ModuleType("product_router")
    router.load_registry = lambda _engine: SimpleNamespace(
        products={"hook-lab": product},
        accounts={"life-manager-capafy-ig": account},
    )
    router.canonical_product_id = lambda product_id: product_id
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "product_router", router)


def _hook_lab_intent_args(tmp_path, attribution_token):
    asset = tmp_path / "hooklab-preview.mp4"
    asset.write_bytes(b"preview")
    return dict(
        engine=ENGINE,
        output_path=tmp_path / "hooklab-intent.json",
        experiment_id="experiment.dd03",
        creative_id="creative.dd03",
        product_id="hook-lab",
        account_id="life-manager-capafy-ig",
        hook_id="hook.dd03",
        renderer_id="watercolor-monk",
        adapter="postiz",
        asset_path=asset,
        caption=f"Open Hook Lab on Capafy https://aniccaai.com/go/{attribution_token}",
        attribution_token=attribution_token,
        scheduled_at="2026-10-16T00:00:00Z",
        visual_approval_id="visual.accepted.dd03",
        now="2026-10-14T00:00:00Z",
    )


def test_intent_create_resolves_immutable_route_from_registry(tmp_path):
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"preview")
    output = tmp_path / "intent.json"
    result = run_create_intent(
        engine=HERE.parent, output_path=output,
        experiment_id="experiment.gate12", creative_id="creative.gate12",
        product_id="ebook-ja", account_id="tiktok.obou_anicca",
        hook_id="hook.gate12", renderer_id="watercolor-monk", adapter="postiz",
        asset_path=asset,
        caption="『アニッチャ・リセット』を読む https://aniccaai.com/go/ej_token ej_token",
        attribution_token="ej_token", scheduled_at="2026-08-02T02:00:00Z",
        visual_approval_id="visual.accepted.gate12", now="2026-08-02T00:00:00Z")
    intent = json.loads(output.read_text())
    assert result["publish_key"] == intent["publish_key"]
    assert intent["native_handle"] == "obou_anicca"
    assert intent["integration_id"] == "cmo5s4edx00vgn10ygnu34a0n"
    assert intent["provider_settings"]["__type"] == "tiktok"
    schema = json.loads((HERE.parent / "schemas/publication-intent.schema.json").read_text())
    jsonschema.validate(intent, schema)


def test_intent_create_rejects_cross_product_route_and_conflicting_output(tmp_path):
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"preview")
    args = dict(
        engine=HERE.parent, output_path=tmp_path / "intent.json",
        experiment_id="experiment.gate12", creative_id="creative.gate12",
        product_id="ebook-ja", account_id="tiktok.obou_anicca",
        hook_id="hook.gate12", renderer_id="watercolor-monk", adapter="postiz",
        asset_path=asset,
        caption="『アニッチャ・リセット』を読む https://aniccaai.com/go/ej_token ej_token",
        attribution_token="ej_token", scheduled_at="2026-08-02T02:00:00Z",
        visual_approval_id="visual.accepted.gate12", now="2026-08-02T00:00:00Z")
    run_create_intent(**args)
    with pytest.raises(ValueError, match="conflicting immutable intent output"):
        run_create_intent(**(args | {"scheduled_at": "2026-08-02T03:00:00Z"}))
    with pytest.raises(ValueError, match="account product mismatch"):
        run_create_intent(**(args | {"output_path": tmp_path / "wrong.json",
                                     "product_id": "ebook-en"}))
    with pytest.raises(ValueError, match="scheduled time must be in the future"):
        run_create_intent(**(args | {"output_path": tmp_path / "past.json",
                                     "scheduled_at": "2026-08-01T23:59:59Z"}))


def test_hook_lab_intent_rewrites_registered_ct_placeholder(monkeypatch, tmp_path):
    _install_hook_lab_test_route(monkeypatch)
    args = _hook_lab_intent_args(tmp_path, "hooklab_ig")
    result = run_create_intent(**args)
    intent = json.loads(args["output_path"].read_text())
    assert intent["attribution_token"] == "hl_r7py2zlsvjjafl4srigi"
    assert "https://aniccaai.com/go/hl_r7py2zlsvjjafl4srigi" in intent["caption"]
    assert "https://aniccaai.com/go/hooklab_ig" not in intent["caption"]
    assert result["external_mutations"] == 0


def test_hook_lab_intent_rejects_foreign_ct(monkeypatch, tmp_path):
    _install_hook_lab_test_route(monkeypatch)
    args = _hook_lab_intent_args(tmp_path, "ej_abcdefghijklmnopqrst")
    with pytest.raises(ValueError, match="Hook Lab attribution token"):
        run_create_intent(**args)


@pytest.mark.parametrize("malformed_url", [
    "https://aniccaai.com/go/hooklab_igx",
    "https://aniccaai.com/go/hooklab_ig?diagnostic=1",
    "https://aniccaai.com/go/hooklab_ig#diagnostic",
])
def test_hook_lab_intent_rejects_non_exact_owned_url(monkeypatch, tmp_path, malformed_url):
    _install_hook_lab_test_route(monkeypatch)
    args = _hook_lab_intent_args(tmp_path, "hooklab_ig")
    args["caption"] = f"Open Hook Lab on Capafy {malformed_url}"
    with pytest.raises(ValueError, match="Hook Lab owned attribution URL"):
        run_create_intent(**args)
    assert not args["output_path"].exists()
