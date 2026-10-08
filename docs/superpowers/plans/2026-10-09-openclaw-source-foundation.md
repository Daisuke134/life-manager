# OpenClaw source foundation

Spec/state: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` 最終OpenClaw section。
Goal: 本番を変更しないworktree実装。
Task 1: package exact pins/lock; command `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`。
Task 2: paths/request/identity、Node testsをRED→GREEN。
Task 3: domain dispatch保存、Python testsをRED→GREEN（排他競合・symlink・変更digest・終端後再送拒否）。
Task 4: Gateway boundary、公式SDKの配布定義を先に読み、Node tests RED→GREEN。SDK/pin conformanceは別証拠として残す。
Task 5: child env allowlist、Node tests RED→GREEN。
Test command: `node --test runtime/openclaw/tests/*.test.mjs test/openclaw-portability.test.mjs`; `python3 -m unittest discover -s runtime/openclaw/tests -p 'test_*.py'`。
Review focus: 再送/データ消失、symlink、secret継承、異なるrunの終了証拠流用。
Ruling: skillのモデル強制/merge承認指示はユーザーAGENTSと矛盾するため、UIモデル継承・依頼済作業は確認待ちなしを採用。

Ruling: OC001の独立protocol依存を削除する。npm 404とgateway-client exportsで確認した実在package + Node pinを利用し、wire protocolは公開SDKで指定する。旧specの「exact5versions」は5 npm packageという意味ではなくruntime/SDK/2plugin/Nodeのpinsへ修正。危険: handshake不整合はOC012でfail closed。

実行ledger: Task2 paths/request/identity 3tests RED(not implemented)→GREEN。Task3 dispatch RED(not implemented)後、macOS /var→/private/var aliasをfixtureがcanonicalizeせず4件失敗。GREEN記載を訂正し、fixture rootをrealpathへ修正して再検証する。Task1 lock未完: nonexistent protocol corrected、npm lock generation ENOSPC。失敗固有tmp D1LnJ1のみ削除、再installなし。
Ruling: session_roleはv2に存在しないため、trusted task_classをroleとしてsession tupleへ利用。侵害時のコストは同owner内session混線なのでclosed request/route authorityで接続前に照合する。

配布SDK package.jsonのdependenciesから正式名称 `@openclaw/gateway-protocol@2026.8.1` を確認しexplicit pinへ追加。旧 `@openclaw/protocol` と別物。既存probe lockを再利用して大きい再展開を避ける。

実行ledger更新: Task1 existing probe lockを種にnpm lock生成成功、5published pins/integrity確認。Task3 fixture canonical path修正後Python5 PASS。Task4 Node5 RPC境界tests RED→GREEN、full runtime conformance未完。Task5 env allowlist RED→GREEN。requestDigest/non-JSON schema RED→GREEN追加、全Node11/Python5 PASS。
Ruling: 固定公開SessionRowにactiveRunIdsなし。exact sessions.list readだけを実装してliveness=unknownを返し、claim解放へ未接続。旧specの停止proofは未達と記録する。危険:後続実装がunknownをfalseへ変換すると二重実行。
一次資料: https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/packages/gateway-protocol/src/schema/sessions-row.ts 、同commit src/gateway/agent-turn/agent-turn-service.ts。SDK tarball2026.8.1のreadiness.d.mts/package.jsonを確認。Context7 /openclaw/openclaw docsでhello/start/request contract照合。

Final: fixed independent review reconnect readiness and first-hello close race — 2回帰tests RED→GREEN、全Node13/Python5 PASS。
Ruling: finishing skillの統合確認menuは依頼済commit/push/通常統合で質問しないユーザー指示に劣後する。PR main統合を自律実行し、本番切替はしない。

Final: fixed digest型coercion — JSON-array regression RED→GREEN。Final: fixed unreadable oversized receipt — size/preservation regression RED→GREEN。全Node14/Python6 PASS。review他に重要指摘なし、実SDK/native runtime/claim/tool本番は明示未検証。Deferred minors: なし。PR7280、通常main append競合は双方の証拠を保持して解消。本番操作0。

Ruling: OSS scannerがsynthetic /Users/bob fixtureをruntime dependencyと判定したため、portable rootテストだけ既存のtop-level test/へ移す。global scanner/allowlistは変更しない。OSS検証FAIL→PASS、test数は維持。
