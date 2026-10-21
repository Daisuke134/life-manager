import unittest
from manager_core.phase04_open_bandit import summarize_policy, compare_policies, CATALOG_SIZE

class BanditExperiment(unittest.TestCase):
    def test_uniform_policy_ips_equals_mean_clicks(self):
        out=summarize_policy([(1,0.5,0),(0,0.5,1),(1,0.5,0),(1,0.5,1)],catalog_size=2)
        self.assertAlmostEqual(out["click_rate"],.75)
        self.assertAlmostEqual(out["random_target_ips"],.75)
        self.assertAlmostEqual(out["random_target_snips"],.75)
        self.assertAlmostEqual(out["importance_weights"]["ess"],4)
    def test_clipping_is_not_hidden_and_randomized_compare_uses_all_arms(self):
        data={}
        for c,k in CATALOG_SIZE.items():
            data["random/"+c]=[(1,1/k,0),(0,1/k,1)]
            data["bts/"+c]=[(0,1/k,0),(1,1/k,1)]
        report=compare_policies(data)
        self.assertEqual(len(report["campaign_results"]),3)
        self.assertFalse(report["limitations"]["causal_benefit_claim"])
        self.assertFalse(report["privacy"]["raw_rows_committed"])
        self.assertEqual(report["campaign_results"][0]["random"]["click_rate"],.5)
    def test_bad_propensities_fail(self):
        for p in (0,-.1,1.01,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                summarize_policy([(1,p,0)],catalog_size=2)
        with self.assertRaises(ValueError):
            summarize_policy([(1,.5,999)],catalog_size=2)
if __name__=="__main__":
    unittest.main()
