import importlib.util
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("ebook_runner.py")
SPEC = importlib.util.spec_from_file_location("ebook_runner", MODULE_PATH)
ebook_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ebook_runner)


class EbookPortabilityTest(unittest.TestCase):
    def test_default_asset_root_is_life_manager_owned(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"HOME": temp}, clear=False):
                os.environ.pop("LM_EBOOK_ASSET_ROOT", None)
                os.environ.pop("XDG_DATA_HOME", None)
                root = ebook_runner.default_asset_root()
        self.assertEqual(root, Path(temp) / ".local/share/life-manager/ebook-assets")
        self.assertNotIn("openclaw", str(root).lower())
        self.assertNotIn("hermes", str(root).lower())
        self.assertNotIn("monk-factory", str(root).lower())

    def test_explicit_asset_root_wins(self):
        with mock.patch.dict(os.environ, {"LM_EBOOK_ASSET_ROOT": "/tmp/ebook-assets"}):
            self.assertEqual(ebook_runner.default_asset_root(), Path("/tmp/ebook-assets"))

    def test_watercolor_clip_paths_use_existing_mark_factory_scene_sequence(self):
        root = Path("/portable/assets")
        self.assertEqual(ebook_runner.watercolor_clip_paths(root), [
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-02.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-03.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-04.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-05.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-06.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-07.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-08.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-09.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-10.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-12.mp4",
            root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips/scene-13.mp4",
        ])

    def test_japanese_render_fails_closed_on_missing_or_mismatched_factory_assets(self):
        script = {
            "product_id": "ebook-ja", "account_id": "product:ebook-ja",
            "cta": "アニッチャ・リセットを読む", "campaign_id": "campaign-ja", "creative_id": "creative-ja",
            "source_mechanism_ids": ["source-ja"], "declared_mutation": "action",
            "body": "ゆっくり呼吸します。", "renderer_id": "watercolor-monk", "hook": "呼吸",
        }
        pack = {"product_id": "ebook-ja", "renderer_id": "watercolor-monk",
                "slots_jst": ["07:00"], "accounts": []}
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(ebook_runner, "load_ebook_packs", return_value={"ja": pack}), \
                mock.patch.object(ebook_runner, "ScriptLedger") as ledger, \
                mock.patch.object(ebook_runner, "provision_default_pack",
                                  return_value={"state": "replayed"}, create=True) as placeholder_provisioner, \
                mock.patch.object(ebook_runner, "render_watercolor", return_value={
                    "renderer_id": "watercolor-monk", "status": "rendered_preview",
                    "output": str(Path(temp) / "out.mp4"), "sha256": "a" * 64,
                }) as renderer:
            ledger.return_value.get.return_value = script
            asset_root = Path(temp) / "assets"
            broken_clip = (asset_root / "packs/watercolor-mark-factory-v1/"
                           "watercolor-monk/clips/scene-02.mp4")
            broken_clip.parent.mkdir(parents=True)
            broken_clip.write_bytes(b"wrong scene bytes")
            receipt = ebook_runner.run(
                engine=Path(temp), product="ebook-ja", slot_at="2026-09-12T07:00:00+09:00",
                script_id="script-ja", ledger_path=Path(temp) / "scripts.db",
                state_root=Path(temp) / "runs", render_output=Path(temp) / "out.mp4",
                asset_root=asset_root,
            )
        placeholder_provisioner.assert_not_called()
        renderer.assert_not_called()
        self.assertEqual(receipt["state"], "setup_required")
        self.assertIn("scene-02.mp4", receipt["setup"]["mismatched"])
        self.assertEqual(len(receipt["setup"]["missing"]), 10)
        self.assertFalse((asset_root / "packs/default-v1").exists())

    def test_verified_watercolor_pack_detects_changed_scene_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "assets"
            clip_root = root / "packs/watercolor-mark-factory-v1/watercolor-monk/clips"
            rows = []
            for scene_id in ebook_runner.WATERCOLOR_FACTORY_SCENE_IDS:
                content = f"factory-scene-{scene_id}".encode()
                path = clip_root / f"scene-{scene_id}.mp4"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                rows.append({
                    "factory_scene_id": scene_id,
                    "path": f"watercolor-monk/clips/scene-{scene_id}.mp4",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                })
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": "marketing.ebook-watercolor-assets.v1",
                "pack_id": "watercolor-mark-factory-v1",
                "source": "test fixture",
                "clips": rows,
            }), encoding="utf-8")

            verified = ebook_runner.verify_watercolor_mark_factory_pack(
                root, manifest_path=manifest)
            self.assertEqual(verified["state"], "verified")
            self.assertEqual(verified["clips"], [
                str(clip_root / f"scene-{scene_id}.mp4")
                for scene_id in ebook_runner.WATERCOLOR_FACTORY_SCENE_IDS
            ])

            (clip_root / "scene-02.mp4").write_bytes(b"changed scene")
            changed = ebook_runner.verify_watercolor_mark_factory_pack(
                root, manifest_path=manifest)
            self.assertEqual(changed["state"], "setup_required")
            self.assertIn("scene-02.mp4", changed["mismatched"])

    def test_english_render_routes_to_repo_owned_heygen_adapter(self):
        script = {
            "product_id": "ebook-en", "account_id": "product:ebook-en",
            "cta": "Read The Anicca Reset", "campaign_id": "campaign-1",
            "creative_id": "creative-1", "source_mechanism_ids": ["source-1"],
            "declared_mutation": "action", "body": "Breathe slowly.",
            "renderer_id": "heygen-avatar-iv", "hook": "Breathe",
        }
        pack = {
            "product_id": "ebook-en", "renderer_id": "heygen-avatar-iv",
            "slots_jst": ["08:00"], "accounts": [],
            "heygen": {
                "avatar_id": "ce6ef33ff2d0484dabf8a13ce059bbe8",
                "voice_id": "8be9884ebd16499fbe0efb274e769ed5",
            },
        }
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(ebook_runner, "load_ebook_packs", return_value={"en": pack}), \
                mock.patch.object(ebook_runner, "ScriptLedger") as ledger, \
                mock.patch.object(ebook_runner, "render_heygen", return_value={
                    "renderer_id": "heygen-avatar-iv", "state": "setup_required",
                    "missing": ["LM_EBOOK_EN_HEYGEN_AVATAR_ID"], "external_effects": [],
                }) as renderer:
            ledger.return_value.get.return_value = script
            hint_path = Path(temp) / "entrypoint-result.json"
            with mock.patch.dict(os.environ, {"LIFE_MANAGER_RESULT_HINT_PATH": str(hint_path)}):
                receipt = ebook_runner.run(
                    engine=Path(temp), product="ebook-en", slot_at="2026-09-12T08:00:00+09:00",
                    script_id="script-1", ledger_path=Path(temp) / "scripts.db",
                    state_root=Path(temp) / "runs", render_output=Path(temp) / "out.mp4",
                )
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.kwargs["script"], "Breathe slowly.")
        self.assertEqual(renderer.call_args.kwargs["output"], Path(temp) / "out.mp4")
        self.assertEqual(
            renderer.call_args.kwargs["intent_path"],
            Path(temp) / "runs" / f"{receipt['run_id']}.heygen-effect.json",
        )
        self.assertEqual(
            renderer.call_args.kwargs["environment"]["LM_EBOOK_EN_HEYGEN_AVATAR_ID"],
            "ce6ef33ff2d0484dabf8a13ce059bbe8",
        )
        self.assertEqual(
            renderer.call_args.kwargs["environment"]["LM_EBOOK_EN_HEYGEN_VOICE_ID"],
            "8be9884ebd16499fbe0efb274e769ed5",
        )
        self.assertEqual(
            renderer.call_args.kwargs["environment"]["LIFE_MANAGER_RESULT_HINT_PATH"],
            str(hint_path),
        )
        self.assertEqual(receipt["state"], "setup_required")
        self.assertEqual(receipt["external_effects"], [])


if __name__ == "__main__":
    unittest.main()
