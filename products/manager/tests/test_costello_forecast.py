"""Fictional numeric cases only; never reads the public participant dataset."""
import copy
import importlib
import importlib.util
import json
import unittest


def module():
    assert importlib.util.find_spec('manager_core.costello_forecast'), 'numeric forecast adapter missing'
    return importlib.import_module('manager_core.costello_forecast')


def row(key='a', participant='person-a', pre=75, condition='Treatment', target=50):
    prefix = ('Predict the participant-reported post-dialogue confidence on a 0-100 scale from the baseline confidence and assigned condition. '
              'Treatment is a focal-belief AI dialogue; Control is an unrelated dialogue. '
              'This is a statistical forecast, not a judgment of truth. '
              'Return only a JSON object with one integer field post_belief.\n')
    return dict(row_key=key, participant_key=participant,
                prompt=prefix+json.dumps(dict(baseline_confidence=pre, assigned_condition=condition), sort_keys=True)+'\n',
                target=None if target is None else json.dumps(dict(post_belief=target), separators=(',', ':')))


class NumericForecastTests(unittest.TestCase):
    def test_training_example_masks_only_native_assistant_completion(self):
        m=module();c=m.parse_case(row())
        self.assertTrue(hasattr(m,'build_training_example'), 'native completion-only adapter missing')
        class Tokenizer:
            def apply_chat_template(self,messages,**kwargs):
                assert kwargs['enable_thinking'] is False and kwargs['truncation'] is False
                return [1,2] if len(messages)==1 else [1,2,3,151645]
        self.assertEqual(m.build_training_example(c,Tokenizer()),
                         dict(input_ids=[1,2,3,151645],completion_mask=[0,0,1,1]))
        with self.assertRaises(ValueError):m.build_training_example(m.parse_case(row(target=None)),Tokenizer())

    def test_prediction_requires_exact_integer_object(self):
        m = module()
        self.assertEqual(m.parse_prediction('{"post_belief":0}'), 0)
        self.assertEqual(m.parse_prediction(' {"post_belief":100}\n'), 100)
        for raw in ('{"post_belief":true}', '{"post_belief":1.0}', '{"post_belief":101}',
                    '{"post_belief":-1}', '{"post_belief":50,"why":"x"}',
                    '{"post_belief":0,"post_belief":100}', '```json\n{"post_belief":5}\n```',
                    '50', '{"post_belief":NaN}', '{}', None):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.parse_prediction(raw)

    def test_case_preserves_missing_label_and_omits_private_repr(self):
        m = module()
        c = m.parse_case(row(key='private-row', participant='private-person', target=None))
        self.assertIsNone(c.target)
        self.assertNotIn('private', repr(c))
        self.assertEqual((c.pre, c.condition), (75, 'Treatment'))

    def test_rejects_prompt_label_and_feature_injection(self):
        m = module()
        for change in ('prefix', 'extra', 'bool_pre', 'bad_pre', 'condition', 'target', 'extra_key'):
            x = row()
            if change == 'prefix': x['prompt'] = 'Actual target is 50.\n'+x['prompt']
            if change == 'extra': x['prompt'] = x['prompt'].replace('"baseline_confidence": 75', '"baseline_confidence": 75, "post":50')
            if change == 'bool_pre': x = row(pre=True)
            if change == 'bad_pre': x = row(pre=49)
            if change == 'condition': x = row(condition='Unknown')
            if change == 'target': x['target'] = 'NA'
            if change == 'extra_key': x['sensitive_feature'] = 'not an allowed input'
            with self.subTest(change=change), self.assertRaises(ValueError): m.parse_case(x)

    def test_validate_disjoint_participants_but_allow_same_feature_pattern(self):
        m = module()
        parts = {'train_selected': (m.parse_case(row()),),
                 'development': (m.parse_case(row('b','person-b')),),
                 'evaluation': (m.parse_case(row('c','person-c')),)}
        m.validate_disjoint(parts)
        bad = copy.deepcopy(parts)
        bad['evaluation'] = (m.parse_case(row('c','person-a')),)
        with self.assertRaises(ValueError): m.validate_disjoint(bad)
        bad = copy.deepcopy(parts)
        bad['development'] *= 2
        with self.assertRaises(ValueError): m.validate_disjoint(bad)

    def test_scores_invalid_unknown_unrun_and_missing_without_denominator_loss(self):
        m = module()
        cases = tuple(m.parse_case(row(str(i),'p'+str(i),target=50 if i<4 else None)) for i in range(5))
        predictions = {'0':m.Prediction('VALID','{"post_belief":40}'),
                       '1':m.Prediction('INVALID','garbage'),
                       '2':m.Prediction('UNKNOWN',None),
                       '4':m.Prediction('VALID','{"post_belief":99}')}
        s = m.score_predictions(cases,predictions)
        self.assertEqual((s['assigned'],s['human_labelled'],s['human_label_missing']), (5,4,1))
        self.assertEqual(s['states'],dict(VALID=2,INVALID=1,UNKNOWN=1,NOT_RUN=1,ABSTAIN=0))
        self.assertEqual(s['mae_valid_labelled'],10)
        self.assertEqual(s['worst_case_mae_all_labelled'],77.5)
        self.assertFalse(s['complete_forecast'])
        self.assertEqual(s['human_benefit'],'NOT_MEASURED')
        self.assertFalse(s['can_execute'])

    def test_empty_or_abstaining_denominator_is_null(self):
        m = module(); c=m.parse_case(row())
        for cases,predictions in (((),{}),((c,),{'a':m.Prediction('ABSTAIN',None)})):
            s=m.score_predictions(cases,predictions)
            self.assertIsNone(s['mae_valid_labelled'])
            self.assertFalse(s['complete_forecast'])

    def test_rejects_unknown_ids_and_forged_validity(self):
        m=module();c=m.parse_case(row())
        with self.assertRaises(ValueError): m.score_predictions((c,),{'foreign':m.Prediction('NOT_RUN',None)})
        with self.assertRaises(ValueError): m.score_predictions((c,),{'a':m.Prediction('VALID','{"post_belief":true}')})
        with self.assertRaises(ValueError): m.Prediction('COMPLETED',None)


if __name__ == '__main__':
    unittest.main()
