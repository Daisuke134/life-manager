"""Scoped Pages release is additive, same bundle for all domains, never broad access."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from phase06_fixed_clock import FixedReviewDate
ROOT=Path(__file__).resolve().parents[1]

class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        from manager_core import digital_environment
        clock=patch.object(digital_environment,'datetime',FixedReviewDate)
        clock.start();self.addCleanup(clock.stop)

    def load(self):
        p=ROOT/'scripts/phase06_release_guard.py'
        self.assertTrue(p.exists(),'verified scoped publisher is not implemented')
        spec=importlib.util.spec_from_file_location('release_guard',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def fixture(self,root):
        from manager_core.digital_environment import build_site
        site=root/'site';checkout=root/'pages';checkout.mkdir()
        (checkout/'index.html').write_text('OTHER PRODUCT - NEVER REPLACE')
        (checkout/'articles').mkdir()
        (checkout/'articles/existing.html').write_text('PRESERVE EXACT BYTES')
        c=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
        manifest=build_site(c,site,'a'*40)
        audit={'sources':[{'id':r['id'],'url':r['url'],'status':'REACHABLE_NOT_OUTCOME','http_status':200,'sha256':'f'*64} for r in c['resources']],'content_rights':'LINK_ONLY','human_outcome':'NOT_MEASURED'}
        return site,checkout,manifest,audit

    def test_additive_stage_preserves_unrelated_site_and_repeat_is_no_action(self):
        m=self.load()
        with TemporaryDirectory() as t:
            site,checkout,manifest,audit=self.fixture(Path(t))
            first=m.stage_release(site,checkout,audit)
            self.assertEqual(first['status'],'STAGED_MANAGER_ONLY')
            self.assertEqual(len(first['changed_files']),7)
            self.assertEqual((checkout/'index.html').read_text(),'OTHER PRODUCT - NEVER REPLACE')
            self.assertEqual((checkout/'articles/existing.html').read_text(),'PRESERVE EXACT BYTES')
            second=m.stage_release(site,checkout,audit)
            self.assertEqual(second['status'],'NO_ACTION');self.assertEqual(second['changed_files'],[])

    def test_missing_or_unreachable_official_source_does_not_publish(self):
        m=self.load()
        for mutation in ('missing','unknown','wrong_source'):
            with TemporaryDirectory() as t:
                site,checkout,manifest,audit=self.fixture(Path(t))
                if mutation=='missing':audit['sources'].pop()
                if mutation=='unknown':audit['sources'][0]['status']='UNKNOWN'
                if mutation=='wrong_source':audit['sources'][0]['url']='https://attacker.test/'
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):m.stage_release(site,checkout,audit)
                self.assertFalse((checkout/'manager-support').exists())

    def test_symlink_target_or_unexpected_existing_files_rejected(self):
        m=self.load()
        with TemporaryDirectory() as t:
            site,checkout,manifest,audit=self.fixture(Path(t))
            (checkout/'manager-support').symlink_to(checkout/'articles',target_is_directory=True)
            with self.assertRaises(ValueError):m.stage_release(site,checkout,audit)
            self.assertEqual((checkout/'articles/existing.html').read_text(),'PRESERVE EXACT BYTES')
        with TemporaryDirectory() as t:
            site,checkout,manifest,audit=self.fixture(Path(t))
            (checkout/'manager-support').mkdir()
            (checkout/'manager-support/owned-by-someone-else.html').write_text('do not delete')
            with self.assertRaises(ValueError):m.stage_release(site,checkout,audit)

    def test_target_source_mismatch_or_tamper_cannot_enter_release(self):
        m=self.load()
        with TemporaryDirectory() as t:
            site,checkout,manifest,audit=self.fixture(Path(t))
            (site/'index.html').write_text('tampered')
            with self.assertRaises(ValueError):m.stage_release(site,checkout,audit)
            self.assertFalse((checkout/'manager-support').exists())

if __name__=='__main__':unittest.main()
