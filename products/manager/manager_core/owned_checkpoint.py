"""Private remote checkpoints of the existing SQLite store, never send authority.

Only the gateway owns the remote lease/CAS. A runner restores its latest state
into fresh private scratch; artifact/cache/old local files are not fallbacks.
Missing state requires explicit operator reconciliation and bootstrap.
"""
import base64
from hashlib import sha256
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener
from uuid import uuid4

ENDPOINT = 'https://ulhsqqkyejzvqgoyjwte.supabase.co/functions/v1/manager-owned-state'
MAX_SNAPSHOT = 1024*1024
MAX_RESPONSE = 2*1024*1024
SOURCE_ROOT = Path(__file__).resolve().parents[3]


class CheckpointUnavailable(RuntimeError):
    """No send/retry is allowed on an uncertain private-store transition."""


def github_state_transport(payload):
    """Exchange the job's existing short-lived identity; never export secrets.

    Environment construction alone authenticates nothing. The remote gateway
    verifies GitHub's signature, immutable repository IDs and trusted main job.
    """
    from scripts.phase06_kernel_release import NoRedirect
    try:
        parts = urlsplit(os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'])
        if (parts.scheme != 'https' or not parts.hostname or
                not parts.hostname.endswith('.actions.githubusercontent.com') or
                parts.username or parts.password or parts.port not in (None, 443) or parts.fragment):
            raise ValueError('unexpected identity issuer endpoint')
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != 'audience']
        identity_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                  urlencode(query+[('audience', ENDPOINT)]), ''))
        opener = build_opener(NoRedirect())
        request = Request(identity_url, headers={
            'Authorization': 'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
        with opener.open(request, timeout=20) as response:
            raw = response.read(65537)
            if response.status != 200 or len(raw)>65536: raise ValueError('identity unavailable')
        token = json.loads(raw)['value']
        if not isinstance(token, str) or not token or len(token)>32768:
            raise ValueError('bounded platform token required')
        request = Request(ENDPOINT, data=json.dumps(payload, allow_nan=False).encode(),
                          headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'}, method='POST')
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE+1)
            if response.status != 200 or len(raw)>MAX_RESPONSE: raise ValueError('state unavailable')
        return json.loads(raw)
    except Exception:
        # HTTP errors/URLs/responses may contain private state. Never echo them.
        raise CheckpointUnavailable('private state transition unavailable; reconcile only') from None


def _database_bytes(db):
    """SQLite Backup API includes committed WAL transactions."""
    with TemporaryDirectory() as tmp:
        target = Path(tmp)/'snapshot.sqlite'
        deadline=monotonic()+20
        def bounded_backup(status, remaining, total):
            if monotonic()>deadline: raise TimeoutError('bounded SQLite backup timed out')
        with sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True) as source, \
             sqlite3.connect(target) as destination:
            source.backup(destination,pages=64,progress=bounded_backup)
        _validate_database(target)
        raw = target.read_bytes()
    if len(raw)>MAX_SNAPSHOT: raise ValueError('checkpoint size limit exceeded')
    return raw


def _validate_database(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('invalid SQLite checkpoint')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required_tables={'schedule','control','owned_effects','owned_deliveries','owned_recovery_cursor'}
        if not required_tables <= tables:
            raise ValueError('not an owned cycle checkpoint')
        if db.execute('SELECT id,stopped FROM control').fetchall() not in ([(1,0)], [(1,1)]):
            raise ValueError('invalid owner control state')
        from .digital_handoff import validate_intent
        for key, packet, parent, status, receipt in db.execute(
                'SELECT key,packet_json,expected_parent,status,receipt_ref FROM owned_effects'):
            packet = json.loads(packet); validate_intent(packet)
            if key != packet['effect_key'] or not re.fullmatch('[0-9a-f]{40}', parent):
                raise ValueError('invalid saved occurrence binding')
            if status not in ('DISPATCHING','ALREADY_PRESENT_UNRECONCILED','PRESENT'):
                raise ValueError('invalid saved occurrence status')
            if (status == 'PRESENT') != (isinstance(receipt,str) and bool(re.fullmatch('[0-9a-f]{40}',receipt))):
                raise ValueError('invalid saved provider receipt')
        if 'owned_rollbacks' in tables:
            from .outbox import validate_owned_rollback
            rollback_columns={row[1] for row in db.execute('PRAGMA table_info(owned_rollbacks)')}
            if {'delivery_status','delivery_json'}<=rollback_columns:
                rollback_rows=db.execute('''SELECT key,packet_json,status,receipt_ref,
                    delivery_status,delivery_json FROM owned_rollbacks''').fetchall()
            else:
                rollback_rows=[(key,packet,status,receipt,'UNKNOWN',None) for
                    key,packet,status,receipt in db.execute(
                        'SELECT key,packet_json,status,receipt_ref FROM owned_rollbacks')]
            for key, packet_json, status, receipt, delivery_status, delivery_json in rollback_rows:
                packet=json.loads(packet_json); validate_owned_rollback(packet)
                if key != packet['effect_key'] or status not in ('DISPATCHING','PRESENT'):
                    raise ValueError('invalid saved rollback binding')
                if (status == 'PRESENT') != (isinstance(receipt,str) and
                                              bool(re.fullmatch('[0-9a-f]{40}',receipt))):
                    raise ValueError('invalid saved rollback receipt')
                original=db.execute('''SELECT packet_json,expected_parent,status,receipt_ref
                    FROM owned_effects WHERE key=?''',
                    (packet['candidate_effect_key'],)).fetchone()
                if original is None:
                    raise ValueError('rollback is detached from its candidate receipt')
                original_packet=json.loads(original[0])
                if (original[2]!='PRESENT' or
                        original[3]!=packet['candidate_commit'] or
                        original[1]!=packet['parent_commit'] or
                        original_packet.get('schema')!='manager.digital-handoff.v2' or
                        original_packet.get('baseline')!=packet['baseline'] or
                        original_packet.get('candidate')!=packet['candidate'] or
                        original_packet.get('baseline_sha256')!=packet['baseline_sha256'] or
                        original_packet.get('candidate_sha256')!=packet['candidate_sha256']):
                    raise ValueError('rollback candidate receipt binding changed')
                if delivery_status not in ('UNKNOWN','PENDING','VERIFIED'):
                    raise ValueError('invalid saved rollback delivery state')
                if delivery_json is None:
                    if delivery_status!='UNKNOWN':
                        raise ValueError('missing saved rollback delivery')
                    continue
                evidence=json.loads(delivery_json);intent=packet
                if (status!='PRESENT' or evidence.get('effect_key')!=key or
                        evidence.get('receipt_ref')!=receipt or
                        evidence.get('baseline_sha256')!=intent['baseline_sha256'] or
                        evidence.get('status')!=delivery_status or
                        evidence.get('human_outcome')!='NOT_MEASURED' or
                        evidence.get('proof_level') not in ('P0','P2') or
                        (delivery_status=='VERIFIED' and evidence.get('proof_level')!='P2')):
                    raise ValueError('invalid saved rollback delivery binding')
                from .models.source import _aware
                _aware(datetime.fromisoformat(evidence['observed_at']))
        from .owned_provider import validate_provider_tables
        validate_provider_tables(db, tables)


class PrivateCheckpoint:
    """One lease/session; any uncertain transition permanently fences this object.

    `save` returns revision/hash data only. It never grants dispatch permission.
    Production callers must persist reservations before their existing publisher
    admission and must not retry a send after a lost response.
    """
    def __init__(self, transport=github_state_transport, *, run_id, run_attempt):
        if any(type(v) is not str or not re.fullmatch('[1-9][0-9]*',v) for v in (run_id,run_attempt)):
            raise ValueError('exact platform run identity required')
        self.transport=transport; self.nonce=str(uuid4())
        self.owner=f'{run_id}:{run_attempt}:{self.nonce}'
        self.revision=None; self.db=None; self.broken=False

    def _transition(self, operation, **fields):
        if self.broken: raise CheckpointUnavailable('private session fenced; reconcile only')
        try:
            value=self.transport(dict(operation=operation,nonce=self.nonce,**fields))
            if (type(value) is not dict or set(value)!={'revision','sha256','snapshot','owner'} or
                    type(value['revision']) is not int or not 0<=value['revision']<=2**53-1 or
                    type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['sha256']) or
                    type(value['snapshot']) is not str or len(value['snapshot'])>MAX_RESPONSE or
                    value['owner'] != (None if operation=='release' else self.owner)):
                raise ValueError('invalid checkpoint response')
            raw=base64.b64decode(value['snapshot'],validate=True)
            if len(raw)>MAX_SNAPSHOT or sha256(raw).hexdigest()!=value['sha256']:
                raise ValueError('invalid checkpoint bytes')
            return value,raw
        except BaseException as exc:
            self.broken=True
            if isinstance(exc, Exception):
                raise CheckpointUnavailable('private state transition uncertain; reconcile only') from None
            raise

    def acquire(self, root):
        if self.db is not None or self.broken:
            raise CheckpointUnavailable('fresh private session required')
        root=Path(root).absolute()
        if (any(p.is_symlink() for p in (root,*root.parents)) or
                root==SOURCE_ROOT or SOURCE_ROOT in root.parents or
                (root.exists() and (any(root.iterdir()) or root.stat().st_mode & 0o077))):
            raise CheckpointUnavailable('fresh private scratch outside source required')
        value,raw=self._transition('acquire')
        try:
            # Validate before installing or allowing CycleStore to create tables.
            with TemporaryDirectory() as tmp:
                scratch=Path(tmp)/'checkpoint.sqlite'; scratch.write_bytes(raw)
                _validate_database(scratch)
            root.mkdir(parents=True,exist_ok=True,mode=0o700)
            self.db=root/'cycle.sqlite'
            fd=os.open(self.db,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as file:
                file.write(raw); file.flush(); os.fsync(file.fileno())
            self.revision=value['revision']
            return self.db
        except Exception:
            self.broken=True
            raise CheckpointUnavailable('checkpoint restore refused; reconcile only') from None

    def save(self):
        if self.db is None or self.broken: raise CheckpointUnavailable('active private session required')
        try:
            _validate_database(self.db); raw=_database_bytes(self.db)
            checksum=sha256(raw).hexdigest()
            value,_=self._transition('checkpoint',revision=self.revision,
                sha256=checksum,snapshot=base64.b64encode(raw).decode())
            if value['revision']!=self.revision+1 or value['sha256']!=checksum:
                raise ValueError('checkpoint CAS acknowledgement differs')
            self.revision=value['revision']
            return dict(revision=self.revision,sha256=checksum)
        except BaseException as exc:
            self.broken=True
            if isinstance(exc, Exception):
                raise CheckpointUnavailable('checkpoint save uncertain; reconcile only') from None
            raise

    def release(self):
        if self.db is None or self.broken: raise CheckpointUnavailable('active private session required')
        value,_=self._transition('release')
        if value['revision']!=self.revision:
            self.broken=True
            raise CheckpointUnavailable('checkpoint revision changed; reconcile only')
        self.broken=True  # released sessions never regain send capability
