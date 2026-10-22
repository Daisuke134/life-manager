# Manager — ローカルCodexへの実装引継ぎ

2026-10-22 UTC。ユーザーがクラウド側での追加実装を止め、ローカルCodexへ引き継ぐよう指示した時点の記録。**未レビューWIP。配備済み・全検査合格・E16完了ではない。** task authorityは既存SSOT/roadmapだけ。この文書は実行状態の引継ぎで、新しいTODO正本ではない。

## 復元するsource

- Repository: `https://github.com/Daisuke134/life-manager`
- このWIPの転送先: `research/manager-e16-local-handoff-20261022`
- 直前の検証済みcommit: `9ea03355acbcb8e251e3f4c79df6ca16da8a09f9`
- 元の実装branch: `research/manager-e01-e16-execution-20261022`
- 元PR: <https://github.com/Daisuke134/life-manager/pull/8527>。draft/open、baseは`research/manager-phase06-owned-public-good-20261022`。mainではない。
- Cloud worktree: `/workspace/manager-execution`、local branch `research/manager-e06-cloud-execution-20261022`、common git `/workspace/life-manager/.git`。
- ローカルでは既存canonical checkout/作業中worktreeを確認し、未コミット差分を保全してから専用worktreeへ移す。クラウドの絶対pathをMacのruntime設定へコピーしない。

最初に`AGENTS.md`、`REVIEW.md`、`.agents/skills/goal-setter/SKILL.md`を実際に読む。`skills/goal-setter`は同skillへのsymlink。利用可能なSuperpowersと`skills/loop-development/SKILL.md`を適用する。goal-setterは実在し、今回`git show HEAD:.agents/skills/goal-setter/SKILL.md`で本文を読んだ。user-sent `/goal`を作成する形式を採用し、このクラウドsessionで新しいgoalをactivateしたとは主張していない。

次に`products/manager/README.md`、製品仕様、既存atomic plan、E16 deployment handoffとrecovery receiptを読む。全工程は`docs/roadmap/START_TO_END_20261022.md`、受入状態は既存`docs/roadmap/tasks.json`を参照。原113件は69 done /41 todo /3 skippedのまま。E01–15をやり直さずE16から続ける。

## 認証情報待ちを再開条件にしない

ユーザーは既存の接続済み認証を使い、無料経路で継続するよう明示した。資格情報の値を再送させない。connectorとrunnerのidentityは別なので、既存GitHub Actions jobの`GITHUB_TOKEN`とGitHub OIDCを利用する最小bridgeを実装中。secretをchat/source/public artifactへ書かない。

実際に確認したもの:

1. GitHub APIは成功。repository ID `1248111245`、public、default branch main、readback上admin/push=true。通常git pushは既存proxy認証で成功済み。一方Actions secrets/variables一覧はHTTP403 `Resource not accessible by integration`。これはsecret不存在の証拠ではない。ローカルで既存認証を確認し、必要なら既存の別経路を使う。再ログインやcredential抽出を先に要求しない。
2. SupabaseのPrimary接続に **`life-manager-staging-20260808` / `ulhsqqkyejzvqgoyjwte` / ACTIVE_HEALTHY** が存在。org `glduujwsvfyvrakhqbvm`。public33tablesはRLS=true、Edge Functions0。既存data/他ownerを保全する。Managerという接続名の別accountには旧`anicca.ai` / `mzkwtwourrkduqkrsxpc`がINACTIVEだが、これを理由に全Supabaseを利用不能扱いしない。
3. Railway既存life-manager project `5ea5e492-a3e8-4778-939a-e59a6261f9a8`、production environment `4ddafa5d-7113-4fea-8608-7dfde4838436`、service `7c8e5f7e-6773-4f94-ab46-a619cdf592e3`。旧deployment SUCCESS、volume0、variable names0。用途を確認せず上書きしない。
4. Railwayには$0/月+$1/月creditの継続Free planがある。Trialは一回$5/30日で別。既存workspaceの実planは未確認。public standard Actions runnerは無料。Supabase FreeにはDB500MB/Edge月50万回等があるが、既存orgのplan/残quota/実費は未確認。新しい有料resource/planは作成していない。無制限・永久無料とは主張しない。

一次資料: <https://docs.github.com/en/billing/concepts/product-billing/github-actions>、<https://docs.github.com/en/actions/reference/security/oidc>、<https://supabase.com/pricing>、<https://supabase.com/docs/guides/functions/auth#external-webhooks>、<https://docs.railway.com/pricing/plans>。

## 直前の検証済み範囲

9ea03355aではPython684 tests OK（optional skip5）。過去intent先行回収、再生不能なfresh dispatch、provider occurrenceとdelivery分離、lag/hash-onlyでrollbackしない処理を実装済み。DBOS固定sourceで実際の16 crash/restart casesを現在方式と比較し16/16合格。DBOS採用はUNDECIDEDで、依存をcore defaultへ足していない。

- 記録: `docs/verification/E16_RECOVERY_HARDENING_20261022.md`
- Runtime比較: `docs/verification/E16_RUNTIME_COMPARISON_20261022.json`
- 直前CI: Python run39806720920 / browser run39806720845 SUCCESS
- 本番CLIは依然`DEPLOYMENT_HOST_REQUIRED`/exit2。fixtureはP0で本番ではない。

## 今回のWIPと現在の検査結果

### v2 main admission

`manager_core/digital_handoff.py`、`scripts/phase06_kernel_release.py`、`tests/test_main_publisher_admission.py`。

v1のref/hash/過去receiptを保持し、v2はmain専用identity。actual workflow SHA/source checkout SHA、event、元のartifact/7paths/admissionを検査。`prepare_owned_change(...,schema=...)`を追加し、`admit_owned`は元packetのleaseを保持する変更を含む。まだworkflow/production cycleへ配線していない。

**現在この新testに1エラーあり。** 全Python検査は694 tests、errors=1、skipped=5。エラーは`test_owned_bridge_revalidates_v2_scope_and_retains_original_packet_lease`で`prepared.packet is None`。読取で実原因を確認した:

- 新testがimportする`test_digital_handoff.NOW`は2026-10-22T00:00Z。
- 再利用fixtureのcriteria/context時刻は`test_candidate_verification.NOW`=同日12:00Z。
- `prepare_owned_change`の実際のreasonは`FUTURE_CONTEXT`。

最初の修正はfixture時刻を整合させ、現在のfreshness拒否を保ったまま再実行すること。検査を削る/未来contextを許す変更で緑にしない。これ以外にもレビューで欠陥が見つかり得るので、この診断を全体合格とは扱わない。

### private SQLite checkpoint client

`manager_core/owned_checkpoint.py`、`tests/test_owned_checkpoint.py`。focused6/6 PASS。SQLite Backup APIでWALのcommitも保存し、整合性/保存intent/parent/hashを検査。fresh private scratchへremote snapshotだけをrestore。missing/旧cache/壊れたDB/source配下/symlink/競合owner/CAS応答消失をfail closed。応答不明のsessionは再利用せず、dispatch flagを復元しない。まだ本番cycleから呼ばれていない。

### Supabase gateway / SQL

`deploy/owned-digital/20261022_private_checkpoint.sql`と`deploy/owned-digital/state-gateway/`。

- `auth.mjs`、`index.ts`、`auth.test.mjs`、`checkpoint.test.mjs`、`deno.json`、`package.json`、`package-lock.json`。
- dependenciesは`jose=6.2.13`、test-only `@electric-sql/pglite=0.5.11`にexact pin。
- Node v24.19.0 test **65/65 PASS**。実jose RSA署名、strict HTTP/秘匿、PGliteの実PostgreSQL SQL/CAS/RLS検査。NodeのTypeScript strippingでindex.tsを読み込む。live Supabase/GitHub OIDCの証拠ではない。
- **Deno typecheckとdeno.lock生成は未実施。fresh独立reviewも未実施。** `node_modules`はignoredで転送しない。
- endpoint固定: `https://ulhsqqkyejzvqgoyjwte.supabase.co/functions/v1/manager-owned-state`。**未配備。**
- verify GitHub issuer/JWKS/RS256/aud、repository/owner IDs、main、既存workflow、schedule/workflow_dispatch、sha=workflow_sha、run/attempt。
- request `{operation,nonce}`。operationはacquire/checkpoint/release。checkpointだけ`revision,sha256,snapshot`を追加。ownerは検証済run ID/attempt+UUIDv4から作る。responseはexact `{revision,sha256,snapshot,owner}`。
- 専用1row、remote owner lease/revision CAS、1MiB raw SQLite/2MiB JSON上限。RLS有効、PUBLIC/anon/authenticatedのtable/RPC権限なし。service_roleはEdge内部の既存platform identityだけ。既存33tablesは変更しない。
- missing rowを自動初期化しない。bootstrap/old-backup restoreは別の照合済みoperator操作。lease失効でUNKNOWNを削除しない。recovery_requiredはacquire/checkpointを止める。
- SQL invalid digestはPT400で拒否、現gatewayはそれを503へ秘匿。安全側停止だがHTTP分類は必要なら次のRED/GREENで精査する。

## 次に実行する順序

1. WIPを保全して復元、source/branch/remote/ownerを確認。新testの時刻を整合させ、focused/全Python検査。Deno typecheck/lockとNode検査を完了する。
2. 上記auth/CAS/checkpoint/admissionの差分をfresh独立read-only reviewerに確認させ、correctness/security/Doneに関わる指摘を修正する。未検証のsourceをそのまま配備しない。
3. 既存atomic plan PATCH05/06を続行。薄い本番host adapterとCLI/workflowを同じcycle/outbox/admit_ownedへ接続。新しいworkflow engine/同じloopの別実装を作らない。**送信予約をremoteへCAS保存し確認した後にだけ元publisherへ進む。** 応答不明はread-only reconciliation、private stateを公開artifactに入れない。
4. 研究PRのbase chainを実確認し、通常review/checks→main→同じimmutable SHAのreleaseへ進める。現PRはmain向けではなく、origin/mainとの差分は約580files。baseを勝手に差し替えてチェック済み扱いせず、元の正常なpromotion経路を復元する。研究refをlive allowlistへ追加しない。
5. 同じcommitted sourceのSQL/Edgeを既存stagingへ限定適用。先にlogs/advisors/schema/ownerを読む。既存advisorsにlm_managed_period等のpre-existing警告があるので、新patchの原因と混同しない。新table/RPCのanon/authenticated拒否、実OIDC positive/negative、two-owner/CAS/応答消失/run跨ぎrestoreを検証。
6. 元7パスpublisher/CAS/唯一のPages owner（既存workflow307239134）で1canary。正確なcommit/parent/all7body、独立公開GET、次run replay-zero、停止/restore/catch-up/限定rollbackを実receiptで確認してE16/Fを判定。
7. E16後も原41件を依存順に継続。研究/eval、利用と便益、出版物/主website、顧客/入金、求人/YC/機会、Phase12/G006は各々の本当の受入証跡で更新。応募/採択/売上/人の便益をfixtureやローカルテストから創作しない。外部待ちの項目を保存し、独立して進められる残作業を続ける。

## 検証command

`products/manager/`で:

```sh
python -m unittest discover -s tests -p 'test_main_publisher_admission.py' -v
python -m unittest discover -s tests -p 'test_owned_checkpoint.py' -v
python -m unittest discover -s tests -q
python scripts/check_boundaries.py
python scripts/make_roadmap.py --check
```

`products/manager/deploy/owned-digital/state-gateway/`で`npm ci --ignore-scripts --no-audit --no-fund`→`npm test`。Deno検査はdeno.json/実runtimeに合わせて実行し結果を残す。browser/CI/実canaryはsource修正に応じた実在の経路で確認する。

rootから`bash scripts/verify-source-boundary.sh`。cloudではcanonical `/home/agent/Projects/life-manager-main` missingでexit2だった。userのcloud source編集許可によりsource作業を継続したがguard PASSとは記録していない。ローカルでは実canonical/worktreeの条件を正規に満たし、guard編集/偽path/env偽装で通さない。

## 作業方針

日本語で報告する。既存認証/既存plugin/正規CLI/ブラウザownerを実際に確認して使い、存在を推測してstopしない。認証を再収集したりログへ出したりしない。無料枠の既存部品を再利用し、まだ解ける実装/検証/復旧を「permission待ち」で放置しない。本物の外部拒否や権限不足が残る場合だけ、試した経路・実エラー・最小の必要操作を記録する。無許可の課金、破壊、他ownerの停止、秘密流出、証拠の捏造で解除しない。

ユーザーは「主張/計画だけでなく実装を続ける」ことを求めている。Doneはゴールの実結果と真正な外部証拠で判定し、長期使命『苦しみを終わらせる』を単一releaseやYC採択で達成したとは宣言しない。
