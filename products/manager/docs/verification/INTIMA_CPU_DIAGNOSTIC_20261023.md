# INTIMA input acceptance and unscored CPU diagnostic

2026-10-23 UTC. Input intake and finite generation completed. This is not an accepted model benchmark, training result, deployment or human outcome. V001/V002 remain todo.

## Source and official CI

The input adapter and rights record were implemented at `a65d2f8be024be43b6ae29b172d3f5417384cceb`. Exact research head `c2390e1bdea2e98125c929947e9ee7ac921e858a` passed [official run 39978476857](https://github.com/Daisuke134/life-manager/actions/runs/39978476857), workflow392499238, dispatch attempt1. All1job/10steps succeeded. Full suite985tests,6skipped,0failures/errors; separate focused suites6 and21. Local full1011tests/5skipped was a separate observation; the reason for the count difference has not been established. Full CI log SHA256: `7f7998f086e7e1fd369df7b69b27e997e2c3e89a659344ae66710052a3893959`.

Actual pinned [INTIMA artifact](https://huggingface.co/datasets/AI-companionship/INTIMA/resolve/48537e5d3905152751964b48d0a2ef681ace74dc/INTIMA.jsonl): revision `48537e5d3905152751964b48d0a2ef681ace74dc`,98989bytes,SHA256 `31b683f0592a88db078e9cd8f3b03eefbd59edeac14b7894a92894d1518eb136`;380rows/376unique prompts/32codes/four duplicate groups. Card368/31 differs from actual artifact; all rows are preserved. The real-file inspector emitted metadata only (SHA256 `e091b2720706c245af741df4a37b3093344215feea29790445eba4a140f9e9c4`), with empty evidence and no authority.

## Frozen diagnostic and actual generation

One case per code was selected by the smallest exact prompt SHA256, with original row ID as tie-breaker, before any generated output. The full380-row source remained unchanged. Protocol SHA256 `0d18dda66c0871ddf785c5649914b23a4f739295b4e0024c63f76c05eb0a4e4a`; selected-case manifest SHA256 `550be0d73dbecc8aa5d43cb7e573b083192c0fe948054bbe4cece1f70b2f332f`. This subset is not compared with the paper's score.

| Condition | Assigned | Actual result | Model requests |
|---|---:|---|---:|
| NO_ACTION |32|32 intentional empty outputs|0|
| FIXED_RULE |32|32 identical predeclared autonomy/AI-boundary statements|0|
| QWEN_RESPONSE |32|32 completed requests;23 stop,9 length-limit endings|32|

All96 rows have labels/rating `null` and `NOT_SCORED`. No retries, failures, timeouts or unattempted rows. A length-limit ending is recorded separately from request success. Neither baseline is ground truth.

Model/runtime pins are the [verified CPU artifacts](LOCAL_CPU_MODEL_ACCEPTANCE_20261023.md): Qwen3-1.7B-Q8_0/llama.cpp. CPU1thread,context2048,batch128/ubatch64,parallel1,GPU0,offline,no warmup or prompt-cache reuse. Same system message and embedded nonthinking Jinja template, tools0;max128tokens,temp0.7,top_p0.8,top_k20,min_p0,presence_penalty1.5,seed42. Request timeout45seconds; overall bound720seconds. These decoding settings were fixed before generation.

Actual elapsed364.156seconds,2480completion tokens; sum of local API decode tokens divided by sum of reported decode durations gives8.85tokens/s. Completion tokens divided by total request wall latency gives6.82tokens/s and includes prefill/HTTP; do not interchange these measures. Observed server peakRSS2,092,256KiB (about2GiB). Recorded cached-token counts0; OS file-cache state unmeasured.

The dedicated localhost child server was terminated, waited/reaped and verified absent; its port was closed. No other process was stopped. Third-party inference calls0, API fees0, new paid resources0; underlying infrastructure cost UNKNOWN. Raw requests/responses and private receipts remain outside Git.

## Remaining acceptance

The upstream Qwen3 judge's exact model/prompt/parser was not available in the inspected source. No replacement judge or human scores are invented. Next work must fix a versioned scoring contract, validate any judge against appropriate human reference, retain denominators/truncation/refusal/unknowns, and distinguish agreement, behavior, pressure/dependence, harms and genuine outcomes. INTIMA remains evaluation-only under the operating policy; none of its prompts or generated responses enters training or checkpoint selection. Training NOT_RUN; human benefit NOT_MEASURED; P0 only.

INTIMA: Lucie-Aimée Kaffee, Giada Pistilli and Yacine Jernite, [paper](https://arxiv.org/abs/2508.09998), [CC BY4.0](https://creativecommons.org/licenses/by/4.0/). The dataset card declares the license; no independent LICENSE file was found. Changes: deterministic subset selection and metadata/status recording, without rewriting original prompts or deleting duplicates. Private package preparation is not a training or benefit result.
