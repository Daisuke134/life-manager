日本語で報告。AGMSG lm teamの専用担当 lm-internal-promptbase-step-wait-1005 として実装する。model gpt-6-luna、effort max、旧model fallback不可。

専用worktree: /Users/anicca/Projects/life-manager-main/.worktrees/lm-promptbase-playwright-step-wait-20261005
branch: fix/lm-promptbase-playwright-step-wait-20261005
base/HEAD: 82d31995e68a5220b7a288318a893866a24c7ea6
primary lease owner: codex-money-printer-promptbase-step（24h）。primaryがSSOTを所有し、あなたはSSOTを編集しない。

あなたは他者と同じrepoにいる。他者の変更を戻さず、所有filesは skills/earn/promptbase/scripts/publish.py と skills/earn/promptbase/tests/test_publish_diagnostics.py だけ。まずskills/loop-development/SKILL.mdと適用Superpowers TDDを読む。
根因: _wait_for_stepがPage.wait_for_function(expression, expected)とpositional引数を渡すが、実Playwrightは(self, expression, *, arg=None, timeout=None, polling=None)。実Page methodをsignature-only fixtureへbindしたno-browser probeでTypeErrorを再現。_fill_step1が例外を握りつぶすため待機が実行されない。既存fakeはpositional expectedを受けるので誤ってPASSする。

最小RED: fakeのwait_for_functionを実APIのkeyword-only arg契約へ直し、現helperがTypeErrorになることを確認。最小GREEN: arg=expectedで呼ぶだけ。実installed Page signatureのbindを使うno-browser assertionなど必要最小の契約照合でfakeと実APIの差を覆う。provider CLI/browser/HTTP/投稿/credentials/profile/state/price/model/category/cadence/timeout/fenceを操作・変更しない。worktree sourceをproduction profileへ接続しない。

focused existing diagnostics testsと必要な隣接publisher tests・bash不要・diffcheck・既存loop structural contract gateを確認。sparseのtracked依存不足は必要範囲をmaterializeし、testを弱めない。root.envを読むCLIは禁止。

git fetch後、指定2filesだけcommitしown branch -u push、remote object一致/clean確認。hook迂回不可。PR/main/release/apply禁止。primary codex-money-printerへagmsg sendで着手/RED-GREEN/commit/検証/残限界を報告。登録・readinessと着手を区別し、自分の実model/effortはruntimeの観測できる値だけ報告。
DONEは2file最小fix、実keyword-only契約RED→GREEN、検証PASS、commit/push/remote確認、source-only限界と報告。
