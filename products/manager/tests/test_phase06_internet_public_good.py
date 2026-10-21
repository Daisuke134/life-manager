"""Phase06 internet-first actual public artifact readback; fail closed on welfare."""
import base64
from datetime import datetime, timezone
from hashlib import sha1, sha256
import json
from pathlib import Path
from urllib.error import HTTPError
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"public_goods/RESOURCE_DIRECTORY_JA.md"
DESIGN=ROOT/"pilot/INTERNET_FIRST_TRIAL_DESIGN.md"
SDK_DEMO=ROOT/"scripts/phase06_growthbook_existing_sdk.py"
BASE_SHA="c16660f9c6d5c1a79a801f0587dc7cc0355df1b3"
NEW_SHA="a"*40
REPO_PATH="products/manager/public_goods/RESOURCE_DIRECTORY_JA.md"

class DummyResponse:
    def __init__(self,data): self.payload=json.dumps(data).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.payload if n<0 else self.payload[:n]


def gitblob(b):
    return sha1(f"blob {len(b)}\\0".encode().replace(b"\\0",b"\0")+b).hexdigest()


def fake_opener(public_bytes, *, change_base=False, forged=False, wrong_path=False):
    def opener(request,timeout=0):
        selfurl=request.full_url
        if request.get_method()!="GET" or "Authorization" in dict(request.header_items()):
            raise AssertionError("only public read-only GET permitted")
        if selfurl.endswith("?ref="+BASE_SHA):
            if change_base:
                return DummyResponse({"content":base64.b64encode(b"already exists").decode(),"encoding":"base64",
                                      "path":REPO_PATH,"sha":gitblob(b"already exists")})
            raise HTTPError(selfurl,404,"absent at baseline",None,None)
        if not selfurl.endswith("?ref="+NEW_SHA):
            raise AssertionError("unexpected request path: "+selfurl)
        b=public_bytes if not forged else b"tampered text"
        path=REPO_PATH if not wrong_path else "wrong/directory.md"
        return DummyResponse({"content":base64.b64encode(b).decode(),"encoding":"base64","size":len(b),
                              "path":path,"sha":gitblob(b)})
    return opener


class PublicInternetFieldContracts(unittest.TestCase):
    def test_real_public_document_uses_only_official_existing_resources(self):
        txt=PUBLIC.read_text(encoding="utf-8")
        for source in ("www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html",
                       "www.fsa.go.jp/policy/kashikin/",
                       "www.mhlw.go.jp/mamorouyokokoro/soudan/",
                       "kennet.mhlw.go.jp/information/information/exercise"):
            self.assertIn(source,txt)
        self.assertIn("NO_ACTION",txt)
        self.assertIn("NOT_MEASURED",txt)
        self.assertNotIn("<form",txt.lower())
        self.assertNotIn("<script",txt.lower())
        self.assertNotIn("個人情報を入力",txt)
        self.assertGreater(len(txt),1200)

    def test_git_hosted_readback_observes_new_public_world_state(self):
        from manager_core.public_good_readback import read_public_artifact
        raw=PUBLIC.read_bytes()
        result=read_public_artifact(head_sha=NEW_SHA,baseline_sha=BASE_SHA,
                                    local_path=PUBLIC,opener=fake_opener(raw))
        self.assertEqual(result.publication_state,"PUBLIC_ARTIFACT_CHANGED")
        self.assertEqual(result.artifact_sha256,sha256(raw).hexdigest())
        self.assertEqual(result.evidence_level,"P2_ARTIFACT_ONLY")
        self.assertEqual(result.beneficiary_outcome,"NOT_MEASURED")
        self.assertFalse(result.causal_net_benefit_verified)
        self.assertIn("api.github.com/repos/Daisuke134/life-manager/contents/",result.public_source_url)
        self.assertNotIn("api_key",repr(result))

    def test_readback_rejects_no_baseline_wrong_path_or_tampered_public_content(self):
        from manager_core.public_good_readback import read_public_artifact,PublicArtifactUnverified
        raw=PUBLIC.read_bytes()
        for flags in ({"change_base":True},{"forged":True},{"wrong_path":True}):
            with self.subTest(**flags),self.assertRaises(PublicArtifactUnverified):
                read_public_artifact(head_sha=NEW_SHA,baseline_sha=BASE_SHA,
                                     local_path=PUBLIC,opener=fake_opener(raw,**flags))
        for ref in ("main","../users","short",""):
            with self.subTest(ref=ref),self.assertRaises(ValueError):
                read_public_artifact(head_sha=ref,baseline_sha=BASE_SHA,
                                     local_path=PUBLIC,opener=fake_opener(raw))

    def test_external_network_errors_are_unknown_not_impact(self):
        from manager_core.public_good_readback import read_public_artifact,PublicArtifactUnverified
        def unavailable(req,timeout=0): raise TimeoutError("not available")
        with self.assertRaises(PublicArtifactUnverified):
            read_public_artifact(head_sha=NEW_SHA,baseline_sha=BASE_SHA,local_path=PUBLIC,
                                 opener=unavailable)

    def test_trial_design_does_not_fabricate_users_or_welfare(self):
        content=DESIGN.read_text(encoding="utf-8")
        for key in ("GrowthBook","NO_ACTION","MENTAL","PHYSICAL","FINANCIAL",
                    "NOT_MEASURED","CFPB","WHO","Playwright","DoWhy",
                    "voluntary","P2_ARTIFACT_ONLY"):
            self.assertIn(key,content)
        self.assertNotIn("randomized field improvement confirmed",content.lower())
        demo=SDK_DEMO.read_text(encoding="utf-8")
        self.assertIn("from growthbook import",demo)
        self.assertIn("synthetic",demo.lower())
        self.assertNotIn("requests.post",demo)
        self.assertNotIn("api_key",demo.lower())

    def test_existing_canonical_113_tasks_and_runtime_are_preserved(self):
        tasks=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(tasks),113)
        self.assertEqual({t["id"]:t["status"] for t in tasks}["F004"],"blocked")
        self.assertEqual({t["id"]:t["status"] for t in tasks}["F007"],"blocked")
        from manager_core.config import DEFAULTS
        self.assertFalse(DEFAULTS.public_posting)
        self.assertFalse(DEFAULTS.money_transfer)
        self.assertFalse(DEFAULTS.physical_actuation)


if __name__=="__main__":
    unittest.main()
