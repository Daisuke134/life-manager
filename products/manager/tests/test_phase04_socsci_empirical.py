"""No private records are used by the self-contained correctness tests."""
import unittest
from manager_core.phase04_socsci_empirical import evaluate_aggregates

def split():
    return {"seen":[f"seen-{i}" for i in range(170)],
            "unseen":[f"unseen-{i}" for i in range(40)]}

def toy():
    # Synthetic data generated only in these tests. Actual validation is CI.
    rows=[]
    for i in range(170):
        rows.extend([(f"seen-{i}","0",10),(f"seen-{i}","1",10)])
    for i in range(40):
        rows.extend([(f"unseen-{i}","0",5),(f"unseen-{i}","1",15)])
    return rows

class SocSciRealAggregateContract(unittest.TestCase):
    def test_no_leakage_and_train_only_fitted(self):
        a=evaluate_aggregates(split(),toy())
        self.assertEqual(a["source_split"]["seen_rows"],3400)
        self.assertEqual(a["source_split"]["unseen_rows"],800)
        self.assertEqual(a["source_split"]["unseen_studies"],40)
        self.assertEqual(a["train_fitted_distribution"]["0"],0.5)
        self.assertEqual(a["train_fitted_distribution"]["1"],0.5)
        self.assertEqual(a["unseen_baselines"]["majority"]["accuracy_micro"],0.25)
        self.assertEqual(a["unseen_baselines"]["frequency"]["tvd_micro"],0.25)
        b=toy()
        b[-1]=("unseen-39","1",100)
        result=evaluate_aggregates(split(),b)
        self.assertEqual(result["train_fitted_distribution"],a["train_fitted_distribution"])
        self.assertEqual(result["train_majority_label"],a["train_majority_label"])
        self.assertEqual(result["abstention_policy"]["train_only_leave_one_study_out_tvd_p90"],
                         a["abstention_policy"]["train_only_leave_one_study_out_tvd_p90"])
        self.assertFalse(a["calibration"]["meaningful_individual_level_calibration_established"])

    def test_deterministic_study_bootstrap_and_never_use_test_metrics_as_policy(self):
        a=evaluate_aggregates(split(),toy())
        b=evaluate_aggregates(split(),toy())
        self.assertEqual(a,b)
        self.assertEqual(a["abstention_policy"]["decision"],"ABSTAIN_ALL_UNSEEN_FOR_DEPLOYMENT")
        self.assertTrue(a["abstention_policy"]["retrospective_tvd_is_never_used_to_predict_abstention"])
        self.assertFalse(a["privacy"]["raw_rows_saved"])
        self.assertEqual(a["scientific_gates"]["S005_pretrained_model_same_split"],"NOT_RUN")

    def test_require_all_studies_and_fail_on_bad_bucket(self):
        m=split()
        a=toy()
        with self.assertRaises(ValueError):
            evaluate_aggregates(m,a[:-2])
        a[-1]=("unseen-39","secret-opinion",15)
        with self.assertRaises(ValueError):
            evaluate_aggregates(m,a)
        m["unseen"][0]="seen-1"
        with self.assertRaises(ValueError):
            evaluate_aggregates(m,toy())

    def test_subgroup_counts_and_multiclass_brier(self):
        r=evaluate_aggregates(split(),toy())
        self.assertEqual(r["study_level_distribution_error"]["n"],40)
        self.assertEqual(sum(x["studies"] for x in r["subgroups"]),40)
        self.assertEqual(sum(x["rows"] for x in r["subgroups"]),800)
        # Multi-class Brier p0=p1=0.5, q0=.25,q1=.75 -> .5
        self.assertAlmostEqual(r["unseen_baselines"]["frequency"]["brier_multiclass_micro"],.5)
        self.assertGreater(r["unseen_baselines"]["frequency"]["tvd_micro"],0)

if __name__=="__main__":
    unittest.main()
