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
