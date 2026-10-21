#!/usr/bin/env python3
"""Real immutable GitHub OBD six-cohort run; do NOT retain input participant rows."""
import csv
import hashlib
import io
import json
import sys
import argparse
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from manager_core.phase04_open_bandit import compare_policies
from scripts.phase04_obd_source_probe import FILES,ROOT as SOURCE_ROOT,sha

def run():
    data={}
    for name,(size,blob_hash) in FILES.items():
        policy,campaign=name.split("/")
        path=f"{SOURCE_ROOT}/{policy}/{campaign}/{campaign}.csv"
        with urlopen(Request(path,headers={"User-Agent":"Manager-ZOZO-OPE-Research/1.0"}),timeout=40) as stream:
            blob=stream.read(size+1)
        if len(blob)!=size or sha(blob)!=blob_hash:
            raise ValueError("immutable source mismatch")
        entries=[]
        for record in csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))):
            entries.append((int(record["click"]),float(record["propensity_score"]),int(record["item_id"])))
        if len(entries)!=10000:
            raise ValueError("unexpected cohort shape")
        data[name]=entries
    result=compare_policies(data)
    # Published output references source provenance; excludes records and identifiers.
    result["original_source"]="https://github.com/st-tech/zr-obp/tree/8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4/obd"
    result["citation"]="Saito et al., Open Bandit Dataset and Pipeline, https://arxiv.org/abs/2008.07146"
    result["source_git_blobs"]={k:v[1] for k,v in FILES.items()}
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);a=parser.parse_args()
    out=run();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":out["schema"],"campaign_results":out["campaign_results"],"limitations":out["limitations"],"privacy":out["privacy"]},sort_keys=True))
