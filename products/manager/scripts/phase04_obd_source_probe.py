#!/usr/bin/env python3
"""Probe six pinned *public anonymized* Open Bandit Dataset samples.

Never print or persist individual records or source-derived profiles.
Outputs only counts, safe schema keys and aggregate click-rate by campaign/policy.
"""
import csv
import hashlib
import io
import json
from urllib.request import Request, urlopen

ROOT = "https://raw.githubusercontent.com/st-tech/zr-obp/8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4/obd"
FILES = {
    "random/all": (5039451, "8ff22a297ec374cc4bfa9cc857d819da3bb9ab97"),
    "bts/all": (5084456, "6ac7a0573c8514dec0a9bb0d9ee60825dba5c80f"),
    "random/men": (3336811, "e99ba925c30ccd537a554ce8ea2104a005c6f49e"),
    "bts/men": (3240432, "fbd217ad69b08f6dc338c7e2180cd8da16fcf658"),
    "random/women": (3817771, "630e72022583db451326bb4f7c23e4f4130708fb"),
    "bts/women": (3722697, "d2a3ac87a545e428241c94e2b6549a386a323a80"),
}

def sha(blob):
    return hashlib.sha1(("blob " + str(len(blob)) + "\0").encode() + blob).hexdigest()

def run():
    results = []
    for name, (expected_bytes, expected_blob) in FILES.items():
        policy, campaign = name.split("/")
        path = f"{ROOT}/{policy}/{campaign}/{campaign}.csv"
        req = Request(path, headers={"User-Agent":"Manager-Public-Research-Safe-Aggregate/1.0"})
        with urlopen(req, timeout=30) as stream:
            blob = stream.read(expected_bytes + 1)
        if len(blob) != expected_bytes or sha(blob) != expected_blob:
            raise ValueError(f"Source mismatch in {name}")
        try:
            reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
            columns = reader.fieldnames or []
            print(json.dumps({"cohort":name,"observed_columns":columns,"source_hash_ok":True}),flush=True)
            # Ignore all human/person proxy columns. Scalar only; no source rows written.
            n = clicks = 0; positions = set(); probmin=1.0; probmax=0.0; samplemin=None; samplemax=None
            for row in reader:
                n += 1; clicks += int(row["click"])
                positions.add(row["position"])
                p = float(row["propensity_score"]); probmin=min(probmin,p);probmax=max(probmax,p)
                t = row.get("timestamp",""); samplemin = t if samplemin is None or t<samplemin else samplemin
                samplemax = t if samplemax is None or t>samplemax else samplemax
            results.append({"cohort":name,"n":n,"click_count":clicks,"click_rate":clicks/n,"columns":columns,
                "positions":sorted(positions),"action_prob_min":probmin,"action_prob_max":probmax,
                "first_timestamp_pattern":samplemin[:10],"last_timestamp_pattern":samplemax[:10],
                "git_blob_sha1":expected_blob,"bytes":expected_bytes})
        except Exception as exc:
            raise ValueError("Cannot safely parse disclosed OBD sample: "+name) from exc
    print(json.dumps({"schema":"manager.obd.aggregate-probe.v1","source_revision":"8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4","cohorts":results,"person_rows_saved":0},indent=2))

if __name__=="__main__":
    run()
