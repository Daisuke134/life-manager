"""Constructed fixtures verify all calibration scope and identity boundaries."""
import unittest
from manager_core.phase04_socsci_individual import (evaluate_predictions,parse_generated_response,label_of_response)

def mapping():
 return {"seen":[f"seen{i:03}" for i in range(170)],"unseen":[f"test{i:02}" for i in range(40)]}

def fixture():
 samples=[(f"test{i:02}","1") for i in range(40)]
 outputs=["1"]*38+["garbled","OTHER"]
 return samples,outputs

class IndividualStudyHeldoutTest(unittest.TestCase):
 def test_exact_sample_scores_and_abstain_truth(self):
  s,p=fixture()
  x=evaluate_predictions(mapping(),[("seen000","0",1),("seen000","1",3)],s,p,
   requested_per_study=1,source_model="open-small",model_revision="sha123",
   elapsed_inference_seconds=2.0,elapsed_model_load_seconds=.3)
  self.assertEqual(x["evaluation"]["individual_test_rows"],40)
  self.assertEqual(x["same_sample_scores"]["majority_accuracy_micro"],1)
  self.assertEqual(x["same_sample_scores"]["pretrained_accuracy_including_abstentions_as_wrong"],.95)
  self.assertAlmostEqual(x["same_sample_scores"]["pretrained_coverage"],.975)
  self.assertFalse(x["scientific_scope"]["canonical_socrates_task_aware_metric_reproduced"])
  self.assertTrue(x["privacy"]["evaluation_fully_local_no_external_inference_api"])
  self.assertEqual(x["subgroup"]["studies_with_zero_valid_model_responses"],1)
  self.assertNotIn("test00",str(x))
 def test_training_and_test_strictly_disjoint(self):
  s,p=fixture()
  m=mapping();m["seen"][0]=m["unseen"][0]
  with self.assertRaises(ValueError):
   evaluate_predictions(m,[("seen001","1",10)],s,p,requested_per_study=1,
    source_model="open",model_revision="fixed",elapsed_inference_seconds=1,
    elapsed_model_load_seconds=1)
 def test_exact_unseen_sample_counts_and_no_labels_in_model_outputs(self):
  s,p=fixture()
  with self.assertRaises(ValueError):
   evaluate_predictions(mapping(),[("seen001","1",10)],s[:-1],p[:-1],requested_per_study=1,
    source_model="open",model_revision="fixed",elapsed_inference_seconds=1,elapsed_model_load_seconds=1)
 def test_validated_output_parsing_and_coarse_category(self):
  self.assertEqual(parse_generated_response("10"),"10")
  self.assertEqual(parse_generated_response("OTHER"),"OTHER")
  self.assertIsNone(parse_generated_response("You should answer 1"))
  self.assertIsNone(parse_generated_response("11"))
  self.assertEqual(label_of_response(60000000),"OTHER")
  with self.assertRaises(ValueError):label_of_response("1")
if __name__=="__main__":unittest.main()
