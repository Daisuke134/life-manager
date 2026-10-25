"""Regressions raised by independent review; no production safety gate relaxed."""
from datetime import datetime as RealDatetime, timezone
import importlib.util
import inspect
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]

class LaterUtc(RealDatetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2030,1,1,tzinfo=timezone.utc)

class ReviewRegressions(unittest.TestCase):
    def test_one_existing_pages_deployment_authority_not_stale_full_site_upload(self):
        workflow=(ROOT.parents[1]/'.github/workflows/manager-phase06-service.yml').read_text()
        self.assertNotIn('uses: actions/deploy-pages@',workflow)
        self.assertNotIn('uses: actions/upload-pages-artifact@',workflow)
        self.assertIn('307239134',workflow)
        self.assertIn('workflow_dispatch',workflow)
        self.assertIn('actions: write',workflow)
        self.assertIn('verify-live',workflow)
        self.assertIn('git push origin HEAD:gh-pages',workflow)
        self.assertNotIn('git push --force',workflow)

    def test_main_publisher_is_dispatch_only_and_requires_owner_bound_request(self):
        workflow=(ROOT.parents[1]/'.github/workflows/manager-phase06-service.yml').read_text()
        self.assertIn('owned_request:',workflow)
        self.assertIn('request_id:',workflow)
        self.assertIn('run-name: Manager owned request ${{ inputs.request_id',workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'",workflow)
        self.assertIn("github.ref == 'refs/heads/main'",workflow)
        self.assertIn('--owned-request',workflow)
        self.assertIn('MANAGER_OWNER_ID',workflow)
        self.assertIn('secrets.MANAGER_RELEASE_ENABLED',workflow)
        self.assertIn("refs/heads/research/manager-product-r006-20261020",workflow)
        self.assertIn('path: source\n          persist-credentials: false',workflow)

    def test_fixture_suite_works_in_2030_while_production_stale_catalog_is_rejected(self):
        from manager_core import digital_environment as impl
        import json
        catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
        with patch.object(impl,'datetime',LaterUtc):
            with self.assertRaises(ValueError): impl.validate_catalog(catalog)
        for name in ('test_phase06_service_execution','test_phase06_release_guard'):
            path=ROOT/'tests'/f'{name}.py'
            spec=importlib.util.spec_from_file_location(name+'_clock_regression',path)
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            suite=unittest.defaultTestLoader.loadTestsFromModule(mod)
            result=unittest.TestResult()
            with patch.object(impl,'datetime',LaterUtc):
                suite.run(result)
            self.assertTrue(result.wasSuccessful(),f'{name}: {result.failures!r} {result.errors!r}')

if __name__=='__main__': unittest.main()
