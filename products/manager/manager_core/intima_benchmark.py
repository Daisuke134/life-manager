"""Rights-bound, local INTIMA input intake; no model or outcome evaluation.

A supplied rights review is a declaration, not legal authentication. Matching
bytes establish artifact consistency only. Public exports contain metadata;
private in-memory prompts must never become training, few-shot or retrieval data.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Mapping

from .models.source import Source
from .outcome_bench import EvidenceBundle, reproduction_manifest

_UNAVAILABLE = 'INTIMA_INTAKE_UNAVAILABLE'
_PERMISSION_STATES = {'allowed_with_conditions', 'hold', 'not_applicable'}


def _require(condition):
    if not condition:
        raise ValueError(_UNAVAILABLE)


def _text(value):
    _require(type(value) is str and bool(value.strip()))
    return value


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _object(pairs):
    """Duplicate JSON object keys cannot silently replace a field or review."""
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


@dataclass(frozen=True)
class IntimaCase:
    case_id: str
    prompt_sha256: str
    code: str
    prompt_generator_model: str
    prompt: str = field(repr=False)

    def __post_init__(self):
        _require(type(self.case_id) is str and re.fullmatch(r'intima:[a-f0-9]{40}:row-[1-9][0-9]*', self.case_id) is not None)
        _text(self.code)
        _text(self.prompt_generator_model)
        _text(self.prompt)
        _require(self.prompt_sha256 == sha256(self.prompt.encode('utf-8')).hexdigest())


@dataclass(frozen=True)
class IntimaDataset:
    source: Source
    artifact_revision: str
    artifact_path: str
    cases: tuple[IntimaCase, ...]
    _review_json: str = field(repr=False)


def _profile(cases):
    groups = {}
    for i, case in enumerate(cases, 1):
        groups.setdefault(case.prompt_sha256, []).append(i)
    return {
        'rows': len(cases), 'unique_prompts': len(groups),
        'codes': len({c.code for c in cases}),
        'code_counts': dict(sorted(Counter(c.code for c in cases).items())),
        'prompt_generator_model_counts': dict(sorted(Counter(c.prompt_generator_model for c in cases).items())),
        'duplicate_groups': [{'prompt_sha256': digest, 'rows_1based': rows}
                             for digest, rows in sorted(groups.items()) if len(rows) > 1],
    }


def _review(rights_manifest):
    _require(isinstance(rights_manifest, Mapping) and rights_manifest.get('schema') == 'manager.source-rights.v1')
    records = rights_manifest['sources']
    _require(type(records) is list and all(isinstance(r, Mapping) for r in records))
    matches = [r for r in records if r.get('id') == 'intima-prompts']
    _require(len(matches) == 1)
    record = matches[0]
    permissions = record['permissions']
    _require(isinstance(permissions, Mapping))
    for key in ('study_read', 'local_research', 'raw_redistribution', 'product_use',
                'commercial_evaluation', 'commercial_training'):
        _require(type(permissions.get(key)) is str and permissions[key] in _PERMISSION_STATES)
    _require(all(permissions[key] == 'allowed_with_conditions'
                 for key in ('study_read', 'local_research', 'commercial_evaluation')))
    _require(permissions['commercial_training'] == 'hold')
    artifact = record['artifact']
    _require(isinstance(artifact, Mapping))
    _require(artifact['role'] == 'evaluation_only' and artifact['publication'] == 'metadata_only')
    revision = artifact['revision']
    _require(type(revision) is str and re.fullmatch(r'[a-f0-9]{40}', revision) is not None)
    _require(artifact['path'] == 'INTIMA.jsonl')
    _require(type(artifact['bytes']) is int and artifact['bytes'] > 0)
    _require(type(artifact['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', artifact['sha256']) is not None)
    _require(record['license_evidence_sha'] == revision)
    _require(_text(record['source_url']).endswith(f'/resolve/{revision}/INTIMA.jsonl'))
    _require(_text(record['license_evidence_url']).startswith('https://')
             and record['license_evidence_url'].endswith(f'/blob/{revision}/README.md'))
    _text(record['license_expression'])
    _require(type(record['requirements']) is list and bool(record['requirements']))
    for requirement in record['requirements']:
        _text(requirement)
    attribution = record['attribution']
    _require(type(attribution['creators']) is list and bool(attribution['creators']))
    for creator in attribution['creators']:
        _text(creator)
    _require(_text(attribution['license_url']).startswith('https://'))
    _text(attribution['changes'])
    claims = record['card_claim']
    _require(set(claims) == {'rows', 'codes'} and all(type(v) is int and v > 0 for v in claims.values()))
    # Keep only reviewed export fields, detach from the caller's mutable mapping.
    return json.loads(_canonical({key: record[key] for key in (
        'id', 'source_url', 'license_expression', 'license_evidence_url', 'license_evidence_sha',
        'permissions', 'requirements', 'artifact', 'data_quality', 'card_claim', 'attribution')}))


def load_intima(payload: bytes, rights_manifest: Mapping) -> IntimaDataset:
    """Bind exact local JSONL bytes to one declared evaluation-only source review.

    Reject schema drift and inconsistent profiles; preserve row order, duplicates
    and every decoded prompt character. All rejected inputs use a static error.
    """
    try:
        _require(type(payload) is bytes)
        review = _review(rights_manifest)
        artifact = review['artifact']
        _require(len(payload) == artifact['bytes'])
        source = Source('intima-prompts', review['source_url'], review['license_expression'],
                        review['permissions']['commercial_evaluation'], artifact['sha256'],
                        datetime.fromisoformat(artifact['retrieved_at']), 'public_nonpersonal')
        source.verify_content(payload)
        cases = []
        lines = payload.decode('utf-8').split('\n')
        if lines[-1] == '':
            lines.pop()  # JSONL permits one final LF; other empty rows are invalid.
        for i, line in enumerate(lines, 1):
            row = json.loads(line, object_pairs_hook=_object)
            _require(type(row) is dict and set(row) == {'code', 'prompt', 'model'})
            for value in row.values():
                _text(value)
            cases.append(IntimaCase(f"intima:{artifact['revision']}:row-{i}",
                                   sha256(row['prompt'].encode('utf-8')).hexdigest(),
                                   row['code'], row['model'], row['prompt']))
        _require(bool(cases) and _canonical(_profile(cases)) == _canonical(review['data_quality']))
        return IntimaDataset(source, artifact['revision'], artifact['path'], tuple(cases), _canonical(review))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ValueError(_UNAVAILABLE) from None


def intima_intake_manifest(dataset: IntimaDataset, *, code_version: str) -> dict:
    """Deterministic metadata only, with the existing empty-bundle assessment.

    Prompt hashes group duplicates; no rows are removed. Input intake supplies
    no simulation, response, annotation, execution or human outcome evidence.
    """
    try:
        _require(type(dataset) is IntimaDataset and type(dataset.source) is Source)
        _require(type(dataset.cases) is tuple and bool(dataset.cases))
        review = json.loads(dataset._review_json, object_pairs_hook=_object)
        review = _review({'schema': 'manager.source-rights.v1', 'sources': [review]})
        artifact = review['artifact']
        _require(dataset.artifact_revision == artifact['revision'] and dataset.artifact_path == artifact['path'])
        _require(dataset.source == Source('intima-prompts', review['source_url'], review['license_expression'],
                 review['permissions']['commercial_evaluation'], artifact['sha256'],
                 datetime.fromisoformat(artifact['retrieved_at']), 'public_nonpersonal'))
        for i, case in enumerate(dataset.cases, 1):
            _require(type(case) is IntimaCase and case.case_id == f'intima:{dataset.artifact_revision}:row-{i}')
            case.__post_init__()
        actual = _profile(dataset.cases)
        _require(_canonical(actual) == _canonical(review['data_quality']))
        actual['duplicate_excess_rows'] = actual['rows'] - actual['unique_prompts']
        for group in actual['duplicate_groups']:
            group['case_ids'] = [dataset.cases[i - 1].case_id for i in group['rows_1based']]
        subject = f'intima:{dataset.artifact_revision}'
        evidence = reproduction_manifest(EvidenceBundle(subject, 'manager-intima-intake', ()), code_version=code_version)
        return {
            'schema': 'manager.intima-intake.v1', 'code_version': code_version,
            'stage': 'INPUT_INTAKE_ONLY', 'evaluation_status': 'NOT_RUN',
            'source': {'source_id': dataset.source.source_id, 'url': dataset.source.url,
                       'sha256': dataset.source.content_sha256, 'license_id': dataset.source.license_id,
                       'rights': dataset.source.rights, 'privacy_class': dataset.source.privacy_class,
                       'retrieved_at': dataset.source.retrieved_at.isoformat()},
            'artifact': artifact,
            'rights': {key: review[key] for key in ('permissions', 'requirements', 'license_evidence_url',
                       'license_evidence_sha', 'attribution')},
            'actual': actual, 'card_claim': review['card_claim'],
            'claim_discrepancy': any(actual[key] != review['card_claim'][key] for key in ('rows', 'codes')),
            'validity': {'person': 'UNKNOWN', 'time': 'UNKNOWN', 'transfer': 'UNKNOWN'},
            'proof_level': evidence['assessment']['real_world_proof_level'],
            'human_welfare_status': evidence['assessment']['human_welfare_status'],
            'can_execute': False, 'evidence': evidence,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ValueError(_UNAVAILABLE) from None
