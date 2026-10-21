"""Read-only independent PUBLIC GitHub API readback of an owned online artifact.

This observes existence/change of a public file between an immutable
pre-publication commit and the published HEAD, not a causal human outcome.
No authentication, private data, publishing, or money operations.
"""
from __future__ import annotations
from dataclasses import dataclass
import base64
from hashlib import sha1,sha256
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request,urlopen

FILE_PATH="products/manager/public_goods/RESOURCE_DIRECTORY_JA.md"
API_ROOT="https://api.github.com/repos/Daisuke134/life-manager/contents/"
LOCAL_PATH=Path(__file__).resolve().parents[1]/"public_goods/RESOURCE_DIRECTORY_JA.md"


class PublicArtifactUnverified(ValueError):
    """External public observation cannot substantiate the asserted artifact."""


@dataclass(frozen=True)
class PublicArtifactEvidence:
    publication_state: str
    artifact_sha256: str
    public_source_url: str
    baseline_source_url: str
    evidence_level: str = "P2_ARTIFACT_ONLY"
    beneficiary_outcome: str = "NOT_MEASURED"
    causal_net_benefit_verified: bool = False


def _read_api(url, opener, *, allow_404=False):
    request=Request(url,headers={"Accept":"application/vnd.github+json",
                                 "User-Agent":"Manager-Public-Goods-Readback/0.1"},method="GET")
    try:
        with opener(request,timeout=15) as response:
            raw=response.read(131073)
    except HTTPError as exc:
        if allow_404 and exc.code==404:
            return None
        raise PublicArtifactUnverified("public artifact API HTTP error") from None
    except Exception:
        raise PublicArtifactUnverified("public artifact provider UNKNOWN") from None
    if not isinstance(raw,bytes) or len(raw)>131072:
        raise PublicArtifactUnverified("unexpected public response size")
    try:
        payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        raise PublicArtifactUnverified("invalid public content response") from None
    if not isinstance(payload,dict):
        raise PublicArtifactUnverified("untrusted public response")
    return payload


def read_public_artifact(*,head_sha:str,baseline_sha:str,
                         local_path:Path=LOCAL_PATH,opener=None) -> PublicArtifactEvidence:
    for ref in (head_sha,baseline_sha):
        if type(ref) is not str or re.fullmatch("[0-9a-f]{40}",ref) is None:
            raise ValueError("immutable 40-digit lowercase public git ref required")
    if head_sha==baseline_sha or Path(local_path).resolve()!=LOCAL_PATH.resolve():
        raise ValueError("only expected public asset with differing baseline/head can be observed")
    current=API_ROOT+FILE_PATH+"?ref="+head_sha
    baseline=API_ROOT+FILE_PATH+"?ref="+baseline_sha
    resolver=opener if opener is not None else urlopen
    previously=_read_api(baseline,resolver,allow_404=True)
    if previously is not None:
        raise PublicArtifactUnverified("source already present in asserted prepublication baseline")
    record=_read_api(current,resolver)
    if record.get("path")!=FILE_PATH or record.get("encoding")!="base64":
        raise PublicArtifactUnverified("public response path or encoding mismatch")
    try:
        value=record["content"]
        if not isinstance(value,str):
            raise ValueError("nonstring content")
        public_bytes=base64.b64decode("".join(value.split()),validate=True)
        local_bytes=Path(local_path).read_bytes()
        if (record.get("size")!=len(public_bytes)
            or sha256(public_bytes).digest()!=sha256(local_bytes).digest()):
            raise ValueError("public bytes differ from verified local owned artifact")
        git_blob=sha1(b"blob "+str(len(public_bytes)).encode()+b"\x00"+public_bytes).hexdigest()
        if record.get("sha")!=git_blob:
            raise ValueError("GitHub public Git blob hash mismatch")
    except (KeyError,TypeError,ValueError,OSError):
        raise PublicArtifactUnverified("public artifact content does not match checked-out source") from None
    return PublicArtifactEvidence(
        publication_state="PUBLIC_ARTIFACT_CHANGED",
        artifact_sha256=sha256(public_bytes).hexdigest(),
        public_source_url=current,baseline_source_url=baseline,
    )
