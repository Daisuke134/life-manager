"""Private LM dispatch receipts, not an OpenClaw session or business ledger.

Persist dispatching before RPC. A missing ACK stays unknown; reconciliation,
not a second send, owns recovery. All transitions are compare-and-swap under
one task lock. Callers must never delete receipts to retry a business effect.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

FIELDS = {'version', 'owner_id', 'occurrence_id', 'task_id', 'session_key',
          'upstream_run_id', 'claim_ref', 'request_digest', 'phase'}
TRANSITIONS = {'prepared': {'dispatching'}, 'dispatching': {'accepted', 'unknown', 'terminal'},
               'accepted': {'unknown', 'terminal'}, 'unknown': {'accepted', 'terminal'}, 'terminal': set()}

def dispatch_key(owner_id, occurrence_id, task_id):
    for value in (owner_id, occurrence_id, task_id):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}',value) or '..' in value:
            raise ValueError('invalid dispatch identity')
    encoded=json.dumps([owner_id,occurrence_id,task_id],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(encoded.encode()).hexdigest()

def _root(root, create=False):
    root=Path(root)
    if not root.is_absolute():raise ValueError('dispatch root must be absolute')
    for p in [*reversed(root.parents),root]:
        if p.is_symlink():raise ValueError('symlink in dispatch root')
    if create:root.mkdir(parents=True,mode=0o700,exist_ok=True)
    if root.exists():
        s=root.stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode & 0o077:
            raise ValueError('dispatch root is not private')
    return root

def _check_fd(fd):
    s=os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1:
        raise ValueError('dispatch file is not private')

def _validate(v):
    if not isinstance(v,dict) or set(v)!=FIELDS or type(v['version']) is not int or v['version']!=2:
        raise ValueError('invalid dispatch shape')
    dispatch_key(v['owner_id'],v['occurrence_id'],v['task_id'])
    if v['phase'] not in TRANSITIONS or not isinstance(v['session_key'],str) or not v['session_key'].startswith('agent:'):
        raise ValueError('invalid dispatch phase or session')
    if not isinstance(v['request_digest'],str) or not re.fullmatch('[a-f0-9]{64}',v['request_digest']):
        raise ValueError('invalid request digest')
    if v['upstream_run_id'] is not None and (not isinstance(v['upstream_run_id'],str) or not v['upstream_run_id']):
        raise ValueError('invalid upstream identity')
    if v['phase']=='accepted' and not v['upstream_run_id']:raise ValueError('accepted needs upstream identity')
    if v['claim_ref'] is not None and (not isinstance(v['claim_ref'],str) or not Path(v['claim_ref']).is_absolute()):
        raise ValueError('invalid claim reference')

def _read(path, identity):
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:return None
    except OSError as e:raise ValueError('unsafe dispatch file') from e
    try:
        _check_fd(fd)
        with os.fdopen(fd,'r',encoding='utf-8',closefd=False) as f:
            text=f.read(16385)
        if len(text)>16384:raise ValueError('oversized dispatch record')
        v=json.loads(text);_validate(v)
        if tuple(v[k] for k in ('owner_id','occurrence_id','task_id'))!=identity:
            raise ValueError('foreign dispatch record')
        return v
    finally:os.close(fd)

def load_dispatch(root, owner_id, occurrence_id, task_id):
    key=dispatch_key(owner_id,occurrence_id,task_id)
    root=_root(root)
    return _read(root/(key+'.json'),(owner_id,occurrence_id,task_id))

@contextmanager
def _lock(root,key):
    try:fd=os.open(root/(key+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    except OSError as e:raise ValueError('unsafe dispatch lock') from e
    try:
        _check_fd(fd);fcntl.flock(fd,fcntl.LOCK_EX);yield
    finally:os.close(fd)

def save_dispatch(root, record, *, expected_phase):
    _validate(record)
    identity=tuple(record[k] for k in ('owner_id','occurrence_id','task_id'))
    key=dispatch_key(*identity);root=_root(root,create=True);path=root/(key+'.json')
    with _lock(root,key):
        old=_read(path,identity)
        if (old['phase'] if old else None)!=expected_phase:raise ValueError('dispatch compare-and-swap conflict')
        if old:
            for k in FIELDS-{'phase','upstream_run_id'}:
                if old[k]!=record[k]:raise ValueError('dispatch binding changed')
            if old['upstream_run_id'] and old['upstream_run_id']!=record['upstream_run_id']:
                raise ValueError('upstream binding changed')
            if record['phase'] not in TRANSITIONS[old['phase']]:raise ValueError('dispatch cannot be replayed')
        elif record['phase']!='prepared':raise ValueError('first dispatch must be prepared')
        fd,name=tempfile.mkstemp(prefix='.'+key+'.',dir=root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump(record,f,ensure_ascii=False,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
            os.replace(name,path)
            directory=os.open(root,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(name):os.unlink(name)
    return path
