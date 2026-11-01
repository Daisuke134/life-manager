"""R007: a small, offline registry of source-linked research claims.

This validates record structure, not scientific truth. The caller must read the
source, judge relevance and audit the labels. Registration never grants rights
to ingest participant data, execute an intervention, or claim Manager impact.
No network, database, model API, credentials or external writes are involved.
"""
from __future__ import annotations

from datetime import date
import ipaddress
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

SOURCE_KINDS = {'primary_paper', 'review_paper', 'company_page', 'official_docs'}
DESIGNS = {'randomized_trial', 'observational_survey', 'simulation', 'benchmark',
           'review', 'software_documentation'}
RIGHTS_STATES = {'hold', 'allowed_with_conditions', 'not_applicable'}


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise ValueError('expected object')
    if not required <= value.keys() or value.keys() - required - (optional or set()):
        raise ValueError(f'wrong object fields; required={sorted(required)}')
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('nonempty text required')
    return value


def _texts(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError('nonempty list of text required')
    for item in value:
        _text(item)


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError('finite number required; booleans and strings are not numbers')
    return value


def _choice(value: Any, options: set[str]) -> str:
    if not isinstance(value, str) or value not in options:
        raise ValueError(f'invalid choice: expected one of {sorted(options)}')
    return value


def _url(value: Any) -> str:
    value = _text(value)
    u = urlsplit(value)
    # RFC 9110 §4.2.4: reject *any* userinfo delimiter, even an empty
    # username, rather than relying on the truthiness of parsed.username.
    if u.scheme != 'https' or not u.hostname or '@' in u.netloc:
        raise ValueError('public HTTPS URL without userinfo required')
    if any(c.isspace() for c in value):
        raise ValueError('invalid public URL')
    # Policy stricter than RFC 3986 reg-name syntax: require DNS/IDNA form.
    # Percent-encoded hostnames introduce ambiguous resolution and can hide
    # local names from text-only checks. No DNS lookups or HTTP requests.
    if '%' in u.hostname:
        raise ValueError('percent-encoded public URL host forbidden')
    host = u.hostname.rstrip('.')
    if not host or u.hostname.endswith('..'):
        raise ValueError('invalid public URL host')
    if host in {'localhost', 'localhost.localdomain'} or host.endswith(
        ('.localhost', '.local', '.internal')
    ):
        raise ValueError('local URL forbidden')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # OWASP SSRF guidance: reject noncanonical numeric hosts that a
        # downstream resolver might treat as hex, octal or shortened IPv4.
        if re.fullmatch(
            r'(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+))*',
            host,
        ):
            raise ValueError('noncanonical numeric public URL host forbidden')
    else:
        if not address.is_global:
            raise ValueError('private/local IP forbidden')
    # We deliberately do not fetch URLs or pretend syntax proves accessibility.
    return value


def _uncertainty(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError('explicit uncertainty object required')
    status = _choice(value.get('status'), {'reported', 'not_reported', 'not_applicable'})
    if status != 'reported':
        _object(value, {'status'})
        return
    _object(value, {'status', 'kind', 'level', 'lower', 'upper'})
    _choice(value['kind'], {'confidence_interval', 'credible_interval'})
    level = _number(value['level'])
    lower, upper = _number(value['lower']), _number(value['upper'])
    if not 0 < level < 1 or lower > upper:
        raise ValueError('invalid uncertainty interval')


def validate_record(record: Any) -> dict:
    """Reject missing sources, ambiguous numbers, and implicit permissions."""
    r = _object(record, {'schema_version', 'id', 'source', 'study', 'claim',
                        'outcome', 'findings', 'limitations', 'rights', 'review'})
    if type(r['schema_version']) is not int or r['schema_version'] != 1:
        raise ValueError('unsupported schema version')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', _text(r['id'])):
        raise ValueError('invalid evidence id')
    s = _object(r['source'], {'kind', 'title', 'authors', 'url', 'version', 'accessed'})
    _choice(s['kind'], SOURCE_KINDS)
    for key in ('title', 'version'):
        _text(s[key])
    _texts(s['authors']); _url(s['url'])
    date.fromisoformat(_text(s['accessed']))
    st = _object(r['study'], {'design', 'population', 'sample_size', 'sample_unit', 'locator'})
    _choice(st['design'], DESIGNS)
    for key in ('population', 'sample_unit', 'locator'):
        _text(st[key])
    if st['sample_size'] is not None and (type(st['sample_size']) is not int or st['sample_size'] <= 0):
        raise ValueError('sample_size must be positive integer or explicit null')
    _text(r['claim'])
    o = _object(r['outcome'], {'name', 'window'})
    _text(o['name']); _text(o['window'])
    if not isinstance(r['findings'], list):
        raise ValueError('findings must be a list; use [] for qualitative-only findings')
    for f in r['findings']:
        _object(f, {'name', 'value', 'unit', 'source_url', 'locator', 'analysis', 'uncertainty'})
        for key in ('name', 'unit', 'locator'):
            _text(f[key])
        _number(f['value']); _url(f['source_url'])
        _choice(f['analysis'], {'primary', 'secondary', 'descriptive', 'vendor_report'})
        _uncertainty(f['uncertainty'])
    _texts(r['limitations'])
    rights = _object(r['rights'], {'use', 'raw_data_use', 'basis_url'})
    if rights['use'] != 'metadata_and_original_summary_only':
        raise ValueError('R007 does not authorize raw-data ingestion or redistribution')
    _choice(rights['raw_data_use'], RIGHTS_STATES); _url(rights['basis_url'])
    review = _object(r['review'], {'status', 'locator', 'reproduced_by_manager'})
    _choice(review['status'], {'source_read', 'abstract_only', 'needs_review'})
    _text(review['locator'])
    if type(review['reproduced_by_manager']) is not bool:
        raise ValueError('reproduction flag must be boolean')
    if review['reproduced_by_manager']:
        raise ValueError('R007 is a literature registry, not a Manager reproduction/field-results store')
    return r


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f'duplicate JSON key: {key}')
        out[key] = value
    return out


def load_registry(directory: str | Path) -> list[dict]:
    """Load reviewed records deterministically; reject an empty or mixed registry."""
    paths = sorted(Path(directory).glob('*.json'))
    if not paths:
        raise ValueError('no evidence records found')
    records, ids = [], set()
    for path in paths:
        record = validate_record(json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys))
        if record['id'] in ids:
            raise ValueError(f'duplicate evidence id: {record["id"]}')
        ids.add(record['id']); records.append(record)
    return records


if __name__ == '__main__':
    import sys
    try:
        root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'evidence'
        records = load_registry(root)
    except (ValueError, OSError) as error:
        raise SystemExit(f'EVIDENCE_INVALID: {error}')
    print(json.dumps({'records': len(records), 'ids': [r['id'] for r in records],
                      'validated': 'structure_only', 'manager_field_impact': 'not_measured'}, indent=2))
