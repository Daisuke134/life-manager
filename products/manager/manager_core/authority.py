"""K007: HMAC-verifiable OFFLINE grants; not a substitute for live legal authority.

Fixture signing is exposed only to construct test grants. Live effects remain
disabled regardless of any signature. A real deployment needs separated issuer,
key storage, revocation service, authorization policy and legal review.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
from math import isfinite
from typing import Mapping
from .models.source import _text, _aware


@dataclass(frozen=True)
class Grant:
    grant_id: str
    issuer: str
    domain: str
    action: str
    target: str
    limit: float
    not_before: datetime
    expires_at: datetime

    def __post_init__(self):
        for key in ("grant_id", "issuer", "domain", "action", "target"):
            _text(getattr(self,key))
        _aware(self.not_before)
        _aware(self.expires_at)
        if self.expires_at <= self.not_before:
            raise ValueError("grant expiry must be after start")
        if type(self.limit) not in (int,float) or not isfinite(self.limit) or not 0 < self.limit <= 1e9:
            raise ValueError("positive bounded grant budget required")


def _payload(grant: Grant) -> bytes:
    data=asdict(grant)
    data["not_before"]=grant.not_before.isoformat()
    data["expires_at"]=grant.expires_at.isoformat()
    return json.dumps(data,sort_keys=True,separators=(",",":")).encode("utf-8")


class AuthorityVerifier:
    def __init__(self, trusted_issuer_keys: Mapping[str,bytes], revoked=()):
        if not isinstance(trusted_issuer_keys, Mapping) or not trusted_issuer_keys:
            raise ValueError("explicit trusted issuer registry required")
        if any(not isinstance(k,str) or not isinstance(v,bytes) or len(v)<16
               for k,v in trusted_issuer_keys.items()):
            raise ValueError("issuer IDs and at least 128-bit fixture keys required")
        self._trusted=dict(trusted_issuer_keys)
        self._revoked=frozenset(revoked)

    def sign_for_fixture(self, grant: Grant) -> str:
        """Test-only issuer simulator; NOT usable to turn on live effects."""
        if grant.issuer not in self._trusted:
            raise PermissionError("untrusted issuer")
        return hmac_new(self._trusted[grant.issuer],_payload(grant),sha256).hexdigest()

    def authorize(self, grant: Grant, signature: str, domain: str, action: str,
                  target: str, cost: float, at: datetime) -> bool:
        if not isinstance(grant,Grant) or grant.issuer not in self._trusted:
            raise PermissionError("no trusted grant")
        if not isinstance(signature,str):
            raise PermissionError("missing signature")
        expected=hmac_new(self._trusted[grant.issuer],_payload(grant),sha256).hexdigest()
        if not compare_digest(signature,expected):
            raise PermissionError("invalid signature")
        _aware(at)
        if grant.grant_id in self._revoked or not grant.not_before <= at < grant.expires_at:
            raise PermissionError("revoked, not-yet-valid or expired grant")
        if (domain,action,target)!=(grant.domain,grant.action,grant.target):
            raise PermissionError("outside grant scope")
        if type(cost) not in (int,float) or not isfinite(cost) or cost < 0 or cost > grant.limit:
            raise PermissionError("outside grant budget")
        return True


@dataclass(frozen=True)
class OwnedDigitalScope:
    """Host configuration for feasibility, NOT authenticated publisher authority.

    Actual effects still require the original privileged platform admission.
    This is not signed by fixture keys or accepted from provider advice JSON.
    """
    scope_id: str
    allowed_paths: frozenset[str]
    not_before: datetime
    expires_at: datetime
    max_changed_files: int
    revoked: bool = False

    def __post_init__(self):
        from .digital_handoff import ALLOWED_PATHS
        _text(self.scope_id);_aware(self.not_before);_aware(self.expires_at)
        if (type(self.allowed_paths) is not frozenset or not self.allowed_paths
                or not self.allowed_paths<=set(ALLOWED_PATHS)
                or self.expires_at<=self.not_before
                or type(self.max_changed_files) is not int or not 1<=self.max_changed_files<=len(ALLOWED_PATHS)
                or type(self.revoked) is not bool):raise ValueError('bounded host-owned digital scope required')

    def allows(self,target: str,at: datetime):
        _aware(at)
        return not self.revoked and self.not_before<=at<self.expires_at and target in self.allowed_paths
