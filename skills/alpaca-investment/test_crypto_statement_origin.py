"""Captured native PDF origin belongs to provenance, never fee attribution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_performance as perf
import effect_store as store
from test_crypto_operating_costs import OBSERVED, billing
from test_crypto_performance import activity_fixture, cycle_fixture
from test_crypto_statement_evidence import ACCOUNT, DOCUMENT, PDF, UI_ACCOUNT, packet, pdf_process


OTHER_ACCOUNT = '33333333-3333-4333-8333-333333333333'
OTHER_UI = '55555555-5555-4555-8555-555555555555'
OTHER_DOCUMENT = '66666666-6666-4666-8666-666666666666'
HTTP_DATE = 'Fri, 02 Jan 2026 00:00:02 GMT'
PDF_SHA256 = hashlib.sha256(PDF).hexdigest()
QUERY_KEYS = ['X-Amz-Algorithm', 'X-Amz-Credential', 'X-Amz-Date',
    'X-Amz-Expires', 'X-Amz-SignedHeaders', 'X-Amz-Signature']
LAYERS = ('native_account_get', 'margin', 'documents', 'url_resolver', 'download')
ANCHORS = ('known_entry_effect_ids', 'known_closed_cycle_ids', 'known_fee_activity_ids',
    'activity_readbacks', 'order_activity_refs', 'fee_activity_refs', 'fee_checked_at',
    'operating_cost_readback', 'known_operating_cost_components', 'known_operating_cost_source_evidence',
    'known_statement_documents', 'statement_readbacks')


def native_readback(capture=1):
    requests = {name: f'00000000-0000-4000-8000-{capture * 10 + index:012x}'
        for index, name in enumerate(LAYERS, 1)}
    target = {'id': DOCUMENT, 'type': 'crypto_account_statement', 'sub_type': '',
        'date': '2026-01-01', 'name': 'Synthetic crypto statement'}
    rows = [{'id': 'synthetic-application', 'type': 'account_application', 'sub_type': '',
        'date': '2026-01-01', 'name': 'Synthetic application'}, target]
    source = f'/api/v1/accounts/{UI_ACCOUNT}'
    redirect = {'source_host': 's3.amazonaws.com',
        'source_path': '/synthetic-statement-bucket/2026/01/opaque-object.pdf',
        'query_keys': QUERY_KEYS.copy()}
    return {
        'source_host': 'app.alpaca.markets', 'observed_at': '2026-01-02T00:00:02.505Z',
        'source_documents_path': source + '/documents',
        'source_margin_path': source + '/trade_account/margin',
        'source_url_resolver_path': source + f'/documents/{DOCUMENT}/url',
        'native_account_get': {'source_host': 'api.alpaca.markets', 'source_path': '/v2/account',
            'http_status': 200, 'request_id': requests['native_account_get'], 'date': HTTP_DATE, 'id': ACCOUNT},
        'margin': {'status': 200, 'request_id': requests['margin'], 'date': HTTP_DATE, 'id': ACCOUNT},
        'documents': {'status': 200, 'request_id': requests['documents'], 'date': HTTP_DATE, 'rows': rows},
        'target_document': copy.deepcopy(target),
        'url_resolver': {'status': 200, 'request_id': requests['url_resolver'], 'date': HTTP_DATE,
            'id': DOCUMENT, 'root_type': 'object', 'root_keys': ['id', 'url']},
        'download_redirect': redirect,
        'download': {**copy.deepcopy(redirect), 'final_host': redirect['source_host'],
            'final_path': redirect['source_path'], 'request_url_sha256': hashlib.sha256(b'synthetic-url').hexdigest(),
            'status': 200, 'request_id': requests['download'], 'date': 'Fri, 02 Jan 2026 00:00:03 GMT',
            'content_type': 'binary/octet-stream', 'bytes': len(PDF), 'pdf_sha256': PDF_SHA256,
            'matches_previous_pdf': False},
        # Producer conclusions are deliberately false; only native records establish the joins.
        'native_account_match': False, 'document_identity_match': False,
        'url_resolver_identity_match': False, 'origin_chain_verified': False,
    }


def origin_packet(root, readback, *, mode='live', readbacks=None, metadata_changes=None):
    metadata = {'native_account_get_request_id': readback['native_account_get']['request_id'],
        'native_account_get_date': readback['native_account_get']['date'],
        'documents_request_id': readback['documents']['request_id'],
        'rows': copy.deepcopy(readback['documents']['rows']),
        'official_pdf_readbacks': {DOCUMENT: readback} if readbacks is None else readbacks}
    metadata.update(metadata_changes or {})
    return packet(root, mode, metadata_changes=metadata)


class CryptoStatementOriginTests(unittest.TestCase):
    def setUp(self):
        self.source_calls = []

    def no_source(self, **kwargs):
        self.source_calls.append(kwargs)
        raise AssertionError('statement provenance must not acquire provider inputs')

    def write(self, root, *, mode='live', reader=None, billing_path=None):
        observation = {'mode': mode, 'paper': mode == 'paper', 'clock': {'observed_at': OBSERVED}}
        env = {'PATH': os.environ.get('PATH', os.defpath)}
        if billing_path is not None:
            env['LM_CFO_ACTUAL_COST_READBACK'] = str(billing_path)
        with patch.dict(os.environ, env, clear=True), patch('subprocess.run', side_effect=pdf_process):
            report = perf.write_crypto_performance(root, observation, mode=mode,
                owner_id='alpaca-investment-' + mode, activity_reader=reader or self.no_source,
                activity_page_reader=self.no_source)
        self.assertEqual(self.source_calls, [])
        self.assertIsNone(report['net_pnl_usd'])
        self.assertFalse(report['capital_expansion_allowed'])
        self.assertEqual(json.loads((root / 'performance-crypto-latest.json').read_text()), report)
        return report

    def seed_anchors(self, root):
        _, frame, _ = cycle_fixture(root, 'live')
        built = perf.build_crypto_performance(store._rows(root / 'receipts.jsonl'), mode='live',
            owner_id='alpaca-investment-live', activity_readbacks={row['order_id']: frame for row in frame['fills']})
        path = root / 'billing.json'
        path.write_text(json.dumps(billing(built['cycles'][0], 'live')))
        def read(**kwargs):
            return activity_fixture(frame, mode='live', start=kwargs['period_start'], end=kwargs['period_end'])
        packet(root, 'live')
        report = self.write(root, reader=read, billing_path=path)
        self.assertEqual(len(report['known_entry_effect_ids']), 1)
        self.assertEqual(len(report['known_closed_cycle_ids']), 1)
        self.assertEqual(len(report['known_operating_cost_components']), 4)
        return report

    def evidence(self, report):
        return report['fee_evidence']['statement_evidence']

    def assert_rows_unattributed(self, report):
        evidence = self.evidence(report)
        self.assertEqual(evidence['observed_row_count'], 8)
        self.assertEqual(len(evidence['observations']), 8)
        self.assertEqual(evidence['completeness_status'], 'unknown')
        for row in evidence['observations']:
            self.assertEqual(row['capture_mapping_status'], 'metadata_filename_only')
            self.assertEqual(row['current_account_scope_status'], 'unknown')
            self.assertEqual(row['attribution_status'], 'unattributed')
            self.assertEqual(row['net_amount_raw'], '$ --')
            self.assertIsNone(row['net_amount_usd'])
            self.assertNotIn('created_at', row)
            self.assertNotIn('fee_activity_id', row)

    def assert_origin(self, ref, readback):
        origin = ref.get('official_pdf_origin')
        self.assertIsInstance(origin, dict, 'verified native origin must survive the real writer/cache')
        self.assertEqual(origin['status'], 'verified')
        self.assertEqual(origin['pdf_sha256'], PDF_SHA256)
        raw = json.dumps(readback, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(origin['readback_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(origin['native_request_ids'], {name: readback[name]['request_id'] for name in LAYERS})

    def assert_invalid(self, report):
        self.assertEqual(report.get('reason'), 'crypto_statement_input_invalid')
        evidence = self.evidence(report)
        self.assertEqual(evidence['status'], 'unknown')
        self.assertIsNone(evidence['observed_row_count'])
        self.assertEqual(evidence['documents'], [])

    def test_native_chain_reaches_capture_refs_and_daily_without_changing_raw_identity(self):
        # Ignoring native origin, trusting producer flags, or altering raw identity all fail here.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = self.seed_anchors(root)
            readback = native_readback()
            origin_packet(root, readback)
            report = self.write(root)
            self.assert_rows_unattributed(report)
            self.assertEqual(report['known_statement_documents'], legacy['known_statement_documents'])
            self.assertEqual(report['fee_evidence']['observed_fee_count'], 0)
            self.assertEqual(report['fee_evidence']['attributed_native_fees'], [])
            for anchor in ANCHORS[:-2]:
                self.assertEqual(report[anchor], legacy[anchor], anchor)
            raw = report['statement_readbacks'][-1]
            self.assertNotIn('official_pdf_origin', raw)
            self.assertEqual(set(raw), set(legacy['statement_readbacks'][0]))
            evidence = self.evidence(report)
            refs = evidence['documents'][0]['capture_refs']
            self.assertEqual(len(refs), 2)
            verified = [ref for ref in refs if 'official_pdf_origin' in ref]
            self.assertEqual(len(verified), 1, 'only the newly proven capture may claim native origin')
            self.assert_origin(verified[0], readback)
            daily = json.loads((root / 'performance-crypto-daily-2026-01-01.json').read_text())
            self.assertEqual(daily['fee_evidence']['statement_evidence'], evidence)
            self.assertNotIn('statement_readbacks', daily)

    def test_every_native_join_is_checked_instead_of_accepting_the_producer_claim(self):
        # Each mutation leaves a readable Fees PDF; accepting one would mislabel its origin.
        variants = [
            ('portal_host', ('source_host',), 'example.invalid'),
            ('trading_host', ('native_account_get', 'source_host'), 'paper-api.alpaca.markets'),
            ('trading_path', ('native_account_get', 'source_path'), '/v2/orders'),
            ('trading_account', ('native_account_get', 'id'), OTHER_ACCOUNT),
            ('margin_account', ('margin', 'id'), OTHER_ACCOUNT),
            ('documents_ui', ('source_documents_path',), f'/api/v1/accounts/{OTHER_UI}/documents'),
            ('margin_ui', ('source_margin_path',), f'/api/v1/accounts/{OTHER_UI}/trade_account/margin'),
            ('resolver_ui', ('source_url_resolver_path',), f'/api/v1/accounts/{OTHER_UI}/documents/{DOCUMENT}/url'),
            ('resolver_doc_path', ('source_url_resolver_path',), f'/api/v1/accounts/{UI_ACCOUNT}/documents/{OTHER_DOCUMENT}/url'),
            ('target_id', ('target_document', 'id'), OTHER_DOCUMENT),
            ('target_type', ('target_document', 'type'), 'account_statement'),
            ('target_subtype', ('target_document', 'sub_type'), 'other'),
            ('target_date', ('target_document', 'date'), '2026-02-01'),
            ('resolver_id', ('url_resolver', 'id'), OTHER_DOCUMENT),
            ('redirect_host', ('download_redirect', 'source_host'), 'example.invalid'),
            ('redirect_path', ('download_redirect', 'source_path'), '/foreign-object.pdf'),
            ('download_host', ('download', 'source_host'), 'example.invalid'),
            ('download_path', ('download', 'source_path'), '/foreign-object.pdf'),
            ('final_host', ('download', 'final_host'), 'example.invalid'),
            ('final_path', ('download', 'final_path'), '/foreign-object.pdf'),
            ('pdf_hash', ('download', 'pdf_sha256'), '0' * 64),
            ('url_hash', ('download', 'request_url_sha256'), 'not-a-hash'),
            ('observed_at', ('observed_at',), 'invalid'),
        ]
        for layer in LAYERS:
            status = 'http_status' if layer == 'native_account_get' else 'status'
            variants.extend([(layer + '_status', (layer, status), 403),
                (layer + '_status_type', (layer, status), 200.0),
                (layer + '_request', (layer, 'request_id'), ''),
                (layer + '_date', (layer, 'date'), 'invalid')])
        for name, path, value in variants:
            with self.subTest(join=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                good = native_readback()
                bad = copy.deepcopy(good)
                selected = bad
                for key in path[:-1]:
                    selected = selected[key]
                selected[path[-1]] = value
                # Keep the outer capture valid so failure must come from the optional native chain.
                origin_packet(root, good, readbacks={DOCUMENT: bad})
                self.assert_invalid(self.write(root))

    def test_outer_capture_and_the_whole_optional_map_are_validated(self):
        # A valid selected item cannot hide a foreign map key or a capture from another request.
        variants = [
            ('outer_account', {'native_trading_account_id': OTHER_ACCOUNT}),
            ('outer_account_request', {'native_account_get_request_id': 'another-account-request'}),
            ('outer_account_date', {'native_account_get_date': 'Fri, 02 Jan 2026 00:00:01 GMT'}),
            ('outer_documents_request', {'documents_request_id': 'another-documents-request'}),
            ('outer_documents_rows', {'rows': native_readback()['documents']['rows'][1:]}),
            ('optional_null', {'official_pdf_readbacks': None}),
            ('optional_bool', {'official_pdf_readbacks': True}),
            ('optional_number', {'official_pdf_readbacks': 7}),
            ('optional_list', {'official_pdf_readbacks': []}),
            ('readback_empty', {'official_pdf_readbacks': {DOCUMENT: {}}}),
            ('readback_null', {'official_pdf_readbacks': {DOCUMENT: None}}),
            ('producer_flags_only', {'official_pdf_readbacks': {DOCUMENT: {
                'origin_chain_verified': True, 'native_account_match': True,
                'document_identity_match': True, 'url_resolver_identity_match': True}}}),
            ('unknown_key', {'official_pdf_readbacks': {DOCUMENT: native_readback(), OTHER_DOCUMENT: native_readback()}}),
            ('non_statement_key', {'official_pdf_readbacks': {DOCUMENT: native_readback(), 'synthetic-application': native_readback()}}),
        ]
        for name, changes in variants:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                origin_packet(root, native_readback(), metadata_changes=changes)
                self.assert_invalid(self.write(root))

    def test_live_origin_is_not_reusable_as_paper_and_legacy_refs_keep_their_shape(self):
        # Live capture is not evidence for Paper; absent proof must not invalidate legacy caches.
        for mode in ('paper', 'live'):
            with self.subTest(legacy=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                packet(root, mode)
                first = self.write(root, mode=mode)
                again = self.write(root, mode=mode)
                self.assert_rows_unattributed(again)
                self.assertEqual(self.evidence(again), self.evidence(first))
                ref = self.evidence(again)['documents'][0]['capture_refs'][0]
                self.assertEqual(set(ref), {'metadata_sha256', 'source_receipt_id'})
                self.assertEqual(list(root.glob('performance-crypto-daily-*.json')), [])
        with self.subTest(case='live_origin_in_paper'), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin_packet(root, native_readback(), mode='paper')
            self.assert_invalid(self.write(root, mode='paper'))

    def test_legacy_new_capture_replay_and_missing_input_retain_one_document_and_provenance(self):
        # Provenance changes may add captures, never another copy of the same eight raw fees.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet(root, 'live')
            legacy = self.write(root)
            first_origin = native_readback(1)
            second_origin = native_readback(2)
            origin_packet(root, first_origin)
            self.write(root)
            origin_packet(root, second_origin)
            captured = self.write(root)
            replay = self.write(root)
            shutil.rmtree(root / 'statement-readbacks')
            missing = self.write(root)
            for wake, report in (('fresh', captured), ('replay', replay), ('missing', missing)):
                with self.subTest(wake=wake):
                    self.assert_rows_unattributed(report)
                    self.assertEqual(report['known_statement_documents'], legacy['known_statement_documents'])
                    self.assertEqual(len(report['statement_readbacks']), 3)
                    evidence = self.evidence(report)
                    self.assertEqual(len(evidence['documents']), 1)
                    refs = evidence['documents'][0]['capture_refs']
                    self.assertEqual(len(refs), 3)
                    by_request = {ref['official_pdf_origin']['native_request_ids']['native_account_get']: ref
                        for ref in refs if 'official_pdf_origin' in ref}
                    self.assertEqual(set(by_request), {first_origin['native_account_get']['request_id'],
                        second_origin['native_account_get']['request_id']})
                    for origin in (first_origin, second_origin):
                        self.assert_origin(by_request[origin['native_account_get']['request_id']], origin)
                    self.assertEqual(evidence['observations'][0]['capture_refs'], refs)
            self.assertEqual(missing['statement_input_status'], 'unavailable')
            self.assertEqual(list(root.glob('performance-crypto-daily-*.json')), [])

    def test_invalid_later_origin_retains_known_rows_origin_and_financial_anchors(self):
        # Rejecting a later capture must keep accepted provenance and unrelated paid history.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_anchors(root)
            accepted_origin = native_readback(1)
            origin_packet(root, accepted_origin)
            first = self.write(root)
            bad = native_readback(2)
            bad['margin']['id'] = OTHER_ACCOUNT
            origin_packet(root, bad)
            report = self.write(root)
            for anchor in ANCHORS:
                self.assertEqual(report[anchor], first[anchor], anchor)
            self.assertEqual(report.get('reason'), 'crypto_statement_input_invalid')
            self.assert_rows_unattributed(report)
            self.assertEqual(self.evidence(report)['documents'], self.evidence(first)['documents'])
            self.assertEqual(self.evidence(report)['observations'], self.evidence(first)['observations'])
            refs = self.evidence(report)['documents'][0]['capture_refs']
            verified = [ref for ref in refs if 'official_pdf_origin' in ref]
            self.assertEqual(len(verified), 1)
            self.assert_origin(verified[0], accepted_origin)
            daily = json.loads((root / 'performance-crypto-daily-2026-01-01.json').read_text())
            self.assertEqual(daily['fee_evidence']['statement_evidence'], self.evidence(first))

    def test_forged_summary_origin_is_rebuilt_from_raw_and_cannot_promote_legacy_capture(self):
        # Trusting a cached verified label would let a legacy capture manufacture official origin.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.seed_anchors(root)
            changed = copy.deepcopy(first)
            evidence = self.evidence(changed)
            for item in [*evidence['documents'], *evidence['observations']]:
                item['capture_refs'][0]['official_pdf_origin'] = {'status': 'verified',
                    'pdf_sha256': PDF_SHA256, 'readback_sha256': 'a' * 64,
                    'native_request_ids': {name: 'forged-request' for name in LAYERS}}
            (root / 'performance-crypto-latest.json').write_text(json.dumps(changed))
            report = self.write(root)
            self.assertEqual(report.get('reason'), 'crypto_statement_evidence_conflict')
            self.assertEqual(self.evidence(report)['status'], 'conflict')
            self.assert_rows_unattributed(report)
            for anchor in ANCHORS:
                self.assertEqual(report[anchor], first[anchor], anchor)
            for item in [*self.evidence(report)['documents'], *self.evidence(report)['observations']]:
                self.assertTrue(all('official_pdf_origin' not in ref for ref in item['capture_refs']))

    def test_valid_raw_origin_rebuilds_a_cache_written_before_the_derived_field_existed(self):
        # Strict comparison with an older derived view must not reject valid retained native proof.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_anchors(root)
            readback = native_readback()
            origin_packet(root, readback)
            first = self.write(root)
            old_cache = copy.deepcopy(first)
            evidence = self.evidence(old_cache)
            for item in [*evidence['documents'], *evidence['observations']]:
                for ref in item['capture_refs']:
                    ref.pop('official_pdf_origin', None)
            (root / 'performance-crypto-latest.json').write_text(json.dumps(old_cache))
            report = self.write(root)
            self.assertEqual(report.get('reason'), 'crypto_costs_or_fx_unknown')
            self.assert_rows_unattributed(report)
            for anchor in ANCHORS:
                self.assertEqual(report[anchor], first[anchor], anchor)
            refs = self.evidence(report)['documents'][0]['capture_refs']
            self.assertEqual(len(refs), 2)
            verified = [ref for ref in refs if 'official_pdf_origin' in ref]
            self.assertEqual(len(verified), 1, 'retained raw proof must reconstruct the newly derived origin')
            self.assert_origin(verified[0], readback)
            daily = json.loads((root / 'performance-crypto-daily-2026-01-01.json').read_text())
            self.assertEqual(daily['fee_evidence']['statement_evidence'], self.evidence(report))


if __name__ == '__main__':
    unittest.main()
