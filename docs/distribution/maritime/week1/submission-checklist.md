# 初週提出のチェックリスト

公式指定形式はT01で確定する。下記は提出準備であり、公式必須条件を発明しない。

2026-10-21 14:09 JSTにLife Managerのentryを`#competition-submissions`へ一度共有し、permalink `https://keikixmaritime.slack.com/archives/C0C9PEL45JA/p1792559347988839`をreadbackした。2026-10-21 15:44 JSTにもentryは1件だけと確認した。channel descriptionは「投稿は必要なformを置き換えない」と明記する。公開ページ・Termsとannouncementsにproject formがないため、`contact@maritime.sh`へWeek 1の正式提出経路・期限・必須demoを問い合わせた（Gmail SENT/readback `1a15d3141c56ee22`）。返信は06:43Z時点で未着。**entry shareは完了、formal submission receiptは未確認**。

2026-10-21 17:06 JSTに公式home/Termsを再crawlし、Week 1 cutoff/rubric/formなしを確認。
17:07 JSTのSlack readbackではannouncementsにsetup/join投稿のみ、help検索結果0件、submissionsのLife Manager entryは1件。
17:08 JSTのorganizer-domain Gmail検索は一致0件。
既存threadへroute確認follow-upを17:13 JSTに送信（message `1a15d85b491c9450`）。
正式受付receiptは未確認。

T23.1のaggregate-only packetは`submission.json`として08:11:36Zにdraft生成済み。
`node --test apps/life-manager/scripts/maritime-week1-export.test.js`は1/1 PASS。
packetにexternal users/work receipts=0、costs=null、formal receipt=nullが入る。
作業時modeは0600、SHA256は`fa891f6e8ed9410a0bb7c6249a0a698c259557578a6816dfaaf5c4f756ca9865`。
このdraftは正式提出ではない。

- [ ] 正式提出先、初週締切、timezone、必須field、再提出可否を`requirements.json`へ保存。
- [ ] メール登録から一つの実業務を試せる公開URLを確認。
- [ ] loaded main source SHA/配備ZIP archive SHA256とMaritime project usageを結合。
- [ ] 一文説明、実行範囲、対象利用者、未接続条件を記述。
- [ ] 最小の実画面demoを保存。2–3分動画は推奨で、指定がなければ受付を遅らせない。
- [ ] 実測の外部利用者/業務完了/再利用/費用を記録。未取得はnullと理由。team/test/founderは別。
- [ ] Local founder実績と新規Cloud利用者の実績を分ける。
- [ ] 改善した不具合/feedbackを記録。friend feedbackがなければ実装観測の修正を事実として書く。
- [ ] 公開URLと正式必須項目が揃い次第提出。友人3人、売上、7日継続、1,000人は初週提出の待ち条件にしない。
- [ ] submit直前に既存受付/重複を読み、一回提出。
- [ ] confirmation画面または受付メール/IDをreadbackして`submission.json`へ証拠参照を保存。
- [x] T23.1 aggregate-only draft packetを生成し、measured fieldsだけと未計測nullをfocused testで確認。
- [ ] 正本のT23を提出済みにする。ファイル生成・送信API成功だけでは受付完了としない。

収益額が最大のチームが勝つという公式条件は確認できない。競技の最終winnerは実利用者1,000人へ到達して検証された先着3組。利益・継続率は製品と獲得を強くするために追う。
