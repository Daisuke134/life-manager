"""Persistent append-only public source history, never execution authority."""
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
from .public_observer import FetchedSnapshot
from .models.source import Source,_aware
from .collaboration import PlannerContext,PublicFact,render_prompt


class _VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','head','nav','footer'}:self.depth+=1
    def handle_endtag(self,tag):
        if tag in {'script','style','head','nav','footer'} and self.depth:self.depth-=1
    def handle_data(self,data):
        if not self.depth:self.parts.append(data)


def _excerpt(body):
    text=body.decode('utf-8',errors='replace')
    parser=_VisibleText();parser.feed(text)
    visible=' '.join(' '.join(parser.parts).split())
    return 'SOURCE EXCERPT (untrusted): '+(visible[:570] if visible else '[no visible text extracted]')


class WorldState:
    def __init__(self,path: str | Path):
        if str(path)==':memory:':raise ValueError('persistent world state path required')
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS world_observations (
              ref TEXT PRIMARY KEY,scope TEXT NOT NULL,source_id TEXT NOT NULL,
              source_json TEXT NOT NULL,body_hash TEXT NOT NULL,body BLOB NOT NULL,
              collected_at TEXT NOT NULL,transport_scope TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS world_current (
              scope TEXT NOT NULL,source_id TEXT NOT NULL,ref TEXT NOT NULL,
              checked_at TEXT NOT NULL,PRIMARY KEY(scope,source_id));
            CREATE TABLE IF NOT EXISTS world_events (
              id INTEGER PRIMARY KEY,scope TEXT NOT NULL,source_id TEXT NOT NULL,
              old_ref TEXT,new_ref TEXT NOT NULL,observed_at TEXT NOT NULL,reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS world_corrections (
              old_ref TEXT NOT NULL,new_ref TEXT NOT NULL,PRIMARY KEY(old_ref,new_ref));
            ''')

    def ingest(self,snapshot: FetchedSnapshot,*,scope='public_information') -> str:
        if type(snapshot) is not FetchedSnapshot or type(scope) is not str or not scope.strip() or len(scope)>500:
            raise ValueError('typed acquired snapshot and bounded scope required')
        source=snapshot.source;source.verify_content(snapshot.body)
        when=snapshot.collected_at.isoformat()
        metadata=json.dumps(dict(url=source.url,license_id=source.license_id,rights=source.rights,
                                 privacy_class=source.privacy_class),sort_keys=True)
        identity=dict(scope=scope,source_id=source.source_id,body_hash=snapshot.body_sha256,
                      collected_at=when,source_metadata=metadata)
        ref=source.source_id+':'+sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        db=sqlite3.connect(self.path,timeout=15,isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('''SELECT c.ref,c.checked_at,o.body_hash,o.source_json
               FROM world_current c JOIN world_observations o ON c.ref=o.ref
               WHERE c.scope=? AND c.source_id=?''',(scope,source.source_id)).fetchone()
            if old and snapshot.collected_at<datetime.fromisoformat(old[1]):
                if old[2]!=snapshot.body_sha256 or old[3]!=metadata:
                    raise ValueError('late old retrieval cannot supersede current source')
                db.execute('COMMIT');return old[0]
            if old and old[2]==snapshot.body_sha256 and old[3]==metadata:
                db.execute('UPDATE world_current SET checked_at=? WHERE scope=? AND source_id=?',
                           (when,scope,source.source_id));db.execute('COMMIT');return old[0]
            if old and snapshot.collected_at==datetime.fromisoformat(old[1]):
                raise ValueError('conflicting bytes at identical source/time')
            db.execute('INSERT INTO world_observations VALUES (?,?,?,?,?,?,?,?)',
                (ref,scope,source.source_id,metadata,snapshot.body_sha256,snapshot.body,when,snapshot.transport_scope))
            db.execute('INSERT INTO world_current VALUES (?,?,?,?) ON CONFLICT(scope,source_id) DO UPDATE SET ref=excluded.ref,checked_at=excluded.checked_at',
                       (scope,source.source_id,ref,when))
            db.execute('INSERT INTO world_events(scope,source_id,old_ref,new_ref,observed_at,reason) VALUES (?,?,?,?,?,?)',
                       (scope,source.source_id,old[0] if old else None,ref,when,'CONTENT_CHANGED' if old else 'FIRST_OBSERVATION'))
            db.execute('COMMIT');return ref
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise
        finally:db.close()

    def context_at(self,scope: str,now: datetime) -> PlannerContext:
        _aware(now)
        with sqlite3.connect(self.path) as db:
            rows=db.execute('''SELECT o.ref,o.source_json,o.body_hash,o.body,c.checked_at
              FROM world_current c JOIN world_observations o ON c.ref=o.ref
              WHERE c.scope=? ORDER BY c.source_id''',(scope,)).fetchall()
        facts=[]
        for ref,metadata,digest,body,checked in rows:
            data=json.loads(metadata)
            source=Source(source_id=ref,content_sha256=digest,retrieved_at=datetime.fromisoformat(checked),**data)
            source.require_fresh(now,max_age_hours=48);source.verify_content(body)
            facts.append(PublicFact(source,_excerpt(body)))
        return PlannerContext(scope,tuple(facts),now)

    def context_hash(self,scope: str,now: datetime) -> str:
        return sha256(render_prompt(self.context_at(scope,now)).encode()).hexdigest()

    def validate_current_refs(self,refs,scope: str,now: datetime):
        context=self.context_at(scope,now)
        if type(refs) is not tuple or not set(refs)<={f.source.source_id for f in context.facts}:
            raise ValueError('superseded, unknown or untyped current citations')
        return True

    def supersede(self,old_ref: str,new_ref: str):
        with sqlite3.connect(self.path) as db:
            old=db.execute('SELECT scope,source_id FROM world_observations WHERE ref=?',(old_ref,)).fetchone()
            new=db.execute('SELECT scope,source_id FROM world_observations WHERE ref=?',(new_ref,)).fetchone()
            current=db.execute('SELECT ref FROM world_current WHERE ref=?',(new_ref,)).fetchone()
            if not old or old!=new or not current or old_ref==new_ref:
                raise ValueError('correction must link same source to its actual current version')
            db.execute('INSERT OR IGNORE INTO world_corrections VALUES (?,?)',(old_ref,new_ref))

    def event_count(self):
        with sqlite3.connect(self.path) as db:return db.execute('SELECT COUNT(*) FROM world_events').fetchone()[0]
