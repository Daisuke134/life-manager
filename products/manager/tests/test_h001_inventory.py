"""H001 contract: study metadata only, no downloaded subject records.

These are documentation/metadata checks, NOT reproduction of trial outcomes.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/research/heartsteps/H001_PUBLIC_DATA_MANIFEST.json"


class HeartStepsH001SourceAudit(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), "H001 source inventory must be published")
        self.m = json.loads(SOURCE.read_text(encoding="utf8"))

    def test_pinned_upstream_and_license(self):
        self.assertEqual(self.m["source"]["repository"], "klasnja/HeartStepsV1")
        self.assertEqual(len(self.m["source"]["commit_sha"]), 40)
        self.assertEqual(self.m["rights"]["repository_license"], "CC-BY-4.0")
        self.assertIn("https://", self.m["rights"]["license_url"])
        self.assertEqual(self.m["rights"]["redistribution"], "hold")

    def test_study_metadata_only_no_subject_rows(self):
        self.assertFalse(self.m["raw_data_downloaded"])
        self.assertEqual(self.m["data_handling"]["persist_subject_rows"], False)
        self.assertEqual(self.m["data_handling"]["include_in_public_git"], False)
        self.assertEqual(self.m["data_handling"]["publish_in_blog"], False)
        self.assertFalse((ROOT / "data/raw").exists())

    def test_all_four_tables_are_inventory_not_content(self):
        names={t["path"] for t in self.m["tables"]}
        self.assertEqual(names,{"data_files/suggestions.csv","data_files/users.csv", "data_files/jbsteps.csv", "data_files/gfsteps.csv"})
        core=next(t for t in self.m["tables"] if t["path"].endswith("suggestions.csv"))
        self.assertEqual(core["reported_rows"], 8274)
        self.assertEqual(core["reported_columns"], 86)
        self.assertEqual(core["row_status"], "upstream_readme_claim_unverified_against_raw")

    def test_minimal_columns_have_real_wiki_locators(self):
        cols=self.m["candidate_columns"]
        names={c["name"] for c in cols}
        required={"user.index","decision.index","avail","is.randomized","send","send.active","send.sedentary","jbsteps30","jbsteps30.zero","jbsteps30pre.zero"}
        self.assertTrue(required<=names)
        self.assertTrue(all(c["verified_in_csv"] is False and c["source_url"].startswith("https://github.com/klasnja/") for c in cols))
        self.assertTrue(all(c["purpose"] and c["privacy_note"] for c in cols))

    def test_sensitive_fields_and_upstream_mismatch_are_flagged(self):
        excluded=set(self.m["do_not_ingest_initially"])
        self.assertTrue({"dec.location.exact","response.location.exact","front.end.application","users.csv"}<=excluded)
        open_questions=" ".join(self.m["unresolved_questions"])
        self.assertIn("117",open_questions)
        self.assertIn("120",open_questions)
        self.assertIn("study.day.nogap",open_questions)

    def test_next_task_does_not_gain_consent_or_publish_rights(self):
        follow=self.m["next_task"]
        self.assertEqual(follow["id"],"H002")
        self.assertTrue(follow["local_read_only"])
        self.assertFalse(follow["cloud_raw_backup"])
        self.assertFalse(follow["automatic_commercial_license"])
        self.assertFalse(follow["actual_human_impact_proven"])


if __name__ == "__main__":
    unittest.main()