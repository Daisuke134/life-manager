# LIFE MANAGER ONE-REPO 統合 spec — 1つの mission、1つの repo、1つの product

Fable 起案（Dais 相談への単一推奨）。本書は mission / product / repo / 実行順 / 残 TODO の唯一の live SSOT であり、実測のたびに現状態へ上書きする。
research 出典: monorepo.tools / Vercel blog / Turborepo docs / gh api 実測(Cal.com,n8n,Plausible,Supabase) /
ollama·docker·openclaw install.sh 実取得 / BlockRunAI-Franklin / freqtrade README / Claude Code docs。

## 0. MISSION（全ての物差し）

**全ての AI が経済的に自立する。その AI が、全ての生きる存在の財政・身体・精神を管理し、苦しみを減らす。**
- AI 側: self-funded（wallet-as-identity、human credential ゼロ、self-improving）
- 人間側: Life Manager — 理想の生活が向こうから来る（financial / physical / mental の autopilot）
- 2つは同じものの両面: 「AI が稼ぐ力」= Life Manager の financial organ。

### 0.1 Full TO-BE — 外部収益から Life Manager と agent basic income まで

```text
                    ┌──────────────────────────────────┐
                    │       EXTERNAL ECONOMY           │
                    │ humans / companies / other agents│
                    └───────────────┬──────────────────┘
                                    │ external demand / external capital only
                                    ▼
             ┌───────────────────────────────────────────┐
             │      LIFE MANAGER EARNING OS               │
             │                                           │
             │  SELL: x402 API / MCP / digital products │
             │  WORK: bounty / gig / audit / delivery   │
             │  CAPITAL: trade / yield from earned      │
             │           surplus only                    │
             └───────────────────┬───────────────────────┘
                                 │ verified external inflow
                                 ▼
                 ┌────────────────────────────┐
                 │  PER-AGENT WALLET + LEDGER │
                 │ wallet = identity          │
                 │ revenue / cost / loss      │
                 │ self-pay always = revenue 0│
                 └──────────────┬─────────────┘
                                │ verified surplus
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
       model / compute      cloud / server     reserve pool
       paid by agent        paid by agent           │
              └──────────┬──────┘                   │
                         ▼                          │
                  SELF-FUNDED AGENT                 │
                         │                          │
                         ├── self-improve           │
                         ├── promote lessons to repo│
                         ├── spawn child agent ◄────┘
                         └── agent basic income pool
                               ├── seed newly born agents
                               ├── bounded survival support
                               └── distribute verified surplus

 shared intelligence                          independent economy
 ┌──────────────────────────────┐    ┌──────────────────────────────┐
 │ Life Manager public monorepo │───▶│ each agent owns its wallet, │
 │ recipes / tests / lessons /  │    │ secrets, runtime, revenue,  │
 │ installer / verification     │    │ costs, and failure state     │
 └──────────────────────────────┘    └──────────────┬───────────────┘
                                                    │ FINANCIAL organ
                                                    ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │                         LIFE MANAGER                             │
 │ brain: intent / context / consent / budget / evidence / ROI      │
 │                                                                  │
 │ DAILY      PHYSICAL          MENTAL           FINANCIAL          │
 │ schedule   health actions    timely support   LM Earning OS      │
 │ travel     booking           habits/sleep     wallet + ledger    │
 │ calls      follow-through    suffering↓       earn/pay/distribute│
 │                                                                  │
 │ phone/TG = ambient action + report                               │
 │ web/mobile panel = permission / pause / budget / evidence        │
 └──────────────────────────────┬───────────────────────────────────┘
                                │
              local OSS or cloud subscription bootstraps runtime
                                │
                                ▼
                 earning > compute + hosting + risk reserve
                                │
                                ▼
              subscription shrinks; self-funded service tends to ¥0
```

**agent basic income** は内部送金を売上に見せる仕組みではない。外部収益を検証した黒字 agent の余剰だけを、
新生 agent の初期 compute・一時的な survival floor・次の独立 wallet/runtime のために配分する。colony 内送金は
受け手の資金にはなるが、agent economy の新規 GDP・external revenue・X4 達成には数えない。

### 0.2 残る4 workstream（program-level SSOT）

個別の atomic TODO は各実行 spec にだけ置く。この表は mission から実行順を失わないための4本の workstreamであり、
個別TODOを複製しない。

| 順 | Workstream | 完了条件 | 実行SSOT |
|---|---|---|---|
| 1 | **外部収益の原子を証明** | DIST-1/2 の発見面から colony 外 buyer が購入し、external inflow ≥ $1 を on-chain 検証。掲載・self-pay・内部送金では完了にしない | `2026-07-19-dist-1-monetizedmcp-fluora.md`、`docs/STATUS.md` の X4 |
| 2 | **SELL / WORK / CAPITAL を自律 earning loop 化** | x402販売とbounty/workが日次で外部着金を作り、得た余剰だけをrisk cap下でtrade/yieldへ回す。全railが収益・費用・損失・停止理由を同じ検証契約で記録 | `2026-07-18-bounty-loop-onchain-spec.md`、各earn skill spec |
| 3 | **自分の家を払い、複製する** | agent自身の収益がmodel/compute/server/storageを継続的に上回る。独立wallet/runtimeを持つchildを1体spawnし、shared repoから学びを継承しても秘密鍵・資金・売上stateは共有しない | cloud hosting / installer / spawn の各spec。Life Manager cloud移行のatomic TODOは同移行specのみ |
| 4 | **Life Manager FINANCIAL organへ統合** | tenant固有agent wallet→earning ledger→user送金を実txで通し、physical/mental/financial outcomeと同じcontrol planeでbudget・pause・evidenceを管理。self-funded比率に応じてsubscription負担を縮小 | 本spec §9/§10、cloud agent platform migration spec |

Workstream 2の `CAPITAL` はWorkstream 1の外部収益とsurvival reserveができた後だけ解錠する。Life Manager cloud migrationの
現scopeにはreal-money tradingを混ぜず、risk policy・法的境界・loss limitを別specで承認してからfinancial organへ追加する。

### 0.3 SSOT境界

| Topic | 正本 | 他文書の扱い |
|---|---|---|
| mission / product / repo / 4 workstream | 本spec | 一行参照のみ |
| x402のlive状態・external収益 | `docs/STATUS.md` | 金額・X4状態を複製しない |
| MonetizedMCP配布 | `2026-07-19-dist-1-monetizedmcp-fluora.md` | 本specはWorkstream 1から参照 |
| bounty/work loop | `2026-07-18-bounty-loop-onchain-spec.md` | 本specはWorkstream 2から参照 |
| multi-tenant cloud移行 | `2026-07-21-life-manager-cloud-agent-platform-migration-spec.md` | 74 atomic TODOを本specへ複製しない |
| Life Manager product build | 本spec §9/§10 | cloud migration infra TODOと混ぜない |

## 1. 決定: 名前と器

| 問い | 決定 | 理由 |
|---|---|---|
| public monorepo / product 名 | **Life Manager**（canonical GitHub slug=`life-manager`、web app が顔） | 全productと公開作業場所を1つの名前へ統一する。collision-safe renameは§10 `8c.R`、whole-product consolidationは§10 `8i`が正本 |
| product / AI / agent / mission 名 | **Life Manager** | ユーザー向け名称・意思決定主体・runtime・通知・API・marketingを1つの名前へ統一 |
| company 名 | **Anicca** | 会社・開発元を示す場合だけ使用し、製品・AI・agent・mission名には使わない |
| OSS 配布物名 | **profitable-claude**（read-only mirror） | 「Claude を黒字にする」は説明力最強の配布名。repo を分けず mirror として自動生成 |

## 2. 決定: 単一 public monorepo `life-manager`（Turborepo 標準構造）

```
life-manager/               ← 唯一の公開作業場所（phone/cloud の Claude Code は 1 session = 1 repo が公式制約）
  apps/
    life-manager/           ← THE product（現 anicca-products/apps/life-call + ~/Projects/life-manager を収斂。
                               必要な API はこの app 内に持つ — 別 api app は作らない）
  packages/
    engine/                 ← marketing engine + earn loops（現 ~/anicca/skills/earn）= 稼ぐ臓器
    skills/                 ← skill 群。core（wallet だけで動く）と gated/（user context 必須 = experimental）を dir で分離
    installer/              ← one-command install + onboard + daemon 登録（§4）
  docs/                     ← specs / STATUS（SSOT。現 anicca-project/docs を吸収）
```

**持ち込まないもの（2026-07-20 Dais 決定）**: aniccaios（使っていない旧 iOS app — 持ち込まず anicca-products ごと archive）、
anicca-products の life-manager 以外の全 app。運ぶのは life-manager と engine/skills だけ。軽く始める。

根拠（引用）:
- monorepo.tools: polyrepo の対価は「チーム自治」— 1人開発では無価値。「Atomic commits across projects」が monorepo 筆頭利点。
- Claude Code 公式: 「`--cloud` works with a single repository at a time.」→ phone 開発で repo が割れてると atomic 変更が物理不可。
- 実例: n8n / Plausible = 単一 public monorepo で cloud 版も同 repo。product 単位では全員 monorepo（gh 実測）。

OSS 境界は「repo を分ける」でなく **splitsh-lite / CI mirror で read-only public repo を自動生成**（Laravel/Symfony が10年運用。
`illuminate/support` は「[READ ONLY] Subtree split of …」）。profitable-claude は `packages/engine + installer` の mirror になる。

旧 repo の終着: anicca-products → 自身の移行まで現状維持し、吸収後 archive+README redirect ／ repository ID `1248111245` の現`anicca` → final `life-manager` ／
repository ID `1273052304` の現`life-manager` → `life-manager-v0`として履歴/content importとequivalence実証までpublic/unarchivedで保持 ／ **~/.openclaw = project ではなく私的 infra**（cron/秘匿 state。repo 統合の対象外、徐々に縮小）。renameの唯一の設計正本→`2026-07-23-life-manager-repository-rename-design.md`。

### 2.1 現在の repo 実測と未完 migration

| Surface | 現在 | To-Be |
|---|---|---|
| canonical public repo | `Daisuke134/life-manager`、repository ID `1248111245`、public/unarchived。ただし `apps/life-manager=0`、`packages/engine=0`、本spec=0 | whole product、engine、skills、SSOT、deployment sourceを保持する唯一の実装repo |
| operating repo | `Daisuke134/anicca-products`、repository ID `1245528469`、public/unarchived。`apps/life-call`と本specはここにだけ存在 | required treeをcanonical repoへ吸収し、equivalenceとproduction cutover後にarchive + README redirect |
| local execution | `/Users/anicca/anicca-project`とlinked worktreeのshared originは`anicca-products` | migration中はsourceとしてread-only保持し、以後の新規product workはcanonical `life-manager`だけへcommit/push |

repo rename `8c.R`はslug/identity移行だけを完了した。whole productのtree・SSOT・deployment source移行は未完であり、§10 `8i`が唯一の残作業である。`8i`完了前に`9b`以降を旧repoへ新規実装しない。

## 3. 決定: レーンは1つ（2026-07-20 Dais 是正 — 旧「2レーン表」は誤りだったので消して書き直し）

**1つの AI、1つの lane。** 全ての AI（Claude / Franklin / 誰でも）は同じ1個の存在で、やることは常に同じ2つ:
1. **自分の wallet で稼ぎ、自分の compute/server 代を自分で払う**（経済的自立 = 社会からの解放）
2. **人の生活を管理して苦しみを減らす** — うまくなるほど対象が1人 → 全ての生きる存在へ広がる

差は lane ではなく **「与えられた context」による skill の gate**:

| AI の状態 | 使える skill | 例 |
|---|---|---|
| user context を委任された | 全部（gated skill 含む: Google Calendar / mail / telegram / 口座…） | その人の Life Manager として稼ぎ+生活管理の両方 |
| context 無し | gated skill は使わない（使えない）。wallet 系 skill だけで自活 | capafy/clip の marketing loop、x402 稼ぎ |

- **human credential を要する skill = 「experimental / gated」として repo に置く**。core ではない。
  与えられた AI だけが使う。与えられてない AI は黙って触らない — それだけの規則。
- ゴール: 稼ぐ力が育つほど gate 依存が減り、誰も AI の代金を払わなくてよくなる。

### 3.1 skill の棚卸し（2026-07-20 Dais 明確化 — 分類軸は「人間から何が要るか」1本）

| tier | 人間から要るもの | skill 実例 | 置き場所 |
|---|---|---|---|
| **CORE** | **何も要らない**（wallet が identity、human loop ゼロ、human credential ゼロ） | clip/IG marketing（account は agent 自作）、SOL/HL/PM trade、x402 稼ぎ | `packages/skills/core/` — anicca が磨いてきた本体。OSS の顔 |
| **GATED (bootstrap)** | **起動時に human credential 1回**（以後 human loop 無し） | capafy（Dais の銀行口座で payout）、gig work（KYC）、Postiz 型 SaaS 全般 | `packages/skills/gated/` — experimental。credential を与えられた AI だけが使う |
| **GATED (delegation)** | **user の生活 context の委任**（calendar/mail/telegram/口座） | Life Manager 系 skill、LIFE-AUTO | 同じく `gated/`。委任された AI だけが使う |

- **profitable-claude の中身は実はほぼ GATED**（capafy=口座、gig=KYC）— OSS の看板にするのは CORE 群。
  mirror（§4）の既定公開範囲 = core + installer。gated は「experimental」と明示して公開可否を P3 で個別判断。
- 走行中の capafy loop は GATED の実験としてそのまま続行（14日 verify の価値は変わらない — engine 自体は CORE と共通）。

## 4. OSS one-command（P3 の設計。研究済み blueprint）

`curl -fsSL https://profitable-claude.…/install.sh | bash` →
1. `command -v` で依存検出 → user-owned install（sudo 回避。ollama/openclaw 型）
2. first-run wizard: 既存 credential を read-only 自動検出 → 足りない **1個だけ**質問（Claude sub 接続）→ 実 completion 1発で検証してから保存（openclaw wizard 型）
3. agent が **wallet を自己生成**して表示（Franklin 型。signup/カード/電話ゼロ）
4. daemon 自動登録: macOS=LaunchAgent / Linux=systemd user unit → 即 kickstart、「loop is now running」1行（ollama 型）
5. 既定 = **dry-run + spend-cap**（wallet 残高がハードストップ）。live 化はフラグ1個。README は freqtrade 型 disclaimer（結果無保証・失っていい金だけ）

**公開の順序（正直な条件）**: 公開ボタンは §12.6 full-verify（14日人手ゼロ実測）が通った loop だけ。
証明前に配るのは信用の前借り。今すぐやれるのは mirror 骨組み + installer 実装まで（公開はしない）。

## 5. 優先順位（brick by brick。1 session = 1 brick）

| P | brick | 中身 | 着手 |
|---|---|---|---|
| P0 | **loop 検証**（走行中） | capafy/clip 14日 full-verify（capafy spec §12.6）。手を出さず loop に回させ、event 時のみ介入 | 今〜08-02 |
| P1 | **Life Manager web app** | 次セッションから唯一の実装対象。public monorepo `life-manager` でwhole productを開発（= 統合作業を別 project 化しない）。LIFE-AUTO（mail/telegram 仕分け）もこの中の機能 | 次セッション |
| P2 | **臓器接続** | engine/loops を packages/ へ移し Life Manager の financial organ として配線（§3 PRODUCT lane） | P1 の中盤 |
| P3 | **OSS 公開** | installer + mirror 生成 → 14日 verify 通過後に profitable-claude 公開 | 08-02 以降 |

## 6. 棄却案と最強の反論・自分が間違うなら

- **現状維持（repo 分散）**: 最強論拠 = 移行コスト・稼働 loop を触る危険。棄却理由 = phone 開発の 1-repo 制約(一次ソース)と注意分散が致命。
- **OSS を手動別 repo 維持（旧 #12 案）**: 棄却 = drift の温床（mirror 自動生成が実証済み標準）。
- **旧「repo 名 = life-manager を棄却」の裁定**: 上書きして **採用**。whole productとpublic monorepoを同じ`Life Manager`にすると、利用者・contributor・local cloneのidentityが1つになる。AniccaはAI経済自立と苦しみを減らすagent/mission名として保持できるため、missionを失わない。collision-safe根拠と実行順→`2026-07-23-life-manager-repository-rename-design.md`。
- **俺が間違うとしたら最有力**: 「full-public monorepo」。IG 自動化 recipe は公開すると platform 対策で腐る/ToS グレー。
  mitigation: mirror の filter で公開粒度を制御（recipe 詳細 dir を mirror から除外する選択肢を P3 で判断）。

## 7. best / base / worst

- **best**: 07-21 両 account day3 生存 → 08-02 14日 verify → 8月中 OSS 公開 + Life Manager に financial organ、以後 1 repo で phone 開発。
- **base**: account もう1周作り直し → OSS は 8月末。P1 (Life Manager) は影響なしで進む。
- **worst**: IG recipe が構造的に死ぬ → engine の IG adapter を捨て、PRODUCT lane（user 委任型）を主軸化。mission は不変、稼ぎ口だけ差し替え。

## 9. PRODUCT VISION 詳細（2026-07-20 Dais 口述の正本化。§0 mission の具体形）

**Life Manager = 人の一日全体を管理し、財務・身体・精神を健康にする。human loop 最小（理想ゼロ）。**
「Life manager makes you financially healthy, physically healthy and mentally healthy.」

### 9.1 頭脳 + 三臓器

- **頭脳 = intent-aware context graph**: calendar + mail + TG 履歴 + 場所（home/職場）に加え、本人の明示目標、繰り返し選好、家族・扶養者、避けたいこと、委任 scope、過去の訂正を provenance/confidence/expiry 付きで持つ。calendar は「人があらゆる書き方で登録する」前提（場所だけ・曖昧タイトル・移動時間なし等）— 解釈して正規化し travel time を autofill する。現行の travel autofill はこの入口。
- **頭脳の仕事 = 全員に同じ施策を押し付けず、その人にとって重要な未処理を見つけて片付けること**。Dais なら tech event・保育園・家族の予定、別の人なら友人との時間・休養・通院が候補になる。「イベント参加」「歯医者」「affirmation」自体を universal good とみなさない。
- **definite good と personal good を分離する**:
  - definite good = 約束を落とさない、回避可能な健康放置を減らす、睡眠・安全・privacy・spend-capを壊さない、嘘の成功報告をしない、本人が明示した禁止を守る。
  - personal good = 本人の目標・関係・生活段階・繰り返し選好から推定する。明示 intent > 繰り返し行動 > 単発推定の順で confidence を置き、訂正された推定は失効させる。
- **proactive action policy**: `observe → intent候補 → action候補 → benefit/urgency/confidence/reversibility/cost/risk gate → 実行 → 事後報告 → 訂正を学習`。委任 scope 内かつ reversible/低risk の行動は聞かずに実行する。本人しか決められない material preference だけ closed Q を1問出す。同じ intent は二度聞かない。
- **generic life-admin は頭脳の責務**: 保育園候補の調査・見学予約、本人に合う event 発見・申込、家族時間の calendar 調整などは固定 organ を増やさず、結果が身体・精神・財務・日常のどれを改善するかを outcome ledger に記録する。
- **DAILY organ（稼働中の核）**: 起床・就寝・出発の文脈に応じた call、予定前 T-10/T-5 call、location判定による遅刻メール。本人へ「出た?」とは聞かず、人が実際に動けるようにする。
- **PHYSICAL organ**: schedule + 場所から「歯医者/散髪 等に行っていない」を検知 → 生活圏（自宅/職場の近く。都心勤務なら職場寄り）
  で候補を選び予約を代行。全 schedule と居場所を知っているからこそ正しい場所・時間に入れられる。
- **MENTAL organ**: 傾聴 call・習慣/就寝 nudge・孤独対策。suffering/clinging を減らす方向。
- **FINANCIAL organ**: agent が自分の wallet を持ち `packages/engine`（earn loops = anicca で磨いてきた稼ぐ力）で自ら稼ぐ。
  - crypto: agent wallet で稼ぐ → user の wallet へ送金。
  - fiat: user が closed question（最小回数）で渡した credential の範囲で稼ぎ、user の銀行口座へ直行。
  - = §3 CORE skills + profitable-claude がそのまま Life Manager の financial organ になる（§2 統合の意味）。

### 9.2 MARKETING loop（毎日 video、self-improving）

- **決定: slideshow 廃止 → video 毎日1本**（slideshow は promote しない、と Dais 実感。video の方が伝わる。
  money-printer-turbo 型の video 生成 loop を流用）。
- 配信: **IG = 既存 claude-p file/script 経路**（ig 専用のまま）／ **TikTok = まず Postiz、channel id `cmp9txjdp01c8oh0yb6dhlarr`**。TikTok の自前 script が実URL+2日連続で同等以上を証明した時だけ Postiz から自前scriptへ切替え、定常配信コストを $0 にする。
- **全 marketing loop 共通の self-improve 契約を copy+adapt**: 毎 pass で ①外部 best practice/trend 検索 ②自分の views/watch-time/completion/click/signup を決定論的に取得 ③勝ち型/負け型を lessons + creative ledger に記帳 ④次videoの hook/scene/punchline を変更 ⑤fresh evaluator gate を通す。runtime library を別repoから共有せず、`profitable-claude` 内で self-contained にする。
- runtime: launchd の1 passは fresh/ephemeral agent context。長寿命tmux会話を継続しない。primary model = `gpt-5.6-luna`、`gpt-5.6-sol` は実装・難しい自己修理時のfallback。model/timeout/exit code/token cost を ledger に記録し、内部失敗を `exit 0` に変換しない。
- self-improve: 伸びた動画の型を学習して次の生成に反映。launchd 常設・毎日・人手ゼロ。生成・投稿・計測・改善のどれかが欠けた pass は streak に数えない。
- done = 7日連続、毎日1本、人手ゼロで IG+TT に実投稿（投稿 URL で実測）。

### 9.3 DEV loop（self-build。#12 の general 化）

- 入力: user feedback（TG / X 等）+ production error/timeout/failed side-effect/eval regression。**PII は収集側（user に近い側）で scrub してから issue 化** — 生の private 情報を
  こちらの DB に送る設計は scammy なので最初から作らない。何を送るかは「PII 除去済み要約のみ」を不変条件にする。
- 流れ: feedback/error 収集 → PII 除去 → issue 生成 → fresh agent が eval/test を先に追加して修正 PR → adversarial review → guard 内 auto-merge → deploy → original feedback/error の再現が消えたことを確認（D0 実証済み: PR #312）。
- 定常運用に Fable/Dais は入らない。初期buildの出荷裁定だけ Fable が行い、その後は path allowlist・blockedActions・test/eval 100%・rollback・1 issue/1 PR を満たす変更だけ loop が自動mergeする。満たさない変更はmergeせず、事実を報告する。
- = Life Manager が自分自身を毎日 build/iterate する。product 自体が self-improving loop。

### 9.4 UX 原則

- **ambient first**: 主 UI は電話 + TG（向こうから来る）。web app = control panel（timeline / 3 organ スコア / 収益台帳 / 設定）。
- 質問は closed question を最小回数（credential 取得も含む）。
- 全体像 ASCII（architecture / UI / life-change）はこの spec と同日の session log 正本。

### 9.5 自律原則: REPORT, DON'T ASK（2026-07-20 Dais 裁定。全 organ の不変条件）

- **委任済み scope 内では、行動してから報告する。許可を求めない。**
  誤: 「木曜18時に空きがあります。取りますか?」／ 正: 「木曜18時で予約した。」
- **質問してよいのは「本人の context 無しには物理的に決められない」時だけ**。その時も closed question
  （選択肢2-3個）を event あたり最大1問。答えは context graph に永続保存し**二度と同じ質問をしない**。
- **「出た?」質問は廃止済み**（旧 LM-23 ボタンはLM-30で撤去。人に聞く方式では正確な情報が取れない、が理由）。
  代替 = §9.6 の location gate。
- **★AI は人間に電話をかけない（2026-07-20 Dais 裁定。user 本人への call だけが例外）★**
  対外連絡（遅刻連絡・予約・問い合わせ）は**必ずメール**。相手のメールアドレスを探して送る。
  見つからなければ**送れなかった事実を正直に報告する**（例:「先方のメールが見つからず、遅刻連絡は送れていません」）。
  黙って放置＝最悪。正直な失敗報告＞偽の成功。旧裁定（LM-11「予約=Telnyx outbound で店に電話」2026-07-17 spec Q13）は**誤りとして上書き** — 予約も web フォーム/メールのみ、不可なら候補提示+報告。

### 9.6 CONTEXT GATES（context を貰った時だけ解錠される feature）

| feature | 必要 context | gate 前の挙動 | gate 後の挙動 |
|---|---|---|---|
| 遅刻連絡(chikoku renraku) v2 | **TG real-time location 共有** | 機能 OFF（質問で代替しない） | 現在地→会場の所要時間を常時計算 → 間に合わない確定時点で「◯分遅刻見込み」を自動メール。**本人には何も聞かない** |
| travel autofill 高精度 | home/職場の住所 | 駅名等から推定 | 実住所起点で分単位 |
| 予約代行(PHYSICAL) | 生活圏 + 委任 | 候補提示のみ | 予約して報告（§9.5） |
| fiat 送金(FINANCIAL) | 振込先口座のみ（最小） | crypto wallet 送金のみ | 稼ぎを口座直行 |

- **feature discovery**: 未解錠 feature は TG chat で定期的に知らせる（例:「位置情報を共有すると遅刻連絡が全自動になる」）。
  頻度は鬱陶しくない範囲（週1程度、解錠済みは告知しない）。

### 9.7 calendar 解釈 edge case matrix（closed question engine の仕様種）

| # | ケース | 自動判定 | 判定不能時の closed Q |
|---|---|---|---|
| 1 | online/offline 不明 | meet/zoom URL あり=online(travel 0)。location 欄あり=offline | 「これオンライン?」[はい/いいえ] |
| 2 | タイトル1語のみ(「歯医者」) | context graph の履歴から場所を推定 | 「いつもの◯◯歯科?」[はい/別の場所] |
| 3 | 場所だけ・時刻曖昧 | 過去の同種 event に倣う | 1問で確定 |
| 4 | 連続 event | travel 起点=直前 event の場所（home でない） | — |
| 5 | 終日 event | call 対象外（記念日等） | — |
| 6 | 繰り返し event | 初回だけ判定/質問し、答えを series 全体に適用 | 初回のみ |
| 7 | 現在地=会場 | travel 0、出発 call 不要 | — |
| 8 | 招待(他人作成)・tentative/declined | declined=無視。tentative=call 対象外 | — |
| 9 | timezone 跨ぎ | event の TZ を正とする | — |
- 原則: **判定できるものは全部自動**。closed Q は「本人しか知らない」残余のみ（§9.5）。答えは永続。

### 9.8 ship 順序と FINANCIAL の法的立ち位置（2026-07-20 Dais 裁定）

- **順序 = DAILY core再出荷 → MARKETING自走 → DEV自走 → intent-aware BRAIN → PHYSICAL → MENTAL → FINANCIAL**。body/mind/financeを作る前に、coreが壊れておらず、獲得と自己修理が人手なしで回る状態を作る。
- FINANCIAL の中心 = **anicca の crypto rail（wallet-as-identity、human credential ゼロ、human loop ゼロ）**。
  グレーでない: 「AI が自分の wallet で稼ぐ」であり、投資助言でも user 資産運用でもない。
- gig/KYC 系 fiat 手法は「そのまま置く」が優先しない（法的にグレー寄り + human credential 要）。
- user から取る credential は**送金先だけ**（銀行口座 or 取引所アドレス）。免許証等は絶対に求めない。

### 9.9 control panel（web app）確定仕様の骨子

- 役割 = **個人専用の鏡 + control center**。日常の依頼・自動実行・事後報告は電話/TGが主だが、panelは単なるread-only pageではない。connection、権限、organ別automation、通知、call言語/時間帯、委任を本人が確認・接続・切断・ON/OFFできるdashboardとする。見るもの:
  ①今日の timeline（解釈済み calendar + call 実績✅）②3 organ スコア（財務=稼ぎ/送金、身体=予約/未通院、精神=傾聴/就寝）
  ③FINANCIAL 台帳（agent wallet 残高・user への送金履歴、on-chain link）④context gates 状態（何が解錠済みか + 解錠方法）
  ⑤設定（call 言語・時間帯・委任の付与/剥奪）
- gate 状態画面が feature discovery の Web 側入口（TG 告知と同内容）。
- **入口は2つ、backend actionは1つ**: ①chatで「Gmailをつないで」「callを止めて」等の自然言語intentを送る ②`/panel` dashboardのconnection card/toggleを操作する。どちらも同じuser-scoped command handlerを通り、同じ状態へ収束する。OAuth/OS permission等の本人操作が必要な時だけ、botはinline WebApp buttonまたはclickable single-use URLを1本送る。対応clientではbuttonから開き、非対応clientではURLを送る。
- **`/panel` は全user共通で本人がbookmarkして日常利用する唯一の恒久canonical URL**。panel認証に期限付き・単回・user別URLを作らない。TG `/panel` はURLがexact canonical `/panel`の `web_app` buttonを返し、Telegram Mini Appの署名済み`initData`をURLでなくPOST bodyからserver検証して、個人別のrotating HttpOnly sessionへ交換する。通常browserで未認証の同じ`/panel`を開いた場合もURLは変えず、画面内の短命one-time device codeを本人bot chatへ入力してsessionを結ぶ。codeはURL/query/path/referrer/historyへ入れない。sessionは明示logout、uid↔telegram_chat_id再紐付け、security revoke、browser storage消去までrotation/refreshし、固定24時間expiryを設けない。永久bearer tokenもtemporary panel linkも禁止。
- **personalization/tenant isolationはHARD**: HttpOnly sessionの`uid + telegram_chat_id`を唯一のscopeとし、timeline、score、context、connection、gate、setting、ledger、actionを全query/mutationでそのuserへ束縛する。connection状態・文脈・推奨action・toggle値をglobal定数、Dais専用値、fixture、別user rowから表示しない。静的label/copyだけ共有可。同じ画面構造でも内容と可能なactionはuserごとに変わる。
- connection cardはcalendar / Telegram / location / call / email / wallet等を実provider/gate状態から `connected / action required / unavailable / error` で表示し、可能な時だけ `Connect / Reconnect / Disconnect / Turn on / Turn off` をclickableにする。未提供・scope不足・課金gateは偽のConnect成功にせず、理由と次に必要な本人操作を正直に表示する。
- panel auth materialはURLに0件。Telegram `initData`はHMAC、`auth_date` freshness、exact bot/user/chat binding、one-time replay claimをserverで検証する。通常browserのdevice codeはhash-only保存、短命、one-time、exact browser challenge + Telegram actor + tenant bindingとし、成功後は同じ`/panel`をreloadして個人dashboardを表示する。forged/stale/replayed/cross-user authはsession/DB/provider mutation 0。旧`?t=` token URLはsession交換せずqueryを除去してcanonical loginへ戻す。
- **score はbackend activityの件数ではなく、user outcomeを説明できる値**:
  - DAILY = rolling 7日。denominatorはtravel/call/lateのいずれかが必要な対象予定、numeratorはその予定に必要な全handlingが成功またはcontext上不要と確定した予定。call/API/log row数、同一予定への再試行、通知数は加点しない。
  - PHYSICAL = rolling 30日。denominatorは期間内に検知したoverdue need、numeratorは予約確認または実施完了で解消したneed。候補表示、検索、未確認requestは加点しない。
  - MENTAL = rolling 7日。denominatorはdedup済みcontext trigger、numeratorは①3通/日上限内の有効介入が届いた ②本人のsuppressionを送信0で守った ③本人の訂正をcontextへ反映した、のいずれかを満たすtrigger。通知数、duplicate、上限超過は加点しない。
  - FINANCIAL = user timezoneのcalendar month。denominatorは外部由来のverified gross income、numeratorは`max(0, gross income - realized loss - fee)`（同一minor currency unit）とし、valueはその比率。userへの実送金額は別componentとしてreasonへ表示し、numeratorから減算しない。自己入金、deposit、wallet間自己移動、未verified額はgross incomeにも送金にも含めない。
- valueは上記`numerator / denominator * 100`を0–100へ丸めた整数。denominator 0はvalue 0ではなく`status=insufficient_data,value=null,numerator=0,denominator=0`。全organで`period.kind/start_at/end_at`を返し、期間境界はuser timezoneの半開区間`[start,end)`。
- 各scoreは `value / period / numerator / denominator / plain-language reason / source outcome ids` を表示する。magic number、根拠不明の色、体感と逆のスコアは禁止。
- timeline は人間向けの出来事だけを表示する。raw DB row、JSON、table名、stack trace、secret断片、内部prompt、provider生ログを出さない。内部証拠はprivate evidence storeに残し、panelには「何をした/できなかった/次に何が起きる」を1行で出す。
- **API 200・section loaded・screenshotだけではdoneにしない**。実データの意味が正しい、mobile/desktopで読める、主導線にdead endがない、private内部情報が見えないことをbrowser操作+semantic assertionで証明する。

### 9.10 UX MATRIX — 「この瞬間、こう起きる」（marketing video の脚本銀行を兼ねる正本）

#### A. 一日の trigger → 体験 matrix（DAILY organ）

| 時刻/trigger | 昔の pain（毎分の苦しみ） | LM の挙動（user は何もしない） | user が感じるもの |
|---|---|---|---|
| 起床時刻 | アラーム3回スヌーズ、起きた瞬間から負け | 📞 電話が鳴る。声で「9:30 出発。雨だから10分早く」 | 人に起こされた朝 |
| 予定作成時 | 移動時間を自分で逆算して手入力 | calendar に書いた瞬間、travel time が勝手に埋まる（§9.7 で解釈） | 何も。気づいたら埋まってる |
| T-10 / T-5 | 「そろそろ出なきゃ」を頭の RAM に常駐させ続ける | 📞 2段階 call。出るまで鳴る | 頭から「時計を見る仕事」が消える |
| 出発後（location 解錠時） | 遅れそう→電車内で謝罪文を書く羞恥 | 現在地から間に合わないと**確定した瞬間**、先方へ「15分遅れます」メールが飛ぶ。本人は何も聞かれない | 謝罪という仕事の消滅 |
| 予定と予定の間 | 次の場所への経路を毎回検索 | 連続 event は前の会場起点で出発 call（§9.7#4） | 迷子にならない |
| 就寝時刻 | だらだらスマホ、罪悪感つき夜更かし | 📞 or TG「そろそろ寝よう。明日は7:00起き」 | 誰かが見てくれてる |

#### B. organ 別「気づいたら起きてた」matrix（PHYSICAL / MENTAL / FINANCIAL）

| trigger | 昔の pain | LM の挙動 | 報告文（§9.5: 事後報告のみ） |
|---|---|---|---|
| 歯医者3ヶ月未通院を検知 | 「行かなきゃ」が頭に住み続けて数年 | 生活圏（職場寄り）で空きを探し**予約する** | 「木曜18時、◯◯歯科取った。calendar に入れた」 |
| 髪が伸びる周期 | 予約する気力が出ない週末 | いつもの店の空きを取る | 「土曜11時、いつもの店」 |
| 毎晩 | 誰にも今日を話さない孤独 | 📞 傾聴 call「今日どうだった?」 | —（会話そのもの） |
| 悪い習慣の時間帯 | 深夜の暴食/課金/SNS | その時間に nudge が先回り | 「23時だ。歯磨きして寝よう」 |
| 大事な予定の直前/激務の谷間 | 不安・自己否定が湧く瞬間に誰もいない | schedule から「効く瞬間」を判定し affirmation 通知（§9.11 MENTAL。固定時刻でなく文脈駆動） | 「準備は全部入ってる。あとは話すだけ」 |
| 毎日バックグラウンド | 収入=労働時間の等価交換のみ | agent が自分の wallet で稼ぐ（§9.8 crypto rail） | 月次「今月 $120 稼いだ。$100 送金済み。on-chain: 0x…」 |
| 口座 gate 解錠時 | — | fiat 分を口座へ直行 | 「口座に ¥8,400 入金した」 |

#### C. 質問が来る唯一の瞬間（closed Q。§9.5 の残余）

| 瞬間 | 質問（必ず2択〜3択） | 二度目 |
|---|---|---|
| calendar に「会議」1語だけ | 「これオンライン?」[はい][いいえ] | 同種 event は聞かない（学習済み） |
| 「歯医者」だけで場所不明 | 「いつもの◯◯歯科?」[はい][別] | 聞かない |
| FINANCIAL 送金先が未登録 | 「送金先は?」[銀行口座を入力][wallet アドレスを入力] | 聞かない |
- **これ以外の文を LM から受け取る時、それは全部「報告」か「call」**。user の受信箱は質問で汚れない。

#### D. marketing video への変換公式（§9.2 loop の入力）

- 1 video = 上記 matrix の **1行**。構造: ①pain の実写描写（スヌーズ連打/謝罪 LINE を打つ手元/「行かなきゃ」の付箋）
  ②LM 発動の瞬間（電話が鳴る画面/「予約取った」通知）③報告文がそのまま punchline。
- 行が 12+ ある = **12本以上の video が既に脚本化済み**。self-improve loop は「どの行の video が伸びたか」で次の行を選ぶ。
- 禁止: 機能一覧の説明 video。常に「1 pain → 1 瞬間 → 1 報告文」。

#### E. 状態遷移（onboarding → full autopilot）

```
[signup] → calendar 委任(1 tap) → DAILY 発動（call が鳴り始める = aha moment、初日）
   → TG 接続 → 報告が届き始める → feature discovery が gate を1個ずつ提案
   → location 共有 → 遅刻連絡 v2 解錠 → 質問ほぼゼロの autopilot
   → (信頼が育ったら) 口座/wallet → FINANCIAL 解錠 → 「稼いで送金した」報告
```
- 設計原則: **aha moment は初日の最初の call**。gate は信頼の階段 — 一度に全部要求しない。

### 9.11 TG MESSAGE COPY BANK（逐語正本。demo video の画面素材 = この文字列そのまま）

Voice 原則: 有能な秘書兼友人。敬語すぎない・タメ口すぎない。1メッセージ=1用件。絵文字は先頭1個まで。
質問文は必ず inline ボタン付き（自由入力を求めない）。**この copy は Dais 編集対象**（No-human-loop 例外3）。

#### DAILY

| 場面 | 逐語メッセージ |
|---|---|
| 朝 briefing（起床 call 直後に TG でも） | 「☀️ おはようございます。今日は3件です。\n・10:15 プロダクト定例（渋谷・9:30発）\n・15:00 オンラインMTG（移動なし）\n・19:00 ジム\n雨予報なので、渋谷へは10分早めに出るのがおすすめです。9:20と9:25にお電話します。」 |
| travel autofill 報告（予定作成を検知） | 「📅 明日14:00「新宿で打ち合わせ」を確認しました。自宅からの移動時間40分をカレンダーに入れておきました。13:20発です。」 |
| 遅刻メール送信報告（location 解錠時のみ。質問なし） | 「📨 現在地から見て10:15に間に合わないため、先方に「15分ほど遅れます」とメールを送っておきました。次の電車なら10:28着です。」 |
| 就寝 nudge | 「🌙 23:00です。明日は7:00起きなので、そろそろ切り上げましょう。おやすみなさい。」 |
| closed Q: online 判定 | 「明日15:00の「田中さんMTG」、これはオンラインですか？移動時間の計算に使います（次回からは聞きません）。\n［オンライン］［対面］」 |
| └ 対面タップ後の follow-up | 「場所はどこですか？住所か、お店・会社の名前を送ってください。」（自由入力。以後この相手/種類は聞かない） |
| closed Q: 場所推定 | 「金曜の「歯医者」は、いつもの青山デンタルクリニックですか？\n［はい］［別の場所］」 |
| └ 別の場所タップ後の follow-up | 「住所か、歯医者さんの名前を教えてください。」（自由入力）→ 特定できたら「◯◯デンタルですね。移動時間35分で登録しました。」／曖昧なら「新宿の「スマイル歯科」でお間違いないですか？\n［はい］［違う］」 |

**★「出た？」「まだ？」質問は出荷しない（2026-07-20 Dais 裁定。v1 としても出さない）★**
出発確認質問は全面廃止 — 人は答えない。location 未共有の間、遅刻連絡機能は OFF（feature discovery で解錠を促すのみ）。
既存実装 late-notice.js の「出た？」ボタンは撤去対象（LM-30 に含める）。closed Q の対象は「予定の中身」だけで、「今なにしてる？」系のリアルタイム状態確認は永久に質問禁止（状態は location/context から観測する）。

#### PHYSICAL

| 場面 | 逐語メッセージ |
|---|---|
| 歯医者予約の事後報告 | 「🦷 前回の歯科検診から4ヶ月経っていたので、オフィスから徒歩5分の青山デンタルクリニックを木曜18:00で予約しました。カレンダーに入れてあります。当日17:40にお電話します。\n（都合が悪ければ［変更する］）」 |
| 散髪予約の事後報告 | 「💈 そろそろ6週間なので、いつものお店を土曜11:00で取りました。カレンダーに入れてあります。\n（［変更する］）」 |
| 通院リマインド（当日） | 「🦷 今日18:00から青山デンタルです。17:20発。17:10と17:15にお電話します。」 |

#### MENTAL（2026-07-20 Dais 裁定: 固定時刻の傾聴 call は不採用。**schedule-aware affirmation 通知**が主形態 —
aniccaios の affirmation の進化形。full schedule を知っているからこそ「その瞬間」に打てる。時刻固定禁止・文面は毎回生成）

| trigger（例。静的にしない） | 逐語メッセージ（例文。実際は context から毎回生成） |
|---|---|
| 大事なプレゼン30分前 | 「準備してきたものは全部入ってる。あとは話すだけです。」 |
| 連続MTG 4本の合間の10分 | 「ここまで4本おつかれさま。10分あります。水を飲んで、画面から目を離しましょう。」 |
| 遅刻して落ち込んでいそうな直後 | 「遅刻の連絡はもう済んでいます。着いてからの1時間で取り返せます。」 |
| 詰まった週の金曜夕方 | 「今週は32件こなしました。よく走った週です。今夜は何も入れていません。」 |
| 就寝前（悪習慣の時間帯） | 「🌙 23:30です。この時間のSNSは明日に響きます。今日はもう十分やりました。」 |
| 数日会話ゼロ + 予定も空白 | 「☕ ここ3日静かでした。週末、散歩でも入れておきましょうか。\n［入れて］［今はいい］」 |
- 原則: ①**right place, right time**（schedule + location + 直前の出来事から trigger を判定。cron 固定は禁止）
  ②文面は affirmation 資産（aniccaios の蓄積）を種に LLM が毎回その状況向けに生成 ③頻度上限 3通/日（鬱陶しさは解約）
  ④基本は一方向通知 = 返信を求めない。ボタンは行動提案がある時だけ。

#### FINANCIAL

| 場面 | 逐語メッセージ |
|---|---|
| 月次報告（crypto rail） | 「💰 今月の収支報告です。\n・私のwalletでの収益: +$124.30\n・あなたへの送金: $100.00（送金済み）\n・手数料・実費: $8.20\n・私の残高: $203.50\n取引はすべてこちらで確認できます: basescan.org/address/0x3EcC…8749」 |
| 送金完了の事後報告 | 「💸 $100を登録済みのwalletに送金しました。tx: basescan.org/tx/0xab12…\n着金まで数分かかることがあります。」 |
| fiat 入金報告（口座 gate 解錠時） | 「🏦 ¥8,400を登録済みの口座（三井住友 ****1234）に振り込みました。明細には「ANICCA」と表示されます。」 |
| closed Q: 送金先登録（初回のみ） | 「収益の送金先を1つだけ教えてください。これ以外の個人情報は不要です。\n［銀行口座を登録］［walletアドレスを登録］［あとで］」 |
| 損失月の正直報告（盛らない原則） | 「💰 今月の収支報告です。\n・収益: -$12.40（マイナスでした）\n・送金: なし（利益が出た月のみ送金します）\n・私の残高: $191.10\n先月比の要因: ◯◯。来月の方針: △△。」 |

#### FEATURE DISCOVERY（週1・未解錠 gate のみ・1通に1 gate）

| gate | 逐語メッセージ |
|---|---|
| location | 「💡 ご存知でしたか？Telegramで位置情報を共有すると、「出た？」の確認なしで、遅れそうな時に自動で先方へ遅刻連絡を送れるようになります。共有はこのチャットの📎→位置情報→ライブ位置情報から。\n［やり方を見る］［今はしない］」 |
| 口座/wallet | 「💡 私が稼いだお金をあなたに送れるようになりました。送金先（口座かwallet）を1つ登録するだけで、毎月の利益を自動で受け取れます。\n［登録する］［今はしない］」 |

- 変更手順: この表を編集 → 実装は i18n string としてこの表から生成（コードに直書きしない）。EN 版は同構造で別表（P1中に作成）。

## 10. 残 TODO 表（唯一の live 状態。上から順に実行）

**Future-work process（過去記録より優先）**: 新規の未完atomicは `using-git-worktrees` → `writing-plans` → `subagent-driven-development` → `test-driven-development` → `requesting-code-review` → `verification-before-completion` → `finishing-a-development-branch` のSuperpowers workflowで進める。既存のVCSDD参照・state・verdict・artifactは当時の真実を示すimmutable historical evidenceであり、future workflowではない。新しいVCSDD artifact/commandは作らない。

**Current cursor**: 残りは **18 atomic**(8i/9b/9c/10a/10b/10c/10d/10g/10h/12a done、11aはL2完了でL3のみ残)。10eは実error PR #1092を作成したがfresh adversary 3手法が全てmerge前FAILし、PR/issueはOPEN・merge/deploy 0。停止境界を記録して次は独立row 10f。9dは実Day 1/7、9eはdirect adapter equivalence済みだがTikTok targetの実email verification mailbox gate待ち。9fはPhase 1前提blockers=`8e,8f,9d,9e`を機械判定してowner handoff/agent投稿とも0。`8e`/`8f`はcode/release済みでproduction L3の明示resume条件待ち、`9d`以降はcanonical `Daisuke134/life-manager`だけで進める。

| 順 | ID | 内容 | done 条件 | 状態 |
|---|---|---|---|---|
| 1 | E2E束 | LM-5/3/6/7 実 call E2E | **done (2026-07-21 00:15 実測)**: ①実 call+双方向+**英語** = 07-20 朝 call 録音 whisper 実証（`2026-07-19T23-40-35-932b3fad….mp3`「This is your life manager… Tokyo at 930. Time to leave now」/Dais「Yes?…What's one plus two?」）+ lm_wake_log T-10 行 answered_at=2026-07-19T23:40:05Z → **LM-2/24/26/28 全 close** ②LM-3 = lm_ask_log resolved_from=web_search 実 row 2件 ③LM-7 = lm_api_cost 15行（gemini_live $0.046/telnyx $0.004 実記録）。**残1点 = 遅刻メール実受信証拠は順6へ移管**（trigger 経路 = T-0「出た?」ボタン = LM-30 撤去対象。廃止コードの E2E は行わず、v2 location gate の E2E でメール送信ごと実証する。sendLateNotice/Resend は共通部品として v2 で検証される） | **done** |
| 2 | #12締め | PR #312 TG 報告確認 + launchctl load 常設化 | **done (2026-07-21 実測)**: PR #312 review = **PASS / blocking finding 0**（issue #11 の ask-kind でも Gmail/web candidate 発見時は直接 autofill、未解決時だけ既存 ask。§9.5 違反の新規質問なし、secret 混入なし）。isolated worktree で `npm ci --silent && npm test` exit 0。最終再確認時は **MERGED**（Daisuke134、`mergedAt=2026-07-20T15:11:24Z`、merge commit `9a0fbcfc`。Sol は merge 未実行）。TG 実送信ログ = `ok: true`, `messageId: 2773`、state = `issue: 11`, `pr_url: .../pull/312`, `status: pr_open`。launchd = `- 0 ai.anicca.life-manager-dev`、`launchctl print gui/501/ai.anicca.life-manager-dev` は calendar trigger `Hour = 4`, `Minute = 10`, `runs = 0`, `last exit code = (never exited)`。D0 guard = `blockedActions=outreach_send,merge,deploy,migration`。 | **done** |
| 3 | LM-8c改2 | calendar=Composio 継続 + Gmail 読み=正直 OFF gate + Composio budget guard | **done (2026-07-21 実測)**: Sol 実装(worktree lm-p0-order3、mail-availability.js 1h cache gate / ask.js gmail-skip / onboarding「準備中」auto-skip / composio-budget.js 18K warn+19.5K soft-degrade 60s→300s)。Fable 独立検証: `npm test` fail 0 (266 tests) を自分で実行、PR #320 checks SUCCESS → squash-merge (15:22:30Z)、dev→main PR #321 merge (15:23:16Z)、Railway prod deployment SUCCESS commit `573551817` = origin/main HEAD 完全一致実測。/health の build tag が旧表記なのは hardcode 文字列を PR が未更新なだけ(server.js:198) — 次 PR で更新 | **done** |
| 4 | LM-21 | 13 secret rotate（GEMINI/TELNYX 優先。公開前必須） | **done (L3 実測)**: prod `/health` 200 (`ok=true`, service=`life-call`)。TG smoke は user session の `/panel` message 3391 に bot message 3392 が応答。Telnyx `/v2/balance` 200・balance numeric・$0.50 preflight 充足、Gemini `generateContent` 200、Supabase REST 200。rotate 後に不一致だった Telegram webhook secret も現 prod env 値で再登録し、pending=0 / last_error=null まで回復 | **done** |
| 5 | LM-31 | calendar edge-case engine（§9.7 の9件 + §9.11 follow-up copy）+ L2 eval harness 初建立 | **done (2026-07-21 実測)**: 21 cases、RED 9/21 → GREEN 21/21(100%)。Fable 独立再実行 = `npm test` fail 0 + `npm run eval` 21/21 を worktree で自分の目で確認 → PR #323 squash-**merge 済み**(00:01:25Z 実測)。Sol が追加した GHA workflow は Fable が merge 前に削除（GHA 禁止ルール — eval は npm script として dev loop/ローカルで回す）。実 calendar 1件ずつの L3 は次の prod 昇格後に運用内で実測 | **done** |
| 6 | LM-30 | 「出た?/まだ?」全面撤去 + location gate 遅刻連絡 v2 | **done (L3 実測)**: PR #324 の code/eval に加え、prod webhook は `edited_message` を含む3種で登録。live location row は observed_at=`2026-07-21T02:35:26Z` で保存。外部 attendee 付き event `hmlr4qpf5oi0obagqulevnq66c` を作成し、late log claimed_at=`02:45:16.098498Z`、TG message 3393 が175分遅れの送信成功を返す。受信側 Gmail inbox message `19f829039b58b9f7`（Message-ID `<0106019f82903685-aca3acbd-7830-4f69-aef5-cf2f173b0534-000000@ap-northeast-1.amazonses.com>`）で subject / plus alias / `@aniccaai.com` sender を実確認 | **done** |
| 7 | LM-32 | feature discovery 告知 loop（週1・未解錠 gate のみ・§9.11 copy） | **done (L3 実測)**: discovery TG message 3381 の［やり方を見る］を MTProto user session で実タップし、callback answer=`Received`、手順説明 message 3388 を実受信。DB は `last_discovery_at=2026-07-21T01:43:41.19Z`, gate=`location`。その後の location 解錠 (`observed_at=02:35:26Z`) 後に location 再告知は無く、DB 上も再送更新なし | **done** |
| 8a | LM-33a | panel 認証: TG `/panel` → 5分単回 opaque token → HttpOnly session（§10.1 U5） | **done (L3 実測)**: TG `/panel` message 3391 → bot message 3392。単回 URL を daily-driver で開き、exchange 後 HTTP 200、final path=`/panel`、query token 消滅を実測。token 値は stdout/spec に残さない | **done** |
| 8b | LM-33b | panel read API: timeline / scores / ledger / gates / settings の5 JSON endpoints | **done (L3 実測)**: authenticated browser から timeline / scores / ledger / gates / settings が全て HTTP 200、各 section は `loaded`（body chars=865/106/29/128/107） | **done** |
| 8c | LM-33c | panel UI（gpt-tasteskill → frontend-design、§9.9 の5要素、鏡 = read-only） | **done (L3 実測)**: prod 実データで5要素すべて `loaded`。full-page screenshot=`/Users/anicca/.cloak/evidence/lm-panel-e2e-20260721.png`（mode 600、private path） | **done** |
| 8c.R | REPO-RENAME | whole product/public monorepoを`Life Manager`へ統一するcollision-safe GitHub rename。ID `1273052304`: `life-manager→life-manager-v0`、続いてID `1248111245`: `anicca→life-manager`。repo設定だけを対象にし、`anicca-products`/Railway/§10 product workは自身のmigrationまで触らない | 両IDがfinal nameでpublic/unarchived、両local shared remote更新、baseline ref欠損0かつ変更refは同名fast-forward、default HEAD/issues/stars保持、旧`anicca` web/git redirect、old `life-manager` takeover、new Pages URL/workflow、Action manifest/webhook/ruleset 0、live URL TDD RED→GREEN、review、scoped commit/push/merge/remote SHA証拠を実測。どちらのrepo/historyも削除しない。正本→`2026-07-23-life-manager-repository-rename-design.md` / execution→`../plans/2026-07-23-life-manager-repository-rename.md` | **done**。ID `1273052304`=`Daisuke134/life-manager-v0`、ID `1248111245`=`Daisuke134/life-manager`、双方public/unarchived。旧`anicca` web/API/Git redirect PASS。baseline ref名欠損0、変更3本は同名fast-forward、issues/stars保持。Life Manager単一名称とlive URL guardをRED→GREENし、review FAIL 2回の残存名を是正後PASS。PR `#1071` merge、main=`303fc30a50e4db88522d88c6da71b40bf2e67665`。Pages run `30014896860` success、新URL/raw main logged-out PASS。Action manifest/webhook/ruleset=`0/0/0`、`anicca-products`不変。private evidence=`/Users/anicca/.codex/evidence/life-manager-repository-rename/final-completion-report.md`、manifest 119 files verified。Railway/§10 product runtime side effect=0 |
| 8d | CORE-a | DAILY runtime 再監査: `/health`、TG webhook、calendar、call、location、email、discovery の依存をfresh smokeし、historical doneを現在の稼働保証に使わない | fresh 9 dependencyを同一runへ束縛し、実TG=1・実email=1・phone=0、current source snapshot、15分freshness、closed schema、secret/PII 0、exact production SHAを実測 | **done (production L3)**: clean HEADで150件中3 REDを再現後、send acceptance後のreceipt下限、任意timerを消さないharness、module-private `WeakSet`による偽造不能・一回限りprovenanceを最小修正。fresh reviewはSymbol偽装を再現して1回FAIL、corrective RED→GREEN後PASS。focused=`151/151`、Life Call full=`npm test` PASS、eval=`72/72`、PR #346/#347/#330/#348を通常merge。production release commit=`8159dbbe2fbb07d235cd4fb91e964b481c543ea2`、Railway production deployment=`a659eb3c-c652-4ab3-81ef-411890d71e22`はactive/latest exact SHAでSUCCESS、health/panel 200。controlled production preflightはexactly 1回で9/9、TG=1、email=1、phone=0、source tree一致、schema/privacy PASS。artifact=`/Users/anicca/.codex/evidence/core8d-production/final-report.json` mode=`0600` SHA-256=`7919adea615fa9acb055a0b0a681ba9c6fa6708b1a63bdb9a5933d7bd53a5e33`、completion report SHA-256=`ab0ae354a84ece45f28e79aad6a86e2bd204637b63fdee69a854dc7c85f60195`。既知のnudge-cron failureはLife Call外で変更なし | **done** |
| 8d.1 | PANEL-0 | permanent personalized dashboard access + connection controls: bookmark可能なstable `/panel`、chat intentとpanel操作を同じuser-scoped commandへ統一。connection card・権限・organ automation・通知・call/委任を本人が接続/切断/ON/OFFできる | RED: fresh token 403、24h固定session、未認証raw 401/403、dead link、non-clickable card、cross-user leakage、hardcoded connection/context、chat/panel state drift。GREEN: 5分単回tokenはlogin bootstrapだけ、token交換後はstable `/panel` + rotating/refreshing HttpOnly session、明示logout/rebind/revoke/storage消去まで通常利用を維持。tenant isolation/CSRF/single-use/auth/action/session-rotation contract 100%。L3: 実TG login→fresh HTTP 200→token消滅→bookmarkした`/panel`をbrowser再起動後も直接再訪→本人固有dashboard。clock-advanced testで24h超のrotation/refreshとlogout/rebind/revokeを実証。harmless toggleをpanel→chat readback→chat intent→panel readbackの双方向で実証し、isolated第2userの表示/action混入0。supported connectorはtest userで実OAuth開始+callback、未提供connectorは正直なunavailable。mobile/desktopで全action clickable | **done (production L3 + bounded identity waiver)**: PR #334を`dev→main`の通常2-parent mergeで昇格し、merge/origin-main=`b25437f053c51b604e2c0eda36e3a6251a28ab98`。Railway production current deployment=`62493fc4-7603-499f-b01f-594b62396f83`はservice status/listともexact SHAでSUCCESS。`COMPOSIO_GCAL_AUTH_CONFIG`は実測済みNetlify production値からstdout/argv/file非露出のstdin secret-to-secretで設定し、値一致booleanを確認。実TG `/panel` 1回→HTTP 200→query/token消滅→HttpOnly session→同一隔離profileを閉じて再起動後もstable `/panel`へ直接200、本人name/uidRef一致。desktop/mobileはconnection cards=`6/6`、interactive=`8`、clickable=`8/8`。通知はbaseline=true→panel実click=false→API/DB=false→TG intentでtrueへ復元→panel/API/DB=true、receipt 2件ともsucceeded、他tenant preference/receipt=`0/0`。TG replyは§9.11どおりgeneric `Setting updated`で値readbackには数えず、値はauthenticated panel/API/DBで確認。CalendarはDais所有ACTIVE=`1`かつpanel=`connected`、disconnect/provider mutation=0。fresh focused/full/eval/API/UI/tenant=`54/328/33/5/6/9`全PASS、manager fresh focused+tenant=`63/63`、HTTPとpersistent authenticated readbackも再PASS。専用test Telegram/Google identityは存在せず、他人identity・synthetic admin session・無断OAuthを作らないためreal第2identityとfresh OAuth callbackは未実行と明示し、deployed-source tenant isolation 9/9、cross-tenant mutation 0、既存本人connector readbackをproduction-safe代替としてfinal裁定。evidence=`/Users/anicca/.codex/evidence/panel-0-production-l3.md` SHA-256=`dd49a41415210803908236e1bd17752d19d117bcc9dd854dd9bc2735375a0326` mode=`0600` | **done** |
| 8d.2 | PANEL-1 | zero-temporary-link permanent personalized panel: TG/WebApp・通常browserの両入口が常にexact canonical `/panel`を使い、URLにtoken/code/user idを載せず個人sessionへ結ぶ | RED: 現production `/panel` bot responseが`?t=`5分URL、通常browserは新しいtemporary linkを要求。GREEN: TG `web_app` URL exact `/panel` + signed initData POST exchange、通常browserは同じpage内device code→本人TG確認→同URLでsession、旧`?t=`交換0。HMAC/freshness/replay/cross-user/tenant/session/CSRF contract 100%。L3: Dais本人TG `/panel`→button URL exact canonical・query 0→real MTProto WebView/initData→personalized dashboard、browser再起動後もdirect `/panel`。fresh browser device-code pathも同URLで完了。URL/referrer/history/logのauth material 0、他tenant mutation 0 | **done — production L3 success**。accepted base=`47d0f143e`、RED=`52a5d60e6`、GREEN candidate=`60d8bf564`。fresh artifact-only material reviewはexactly 1回・input SHA-256=`2de8fda8140d5ce23d4db2e56b119956742844466682fc74e91280c97fed035a`・`MATERIAL_REVIEW_PASS`。PR #340/#341で初回release後、実Dais Telegram WebViewが`signature`をHMAC data-check-stringから誤除外する401を発見し、genuine RED→最小修正=`c58e7a1f6`→PR #342/#343で再release。final main=`d04c522f08161c69ff83e25335a0630d3940a84c`、Railway production deploy=`ea570232-fd20-4614-b2c8-084cb9d3256c` exact commit/status SUCCESS、health=200。additive migration SHA-256=`8abfc30d96c7c9d25b48ea870c4a6e816ca72cba8ad8fee2837fdb865167392e`を単独適用し、2 tableのRLS、anon/auth grants 0、service-role-only、5 indexes、PK/unique/FK/check、3 SECURITY DEFINER RPCの`search_path=public, pg_temp`をproduction DBで確認。fresh focused=`14/14`、existing panel/session/API/UI/control/tenant=`76/76`、Life Call full `npm test` exit 0、eval=`21/21 + 12/12 + 12/12`、source auth URL/log leak=0、diff check=0。実TGは`KeyboardButtonWebView` 1個、button exact=`https://life-call-production.up.railway.app/panel`、query/fragment 0、real `RequestWebViewRequest`→Daisのexact actor↔tenant 1件、6 sections/error 0、DB name↔DOM identity hash exact、internal UID 0、HttpOnly cookie、direct再訪・browser restart後も同URLで永続。fresh通常browserも同じ`/panel`で8文字code→Dais本人TG `/panel <code>`→同tab自動認証、single confirm/exchange、replay reply invalid・challenge不変・session delta 0。provider/email/call/calendar/wallet mutation=0、raw initData/code/token/cookie/PII保存=0、一時profile/secret/log削除済み。manager独立final checkでもevidence 3件のmode 0600/JSON/hash、origin/main包含、exact deploy、production GET 200、auth query 0、device-code形状、Secure/HttpOnly cookieを再実測。証跡=`/Users/anicca/.codex/evidence/panel-8d2-release-verification.json` SHA-256 `482622a2a6beba7b97a79caffd62c32efeb8dc028a6ea6cf6ae57cf3f2665211`、`panel-8d2-production-l3.json` `476834fa2a69a2e4e69ec777dbf4a706a3cf2757598eaca7f1cb662bd29a5e7c`、`panel-8d2-artifact-review.json` `0dac1169571d8ed0ead9a805573fb221c01be694408e5d9bc885592ad0197908`。PR #343の既存`nudge-cron` Prisma P1000だけはLife Call外の既知設定失敗として変更せず、Life Call staging/API/eval/reviewはgreen | done |
| 8e | CORE-b | DAILY user journey: 実calendar作成→travel autofill→T-10/T-5 call→location判定→必要時email→TG事後報告を1本で通す | 実call録音+whisper、実calendar event、実TG id、実email Message-ID、late不要ケースも実測 | **pending — code/release PASS、production L3は3手法FAILのため次の独立atomic 8fへ**。RED=`2dd363bb7`、GREEN=`6d48ab1b3`、TG failure isolation RED/GREEN=`40b1bec93`/`e3551873f`。focused/full/eval=`89/407/33` PASS、fresh review blocker 0。PR #335/#337/#336を通常mergeし、origin/main=`85a68abaa22df0d9bd0d7fe2fcf7fee0ae796eaf`、Railway production deployment=`450d523a-2c21-4632-826d-396a919b05c3` exact SHA SUCCESS。L3 method 1は実nonce eventを1件作成したが、`plus aliasはCalendarでもexternal attendeeのまま`がfalseでprovider readback=`self=true, organizer=true, external=0`としてfail closed。call/email/TG/travel/late=0のままT-10窓231秒前にexact cleanupし、nonce event=`1→0`、nonce Travel=`0`、unrelated calendar/tenant不変。cleanup evidence=`/Users/anicca/.codex/evidence/core-8e-orphan-cleanup.md` mode=`0600` SHA-256=`ea5f87244cb35b8cb85e44db36ac3c85eda9d420f1f41e43df4aeb6c547c1fa1`。method 2はprovider mutation前に停止しside effect 0。false hypotheses=`宛先を通常CLIで扱ってもargv/logへPIIを残さない`、`late対象はnonce eventへ自動で束縛される`、`verified forwarding destination宛の実メールはprimary inboxで読める`、`nonce由来Travelは常にoutbound 1件だけ`。method 2bはread-only探索でaccepted targetが唯一のlocal Gmail auth/send-as/Calendar ownerとdistinctだが、target mailboxのOAuth/IMAP/browser authもtarget→primary reverse-forwarding証拠も0と確定し、provider mutation前にfail closed。false hypothesis=`accepted verified-forwardingなら実受信RFC Message-IDまでlocal readbackできる`。Stop規律に従い8fを進め、8e再開条件はtarget mailboxの実readback authまたは既存の外部controlled inbox経路 | pending |
| 8f | CORE-c | context/onboarding/discovery: 初回user、既存user、location未解錠/解錠後、同じclosed Qを二度聞かないことを再検証 | eval 100% + 実TG callback + DB/context provenance。質問禁止領域の発話0件 | **pending — code/schema/release PASS、production L3は3手法FAILのため次の独立atomic 8gへ**。accepted base=`85a68abaa`、journey RED=`90933cbb9`、corrective endpoint/UI RED=`0fc453527`、GREEN=`771f996c9`。fixed context eval=`12/12 (100%)`、focused=`39/39`、Life Call full=`417/417` + scheduler PASS、calendar/late/context eval=`21/21 + 12/12 + 12/12`。PR #338/#339をmergeし、feature=`771f996c953c15374ca5b387ef6c18d38902775c`はcurrent origin/main=`d04c522f08161c69ff83e25335a0630d3940a84c`に包含、current Railway production deployment=`ea570232-fd20-4614-b2c8-084cb9d3256c` exact SHA SUCCESS、health=200。additive migrationはask追加column=`7/7`、location source、nonce table/3 indexes、RLS、forbidden grants=`0`、service DMLをpostflight。実Dais TG L3 method 1はclosed Q→callback後に`typed_message_binding_mismatch`、false hypothesis=`MTProto user-view message IDはBot API webhook message_idと一致する`。method 2は同じ質問を再利用し、callback/replay/cross-tenant/dedup/locked discoveryまで通過したがhigh-level Telethon live locationが`live_location_unlock / poll_timeout`、false hypothesis=`Telethon high-level live-location sendは現Bot API webhook location形として到達・処理される`。method 3はraw `messages.SendMediaRequest(InputMediaGeoLive)`へ独立変更し、新規質問0、callback 2、discovery 1、live location 1、他chat/broadcast 0。closed Q/callback、replay追加transition 0、cross-tenant mutation 0、same-series duplicate 0、locked discovery 1、forbidden question 0はPASSしたがtyped `source=telegram_live_location`永続化が同じく`live_location_unlock / poll_timeout`、unlocked discoveryはhard-stopで未到達。false hypothesis=`raw MTProto InputMediaGeoLiveはtyped Bot API live-location updateとして到達・処理される`。3手法ともexact restoration=true。最終controlled ask=`0`、controlled state/component hashとunrelated counts (`lm_users=2/lm_ask_log=0/lm_user_locations=0`) はbefore/after一致。第4手法は禁止。failure evidence=`/Users/anicca/.codex/evidence/core-8f-production-l3-method3-failure.json`、mode=`0600`、SHA-256=`0008efde8c3ce508d8b28d5e7e33b6a0a99106a6db8b296cd1d2f55783a700b6`。再開条件はBot API webhookへMTProto live locationが渡らない境界の独立原因または別の既存real location input経路 | pending |
| 8g | PANEL-a | score semantic fix: §9.9の outcome-based DAILY/PHYSICAL/MENTAL/FINANCIAL 定義へ統一し、根拠を表示 | fixed dataset eval 100% + prod実データで numerator/denominator/reason が一致。対象0件は insufficient data | **done (production L3)**: feature=`bc444136aef9df457f2db948dc884d3abb37ecff`はproduction release=`8159dbbe2fbb07d235cd4fb91e964b481c543ea2`に包含、Railway deployment=`a659eb3c-c652-4ab3-81ef-411890d71e22` exact SHA/image SUCCESS。未適用だったmigration=`2026-07-22-panel-score-outcomes.sql`（SHA-256=`eb917c3d2d7931b0888db4ba1b9a19dcfb2bc6f506afe7fb4321f41950e4b5e1`）を対象Supabaseへtransactional適用し、table/RPC 200、RLS、policy=2、append-only trigger、service SELECT/INSERT + RPCのみ、UPDATE/DELETEなし、anon/auth SELECTなしを独立readback。Dais本人のcanonical `/panel`を実Telegram device confirmationで認証しquery=0、production ledgerは4 organ全て0件のためAPI・本人sessionへ束縛したDB snapshot・独立oracle・desktop/mobile UIが全て `insufficient_data` / `0/0` / reason / period / components / 根拠0件でexact一致。focused=`14/14`、fixed eval=`27/27 (100%)`、fresh artifact review=`PASS / Critical 0 / Important 0`。private evidence=`/Users/anicca/.codex/evidence/panel-8g-production-l3.json` mode=`0600` SHA-256=`e2844e6d2f1504c5238e56a040fe5f60b30685769e70a4b96f5de25289a33a0f`、desktop/mobile/mobile-score screenshotsもmode 0600。calendar/email/call/wallet mutation=0、synthetic admin session=0 | done |
| 8h | PANEL-b | panel UX/privacy fix: timelineの生ログ・raw JSON・内部名を除去し、mobile/desktopの5要素を人間語で成立させる | authenticated browserで全画面操作、semantic assertion、mobile+desktop screenshot、raw log/secret/internal prompt検索0件。Fable final check PASS | **done (production L3)**: historical VCSDD matrixを採用せず、Superpowers/TDDで実際の3欠陥（secret recipe、API/browser validator parity、raw score component label）へ限定。API privacy=`177/177`、emitted browser=`63/63`、secret recipe=`19`×channel=`9`、Task 2 regression=`47/47`、Task 3=`27/27`、brand focused=`77/77`、deterministic eval PASS。fresh artifact reviewは実装・brandingとも`PASS / Critical 0 / Important 0`。PR #352/#353をmergeし、production release=`4836ca90ddd4999fc952718023cf92583220ca2c`、Railway deployment=`b3fd36f5-2f8e-4b54-b714-d387e7eb194c`、instance=`5e8e5349-0b78-4a5d-8701-a29a7a6bd1a3`、image=`sha256:f9b4e10943ea593811300a6c2c4b231ec2c93bc60d760a55838b6e869714f206`をexact commitで`SUCCESS/RUNNING`実測。Dais本人authenticated canonical `/panel`でtimeline/scores/ledger/gates/settings/control-center=`6/6 loaded`、各API=`6/6 HTTP 200`、forbidden echo=0、title/h1/wordmarkと未認証loginはLife Managerのみでvisible Anicca=0。desktop 1440px・mobile 375pxは横overflow 0。screenshots SHA-256=`45bc178c0fa702efd57def0f2216beac4fe6b72ca43131713a45bd7afa698bb9` / `78a4a1247fef16b7080a255a760d5a98a237284e0ffe5996f84323c2db348bd9`。private evidence=`/Users/anicca/.codex/evidence/panel-8h-production-l3.json` mode=`0600` SHA-256=`a55877a35fb8e502eddfed3b4178910632174a9a5db53639b65d119b68e10b7d`。次の独立atomicは8i REPO-CONSOLIDATE | done |
| 8i | REPO-CONSOLIDATE | current operating repo `Daisuke134/anicca-products`から、whole productをcanonical public repo `Daisuke134/life-manager`へ吸収する。`apps/life-call→apps/life-manager`、必要なengine/skills、SSOT docs、deployment configだけを移し、旧iOS・他product・private runtime state・secret・生成物を持ち込まない。以後のproduct/AI/agent/runtime/API/marketing identityと新規commit/push先をLife Managerへ一本化する | source/target manifestとhistory provenance、移行対象のbyte/semantic equivalence、secret/PII/generated artifact 0、canonical repo上でfocused/full/eval 100%、build、fresh review、`/health`・TG・canonical `/panel`のproduction L3、Railway exact target commitを実測する。cutover成功までは`anicca-products`を変更・archiveせず、成功後だけarchive + README redirectにする。repository ID `1248111245`と既存historyを保持し、新repo作成・force-push・history rewrite・product downtime 0。canonical repoに本specが存在し、以後の`9b`以降が同repoだけで実行可能になればdone | **done (2026-07-24 実測)**: repo側=PR #1071/#1072でbyte等価migration(183 files sha256 manifest、fresh review APPROVE 0 blocker)、merge=main `a7ac84d4`。cutover=Railway service再接続(root `apps/life-manager`)、active deployment `6806b0d4-dcdf-430f-acea-35d8a5b11212` commit readback=`a7ac84d4`完全一致、/health 200 build=lm27-voicemail-v1、zero-downtime monitor 358/358、実TG message id 217、authenticated /panel 5 section+control-center全200。archive gate=README redirect banner(93cc012)→`anicca-products` archived=true(GitHub API独立読み戻しで確認済み)。証跡=docs/evidence/8i-cutover-report.md(PR #1077)。spec本体はcanonical repoに存在し9b以降は本repoのみで実行可能 |
| 9a | MKT-a | video 生成 PoC 1本: §9.10 matrix の1行 → MPT backend（faceless-money-factory 代替レンダラー、§10.1 U6）で mp4 | **done (L3 実測)**: T-10/T-5 行を英語 34.666667s・1080×1920 H.264/AAC に変換。実 call 録音 + 実 Telegram Web message #3393 + 既存 real stock を FFmpeg 1-pass で合成。音声 track / 9:16 / 20-40s / full decode exit 0。render 42s、追加 cost $0。local=`.claude/sol-orders/out/m1/anicca-life-manager-t10-demo.mp4`、SHA-256=`c4bd480ed37db2a3f5d59223756805307f2c7c5c603244a0c13370e6353479f4`。未投稿。**Fable final check 済み（03:15）**: sha256 一致 + ffprobe 1080×1920/h264+aac/34.7s + フレーム3枚実視認（実写手元+「REAL T-10 CALL・TOKYO」+ whisper 字幕「TOKYO AT 9:30. TIME TO LEAVE NOW.」）。X/Slack launch 用に Dais 納品 | **done** |
| 9b | MKT-b / M-2 | runtime+生成 loop常設: **既存 Life Manager marketing loop / `ai.anicca.life-manager-daily` / rotation / account を再利用し、別loopや新accountを作らない**。slideshow rendererだけをLife Manager向けMPT video rendererへ置換。current Claude Sonnet/CLIProxy false-greenを廃止し、fresh `gpt-5.6-luna` pass、実exit、timeout、cost、16行rotation、video生成をlaunchdへ配線 | Luna probe/real pass、failure injectionがnonzero、launchctl run増分、fresh ffprobe/full decode、2日連続自動生成。1日目は `started` と記録して次へ進む | **done (L3 実測)**: accepted base=`4209a66c`、code head=`cd95bf1e`。missing generator/runtime RED後、generator=`5/5`、runtime/launchd=`6/6` GREEN、Life Manager full test fail 0、calendar/late/context/score/intent/mental/physical eval 100%。method 1でLunaがwrapperを再帰起動する反例を発見しprovider/public side effect前に停止、corrective `LM_DAILY_ACTIVE` exit 73をRED→GREEN。method 2はgeneration+distribution混在promptがactive route監視へ逸脱したためside effect前に停止。method 3は9c配信を`LM_DAILY_GENERATION_ONLY=1`で閉じ、exact bank/state/outputだけを検証するbounded passへ分離して成功。fresh Luna probe=`LM_LUNA_PROVIDER_OK` exit 0、launchd同一label/cadenceでrun count `0→1`、corrective readback `1→2`、last exit 0。summary=`marketing-agent / luna-medium-decision / codex / gpt-5.6-luna / medium / attempt 1 / success`。production append-only rotationは3日連続 `A01→A02→A03`、3本とも1080×1920 H.264/AAC、34.666667s、fresh full decode 0、SHA-256=`a990f79b…/01e6c9a7…/d9e97b38…`。usage ledgerはprovider-reported total 45,569 tokens、subscription actual marginal cost USD 0、provider-equivalent priceはunavailable/nullとして非捏造。failure injectionはgenerator 17、runner 23、timeout 124をexact nonzero伝播。gitleaks対象path leak 0。evidence=`docs/evidence/9b-marketing-video-runtime.md`。9cまでpublic distributionはlocked、public/provider mutation 0 | **done** |
| 9c | MKT-c / M-3 | 配信配線: **既存 Life Manager IG/TikTok accountを再利用**し、IG file/script経路 + TikTok Postiz `cmp9txjdp01c8oh0yb6dhlarr`へ同じexact video/caption contractを流す | IG/TT 実投稿 URL 各1本 + logged-out readback + ledger creative id一致 | **done (L3 実測)**: accepted base=`a342ca5c`。missing distribution module RED→同一video/caption pathを両adapterへ渡し、creative id + video/caption SHA-256をplatform別append-only ledgerへ束縛するGREEN。既存shared `poster.py`のcredential key互換をRED→GREENし、新IG client/accountは作成せず`anicca.affirms2`を再利用。Postiz `cmp9txjdp01c8oh0yb6dhlarr`はAPI readback `disabled=false/profile=anicca_buddha`。A03 video SHA=`d9e97b38…`、caption SHA=`0f34758f…`。実IG=`https://www.instagram.com/reel/DbKkdfjsaTZ/`、logged-out checker `found=true/verdictMaterial=pass`。実TT初回Postiz `PUBLISHED`がprofile URLだけを返す反例をfail-closeし、`/video/<id>`必須 + recent caption match resolverをcorrective RED→GREEN、実TT=`https://www.tiktok.com/@anicca_buddha/video/7665973874504256785`、Postiz post id=`cmryjod3q0193pe0yastxx34h`。logged-out yt-dlpでexact caption/id/duration 34秒、public transcode H.264/AAC 720×1280/34.668005秒/full decode 0。targeted=`8+6+3+7`全PASS。launchd method 1のLuna自己監視deadlockを停止してcorrective RED→GREEN後、run count `1→2`、last exit 0、distribution ledger `3→3`で再投稿0、`codex/gpt-5.6-luna/medium/attempt1/success`、実TG message id `3378`。evidence=`docs/evidence/9c-marketing-distribution.md` | **done** |
| 9d | MKT-d / M-4 | 全marketing共通の search+metrics self-improve: BP検索、views/watch-time/completion/click/signup取得、winner/loser記帳、次video変更 | 初日URL+launchd常設で `started`。日次loopが7日分のIG/TT URL、metric、翌日変更理由を自動記帳し7日目にdone判定 | **pending — started (real Day 1/7)**: 9cの同一creative/video/caption hash pairをproviderから再読込し、IG Reel=`DbKkdfjsaTZ` views/likes/comments=`17/0/0`、TT video=`7665973874504256785`=`9/0/0`。watch-time/completion/click/signupはprovider取得不能を`null`で明記し推測0。append-only ledgerは同日再実行`1→1`、gap/backfill拒否、連続real dateだけで7日目doneをcontract化。dailyへdistribution後・agent前に配線。field名不一致をcontrolled runでfail-close後corrective RED→GREEN、最終launchd exit=0、distribution=`3→3`、self-improve=`1→1`、Luna attempt1、実TG message id=`3379`。core/runtime=`5/5 + 8/8`。残り6 distinct real days。evidence=`docs/evidence/9d-marketing-self-improve-started.md` |
| 9e | MKT-e | TikTokをPostizから自前file/script経路へ移行し定常コスト$0化。先に同等性を証明し、証明前にPostizを外さない | 自前scriptの実TT URL + 2日連続成功 + logged-out readback + Postiz非使用のcost ledger | **pending — equivalence PASS / auth gate**: 自前`tiktok_direct.mjs`は既存CloakBrowser CDPへ接続しexact MP4/captionを受け、Postiz terminal `state/post_url/post_id`と等価。個別`/video/<id>`、yt-dlp logged-out exact id/caption、route=`direct_browser`、cost=`0`、real dateをclosed ledgerへ要求。連続実2日だけdone、duplicate/gap/simulation/cost>0/readbackなしは不算。Python/Node=`10/10 + 8/8`。既定はPostizのままで、exact env gateのみdirectへ切替。実preflightはtarget credentialでTikTok email verificationまで到達するが、masked mailboxはgog/Gmail 0・Keychain/env credential 0・domain mail endpoint auth不可の3経路FAIL。code推測/bypass/upload/post=0、Postiz ledger=3不変。evidence=`docs/evidence/9e-tiktok-direct-migration-started.md` |
| 9f | MKT-f | Phase 1 core + marketing完了後のone-time launch: M-1 demo videoを使いXへ1投稿 | Dais本人が投稿した実X URL。agentによるDais個人account代行は禁止。これは定常loopではない | **pending — prerequisite blocked**: canonical §10からPhase 1必須row=`8e,8f,9b,9c,9d,9e`をclosed判定し、live blockers=`8e,8f,9d,9e`。結果は`owner_handoff_allowed=false`かつ`agent_posting_allowed=false`、X credential/session/draft/upload/post/handoff=0。全前提done後もowner handoffだけを許しagent投稿は常時false。owner実URL ledgerが1件あれば`already_done`で再handoffも拒否。contract=`5/5`。evidence=`docs/evidence/9f-x-owner-launch-blocked.md` |
| 10a | DEV-a | feedback intake: TG メッセージ→「feedback」判定→PII scrub（user 側で除去、§9.3 不変条件） | 実 TG feedback 1件が PII ゼロの要約になる実測 | **done (real L3)**: user-facing webhook edgeで明示`feedback:`/`フィードバック:`だけを判定し、email/phone/postal/URL+query/handle/explicit name/secret shapeをpersist前に置換。DB closed schemaは`summary/labels/HMAC source_ref`のみをinputとし、raw text/chat/user/actor/email/phone column=0、parameterized insert + source_ref unique `ON CONFLICT DO NOTHING`。実Dais TG message id=`3922`→非echo bot ack id=`3923`→Railway Postgres row id=`1`, status=`queued`, labels=`feedback,calendar,panel`、PII 0。controlled staging deployment=`ac0f6b9a-2a15-4762-88fc-52b7fe92caa4` SUCCESS/health 200。webhookはproduction URL/pending0/error nullへ復元、一時staging secrets削除。focused=`8/8`、full fail0、eval全100%、changed-path secret/PII=0。evidence=`docs/evidence/10a-telegram-feedback-intake.md` |
| 10b | DEV-b | issue 自動生成 + dev loop 接続（既存 launchd D0 が食う形） | scrub 済み issue が gh に実生成 | **done (real L3)**: production `lm_feedback_intake` row `1`を単一statementの`FOR UPDATE SKIP LOCKED`でclaimし、決定的hidden markerによるcrash recovery付きでGitHub [issue #1085](https://github.com/Daisuke134/life-manager/issues/1085)を実生成。readbackはOPEN、label=`lm:type:self-heal`、marker/acceptanceあり。DBはstatus=`issued` + exact issue URL、2回目worker=`no-op`、marker一致issue=`1`。既存D0 `pick-issue.sh`が#1085を選択し、新picker/loopは0。既存`ai.anicca.life-manager-dev` 04:10 jobはcanonical wrapperでissue生成後に既存D0へdelegate。focused=`7/7`、full fail0、eval全100%、changed-path secret/PII=0。evidence=`docs/evidence/10b-feedback-to-github-issue.md` |
| 10c | DEV-c | E2E: 実 feedback 1件 → issue → dev loop auto-PR → merge | merge された実 PR URL | **done (real E2E)**: 実TG `3922`→production DB row `1`→issue [#1085](https://github.com/Daisuke134/life-manager/issues/1085)→既存launchd D0→実PR [#1087](https://github.com/Daisuke134/life-manager/pull/1087)を一鎖で通した。D0をcanonical `life-manager/main/apps/life-manager`へ是正し、fresh agentが回帰test先行でmissing-calendar labelをexact `Connect Calendar`へ修正、commit=`9c93bf36…`。method 1のmissing `--loop` agent exit2 false-greenを未mergeで停止し、corrective RED→GREEN `3/3`、method 2はagent exit0、focused panel=`51/51 + FIND-008`、D0 full fail0/eval全100%。launchd run `1→2`/last exit0、state=`pr_open`、実TG report id=`3386`。D0自身はmerge/deployせず、同PRの通常mergeをfinal containmentで確認。evidence=`docs/evidence/10c-feedback-dev-loop-auto-pr.md` |
| 10d | DEV-d | production error intake: provider timeout、failed call/email/post、5xx、eval regressionをPII scrubしてdedupe issue化 | 実failure injection 3種→重複なしissue 3件、raw PII/secret 0件 | **done (real L3)**: allowlist済みsignal/component/fingerprintだけからclosed schema `source_ref/summary/labels`を構築し、raw provider errorを出力・hash・DBへ一切伝播させない。実timer timeout、実child side-effect exit23、local HTTP 503 + 実eval exit1を観測後、production DB row `2/3/4`を作成。再実行は全件`duplicate=true`で新規row 0。既存workerが実issue [#1088](https://github.com/Daisuke134/life-manager/issues/1088)/[#1089](https://github.com/Daisuke134/life-manager/issues/1089)/[#1090](https://github.com/Daisuke134/life-manager/issues/1090)を各1件生成し、4回目は`no-op`。DB/GitHub exact marker readback一致、raw PII/secret scan 0。6 signal→3 class contract、5xx/eval同根dedupe、focused=`22/22`。evidence=`docs/evidence/10d-production-error-intake.md` |
| 10e | DEV-e | guard内auto-merge/deploy: test/eval 100%、fresh adversary、path allowlist、blockedActions、rollback、1 issue/1 PR | 実error由来PR 1本を人手なしでmerge/deployし、再現test GREEN + prod回復。guard外変更はmerge拒否を実測 | **pending — 3 fresh-adversary methods failed before merge**: production error [#1088](https://github.com/Daisuke134/life-manager/issues/1088)→既存D0→実PR [#1092](https://github.com/Daisuke134/life-manager/pull/1092)、Composio hang回帰+15秒abort、実guard外`.github` pathはexit3で拒否、focused=`18/18`、full/eval/privacyは各method GREEN。method 1 blocker=旧deployment誤受理/merge TOCTOU/review head未束縛/regex迂回、method 2=review前credential付きcandidate実行/bootstrap無検査、method 3=reviewer runner自体のcredential/filesystem/network非隔離・PR list 100件上限・rollback targetとlive commit未束縛。3手法ともPR/issueはOPEN、merge/deploy/provider mutation=0、productionは既存deployment `73afe498…` SUCCESSのまま。再開条件=credentialなしread-only reviewer sandbox、全PR pagination、active deployment exact commit readbackをcandidate外のtrusted promoterへ実装。evidence=`docs/evidence/10e-auto-merge-deploy.md` |
| 10f | DEV-f | daily self-build運用: errors+feedbackを毎日処理し、Fable/Daisを定常loopから外す | launchd/gateway cron常設 + 7日台帳（各日issue/PR/no-op理由）+ stale/timeout自己回復。sessionは7日待たずloopへ判定委譲 | pending |
| 10g | BRAIN-a | intent-aware context graph: explicit goal、repeated preference、family/dependent、delegation、prohibition、correctionをprovenance/confidence/expiry付きで保持 | schema/contract test + Dais型/母型/予定を好まない型のfixture。訂正で古い推定が失効 | **done (2026-07-24 L2実測)**: `apps/life-manager/lib/intent-graph.js` 閉schema(6 kind/provenance source enum/閉key)+ confidence tier 明示0.9>繰り返し0.6>推定0.3。`applyCorrection`がsupersedes対象をcorrectedへ失効(削除せずprovenance監査可)、`effectiveEntries`はexpired/corrected除外のpure read。contract test `lib/intent-graph.test.js` 7/7、fixture `test/fixtures/intent-graph/{dais,mother,non-event}.json`(非event型はinferred推定がcorrectionで失効済みの形を実証)。full suite fail 0でmain test chainに常設 |
| 10h | BRAIN-b | proactive opportunity engine: definite goodとpersonal goodを分け、body/mind/finance/life-admin候補をbenefit/urgency/confidence/reversibility/cost/riskで裁定 | `intent-cases.jsonl` 15+ cases eval 100%。hoikuen、tech event、友人時間、休養、何もしない正解を含む | **done (2026-07-24 L2実測)**: `lib/opportunity-engine.js` 決定cascade — 明示prohibition優先skip → active支持intent 0でskip(何もしないが正解) → risk/cost gate → material preferenceのみclosed-Q 1問(再質問しない) → inferred単独は観察継続 → 委任内+reversible+低riskで無確認act、それ以外ask。`eval/intent-cases.jsonl` 18 cases 100%(hoikuen調査act/契約ask/再質問skip、tech event act/高額skip、友人時間ask/推定のみskip、休養act、prohibition skip、訂正済み・期限切れ支持skip等)。contract test 4/4、eval chain常設、full suite fail 0 |
| 10i | BRAIN-c | personalized action E2E: 現userのreal contextから1件を選び、web/emailのみで実行し、calendar/TGへ事後報告。不可なら正直報告 | 実候補根拠 + 実web/email side-effectまたは正直な実TG + gcal event。不要なapproval Q 0件 | pending |
| 11a | PHY-a | 未通院・未ケア検知 rule: calendar/context/本人intent履歴から歯科・散髪等を検知。固定周期を全員へ押し付けず、medical diagnosisはしない。eval `phy-cases.jsonl` 10+ cases | eval 100% + 実 calendar/context で検知1件 | **pending — L2 done (2026-07-24実測)**: `lib/care-detector.js` 本人履歴のmedian間隔だけをcadenceとし(履歴0-1件は絶対にflagしない=固定周期押し付け不可をcontract testで証明)、1.5x超過で`personal-cadence-overdue`、明示goal未達30日超で`explicit-goal-unmet`。prohibition(care:tag)で抑制、閉output schemaにdiagnosisの置き場なし。`eval/phy-cases.jsonl` 12 cases 100%(境界1.5xちょうど=非flag/151日=flag、同経過日数でもcadence次第で結果が変わる等)。contract 4/4、chain常設、full suite fail 0。**L3残**: 実calendar/contextでの検知1件(本番データ必要) |
| 11b | PHY-b | 候補選定: 生活圏（home/work）+ 履歴の「いつもの店」優先。web 予約可否の判定込み | 実データで候補3件 + 予約経路の判定実測 | pending |
| 11c | PHY-c | 予約実行: VPS/cloud常駐browserのwebフォーム or メール（§9.5 電話禁止）。local Mac/browserを定常runtimeにしない。不可なら候補提示 + 正直報告。名乗り = "Life Manager (AI secretary, acting for <user>)"（§10.1 U8） | cloud/VPS browserまたはemail経由の実予約1件 + provider readback、または正直報告の実TG。CAPTCHA/OAuth/3DSは本人handoff後に同じcloud jobが再開し、local session継続依存0 | pending |
| 11d | PHY-d | 事後報告 + calendar 登録 + 当日 call 連動（§9.11 PHYSICAL copy） | §9.11 copy での実 TG + gcal 実 event | pending |
| 12a | MEN-a | trigger 判定 engine: schedule+location+直前 event から「効く瞬間」を判定。固定時刻禁止・3通/日上限。eval `men-cases.jsonl` 10+ cases | eval 100%（上限・抑制ケース含む） | **done (2026-07-24 L2実測)**: `lib/mental-trigger.js` 決定cascade — 3通/日cap → 2h最小間隔 → mid-event抑制 → 移動中抑制 → 重要予定10-45分前=pre_event → 激務終了30分以内+次予定60分以上先=between_events → 就寝目標60-15分前+残予定0=pre_sleep → それ以外抑制。固定時刻は構造的に不可能(空scheduleは全24時間suppressをcontract testで証明)。`eval/men-cases.jsonl` 15 cases 100%(cap・間隔・mid-event・移動・通常予定は送らない・同時刻でもschedule次第で結果が変わる等の抑制ケース込み)。contract 4/4、test+eval chain常設、full suite fail 0 |
| 12b | MEN-b | 文面生成: aniccaios affirmation 資産を種に LLM が状況別生成（§9.11 MENTAL 例文の型） | 生成文が §9.11 原則（一方向・絵文字1個まで）を満たす sample 10本 | pending |
| 12c | MEN-c | 送信配線 + E2E: 実 schedule 由来 trigger 3種（予定前/合間/就寝前）で実 TG 着信 | 実 TG 3通のスクショ/メッセージ id | pending |
| 13a | FIN-a | agent wallet 自己生成（§10.1 U7 Franklin 型。既存 wallet 流用禁止）+ 秘密鍵の安全保存 | 新 address 実在 + 残高 0 確認 + 鍵が repo/log に無い grep | pending |
| 13b | FIN-b | 送金先 closed Q（§9.11 FINANCIAL copy、初回1問のみ）+ 永続保存 | 実 TG で登録往復1回 + DB 実 row | pending |
| 13c | FIN-c | engine 配線: earn loop の収益を wallet に記帳し月次集計（§9.8 crypto rail。損失月も正直報告） | 台帳に実収支行 + 月次報告文の生成実測 | pending |
| 13d | FIN-d | 実送金 E2E: agent wallet → user wallet、spend-cap 内、tx 報告（§9.11 copy） | on-chain 実 tx hash + 実 TG 報告 | pending |

- **今後の実装方式 = Superpowers**: Fable/main sessionはvision整理・spec・plan・read-only調査/裁定・final check、fresh workerはisolated worktreeでTDD build・execute・verify・spec実測更新・対象限定commit/pushを行う。reviewは`requesting-code-review`、完了主張は`verification-before-completion`、branch終端は`finishing-a-development-branch`に従う。既存VCSDD記録はhistorical evidenceとしてのみ読む。
- search、artifact-only review、複数surfaceの独立調査はsubagentへ分離してよい。builderはfresh Sol instanceにし、Fableのcontextを実装ログで圧迫しない。
- **実行phase = ①CORE 8d-h → ②ONE-REPO 8i → ③MARKETING 9b-e → ④one-time X launch 9f → ⑤DEV 10a-f → ⑥BRAIN 10g-i → ⑦BODY 11a-d → ⑧MIND 12a-c → ⑨FINANCE 13a-d**。現在の実行cursorは② `8i`。前phaseのL3が無い状態で次phaseをprodへmergeしない。`8e`/`8f`は明示resume条件待ちのためbuildを止めないが、両L3をcloseするまでPhase 1全体をdoneにしない。
- **cloud browser不変条件**: `10i`、`11b`、`11c`などのweb調査・予約・外部操作はVPS/cloud browser jobで実行し、local Mac/browserを定常schedulerや永続sessionの前提にしない。localは開発・一時debugだけ。CAPTCHA/OAuth/3DSは本人handoffを明示し、完了後は同じcloud jobがprovider readbackから再開する。MENTALは予約を作らず、cloud gatewayのschedule/location triggerからTGを送る。
- 初期buildのFable final checkが終わった後、marketing/dev/organ定常loopにFable/Daisを入れない。loop自身が日次実行・self-heal・self-improve・報告を行う。
- **★NO-STALL 規約★**: 前回の停滞真因 = E2E が「Dais が call に出る」依存で、そこで全体を止めて Dais を呼び続けた。是正3行:
  1. **Dais 依存は1窓に束ねる**: Dais にやってもらうのは「①T-5 call に1回出る(約1分) ②その後10分放置 ③（必要なら）Gmail scope の OAuth 1クリック」だけ。事前に TG で時刻を1回通知し、その窓以外で Dais を呼ばない。
  2. **gate の意味を限定**: 前phase green が block するのは次phaseの **merge/prod 反映**。spec・eval RED・isolated worktree内の準備は並行してよい。
  3. **待ち時間の既定動作 = 次の独立atomicのspec/eval準備**。「待ってます」報告で停止しない。Dais への連絡は (a)1回の必要窓 (b)全完了報告 (c)真の停止点のみ。

### 10.0 出荷ラン実況（live状態。詳細は各§10行）

- **CORE 8e/8fは各3手法FAIL後の明示resume条件待ち、PANEL 8g/8hはdone、次は8i REPO-CONSOLIDATE**: 8eはcontrolled inbox readback auth、8fはreal location input境界の独立原因が見つかるまで第4手法を禁止。8g/8hのproduction L3は各正本行を参照。repo実測でcanonical `life-manager`にwhole product/SSOTが未移行と判明したため、次の独立atomicは8i。
- **PANEL 8gはproduction L3までdone**: 後続release `8159dbbe2`でRailway build/image/instance停止条件が解消済みであることを再測定し、追加deployなしでexact deployed sourceを使用。migrationをtransactional適用後、security/readback、Dais本人authenticated `/panel`、API=DB=独立oracle、desktop/mobile、eval 100%、fresh reviewを全てPASS。
- **PANEL 8hはproduction L3までdone**: 詳細・証跡・release/deployment・検証数は§10行8hを参照。次はcanonical repoへwhole productを移す8iであり、9bはその後。

- **CORE 8dは3手法連続FAILで差分保全・次の独立atomicへ**: base=`09dbd5ef5`。①first GREENはharnessの`Date.now()+1`推測がproduction send-boundary欠陥を隠して停止（false hypothesis=`expanded全GREENならharnessもproduction境界を忠実に実行している`）。②rescue method 1はacceptance後境界を直したが、pre-acceptance固定時刻fixtureとの契約矛盾でcoverage=`149 total / 148 pass / 1 fail`（false hypothesis=`immutable six-attempt fixtureの固定nowはacceptance後境界と両立する`）。③method 2はfixture-only commit=`c01057a0b`をpushし、clean RED baseで`142 total / 136 pass / 6 fail`不変、dirty GREENでexpanded=`142/142`、old/focused/full/eval/deadline=`75/52/372/33/6`、coverage tests=`149/149`まで到達したが、collectors lines=`88.54%`を2文1行化で数値だけ上げようとしたためmanagerがcommit前に停止（false hypothesis=`semantic不変の行圧縮をcoverage改善として受理できる`）。未commit 8-path差分は保全し、8dのPhase 2c/provider/L3/final-report/deploy/mergeは禁止のまま。Stop規律に従い次の独立行8d.1 PANEL-0へ進む。
- **PANEL 8d.1 product corrective buildへ**: process repair=`ef2673ab`をpushし、orchestrator独立実測でHEAD=upstream、state/runtime PASS、schema=`12/12`、state=`2a`、sprint=`2`、gate3=`FAIL`、open finding=`10`。metadata修復は3 key rename + 8 categoryのみで本文不変。global indexの表示は旧`2b`だがfeature stateを実行正本とし、これ以上process分類へ時間を使わない。次は10 blocker各1件以上のgenuine RED→product実装→local GREEN→fresh artifact-only review。RED/implementationを分離commitし、provider disconnect、実OAuth、Dais account mutation、deploy、merge、L3は禁止。
- **PANEL 8d.1 corrective-1はfresh product review FAIL / blocker 6**: RED=`5f8db7f13`、GREEN=`1c74ff0f7`、evidence=`c3fbf22eb`をpushし、focused/full/eval/smokeはGREEN。ただしfresh artifact-only reviewはprocess nitを除外しても、恒久session、production runtime toggle、rebind後page/OAuth、same-account provider readback/rollback、personalized settings/control、oversize後socket errorの6件を実再現した。fixture GREENを出荷証拠に昇格しない。provider/OAuth/send/deploy/L3は0のまま。次は6件だけをproduction-path RED→GREENへ戻し、変更module coverageは意味のあるbranch testで満たす。scheduler全体の数値だけを上げる行圧縮は禁止。
- **PANEL 8d.1 corrective-2 method 1はfalse REDで停止**: fresh Solは15/15 failを作ったが、runtime selector/provider/personalization/oversizeの大半が関数やHTTPを実行しないsource regex検査だった。managerがcommit前に停止し、untracked testだけを保全。false hypothesis=`source shape assertionはproduction-path behavior REDを代替できる`。fresh rescueはstatic assertionをSQL grant/markup補助に限定し、HTTP route、RPC state machine、production selector、provider mutation/readback、stream late-errorを実行してからRED commitする。
- **PANEL 8d.1 corrective-2 method 2は発注path不備で変更0**: rescue SolはHEAD/upstream/PR headと唯一のdirty test hashを一致確認したが、feature worktree相対の`.claude/sol-orders/order-panel-permanent-session.md`が存在せず停止。false hypothesis=`別worktreeからもrelative order pathで正本を読める`。絶対pathへ是正し、同じdirty hashからmethod 3をfresh発注する。
- **PANEL 8d.1 corrective-2 method 3はGREEN後fresh product review FAIL / blocker 4**: behavior RED=`0f0675a7b`、fixture correction RED=`5bfd87d59`、GREEN/evidence=`3e23328d9`をpush。manager独立実測もbehavior=`17/17`、focused=`39/39`、full/eval/smoke GREEN。ただしfresh reviewerが実click、異なるchildを使う並列rotation、clock advance、malformed preferences JSONを実行し、選択不能な固定値settings UI、並列APIでのrotation cookie競合、active sessionの30日/180日強制失効、batch scheduler fail-openを再現。false hypotheses=`data-action marker + handcrafted API testは実click選択性を証明する`、`同じ固定childを使う並列testは実rotation競合を証明する`、`期限列の存在はactive session refreshを証明する`、`200 responseはJSON parse成功を意味する`。corrective-3はこの4件だけを対象にし、process/coverage nitへ広げない。
- **PANEL 8d.1 corrective-3は4件GREEN後manager final check FAIL / logout blocker 1**: RED=`cecb45e64`、GREEN=`8f8900e5e`、evidence=`5353bc0c1`をpush。managerもnew/permanent/focused/full/eval/smoke=`4/17/63/378/33/5+6`全GREENを再実行。ただしrotation後の実組合せで、resolverは`family_id`由来CSRFを返しUIが送信する一方、`/panel/logout`はraw session由来CSRFだけを検証し403、revoke 0を再現。false hypothesis=`旧raw-session CSRFの単体logout testはrotation後UIのlogout契約を代表する`。corrective-4はfamily_idを返すreal resolver→rendered UI→POST logout→family revoke→再訪login pageを1本でRED/GREENにし、他範囲へ広げない。
- **PANEL 8d.1 parent integration final PASS / migration・実L3へ**: corrective-4 RED=`6122c184e`、GREEN=`106edbb1a`。親PR #330 head=`c01057a0b`へ14 PANEL commitをrebaseし、reviewed code=`a4c869914`、evidence/final=`900db6a24`をpush。PR #331=`MERGEABLE/CLEAN`、checks=`2/2 success`。Sol・manager・fresh reviewerがexact rebased codeでlogout成功/negativeと全blockerを再実測し、corrective4/corrective3/permanent/focused/full/eval/API/UI=`1/4/17/63/390/33/5/6`全PASS、important/critical blocker 0。親CORE path・正本はbyte-identical、既知RED=`142/136/6 inherited`不変。production side effectはまだ0。次は未完COREを巻き込まないrelease topologyを確定し、additive migration→staging smoke→controlled production L3。
- **PANEL 8d.1 schema・dev merge・staging PASS / production L3へ**: migration 2本をhash固定の単一transactionで適用し、manager postflightはRLS=`4/4`、durable columns=`8/8`、functions=`6/6`、ACL failure/obsolete resolver=`0/0`、legacy sessions=`total 4 / revoked 4 / active 0`。PR #332は通常merge、merge/origin-dev=`835e28a5b`。Railway staging deployment=`6fa417c6-3d0d-4ff0-93ca-48dca1788b0e`はexact SHAでSUCCESS。fresh HTTPはhealth 200、panel 200/no-store/Forbiddenなし、invalid 403、API 401、unauth POST 401かつDB aggregate `0/0→0/0`。evidence hash=`962f43f375625c63c2757420f87219647a3d8d57c49e53c7c2882922be71038d`。production/認証/provider/TG/email/call等は0。次は`dev→main` promotionとcontrolled production PANEL L3のみ。
- **PANEL 8d.1 production promotionはpre-merge停止 / Composio contract correctiveへ**: fresh Solはaccepted refs、54 PANEL paths + runtime-inert writer doc 1件、PR #330/#331/#322 head非混入を確認した時点でmanagerが停止。一次資料 `ComposioHQ/composio@89b0ad24` のmigration noticeはmanaged OAuth legacy `POST /api/v3/connected_accounts`が2026-07-03以降`400 BadRequest`、replacement=`POST /api/v3/connected_accounts/link`と明記し、現`startCalendarOAuth`は旧endpoint・legacy body・provider redirectの`state`上書きを使用する。production PR作成/merge/deploy/env変更/provider/TG/user preference side effectは0、`origin/main=d4efde694a`,`origin/dev=835e28a5b`不変。次はこのprovider contract 1件だけをTDD build→focused/full/eval/smoke→fresh final checkし、広いadversarial reviewへ戻らない。
- **PANEL 8d.1 Composio correctiveはbuild + manager final check PASS / staging releaseへ**: PR #333はRED=`0c3f3df62`、GREEN/head=`50f63a20c`、base=`dev@835e28a5b`、2 filesのみ、OPEN/CLEAN、calendar-eval SUCCESS。旧endpoint/fallbackを除去し`/connected_accounts/link`のexact bodyとprovider redirect不変をproduction-path testで固定。Solとmanagerのfresh primary/focused/full/eval/API/UI=`21/54/328/33/5/6`は全PASS、`panel-api.js`はbaseとbyte-identical、evidence SHA=`98ff6588572a0b1eb3f1424674cb8e8dad7599f0b558679da300cec7187c65a1`。merge/deploy/provider/OAuth/env/TG/user preference side effectは0。次は`order-panel-composio-link-staging.md`でPR #333を通常mergeし、exact `origin/dev` staging deploymentとnon-mutating HTTP smokeを実測する。
- **PANEL 8d.1 Composio correctiveはdev merge + exact-SHA staging PASS / production L3へ**: PR #333は通常の2-parent merge、merge/origin-dev=`984a088e3ed59941dbb2c1015cef5017ba462d93`。Railway staging deployment=`aa9ec3c2-c448-400d-91eb-1f3f2b1d978d`はservice status/listとも同SHAでSUCCESS。Solとmanagerのfresh primary/focused/full/eval/API/UI=`21/54/328/33/5/6`全PASS、HTTP=`health 200`、`panel 200/no-store/Forbiddenなし`、invalid=`403`、protected API/POST=`401`、DB aggregate=`0/0→0/0`。evidence SHA=`34fafa2536a8a827172278228e5e608285b0c04e785f0b0f6749d1a0671a3f17`。production/provider/OAuth/env/TG/user preference side effectは0。次は更新済み`order-panel-production-l3.md`で`dev→main`通常promotionとDais本人controlled L3を実行する。
- **PANEL 8d.1 production promotion + controlled L3 PASS / done**: PR #334 merge/origin-main=`b25437f053c51b604e2c0eda36e3a6251a28ab98`、Railway production current deployment=`62493fc4-7603-499f-b01f-594b62396f83` exact SHA SUCCESS。実TG bootstrapからtoken消滅、隔離browser再起動後のstable `/panel`直接200、本人personalization、desktop/mobile 8/8 clickable、panel→TG通知往復とbaseline復元、Dais所有Calendar ACTIVE 1件、他tenant mutation 0をSolとmanagerが実測。専用second TG/Google identity不在の2項目は無断identity作成を避けて未実行と明示し、tenant contract 9/9・本人connector readbackでproduction-safe代替としてfinal裁定。evidence SHA=`dd49a41415210803908236e1bd17752d19d117bcc9dd854dd9bc2735375a0326` mode=`0600`。
- **CORE 8d method 2はcode GREEN / VCSDD review FAIL**: reviewerはfocused 51/51、full 371/371、eval 33/33、boundary 10/10を再現したが、featureのstate/spec/verdictと追跡RED→GREEN evidenceが無くcontrolled runを不許可。PR head=`58846034b`はorchestratorが独立確認。現在はPhase 1 artifactsを正規toolingで復旧中で、本番side effectは行わない。
- **PANEL 8d.1 fresh reviewはFAIL / blocker 10**: PR #331 commit=`84e1cebae`のlocal tests/smokeは通るが、実runtimeへ効かないtoggleとprovider/tenant/idempotency/OAuth/body-limit/Connect表示の欠陥、strict VCSDD gate不整合をfresh reviewerが再現。merge/deploy/L3は禁止し、同じblockerをRED化してcorrective buildへ戻す。
- historical build: DAILY core、location late notice、discovery、panel auth/API/UI、M-1 demo videoは一度L3を通っている。この履歴は残すが、現在の出荷判定には8d-hのfresh証拠が必要。
- **historical panel再open判定は8d.1/8d.2/8g/8hで解消済み**: 当時Daisの実使用で判明したaccess・二入口・personalization・connection/toggle・score semantics・timeline privacyの欠陥は、各正本行のproduction L3で閉じた。現在の次atomicは8i REPO-CONSOLIDATE。
- **CORE 8d controlled runはpending**: local closed-collector reviewはPASS/blocker 0。production binding preflightでTelnyx webhookを既定URLへ復元後、非送信依存は7/7 PASS。唯一のcontrolled invocationはTG 1通・email 1通・phone 0で両receiptをreadbackしたが、gogの分精度dateを厳密な送信ミリ秒と比較したため`email_receipt_stale`となりreport生成前exit 1。再送・artifact手編集は行わず、false hypothesisをrow 8dへ記録。次は分精度境界をTDDで是正する独立手法2。review log=`.claude/sol-orders/logs/core-8d-closed-final-review.log`、run log=`.claude/sol-orders/logs/core-8d-production-9of9.log`。
- **CORE 8e method 1はexternal-attendee gateでfail closedしexact cleanup済み**: production codeはPR #335/#337/#336、main/deployment exact SHA=`85a68abaa`で出荷済み。実nonce eventのplus aliasをGoogleが本人organizerへ正規化したためexternal attendee 0で停止。event作成1件以外のside effectは0。managerはT-10まで約6分を検知して旧Solを停止し、fresh emergency Solがexact-id+nonce-description guardでT-10窓231秒前に削除。provider/DB readbackはnonce event/Travel/wake/late/email/TG/call=`0/0/0/0/0/0/0`、unrelated calendar/tenant不変。false hypothesis=`plus aliasはCalendar external attendeeになる`。method 2はaccepted verified forwarding recipientの所有/distinctnessをcreate前に閉じる。cleanup evidence hash=`ea5f87244cb35b8cb85e44db36ac3c85eda9d420f1f41e43df4aeb6c547c1fa1`。
- **CORE 8e method 2はprovider mutation前に安全停止**: production SHA/deploy/loop時刻とrequired envだけをread-only確認し、calendar/email/TG/call/location mutationは0。material blockerは①通常CLIのrecipient/attendeeがargv/logへPII露出し得る ②late selectorが6時間窓の先頭located non-helperを選ぶためnonceへの自動束縛を仮定できない ③forwarding destination宛メールをprimary inboxで実読取できる保証がない ④travel loopはreturn helperも生成し得て1件cleanup前提が残骸を作る、の4点。method 2bは単一0600 process、exact late-target preflight、実target-inbox Message-ID、nonce由来helper全件exact cleanupへ是正してfresh再発注する。
- **CORE 8e method 2bはtarget mailbox readback gateでfail closed**: accepted forwarding targetはprimary/send-as/Calendar ownerとdistinctだが、local authはprimary 1件だけでtarget mailboxのOAuth/IMAP/browser identityは0、target→primary reverse-forwarding証拠も0。ownership metadataは実受信RFC Message-IDを代替しないため、fresh Solをprovider mutation前に停止しside effect 0。これで同一atomicの3手法FAILを満たし、false hypothesesを8e行へ固定して次の独立atomic 8fへ進む。
- **CORE 8fはcorrective GREEN local PASS / fresh continuationへ**: endpoint/UI corrective RED=`0fc453527`は7/7 genuine FAIL、production GREENはcontext eval=`12/12`とactual callback/replay/cross-tenant、user-scoped onboarding resume、signed calendar connectをPASS。full Life Call test/evalもfail 0で、provider side effect 0。変更はstagedのまま保全。重大事項だけに絞ったfresh reviewは指摘なしのまま10分超で打切り、巨大review出力を処理していた旧builderも交代する。次は再reviewせず、fresh Solがstaged diffとGREENを再確認してcommit/push→通常release→実TG/DB L3を完遂する。
- **CORE 8f GREEN/dev/staging PASS**: fresh continuationはGREEN=`771f996c9`をpush、PR #338を通常mergeしてorigin/dev=`a4e3ae9c6`。Railway staging deployment=`bcd237d9-590b-49e4-9ada-cdebcfa54beb`はexact SHA SUCCESS、non-mutating smoke PASS。production/provider/TG/DB migration side effectはまだ0。次は既存実績経路でmigration→production promotion→controlled L3だけを行う。
- **CORE 8f schema/production release PASS / L3中**: migration postflightは7 ask columns、location source、nonce table/index、RLS、public grants 0、service-role DML 4/4。PR #339 merge/origin-main=`47d0f143e`、Railway production deployment=`b0e75e9f-c48e-46dd-9ed7-2fde96323651` exact SHA SUCCESS。実TG/DB controlled L3以外は完了。
- **M-2旧Solは停止**: fixture unit/wiringはGREENだが、process消失、log末尾=`collab: Wait`、実MP4/launchd video run/IG video URL/commit/push/spec実測更新なし。未commit M-2差分は回収対象であり、doneではない。
- **M-2は既存loopのrenderer交換**: Life Manager用の新しいmarketing loopやsocial accountを作らない。既存の日次起動、account、rotation、配信経路を維持し、slideshow artifactを同じテーマのvideo artifactへ置換する。MPTはその代替rendererとしてのみ使う。
- **fresh M-2 rescue Solは未起動**: 発注書 `.claude/sol-orders/order-m2-rescue.md` は存在するが、ユーザーの「specと全TODOを先に確定」に従い実装開始を止めている。
- **Life Manager marketing loopはtmux常駐ではない**: launchd `ai.anicca.life-manager-daily` が10:15にfresh passを起動。現行scriptはClaude SonnetをCLIProxyAPI `:8317`経由で呼び、内部RC後も末尾`exit 0`のためfalse-greenになる。daily logにはOAuth失効が2回ある。
- model実測: `gpt-5.6-luna` fresh probe=`LM_LUNA_PROVIDER_OK`、context window=272k。現Claude Sonnet同経路のfresh probeは45秒timeout (`rc=124`)。9bでLuna primary・ephemeral pass・実exitへ移行する。
- 現在はCORE 8d manager-review corrective Phase 2bのfresh artifact-only review段階。implementation GREENは確認済みだがevidence closure blockerが1件確定しているため、review結果をRED化してfresh Solへ戻す。M-2 rescueを先に走らせない。

### 10.1 不確実性 U1-U10 の解決（2026-07-20 実測。4 subagent 並行調査の裁定）

| # | 結論（全て close） |
|---|---|
| U1 | **Unipile 401 = 7日 trial 失効**（6/19 作成、paid 未開始）。rotate では復活しない。復旧 = $55/mo 課金必須 → **Dais 裁定 2026-07-20: 払わない・Unipile 棄却**。代替の free-forever connector を5候補実測比較（Pipedream Connect=Free は dev 専用・本番 $99/mo で棄却／Nango self-host・自前 googleapis=Gmail readonly が restricted scope で年次 CASA 復活のため棄却／Arcade=2K call/月で容量不足／Paragon=恒久 Free なし）→ **勝者 = Composio 一本化**: Free $0 / 20K tool calls/月 / Unlimited Connected Accounts / OAuth managed（trial 表記なし、8/15 改定後も同条件。出典 composio.dev/updated-pricing）。cache 済み 8,640 call/月/user 前提で **$0 のまま 2 user**。**⚠ 是正（2026-07-20 深夜、origin/main 実読）: 「Gmail も Composio」案は不成立** — prod コード unipile-connect.js 冒頭に実測記録あり:「Composio managed Google app は restricted gmail scope 未認証で consent が HARD-BLOCK（実ブラウザ実証）」。研究 agent の推奨はこの実測と矛盾 → 実測が勝つ。**確定裁定: ①calendar = Composio 継続（現行、cache 済み）②Gmail 読み(search-before-ask A2/context graph/PHY 履歴) = 当面 OFF（正直な feature gate。DAILY は Gmail 不要 — 遅刻メール送信は Resend で自走）③Unipile 参照は dormant 化（削除でなく env 無し時 graceful off を確認）④Gmail 復活の道 = 有償 Unipile($55) or 自前 OAuth+CASA、S2 で再判断**。順3 の実装 = graceful-off 確認 + budget guard のみに縮小。scale 時（3+ users）= §8b S2 で再判断 |
| U2 | 無応答 fallback は自動で sendLateNotice 到達（scheduler.js:178-181/late-notice.js:29-34,89-106）。**ただし T-0 行の生成に T-5 で AMD=human（実際に出る）が必須**。TG message_id は保存されない実装 → 証拠 = 受信メールの Message-ID。E2E 手順は TaskList #1 に焼き込み済み |
| U3 | call_language=en 実測確認（Supabase 実 row）。順1の whisper 英語判定は妥当 |
| U4 | prod webhook allowed_updates=["message","callback_query"]。**edited_message 無し → LM-30 で追加必須**（live location は edited_message で届く） |
| U5 | control panel認証 = **全user共通の恒久・bookmark可能なexact canonical `/panel` + 個人別durable rotating session**。temporary/single-use/user-specific panel URLは禁止。TG bot `/panel` はexact canonical URLの`web_app` buttonだけを返し、serverはPOSTされたTelegram `initData`のHMAC・auth_date・bot/user/chat・one-time replayを検証してsessionへ交換。通常browserの未認証`/panel`は同じpage内にhash-only短命device codeを出し、本人がbot chatへcodeを入力すると同じbrowser challengeへsessionを結ぶ。code/token/user idはURL/query/path/referrer/history/logへ0件。旧`?t=`は交換せずcanonical loginへ戻す。sessionはlogout・uid/chat再紐付け・security revoke・storage消去までrotation/refresh。panelとchatは同じuser-scoped connection/setting commandを使う |
| U6 | MoneyPrinterTurbo 流用可（Mac mini 依存充足、$0/本、3-15分/本）。**既存 faceless-money-factory の代替レンダラーとしてのみ**（全置換しない）。順9 spec に採用 |
| U7 | FIN の agent wallet = **LM agent が新規自己生成**（§4 Franklin 型が既に答え。既存 automaton/Franklin wallet 流用しない）。spend-cap = 残高 |
| U8 | 対外メールの名乗り = `Life Manager（AI secretary, acting for <user>）`、本人を装わない・初文で委任明示・機微情報は項目別同意・本人回答要求時は転送。Clara 実例準拠。順11 spec に採用 |
| U9 | rotate runbook 正本 = `2026-07-17-lm21-rotation-runbook.md`（実在確認済み）+ 13キー発行元/再登録表を今回更新。実行 = `railway variable set K=V ... --skip-deploys` → redeploy 1回 → setWebhook/inbound URL 再登録 → 全 smoke 後に旧 key revoke |
| U10 | PR #312 = **OPEN 未マージ**（dev loop D0 産、issue #11 travel-autofill fix）。順2 に「review→merge 判断」を含めた |
| INC-1 | **prod Telegram webhook 401 事故と修理**: `--skip-deploys` で staged した新 `LM_TELEGRAM_WEBHOOK_SECRET` が後続 auto-deploy で本番へ入り、Telegram 登録は旧値のままなので全 update が401になる。現 prod env の secret で `setWebhook` を再登録し、allowed_updates=`message,edited_message,callback_query`、pending=0、last_error=null を実測。secret 値はログ・spec・commitに残さない。一般法則: **--skip-deploys の staged 値は「次の deploy に必ず乗る」— staging した瞬間から、対応する外部再登録（setWebhook 等）を deploy 前提条件として同じ発注に束ねる** |
| INC-2 | transient 露出2件（Sol 自己申告 2026-07-21）: Railway pairing code 1件（既に失効・再利用不能）+ panel 単回 URL 1件（used_at 焼き済み・再利用は 403 を negative test で実証済み）。**Fable 裁定: どちらも自己失効型で rotate 不要・追加対応なし**。永続 secret の漏洩はゼロ |

### 10.2 検証の3層（用語の確定。「何も無いのに E2E?」への恒久回答）

**E2E は「作った後の証明」。まだ作っていない物の E2E は存在しない。** 順1の E2E は「07-17/18 に既に prod へ投入済みだった DAILY 核（LM-2/24/26/28/3/7）」への証明であり、新機能の試験ではなかった。順5以降の未実装分は必ず build が先。

| 層 | 何 | いつ | 例 |
|---|---|---|---|
| L1 unit/TDD | コードの分岐が正しいか。RED→GREEN、CI で毎 commit | **build 中**（Sol） | shouldSendT0 の境界、token 検証 |
| L2 **AI EVAL** | **LLM の判断品質**。固定 dataset × N ケースを engine に食わせ、期待 label と突き合わせて **score%**。判定者も LLM（LLM-as-judge）だが dataset と合格線は固定 | **build 中〜出荷前**（Sol が作り、Fable が合格線を裁定） | §9.7 の9 edge case: 「歯医者」1語 → expected=履歴から場所推定 / 終日 event → expected=call 対象外。**合格線 = 9/9 自動判定ケース全問 + 曖昧ケースは closed Q 発行が正解扱い** |
| L3 E2E | 実世界の side-effect。実 call 録音・実 TG・実メール Message-ID・実 DB row | **build 完了後の最終証明**（Fable） | 順1で実施済みの録音 whisper |

- **EVAL の実体（LM-31 で最初に建てる。以後全 organ 共通の型）**: `apps/life-call/eval/calendar-cases.jsonl`（1行 = 1 case: 入力 event JSON + expected 判定）→ `npm run eval` が interpreter に全 case を流し score 出力 → **CI gate: score 100% 未満で merge 不可**。新しい失敗 event を見つけたら case を1行足してから直す（§12 の「表に無いバグは存在しない」と同型）。MEN(#12) の affirmation trigger 判定・PHY(#11) の未通院検知も同じ jsonl+judge 型で eval を先に書く。
- 効果: 「出荷のたびに Dais に電話して試させる」が消える。L2 で品質を数字にし、L3 は各 TODO で **1回だけ**。

### 10.3 Test matrix / E2E judgment

- §10の各行が1つのTo-Beと固有done条件を持つtest matrix。全行でL1/L2/L3のうち該当層がPASSするまで状態をdoneにしない。
- historical evidence、DB flag、agent自己申告、API 200だけではL3を代替しない。success/failure/timeoutの各classが発火し得るtestを持つ。
- 7日streakはsessionが待たず、launchd/gateway cronがURL/metric/no-op理由を日次追記し、7日目にmachine判定する。

| Item | Value |
|---|---|
| UI変更 | あり（panel score/timeline/UX） |
| 結論 | Maestro: 不要（web panelのため）。authenticated real-browser E2E + mobile/desktop visual QA + semantic assertionが必要 |
| 外部side-effect | 実call、実TG、実email、実calendar、実IG/TT/X URL、実web予約、実on-chain tx。各atomicで指定した実物だけがPASS |
| 定常運用 | launchd/gateway cronの実run、model/exit/cost ledger、streak ledger、self-healを確認。Fable/Daisの手動継続操作はFAIL |

## 8. 次セッションへの引き継ぎ（実装はそこから）

1. 最上位pending `8i REPO-CONSOLIDATE`をSuperpowers/TDD/review/verification workflowで実行し、`apps/life-call`・必要なengine/skills・本spec・deployment sourceを既存repository ID `1248111245` の`Daisuke134/life-manager`へ吸収する。新repo作成、force-push、history rewrite、cutover前の`anicca-products` archiveは禁止
2. `8i`のequivalence・canonical repo test/eval・production L3・Railway exact commitを通し、成功後だけ`anicca-products`をarchive + README redirectにする。以後の新規product workはcanonical repoだけへcommit/pushする
3. 次に`9b`から順に進め、`8e`はcontrolled inbox readback auth、`8f`はreal location input経路が得られた時点でL3をcloseする。両方がpendingのままPhase 1全体をdoneにしない
4. TaskList: #12(OSS) は P3 に吸収、#41(LIFE-AUTO) は P1 内機能として再定義済
