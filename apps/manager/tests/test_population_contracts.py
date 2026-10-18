import unittest
from manager.population.contracts import JointTable, Marginals, PopulationDataError
from helpers import source

class ContractTests(unittest.TestCase):
    def test_joint_rejects_invalid_values_and_total(self):
        for counts,total in [((1,)*6,7), ((-1,1,1,1,1,1),4), ((float('nan'),)*6,6),
                             ((True,1,1,1,1,1),6), ((1,2),3)]:
            with self.subTest(counts=counts), self.assertRaises(PopulationDataError):
                JointTable('0400000US01',source(),counts,total)

    def test_marginals_validate_both_totals(self):
        Marginals('0400000US01',source(),(30,70),(20,60,20),100)
        for poverty,age,total in [((30,60),(20,60,20),100), ((30,70),(20,50,20),100),
                                   ((30,70),(20,60,20),True), ((0,0),(0,0,0),0)]:
            with self.subTest(poverty=poverty), self.assertRaises(PopulationDataError):
                Marginals('0400000US01',source(),poverty,age,total)
