from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("product_binding.py")
SPEC = importlib.util.spec_from_file_location("product_binding", MODULE_PATH)
assert SPEC and SPEC.loader
binding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n")


class ProductBindingTest(unittest.TestCase):
    def test_exact_integration_binds_account_and_product(self):
        bound, report = binding.bind_product_ids(
            [{"postiz_post_id": "p1", "integration_id": "i1"}],
            {"i1": {"account_id": "tiktok.obou_anicca", "product_id": "ebook-ja"}},
        )
        self.assertEqual(bound[0]["account_id"], "tiktok.obou_anicca")
        self.assertEqual(bound[0]["product_id"], "ebook-ja")
        self.assertIsNone(bound[0]["product_id_null_reason"])
        self.assertEqual(bound[0]["product_binding_source"], "account_manifest.publisher_integration_id")
        self.assertEqual(report, {"rows": 1, "bound": 1, "unmapped": 0, "already_bound": 0})

    def test_unknown_integration_stays_null_with_reason(self):
        bound, report = binding.bind_product_ids(
            [{"postiz_post_id": "p1", "integration_id": "unknown"}], {}
        )
        self.assertIsNone(bound[0]["product_id"])
        self.assertEqual(bound[0]["product_id_null_reason"], "account_manifest_integration_unmapped")
        self.assertEqual(report["unmapped"], 1)

    def test_duplicate_integration_with_different_product_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "a.json", {
                "account_id": "tiktok.one",
                "product_id": "ebook-ja",
                "publisher_integration_id": "i1",
            })
            write_json(root / "b.json", {
                "account_id": "tiktok.two",
                "product_id": "ebook-en",
                "publisher_integration_id": "i1",
            })
            with self.assertRaisesRegex(ValueError, "conflicting duplicate integration mapping"):
                binding.load_account_bindings(root, {"ebook-ja", "ebook-en"})

    def test_duplicate_identical_integration_mapping_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "account_id": "tiktok.one",
                "product_id": "ebook-ja",
                "publisher_integration_id": "i1",
            }
            write_json(root / "a.json", manifest)
            write_json(root / "b.json", manifest)
            self.assertEqual(
                binding.load_account_bindings(root, {"ebook-ja"}),
                {"i1": {"account_id": "tiktok.one", "product_id": "ebook-ja"}},
            )

    def test_unknown_manifest_product_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "account.json", {
                "account_id": "tiktok.one",
                "product_id": "not-registered",
                "publisher_integration_id": "i1",
            })
            with self.assertRaisesRegex(ValueError, "unknown product_id"):
                binding.load_account_bindings(root, {"ebook-ja"})

    def test_missing_account_or_product_ids_are_rejected(self):
        cases = (
            ({"product_id": "ebook-ja", "publisher_integration_id": "i1"}, "account_id"),
            ({"account_id": "tiktok.one", "publisher_integration_id": "i1"}, "product_id"),
        )
        for manifest, field in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_json(root / "account.json", manifest)
                with self.assertRaisesRegex(ValueError, f"missing {field}"):
                    binding.load_account_bindings(root, {"ebook-ja"})

    def test_missing_product_manifest_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "product.json", {"name": "missing id"})
            with self.assertRaisesRegex(ValueError, "missing product_id"):
                binding.load_product_ids(root)

    def test_conflicting_existing_row_binding_is_rejected(self):
        rows = [{"postiz_post_id": "p1", "integration_id": "i1", "product_id": "ebook-en"}]
        with self.assertRaisesRegex(ValueError, "publication product binding conflict"):
            binding.bind_product_ids(
                rows,
                {"i1": {"account_id": "tiktok.one", "product_id": "ebook-ja"}},
            )

    def test_legacy_product_alias_is_the_same_binding(self):
        # Rows persisted before the product-id rename carry "aniccaios"/"honne";
        # treating them as conflicts made marketing-owner-events exit 1 every run.
        bound, report = binding.bind_product_ids(
            [{"postiz_post_id": "p1", "integration_id": "i1", "product_id": "aniccaios"},
             {"postiz_post_id": "p2", "integration_id": "i2", "product_id": "honne"}],
            {"i1": {"account_id": "tiktok.one", "product_id": "anicca-ios"},
             "i2": {"account_id": "tiktok.two", "product_id": "honne-ai"}},
        )
        self.assertEqual([row["product_id"] for row in bound], ["anicca-ios", "honne-ai"])
        self.assertEqual(report["already_bound"], 2)

    def test_same_existing_binding_is_idempotent(self):
        bound, report = binding.bind_product_ids(
            [{
                "postiz_post_id": "p1",
                "integration_id": "i1",
                "account_id": "tiktok.one",
                "product_id": "ebook-ja",
            }],
            {"i1": {"account_id": "tiktok.one", "product_id": "ebook-ja"}},
        )
        self.assertEqual(bound[0]["product_id"], "ebook-ja")
        self.assertEqual(report, {"rows": 1, "bound": 1, "unmapped": 0, "already_bound": 1})

    def test_nullable_manifest_integration_creates_no_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "account.json", {
                "account_id": "instagram.one",
                "product_id": "ebook-ja",
                "publisher_integration_id": None,
            })
            self.assertEqual(binding.load_account_bindings(root, {"ebook-ja"}), {})

    def test_registry_loaders_sort_json_files_deterministically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products = root / "products"
            accounts = root / "accounts"
            products.mkdir()
            accounts.mkdir()
            write_json(products / "z-product.json", {"product_id": "z"})
            write_json(products / "a-product.json", {"product_id": "a"})
            self.assertEqual(binding.load_product_ids(products), {"a", "z"})
            write_json(accounts / "z-account.json", {
                "account_id": "account.z",
                "product_id": "z",
                "publisher_integration_id": "i-z",
            })
            write_json(accounts / "a-account.json", {
                "account_id": "account.a",
                "product_id": "a",
                "publisher_integration_id": "i-a",
            })
            self.assertEqual(
                binding.load_account_bindings(accounts, {"a", "z"}),
                {
                    "i-a": {"account_id": "account.a", "product_id": "a"},
                    "i-z": {"account_id": "account.z", "product_id": "z"},
                },
            )

    def test_malformed_json_and_non_object_manifests_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "broken.json").write_text("{")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                binding.load_product_ids(root)
            (root / "broken.json").unlink()
            write_json(root / "list.json", [])
            with self.assertRaisesRegex(ValueError, "manifest object"):
                binding.load_product_ids(root)

    def test_binding_does_not_mutate_rows_or_bindings(self):
        rows = [{"postiz_post_id": "p1", "integration_id": "i1"}]
        bindings = {"i1": {"account_id": "tiktok.one", "product_id": "ebook-ja"}}
        original_rows = copy.deepcopy(rows)
        original_bindings = copy.deepcopy(bindings)
        binding.bind_product_ids(rows, bindings)
        self.assertEqual(rows, original_rows)
        self.assertEqual(bindings, original_bindings)

    def test_binding_output_is_deterministic_and_preserves_input_order(self):
        rows = [
            {"postiz_post_id": "p2", "integration_id": "i2"},
            {"postiz_post_id": "p1", "integration_id": "i1"},
        ]
        bindings = {
            "i1": {"account_id": "account.one", "product_id": "ebook-ja"},
            "i2": {"account_id": "account.two", "product_id": "ebook-en"},
        }
        bound, _ = binding.bind_product_ids(rows, bindings)
        self.assertEqual([row["postiz_post_id"] for row in bound], ["p2", "p1"])
        self.assertEqual(bound, binding.bind_product_ids(rows, bindings)[0])

    def test_exact_rerun_returns_equal_rows_and_report(self):
        rows = [
            {"postiz_post_id": "p1", "integration_id": "i1"},
            {"postiz_post_id": "p2", "integration_id": "missing"},
        ]
        bindings = {"i1": {"account_id": "tiktok.one", "product_id": "ebook-ja"}}
        first, first_report = binding.bind_product_ids(rows, bindings)
        second, second_report = binding.bind_product_ids(first, bindings)
        self.assertEqual(second, first)
        self.assertEqual(second_report, first_report | {"already_bound": 1})

    def test_every_mobile_destination_integration_has_a_product_binding(self):
        repo_root = Path(__file__).resolve().parents[4]
        destinations = json.loads(
            (repo_root / "config/marketing-destinations.json").read_text(encoding="utf-8")
        )
        targets = [
            row for row in destinations["targets"]
            if row.get("job_product_id") in {"anicca-ios", "honne-ai"}
        ]
        self.assertTrue(targets, "mobile destinations must be declared")
        products = binding.load_product_ids(
            repo_root / "skills/earn/marketing-engine/registry/products"
        )
        account_bindings = binding.load_account_bindings(
            repo_root / "skills/earn/marketing-engine/registry/accounts", products
        )
        missing = sorted(
            row["integration_id"] for row in targets
            if row["integration_id"] not in account_bindings
        )
        self.assertEqual(missing, [])
        for row in targets:
            with self.subTest(integration_id=row["integration_id"]):
                self.assertEqual(
                    account_bindings[row["integration_id"]]["product_id"],
                    row["job_product_id"],
                )


if __name__ == "__main__":
    unittest.main()
