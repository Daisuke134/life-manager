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
from manager_core.candidate_verification import TechnicalCriteria,verify_candidate

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


if __name__=='__main__':unittest.main()
