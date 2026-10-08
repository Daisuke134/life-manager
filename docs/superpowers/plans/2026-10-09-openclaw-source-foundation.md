# OpenClaw source foundation

Spec/state: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` 最終OpenClaw section。
Goal: 本番を変更しないworktree実装。
Task 1: package exact pins/lock; command `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`。
Task 2: paths/request/identity、Node testsをRED→GREEN。
Task 3: domain dispatch保存、Python testsをRED→GREEN（排他競合・symlink・変更digest・終端後再送拒否）。
Task 4: Gateway boundary、公式SDKの配布定義を先に読み、Node tests RED→GREEN。SDK/pin conformanceは別証拠として残す。
Task 5: child env allowlist、Node tests RED→GREEN。
Test command: `node --test runtime/openclaw/tests/*.test.mjs`; `python3 -m unittest discover -s runtime/openclaw/tests -p 'test_*.py'`。
Review focus: 再送/データ消失、symlink、secret継承、異なるrunの終了証拠流用。
Ruling: skillのモデル強制/merge承認指示はユーザーAGENTSと矛盾するため、UIモデル継承・依頼済作業は確認待ちなしを採用。

Ruling: OC001の独立protocol依存を削除する。npm 404とgateway-client exportsで確認した実在4package + Node pinを利用し、wire protocolは公開SDKで指定する。旧specの「exact5versions」は5 npm packageという意味ではなくruntime/SDK/2plugin/Nodeの5pinsへ修正。危険: handshake不整合はOC012でfail closed。

実行ledger: Task2 paths/request/identity 3tests RED(not implemented)→GREEN。Task3 dispatch 5tests RED(not implemented)→GREEN。Task1 lock未完: nonexistent protocol corrected、npm lock generation ENOSPC。失敗固有tmp D1LnJ1のみ削除、再installなし。
Ruling: session_roleはv2に存在しないため、trusted task_classをroleとしてsession tupleへ利用。侵害時のコストは同owner内session混線なのでclosed request/route authorityで接続前に照合する。
