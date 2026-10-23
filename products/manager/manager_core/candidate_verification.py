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
from .digital_handoff import digest,_manifest,ALLOWED_PATHS,PUBLIC_BASE
from .collaboration import _strict_pairs,_no_nonfinite_constant

POLICY="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
_SOURCE_LINK=re.compile(re.escape(SOURCE_REPO)+r'/tree/[0-9a-f]{40}/products/manager')
CURRENT_PAGE_VERSION='owned-digital-technical-v2'
CURRENT_PAGE_W3C_URL='https://www.w3.org/TR/wai-aria-1.2/#aria-current'
_CURRENT_PAGE_TARGETS=frozenset({'finance.html','mental.html'})
_CURRENT_PAGE_NAV_HREFS=('index.html','finance.html','mental.html','physical.html','proof.html')
_CURRENT_PAGE_NAV_START=re.compile(
    r'<a href="(index\.html|finance\.html|mental\.html|physical\.html|proof\.html)"'
    r'(?: aria-current="page")?>\Z'
)


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
class CurrentPageCriteria:
    """Separate, source-bound criteria for one owned navigation current-page cue."""
    candidate: Candidate
    official_sources: tuple[Source,...]
    w3c_reference_bytes: bytes
    at: datetime
    version: str = CURRENT_PAGE_VERSION

    def __post_init__(self):
        _aware(self.at)
        if type(self.candidate) is not Candidate or self.version!=CURRENT_PAGE_VERSION:
            raise ValueError('typed current-page candidate and versioned criteria required')
        target=self.candidate.target.removeprefix(PUBLISH_PREFIX)
        if (self.candidate.target!=PUBLISH_PREFIX+target or target not in _CURRENT_PAGE_TARGETS
                or self.candidate.action!='ADD_CURRENT_PAGE_CUE'
                or self.candidate.technical_criterion!='current_page_navigation_cue'):
            raise ValueError('current-page cue criteria outside exact owned target')
        if type(self.official_sources) is not tuple or len(self.official_sources)!=2 or any(
                type(source) is not Source for source in self.official_sources):
            raise ValueError('owned baseline and W3C primary sources required')
        baseline,reference=self.official_sources
        if ((baseline.source_id,baseline.url)!=(f'owned-baseline:{target}',PUBLIC_BASE+target)
                or (reference.source_id,reference.url)!=('w3c:aria-current-1.2',CURRENT_PAGE_W3C_URL)
                or self.candidate.source_refs!=(baseline.source_id,reference.source_id)):
            raise ValueError('current-page source identities must bind the owned GET and W3C definition')
        if (type(self.w3c_reference_bytes) is not bytes or not self.w3c_reference_bytes
                or len(self.w3c_reference_bytes)>2*1024*1024):
            raise ValueError('bounded primary W3C source bytes required')
        reference.verify_content(self.w3c_reference_bytes)
        lowered=self.w3c_reference_bytes.lower()
        if b'aria-current' not in lowered or b'page' not in lowered:
            raise ValueError('W3C source does not contain the cited current-page definition')


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


class _CurrentNavigation(HTMLParser):
    """Recognize only the one fixed header navigation self-link shape."""
    _VOID=frozenset({'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'})

    def __init__(self,target):
        super().__init__(convert_charrefs=True)
        self.target=target
        self.htmls=self.html_ends=self.bodies=self.body_ends=0
        self.headers=self.header_ends=self.navs=self.nav_ends=0
        self.header_depth=self.nav_depth=0
        self.header_navs=[]
        self.self_links=[]
        self.current=[]
        self.nav_hrefs=[]
        self.nav_anchor_text=[]
        self.nav_shape_valid=True
        self.duplicate_attributes=False
        self.malformed=False
        self.structure=[]
        self.text=''

    def handle_starttag(self,tag,attrs):
        parent=self.structure[-1] if self.structure else None
        counts={}
        for key,_ in attrs:counts[key]=counts.get(key,0)+1
        if any(count>1 for count in counts.values()):self.duplicate_attributes=True
        values={key:value for key,value in attrs}
        if 'aria-current' in counts:self.current.append((tag,values.get('aria-current'),self.nav_depth>0))
        if self.nav_depth:
            if parent!='nav' or tag!='a':
                self.nav_shape_valid=False
            else:
                raw=self.get_starttag_text() or ''
                match=_CURRENT_PAGE_NAV_START.fullmatch(raw)
                if match is None:
                    self.nav_shape_valid=False
                    self.nav_hrefs.append('')
                else:
                    self.nav_hrefs.append(match.group(1))
                self.nav_anchor_text.append('')
        if tag not in self._VOID:self.structure.append(tag)
        if tag=='html':
            self.htmls+=1
            if parent is not None:self.nav_shape_valid=False
        if tag=='body':
            self.bodies+=1
            if parent!='html':self.nav_shape_valid=False
        if tag=='header':
            self.headers+=1
            if parent!='body':self.nav_shape_valid=False
            self.header_depth+=1
        if tag=='nav':
            self.navs+=1
            if parent!='header':self.nav_shape_valid=False
            if self.header_depth:
                self.header_navs.append(tuple(attrs))
            if self.nav_depth:
                self.malformed=True
            self.nav_depth+=1
        if tag=='a' and self.nav_depth:
            hrefs=[value for key,value in attrs if key=='href']
            if hrefs and self.target in hrefs:
                line,column=self.getpos()
                lines=self.text.splitlines(keepends=True)
                offset=sum(len(part) for part in lines[:line-1])+column
                self.self_links.append((tuple(attrs),self.get_starttag_text(),offset))

    def handle_data(self,data):
        if not self.nav_depth:return
        if self.structure and self.structure[-1]=='a' and self.nav_anchor_text:
            self.nav_anchor_text[-1]+=data
        elif data.strip():
            self.nav_shape_valid=False

    def handle_comment(self,data):
        if self.nav_depth:self.nav_shape_valid=False

    def handle_endtag(self,tag):
        if not self.structure or self.structure[-1]!=tag:
            self.malformed=True
        else:
            self.structure.pop()
        if tag=='nav':
            self.nav_ends+=1
            self.nav_depth-=1
            if self.nav_depth<0:self.malformed=True
        if tag=='body':self.body_ends+=1
        if tag=='html':self.html_ends+=1
        if tag=='header':
            self.header_ends+=1
            self.header_depth-=1
            if self.header_depth<0:self.malformed=True

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self._VOID:self.handle_endtag(tag)


def _current_navigation(body,target):
    """Return MISSING, CURRENT, or INVALID for the exact owned header nav item."""
    if (type(body) is not bytes or target not in _CURRENT_PAGE_TARGETS):return 'INVALID',None
    try:
        text=body.decode('utf-8')
        parser=_CurrentNavigation(target)
        parser.text=text
        parser.feed(text)
        parser.close()
    except (UnicodeError,ValueError):
        return 'INVALID',None
    if (parser.malformed or parser.structure or parser.duplicate_attributes or not parser.nav_shape_valid
            or parser.nav_hrefs!=list(_CURRENT_PAGE_NAV_HREFS)
            or len(parser.nav_anchor_text)!=len(_CURRENT_PAGE_NAV_HREFS)
            or any(not label.strip() for label in parser.nav_anchor_text)
            or parser.htmls!=1 or parser.html_ends!=1 or parser.bodies!=1 or parser.body_ends!=1
            or parser.headers!=1 or parser.header_ends!=1
            or parser.navs!=1 or parser.nav_ends!=1 or parser.header_depth!=0 or parser.nav_depth!=0
            or len(parser.header_navs)!=1 or len(parser.self_links)!=1):
        return 'INVALID',None
    nav_attrs=parser.header_navs[0]
    if nav_attrs!=(('aria-label','主な案内'),):return 'INVALID',None
    attrs,raw,offset=parser.self_links[0]
    hrefs=[value for key,value in attrs if key=='href']
    currents=[value for key,value in attrs if key=='aria-current']
    if hrefs!=[target] or not raw or not raw.lower().startswith('<a ') or raw.endswith('/>'):
        return 'INVALID',None
    if not currents and not parser.current:return 'MISSING',(text,raw,offset)
    if (len(currents)==1 and currents[0]=='page' and len(parser.current)==1
            and parser.current[0][0]=='a' and parser.current[0][2]):
        return 'CURRENT',(text,raw,offset)
    return 'INVALID',None


def add_current_page_cue(body,target):
    status,location=_current_navigation(body,target)
    if status!='MISSING' or location is None:raise ValueError('current-page self-link is not uniquely eligible')
    text,raw,offset=location
    if text[offset:offset+len(raw)]!=raw:raise ValueError('current-page start tag position changed')
    updated=raw[:-1]+' aria-current="page">'
    return (text[:offset]+updated+text[offset+len(raw):]).encode('utf-8')


def _load(site):
    site=Path(site)
    manifest=json.loads((site/'manifest.json').read_text(),object_pairs_hook=_strict_pairs,parse_constant=_no_nonfinite_constant)
    manifest=_manifest(manifest);verify_bundle(site,manifest)
    bodies={name:(site/name).read_bytes() for name in PAGES}
    return manifest,bodies


def _normalized(body):return _SOURCE_LINK.sub('<OWNED_SOURCE_REVISION>',body.decode('utf-8'))


def _verify_current_page_candidate(baseline_bundle,candidate_bundle,criteria):
    c=criteria.candidate;before_hash=after_hash='';changed=()
    def result(status,*reasons):
        return TechnicalAssessment(status,c.candidate_id,before_hash,after_hash,changed,c.source_refs,
                                   criteria.version,tuple(reasons))
    try:
        before,old=_load(baseline_bundle);after,new=_load(candidate_bundle)
        before_hash=digest(before);after_hash=digest(after)
        target=c.target.removeprefix(PUBLISH_PREFIX)
        if c.target!=PUBLISH_PREFIX+target or target not in _CURRENT_PAGE_TARGETS:
            return result('DENIED','TARGET_SCOPE')
        sources={source.source_id:source for source in criteria.official_sources}
        if (len(sources)!=2
                or c.source_refs!=tuple(source.source_id for source in criteria.official_sources)):
            return result('DENIED','SOURCE_IDENTITY')
        baseline,reference=criteria.official_sources
        if ((baseline.source_id,baseline.url)!=(f'owned-baseline:{target}',PUBLIC_BASE+target)
                or (reference.source_id,reference.url)!=('w3c:aria-current-1.2',CURRENT_PAGE_W3C_URL)):
            return result('DENIED','SOURCE_IDENTITY')
        baseline.verify_content(old[target])
        reference.verify_content(criteria.w3c_reference_bytes)
        for source in criteria.official_sources:source.require_fresh(criteria.at,48)
        if before==after:return result('NO_ACTION','UNCHANGED_BUNDLE')
        changed=tuple(sorted([PUBLISH_PREFIX+n for n in PAGES if old[n]!=new[n]]+['manager-support/manifest.json']))
        if not set(changed)<=set(ALLOWED_PATHS):return result('DENIED','UNRELATED_PATH')
        expected_source=f'{SOURCE_REPO}/tree/{after["source_commit"]}/products/manager'
        for name,body in new.items():
            text=body.decode('utf-8');safety=_Safety();safety.feed(text)
            if not safety.safe or not safety.csp or set(_SOURCE_LINK.findall(text))!={expected_source}:
                return result('DENIED','UNSAFE_OR_MISIDENTIFIED_PAGE')
            if name!=target and _normalized(body)!=_normalized(old[name]):
                return result('DENIED','UNRELATED_ROUTE_CHANGE')
        before_state,_=_current_navigation(old[target],target)
        after_state,_=_current_navigation(new[target],target)
        if before_state!='MISSING' or after_state!='CURRENT':
            return result('DENIED','CURRENT_PAGE_MARKUP_AMBIGUOUS')
        expected=add_current_page_cue(old[target],target)
        if _normalized(new[target])!=_normalized(expected):
            return result('DENIED','UNPLANNED_CONTENT_CHANGE')
        return result('VERIFIED_TECHNICAL','EXACT_CURRENT_PAGE_CUE')
    except (ValueError,TypeError,KeyError,OSError,UnicodeError):
        return result('DENIED','INVALID_BUNDLE_OR_CRITERIA')


def verify_candidate(baseline_bundle,candidate_bundle,criteria: TechnicalCriteria | CurrentPageCriteria) -> TechnicalAssessment:
    if type(criteria) is CurrentPageCriteria:
        return _verify_current_page_candidate(baseline_bundle,candidate_bundle,criteria)
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
