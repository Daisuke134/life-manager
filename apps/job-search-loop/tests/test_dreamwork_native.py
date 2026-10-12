import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from job_search_loop.ledger import Ledger, FenceError

try:
    native = importlib.import_module('job_search_loop.dreamwork_native')
except ModuleNotFoundError:
    native = None


class Provider:
    def __init__(self):
        self.state = 'off'
        self.settings = {'scoreFloor': 70, 'resumeVariant': 'default'}
        self.preferences = {'excludedCompanies': []}
        self.confirmed = []
        self.timeout = False

    def action(self, name, args, confirmation_token=None):
        values = {
            'get_usage': {'tier': 'dreamer', 'applicationsLimit': 40, 'applicationsUsedToday': 0},
            'get_application_readiness': {'ready': True, 'autopilotReady': True, 'autopilotAvailable': True, 'entitlement': {'autoApply': True, 'reason': None}},
            'get_autopilot_status': {'state': self.state, 'inFlightCount': 0, 'sentToday': 0, 'dailyLimit': 40, 'sentThisMonth': 0, 'monthlyLimit': 1200, 'nextRunAt': None},
            'get_autopilot_settings': self.settings,
            'get_preferences': {'preferences': self.preferences, 'unanswered': []},
        }
        if name in values:
            return {'status': 'completed', 'output': values[name]}
        if confirmation_token is None:
            self.held = (name, json.loads(json.dumps(args)))
            return {'status': 'held', 'needsInput': {'token': 'fixture-confirmation', 'summary': 'authorized action'}}
        if (name, args) != self.held or confirmation_token != 'fixture-confirmation':
            raise ValueError('exact confirmation binding violated')
        self.confirmed.append(name)
        if name == 'set_autopilot':
            if self.timeout:
                raise TimeoutError('provider outcome unknown')
            self.state = args['state']
        elif name == 'update_autopilot_settings':
            self.settings.update(args)
        elif name == 'update_preferences':
            self.preferences.update(args['patch'])
        return {'status': 'completed', 'output': {'status': 'completed', 'taskId': 'fixture-task'}}


class DreamworkNativeTests(unittest.TestCase):
    def test_native_owner_exists(self):
        self.assertIsNotNone(native, 'native Dreamwork application owner is missing')

    @unittest.skipIf(native is None, 'owner is absent')
    def test_free_match_selector_preserves_rank_but_skips_excluded_applied_and_fenced_companies(self):
        selector = getattr(native, 'select_free_matches', None)
        self.assertTrue(callable(selector), 'free Dreamwork match selector is missing')
        rows = [
            {'id': 'good', 'company': 'Tokyo AI', 'title': 'AI Engineer', 'applied': False, 'saved': False, 'matchPercent': 96},
            {'id': 'excluded', 'company': 'OpenAI', 'title': 'AI Engineer', 'applied': False, 'saved': False, 'matchPercent': 95},
            {'id': 'fenced-alias', 'company': 'Neuralconcept', 'title': 'FDE Japan', 'applied': False, 'saved': False, 'matchPercent': 94},
            {'id': 'already-applied', 'company': 'Other AI', 'title': 'AI Engineer', 'applied': True, 'saved': False, 'matchPercent': 93},
            {'id': 'saved', 'company': 'Saved AI', 'title': 'Applied AI Engineer', 'applied': False, 'saved': True, 'matchPercent': 92},
            {'id': 'unknown-applied', 'company': 'Unknown AI', 'title': 'AI Engineer', 'saved': False, 'matchPercent': 91},
        ]
        selected = selector(
            rows,
            employer_exclusions=['OpenAI', 'Aaru', 'Simily'],
            fenced_companies=['Neural Concept'],
        )
        self.assertEqual([row['id'] for row in selected], ['good', 'saved'])

    @unittest.skipIf(native is None, 'owner is absent')
    def test_free_match_preparation_queues_exact_ats_rows_without_submitting(self):
        prepare = getattr(native, 'prepare_free_matches', None)
        self.assertTrue(callable(prepare), 'free Dreamwork match-to-ATS preparation is missing')
        class FreeProvider:
            def __init__(self):
                self.calls = []
            def action(self, name, args, confirmation_token=None):
                self.calls.append((name, args))
                if name == 'list_matches':
                    return {'status':'completed','output':{'jobs':[
                        {'id':'excluded','company':'OpenAI','title':'Agent Engineer','applied':False,'saved':False,'matchPercent':99},
                        {'id':'fenced','company':'Neuralconcept','title':'FDE Japan','applied':False,'saved':False,'matchPercent':98},
                        {'id':'already-applied','company':'Fresh AI','title':'Applied AI','applied':True,'saved':False,'matchPercent':97},
                        {'id':'fresh','company':'Fresh AI','title':'Applied AI Engineer','applied':False,'saved':False,'matchPercent':96},
                        {'id':'stale','company':'Old AI','title':'Research Engineer','applied':False,'saved':False,'matchPercent':95},
                    ],'total':5,'poolSize':5,'poolStatus':'ready','poolChanged':False,'nextCursor':None}}
                if name == 'get_job':
                    job_id=args['jobId']
                    return {'status':'completed','output':{'job':{
                        'id':job_id,'title':'Applied AI Engineer' if job_id=='fresh' else 'Research Engineer',
                        'company':'Fresh AI' if job_id=='fresh' else 'Old AI','eligible':job_id=='fresh',
                        'sourceUrl':f'https://jobs.ashbyhq.com/{job_id}/role','url':f'https://www.dreamworkhq.com/job/{job_id}'}}}
                if name == 'prepare_applications':
                    return {'status':'completed','output':{'results':[{'jobId':'fresh','applicationId':'provider-app-1','outcome':'queued','message':'queued'}],
                        'allowance':{'limit':3,'usedBefore':0,'admitted':1,'remaining':2,'resetsAt':'2026-10-13T00:00:00Z'}}}
                raise AssertionError(f'unexpected Dreamwork action {name}')
        with tempfile.TemporaryDirectory() as root:
            ledger=Ledger(Path(root)/'ledger.sqlite3')
            try:
                previous=ledger.add_application('Neural Concept','Old Role',
                    'https://jobs.ashbyhq.com/neuralconcept/old')
                ledger.transition(previous,'qualified',{'fixture':True})
                ledger.transition(previous,'materials_ready',{'fixture':True})
                ledger.transition(previous,'submit_claimed',{'fixture':True})
                ledger.transition(previous,'submitted',{'fixture':True})
                provider=FreeProvider()
                result=prepare(provider,state_root=Path(root),ledger=ledger,
                    profile={'candidate':{'employer_exclusions':['OpenAI']}},
                    usage={'tier':'free','applicationsLimit':0,'packsLimit':3,'packsUsedToday':0},max_job_reads=3)
                self.assertEqual(ledger.current_state(previous),'submitted')
                queued=result['queued_application_ids']
                self.assertEqual(len(queued),1)
                self.assertEqual(ledger.current_state(queued[0]),'materials_ready')
                self.assertEqual(result['pack_jobs_queued'],1)
                self.assertEqual([name for name,_ in provider.calls].count('get_job'),2)
                self.assertEqual([name for name,_ in provider.calls].count('prepare_applications'),1)
                self.assertNotIn('apply',[name for name,_ in provider.calls])
                self.assertNotIn('set_autopilot',[name for name,_ in provider.calls])
                pack_state=Path(root)/'dreamwork-free-packs.v1.json'
                self.assertTrue(pack_state.is_file())
                self.assertEqual(pack_state.stat().st_mode & 0o777,0o600)
                record=json.loads(pack_state.read_text())['entries'][queued[0]]
                self.assertEqual(record['dreamwork_application_id'],'provider-app-1')
                self.assertEqual(record['canonical_url'],'https://jobs.ashbyhq.com/fresh/role')
            finally:
                ledger.close()

    @unittest.skipIf(native is None, 'owner is absent')
    def test_free_pack_ingestion_uses_provider_allowance_and_records_local_binding(self):
        prepare = getattr(native, 'prepare_free_matches', None)
        self.assertTrue(callable(prepare), 'Dreamwork Free pack ingestion is missing')
        class FreeProvider:
            def __init__(self):
                self.calls=[]
            def action(self,name,args,confirmation_token=None):
                self.calls.append((name,args))
                if name=='list_matches':
                    return {'status':'completed','output':{'jobs':[
                        {'id':'blocked-by-profile','company':'OpenAI','title':'AI Engineer','applied':False,'saved':False},
                        {'id':'blocked-by-ledger','company':'Neuralconcept','title':'FDE Japan','applied':False,'saved':False},
                        {'id':'already-applied','company':'Fresh AI','title':'AI Engineer','applied':True,'saved':False},
                        {'id':'fresh-job','company':'Fresh AI','title':'Applied AI Engineer','applied':False,'saved':False,'matchPercent':96},
                        {'id':'stale-job','company':'Stale AI','title':'AI Engineer','applied':False,'saved':False,'matchPercent':95},
                    ],'total':5,'poolSize':5,'poolStatus':'ready','poolChanged':False,'nextCursor':None}}
                if name=='get_job':
                    job_id=args['jobId']
                    return {'status':'completed','output':{'job':{
                        'id':job_id,'title':'Applied AI Engineer' if job_id=='fresh-job' else 'AI Engineer',
                        'company':'Fresh AI' if job_id=='fresh-job' else 'Stale AI',
                        'eligible':job_id=='fresh-job','applicationId':None,
                        'sourceUrl':f'https://jobs.ashbyhq.com/{job_id}/role',
                    }}}
                if name=='prepare_applications':
                    return {'status':'completed','output':{'results':[
                        {'jobId':'fresh-job','applicationId':'provider-app-1','outcome':'queued','message':'queued'}
                    ],'allowance':{'limit':3,'usedBefore':0,'admitted':1,'remaining':2,'resetsAt':'2026-10-13T00:00:00Z'}}}
                raise AssertionError(f'unexpected Dreamwork action: {name}')
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            ledger=Ledger(root/'ledger.sqlite3')
            try:
                previous=ledger.add_application('Neural Concept','Old Role',
                    'https://jobs.ashbyhq.com/neuralconcept/old')
                ledger.transition(previous,'qualified',{'fixture':True})
                ledger.transition(previous,'materials_ready',{'fixture':True})
                ledger.transition(previous,'submit_claimed',{'fixture':True})
                ledger.transition(previous,'submitted',{'fixture':True})
                provider=FreeProvider()
                result=prepare(provider,state_root=root,ledger=ledger,
                    profile={'candidate':{'employer_exclusions':['OpenAI']}},
                    usage={'tier':'free','applicationsLimit':0,'packsLimit':3,'packsUsedToday':0},max_job_reads=3)
                self.assertEqual(ledger.current_state(previous),'submitted')
                self.assertEqual(len(result['queued_application_ids']),1)
                local_id=result['queued_application_ids'][0]
                self.assertEqual(ledger.current_state(local_id),'materials_ready')
                self.assertEqual(result['pack_jobs_queued'],1)
                calls=[name for name,_ in provider.calls]
                self.assertEqual(calls.count('get_job'),2)
                self.assertEqual(calls.count('prepare_applications'),1)
                self.assertNotIn('apply',calls)
                self.assertNotIn('set_autopilot',calls)
                map_path=root/'dreamwork-free-packs.v1.json'
                self.assertTrue(map_path.is_file())
                self.assertEqual(map_path.stat().st_mode & 0o777,0o600)
                entry=json.loads(map_path.read_text())['entries'][local_id]
                self.assertEqual(entry['dreamwork_job_id'],'fresh-job')
                self.assertEqual(entry['dreamwork_application_id'],'provider-app-1')
                self.assertEqual(entry['canonical_url'],'https://jobs.ashbyhq.com/fresh-job/role')
            finally:
                ledger.close()

    @unittest.skipIf(native is None, 'owner is absent')
    def test_complete_official_tier_zero_view_allows_only_unmanaged_fallback(self):
        result = {'status': 'unavailable', 'native_managed_on': False, 'readiness': {'entitlement': {'autoApply': False, 'reason': 'tier'}}, 'usage': {'applicationsLimit': 0}, 'autopilot': {'state': 'unavailable', 'sentToday': 0, 'sentThisMonth': 0, 'inFlightCount': None}}
        pipeline = {'jobs': [], 'count': 0, 'total': 0, 'activeTotal': 0, 'closedTotal': 0, 'hasMore': False}
        self.assertTrue(native.unavailable_fallback_is_verified(result, pipeline))
        self.assertFalse(native.unavailable_fallback_is_verified({**result, 'autopilot': {**result['autopilot'], 'inFlightCount': 1}}, pipeline))
        self.assertFalse(native.unavailable_fallback_is_verified(result, {**pipeline, 'hasMore': True}))
        self.assertFalse(native.unavailable_fallback_is_verified({**result, 'native_managed_on': True}, pipeline))
        self.assertFalse(native.unavailable_fallback_is_verified({**result, 'status': 'effect_unknown'}, pipeline))
        prepared_only = {**pipeline, 'jobs':[{'applicationId':'dw-app','saved':True,
            'applied':False,'materialsReady':True,'submission':None}], 'count':1,'total':1}
        self.assertTrue(native.unavailable_fallback_is_verified(result, prepared_only))
        submitted_or_unknown = {**prepared_only, 'jobs':[
            {**prepared_only['jobs'][0], 'submission':{'disposition':'unknown'}}
        ]}
        self.assertFalse(native.unavailable_fallback_is_verified(result, submitted_or_unknown))
        self.assertFalse(native.unavailable_fallback_is_verified(result, {
            **prepared_only, 'jobs':[{**prepared_only['jobs'][0], 'applied':True}]
        }))

    @unittest.skipIf(native is None, 'owner is absent')
    def test_free_account_does_not_call_gated_settings(self):
        class FreeProvider(Provider):
            def action(self, name, args, confirmation_token=None):
                if name == 'get_application_readiness':
                    return {'status': 'completed', 'output': {'ready': False, 'autopilotReady': False, 'autopilotAvailable': True, 'entitlement': {'autoApply': False, 'reason': 'tier'}}}
                if name == 'get_autopilot_settings':
                    raise AssertionError('settings are tier-gated')
                return super().action(name, args, confirmation_token)
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(native.ensure_autopilot(FreeProvider(), Path(root) / 'state.json', {})['status'], 'unavailable')

    @unittest.skipIf(native is None, 'owner is absent')
    def test_paid_dreamwork_tier_is_not_used_under_free_only_policy(self):
        with tempfile.TemporaryDirectory() as root:
            provider = Provider()
            provider.timeout = True
            result = native.ensure_autopilot(provider, Path(root) / 'state.json', {'excludedCompanies': ['Aaru', 'Simily']})
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(result['reason'], 'paid_plan_not_authorized')
            self.assertEqual(provider.state, 'off')
            self.assertEqual(provider.settings['resumeVariant'], 'default')
            self.assertEqual(provider.preferences['excludedCompanies'], [])
            self.assertEqual(provider.confirmed, [])

    @unittest.skipIf(native is None, 'owner is absent')
    def test_native_owner_prepares_free_matches_only_after_verified_zero_entitlement(self):
        class FreeFallbackProvider:
            def __init__(self):
                self.calls = []
            def action(self, name, args, confirmation_token=None):
                self.calls.append((name, args))
                if name == 'get_preferences':
                    return {'status':'completed','output':{'preferences':{'excludedCompanies':[]}}}
                if name == 'list_matches':
                    return {'status':'completed','output':{'jobs':[],'total':0,'poolSize':0,
                        'poolStatus':'ready','poolChanged':False,'nextCursor':None}}
                raise AssertionError(f'unexpected Dreamwork action: {name}')
            def request(self, path):
                self.asserted_path = path
                return {'jobs':[],'hasMore':False}

        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            state_root=root/'state'
            profile_path=root/'profile.json'
            output_path=root/'evidence'/'dreamwork.json'
            profile_path.write_text(json.dumps({'candidate':{
                'application_autonomy':{'authorized':True},
                'dreamwork_preferences':{},'employer_exclusions':[],
            }}))
            provider=FreeFallbackProvider()
            fallback={'status':'unavailable','native_managed_on':False,
                'readiness':{'entitlement':{'autoApply':False,'reason':'tier'}},
                'usage':{'tier':'free','applicationsLimit':0,'packsLimit':3,'packsUsedToday':0},
                'autopilot':{'state':'off','inFlightCount':0,'sentToday':0,'sentThisMonth':0}}
            with mock.patch.object(sys,'argv',['dreamwork_native','--profile',str(profile_path),
                    '--state-root',str(state_root),'--output',str(output_path)]), \
                 mock.patch.object(native,'load_key',return_value='fixture-key'), \
                 mock.patch.object(native,'DreamworkClient',return_value=provider), \
                 mock.patch.object(native,'ensure_autopilot',return_value=fallback), \
                 mock.patch.object(native,'unavailable_fallback_is_verified',return_value=True):
                code=native.main()
            self.assertEqual(code,69)
            self.assertEqual(provider.asserted_path,'/pipeline?limit=500')
            self.assertIn(('list_matches',{'limit':50}),provider.calls)
            self.assertNotIn('apply',[name for name,_ in provider.calls])
            self.assertNotIn('set_autopilot',[name for name,_ in provider.calls])
            output=json.loads(output_path.read_text())
            self.assertTrue(output['fallback_safe'])
            self.assertEqual(output['free_match_preparation']['status'],'no_eligible_matches')

    @unittest.skipIf(native is None, 'owner is absent')
    def test_board_applied_and_queued_are_not_completed_submissions(self):
        rows = [
            {'applicationId': 'A', 'status': 'APPLIED', 'submission': {'disposition': 'unknown'}},
            {'applicationId': 'B', 'submission': {'disposition': 'user_reported'}},
            {'applicationId': 'C', 'submission': {'disposition': 'submitted', 'proof': 'ats_receipt', 'submittedAt': '2026-10-11T00:00:00Z'}},
        ]
        self.assertEqual([row['applicationId'] for row in native.confirmed_submissions(rows)], ['C'])


class ProviderReceiptImportTests(unittest.TestCase):
    def test_imported_receipt_has_one_append_only_origin(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                first = ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                second = ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                self.assertEqual(first, second)
                self.assertEqual(len(ledger.events(first)), 1)
                self.assertEqual(ledger.events(first)[0]['to_state'], 'submitted')
                ledger.event_summary_rows()
            finally:
                ledger.close()

    def test_provider_receipt_does_not_clear_an_unbound_legacy_occurrence(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                application = ledger.add_application('Example', 'AI Engineer', 'https://example.com/jobs/1')
                with self.assertRaises(FenceError):
                    ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                self.assertEqual(ledger.events(application)[-1]['to_state'], 'discovered')
            finally:
                ledger.close()
