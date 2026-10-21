"""K013: restricted public trace with SHA-256 linked events, NOT a tamper-proof ledger.

An operator controlling SQLite can replace the chain; independent publication
or cryptographic signature is required for genuine immutability.
"""
import hashlib
import json
import sqlite3
from pathlib import Path


SAFE_FIELDS={
    "source_id","measure_id","problem_id","hypothesis","alternative",
    "option_id","decision","reason","grant_id","effect_key",
    "receipt_ref","readback_ref","status","comparator","net_impact",
    "uncertainty","proof_level","policy_version","benefit_status","state",
}
STAGES={
    "source","observation","hypothesis","proposal","risk","authorization",
    "execution","reconciliation","verification","evaluation","learning","decision",
}


def _canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False)


class AuditTrail:
    def __init__(self,path:str|Path):
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL, seq INTEGER NOT NULL, stage TEXT NOT NULL,
                data_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
                digest TEXT NOT NULL, PRIMARY KEY (run_id,seq))""")

    def append(self,run_id,stage,data):
        if not isinstance(run_id,str) or not run_id.strip() or len(run_id)>256:
            raise ValueError("valid scoped run id required")
        if stage not in STAGES or not isinstance(data,dict) or not data or not set(data)<=SAFE_FIELDS:
            raise ValueError("unapproved public audit field or stage")
        for key,val in data.items():
            if isinstance(val,(dict,list,tuple)) or not isinstance(val,(str,int,float,type(None))) or isinstance(val,bool):
                raise ValueError("public audit values must be bounded primitives")
            if isinstance(val,str) and (len(val)>1024 or any(s in val.lower() for s in (
                    "password","secret","api_key","bearer ","private key"))):
                raise ValueError("possible credential in public trace")
        serialized=_canonical(data)
        with sqlite3.connect(self.path,timeout=15,isolation_level=None) as db:
            db.execute("BEGIN IMMEDIATE")
            previous=db.execute("SELECT seq,digest FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1",(run_id,)).fetchone()
            seq=previous[0]+1 if previous else 0
            prior=previous[1] if previous else "0"*64
            digest=hashlib.sha256(f"{run_id}|{seq}|{stage}|{serialized}|{prior}".encode()).hexdigest()
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                       (run_id,seq,stage,serialized,prior,digest))
            db.execute("COMMIT")
        return digest

    def trace(self,run_id):
        with sqlite3.connect(self.path) as db:
            rows=db.execute("SELECT seq,stage,data_json,previous_hash,digest FROM events WHERE run_id=? ORDER BY seq",(run_id,)).fetchall()
        return [{"seq":r[0],"stage":r[1],"data":json.loads(r[2]),"previous_hash":r[3],"hash":r[4]} for r in rows]

    def verify_chain(self,run_id):
        trace=self.trace(run_id)
        if not trace: return False
        prior="0"*64
        for i,row in enumerate(trace):
            expected=hashlib.sha256(f"{run_id}|{i}|{row['stage']}|{_canonical(row['data'])}|{prior}".encode()).hexdigest()
            if row["seq"]!=i or row["previous_hash"]!=prior or row["hash"]!=expected:
                return False
            prior=expected
        return True

    def public_blessing(self,run_id):
        trace=self.trace(run_id)
        # No authorized live provider, comparator or real beneficiary in Phase05.
        return {"run_id":run_id,"proof_level":"P0","benefit_status":"NOT_MEASURED",
                "trace_valid":self.verify_chain(run_id),
                "events":trace,"challenge":"Request a reviewed source/counterfactual or dispute an event with its SHA256 hash",
                "limitation":"Offline fixture only; no actual human or environmental improvement"}
