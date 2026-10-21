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

def run(*, transport='remote'):
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
    local_cache=None
    if transport=='local':
        from huggingface_hub import snapshot_download
        from tempfile import TemporaryDirectory
        local_cache=TemporaryDirectory(prefix='socsci210-ephemeral-')
        snapshot_download(repo_id='socratesft/SocSci210', repo_type='dataset',
            revision=DATA_REV, allow_patterns=['data/train-*.parquet'],
            local_dir=local_cache.name, max_workers=6)
        local_paths=sorted((Path(local_cache.name)/'data').glob('train-*.parquet'))
        if len(local_paths)!=17:
            raise ValueError('incomplete pinned local parquet dataset')
        source_files=[str(p) for p in local_paths]
    elif transport=='remote':
        source_files=PARQUET_URLS
    else:
        raise ValueError('unsupported source transport')
    subset=','.join("'"+url+"'" for url in source_files)
    sql=f"""SELECT study_id, {SQL_EXPR} AS bucket, COUNT(*)::BIGINT AS n
        FROM read_parquet([{subset}], union_by_name=true)
        GROUP BY 1,2 ORDER BY 1,2"""
    start=time.monotonic()
    try:
        rows=con.execute(sql).fetchall()
    finally:
        con.close()
        if local_cache is not None:
            local_cache.cleanup()
    # Only aggregate cells are handled after remote source read, no raw logs.
    summarized=[(str(s),str(b),int(n)) for s,b,n in rows]
    report=evaluate_aggregates(mapping,summarized)
    report["evidence"]={
      "dataset_revision":DATA_REV,"study_mapping_sha1":EXPECTED_BLOB_SHA1,
      "parquet_files":17,"method":"DuckDB projection and GROUP BY study_id,coarse_code; no individual records persisted",
      "elapsed_seconds":round(time.monotonic()-start,2),
      "source_sql_result_cells":len(summarized),
      "transport":transport,
    }
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--transport",choices=["remote","local"],default="remote")
    args=parser.parse_args()
    result=run(transport=args.transport)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("source_split","unseen_baselines","study_level_distribution_error","scientific_gates","privacy","evidence")},sort_keys=True))

if __name__=="__main__":
    main()
