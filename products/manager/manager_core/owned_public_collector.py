"""Bounded fixed-origin public GET collectors; supplied transport is P0 only.

Provider occurrence and current delivery are separate observations. No function
here issues a write, infers absence or authorizes a retry/rollback.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re

from .digital_handoff import (REPOSITORY, PUBLIC_BASE, commit_message,
                              validate_commit_receipt, verify_readback)
from .models.source import _aware
from .reconcile import OwnedOccurrenceEvidence


@dataclass(frozen=True)
class DeliveryObservation:
    status: str
    reason: str
    proof_ref: str

    def __post_init__(self):
        if self.status not in ('VERIFIED', 'PENDING', 'REGRESSION', 'UNKNOWN'):
            raise ValueError('typed delivery status required')


def collect_owned_occurrence(key, journal, observed_at=None, *, get=None, max_pages=5):
    """Find the exact saved effect across bounded gh-pages commit pages.

    A missing result/page limit/network error is UNKNOWN, never proven absence.
    An injected transport exercises the validator, not authenticated collection.
    """
    from scripts.phase06_kernel_release import public_get, immutable_snapshot
    observed_at=observed_at or datetime.now(timezone.utc); _aware(observed_at)
    if type(max_pages) is not int or not 1<=max_pages<=10:
        raise ValueError('bounded provider pagination required')
    record=journal.record(key)
    if record is None: raise ValueError('saved owned intent required')
    packet=json.loads(record.packet_json); message=commit_message(packet)
    read=get or public_get
    try:
        for page in range(1,max_pages+1):
            rows=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page={page}'))
            if type(rows) is not list or len(rows)>100: return None
            for row in rows:
                if not isinstance(row,dict) or row.get('commit',{}).get('message','').strip()!=message:
                    continue
                sha=row.get('sha')
                if type(sha) is not str or not re.fullmatch('[0-9a-f]{40}',sha): continue
                try:
                    receipt=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'))
                    if receipt.get('sha')!=sha: continue
                    if receipt['parents']!=[{'sha':record.expected_parent}]:
                        # GitHub parent objects contain additional public fields.
                        if len(receipt['parents'])!=1 or receipt['parents'][0].get('sha')!=record.expected_parent:
                            continue
                    manifest,bodies=immutable_snapshot(sha,get=read)
                    parent,old_bodies=immutable_snapshot(record.expected_parent,get=read)
                    validate_commit_receipt(packet,receipt,manifest,observed_at,
                        committed_bodies=bodies,parent_commit=record.expected_parent,
                        parent_manifest=parent,parent_bodies=old_bodies)
                    return OwnedOccurrenceEvidence(receipt,manifest,bodies,
                                                    record.expected_parent,parent,old_bodies)
                except (ValueError,KeyError,TypeError,OSError):
                    continue
            if len(rows)<100: break
    except (ValueError,KeyError,TypeError,OSError):
        return None
    return None


def collect_owned_delivery(key, journal, observed_at=None, *, get=None):
    """Verify currently served candidate bytes independently of provider success.

    Public mismatch cannot bind corrupted bytes to a completed deployment, so
    this collector alone never reports REGRESSION or requests rollback.
    """
    from scripts.phase06_kernel_release import served_snapshot
    observed_at=observed_at or datetime.now(timezone.utc); _aware(observed_at)
    record=journal.record(key)
    if record is None or record.status!='PRESENT':
        raise ValueError('validated provider occurrence required before delivery')
    packet=json.loads(record.packet_json)
    result=dict(status='UNKNOWN',effect_key=key,receipt_ref=record.receipt_ref,
                candidate_sha256=packet['candidate_sha256'],observed_at=observed_at.isoformat(),
                proof_ref=PUBLIC_BASE,proof_level='P0',reason='DELIVERY_UNCONFIRMED',
                human_outcome='NOT_MEASURED')
    try:
        manifest,bodies=served_snapshot(get=get)
        if manifest!=packet['candidate']:
            return dict(result,status='PENDING',reason='DIFFERENT_SERVED_VERSION')
        verify_readback(packet['candidate'],bodies)
    except (ValueError,KeyError,TypeError,OSError):
        return result
    return dict(result,status='VERIFIED',reason='EXACT_SERVED_CANDIDATE',
                proof_level='P0' if get is not None else 'P2')
