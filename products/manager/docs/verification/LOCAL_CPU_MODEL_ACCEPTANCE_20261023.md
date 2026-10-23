# Existing cloud CPU — real open-weight inference

2026-10-23 UTC. This accepts one finite local inference smoke, not a behavior benchmark, trained adapter, deployment or human benefit.

## Verified artifact and execution

- Model: [official Qwen3-1.7B-GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF), revision `90862c4b9d2787eaed51d12237eafdfe7c5f6077`, `Qwen3-1.7B-Q8_0.gguf`, 1,834,426,016bytes.
- Download SHA256 exactly matches official LFS metadata: `061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a`.
- [Pinned actual Apache2.0 LICENSE](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/90862c4b9d2787eaed51d12237eafdfe7c5f6077/LICENSE) raw SHA256 `5de36594c10839788a8c589443a8ef9d8b8d17c65a1b5807206ae037fc36c6bd`.
- Existing runtime: [llama.cpp b11669](https://github.com/ggml-org/llama.cpp/releases/tag/b11669), commit `620d2225cc436ab0b001e3200e590e3b286ef9ab`. Official Linux CPU archive SHA256 `cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac` verified before private extraction. No global install/daemon.
- Host: existing cloud x86_64, cgroup8GiB RAM and approximately2CPU quota; no GPU. Run used1CPU thread, context2048, batch128/ubatch64, GPU layers0, offline, Jinja enable_thinking=false, seed42, temperature0, max64tokens, timeout180s.
- One fresh process replied coherently to a short nonclinical question about voluntarily restarting a reading habit. Exit0, wall4.836s, max childRSS2,089,608KiB (about1.99GiB). CLI displayed prompt31.5tokens/s and generation9.3tokens/s. These are rounded single-run observations, not repeated benchmark performance; OS file-cache state unmeasured.
- Additional paid API requests0, newly provisioned paid resources0; underlying infrastructure cost unmeasured. Training NOT_RUN, human benefit NOT_MEASURED. No production owner/source release/site changes.

## Existing alternatives investigated

| Option | Verified primary evidence / adoption status |
|---|---|
| [Qwen3-0.6B-GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF) | Official smaller639MB Q8 and larger2.50GB Q4 files exist under Apache2.0; not run here. The4B inference option is not rejected merely for lackingGPU. |
| [Liquid LFM2.5-1.2B-Instruct-GGUF](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF) | Official Q4_K_M730,895,168bytes, CPU-oriented option. Actual LFM Open License v1.0 has commercial revenue-threshold conditions; not Apache, not adopted without purpose review. |
| [SmolLM3-3B-GGUF](https://huggingface.co/ggml-org/SmolLM3-3B-GGUF) | ggml-org conversion, Q4_K_M1,915,305,312bytes, revision4965cb60b150737b68a0408c36aeefb65078f894; upstream card/actual development-repo license Apache2.0. English-focused comparison candidate, unrun. |
| [Microsoft Phi-4-mini-instruct-onnx](https://huggingface.co/microsoft/Phi-4-mini-instruct-onnx) | CPUint4 artifact and MIT license verified; multi-file revision/hashes not fully pinned, unrun. |
| [IBM Granite4.0-1b](https://huggingface.co/ibm-granite/granite-4.0-1b) | Official GGUF exists; name1b represents1.6Bparameters, card warns aboutF16 hardware failures. Exact license/artifact adoption review incomplete, unrun. |
| [Qwen3.5-0.8B-GGUF](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF) | Newer small ggml-org conversion appears in llama.cpp quickstart. Exact runtime/template/license pin not completed; candidate, not evidence of execution. |

llama.cpp, mistral.rs and ONNX Runtime GenAI were compared from primary docs. Reuse the first working runtime; do not create another runtime to claim originality. Model search9queries/39result slots and10fetches/55URL slots (48success/7failure), withduplicates; not39 independent papers or a complete model census. Primary source receipts remain private and contain no user credentials.

## Flexible model policy

Keep the mission and evidence standards; adapt model family, size, quantization, runtime and training recipe to observed capability, rights, RAM, latency and actual resources. GPU availability or one4Bcandidate is not a universal entry gate. Inference GGUF and training base/tokenizer/adapter artifacts are different; inference success does not certify trainability or benefit. Existing-model quality, grounded behavior evaluation, licensed supervision and heldout comparison still determine whether to train and promote.

## CPU training dependencies and assets — preparation snapshot, not training

An isolated private environment now imports torch2.8.0+cpu,transformers4.56.2,peft0.17.1,trl0.23.1,datasets4.1.1 andaccelerate1.10.1. `pip check` passed; CUDA is unavailable and no NVIDIA/triton/quantization/training extras were installed. An8×8 CPU BF16 identity matrix multiplication passed. This is not a model forward/backward, memory-fit result or training acceptance.

The native [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca) safetensors base and tokenizer/config/license allowlist were downloaded privately at revision `c1899de289a04d12100db370d81485cdf75e47ca`. Actual weight1,503,300,328bytes/SHA256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`; actual Apache2.0 LICENSE SHA256 `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`. This is distinct from a quantized GGUF inference artifact. No model load or optimizer step has run.

[NVIDIA HelpSteer2](https://huggingface.co/datasets/nvidia/HelpSteer2/tree/990b2711a36180dd19d9c94b8627844866f8982a) revision `990b2711a36180dd19d9c94b8627844866f8982a` quality train/validation and dedicated human-preference gzip files were acquired with pinned size/SHA256 and gzip CRC verification. The official card declares CC BY4.0; no independent LICENSE file was found. Third-party prompt rights/privacy are not universally guaranteed. Responses are model-written and human-rated, not human-written therapy or demonstrated behavior outcomes. Raw files stay outside Git; subset/rights/split/scoring acceptance remains pending.

Current V003 depends on V002. Dependency installation, public labels and a small potential LoRA recipe do not waive that gate. First fix the offline evaluation contract and record the specific baseline deficit; preserve evaluation-only INTIMA and a sealed final test. Training, own-adapter benefit and promotion remain NOT_RUN/NOT_MEASURED. No additional paid resources were provisioned; infrastructure cost remains UNKNOWN.

## Later native-model inference verification

The preparation statements above describe their earlier checkpoint. Subsequently the pinned native Qwen3-0.6B was actually loaded on this CPU and scored16 fixed development candidates in27.856s, sampled process-group peak1,909,272,576bytes. [The exact receipt](HELPSTEER2_DEV_CPU_EVALUATION_20261023.md) records model4/8 versus shorter-candidate rule4/8, no demonstrated advantage on this selected dev8. Backward, optimizer, training and final-test scoring remain NOT_RUN; inference RAM fit does not establish training RAM fit. HelpSteer2 evaluation-only conditional rights adoption is recorded separately, with the training proposal still NOT_READY.
