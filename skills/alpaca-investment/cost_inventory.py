"""Independent execution/source evidence; never a billing or net-P&L calculator."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from effect_store import _append_once


CATALOG_PATH = Path('apps/life-manager/config/product-loop-catalog.json')


def _gap(reason):
    return {'coverage_state': 'gap', 'reason': reason, 'appended': False}


def record_source_inventory(ledger: Path, *, release_root: Path, owner_id: str,
                            run_id: str | None, occurrence_id: str | None) -> dict:
    """Capture this execution release's declaration without inferring costs.

    Physical run and claimed occurrence are distinct host identities. Missing
    identity or release evidence produces no invented snapshot or zero cost.
    """
    if (not isinstance(owner_id, str) or not owner_id
            or not isinstance(run_id, str) or not run_id
            or not isinstance(occurrence_id, str) or not occurrence_id.startswith(owner_id + ':')):
        return _gap('source_execution_identity_missing')
    try:
        manifest = json.loads((Path(release_root) / 'RELEASE.json').read_text())
        catalog_bytes = (Path(release_root) / CATALOG_PATH).read_bytes()
        catalog = json.loads(catalog_bytes)
        sha = manifest.get('sha')
        if (not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha)
                or manifest.get('release_paths') != 'ALL'):
            return _gap('source_release_invalid')
        loops = [row for row in catalog['loops'] if row.get('id') == 'investment']
        if len(loops) != 1 or owner_id not in loops[0].get('job_ids', []):
            return _gap('source_owner_invalid')
        declaration = loops[0].get('cost_source_inventory')
        if (not isinstance(declaration, dict) or declaration.get('schema_version') != 1
                or declaration.get('status') not in ('unverified', 'verified')
                or not isinstance(declaration.get('sources'), list)):
            return _gap('source_declaration_unavailable')
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return _gap('source_declaration_unavailable')
    digest = hashlib.sha256(catalog_bytes).hexdigest()
    identity = {'owner_id': owner_id, 'release_sha': sha}
    prepared = {}
    def prepare(existing):
        previous = [row for row in existing if row.get('receipt_type') == 'cost_source_inventory'
                    and all(row.get(key) == value for key, value in identity.items())]
        conflict = any(row.get('catalog_sha256') != digest for row in previous)
        prepared['conflict'] = conflict
        row = {**identity, 'receipt_type': ('cost_source_inventory_conflict' if conflict else 'cost_source_inventory'),
               'schema_version': 1, 'catalog_sha256': digest, 'run_id': run_id, 'occurrence_id': occurrence_id,
               'recorded_at': datetime.now(timezone.utc).isoformat(),
               'evidence_refs': [f'lm-release://{sha}/{CATALOG_PATH.as_posix()}']}
        if not conflict:
            row['source_declaration'] = declaration
            row['execution_owner_ids'] = loops[0]['job_ids']
        return row
    appended = _append_once(Path(ledger), prepare, ('receipt_type', 'owner_id', 'release_sha', 'catalog_sha256'))
    return {'coverage_state': 'gap', 'reason': ('source_declaration_conflict' if prepared['conflict']
            else 'source_inventory_not_evaluated' if declaration['status'] == 'verified'
            else 'source_declaration_unverified'), 'appended': appended,
            'release_sha': sha, 'catalog_sha256': digest}
