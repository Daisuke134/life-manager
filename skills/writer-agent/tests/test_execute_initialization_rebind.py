from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "execute-initialization-pair.py"
SPEC = importlib.util.spec_from_file_location("execute_initialization_rebind", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(SCRIPT.parent))


class ExecuteInitializationRebindTest(unittest.TestCase):
    def test_missing_old_release_script_rebinds_to_current_writer_release(self) -> None:
        with TemporaryDirectory() as tmp:
            releases = Path(tmp) / "loops" / "releases"
            release = releases / "20260918T000000-deadbeef"
            writer_root = release / "skills" / "writer-agent"
            script = writer_root / "scripts" / "run.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            script.chmod(0o555)
            old = "/old/loops/releases/20260917T221451-98fa0346/skills/writer-agent/scripts/run.sh"

            old_root = os.environ.get("ARTICLE_ROOT")
            os.environ["ARTICLE_ROOT"] = str(writer_root)
            try:
                rebound, changed = MODULE.rebind_missing_writer_argv(["bash", old, "--channel", "note"])
            finally:
                if old_root is None:
                    os.environ.pop("ARTICLE_ROOT", None)
                else:
                    os.environ["ARTICLE_ROOT"] = old_root

            self.assertTrue(changed)
            self.assertEqual(rebound[0], "bash")
            self.assertEqual(rebound[1], str(script.resolve()))
            self.assertEqual(rebound[2:], ["--channel", "note"])

    def test_unknown_missing_script_is_not_rebound(self) -> None:
        with TemporaryDirectory() as tmp:
            writer_root = Path(tmp) / "loops" / "releases" / "20260918T000000-deadbeef" / "skills" / "writer-agent"
            (writer_root / "scripts").mkdir(parents=True)
            old_root = os.environ.get("ARTICLE_ROOT")
            os.environ["ARTICLE_ROOT"] = str(writer_root)
            try:
                argv, changed = MODULE.rebind_missing_writer_argv(["bash", "/old/custom-publisher.sh"])
            finally:
                if old_root is None:
                    os.environ.pop("ARTICLE_ROOT", None)
                else:
                    os.environ["ARTICLE_ROOT"] = old_root

            self.assertFalse(changed)
            self.assertEqual(argv, ["bash", "/old/custom-publisher.sh"])

    def _v1_fixture(self, root: Path, pairs: list[tuple[str, str, str]], *, product_env: bool = True):
        run_id = "daily-2026-10-15"
        run_dir = root / "state" / "runs" / run_id
        gates = run_dir / "gates"
        gates.mkdir(parents=True)
        ledger = root / "state" / "articles.jsonl"
        state_path = gates / "publication-state.json"
        drafts = {}
        for lang, artifact in (("ja", "article-ja"), ("en", "article-en")):
            source = run_dir / f"article-{lang}.md"
            source.write_text(
                f"# {lang}\n\nBody\n\n"
                f"[Read more](https://writer.example/product?product_id=writer&run_id={run_id}"
                f"&artifact_id={artifact}&variant_id=fixture&click_id=base-{lang})\n",
                encoding="utf-8",
            )
            drafts[lang] = {
                "path": str(source),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        state_path.write_text(json.dumps({
            "version": 1,
            "run_id": run_id,
            "run_dir": str(run_dir),
            "state_path": str(state_path),
            "ledger_path": str(ledger),
            "topic_id": "fixture-topic",
            "drafts": drafts,
            "pairs": {},
        }), encoding="utf-8")
        capture = root / "publisher-copy-path.txt"
        child = root / "fake-publisher.py"
        child.write_text(
            "import json, os, pathlib, sys\n"
            "copy = pathlib.Path(os.environ.get('ARTICLE_PUBLISH_COPY_PATH', ''))\n"
            "if not copy.is_file(): raise SystemExit('missing publisher CTA copy')\n"
            "with open(os.environ['CAPTURE'], 'a', encoding='utf-8') as h: h.write(os.environ['ARTICLE_PUBLISH_PAIR'] + ' ' + str(copy) + '\\n')\n"
            "state_path = pathlib.Path(os.environ['ARTICLE_PUBLICATION_STATE'])\n"
            "state = json.loads(state_path.read_text(encoding='utf-8'))\n"
            "state['pairs']['note/ja'] = {'status':'intent','target_kind':'note-key','target':'n1234567890'}\n"
            "state_path.write_text(json.dumps(state), encoding='utf-8')\n",
            encoding="utf-8",
        )
        rows = []
        for platform, lang, pair in pairs:
            env = {
                "ARTICLE_RUN_DIR": str(run_dir),
                "ARTICLE_PUBLICATION_STATE": str(state_path),
                "ARTICLE_LEDGER": str(ledger),
                "ARTICLE_PUBLISH_PAIR": pair,
                "ARTICLE_PUBLISH_CTA_V1": "1",
                "CAPTURE": str(capture),
            }
            if product_env:
                env["ARTICLE_PRODUCT_ID"] = "writer"
                env["ARTICLE_PRODUCT_LANDING_URL"] = "https://writer.example/product"
            rows.append({
                "platform": platform,
                "lang": lang,
                "argv": [sys.executable, str(child), str(run_dir / f"article-{lang}.md")],
                "env": env,
            })
        (gates / "platform-dispatch.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        return run_dir, state_path, ledger, capture

    def _initialize_note(self, run_dir: Path, state_path: Path, ledger: Path):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"ARTICLE_PRODUCT_ID", "ARTICLE_PRODUCT_LANDING_URL"}
        }
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--pair", "note/ja",
                "--run-dir", str(run_dir),
                "--state", str(state_path),
                "--ledger", str(ledger),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_v1_initialization_dispatch_passes_the_saved_pair_copy(self) -> None:
        with TemporaryDirectory(prefix="writer-initialize-cta-") as tmp:
            run_dir, state_path, ledger, capture = self._v1_fixture(Path(tmp), ACTIVE_ROWS)

            result = self._initialize_note(run_dir, state_path, ledger)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                capture.read_text(encoding="utf-8").splitlines(),
                [f"note/ja {(run_dir / 'gates' / 'publisher-cta' / 'note-ja.md').resolve()}"],
            )
            copy_path = run_dir / "gates" / "publisher-cta" / "note-ja.md"
            self.assertIn("click_id=base-ja-note-ja", copy_path.read_text(encoding="utf-8"))
            self.assertFalse((run_dir / "gates" / "publisher-cta" / "x-article-ja.md").exists())

    def test_legacy_active_four_run_initializes_only_the_active_pairs(self) -> None:
        """20261017-050403 shape: four-row manifest, four-pair CTA contract, no product env."""
        import publisher_cta_copy

        with TemporaryDirectory(prefix="writer-initialize-legacy-four-") as tmp:
            run_dir, state_path, ledger, capture = self._v1_fixture(
                Path(tmp), ACTIVE_ROWS + [("x-article", "ja", "x-article/ja")], product_env=False
            )
            current = publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS
            publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS = current + ("x-article/ja",)
            try:
                publisher_cta_copy.prepare_all(
                    run_dir, landing_url="https://writer.example/product", product_id="writer"
                )
            finally:
                publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS = current
            contract = json.loads((run_dir / "gates" / "publisher-cta" / "contract.json").read_text())
            self.assertIn("x-article/ja", contract["active_pairs"])

            result = self._initialize_note(run_dir, state_path, ledger)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                capture.read_text(encoding="utf-8").splitlines(),
                [f"note/ja {(run_dir / 'gates' / 'publisher-cta' / 'note-ja.md').resolve()}"],
            )

    def test_manifest_missing_an_active_pair_is_refused(self) -> None:
        with TemporaryDirectory(prefix="writer-initialize-missing-") as tmp:
            run_dir, state_path, ledger, capture = self._v1_fixture(
                Path(tmp), ACTIVE_ROWS[:2] + [("x-article", "ja", "x-article/ja")]
            )

            result = self._initialize_note(run_dir, state_path, ledger)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refuse initialization", result.stderr)
            self.assertFalse(capture.exists())


ACTIVE_ROWS = [
    ("note", "ja", "note/ja"),
    ("substack-ja", "ja", "substack/ja"),
    ("substack-en", "en", "substack/en"),
]
