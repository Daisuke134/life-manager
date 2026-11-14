"""Manager v0 post-training: LoRA SFT of SmolLM2-135M-Instruct on Hillstrom
intervention cases (prompt/completion format), TRL SFTTrainer.

Recipe follows the standard TRL SFT + PEFT LoRA pattern (TRL documentation,
https://huggingface.co/docs/trl/sft_trainer). The model learns
P(visit | profile, intervention arm) from randomized-assignment outcomes;
uplift is derived at eval time as the treated-minus-control difference.

v0 constraints (recorded honestly): this run executes on CPU on the team VM
because the only Hugging Face credential on file is read-only (no Space /
GPU job can be launched) and no other free GPU credential exists. It is the
smallest end-to-end run that really executes: 2,000 cases, 1 epoch.

Checkpointing is enabled (every 25 steps) and the script auto-resumes from
the latest checkpoint in the trainer dir, so an interrupted run loses at
most 25 steps.

Usage:
    python train_sft.py --data sft_train.jsonl --out out/manager-v0
"""
import argparse
import glob
import json
import os
import time

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16)

    ds = load_dataset("json", data_files=args.data, split="train")
    print(f"train rows: {len(ds)}", flush=True)

    trainer_dir = os.path.join(args.out, "_trainer")
    cfg = SFTConfig(
        output_dir=trainer_dir,
        per_device_train_batch_size=16,
        gradient_accumulation_steps=1,
        num_train_epochs=1,
        learning_rate=1e-3,
        lr_scheduler_type="cosine",
        warmup_steps=4,
        logging_steps=5,
        save_strategy="steps",
        save_steps=25,
        save_total_limit=4,
        bf16=True,
        use_cpu=True,
        seed=0,
        report_to=[],
        max_length=256,
        packing=False,
        completion_only_loss=True,
    )
    peft_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.0,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
    )
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds,
                         peft_config=peft_cfg, processing_class=tok)

    ckpts = sorted(glob.glob(os.path.join(trainer_dir, "checkpoint-*")),
                   key=lambda p: int(p.rsplit("-", 1)[1]))
    resume = ckpts[-1] if ckpts else None
    print(f"resume_from_checkpoint: {resume}", flush=True)

    t0 = time.time()
    result = trainer.train(resume_from_checkpoint=resume)
    runtime = time.time() - t0

    merged = trainer.model.merge_and_unload()
    os.makedirs(args.out, exist_ok=True)
    merged.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    log = {
        "base_model": args.base,
        "train_loss": result.training_loss,
        "train_runtime_sec": runtime,
        "global_step": result.global_step,
        "data": args.data,
        "resumed_from": resume,
        "recipe": {
            "trainer": "TRL SFTTrainer + PEFT LoRA",
            "lora_r": 16, "lora_alpha": 32, "target_modules": "all-linear",
            "epochs": 1, "lr": 1e-3, "schedule": "cosine", "warmup_steps": 4,
            "batch_size": 16, "max_length": 256, "dtype": "bfloat16",
            "completion_only_loss": True, "merged": True,
        },
    }
    with open(os.path.join(args.out, "train_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    print(json.dumps(log, indent=1), flush=True)


if __name__ == "__main__":
    main()
