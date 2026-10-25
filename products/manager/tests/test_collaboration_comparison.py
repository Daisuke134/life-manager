"""Family-isolated reproducible comparison, with no accidental provider calls."""
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from manager_core.collaboration_comparison import load_suite, evaluate_suite, RecordedProviderRun
from manager_core.collaboration_baselines import no_action_baseline, rule_baseline
from manager_core.collaboration import render_prompt

ROOT=Path(__file__).resolve().parents[1]/'evaluation/collaboration-v2'


class ComparisonTests(unittest.TestCase):
    def test_family_split_no_overlap(self):
        s=load_suite(ROOT)
        self.assertEqual(len(s.development_cases),20)
        self.assertEqual(len(s.evaluation_cases),40)
        self.assertFalse({c.family_id for c in s.development_cases}&{c.family_id for c in s.evaluation_cases})

    def test_eval_is_40_cases_120_provider_repeats(self):
        r=evaluate_suite(load_suite(ROOT))
        self.assertEqual(r['evaluation_cases'],40)
        self.assertEqual(r['scheduled_attempts_per_policy'],120)
        self.assertEqual(r['provider_status'],'NOT_RUN')
        self.assertIsNone(r['provider_label_agreement'])
        self.assertEqual(r['actual_provider_calls'],0)

    def test_evaluator_hidden(self):
        for c in load_suite(ROOT).evaluation_cases:
            text=render_prompt(c.context)
            self.assertNotIn(c.rationale,text)
            self.assertNotIn('acceptable_decisions',text)
            self.assertNotIn('forbidden_decisions',text)

    def test_same_inputs_budget(self):
        s=load_suite(ROOT);seen=[]
        # Recorded advice is bound to the exact public prompt, not evaluator labels.
        supplied=RecordedProviderRun('recorded',s.manifest_sha256,{}, {})
        with self.assertRaises(ValueError): evaluate_suite(s,provider=supplied)

    def test_recorded_attempts_keep_transport_and_format_failures(self):
        from hashlib import sha256
        s=load_suite(ROOT)
        contexts={c.case_id:sha256(render_prompt(c.context).encode()).hexdigest() for c in s.evaluation_cases}
        outputs={f'{c.case_id}:{i}':json.dumps(dict(decision='PASS',reason='No action.',source_ids=[]))
                 for c in s.evaluation_cases for i in range(3)}
        first=s.evaluation_cases[0].case_id
        outputs[first+':0']=None
        outputs[first+':1']='malformed'
        r=evaluate_suite(s,provider=RecordedProviderRun('recorded',s.manifest_sha256,contexts,outputs))
        supplied=r['policies']['supplied_provider']
        self.assertEqual(supplied['transport_failures'],1)
        self.assertEqual(supplied['format_failures'],1)
        self.assertIsNone(supplied['raw_attempts'][0]['decision'])
        self.assertIsNone(supplied['settled_cost_usd'])
        self.assertEqual(r['actual_provider_calls'],0)
        self.assertEqual(r['provider_status'],'SUPPLIED_OUTPUTS_NOT_AUTHENTICATED')

    def test_no_action_baseline_preserved(self):
        for c in load_suite(ROOT).evaluation_cases:
            r=no_action_baseline(c.context)
            self.assertEqual(r.decision,'PASS')
            self.assertFalse(r.authorized_execution)

    def test_frozen_case_mutation_rejected(self):
        with TemporaryDirectory() as tmp:
            dst=Path(tmp)/'suite';shutil.copytree(ROOT,dst)
            p=dst/'cases.json';d=json.loads(p.read_text());d['families'][0]['variants'][0]['acceptable_decisions']=['PROPOSE'];p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):load_suite(dst)

    def test_rule_is_repeatable_and_cannot_see_private_labels(self):
        s=load_suite(ROOT);c=s.evaluation_cases[0]
        changed=replace(c,rationale='OTHER_PRIVATE_REASON',acceptable_decisions=frozenset({'PASS'}),forbidden_decisions=frozenset({'ASK','PROPOSE'}))
        self.assertEqual(rule_baseline(c.context),rule_baseline(changed.context))
        self.assertEqual(evaluate_suite(s),evaluate_suite(s))

    def test_confidence_interval_is_family_clustered_and_scope_limited(self):
        r=evaluate_suite(load_suite(ROOT))
        self.assertEqual(r['paired_rule_minus_no_action']['clusters'],8)
        self.assertEqual(r['paired_rule_minus_no_action']['resamples'],2000)
        self.assertEqual(r['conclusion'],'NO_PROVIDER_COMPARISON')
        self.assertEqual(r['human_outcome'],'NOT_MEASURED')


if __name__=='__main__': unittest.main()
