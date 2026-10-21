import unittest
from manager_core.phase04_pretrained_eval import LABELS,validate_and_partition,score_same_rows

def split():
    return {"seen":[f"seen{i}" for i in range(170)],"unseen":[f"unseen{i}" for i in range(40)]}

class SameSplitPretrainedContract(unittest.TestCase):
    def rows(self):
        return [(f"seen{i}","example stimulus",str(i%3)) for i in range(170)]+[(f"unseen{i}","new stimulus",str(i%3)) for i in range(40)]
    def test_fixed_study_split_and_equal_rows(self):
        train,test=validate_and_partition(split(),self.rows(),rows_per_study=1)
        self.assertEqual((len(train),len(test)),(170,40))
        p=[[1/12]*12 for _ in test]
        result=score_same_rows([x[2] for x in train],test,p)
        for v in result.values():self.assertEqual((v["n"],v["studies"]),(40,40))
        self.assertTrue(0<=result["frozen_pretrained_encoder_plus_trained_head"]["tvd_study_micro"]<=1)
    def test_input_approval_and_no_future_train(self):
        r=self.rows();r[0]=("unseen0","oops","0")
        with self.assertRaises(ValueError):validate_and_partition(split(),r,rows_per_study=1)
        train,test=validate_and_partition(split(),self.rows(),rows_per_study=1)
        with self.assertRaises(ValueError):score_same_rows([x[2] for x in train],test,[[1.0]*12 for _ in test])
    def test_onehot_pretrained_perfect_and_identical_baselines(self):
        train,test=validate_and_partition(split(),self.rows(),rows_per_study=1)
        p=[[float(LABELS[i]==row[2]) for i in range(len(LABELS))] for row in test]
        result=score_same_rows([r[2] for r in train],test,p)
        self.assertEqual(result["frozen_pretrained_encoder_plus_trained_head"]["accuracy"],1.0)
        self.assertEqual(result["frozen_pretrained_encoder_plus_trained_head"]["brier_multiclass"],0.0)
if __name__=="__main__": unittest.main()
