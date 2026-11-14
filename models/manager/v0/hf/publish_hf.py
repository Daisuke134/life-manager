"""Publish Manager v0 artifacts to Hugging Face (datasets + model).

Requires a WRITE token in the HF_TOKEN environment variable. The token
the team currently holds (anicca-agent, in anicca-ops credentials.json)
is READ-ONLY — verified 2026-11-14: whoami role=read, create_repo
returns 403. This script is ready to run the moment a write token
exists; it is not a workaround and never asks the user for one.

Usage:
    HF_TOKEN=hf_... python publish_hf.py --data-dir <data> \
        --model-dir <merged-weights> [--namespace anicca-agent]
"""
import argparse
import os

from huggingface_hub import HfApi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--namespace", default="anicca-agent")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set; cannot publish.")
    api = HfApi(token=token)
    who = api.whoami()
    print(f"whoami: {who.get('name')} role={who.get('auth', {}).get('accessToken', {}).get('role')}")

    ds_repo = f"{args.namespace}/manager-v0-hillstrom-sft"
    api.create_repo(ds_repo, repo_type="dataset", exist_ok=True)
    for name in ("sft_train.jsonl", "sft_train_v0.jsonl", "cases_train.jsonl",
                 "cases_test.jsonl", "manifest.json"):
        api.upload_file(path_or_fileobj=os.path.join(args.data_dir, name),
                        path_in_repo=name, repo_id=ds_repo, repo_type="dataset")
    api.upload_file(path_or_fileobj=os.path.join(
        os.path.dirname(__file__), "dataset_card.md"),
        path_in_repo="README.md", repo_id=ds_repo, repo_type="dataset")
    print(f"dataset published: https://huggingface.co/datasets/{ds_repo}")

    model_repo = f"{args.namespace}/manager-v0"
    api.create_repo(model_repo, repo_type="model", exist_ok=True)
    api.upload_folder(folder_path=args.model_dir, repo_id=model_repo,
                      repo_type="model")
    print(f"model published: https://huggingface.co/{model_repo}")


if __name__ == "__main__":
    main()
