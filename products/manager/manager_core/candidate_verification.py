"""Exact bounded HTML transformations before the original publisher's gates.

This verifies static technical criteria, not remote source truth, a complete WCAG
certificate, authenticated execution authority or human benefit. Existing browser
and live-source-audit release gates remain mandatory for external publication.
"""
from dataclasses import dataclass,field
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from .models.intervention import Candidate
from .models.source import Source,_aware
from .digital_environment import PAGES,PUBLISH_PREFIX,SOURCE_REPO,verify_bundle,_url
from .digital_handoff import digest,_manifest,ALLOWED_PATHS
from .collaboration import _strict_pairs,_no_nonfinite_constant

POLICY="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
_SOURCE_LINK=re.compile(re.escape(SOURCE_REPO)+r'/tree/[0-9a-f]{40}/products/manager')


@dataclass(frozen=True)
class TechnicalCriteria:
    candidate: Candidate
    old_link_url: str
    expected_link_url: str
    required_label: str | None
    official_sources: tuple[Source,...]
    at: datetime
    version: str = 'owned-digital-technical-v1'

    def __post_init__(self):
        _aware(self.at)
        if type(self.candidate) is not Candidate or self.version!='owned-digital-technical-v1':
            raise ValueError('typed candidate and versioned criteria required')
        if type(self.official_sources) is not tuple or not self.official_sources:
            raise ValueError('explicit host source bindings required')


@dataclass(frozen=True)
class TechnicalAssessment:
    status: str
    candidate_id: str
    baseline_digest: str
    candidate_digest: str
    changed_paths: tuple[str,...]
    source_refs: tuple[str,...]
    criteria_version: str
    reasons: tuple[str,...]
    proof_level: str = field(default='P0',init=False)
    authorized_execution: bool = field(default=False,init=False)
    human_outcome: str = field(default='NOT_MEASURED',init=False)
    remaining_release_gates: tuple[str,...] = field(default=('BROWSER_CHECKS','FRESH_OFFICIAL_SOURCE_AUDIT','PRIVILEGED_PLATFORM_ADMISSION'),init=False)


class _Safety(HTMLParser):
    def __init__(self):super().__init__();self.safe=True;self.csp=False;self.links=[];self.anchor=None
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag in {'script','iframe','object','embed','form','input','base'}:self.safe=False
        if any(k.lower().startswith('on') for k,v in attrs):self.safe=False
        if values.get('href','').strip().lower().startswith(('javascript:','data:','file:')):self.safe=False
        if tag=='meta' and values.get('http-equiv','').lower()=='refresh':self.safe=False
        if tag=='meta' and values.get('http-equiv','').lower()=='content-security-policy':
            self.csp=values.get('content')==POLICY
        if tag=='a':self.anchor=[values.get('href'),values.get('aria-label') or '',[]]
    def handle_data(self,data):
        if self.anchor is not None:self.anchor[2].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor is not None:
            href,label,text=self.anchor;self.links.append((href,label or ''.join(text).strip()));self.anchor=None


def _load(site):
    site=Path(site)
    manifest=json.loads((site/'manifest.json').read_text(),object_pairs_hook=_strict_pairs,parse_constant=_no_nonfinite_constant)
    manifest=_manifest(manifest);verify_bundle(site,manifest)
    bodies={name:(site/name).read_bytes() for name in PAGES}
    return manifest,bodies


def _normalized(body):return _SOURCE_LINK.sub('<OWNED_SOURCE_REVISION>',body.decode('utf-8'))


def verify_candidate(baseline_bundle,candidate_bundle,criteria: TechnicalCriteria) -> TechnicalAssessment:
    if type(criteria) is not TechnicalCriteria:raise ValueError('typed fixed technical criteria required')
    c=criteria.candidate;before_hash=after_hash='';changed=()
    def result(status,*reasons):
        return TechnicalAssessment(status,c.candidate_id,before_hash,after_hash,changed,c.source_refs,criteria.version,tuple(reasons))
    try:
        before,old=_load(baseline_bundle);after,new=_load(candidate_bundle)
        before_hash=digest(before);after_hash=digest(after)
        if before==after:return result('NO_ACTION','UNCHANGED_BUNDLE')
        changed=tuple(sorted([PUBLISH_PREFIX+n for n in PAGES if old[n]!=new[n]]+['manager-support/manifest.json']))
        if not set(changed)<=set(ALLOWED_PATHS):return result('DENIED','UNRELATED_PATH')
        target=c.target.removeprefix(PUBLISH_PREFIX)
        if c.target!=PUBLISH_PREFIX+target or target not in PAGES:return result('DENIED','TARGET_SCOPE')
        _url(criteria.expected_link_url);_url(criteria.old_link_url)
        sources={s.source_id:s for s in criteria.official_sources if type(s) is Source}
        if (len(sources)!=len(criteria.official_sources) or not set(c.source_refs)<=set(sources)
                or not any(sources[ref].url==criteria.expected_link_url for ref in c.source_refs)):
            return result('DENIED','SOURCE_IDENTITY')
        for s in sources.values():s.require_fresh(criteria.at,48)
        for name,body in new.items():
            text=body.decode('utf-8');safety=_Safety();safety.feed(text)
            expected_source=f'{SOURCE_REPO}/tree/{after["source_commit"]}/products/manager'
            if not safety.safe or not safety.csp or set(_SOURCE_LINK.findall(text))!={expected_source}:
                return result('DENIED','UNSAFE_OR_MISIDENTIFIED_PAGE')
            if name!=target and _normalized(body)!=_normalized(old[name]):return result('DENIED','UNRELATED_ROUTE_CHANGE')
        baseline=_normalized(old[target]);candidate=_normalized(new[target])
        old_href='href="'+escape(criteria.old_link_url,quote=True)+'"'
        new_href='href="'+escape(criteria.expected_link_url,quote=True)+'"'
        if c.action=='CORRECT_LINK':
            if criteria.old_link_url==criteria.expected_link_url or old_href not in baseline:
                return result('NO_ACTION' if baseline==candidate else 'DENIED','NO_TECHNICAL_IMPROVEMENT')
            expected=baseline.replace(old_href,new_href)
        elif c.action=='IMPROVE_ACCESSIBILITY':
            if not criteria.required_label:return result('DENIED','MISSING_REQUIRED_LABEL')
            pattern=r'(<a\b[^>]*\bhref="'+re.escape(escape(criteria.expected_link_url,quote=True))+r'"[^>]*>)\s*</a>'
            expected,count=re.subn(pattern,lambda m:m.group(1)+escape(criteria.required_label)+'</a>',baseline)
            if not count:return result('DENIED','NO_EMPTY_TARGET_LABEL')
        else:return result('NO_ACTION','NON_EXECUTING_CANDIDATE')
        parsed=_Safety();parsed.feed(candidate)
        if not any(href==criteria.expected_link_url and label for href,label in parsed.links):
            return result('DENIED','MISSING_ACCESSIBLE_LABEL')
        if candidate!=expected:return result('DENIED','UNPLANNED_CONTENT_CHANGE')
        return result('VERIFIED_TECHNICAL','EXACT_BOUNDED_TRANSFORMATION')
    except (ValueError,TypeError,KeyError,OSError,UnicodeError):
        return result('DENIED','INVALID_BUNDLE_OR_CRITERIA')
