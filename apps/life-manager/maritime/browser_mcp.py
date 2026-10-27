#!/usr/bin/env python3
"""Restricted, tenant-bound browser tools for the Maritime Life Manager agent."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
import uuid
from urllib.parse import parse_qsl, unquote, urlsplit


TENANT_PATTERN = re.compile(r'lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
CDP_ENDPOINT = 'http://127.0.0.1:9229'
ALLOWED_HOSTS = frozenset({
    'capafy.ai', 'google.com', 'www.google.com', 'bing.com', 'www.bing.com',
    'duckduckgo.com', 'www.duckduckgo.com',
})
MAX_TOOL_CALLS = 80
MAX_RECEIPT_BYTES = 1_048_576
MAX_SAFE_LINKS = 25
MAX_URL_DECODE_PASSES = 12
PERCENT_ESCAPED_BYTE_PATTERN = re.compile(r'%[0-9a-f]{2}', re.I)
EMAIL_PATTERN = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
PHONE_PATTERN = re.compile(r'(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)')
CODE_PATTERN = re.compile(r'(?<!\d)\d{6}(?!\d)')
AUTH_SCHEME_PATTERN = re.compile(
    r'\b(?:proxy[-_ ]?authorization|authorization)["\']?\s*[:=]\s*["\']?'
    r'[A-Za-z][A-Za-z0-9_-]*\s+[^\s,;<>"\']{4,}', re.I,
)
CONTEXT_CODE_PATTERN = re.compile(
    r'\b(?:one[- ]time\s+)?(?:verification|security|login|authentication|auth|otp|passcode|pin|code)'
    r'\s*(?:code)?\s*(?:is|:|-)?\s*\d{4,8}\b', re.I,
)
REVERSE_CODE_PATTERN = re.compile(
    r'\b\d{4,8}\s+(?:(?:is|was)\s+(?:your|the)\s+)?(?:one[- ]time\s+)?'
    r'(?:verification|security|login|authentication|auth|otp|passcode|pin|code)\b', re.I,
)
BEARER_PATTERN = re.compile(r'\bBearer\s+[A-Za-z0-9._~+/=-]{8,}', re.I)
JWT_PATTERN = re.compile(r'\beyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]{8,}){2}\b')
PREFIXED_TOKEN_PATTERN = re.compile(r'\b(?:sk-(?:live|test)-|gh[pousr]_|xox[baprs]-|AKIA)[A-Za-z0-9_./-]{8,}\b')
CREDENTIAL_PATTERN = re.compile(
    r'\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|id[_ -]?token|'
    r'auth(?:orization)?(?:[_ -]?(?:key|token|secret))?|authorization|token|'
    r'session(?:[_ -]?(?:id|token))?|csrf|xsrf|nonce|verifier|client[_ -]?secret|'
    r'credential|password|secret)'
    r'["\']?\s*[:=]\s*["\']?(?:Bearer\s+)?[^\s,;<>"\']{4,}', re.I,
)
READONLY_ACTION_PATH = re.compile(
    r'/(?:login|sign-?in|sign-?up|register|create|publish(?:ing)?|submit(?:ted|s)?|upload|payment|checkout|'
    r'payouts?|withdraw(?:al)?|delete|remove|cancel|confirm|approve|send|post(?:s|ed)?)(?:/|$)', re.I,
)
READONLY_ACTION_QUERY = re.compile(
    r'\b(?:publish|submit|create|delete|remove|cancel|withdraw|payout|transfer|purchase|send|post|approve|confirm)\b',
    re.I,
)
CAPAFY_PUBLIC_PATH = re.compile(
    r'^/(?:$|market(?:place)?|explore|search|categories?|category/[^/]+|developer/doc(?:/.*)?)$', re.I,
)
SEARCH_PUBLIC_PATHS = frozenset({'/', '/search'})
PUBLIC_QUERY_KEYS = frozenset({
    'q', 'query', 'search', 'keyword', 'term', 'page', 'category', 'sort',
    'filter', 'limit', 'offset', 'lang', 'text', 'wd',
})


def _sensitive_query_key(value: str) -> bool:
    normalized = re.sub(r'[^a-z0-9]', '', value.lower())
    return (normalized.endswith(('token', 'secret', 'password', 'credential', 'session',
                                'authorization', 'auth', 'email', 'phone', 'otp',
                                'verification', 'code', 'key', 'nonce', 'verifier'))
            or normalized in {'state', 'csrf', 'xsrf'})


class BrowserToolError(RuntimeError):
    """A stable browser refusal or tool-input failure without page data."""

    def __init__(self, code: str, *, outcome: str = 'blocked', record: bool = True) -> None:
        super().__init__(code)
        self.outcome = outcome
        self.record = record


def _redact_text(value: str) -> str:
    if '\n' in value:
        return '\n'.join(_redact_text(line) for line in value.split('\n'))
    if PERCENT_ESCAPED_BYTE_PATTERN.search(value):
        decoded = _decode_url_component(value)
        if decoded is None or (decoded != value and _contains_sensitive_url_data(decoded)):
            return '[encoded sensitive text redacted]'
    value = EMAIL_PATTERN.sub('[email redacted]', value)
    value = PHONE_PATTERN.sub('[phone redacted]', value)
    value = AUTH_SCHEME_PATTERN.sub('[credential redacted]', value)
    value = CREDENTIAL_PATTERN.sub('[credential redacted]', value)
    value = BEARER_PATTERN.sub('[credential redacted]', value)
    value = JWT_PATTERN.sub('[credential redacted]', value)
    value = PREFIXED_TOKEN_PATTERN.sub('[credential redacted]', value)
    value = CONTEXT_CODE_PATTERN.sub('[code redacted]', value)
    value = REVERSE_CODE_PATTERN.sub('[code redacted]', value)
    return CODE_PATTERN.sub('[code redacted]', value)


def _allowed_url(value: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 2_048:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        port = parsed.port
    except ValueError:
        return False
    if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
            or port not in (None, 443) or parsed.fragment):
        return False
    return host in ALLOWED_HOSTS or host.endswith('.capafy.ai')


def _decode_url_component(value: str) -> str | None:
    decoded = value
    for _ in range(MAX_URL_DECODE_PASSES):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return None if PERCENT_ESCAPED_BYTE_PATTERN.search(decoded) else decoded


def _contains_sensitive_url_data(value: str) -> bool:
    return bool(
        EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value)
        or CODE_PATTERN.search(value) or CONTEXT_CODE_PATTERN.search(value)
        or REVERSE_CODE_PATTERN.search(value) or CREDENTIAL_PATTERN.search(value)
        or BEARER_PATTERN.search(value) or JWT_PATTERN.search(value)
        or PREFIXED_TOKEN_PATTERN.search(value)
    )


def _readonly_url(value: str) -> bool:
    if not _allowed_url(value):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        path = _decode_url_component(parsed.path.replace('\\', '/'))
        if path is None:
            return False
        path = path.replace('\\', '/')
        if READONLY_ACTION_PATH.search(path) or _contains_sensitive_url_data(path):
            return False
        if host in {'capafy.ai', 'www.capafy.ai', 'docs.capafy.ai'}:
            if not CAPAFY_PUBLIC_PATH.fullmatch(path):
                return False
        elif host.endswith('.capafy.ai'):
            return False
        elif path not in SEARCH_PUBLIC_PATHS:
            return False
        query_text = _decode_url_component(parsed.query)
        if query_text is None or _contains_sensitive_url_data(query_text):
            return False
        for key, query_value in parse_qsl(query_text, keep_blank_values=True):
            decoded_key = _decode_url_component(key)
            decoded_value = _decode_url_component(query_value)
            if (decoded_key is None or decoded_value is None
                    or _contains_sensitive_url_data(decoded_key)
                    or _contains_sensitive_url_data(decoded_value)
                    or _sensitive_query_key(decoded_key)
                    or re.sub(r'[^a-z0-9]', '', decoded_key.lower()) not in PUBLIC_QUERY_KEYS
                    or (decoded_key.lower() in {'action', 'intent', 'op', 'operation', 'method', 'cmd', 'do'}
                        and READONLY_ACTION_QUERY.search(decoded_value))):
                return False
        return True
    except ValueError:
        return False


def _search_endpoint(value: str) -> bool:
    if not _readonly_url(value):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        path = unquote(parsed.path)
    except ValueError:
        return False
    if host.endswith('.capafy.ai') or host in {'capafy.ai', 'www.capafy.ai'}:
        return path == '/search'
    return path in SEARCH_PUBLIC_PATHS


def _origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if _allowed_url(value):
            return f'https://{(parsed.hostname or "").lower()}'
    except ValueError:
        pass
    return 'about:blank' if value == 'about:blank' else 'unknown'


def _private_directory(path: Path, owner: int) -> bool:
    try:
        info = path.lstat()
        return (path.resolve(strict=True) == path and stat.S_ISDIR(info.st_mode)
                and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700)
    except OSError:
        return False


TOOLS = [
    {
        'name': 'browser_observe',
        'description': 'Inspect the current allowlisted page. Returns redacted title and visible text; pixels and form values are withheld.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'browser_navigate',
        'description': 'Open a public Capafy or search page over HTTPS. Other hosts and private addresses are blocked.',
        'inputSchema': {
            'type': 'object', 'properties': {'url': {'type': 'string', 'maxLength': 2048}},
            'required': ['url'], 'additionalProperties': False,
        },
    },
    {
        'name': 'browser_follow_link',
        'description': 'Follow one safe public link from the most recent browser_observe result. The observation expires if the page changes.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'observation_id': {'type': 'string', 'minLength': 32, 'maxLength': 32},
                'link_id': {'type': 'string', 'minLength': 1, 'maxLength': 2},
            },
            'required': ['observation_id', 'link_id'], 'additionalProperties': False,
        },
    },
    {
        'name': 'browser_search',
        'description': 'Search a same-origin public GET search form. Other form methods, origins, and write requests are blocked.',
        'inputSchema': {
            'type': 'object', 'properties': {'query': {'type': 'string', 'minLength': 1, 'maxLength': 200}},
            'required': ['query'], 'additionalProperties': False,
        },
    },
]


class BrowserMcpSession:
    def __init__(self, *, page: Any | None, context: Any | None = None,
                 tenant_id: str, occurrence_id: str, release_sha: str,
                 tenant_root: Path | str, receipt_path: Path | str, clock=None) -> None:
        self.page = None
        self.context = context or (getattr(page, 'context', None) if page is not None else None)
        self.tenant_id = tenant_id
        self.occurrence_id = occurrence_id
        self.release_sha = release_sha
        self.tenant_root = Path(tenant_root)
        self.receipt_path = Path(receipt_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.calls = 0
        self.effect_unknown = False
        self._last_observation = None
        self._unexpected_page = False
        self._service_worker_guard_failed = False
        self._cdp_sessions = []
        self._validate_paths()
        if (self.context is None or not hasattr(self.context, 'route')
                or not hasattr(self.context, 'new_cdp_session')):
            raise BrowserToolError('browser_context_unavailable', record=False)
        try:
            self.context.route('**/*', self._route_request)
            self.context.add_init_script(
                "Object.defineProperty(navigator, 'serviceWorker', "
                "{get() { throw new Error('service workers disabled by Life Manager'); }});"
            )
            self.context.on('page', self._on_new_page)
            if page is not None:
                self._attach_primary_page(page)
        except BrowserToolError:
            raise
        except Exception:
            raise BrowserToolError('browser_context_guard_unavailable', record=False) from None

    def _attach_service_worker_bypass(self, page: Any) -> None:
        try:
            cdp = self.context.new_cdp_session(page)
            cdp.send('Network.enable')
            cdp.send('Network.setBypassServiceWorker', {'bypass': True})
            self._cdp_sessions.append(cdp)
        except Exception:
            self._service_worker_guard_failed = True
            raise BrowserToolError('browser_service_worker_guard_unavailable', record=False) from None

    def _attach_primary_page(self, page: Any) -> None:
        self.page = page
        self._attach_service_worker_bypass(page)

    def _on_new_page(self, page: Any) -> None:
        if self.page is None:
            try:
                self._attach_primary_page(page)
            except BrowserToolError:
                try:
                    page.close()
                except Exception:
                    pass
            return
        if page is self.page:
            return
        self._unexpected_page = True
        try:
            self._attach_service_worker_bypass(page)
        except BrowserToolError:
            pass
        try:
            page.close()
        except Exception:
            self._service_worker_guard_failed = True

    def _ensure_context_ready(self) -> None:
        if self._service_worker_guard_failed or self._unexpected_page:
            raise BrowserToolError('browser_context_unavailable')

    def _validate_paths(self) -> None:
        owner = os.geteuid()
        try:
            root = self.tenant_root.resolve(strict=True)
            receipt = Path(os.path.abspath(self.receipt_path))
            parent = receipt.parent
            parent_info = parent.lstat()
            if (not TENANT_PATTERN.fullmatch(self.tenant_id)
                    or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', self.occurrence_id)
                    or not re.fullmatch(r'[0-9a-f]{40}', self.release_sha)
                    or not self.tenant_root.is_absolute()
                    or not self.receipt_path.is_absolute()
                    or root != self.tenant_root
                    or root.name != self.tenant_id
                    or not _private_directory(root, owner)
                    or not receipt.is_absolute()
                    or receipt.is_symlink()
                    or parent.resolve(strict=True) != parent
                    or not _private_directory(parent, owner)
                    or parent_info.st_uid != owner
                    or parent != root / 'receipts' / self.occurrence_id):
                raise BrowserToolError('browser_receipt_path_invalid')
            if receipt.exists():
                info = receipt.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise BrowserToolError('browser_receipt_path_invalid')
        except BrowserToolError:
            raise
        except (OSError, ValueError):
            raise BrowserToolError('browser_receipt_path_invalid') from None
        self.tenant_root = root
        self.receipt_path = receipt

    def _route_request(self, route: Any) -> None:
        try:
            target = route.request.url
            method = str(route.request.method or '').upper()
            if method in {'GET', 'HEAD'} and _readonly_url(target):
                route.continue_()
            else:
                route.abort()
        except Exception:
            try:
                route.abort()
            except Exception:
                pass

    def list_tools(self) -> dict[str, Any]:
        return {'tools': TOOLS}

    def _record(self, tool: str, outcome: str, action_id: str, *, state_hash: str | None = None,
                observation_id: str | None = None, link_id: str | None = None,
                link_count: int | None = None) -> None:
        record = {
            'at': self.clock(), 'actionId': action_id, 'tool': tool,
            'outcome': outcome, 'origin': _origin(str(getattr(self.page, 'url', ''))),
            'tenantId': self.tenant_id, 'occurrenceId': self.occurrence_id,
            'releaseSha': self.release_sha,
        }
        if state_hash is not None:
            if not re.fullmatch(r'[a-f0-9]{64}', state_hash):
                raise BrowserToolError('browser_receipt_evidence_invalid', record=False)
            record['stateHash'] = state_hash
        if observation_id is not None:
            if not re.fullmatch(r'[a-f0-9]{32}', observation_id):
                raise BrowserToolError('browser_receipt_evidence_invalid', record=False)
            record['observationId'] = observation_id
        if link_id is not None:
            if not re.fullmatch(r'[1-9][0-9]?', link_id):
                raise BrowserToolError('browser_receipt_evidence_invalid', record=False)
            record['linkId'] = link_id
        if link_count is not None:
            if (isinstance(link_count, bool) or not isinstance(link_count, int)
                    or not 0 <= link_count <= MAX_SAFE_LINKS
                    or tool != 'browser_observe' or outcome != 'read'):
                raise BrowserToolError('browser_receipt_evidence_invalid', record=False)
            record['linkCount'] = link_count
        payload = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        parent_fd = None
        try:
            parent_fd = os.open(
                self.receipt_path.parent,
                os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0),
            )
            parent_info = os.fstat(parent_fd)
            if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.geteuid()
                    or stat.S_IMODE(parent_info.st_mode) != 0o700):
                raise BrowserToolError('browser_receipt_path_invalid', record=False)
            fd = os.open(self.receipt_path.name, flags, 0o600, dir_fd=parent_fd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                        or info.st_size + len(payload) > MAX_RECEIPT_BYTES):
                    raise BrowserToolError('browser_receipt_path_invalid', record=False)
                fcntl.flock(fd, fcntl.LOCK_EX)
                written = 0
                while written < len(payload):
                    count = os.write(fd, payload[written:])
                    if count <= 0:
                        raise OSError('short_receipt_write')
                    written += count
                # A pre-dispatch "started" row must survive a process or VM
                # crash before an external browser action is issued.
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(parent_fd)
        except BrowserToolError:
            raise
        except OSError:
            raise BrowserToolError('browser_receipt_write_failed', record=False) from None
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

    def _record_after_dispatch(self, tool: str, outcome: str, action_id: str, *,
                               state_hash: str | None = None,
                               observation_id: str | None = None,
                               link_id: str | None = None) -> None:
        evidence = {key: value for key, value in {
            'state_hash': state_hash, 'observation_id': observation_id, 'link_id': link_id,
        }.items() if value is not None}
        try:
            self._record(tool, outcome, action_id, **evidence)
        except BrowserToolError:
            try:
                # If the success row was partially appended but could not be
                # fsynced, a duplicate terminal ID makes the cycle fail closed.
                self._record(tool, 'effect_unknown', action_id, **evidence)
            except BrowserToolError:
                pass
            raise BrowserToolError(
                'browser_effect_unknown_receipt_unavailable',
                outcome='effect_unknown', record=False,
            ) from None

    def _read_page_state(self) -> dict[str, Any]:
        try:
            current_url = str(getattr(self.page, 'url', ''))
            if current_url != 'about:blank' and not _readonly_url(current_url):
                raise BrowserToolError('navigation_blocked')
            title = _redact_text(str(self.page.title())[:200])
            title_url = str(getattr(self.page, 'url', ''))
            if (title_url != current_url
                    or (title_url != 'about:blank' and not _readonly_url(title_url))):
                raise BrowserToolError('navigation_blocked')
            visible = str(self.page.locator('body').inner_text(timeout=5_000))[:12_000]
            final_url = str(getattr(self.page, 'url', ''))
            if (final_url != title_url
                    or (final_url != 'about:blank' and not _readonly_url(final_url))):
                raise BrowserToolError('navigation_blocked')
            visible = _redact_text(visible)
            raw_links = self.page.locator('a[href]').evaluate_all(
                '(anchors) => { const links = []; let visited = 0; '
                'for (const anchor of anchors) { if (++visited > 250) break; '
                'const text = (anchor.innerText || anchor.getAttribute("aria-label") || anchor.title || "").trim(); '
                'if (text) links.push({ text: text.slice(0, 240), href: anchor.href }); } return links; }'
            )
            links = []
            if not isinstance(raw_links, list):
                raise BrowserToolError('browser_observation_failed')
            for item in raw_links:
                if not isinstance(item, dict):
                    continue
                href = item.get('href')
                label = re.sub(r'\s+', ' ', _redact_text(str(item.get('text') or '')).strip())[:160]
                if not label or not _readonly_url(href):
                    continue
                links.append({'linkId': str(len(links) + 1), 'label': label, 'href': href})
                if len(links) >= MAX_SAFE_LINKS:
                    break
            links_url = str(getattr(self.page, 'url', ''))
            if (links_url != final_url
                    or (links_url != 'about:blank' and not _readonly_url(links_url))):
                raise BrowserToolError('navigation_blocked')
        except BrowserToolError:
            raise
        except Exception:
            raise BrowserToolError('browser_observation_failed') from None
        state = {
            'url': final_url, 'title': title, 'visible': visible,
            'links': [{'linkId': item['linkId'], 'label': item['label'],
                       'href': item['href']} for item in links],
        }
        canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return {'url': final_url, 'title': title, 'visible': visible, 'links': links,
                'stateHash': hashlib.sha256(canonical.encode()).hexdigest()}

    def _observe(self, action_id: str) -> dict[str, Any]:
        state = self._read_page_state()
        observation_id = uuid.uuid4().hex
        self._last_observation = {
            'observationId': observation_id,
            'stateHash': state['stateHash'],
            'links': {item['linkId']: item for item in state['links']},
        }
        self._record('browser_observe', 'read', action_id, state_hash=state['stateHash'],
                     observation_id=observation_id, link_count=len(state['links']))
        link_lines = [f"[{item['linkId']}] {item['label']} ({_origin(item['href'])})"
                      for item in state['links']]
        links_text = ('\nSafe public links (choose by link ID):\n' + '\n'.join(link_lines)
                      if link_lines else '\nSafe public links: none observed')
        return {'content': [{
            'type': 'text',
            'text': (f"Title: {state['title']}\nPage: {_origin(state['url'])}"
                     f"\nObservation ID: {observation_id}\nPage state hash: {state['stateHash']}"
                     f"\nVisible text (redacted, capped):\n{state['visible']}{links_text}"),
        }]}

    def _navigate(self, arguments: dict[str, Any], action_id: str) -> dict[str, Any]:
        target = arguments.get('url')
        if not _readonly_url(target):
            raise BrowserToolError('browser_navigation_blocked')
        self._record('browser_navigate', 'started', action_id)
        self._last_observation = None
        try:
            self.page.goto(target, wait_until='domcontentloaded', timeout=20_000)
            if not _readonly_url(str(getattr(self.page, 'url', ''))):
                raise BrowserToolError('browser_navigation_effect_unknown', outcome='effect_unknown')
        except Exception:
            raise BrowserToolError('browser_navigation_effect_unknown', outcome='effect_unknown') from None
        self._record_after_dispatch('browser_navigate', 'opened', action_id)
        return {'content': [{'type': 'text', 'text': f'Opened {_origin(str(self.page.url))}'}]}

    def _follow_link(self, arguments: dict[str, Any], action_id: str) -> dict[str, Any]:
        observation_id = arguments.get('observation_id')
        link_id = arguments.get('link_id')
        if (not isinstance(observation_id, str) or not re.fullmatch(r'[a-f0-9]{32}', observation_id)
                or not isinstance(link_id, str) or not re.fullmatch(r'[1-9][0-9]?', link_id)):
            raise BrowserToolError('browser_link_input_invalid')
        observed = self._last_observation
        if not isinstance(observed, dict) or observed.get('observationId') != observation_id:
            raise BrowserToolError('browser_link_observation_stale')
        link = observed.get('links', {}).get(link_id)
        if not isinstance(link, dict):
            raise BrowserToolError('browser_link_not_observed')
        state = self._read_page_state()
        if state['stateHash'] != observed.get('stateHash'):
            self._last_observation = None
            raise BrowserToolError('browser_link_observation_stale')
        target = link.get('href')
        if not _readonly_url(target):
            self._last_observation = None
            raise BrowserToolError('browser_link_not_observed')
        self._record('browser_follow_link', 'started', action_id,
                     state_hash=state['stateHash'], observation_id=observation_id,
                     link_id=link_id)
        self._last_observation = None
        try:
            self.page.goto(target, wait_until='domcontentloaded', timeout=20_000)
            if not _readonly_url(str(getattr(self.page, 'url', ''))):
                raise BrowserToolError('browser_link_effect_unknown', outcome='effect_unknown')
        except Exception:
            raise BrowserToolError('browser_link_effect_unknown', outcome='effect_unknown') from None
        self._record_after_dispatch('browser_follow_link', 'opened', action_id,
                                    state_hash=state['stateHash'], observation_id=observation_id,
                                    link_id=link_id)
        return {'content': [{'type': 'text', 'text': f'Opened {_origin(str(self.page.url))}'}]}

    def _search(self, arguments: dict[str, Any], action_id: str) -> dict[str, Any]:
        query = arguments.get('query')
        decoded_query = _decode_url_component(query) if isinstance(query, str) else None
        if (not isinstance(query, str) or not query.strip() or len(query) > 200
                or EMAIL_PATTERN.search(query) or PHONE_PATTERN.search(query)
                or CONTEXT_CODE_PATTERN.search(query) or REVERSE_CODE_PATTERN.search(query)
                or CODE_PATTERN.search(query) or CREDENTIAL_PATTERN.search(query)
                or BEARER_PATTERN.search(query) or JWT_PATTERN.search(query)
                or PREFIXED_TOKEN_PATTERN.search(query)
                or decoded_query is None or _contains_sensitive_url_data(decoded_query)):
            raise BrowserToolError('browser_search_query_invalid')
        try:
            locator = self.page.get_by_role('searchbox')
            if locator.count() != 1:
                raise BrowserToolError('browser_search_unavailable')
            form = locator.evaluate(
                '(element) => { const form = element.form; return { '
                'method: form ? form.method : "GET", action: form ? form.action : window.location.href, '
                'target: form ? (form.target || "_self") : "_self", inputName: element.name || "", '
                'fieldNames: form ? Array.from(form.elements).map((item) => item.name).filter(Boolean) : [element.name || ""] }; }'
            )
            current_url = str(getattr(self.page, 'url', ''))
            action = str(form.get('action') or '') if isinstance(form, dict) else ''
            field_names = form.get('fieldNames') if isinstance(form, dict) else None
            if (not isinstance(form, dict) or str(form.get('method') or '').upper() != 'GET'
                    or str(form.get('target') or '').lower() not in {'', '_self'}
                    or form.get('inputName') not in {'q', 'query', 'search', 'keyword', 'term'}
                    or not isinstance(field_names, list)
                    or any(re.sub(r'[^a-z0-9]', '', str(name).lower()) not in PUBLIC_QUERY_KEYS
                           for name in field_names)
                    or not _search_endpoint(action) or _origin(action) != _origin(current_url)):
                raise BrowserToolError('browser_search_blocked')
        except BrowserToolError:
            raise
        except Exception:
            raise BrowserToolError('browser_search_blocked') from None
        self._record('browser_search', 'started', action_id)
        self._last_observation = None
        try:
            locator.fill(query, timeout=5_000)
            locator.press('Enter', timeout=5_000)
        except Exception:
            raise BrowserToolError('browser_search_effect_unknown', outcome='effect_unknown') from None
        self._record_after_dispatch('browser_search', 'searched', action_id)
        return {'content': [{'type': 'text', 'text': 'Search submitted; inspect the resulting page.'}]}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in {tool['name'] for tool in TOOLS} or not isinstance(arguments, dict):
            raise BrowserToolError('browser_tool_not_allowed')
        self._ensure_context_ready()
        if self.effect_unknown:
            raise BrowserToolError(
                'browser_effect_unknown_fence', outcome='effect_unknown', record=False,
            )
        if self.calls >= MAX_TOOL_CALLS:
            raise BrowserToolError('browser_action_budget_exhausted')
        self.calls += 1
        action_id = uuid.uuid4().hex
        try:
            if name == 'browser_observe':
                return self._observe(action_id)
            if name == 'browser_navigate':
                return self._navigate(arguments, action_id)
            if name == 'browser_follow_link':
                return self._follow_link(arguments, action_id)
            if name == 'browser_search':
                return self._search(arguments, action_id)
        except BrowserToolError as error:
            if error.outcome == 'effect_unknown':
                self.effect_unknown = True
            if error.record:
                try:
                    self._record(name, error.outcome, action_id)
                except BrowserToolError:
                    if error.outcome == 'effect_unknown':
                        raise BrowserToolError(
                            'browser_effect_unknown_receipt_unavailable',
                            outcome='effect_unknown', record=False,
                        ) from None
                    raise
            raise
        raise BrowserToolError('browser_tool_not_allowed')


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}}


def _tool_error(message: str) -> dict[str, Any]:
    return {'content': [{'type': 'text', 'text': message}], 'isError': True}


def run_stdio(session: BrowserMcpSession, input_stream=None, output_stream=None) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    initialized = False
    for line in input_stream:
        try:
            request = json.loads(line)
        except (ValueError, TypeError):
            output_stream.write(json.dumps(_rpc_error(None, -32700, 'parse error')) + '\n')
            output_stream.flush()
            continue
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
            request_id = request.get('id') if isinstance(request, dict) else None
            output_stream.write(json.dumps(_rpc_error(request_id, -32600, 'invalid request')) + '\n')
            output_stream.flush()
            continue
        method = request.get('method')
        request_id = request.get('id')
        params = request.get('params') if isinstance(request.get('params'), dict) else {}
        if not isinstance(method, str):
            if 'id' in request:
                output_stream.write(json.dumps(_rpc_error(request_id, -32600, 'invalid request')) + '\n')
                output_stream.flush()
            continue
        if method.startswith('notifications/'):
            if method == 'notifications/exit':
                return 0
            continue
        try:
            if method == 'initialize':
                version = params.get('protocolVersion')
                if not isinstance(version, str):
                    raise ValueError('mcp_protocol_version_missing')
                result = {
                    'protocolVersion': version,
                    'capabilities': {'tools': {'listChanged': False}},
                    'serverInfo': {'name': 'life-manager-maritime-browser', 'version': '1'},
                }
                initialized = True
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                if not initialized:
                    raise ValueError('mcp_not_initialized')
                result = session.list_tools()
            elif method == 'tools/call':
                if not initialized:
                    raise ValueError('mcp_not_initialized')
                arguments = params.get('arguments', {})
                try:
                    result = session.call(params.get('name'), arguments)
                except BrowserToolError as error:
                    result = _tool_error(str(error))
            elif method == 'shutdown':
                result = {}
            else:
                output_stream.write(json.dumps(_rpc_error(request_id, -32601, 'method not found')) + '\n')
                output_stream.flush()
                continue
            output_stream.write(json.dumps({'jsonrpc': '2.0', 'id': request_id, 'result': result}, ensure_ascii=False) + '\n')
            output_stream.flush()
            if method == 'shutdown':
                return 0
        except ValueError as error:
            output_stream.write(json.dumps(_rpc_error(request_id, -32603, str(error))) + '\n')
            output_stream.flush()
        except Exception:
            output_stream.write(json.dumps(_rpc_error(request_id, -32603, 'browser_mcp_internal_error')) + '\n')
            output_stream.flush()
    return 0


def _connect(args: argparse.Namespace) -> tuple[Any, Any]:
    tenant_id = os.environ.get('LM_RUNTIME_TENANT_ID', '')
    occurrence_id = os.environ.get('LM_RUNTIME_OCCURRENCE_ID', '')
    release_sha = os.environ.get('LM_RELEASE_SHA', '')
    endpoint = os.environ.get('LM_MARITIME_BROWSER_CDP_URL', '')
    if (not TENANT_PATTERN.fullmatch(tenant_id) or tenant_id != args.tenant_root.name
            or occurrence_id != args.occurrence_id or release_sha != args.release_sha
            or endpoint != CDP_ENDPOINT):
        raise BrowserToolError('browser_session_binding_invalid')
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=10_000)
        contexts = browser.contexts
        if len(contexts) != 1:
            raise BrowserToolError('browser_context_unavailable')
        context = contexts[0]
        session = BrowserMcpSession(
            page=None, context=context, tenant_id=tenant_id, occurrence_id=occurrence_id,
            release_sha=release_sha, tenant_root=args.tenant_root,
            receipt_path=args.receipt_path,
        )
        pages = list(context.pages)
        if not pages:
            page = context.new_page()
            if session.page is None:
                session._attach_primary_page(page)
        else:
            for page in pages:
                if session.page is None:
                    session._attach_primary_page(page)
                else:
                    session._on_new_page(page)
        if session.page is None or session._unexpected_page:
            raise BrowserToolError('browser_context_unavailable')
        return playwright, session
    except Exception:
        playwright.stop()
        if isinstance(sys.exc_info()[1], BrowserToolError):
            raise
        raise BrowserToolError('browser_cdp_unavailable') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tenant-root', type=Path, required=True)
    parser.add_argument('--receipt-path', type=Path, required=True)
    parser.add_argument('--occurrence-id', required=True)
    parser.add_argument('--release-sha', required=True)
    args = parser.parse_args(argv)
    try:
        playwright, session = _connect(args)
    except (BrowserToolError, OSError, ValueError):
        return 2
    try:
        return run_stdio(session)
    finally:
        playwright.stop()


if __name__ == '__main__':
    raise SystemExit(main())
