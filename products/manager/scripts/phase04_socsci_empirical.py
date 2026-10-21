#!/usr/bin/env python3
"""Run a pinned real SocSci210 study holdout without saving respondent records.

DuckDB pushes aggregation (study_id + predeclared numeric response bucket) into
the local analytic database. Only 210*12 rows of anonymous *counts* ever reach
the Python evaluator. No raw data / private/person fields in outputs.
"""
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.socsci_split_audit import MAPPING_URL, EXPECTED_BYTES, git_blob_sha, EXPECTED_BLOB_SHA1
from manager_core.phase04_socsci_empirical import evaluate_aggregates

DATA_REV="048481111a4425ed83dc0eacf15f8431f252b21a"
PARQUET_URLS=[
  f"https://huggingface.co/datasets/socratesft/SocSci210/resolve/{DATA_REV}/data/train-{i:05d}-of-00017.parquet"
  for i in range(17)
]
SQL_EXPR=("CASE WHEN response BETWEEN 0 AND 10 THEN CAST(response AS VARCHAR) "
          "ELSE 'OTHER' END")

def run():
    req=Request(MAPPING_URL,headers={"User-Agent":"Manager-Research-SocSci210/1.0"})
    with urlopen(req,timeout=30) as stream:
        content=stream.read(EXPECTED_BYTES+1)
    if len(content)!=EXPECTED_BYTES or git_blob_sha(content)!=EXPECTED_BLOB_SHA1:
        raise ValueError("study split hash mismatch; refusing analysis")
    mapping=json.loads(content.decode("utf-8"))
    import duckdb
    con=duckdb.connect(database=":memory:")
    con.execute("SET enable_progress_bar=false")
    con.execute("SET threads=4")
    con.execute("SET memory_limit='3GB'")
    con.execute("SET http_timeout=120")
    # Pin immutable revision; DuckDB remote Parquet processes only two named
    # columns (study_id,response), not demographics, prompts, participants etc.
    subset=','.join("'"+url+"'" for url in PARQUET_URLS)
    sql=f"""SELECT study_id, {SQL_EXPR} AS bucket, COUNT(*)::BIGINT AS n
        FROM read_parquet([{subset}], union_by_name=true)
        GROUP BY 1,2 ORDER BY 1,2"""
    start=time.monotonic()
    rows=con.execute(sql).fetchall()
    # Only aggregate cells are handled after remote source read, no raw logs.
    summarized=[(str(s),str(b),int(n)) for s,b,n in rows]
    report=evaluate_aggregates(mapping,summarized)
    report["evidence"]={
      "dataset_revision":DATA_REV,"study_mapping_sha1":EXPECTED_BLOB_SHA1,
      "parquet_files":17,"method":"DuckDB projection and GROUP BY study_id,coarse_code; no individual records persisted",
      "elapsed_seconds":round(time.monotonic()-start,2),
      "source_sql_result_cells":len(summarized),
    }
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("source_split","unseen_baselines","study_level_distribution_error","scientific_gates","privacy","evidence")},sort_keys=True))

if __name__=="__main__":
    main()
