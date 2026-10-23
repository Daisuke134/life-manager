import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class LocalFleetManifestTest(unittest.TestCase):
    def build(self, root=ROOT):
        from runtime.loop.local_fleet import build_fleet_manifest

        return build_fleet_manifest(root)

    def test_manifest_keeps_all_registered_jobs_including_system_owners(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        catalog = json.loads((ROOT / "apps/life-manager/config/product-loop-catalog.json").read_text())
        catalog_ids = {job for agent in catalog["loops"] for job in agent["job_ids"]}
        manifest = self.build()

        self.assertEqual(manifest["schema_version"], "local.fleet.v1")
        jobs = {job["loop_id"]: job for job in manifest["jobs"]}
        self.assertEqual(set(jobs), set(registry["loops"]))
        self.assertEqual(manifest["coverage"], {
            "registered_jobs": len(registry["loops"]),
            "catalog_jobs": len(catalog_ids),
            "system_jobs": len(set(registry["loops"]) - catalog_ids),
            "external_labels": len(registry["external_labels"]),
            "additional_host_owners": 1,
        })
        for loop_id in set(jobs) - catalog_ids:
            self.assertEqual(jobs[loop_id]["system_role"], registry["loops"][loop_id]["system_role"])
            self.assertEqual(jobs[loop_id]["product_ids"], [])
        for job in jobs.values():
            self.assertEqual(set(job), {
                "loop_id", "label", "entrypoint", "product_ids", "system_role",
                "browser_target_owner", "browser_identity", "resource_class",
            })
        self.assertEqual(manifest["external_labels"], registry["external_labels"])

    def test_host_steward_distinguishes_registry_jobs_from_disk_watchdog(self):
        manifest = self.build()
        steward = next(agent for agent in manifest["agents"] if agent["id"] == "host-steward")
        self.assertEqual(set(steward["job_ids"]), {
            "life-manager-disk-cleanup", "life-manager-disk-cleanup-15d",
            "lm-fence-reconciler", "life-manager-release-reconciler",
        })
        self.assertNotIn("com.anicca.disk-watchdog", steward["job_ids"])
        self.assertEqual(manifest["host_owners"], [{
            "id": "disk-watchdog",
            "label": "com.anicca.disk-watchdog",
            "installer": "skills/self/disk-cleanup/install-launchd.sh",
            "template": "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist",
        }])

    def test_unmanaged_browser_target_is_informational_and_not_an_inferred_mapping(self):
        manifest = self.build()
        unmanaged = [item for item in manifest["diagnostics"]
                     if item["code"] == "browser_target_not_managed"]
        self.assertEqual({(item["owner_id"], item["target"]) for item in unmanaged}, {
            ("mercor-revenue-application", "mercor-revenue-browser"),
            ("mercor-revenue-reply", "mercor-revenue-browser"),
        })
        for diagnostic in unmanaged:
            self.assertEqual(diagnostic["severity"], "informational")
            self.assertEqual(diagnostic["runtime_validity"], "unverified")
        self.assertIn("ai.anicca.job-search-mercor-browser", manifest["external_labels"])
        self.assertFalse(any(item["target"] == "job-search-browser" for item in unmanaged))
        jobs = {job["loop_id"]: job for job in manifest["jobs"]}
        self.assertEqual(jobs["mercor-revenue-application"]["browser_target_owner"], "mercor-revenue-browser")

    def test_cli_emits_manifest_json_to_stdout(self):
        result = subprocess.run([
            sys.executable, "-m", "runtime.loop.local_fleet", "--repo-root", str(ROOT),
        ], cwd=ROOT, capture_output=True, text=True, check=True)

        self.assertEqual(json.loads(result.stdout), self.build())
        self.assertEqual(result.stderr, "")

    def test_cli_can_save_the_same_json_to_an_explicit_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            result = subprocess.run([
                sys.executable, "-m", "runtime.loop.local_fleet", "--repo-root", str(ROOT),
                "--output", str(output),
            ], cwd=ROOT, capture_output=True, text=True, check=True)

            self.assertEqual(json.loads(output.read_text()), self.build())
            self.assertEqual(output.read_text(), result.stdout)

    def test_invalid_source_joins_are_reported_without_hiding_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "config/loop-registry.json",
                "apps/life-manager/config/product-loop-catalog.json",
                "README.md", "README.ja.md",
                "skills/self/disk-cleanup/install-launchd.sh",
                "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            registry_path = root / "config/loop-registry.json"
            registry = json.loads(registry_path.read_text())
            registry["loops"]["boot-panic-evidence"]["system_role"] = "unclassified"
            registry["loops"]["session-vault"].pop("system_role")
            registry_path.write_text(json.dumps(registry))
            catalog_path = root / "apps/life-manager/config/product-loop-catalog.json"
            catalog = json.loads(catalog_path.read_text())
            catalog["loops"][0]["job_ids"].append("missing-catalog-job")
            catalog_path.write_text(json.dumps(catalog))
            with (root / "README.md").open("a") as stream:
                stream.write("\n| 999 | Unmapped future capability | `unmapped-job` | Future work |\n")

            manifest = self.build(root)

        self.assertEqual(len(manifest["jobs"]), len(registry["loops"]))
        diagnostics = {(item["code"], item["owner_id"], item["target"])
                       for item in manifest["diagnostics"]}
        self.assertIn(("unknown_system_role", "boot-panic-evidence", "unclassified"), diagnostics)
        self.assertIn(("system_role_missing", "session-vault", "session-vault"), diagnostics)
        self.assertIn(("catalog_job_missing", "gig-coconala", "missing-catalog-job"), diagnostics)
        self.assertIn(("readme_agent_unmapped", "README.md", "Unmapped future capability"), diagnostics)


if __name__ == "__main__":
    unittest.main()
