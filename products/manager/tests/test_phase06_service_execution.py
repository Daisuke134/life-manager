"""Digital-environment contracts. These tests do NOT establish human benefit."""
import copy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServiceExecutionTests(unittest.TestCase):
    def module(self):
        path = ROOT / 'manager_core/digital_environment.py'
        self.assertTrue(path.exists(), 'digital environment integration is not implemented')
        spec = importlib.util.spec_from_file_location('digital_environment', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def catalog(self):
        p = ROOT / 'public_goods/service/catalog.json'
        self.assertTrue(p.exists(), 'official resource catalog is missing')
        return json.loads(p.read_text())

    def test_same_renderer_builds_three_domains_and_control(self):
        m = self.module()
        catalog = self.catalog()
        with TemporaryDirectory() as tmp:
            manifest = m.build_site(catalog, Path(tmp), 'a' * 40)
            for name in ('index.html', 'finance.html', 'mental.html', 'physical.html', 'control.html', 'proof.html', 'manifest.json'):
                self.assertTrue((Path(tmp) / name).exists(), name)
            self.assertEqual(manifest['beneficiary_outcome'], 'NOT_MEASURED')
            self.assertEqual(manifest['real_participants'], 0)
            self.assertFalse(manifest['clinical_claim'])
            self.assertEqual(manifest['source_commit'], 'a' * 40)
            self.assertEqual(len(manifest['files']), 6)
            for filename, digest in manifest['files'].items():
                import hashlib
                self.assertEqual(hashlib.sha256((Path(tmp)/filename).read_bytes()).hexdigest(), digest)

    def test_no_tracking_forms_remote_scripts_or_model_personalization(self):
        m = self.module()
        with TemporaryDirectory() as tmp:
            m.build_site(self.catalog(), Path(tmp), 'b' * 40)
            for path in Path(tmp).glob('*.html'):
                html = path.read_text().lower()
                for forbidden in ('<script', '<form', 'localstorage', 'googletagmanager', 'facebook.com/tr', 'api_key'):
                    self.assertNotIn(forbidden, html, path.name)
                self.assertIn('no-referrer', html)
                self.assertIn('not_measured', html)

    def test_rejects_credentials_lookalike_hosts_unreviewed_sources_and_future_dates(self):
        m = self.module()
        for bad in ('https://www.mhlw.go.jp.evil.test/x', 'http://www.mhlw.go.jp/x', 'https://u:p@www.mhlw.go.jp/x', 'https://127.0.0.1/x', 'https://www.mhlw.go.jp:8443/x'):
            c = self.catalog()
            c['resources'][0]['url'] = bad
            with self.subTest(url=bad), self.assertRaises(ValueError):
                m.validate_catalog(c)
        c = self.catalog()
        c['resources'][0]['reviewed_on'] = '2999-01-01'
        with self.assertRaises(ValueError): m.validate_catalog(c)
        c = self.catalog()
        c['resources'][0]['rights'] = 'UNKNOWN'
        with self.assertRaises(ValueError): m.validate_catalog(c)

    def test_escapes_provider_text_and_never_accepts_new_fields(self):
        m = self.module()
        c = self.catalog()
        c['resources'][0]['title'] = '<img src=x onerror=alert(1)>'
        with TemporaryDirectory() as tmp:
            m.build_site(c, Path(tmp), 'a' * 40)
            s = (Path(tmp)/'finance.html').read_text()
            self.assertNotIn('<img src=x', s)
            self.assertIn('&lt;img', s)
        c['resources'][0]['email'] = 'private@example.com'
        with self.assertRaises(ValueError): m.validate_catalog(c)

    def test_release_cannot_replace_another_product_or_change_validated_files(self):
        m = self.module()
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = m.build_site(self.catalog(), out, 'a' * 40)
            self.assertTrue(m.verify_bundle(out, manifest))
            (out/'finance.html').write_text('tampered')
            with self.assertRaises(ValueError): m.verify_bundle(out, manifest)
        self.assertEqual(m.PUBLISH_PREFIX, 'manager-support/')
        self.assertFalse(m.permitted_publish_path('index.html'))
        self.assertFalse(m.permitted_publish_path('articles/index.html'))
        self.assertFalse(m.permitted_publish_path('manager-support/../index.html'))
        self.assertFalse(m.permitted_publish_path('manager-support/.github/workflows/x.yml'))
        self.assertTrue(m.permitted_publish_path('manager-support/finance.html'))

    def test_readback_rejects_missing_hash_and_never_infers_welfare(self):
        m = self.module()
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = m.build_site(self.catalog(), out, 'a' * 40)
            bodies = {name: (out/name).read_bytes() for name in manifest['files']}
            result = m.verify_readback(manifest, bodies)
            self.assertEqual(result['delivery'], 'VERIFIED_BYTES_ONLY')
            self.assertEqual(result['beneficiary_outcome'], 'NOT_MEASURED')
            self.assertFalse(result['causal_effect_verified'])
            bodies.pop('mental.html')
            with self.assertRaises(ValueError): m.verify_readback(manifest, bodies)

    def test_reuses_existing_proof_ladder_without_live_write_flags(self):
        m = self.module()
        import inspect
        self.assertIn('outcome_ladder', inspect.getsource(m))
        from manager_core.config import DEFAULTS
        self.assertFalse(DEFAULTS.money_transfer)
        self.assertFalse(DEFAULTS.physical_actuation)
        self.assertFalse(DEFAULTS.private_person_data)

    def test_no_outcomes_returns_missing_not_zero_or_inconclusive_rct(self):
        m = self.module()
        result = m.assess_outcomes(None)
        self.assertEqual(result['status'], 'NOT_MEASURED')
        self.assertIsNone(result['effect'])
        self.assertIsNone(result['n'])
        for invented in ({'n': 0, 'effect': 100}, {'n': 50, 'effect': 12, 'basis': 'synthetic'}, {'basis': 'site_clicks'}):
            self.assertNotEqual(m.assess_outcomes(invented)['status'], 'CAUSAL_BENEFIT')


if __name__ == '__main__':
    unittest.main()
