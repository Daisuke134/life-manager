"""K012: persistent shadow/holdout promotion with automatic regression rollback.

No policy ever changes its own authority or enables external effects. Small,
fail-closed offline candidate registry; policy scores are not field outcomes.
"""
import json
from math import isfinite
from pathlib import Path
import sqlite3
from .calibration import assert_disjoint_groups


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
