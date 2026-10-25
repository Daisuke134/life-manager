> Historical review, before fix pass. Both Blocking findings below were reproduced and fixed; see [final verification](E16_RECOVERY_HARDENING_20261022.md). This is not a second review or an unresolved-finding claim.

# E16 recovery whole-change review — 2026-10-22

**2 findings (2 Blocking / 0 Nit / 0 Pre-existing).** 修正すべき点は以下の2件。両方とも現在のsourceで再現した機能上の問題であり、本番未実装の要求ではない。

対象: `/workspace/manager-execution`、baseline `764bf220af4132f084bb3f6f698cc08f19e536ee` から HEAD `c8c27e57d4e8f51f8e50de4bbf118ea182128a4e` と作業treeの全変更。commits `7862b9472` / `1b8201d9d` / `c8c27e57d`、未追跡portable probe/tests/verification docs、仕様・handoff・plan編集を含む。sourceは読取専用、作成物は本review artifactのみ。AGENTS.md / REVIEW.md / 製品仕様 / atomic plan / progress ledgerを読んだ。他reviewerの結論は読んでいない。

## 1. Blocking — UNKNOWN先頭への固定で後続recoveryが永久に走査されない

**Bug class: recovery queue starvation / head-of-line blocking.**

- `products/manager/manager_core/reconcile.py:75`、`:76`: `reconcile_pending_owned` は毎回 `pending_records()` の先頭100件のみ取得する。`after_key` APIを使わず、wakeをまたぐcursorもない。先頭100件がUNKNOWNで残ると101件目以降には永遠に到達しない。
- `products/manager/manager_core/owned_cycle.py:212`、`:216`: deliveryにも同型の問題がある。通常運転では最初の未確認deliveryでreturnするため、2件目さえ観測されない。STOPPED時にはUNKNOWNをcontinueするが、先頭100件から次batchへ進まない点は同じ。
- `products/manager/manager_core/owned_cycle.py:275`、`:276`（public helperは`:258`、`:259`）: 未解決occurrenceが1件でもある間、delivery recoveryにも進まない。dispatch禁止は正しいが、後続の読取recoveryまで永久に妨げている。

**再現:** 既存 `CycleAcceptanceTests.prepare` fixtureと `OwnedEffectJournal.reserve` を使い、`test_pending_records_are_bounded_ordered_and_paginated` と同じ方法で102件の異なるcandidate-sourceを予約する。`read_occurrence` がUNKNOWN (`None`) を返す状態で `reconcile_pending_owned` を3回呼んだ結果:

```json
{"ticks":3,"total_reads":300,"unique_read_keys":100,"tail_read":[false,false]}
```

同じfixtureで2件の保存済みPRESENT rowを用意し、先頭の `DeliveryObservation` をUNKNOWN、後続をVERIFIEDにした読取fixtureで `_recover_owned_deliveries` を3回呼んだ結果:

```json
{"total_reads":3,"unique_read_keys":1,"second_read":false,"statuses":["UNKNOWN","UNKNOWN","UNKNOWN"],"second_saved":null}
```

後者のPRESENT rowはprivate journal APIで構成したsynthetic fixtureであり、公式provider証明の主張ではない。loop選択の再現に限る。

**影響:** 修正前の複数candidateから持ち越した予約や複数のPRESENT履歴を回収する際、一部のUNKNOWNが永続するだけで、他の照合可能occurrence / deliveryが読まれない。PATCH-01/04の「保存済み過去intentを読取照合する」要件が満たされない。UNKNOWNそのものを解消したりdispatchを許可したりせず、未解決・未走査全体によるwrite禁止を維持したまま、後続読取に進む必要がある。occurrenceとdeliveryは同じbug classとして数えた。

## 2. Blocking — 有効なpacketでも時刻が1秒進むとpublic dispatch helperが拒否する

`products/manager/manager_core/owned_cycle.py:232`、`:233`。

`prepare_owned_change(..., now)` は `plan_release(..., now)` により `created_at` / `expires_at` / `packet_sha256` を毎回生成する。ここでpacket全体を比較するため、元packetのlease内でscope・context・assessment・targetが完全に同じでも、prepare時とdispatch時の `now` が違うだけでNO_ACTIONになる。public helperの契約には「生成時刻とdispatch時刻は完全同一でなければならない」という条件はなく、既存 `admit_release` はこのpacketを正しく許可する。

**再現:**

```python
packet = prepare_owned_change(host.context, host.assessment, host.scope, NOW).packet
later = NOW + timedelta(seconds=1)
admitted = admit_release(packet, context, host.manifest(), packet['candidate'], later)
result = dispatch_owned_once(store, host, packet, later)
```

既存local-Git fixture、未予約、scope未変更、target未変更で実測:

```json
{"admission":"ADMITTED_MANAGER_PREFIX_ONLY","helper":{"status":"NO_ACTION","writes":0,"effect_key":"11118a1703c061bf8764a176993a411bc2c5d1e28b14c6e6af428ea5f402022a","reason":"ORIGINAL_PUBLISHER_GATES_REQUIRED"},"send_count":0,"reserved":false}
```

**影響:** durable runtimeへpacketを渡してから初回送信stepが遅れた場合や、予約前の再開で現在時刻を正しく更新した場合、まだ有効なintentが一切送信されない。現在のprobeはJSONに保存した同じ `NOW` を全stepで使うのでこの問題を検出しない。scope/assessmentのfresh再検証と、元packetの期限・binding admissionを両立させる必要がある。時計を固定して通すことは解決にならない。

## 実施した確認と範囲

- Git root / branch / common Git directory / canonical originを確認。実行環境のnetwork policyはunrestricted/enforced、configured secrets/outbound identitiesなし。外部provider操作なし。
- `python -m unittest discover -s tests -p 'test_owned_*.py' -q`: **33 tests OK**（portable current-backend subprocess probeを含む）。
- `python -m unittest discover -s tests -p 'test_digital_cycle_acceptance.py' -q`: **10 tests OK**。
- `python scripts/check_boundaries.py`: PASS。
- `python scripts/make_roadmap.py --check`: PASS、113 tasks / task JSON untouched。
- `git diff --check`: PASS。
- 上記2件のfocused reproductionsをsource外temporary directoryで実行。
- 新しいexact-parent immutable bundle validation、typed deliveryのP0表示、lag/hash-onlyでrollbackしない分岐、rollback直前expected commit照合、packet/parent保存、owner lockとscope/stop gate、checkpoint結果がdispatch permissionを含まない点を確認した。
- portable probeのsource snapshot、child isolation、DBOS pin/portable serialization、core dependency非追加、source-state拒否、文書のproduction未達表示を確認した。DBOS16ケースは記録されたP0 receiptとして読み、今回DBOS実行を再度行ったとは主張しない。

## 判断を差し控えた事項

- PATCH-05/06の本番bridge・credentials delivery・volume/backup/stale restore・実hosting費用・live canaryの合否。実装/実証未達が明示されており、今回のsource publicationへ架空の本番完了を求めない。exit2のnegative preflightは成功canaryと認定しない。
- PATCH-07〜12の未実装publication/assets/benchmark成果。今回のdiffはその実装や外部公開を主張しておらず、既存調査を再監査する別taskには広げない。
- 本番採用としてのDBOSの優劣、長期wait/運用費/復旧code削減。今回の2秒・P0比較では判定不能という文書の限界を維持する。
- 既存 `OwnedEffectJournal` / `OwnedOccurrenceEvidence` のhost-owned APIだけを直接呼べる攻撃者に本番権限があるとは推定しない。現行sandbox guardを将来のproduction authenticationとして認定しない。
