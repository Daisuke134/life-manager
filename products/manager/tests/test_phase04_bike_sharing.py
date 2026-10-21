"""Proof tests for a rights-cleared PUBLIC AGGREGATE bike-rental benchmark.

Every row is a fictional daily total. These tests do not access real persons.
"""
import csv
import io
import json
import unittest

from manager_core.phase04_bike_sharing import (
    FIELDS, build_report, parse_aggregate_days, git_blob_sha, verify_snapshot,
)


def row(day, year, season, casual, registered, weather=1):
    data = {k: "0" for k in FIELDS}
    data.update({
        "instant": str(day), "dteday": year, "season": str(season),
        "yr": str(int(year[:4]) - 2011), "mnth": year[5:7],
        "holiday": "0", "weekday": "1", "workingday": "1",
        "weathersit": str(weather), "temp": ".3", "atemp": ".3",
        "hum": ".5", "windspeed": ".1", "casual": str(casual),
        "registered": str(registered), "cnt": str(casual + registered),
    })
    return data


def fixture(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


class Phase04RealAggregateContract(unittest.TestCase):
    def sample(self):
        return [
            row(1, "2011-01-01", 1, 100, 100),
            row(2, "2011-01-02", 1, 100, 200),
            row(3, "2011-07-01", 3, 300, 300),
            row(4, "2011-07-02", 3, 400, 400),
            row(5, "2012-01-01", 1, 120, 150),
            row(6, "2012-01-02", 1, 100, 120),
            row(7, "2012-07-01", 3, 430, 500),
            row(8, "2012-07-02", 3, 500, 550),
        ]

    def test_hash_fails_closed_on_any_source_change(self):
        blob = fixture(self.sample())
        sha = git_blob_sha(blob)
        self.assertEqual(verify_snapshot(blob, expected_bytes=len(blob), expected_sha=sha), sha)
        with self.assertRaises(ValueError):
            verify_snapshot(blob + b"x", expected_bytes=len(blob), expected_sha=sha)
        with self.assertRaises(ValueError):
            verify_snapshot(blob, expected_bytes=len(blob), expected_sha="0" * 40)

    def test_2011_train_2012_holdout_and_two_genuine_observed_conditions(self):
        rows = parse_aggregate_days(fixture(self.sample()))
        report = build_report(rows, source_verified=False)
        self.assertEqual(report["train_days"], 4)
        self.assertEqual(report["heldout_days"], 4)
        self.assertEqual(report["split"]["train_year"], 2011)
        self.assertEqual(report["split"]["test_year"], 2012)
        self.assertEqual([x["name"] for x in report["heldout_conditions"]],
                         ["winter_2012", "summer_2012"])
        self.assertEqual(report["heldout_conditions"][0]["days"], 2)
        self.assertEqual(report["heldout_conditions"][1]["days"], 2)
        self.assertIn("mae_daily_rentals", report["baselines"]["season_only"])
        self.assertFalse(report["causal_effect_estimated"])
        self.assertFalse(report["manager_benefit_proven"])
        self.assertEqual(report["socsci210_human_benchmark"], "NOT_PERFORMED_RIGHTS_HOLD")
        self.assertNotIn("dteday", json.dumps(report))
        self.assertNotIn("2012-07-01", json.dumps(report))

    def test_not_randomized_and_no_claim_of_individual_model(self):
        report = build_report(parse_aggregate_days(fixture(self.sample())), source_verified=False)
        self.assertEqual(report["empirical_unit"], "daily aggregate rental count")
        self.assertEqual(report["source_kind"], "PUBLIC_AGGREGATE_OBSERVED")
        self.assertFalse(report["individual_human_behavior_validated"])
        self.assertFalse(report["randomized_intervention_test"])
        self.assertIn("not an unseen SocSci210 study", report["scientific_limitations"])

    def test_rejects_extra_columns_bad_totals_bad_year_duplicate_dates(self):
        base = self.sample()
        wrong = [dict(x) for x in base]
        wrong[2]["cnt"] = "999"
        with self.assertRaises(ValueError):
            parse_aggregate_days(fixture(wrong))
        wrong = [dict(x) for x in base]
        wrong[1]["dteday"] = wrong[0]["dteday"]
        with self.assertRaises(ValueError):
            parse_aggregate_days(fixture(wrong))
        wrong = [dict(x) for x in base]
        wrong[0]["yr"] = "1"
        with self.assertRaises(ValueError):
            parse_aggregate_days(fixture(wrong))
        altered = fixture(base).replace(b"registered,cnt", b"registered,cnt,person_id")
        with self.assertRaises(ValueError):
            parse_aggregate_days(altered)

    def test_rejects_nonchronological_date_and_bad_weather(self):
        wrong = list(reversed(self.sample()))
        with self.assertRaises(ValueError):
            parse_aggregate_days(fixture(wrong))
        wrong = [dict(x) for x in self.sample()]
        wrong[0]["weathersit"] = "999"
        with self.assertRaises(ValueError):
            parse_aggregate_days(fixture(wrong))

    def test_no_outcome_target_in_train_features_and_no_test_label_training(self):
        x = self.sample()
        a = build_report(parse_aggregate_days(fixture(x)), source_verified=False)
        # Modify held-out outcomes only. Train threshold and model probabilities must be identical.
        y = [dict(v) for v in x]
        y[-1]["cnt"] = "1"
        y[-1]["casual"] = "1"
        y[-1]["registered"] = "0"
        b = build_report(parse_aggregate_days(fixture(y)), source_verified=False)
        self.assertEqual(a["train_threshold_daily_rentals"], b["train_threshold_daily_rentals"])
        self.assertEqual(a["train_fitted_parameters"], b["train_fitted_parameters"])

    def test_all_predictions_finite_and_bootstrap_has_fixed_seed(self):
        rows = parse_aggregate_days(fixture(self.sample()))
        a = build_report(rows, source_verified=False)
        b = build_report(rows, source_verified=False)
        self.assertEqual(a, b)
        ci = a["block_bootstrap"]["mae_gain_season_minus_global_ci95"]
        self.assertEqual(len(ci), 2)
        self.assertLessEqual(ci[0], ci[1])


if __name__ == "__main__":
    unittest.main()
