"""Exact bounded candidate transformation plus existing release-bundle checks."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from manager_core.digital_environment import build_site
from manager_core.models.source import Source
from manager_core.models.intervention import Candidate
from manager_core.candidate_verification import CurrentPageCriteria,TechnicalCriteria,verify_candidate

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)
NEW='https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html'
OLD='https://www.mhlw.go.jp/obsolete-manager-fixture-route'


def mutate(site,name,change):
    p=site/name;p.write_bytes(change(p.read_bytes()))
    mp=site/'manifest.json';m=json.loads(mp.read_text());m['files'][name]=sha256(p.read_bytes()).hexdigest();mp.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')


def setup(root):
    catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
    before=root/'before';after=root/'after'
    build_site(catalog,before,'a'*40);build_site(catalog,after,'b'*40)
    mutate(before,'finance.html',lambda x:x.replace(NEW.encode(),OLD.encode(),1))
    source=Source('current-citation',NEW,'Government standard terms','allowed_with_conditions','a'*64,NOW,'public_nonpersonal')
    candidate=Candidate('fix-link','CORRECT_LINK','manager-support/finance.html',('current-citation',),'verified_official_link_target')
    criteria=TechnicalCriteria(candidate,OLD,NEW,None,(source,),NOW)
    return before,after,criteria


def setup_current_page(root):
    catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
    before=root/'current-before';after=root/'current-after'
    build_site(catalog,before,'a'*40);build_site(catalog,after,'b'*40)
    mutate(after,'finance.html',lambda body:body.replace(
        b'<a href="finance.html">',b'<a href="finance.html" aria-current="page">',1))
    baseline_bytes=(before/'finance.html').read_bytes()
    reference_bytes=(
        b'<p>aria-current identifies the current item in a related set. '
        b'The page token indicates the current page; one item should be current.</p>'
    )
    from manager_core.digital_handoff import PUBLIC_BASE
    baseline=Source('owned-baseline:finance.html',PUBLIC_BASE+'finance.html','Owned public baseline',
                    'allowed_with_conditions',sha256(baseline_bytes).hexdigest(),NOW,'public_nonpersonal')
    reference=Source('w3c:aria-current-1.2','https://www.w3.org/TR/wai-aria-1.2/#aria-current',
                     'W3C WAI-ARIA 1.2', 'allowed_with_conditions',
                     sha256(reference_bytes).hexdigest(),NOW,'public_nonpersonal')
    candidate=Candidate('current-page-finance','ADD_CURRENT_PAGE_CUE','manager-support/finance.html',
                        (baseline.source_id,reference.source_id),'current_page_navigation_cue')
    criteria=CurrentPageCriteria(candidate,(baseline,reference),reference_bytes,NOW)
    return before,after,criteria


class CandidateVerificationTests(unittest.TestCase):
    def test_verified_link_correction_and_hashes(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));r=verify_candidate(a,b,c)
            self.assertEqual(r.status,'VERIFIED_TECHNICAL')
            self.assertEqual(r.candidate_id,c.candidate.candidate_id)
            self.assertFalse(r.authorized_execution)

    def test_broken_official_link_denied(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));mutate(b,'finance.html',lambda x:x.replace(NEW.encode(),b'https://www.mhlw.go.jp/other-wrong-route',1))
            self.assertEqual(verify_candidate(a,b,c).status,'DENIED')

    def test_missing_label_denied(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp))
            import re
            mutate(b,'finance.html',lambda x:re.sub(b'(<a data-official href="'+re.escape(NEW.encode())+b'"[^>]*>)[^<]+',rb'\1',x,count=1))
            self.assertEqual(verify_candidate(a,b,c).status,'DENIED')

    def test_removed_unrelated_route_denied(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));mutate(b,'mental.html',lambda x:x.replace(b'physical.html',b'removed.html'))
            self.assertEqual(verify_candidate(a,b,c).status,'DENIED')

    def test_injected_script_denied(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));mutate(b,'finance.html',lambda x:x+b'<script>alert(1)</script>')
            self.assertEqual(verify_candidate(a,b,c).status,'DENIED')

    def test_misidentified_source_denied(self):
        from dataclasses import replace
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));wrong=replace(c.official_sources[0],source_id='another-source')
            self.assertEqual(verify_candidate(a,b,replace(c,official_sources=(wrong,))).status,'DENIED')

    def test_uncited_extra_source_cannot_bless_destination(self):
        from dataclasses import replace
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp))
            cited=replace(c.official_sources[0],url='https://www.fsa.go.jp/policy/kashikin/')
            uncited=replace(c.official_sources[0],source_id='uncited')
            self.assertEqual(verify_candidate(a,b,replace(c,official_sources=(cited,uncited))).status,'DENIED')

    def test_accessibility_candidate_restores_empty_target_name(self):
        from dataclasses import replace
        import re
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp))
            # Restore the current URL, then remove only its accessible text in baseline.
            mutate(a,'finance.html',lambda x:x.replace(OLD.encode(),NEW.encode(),1))
            match=re.search(rb'(<a data-official href="'+re.escape(NEW.encode())+rb'"[^>]*>)([^<]+)</a>',(a/'finance.html').read_bytes())
            label=match.group(2).decode()
            mutate(a,'finance.html',lambda x:x.replace(match.group(0),match.group(1)+b'</a>',1))
            candidate=replace(c.candidate,action='IMPROVE_ACCESSIBILITY',technical_criterion='accessible_link_label')
            c=replace(c,candidate=candidate,old_link_url=NEW,required_label=label)
            self.assertEqual(verify_candidate(a,b,c).status,'VERIFIED_TECHNICAL')

    def test_clean_existing_bundle_needs_no_change(self):
        with TemporaryDirectory() as tmp:
            a,b,c=setup(Path(tmp));self.assertEqual(verify_candidate(b,b,c).status,'NO_ACTION')

    def test_current_page_cue_accepts_only_the_exact_header_navigation_self_link_attribute(self):
        with TemporaryDirectory() as tmp:
            before,after,criteria=setup_current_page(Path(tmp))
            result=verify_candidate(before,after,criteria)
            self.assertEqual(result.status,'VERIFIED_TECHNICAL')
            self.assertEqual(result.criteria_version,'owned-digital-technical-v2')
            self.assertEqual(result.changed_paths,tuple(sorted(
                ['manager-support/'+name for name in ('index.html','finance.html','mental.html',
                 'physical.html','control.html','proof.html','manifest.json')]
            )))
            self.assertFalse(result.authorized_execution)
            self.assertEqual(result.human_outcome,'NOT_MEASURED')

    def test_current_page_cue_rejects_unrelated_text_links_attributes_and_other_pages(self):
        mutations={
            'unrelated_attribute': lambda root: mutate(root,'finance.html',
                lambda body:body.replace(b'<main id="main"',b'<main id="main" data-extra="x"',1)),
            'link_text': lambda root: mutate(root,'finance.html',
                lambda body:body.replace('生活費・仕事・借入'.encode(),b'changed navigation text',1)),
            'href': lambda root: mutate(root,'finance.html',
                lambda body:body.replace(b'href="finance.html"',b'href="mental.html"',1)),
            'other_page': lambda root: mutate(root,'mental.html',
                lambda body:body.replace(b'href="physical.html"',b'href="proof.html"',1)),
            'wrong_nav': lambda root: mutate(root,'finance.html',
                lambda body:body.replace('aria-label="主な案内"'.encode(),
                                         'aria-label="別の案内"'.encode(),1)),
            'duplicate_self_link': lambda root: mutate(root,'finance.html',
                lambda body:body.replace(b'</nav>',
                    b'<a href="finance.html">duplicate</a></nav>',1)),
            'wrong_current_value': lambda root: mutate(root,'finance.html',
                lambda body:body.replace(b'aria-current="page"',b'aria-current="step"',1)),
            'duplicate_current_attribute': lambda root: mutate(root,'finance.html',
                lambda body:body.replace(b'aria-current="page"',
                                         b'aria-current="page" aria-current="page"',1)),
        }
        for name,mutate_candidate in mutations.items():
            with self.subTest(name=name),TemporaryDirectory() as tmp:
                before,after,criteria=setup_current_page(Path(tmp))
                mutate_candidate(after)
                self.assertEqual(verify_candidate(before,after,criteria).status,'DENIED')

    def test_current_page_cue_requires_fresh_exact_baseline_and_w3c_source_bindings(self):
        from dataclasses import replace
        with TemporaryDirectory() as tmp:
            before,after,criteria=setup_current_page(Path(tmp))
            wrong_baseline=replace(criteria.official_sources[0],content_sha256='f'*64)
            wrong_criteria=replace(criteria,official_sources=(wrong_baseline,criteria.official_sources[1]))
            self.assertEqual(verify_candidate(before,after,wrong_criteria).status,'DENIED')
            wrong_reference=replace(criteria.official_sources[1],url='https://example.org/aria-current')
            with self.assertRaises(ValueError):
                replace(criteria,official_sources=(criteria.official_sources[0],wrong_reference))
            with self.assertRaises(ValueError):
                replace(criteria,candidate=replace(criteria.candidate,target='manager-support/control.html'))
            self.assertEqual(verify_candidate(before,after,replace(criteria,at=NOW.replace(day=25))).status,'DENIED')


if __name__=='__main__':unittest.main()
