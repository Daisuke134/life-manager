"""K012: persistent shadow/holdout promotion with automatic regression rollback.

No policy ever changes its own authority or enables external effects. Small,
fail-closed offline candidate registry; policy scores are not field outcomes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from .calibration import assert_disjoint_groups
from .models.source import _aware


@dataclass(frozen=True)
class NativeTechnicalObservation:
    """One private, source-bound technical fact from an authorized collector.

    Construction validates shape and binding syntax. It does not authenticate a
    caller, validate a provider receipt, or grant authority to publish evidence.
    The host must call this API only after its existing journal/provider checks.
    """
    effect_key: str
    candidate_sha256: str
    receipt_ref: str
    observed_at: datetime
    measure_id: str
    unit: str
    status: str
    proof_level: str
    native_value: int | float | None
    missing_reason: str | None
    human_outcome: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self):
        if type(self.effect_key) is not str or not re.fullmatch(r'[0-9a-f]{64}', self.effect_key):
            raise ValueError('exact effect key required')
        if type(self.candidate_sha256) is not str or not re.fullmatch(r'[0-9a-f]{64}', self.candidate_sha256):
            raise ValueError('exact candidate SHA-256 required')
        if type(self.receipt_ref) is not str or not re.fullmatch(r'[0-9a-f]{40}', self.receipt_ref):
            raise ValueError('exact provider receipt commit required')
        if type(self.observed_at) is not datetime:
            raise ValueError('aware observation time required')
        _aware(self.observed_at)
        if (type(self.measure_id) is not str or
                not re.fullmatch(r'[a-z][a-z0-9_.-]{1,127}', self.measure_id)):
            raise ValueError('canonical measure id required')
        if type(self.unit) is not str or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', self.unit):
            raise ValueError('canonical measurement unit required')
        if type(self.status) is not str or self.status not in ('VERIFIED', 'PENDING', 'REGRESSION', 'UNKNOWN'):
            raise ValueError('typed native observation status required')
        if type(self.proof_level) is not str or self.proof_level not in ('P1', 'P2'):
            raise ValueError('native observations require exact P1 or P2 proof')
        if type(self.human_outcome) is not str or self.human_outcome != 'NOT_MEASURED':
            raise ValueError('human outcome must remain NOT_MEASURED')
        if self.status in ('PENDING', 'UNKNOWN'):
            if self.native_value is not None or type(self.missing_reason) is not str or not self.missing_reason.strip():
                raise ValueError('missing technical values require null and a reason')
        else:
            try:
                finite_native_value = type(self.native_value) in (int, float) and isfinite(float(self.native_value))
            except (OverflowError, ValueError):
                finite_native_value = False
            if not finite_native_value or self.missing_reason is not None:
                raise ValueError('verified technical values must be finite and complete')
        if (type(self.missing_reason) is str and
                (not self.missing_reason.strip() or len(self.missing_reason) > 256)):
            raise ValueError('bounded missing reason required')
        if type(self.provenance_refs) is not tuple or not self.provenance_refs:
            raise ValueError('immutable provenance reference tuple required')
        for ref in self.provenance_refs:
            if type(ref) is not str or len(ref) > 2048 or ref != ref.strip():
                raise ValueError('bounded provenance URL required')
            parsed = urlsplit(ref)
            if (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or
                    parsed.query or parsed.fragment):
                raise ValueError('canonical HTTPS provenance reference required')
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ValueError('duplicate provenance reference')

    def canonical_payload(self):
        """Return the fixed schema stored in the private native table."""
        return {
            'effect_key': self.effect_key,
            'candidate_sha256': self.candidate_sha256,
            'receipt_ref': self.receipt_ref,
            'observed_at': self.observed_at.astimezone(timezone.utc).isoformat(),
            'measure_id': self.measure_id,
            'unit': self.unit,
            'status': self.status,
            'proof_level': self.proof_level,
            'native_value': self.native_value,
            'missing_reason': self.missing_reason,
            'human_outcome': self.human_outcome,
            'provenance_refs': sorted(self.provenance_refs),
        }


def _loss(value):
    if type(value) not in (int,float) or not isfinite(value) or not 0<=value<=1:
        raise ValueError("bounded finite loss required")
    return float(value)


class PolicyLearner:
    def __init__(self,path:str|Path):
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS policies (
                version TEXT PRIMARY KEY, holdout_loss REAL NOT NULL,
                shadow_loss REAL NOT NULL, train_ids TEXT NOT NULL,
                test_ids TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS active_policy (
                id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL,
                previous TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_technical_observations (
                observation_id TEXT PRIMARY KEY,
                effect_key TEXT NOT NULL,
                candidate_sha256 TEXT NOT NULL,
                receipt_ref TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                measure_id TEXT NOT NULL,
                unit TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('VERIFIED','PENDING','REGRESSION','UNKNOWN')),
                proof_level TEXT NOT NULL CHECK(proof_level IN ('P1','P2')),
                native_value REAL,
                missing_reason TEXT,
                human_outcome TEXT NOT NULL CHECK(human_outcome='NOT_MEASURED'),
                provenance_refs_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(effect_key,candidate_sha256,receipt_ref,observed_at,measure_id)
            )""")

    def initialize(self,version):
        if not isinstance(version,str) or not version.strip():
            raise ValueError("version required")
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT version FROM active_policy WHERE id=1").fetchone()
            if row and row[0]!=version:
                raise ValueError("already initialized under another active version")
            db.execute("INSERT OR IGNORE INTO active_policy VALUES (1,?,NULL)",(version,))

    def active(self):
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT version FROM active_policy WHERE id=1").fetchone()
            return row[0] if row else None

    def propose(self,version,holdout_loss,shadow_loss,train_ids,test_ids):
        if not isinstance(version,str) or not version.strip():
            raise ValueError("valid version id required")
        h,s=_loss(holdout_loss),_loss(shadow_loss)
        assert_disjoint_groups(train_ids,test_ids)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO policies VALUES (?,?,?,?,?)",
                       (version,h,s,json.dumps(list(train_ids)),json.dumps(list(test_ids))))

    def promote(self,version,*,baseline_loss):
        base=_loss(baseline_loss)
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT holdout_loss,shadow_loss FROM policies WHERE version=?",(version,)).fetchone()
            current=db.execute("SELECT version FROM active_policy WHERE id=1").fetchone()
            if not row or not current:
                raise ValueError("existing candidate and initialized policy required")
            if row[0]>=base or row[1]>base:
                return False
            db.execute("UPDATE active_policy SET previous=version,version=? WHERE id=1",(version,))
            return True

    def observe_loss(self,observed_loss,*,max_allowed_loss):
        loss,threshold=_loss(observed_loss),_loss(max_allowed_loss)
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT version,previous FROM active_policy WHERE id=1").fetchone()
            if not row: raise ValueError("no current policy")
            if loss>threshold and row[1]:
                db.execute("UPDATE active_policy SET version=?,previous=NULL WHERE id=1",(row[1],))
                return row[1]
            return row[0]

    def record_sandbox_technical(self,event):
        """Store native sandbox verdicts separately from scalar policy losses.

        No promotion, human-benefit score or public proof level is inferred.
        UNKNOWN remains an explicit observation with no numerical loss.
        """
        if (type(event) is not dict or event.get('proof_level')!='P0'
                or event.get('human_outcome')!='NOT_MEASURED' or event.get('deployed') is not False
                or type(event.get('status')) is not str):
            raise ValueError('explicit sandbox technical observation required')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sandbox_technical_observations(id INTEGER PRIMARY KEY,event_json TEXT NOT NULL)')
            db.execute('INSERT INTO sandbox_technical_observations(event_json) VALUES(?)',(json.dumps(event,sort_keys=True,allow_nan=False),))

    def sandbox_technical_observations(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sandbox_technical_observations(id INTEGER PRIMARY KEY,event_json TEXT NOT NULL)')
            return [json.loads(row[0]) for row in db.execute('SELECT event_json FROM sandbox_technical_observations ORDER BY id')]

    def record_native_technical_observation(self, observation):
        """Append one validated P1/P2 fact; P0 and caller JSON are not accepted.

        Identity binds one exact effect/candidate/receipt/time/measure snapshot.
        An identical replay returns the same ID; a conflicting replay fails and
        historical rows are never updated to reflect current delivery state.
        """
        if type(observation) is not NativeTechnicalObservation:
            raise TypeError('NativeTechnicalObservation required')
        payload = observation.canonical_payload()
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        identity = {name: payload[name] for name in (
            'effect_key', 'candidate_sha256', 'receipt_ref', 'observed_at', 'measure_id')}
        observation_id = sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with sqlite3.connect(self.path, timeout=15, isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload_json FROM native_technical_observations WHERE observation_id=?',
                             (observation_id,)).fetchone()
            if row is not None:
                if row[0] != encoded:
                    db.execute('ROLLBACK')
                    raise ValueError('conflicting immutable native observation')
                db.execute('COMMIT')
                return observation_id
            db.execute('''INSERT INTO native_technical_observations
                (observation_id,effect_key,candidate_sha256,receipt_ref,observed_at,measure_id,unit,
                 status,proof_level,native_value,missing_reason,human_outcome,provenance_refs_json,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (observation_id, payload['effect_key'], payload['candidate_sha256'], payload['receipt_ref'],
                 payload['observed_at'], payload['measure_id'], payload['unit'], payload['status'],
                 payload['proof_level'], payload['native_value'], payload['missing_reason'],
                 payload['human_outcome'], json.dumps(payload['provenance_refs'], separators=(',', ':')), encoded))
            db.execute('COMMIT')
        return observation_id

    def native_technical_observations(self, *, effect_key=None):
        """Read typed private observations in immutable insertion identity order."""
        with sqlite3.connect(self.path, timeout=15) as db:
            if effect_key is None:
                rows = db.execute('SELECT payload_json FROM native_technical_observations ORDER BY rowid').fetchall()
            else:
                if type(effect_key) is not str or not re.fullmatch(r'[0-9a-f]{64}', effect_key):
                    raise ValueError('exact effect key required')
                rows = db.execute('''SELECT payload_json FROM native_technical_observations
                                     WHERE effect_key=? ORDER BY rowid''', (effect_key,)).fetchall()
        result = []
        for (encoded,) in rows:
            payload = json.loads(encoded)
            result.append(NativeTechnicalObservation(
                **{**payload, 'observed_at': datetime.fromisoformat(payload['observed_at']),
                   'provenance_refs': tuple(payload['provenance_refs'])}))
        return result
