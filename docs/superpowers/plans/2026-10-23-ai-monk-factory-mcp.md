# AI Monk Factory Local MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 他者のローカルAIが既存Factoryの計画・生成・素材確認記録・投稿/照合をstdio MCPで呼べる。
**Architecture:** 既存SDK/zodで4toolを登録し、固定Python executable/CLI path/argvへ接続する。ドメイン検証、費用guard、投稿fence、公式readbackは既存Pythonへ委譲する。
**Tech Stack:** Node.js、既存@modelcontextprotocol/sdk 1.x/zod、Python3、既存bin/lm。
**Spec:** docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md のAM-15d。

## Global Constraints
- Runtimeはrepo所有sourceのみ。新dependency、provider、scheduler、ledger、認証/tenant切替なし。
- tools: factory_plan / factory_render / factory_publish / factory_record_review。引数は既存CLIと同じ意味。外部effectを伴うtoolは副作用をdescriptionに明示する。
- shell/executable/environment/追加flagsを入力に含めない。未知fields、不正operation、空string/NULを拒否。固定argv、shell=false。
- childの結果JSON/exit_codeを保持し、非0/transport不正はMCP isError。公開や費用確定をwrapperで判定し直さない。
- child stderr/stdoutの巨大出力は有限にし、timeout/終了は所有process groupだけ停止する。途中provider effectは既存sidecar/fenceに任せ、再試行しない。
- 本番provider/SSOT/private stateをテストで読まない。

## Review Focus
- path/本文にshell metacharacterやleading dashが含まれてもcommandとして実行しない。
- wallet_cost=nullやPUBLISHED未確定をexit0/成功labelに上書きしない。
- production omittedは既存CLIと同じ拒否。run ID/素材確認/receipt入力を省略しない。
- parse不能/child timeoutは偽JSONや再送許可を作らない。owned child以外にsignalしない。
- stdio stdoutはprotocol専用、起動時/planでprovider呼出0。

### Task 1: 既存CLIへのstdio接続と利用例
**Files:** Create skills/earn/marketing-engine/factory-mcp.mjs、factory-mcp.test.mjs。Modify 同README.mdのみ。primaryがS11/本計画を所有する。
**Interfaces:** factory tool schemasから固定argvを作り、CLI JSONとexit_codeをMCP content/structuredContentへ返す。testのexecutor差替えはmodule関数引数だけにし、runtime環境から任意実行先を選ばせない。
- [x] tools/listと無通信plan/失敗JSON保持、固定argv/未知fields/production省略、記録toolの既存必須flags、timeout/stdioの最小REDを確認する。
- [x] SDKの既存registerTool/StdioServerTransportを使い最小実装する。CLI全体やapproval検証を作り直さない。
- [x] `node --test skills/earn/marketing-engine/factory-mcp.test.mjs` と既存Factory Python testsを実行する。
- [x] READMEにroot npm ci、stdio設定例、4toolの既存CLIとの対応、認証/費用/素材確認/公開状態の実際の制約を記す。
- [x] Loop Contract/source-boundary/OSS/diffを確認し、fetch/commit/pushする。

### Task 2: 統合と固定版受入（primary）
- [x] 最終headのfresh read-only review、必要反証を修復する。初回HIGH1→head935cacbabcの独立再反証で残blocking0。
- [ ] PR/必要CIをPASSし--admin --merge、main由来immutableのMCP実stdio list/planを無通信で確認する。
- [ ] S11へsource受入と未完の実生成/導入/収益を区別して記録する。

**Approach decision:** primaryは既存CLIの薄いstdio接続を選ぶ。CLI domainを複製する方式は費用/投稿fenceが二重化し、hosted API先行は顧客認証/利用権が未接続なので採らない。この計画はDaisのNo-human-loop委任で実行し、設計承認を再要求しない。
