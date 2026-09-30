# Life Manager handover — universal observability / No-Human / One Entity

## 正本と作業場所

- TODO/状態SSOT: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-observability-readback-20260929/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の EOF 節「現在の正本cursor（2026-09-30、全Skill共通observability・No-Human・One Entity契約）」、特に「E. 新しい原子TODO」1–12。
- 実装可能な専用worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-observability-readback-20260929`
- branch/upstream: `docs/lm-universal-observability-20260930` / `origin/docs/lm-universal-observability-20260930`
- 最新確認commit: `a4358ea4b7913f917c8bf581d12379308064ae98`; worktreeはclean、同じSHAがremote branchに存在する。
- `origin/main`は現在`de3c9064fac327e869558a43f93ae32957317d3f`で、現在branchより2 commit先行。編集前に必ず`git fetch origin`、HEAD/upstream/dirty-stateを再確認し、必要なら専用branch上で安全にrebaseする。
- 触ってはいけない場所: 共有checkout `/Users/anicca/Projects/life-manager-main`、無効な境界の`/private/tmp/lm-source-reconcile-20260930`、production `/Users/anicca/loops/current`、provider/browser profile、他agentのworktree。

## 何を完了したか

- specに、全Skill共通`lm-loop.health.v1`、6観測軸、4時計、型付きstatus/exit code、5分read-only observer、state-change dedupe、`human_required` qualification、One Entity/interface-free方針、canonical `/lm`、Meta Loop gate、収益readback、原子TODO 1–12を記録した。
- commit `a4358ea4b7`をpush済み。`git diff --check HEAD^ HEAD`と専用worktree内`bash scripts/verify-source-boundary.sh`はPASS。
- spec更新だけを行い、production owner、browser、provider、外部ページ、Ryu DMは変更していない。重複送信もしていない。
- 参照済みの公開面: `https://aniccaai.com/en`、`/ja`、`/lm`。これは現状把握のみで、統合ページは未実装。

## 現在cursor / 未完了

1. まず`lm-loop health` read-only集約CLI（human-readable、`--json`、`--skill`、`--loop --explain`、exit code）を実装する。
2. `lm-loop.health.v1` schema/validator/focused testとregistry全jobの`skill_id/product_loop_id`結合。
3. runtime event・receipt・admission・launchd・CFOからatomic HealthSnapshotを生成し4時計を全Skillへ展開。
4. `lane_health.py`、`pass_health.py`、`status --explain`を共通projectionへ接続。
5. 5分observer、state-change alert dedupe、Telegram/outbox `next_action`、retention。
6. 全platform共通`human_required` qualification。面接・試験・録音・camera・screen share・自由回答・継続承認が必要な候補はskip/holdし、人へ委譲しない。
7. Coconala/Lancers/CrowdWorks/Mercor/Upwork/Freelancer adapterへhuman-free eligibility、account-bound authorization、funded contract、official receipt、replay-zeroを接続。
8. `/en`・`/ja`・`/lm`をcanonical `/lm`へ統合し、redirect/alias、mobile/locale/SEO/privacy/readbackを検証。
9. Meta LoopをHealthSnapshot consumerとして接続し、gates未達platformをenrollしない。
10. 全Skillが`healthy`または型付き`safely_fenced`、`telemetry_gap=0`、未説明`effect_unknown=0`、release provenance一致になるまで24/7正常・収益達成を主張しない。その後にpaid E2E、settlement、payout、net MRRを実測する。

## 既知の注意点 / blocker

- spec作成時の観測値とlive値を混同しない。live `current`は現在`/Users/anicca/loops/releases/20260930T113159-de3c9064`を指すが、health/readbackの合格を意味しない。
- specに記録したadmission値は有効`526761984 bytes`対必要`536870912 bytes`でcapacity gate失敗。通常の`df`空き容量やPID/registryだけでhealthyと判定しない。
- 直近readbackでは一部Coconala/CrowdWorks/Lancers/Mercor ownerが`75/78/1`系の失敗・停止を示した。再実行前にoccurrence、effect、official receiptを追加観測する。
- `effect_unknown`は公式readbackまで再送禁止。KYC/CAPTCHA/本人確認を突破しない。providerが人を要求する案件は選ばずholdする。一度だけの法的・provider必須KYC/authorizationはbootstrap境界として記録する。

## 最初の安全な再開操作

1. 専用worktreeで`git fetch origin`、`git status --short --branch`、`git rev-parse HEAD origin/main`、差分を再確認する。
2. 上記SSOT EOF節を読み、現在値（release、admission、owner、receipt）をread-onlyで更新する。新しい事実があれば同じspecへ反映してcommit/pushする。
3. TODO 1から、既存の`runtime/loop`、`runtime_event.py`、registry、admission、receipt実装を再利用してCLI→schema→projectionの順に最小差分で実装する。production/provider/browserを直接変更しない。
4. focused test、natural run、official readback、replay-zeroを各外部効果の境界で実測し、Done判定を証拠で更新する。

