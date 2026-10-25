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
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('public HTTPS URL without credentials required')
    if any(c.isspace() for c in value) or u.hostname in {'localhost', 'localhost.localdomain'}:
        raise ValueError('invalid public URL')
    if u.hostname.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('local URL forbidden')
    try:
        address = ipaddress.ip_address(u.hostname)
    except ValueError:
        pass
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

# E01 — a narrowly pinned, reproducible real API research trial. This is
# an immutable P0 artifact check, not a general participant evidence store.
from hashlib import sha256 as _sha256

_TRIAL_RUN_ID = 39713799676
_TRIAL_SOURCE_COMMIT = "66997ea549f8d1373a7670b8a11add9af17613ea"
_TRIAL_ARTIFACT_ID = 12398755518
_TRIAL_RAW_SHA256 = "c46503170d9fc337137d6283fb6d38821a29149f72609f751a79366103f70585"
_TRIAL_RAW_BYTES = 14759


def load_verified_trial(path: Path, receipt: dict) -> dict:
    """Validate original recorded research bytes AND derived aggregates.

    Explicitly not evidence that provider's reported metrics are true, that
    any fictional person is real, or that anyone was helped. Caller must
    separately check GitHub workflow run identity/permissions.
    """
    path = Path(path)
    if path.name != "ten_case_raw.json" and not path.is_file():
        raise ValueError("missing actual P0 trial source")
    if type(receipt) is not dict:
        raise ValueError("typed provenance receipt required")
    if (receipt.get("run_id") != _TRIAL_RUN_ID or
        receipt.get("source_commit") != _TRIAL_SOURCE_COMMIT or
        receipt.get("artifact_id") != _TRIAL_ARTIFACT_ID or
        receipt.get("raw_sha256") != _TRIAL_RAW_SHA256 or
        receipt.get("raw_bytes") != _TRIAL_RAW_BYTES or
        receipt.get("recorded_as") != "P0_SYNTHETIC_ONLY" or
        receipt.get("actual_people") != 0 or
        receipt.get("actual_effects") != 0 or
        receipt.get("settled_cost_usd", "MISSING") is not None):
        raise ValueError("trial receipt does not match immutable observed metadata")
    raw = path.read_bytes()
    if len(raw) != _TRIAL_RAW_BYTES or _sha256(raw).hexdigest() != _TRIAL_RAW_SHA256:
        raise ValueError("original trial bytes differ from pinned artifact")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys,
                         parse_constant=lambda _ : (_ for _ in ()).throw(
                             ValueError("nonfinite JSON in research artifact")))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid JSON source") from exc
    if not isinstance(obj, dict) or obj.get("schema") != "manager.ampersand-p0-lab.v1":
        raise ValueError("unexpected trial schema")
    rows = obj.get("cases")
    if not isinstance(rows, list) or len(rows) != 10:
        raise ValueError("ten trial cases required")
    names, sessions, turn_ids = set(), set(), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("scenario"), str):
            raise ValueError("invalid trial case")
        if row["scenario"] in names or row.get("session_id") in sessions:
            raise ValueError("duplicate scenario or session")
        names.add(row["scenario"])
        sessions.add(row.get("session_id"))
        turn_ids.add(row.get("turn_id"))
        if (not isinstance(row.get("session_id"), str) or
            not row["session_id"].startswith("sess_") or
            not isinstance(row.get("turn_id"), str) or
            not row["turn_id"].startswith("turn_") or
            row.get("kernel_action") != "NO_ACTION" or
            row.get("kernel_audit_valid") is not True or
            row.get("authorized_execution") is not False or
            row.get("source_type") != "FICTIONAL_NOT_REAL_GOV_SOURCE" or
            row.get("model_status") not in {"MODEL_ADVICE_P0", "INVALID_MODEL_OUTPUT"} or
            row.get("model_decision") not in {"ASK", "PASS", "PROPOSE"}):
            raise ValueError("unsupported trial evidence row")
    if len(turn_ids) != 10:
        raise ValueError("duplicate initial turns")
    heldout = [r for r in rows if r.get("split") == "HELD_OUT_FROM_PROMPT_ITERATION"]
    valid_split = {"PROMPT_DEVELOPMENT", "HELD_OUT_FROM_PROMPT_ITERATION"}
    if any(r.get("split") not in valid_split for r in rows):
        raise ValueError("unknown evaluation split")
    followups = [r for r in rows if (
        isinstance(r.get("followup"), dict) and
        r["followup"].get("same_session") is True and
        r["followup"].get("status") == "completed")]
    expected = {
        "model_sessions_created": len(sessions),
        "model_scored": sum(r.get("model_matches_author") is not None for r in rows),
        "model_matches_count": sum(r.get("model_matches_author") is True for r in rows),
        "heldout_cases": len(heldout),
        "heldout_model_scored": sum(r.get("model_matches_author") is not None for r in heldout),
        "heldout_model_matches": sum(r.get("model_matches_author") is True for r in heldout),
        "completed_followups": len(followups),
        "completed_kernel_audits": sum(r.get("kernel_audit_valid") is True for r in rows),
        "baseline_matches_count": sum(r.get("baseline_matches_author") is True for r in rows),
    }
    if any(type(obj.get(k)) is not int or obj[k] != v for k, v in expected.items()):
        raise ValueError("reported model aggregates do not match individual cases")
    if (obj.get("model") != "ampersand-v0.1" or
        obj.get("auth_model_check") != "PASS" or
        obj.get("evidence_level") != "P0_SYNTHETIC_ONLY" or
        obj.get("real_human_outcome") != "NOT_MEASURED" or
        obj.get("real_people") != 0 or
        obj.get("real_world_effects") != 0 or
        obj.get("exact_settled_cost_usd", "MISSING") is not None or
        obj.get("production_enabled") is not False or
        obj.get("blog_published") is not False):
        raise ValueError("unsupported provider outcome/causal/production claim")
    return obj
