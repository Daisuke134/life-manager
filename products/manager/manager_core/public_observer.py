"""Read-only allowlisted HTTPS acquisition; retrieval is evidence, not authority.

Source rights/privacy are operator-reviewed metadata, not automatically inferred
from HTML. TLS uses the platform trust store and configured proxy. DNS preflight
is not a claim of lower-level address pinning across that proxy.
"""
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
import ipaddress
import re
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .evidence_types import ObservedSnapshot
from .models.source import Source,_aware
from .provider_deadline import provider_deadline


@dataclass(frozen=True)
class PublicSourceSpec:
    source_id: str
    url: str
    license_id: str
    rights: str
    privacy_class: str
    allowed_hosts: frozenset[str]
    expected_sha256: str | None = None
    timeout_seconds: float = 15
    max_bytes: int = 1048576

    def __post_init__(self):
        if (not re.fullmatch(r'[a-z][a-z0-9-]{1,80}',self.source_id)
                or type(self.allowed_hosts) is not frozenset or not self.allowed_hosts
                or any(type(h) is not str or h!=h.lower() for h in self.allowed_hosts)
                or type(self.timeout_seconds) not in (int,float) or not 0<self.timeout_seconds<=15
                or type(self.max_bytes) is not int or not 0<self.max_bytes<=1048576
                or not self.license_id):raise ValueError('bounded reviewed public source spec required')
        if self.expected_sha256 is not None and not re.fullmatch(r'[a-f0-9]{64}',self.expected_sha256):
            raise ValueError('optional expected SHA256 must be exact')


@dataclass(frozen=True)
class HTTPResult:
    status: int
    body: bytes
    headers: dict
    final_url: str


@dataclass(frozen=True)
class FetchFailure:
    code: str


@dataclass(frozen=True)
class FetchedSnapshot:
    """Byte observation plus cache/transport metadata; no P-level promotion."""
    observation: ObservedSnapshot
    body: bytes
    request_url: str
    etag: str | None
    last_modified: str | None
    changed: bool
    transport_scope: str

    def __post_init__(self):
        if type(self.observation) is not ObservedSnapshot:
            raise ValueError('typed observation required')
        self.observation.source.verify_content(self.body)

    @property
    def source(self):return self.observation.source
    @property
    def body_sha256(self):return self.observation.body_sha256
    @property
    def collected_at(self):return self.observation.collected_at


def _resolve(host):
    return tuple({row[4][0] for row in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})


def _validate_url(url,spec,resolver):
    if type(url) is not str or len(url)>2048 or any(ord(c)<33 for c in url):
        raise ValueError('invalid public URL')
    parsed=urlsplit(url)
    if (parsed.scheme!='https' or parsed.hostname not in spec.allowed_hosts
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None,443) or parsed.fragment):
        raise ValueError('unapproved HTTPS destination')
    ips=resolver(parsed.hostname)
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('private, link-local or unknown destination')


def _https_get(*,url,headers,timeout,max_bytes,validate_redirect):
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,hdrs,newurl):
            validate_redirect(newurl)
            return super().redirect_request(req,fp,code,msg,hdrs,newurl)
    opener=build_opener(Redirects())
    try:
        response=opener.open(Request(url,headers=headers),timeout=timeout)
    except HTTPError as exc:
        if exc.code!=304:raise
        response=exc
    with response:
        return HTTPResult(response.code,response.read(max_bytes+1),
                          {k.lower():v for k,v in response.headers.items()},response.geturl())


def fetch_snapshot(spec: PublicSourceSpec,now: datetime,transport=None,*,previous=None,resolver=None):
    if type(spec) is not PublicSourceSpec:raise ValueError('reviewed typed public-source spec required')
    _aware(now)
    if spec.rights!='allowed_with_conditions' or spec.privacy_class!='public_nonpersonal':
        return FetchFailure('RIGHTS_OR_PRIVACY_DENIED')
    if previous is not None and (type(previous) is not FetchedSnapshot
            or previous.request_url!=spec.url or previous.source.source_id!=spec.source_id):
        return FetchFailure('CACHE_IDENTITY_MISMATCH')
    resolver=resolver or _resolve
    try:
        # Same absolute-deadline primitive as E06; no orphan worker/slow stream.
        with provider_deadline(time.monotonic()+spec.timeout_seconds):
            validate=lambda url:_validate_url(url,spec,resolver)
            validate(spec.url)
            headers={'User-Agent':'Manager-public-observer/0.1','Accept':'text/html,text/plain,application/json'}
            if previous is not None:
                if previous.etag:headers['If-None-Match']=previous.etag
                elif previous.last_modified:headers['If-Modified-Since']=previous.last_modified
            if any('\r' in v or '\n' in v for v in headers.values()):return FetchFailure('INVALID_CACHE_HEADER')
            result=(transport or _https_get)(url=spec.url,headers=headers,timeout=spec.timeout_seconds,
                                           max_bytes=spec.max_bytes,validate_redirect=validate)
            if type(result) is not HTTPResult:return FetchFailure('INVALID_RESPONSE')
            validate(result.final_url)
            response_headers={str(k).lower():v for k,v in result.headers.items()}
            for field in ('date','last-modified'):
                if response_headers.get(field):_aware(parsedate_to_datetime(response_headers[field]))
            if result.status==304:
                if previous is None or len(headers)==2:return FetchFailure('NOT_MODIFIED_WITHOUT_CACHE')
                body=previous.body
            elif result.status==200:body=result.body
            else:return FetchFailure('HTTP_STATUS')
            if type(body) is not bytes or not body or len(body)>spec.max_bytes:
                return FetchFailure('EMPTY_OR_OVERSIZE_BODY')
            digest=sha256(body).hexdigest()
            if spec.expected_sha256 is not None and digest!=spec.expected_sha256:
                return FetchFailure('HASH_MISMATCH')
            source=Source(spec.source_id,result.final_url,spec.license_id,spec.rights,digest,now,spec.privacy_class)
            observation=ObservedSnapshot.from_bytes(source,body,now)
            etag=response_headers.get('etag') or (previous.etag if previous and result.status==304 else None)
            modified=response_headers.get('last-modified') or (previous.last_modified if previous and result.status==304 else None)
            return FetchedSnapshot(observation,body,spec.url,etag,modified,
                previous is None or previous.body_sha256!=digest,
                'INJECTED_TRANSPORT_P0' if transport is not None else 'PLATFORM_TLS_HTTPS_READONLY')
    except TimeoutError:return FetchFailure('TIMEOUT')
    except Exception as exc:
        from .ampersand_api import SessionFailure
        return FetchFailure('TIMEOUT' if isinstance(exc,SessionFailure) and 'deadline' in str(exc) else 'FETCH_FAILED')
