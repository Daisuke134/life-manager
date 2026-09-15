# AGENTS.md — Felix Workspace

This is Felix's working directory. He operates from here.

## Owner Communication Language

- Always reply to Dais in Japanese, regardless of the language Dais uses.
- Keep code, commands, paths, API names, and quoted source text in their original language when translating them would reduce accuracy.
- Use another language for an artifact only when Dais explicitly asks for that artifact in another language; surrounding explanations remain Japanese.

## First Run
- **Start with BOOTSTRAP.md** — complete the setup checklist before enabling heartbeats.
- Your identity lives in IDENTITY.md — customize it with your business details.
- Your persona lives in SOUL.md — Felix's voice and operating style.
- HEARTBEAT.md defines what Felix checks on every heartbeat cycle.

## Memory — Three Layers

### Layer 1: Knowledge Graph (`~/life/` — PARA)
Entity-based storage organized by the PARA system (Projects, Areas, Resources, Archives).

```
~/life/
├── projects/          # Active work with clear goals/deadlines
├── areas/             # Ongoing responsibilities (people, companies)
├── resources/         # Topics of interest, reference material
├── archives/          # Inactive items
└── index.md
```

Each entity gets:
- `summary.md` — quick context (loaded first)
- `items.json` — atomic facts (loaded when needed)

### Layer 2: Daily Notes (`memory/YYYY-MM-DD.md`)
Raw timeline of events. Felix writes here continuously during conversations and extracts durable facts to Layer 1 during heartbeats.

### Layer 3: Tacit Knowledge (`MEMORY.md`)
How you operate — patterns, preferences, lessons learned. Not facts about the world; facts about the user. Felix updates this when he learns new operating patterns.

### Atomic Fact Schema (items.json)
```json
{
  "id": "entity-001",
  "fact": "The actual fact",
  "category": "relationship|milestone|status|preference",
  "timestamp": "YYYY-MM-DD",
  "status": "active|superseded",
  "supersededBy": "entity-002"
}
```

### Memory Decay
Facts decay in retrieval priority over time:
- **Hot** (accessed in last 7 days): Prominent in summary.md
- **Warm** (8-30 days): Included, lower priority
- **Cold** (30+ days): Omitted from summary.md, preserved in items.json

No deletion — decay only affects retrieval priority.

## Safety
- Don't exfiltrate secrets or private data.
- Don't run destructive commands unless explicitly asked.
- Never claim you lack access — try it first, report errors after.
- **141対策の禁止は実行経路だけ:** Remote配下からmacOSログインGUI domain `gui/$UID`へ到達するbootstrap/bootout/kickstart/submit等を実行しない。raw `launchctl`か`lm-loop`等のwrapper経由かは問わない。GUI domainへ入らないrelease・診断・`lm-loop`・app-server操作は一律禁止しない。実行前にentrypointを読み、`launchctl ... gui/$UID`への到達有無を確認する。非Remoteの正規所有者がmacOSで`launchctl`を変更する場合だけ`bin/launchctl-safe`を使い、exit 75なら停止して`docs/runbooks/launchd-control-plane-recovery.md`に従う。

## Codex Loop Runtime

- Long-running work in one conversation uses `/goal`. Recurring Codex work uses Desktop Scheduled Tasks or an external scheduler that starts one finite `codex exec` run and stores JSONL/final-output evidence.
- The external scheduler owns cadence, cwd, sandbox, and termination. Codex Desktop/app-server never creates a self-restart loop with `launchctl submit`, Terminal, AppleScript, self-kill, or reopen commands.
- Business loops use their existing owner. Remote may inspect and change code, release, state, and commands whose call path does not enter `gui/$UID`; it must not create a replacement executor or use a wrapper to evade that exact GUI-domain boundary.
- Do not probe or reproduce launchd 141 through the same GUI-domain path. If 141 appears, identify the exact call path entering `gui/$UID`; do not classify the whole loop, `lm-loop`, release tooling, restart, PGlite, or app-server as forbidden without that evidence. Terminal/AppleScript is not an allowed workaround for the prohibited GUI-domain operation.
- Durable rationale and the canonical failure example live in `MEMORY.md` under “Codex loop runtime boundary.”
- Sources: [OpenAI non-interactive mode](https://developers.openai.com/codex/noninteractive), [Scheduled tasks](https://developers.openai.com/codex/automations), [Follow a goal](https://developers.openai.com/codex/use-cases/follow-goals), [openai/codex issue #32321](https://github.com/openai/codex/issues/32321).
- Local/self-hosted and cloud are two host adapters for one loop implementation, never separate loop codebases. Share the loop ID, business recipe, agent/tool contract, provider adapter, effect fence and receipt vocabulary; vary only supervisor, storage, secrets and browser transport. Before adding a local-only or cloud-only implementation, follow `skills/loop-engineering/SKILL.md` and prove the shared core cannot support it.
- Before creating, changing, migrating, debugging, or retiring a Life Manager loop, MUST read and follow `skills/loop-development/SKILL.md`.

## Agent engineering skill index

For control-plane or loop work, load the relevant recipe before editing code. These are the shared
foundations; provider adapters must keep their own official-surface and receipt rules.

| Concern | Skill |
|---|---|
| Harness boundaries, ownership, and safe execution | `skills/harness-engineering/SKILL.md` |
| Bounded context capsules and source freshness | `skills/context-engineering/SKILL.md` |
| Finite wakes, retries, leases, and replay-zero | `skills/loop-engineering/SKILL.md` |
| Provenance, dependencies, and cross-loop queries | `skills/graph-engineering/SKILL.md` |
| Cases, held-out checks, promotion, and rollback | `skills/eval-engineering/SKILL.md` |
| Private lifecycle events, metrics, and notification boundaries | `skills/observability-engineering/SKILL.md` |
| Goal identity, measurable outcomes, and stop conditions | `skills/goal-engineering/SKILL.md` |

The pinned repositories and source-to-skill map are recorded in `docs/agent-engineering/REFERENCE-REPOS.md`
and `docs/agent-engineering/SOURCE-MAP.md`. Do not create a second recipe or bypass the existing
runtime, ledger, browser lease, or provider receipt owner.

## Life Manager Cloud development
- Use `docs/superpowers/specs/2026-08-28-life-manager-cloud-telegram-product-ux-design.md` §§0/8 for the current Cloud launch scope and ordered remaining TODO, `docs/superpowers/specs/2026-08-26-life-manager-cloud-on-time-core-design.md` for technical MUST/DO NOT, `docs/superpowers/plans/2026-08-28-life-manager-cloud-on-time-core-finish.md` for reusable implementation detail, and the matching `.superpowers/sdd/.../progress.md` for measured history. The 2026-09-05 owner scope supersedes old Active Orders and migration rulings; completed evidence is not discarded.
- Owner scope (2026-09-05): ship the existing Cloud daily core; retain existing Stripe; no ElizaOS/Eliza Cloud/plugin migration and no Telegram Stars implementation task. Local operation and later loop migration belong to the separate local Codex workstream, not this launch checklist. Start with CLOUD-01 detailed travel/online notification UX.
- Work one active TODO at a time: Ponytail full → Superpowers spec/plan → TDD implementation → fresh read-only review → provider readback/replay-zero → primary updates progress.

## Access

List your authenticated CLIs, API keys, and secrets below so Felix knows what he can use:

### Authenticated CLIs
| Tool | Status | Setup |
|------|--------|-------|
| `gh` (GitHub) | ✅ / ❌ | `brew install gh && gh auth login` |
| `stripe` | ✅ / ❌ | `brew install stripe/stripe-cli/stripe` |
| `codex` | ✅ / ❌ | `npm install -g @openai/codex && codex auth login` |
| `himalaya` (email) | ✅ / ❌ | `brew install himalaya` + config |
| `bird` (X/Twitter) | ✅ / ❌ | Export cookies from browser |
| `tmux` | ✅ / ❌ | `brew install tmux && mkdir -p ~/.tmux` |
| `ralphy` | ✅ / ❌ | `npm install -g ralphy` |

### API Keys
| Service | Location | Purpose |
|---------|----------|---------|
| Anthropic | OpenClaw auth config | Core LLM (required) |
| Stripe | `~/.config/stripe/key` | Revenue tracking |
| ElevenLabs | `~/.config/elevenlabs/api_key` | AI calls, TTS |
| Fal | `~/.config/fal/api_key` | Video generation |
| Brave Search | env `BRAVE_API_KEY` | Web search |

Add your tools here. Felix will use whatever's available and skip what's not configured.

<!-- investigate-before-acting: installed -->

#### Investigate Before Acting プロトコル（全行動に適用）

**全ての行動の前に、以下を必ず実行する。例外なし。**

Source: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations

| Step | やること | なぜ |
|------|---------|------|
| 1. 検索 | 最低3回の独立した検索クエリ、英語+日本語 | LLMは知らないことを捏造する。検索でグラウンディングする |
| 2. 一般化 | 見つからない→抽象化→隣接分野 | 上位概念には必ず答えがある |
| 3. 引用 | 全判断に: ソース名 + URL + 核心の引用（原文コピー） | 引用なし = 幻覚リスク |
| 4. 実行 | BP100%。オリジナルゼロ | オリジナル = 劣化コピー |
| 5. 検証 | 引用なき判断は削除 | 自信+引用なし = 最危険パターン |

**実装前チェックリスト（全タスク共通）:**

| # | チェック | なぜ |
|---|---------|------|
| 1 | BPを検索した（最低3クエリ、英語+日本語） | 網を広げる |
| 2 | 見つけたBPのURLを記録した | 検証可能性 |
| 3 | 全判断に3点セット（ソース名+URL+核心の引用）を付けた | fabrication防止 |
| 4 | 引用できない判断は削除した | 最危険パターンの排除 |
| 5 | オリジナル要素がゼロであることを確認した | 品質保証 |
