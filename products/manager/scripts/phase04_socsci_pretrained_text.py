#!/usr/bin/env python3
"""Actual 170/40 studied record-matched comparator.

Sample 20 text stimuli + responses per study (not demographics) transiently;
compares frozen Apache 2.0 MiniLM encoder + train-only logistic head vs pure
categorical frequency and majority on the exact same samples. Does not train
on any 40 unseen records. Emits no prompts, individual records, demographics.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
import argparse,json,time,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.socsci_split_audit import MAPPING_URL,EXPECTED_BYTES,EXPECTED_BLOB_SHA1,git_blob_sha,PINNED_DATASET_REVISION
from manager_core.phase04_pretrained_eval import LABELS,validate_and_partition,score_same_rows

MODEL="sentence-transformers/all-MiniLM-L6-v2"
EXPERIMENT_ROWS=20
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);a=parser.parse_args()
    with urlopen(Request(MAPPING_URL,headers={"User-Agent":"Manager-SocSci210-MiniLM-Eval/1.0"}),timeout=25) as r:
        blob=r.read(EXPECTED_BYTES+1)
    if len(blob)!=EXPECTED_BYTES or git_blob_sha(blob)!=EXPECTED_BLOB_SHA1:
        raise ValueError("untrusted study split")
    mapping=json.loads(blob)
    import duckdb
    from huggingface_hub import snapshot_download,model_info
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    start=time.perf_counter()
    with TemporaryDirectory(prefix="socsci-private-ephemeral-") as tmp:
        snapshot_download(repo_id="socratesft/SocSci210",repo_type="dataset",
                          revision=PINNED_DATASET_REVISION,allow_patterns=["data/train-*.parquet"],
                          local_dir=tmp,max_workers=8)
        parquet=sorted((Path(tmp)/"data").glob("train-*.parquet"))
        if len(parquet)!=17:raise ValueError("missing original 17 shards")
        con=duckdb.connect(":memory:")
        con.execute("SET threads=4")
        con.execute("SET memory_limit='5GB'")
        dataset=','.join("'"+str(p)+"'" for p in parquet)
        # Source row subset selected by source identifiers ONLY (never the outcome)
        # and a fixed seed, retaining 20 records per original study.
        sql=f"""SELECT study_id, SUBSTR(CAST(stimuli AS VARCHAR),1,600) AS stimulus,
                  CASE WHEN response BETWEEN 0 AND 10 THEN CAST(response AS VARCHAR)
                       ELSE 'OTHER' END AS label
               FROM (SELECT study_id,stimuli,response,
                            ROW_NUMBER() OVER(PARTITION BY study_id
                              ORDER BY HASH(study_id,sample_id,task_num,condition_num)) AS rn
                     FROM read_parquet([{dataset}],union_by_name=true))
               WHERE rn <= {EXPERIMENT_ROWS} ORDER BY study_id,rn"""
        rows=con.execute(sql).fetchall()
        con.close()
        train,test=validate_and_partition(mapping,rows,rows_per_study=EXPERIMENT_ROWS)
        # Frozen published encoder is not fine-tuned. Only head is trained on seen.
        encoder=SentenceTransformer(MODEL,device="cpu")
        e_start=time.perf_counter()
        x_train=encoder.encode([x[1] for x in train],batch_size=40,normalize_embeddings=True,show_progress_bar=False)
        x_test=encoder.encode([x[1] for x in test],batch_size=40,normalize_embeddings=True,show_progress_bar=False)
        embedding_time=time.perf_counter()-e_start
        model=LogisticRegression(max_iter=250,solver="lbfgs")
        y_train=[LABELS.index(x[2]) for x in train]
        model.fit(x_train,y_train)
        raw=model.predict_proba(x_test)
        # Fill 12-class zero probabilities for unseen training labels.
        probabilities=[]
        for row in raw:
            p=[0.0]*len(LABELS)
            for cls,val in zip(model.classes_,row):
                p[int(cls)]=float(val)
            probabilities.append(p)
        scored=score_same_rows([x[2] for x in train],test,probabilities)
        model_sha=model_info(MODEL).sha
        report={
            "schema":"manager.phase04.socsci210.real-study-matched-pretrained-text-comparison.v1",
            "basis":"REAL_SOCIETAL_EXPERIMENT_STIMULI_AND_RESPONSES_EPHEMERALLY_SAMPLED",
            "study_split":{"train_studies":170,"unseen_studies":40,"train_rows":len(train),
                           "unseen_rows":len(test),"records_per_study":EXPERIMENT_ROWS},
            "evaluation":scored,
            "pretrained":{"name":MODEL,"revision":model_sha,"license":"Apache-2.0",
              "architecture":"frozen 384-dimension sentence embeddings + logistic regression fitted ONLY on seen studies",
              "no_training_of_pretrained_encoder":True,"head_training_data":"170 original seen studies only",
              "inference_embedding_seconds_cpu":round(embedding_time,2),
              "runtime_wall_seconds_total":round(time.perf_counter()-start,2),
              "measured_metered_provider_dollars":None,
              "cost_caveat":"Wall seconds were observed. CPU electricity/cloud cost and billed inference dollars are NOT inferred."},
            "limitations":{
                "numeric_response_code_semantics_not_uniform_across_studies":True,
                "not_the_original_socrates_8b_or_14b_model":True,
                "test_case_label_not_used_to_fit_any_model":True,
                "study_condition_level_question_options_not_available_as_features":True,
                "not_a_population_fidelity_certification":True,
                "not_a_real_world_intervention":True,
                "beneficiaries_verified":0,
                "model_inference_authorized_by_operator":True,
            },
            "privacy":{"respondent_demographics_loaded":False,"participant_ids_output":False,
                       "raw_rows_stored_or_uploaded":False,"text_or_profiles_committed":False,
                       "sample_responses_output":False},
            "source":"socratesft/SocSci210@"+PINNED_DATASET_REVISION
        }
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        print(json.dumps({"study_split":report["study_split"],
                         "evaluation":{k:{m:val for m,val in v.items() if m!="reliability"} for k,v in scored.items()},
                         "model_revision":model_sha,"embedding_seconds_cpu":round(embedding_time,2),
                         "limitations":report["limitations"],"privacy":report["privacy"]},sort_keys=True))

if __name__=="__main__": main()
