from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import publisher_cta_copy  # noqa: E402
from publication_contract import ACTIVE_PAIRS, NEWLY_DORMANT_PAIRS  # noqa: E402
from publisher_cta_copy import (  # noqa: E402
    ACTIVE_PUBLISHER_PAIRS,
    PublisherCTAError,
    prepare_all,
    publisher_copy_path,
)


LANDING = "https://writer.example/product"
RUN_ID = "daily-2026-10-15"
BASE_JA = (
    "# Article JA\n\n本文です。\n\n"
    f"[続きを読む]({LANDING}?product_id=writer&run_id={RUN_ID}"
    "&artifact_id=article-ja&variant_id=role-map&click_id=click-base-ja)\n"
)
BASE_EN = (
    "---\ntitle: A useful guide\ntags: agents, writing\n---\n"
    "# Article EN\n\nUseful body.\n\n"
    f"[Read more]({LANDING}?product_id=writer&run_id={RUN_ID}"
    "&artifact_id=article-en&variant_id=role-map&click_id=click-base-en)\n"
)
EXPECTED_CLICK_IDS = {
    "note/ja": "click-base-ja-note-ja",
    "substack/ja": "click-base-ja-substack-ja",
    "substack/en": "click-base-en-substack-en",
}
LEGACY_X_CLICK_ID = "click-base-ja-x-article-ja"


def prepare_legacy_active_four(run_dir: Path) -> None:
    """Persist the pre-fix contract that still listed dormant x-article/ja."""
    current = publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS
    publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS = current + NEWLY_DORMANT_PAIRS
    try:
        prepare_all(run_dir, landing_url=LANDING, product_id="writer")
    finally:
        publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS = current


def make_run(root: Path, *, ja: str = BASE_JA, en: str = BASE_EN) -> Path:
    run_dir = root / RUN_ID
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    drafts = {}
    for lang, body in (("ja", ja), ("en", en)):
        path = run_dir / f"article-{lang}.md"
        path.write_text(body, encoding="utf-8")
        drafts[lang] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (gates / "publication-state.json").write_text(
        json.dumps({"run_id": RUN_ID, "drafts": drafts}), encoding="utf-8"
    )
    return run_dir


class PublisherCTACopyTests(unittest.TestCase):
    def test_active_publisher_pairs_are_the_publication_contract(self) -> None:
        self.assertEqual(ACTIVE_PUBLISHER_PAIRS, ACTIVE_PAIRS)
        self.assertNotIn("x-article/ja", ACTIVE_PUBLISHER_PAIRS)

    def test_legacy_active_four_contract_still_serves_the_active_copies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-legacy-four-") as tmp:
            run_dir = make_run(Path(tmp))
            prepare_legacy_active_four(run_dir)

            receipts = prepare_all(run_dir, landing_url=LANDING, product_id="writer")

            self.assertEqual(set(receipts), set(ACTIVE_PAIRS) | set(NEWLY_DORMANT_PAIRS))
            for pair in ACTIVE_PAIRS:
                source = run_dir / f"article-{pair.rsplit('/', 1)[1]}.md"
                self.assertEqual(
                    publisher_copy_path(run_dir, pair, source),
                    Path(receipts[pair]["copy_path"]),
                )

    def test_contract_with_unknown_or_missing_pairs_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-bad-contract-") as tmp:
            run_dir = make_run(Path(tmp))
            prepare_all(run_dir, landing_url=LANDING, product_id="writer")
            contract_path = run_dir / "gates" / "publisher-cta" / "contract.json"
            original = json.loads(contract_path.read_text(encoding="utf-8"))
            source = run_dir / "article-ja.md"
            for pairs in (list(ACTIVE_PAIRS[:2]), list(ACTIVE_PAIRS) + ["devto/en"]):
                with self.subTest(pairs=pairs):
                    contract_path.write_text(
                        json.dumps({**original, "active_pairs": pairs}), encoding="utf-8"
                    )
                    with self.assertRaises(PublisherCTAError):
                        publisher_copy_path(run_dir, "note/ja", source)
                    with self.assertRaises(PublisherCTAError):
                        prepare_all(run_dir, landing_url=LANDING, product_id="writer")

    def test_active_pair_copies_change_only_click_id_and_keep_frozen_drafts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-") as tmp:
            run_dir = make_run(Path(tmp))
            original = {
                lang: hashlib.sha256((run_dir / f"article-{lang}.md").read_bytes()).hexdigest()
                for lang in ("ja", "en")
            }

            receipts = prepare_all(
                run_dir, landing_url=LANDING, product_id="writer"
            )

            self.assertEqual(set(receipts), set(ACTIVE_PUBLISHER_PAIRS))
            self.assertEqual(
                {receipt["click_id"] for receipt in receipts.values()},
                set(EXPECTED_CLICK_IDS.values()),
            )
            for pair, receipt in receipts.items():
                lang = pair.rsplit("/", 1)[1]
                artifact_id = "article-en" if lang == "en" else "article-ja"
                source = run_dir / f"article-{lang}.md"
                copy_path = Path(receipt["copy_path"])
                expected_suffix = f"click_id={EXPECTED_CLICK_IDS[pair]})"
                base_suffix = (
                    "click_id=click-base-en)"
                    if lang == "en"
                    else "click_id=click-base-ja)"
                )

                self.assertEqual(receipt["pair"], pair)
                self.assertEqual(receipt["product_id"], "writer")
                self.assertEqual(receipt["run_id"], RUN_ID)
                self.assertEqual(receipt["artifact_id"], artifact_id)
                self.assertEqual(receipt["variant_id"], "role-map")
                self.assertEqual(receipt["source_sha256"], original[lang])
                self.assertEqual(
                    receipt["copy_sha256"],
                    hashlib.sha256(copy_path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    copy_path.read_text(encoding="utf-8"),
                    source.read_text(encoding="utf-8").replace(
                        base_suffix, expected_suffix
                    ),
                )
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(), original[lang]
                )
                self.assertEqual(
                    publisher_copy_path(run_dir, pair, source), copy_path
                )

    def test_retries_reuse_the_same_copy_and_receipt_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-retry-") as tmp:
            run_dir = make_run(Path(tmp))
            first = prepare_all(run_dir, landing_url=LANDING, product_id="writer")
            before = {
                pair: (
                    Path(receipt["copy_path"]).read_bytes(),
                    Path(receipt["receipt_path"]).read_bytes(),
                )
                for pair, receipt in first.items()
            }

            second = prepare_all(run_dir, landing_url=LANDING, product_id="writer")

            for pair, receipt in second.items():
                self.assertEqual(
                    (Path(receipt["copy_path"]).read_bytes(), Path(receipt["receipt_path"]).read_bytes()),
                    before[pair],
                )

    def test_historical_run_without_contract_marker_keeps_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-legacy-") as tmp:
            run_dir = make_run(Path(tmp))
            source = run_dir / "article-ja.md"
            self.assertEqual(publisher_copy_path(run_dir, "x-article/ja", source), source)

    def test_partial_v1_directory_never_falls_back_to_the_frozen_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-partial-") as tmp:
            run_dir = make_run(Path(tmp))
            (run_dir / "gates" / "publisher-cta").mkdir()
            source = run_dir / "article-ja.md"
            with self.assertRaises(PublisherCTAError):
                publisher_copy_path(run_dir, "x-article/ja", source)

    def test_live_content_readback_uses_pair_copy_but_keeps_source_artifact_hash(self) -> None:
        import publication_remote

        with tempfile.TemporaryDirectory(prefix="writer-cta-readback-") as tmp:
            run_dir = make_run(Path(tmp))
            source = run_dir / "article-ja.md"
            source.write_text(
                "# Article JA\n\n本文です。\n\n"
                f"{LANDING}?product_id=writer&run_id={RUN_ID}&artifact_id=article-ja"
                "&variant_id=role-map&click_id=click-base-ja\n",
                encoding="utf-8",
            )
            state_path = run_dir / "gates" / "publication-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            state["drafts"]["ja"]["sha256"] = source_sha
            state["run_dir"] = str(run_dir)
            state["pairs"] = {"note/ja": {"lang": "ja"}}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            prepare_all(run_dir, landing_url=LANDING, product_id="writer")

            copy_path = publication_remote._publisher_content_path(state, "note/ja")
            public_body = copy_path.read_text(encoding="utf-8")
            frozen_body = source.read_text(encoding="utf-8")

            self.assertNotEqual(copy_path, source)
            self.assertTrue(publication_remote.note_content_matches(public_body, copy_path))
            self.assertIn("click_id=click-base-ja-note-ja", public_body)
            self.assertIn("click_id=click-base-ja\n", frozen_body)
            self.assertNotEqual(public_body, frozen_body)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_sha)

    def test_invalid_or_ambiguous_ctas_fail_before_copy_receipts_are_created(self) -> None:
        cases = {
            "missing": "# Article JA\n\n本文です。\n",
            "duplicate-field": BASE_JA.replace(
                "click_id=click-base-ja)",
                "click_id=click-base-ja&click_id=other)",
            ),
            "unsafe": BASE_JA.replace("click-base-ja", "click%20unsafe"),
            "oversized": BASE_JA.replace("click-base-ja", "x" * 129),
            "multiple-links": BASE_JA + BASE_JA.rsplit("\n", 2)[-2] + "\n",
        }
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-invalid-") as tmp:
            for name, ja in cases.items():
                with self.subTest(case=name):
                    case_root = Path(tmp) / name
                    case_root.mkdir()
                    run_dir = make_run(case_root, ja=ja)
                    with self.assertRaises(PublisherCTAError):
                        prepare_all(
                            run_dir, landing_url=LANDING, product_id="writer"
                        )
                    self.assertFalse((run_dir / "gates" / "publisher-cta").exists())

    def test_copy_or_receipt_drift_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="writer-cta-copy-drift-") as tmp:
            root = Path(tmp)
            run_dir = make_run(root / "copy-drift")
            receipts = prepare_all(
                run_dir, landing_url=LANDING, product_id="writer"
            )
            pair = "note/ja"
            copy_path = Path(receipts[pair]["copy_path"])
            source = run_dir / "article-ja.md"
            copy_path.write_text("changed after receipt\n", encoding="utf-8")

            with self.assertRaises(PublisherCTAError):
                publisher_copy_path(run_dir, pair, source)

            receipt_run = make_run(root / "receipt-drift")
            receipt_rows = prepare_all(
                receipt_run, landing_url=LANDING, product_id="writer"
            )
            receipt_path = Path(receipt_rows[pair]["receipt_path"])
            changed = json.loads(receipt_path.read_text(encoding="utf-8"))
            changed["click_id"] = "forged-publisher-click"
            receipt_path.write_text(json.dumps(changed), encoding="utf-8")

            with self.assertRaises(PublisherCTAError):
                publisher_copy_path(
                    receipt_run, pair, receipt_run / "article-ja.md"
                )

            source_run = make_run(root / "source-drift")
            prepare_all(source_run, landing_url=LANDING, product_id="writer")
            changed_source = source_run / "article-ja.md"
            changed_source.write_text(
                changed_source.read_text(encoding="utf-8") + "changed\n",
                encoding="utf-8",
            )
            with self.assertRaises(PublisherCTAError):
                publisher_copy_path(source_run, pair, changed_source)

    def test_x_same_id_repair_adapts_the_saved_x_publisher_copy(self) -> None:
        x_scripts = SCRIPT_DIR / "x-publish"
        sys.path.insert(0, str(x_scripts))
        module_spec = importlib.util.spec_from_file_location(
            "x_inplace_repair", x_scripts / "x_inplace_repair.py"
        )
        self.assertIsNotNone(module_spec)
        module = importlib.util.module_from_spec(module_spec)
        assert module_spec is not None and module_spec.loader is not None
        module_spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory(prefix="writer-cta-x-repair-") as tmp:
            run_dir = make_run(Path(tmp))
            prepare_legacy_active_four(run_dir)
            source = run_dir / "article-ja.md"
            original = source.read_bytes()
            adapted = run_dir / "gates" / "x-article-ja-with-media.md"
            body_asset = run_dir / "body-diagram.png"
            body_asset.write_bytes(b"fixture diagram")

            module._adapt_source(
                {"run_id": RUN_ID, "run_dir": str(run_dir)},
                "x-article/ja",
                source,
                [{"path": str(body_asset), "sha256": hashlib.sha256(body_asset.read_bytes()).hexdigest()}],
                adapted,
            )

            adapted_text = adapted.read_text(encoding="utf-8")
            self.assertIn(
                f"click_id={LEGACY_X_CLICK_ID})",
                adapted_text,
            )
            self.assertNotIn("click_id=click-base-ja)", adapted_text)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
