# Task 6 実施報告

## 状態

DONE。Calendar binding の安全な復旧と定期 Web travel の ACTIVE account gate を実装し、指定 feature branch へ push した。

## 変更

- `resolveActiveWebCalendar(uid, opts)` を追加。NULL-Telegram row の保存済み provider/account を読み、verified uid に対する account 固定の ACTIVE readback 後、marker が不変であることを再読して返す。
- GET status は保存済み binding と exact ACTIVE readback だけで connected を返す。GET は読み取り専用。
- POST start は callback 中断後、同一 uid の exact ACTIVE account が一意な場合のみ marker を条件付き保存し、representation と GET readback 後に connected を返す。ACTIVE account が曖昧なら binding も OAuth start も行わない。既存の selected disabled account の再開も維持した。
- `travelUserOnce` は `lm_<uuid>` の NULL-Telegram row で shared Web gate を `fillTravel` の直前に実行する。ACTIVE 未確認・marker rebound・Telegram binding 欄不在なら Calendar 処理を呼ばず、Telegram user の経路は従来どおり。
- Web uid/account は request body から使わず、認証済み scope と provider owner readback を使う。

## 検証

- TDD RED: `node --test lib/web-calendar.test.js lib/web-travel.test.js test/scheduler.test.js` で status、recovery、ambiguity、scheduler gate の新規回帰ケースが実装前に失敗することを確認。
- focused GREEN: 同じコマンドで 37/37 PASS。
- `node --check` を `web-calendar.js`、`web-calendar.test.js`、`scheduler.js`、`scheduler.test.js` に実施。
- `git diff --check` と staged diff check は PASS。
- この worktree に依存がなかったため `npm ci --ignore-scripts --no-audit --no-fund` を実行した。lockfile の変更はない。指定外の full package suite は実行していない。

## Git

- branch: `feat/lm-web-first-travel-20261006`
- implementation commit: `dc1a1c99d7d965d53b25850a7027902881f8dc1a` (`fix(life-manager): recover web calendar binding safely`)
- remote readback: `git ls-remote origin refs/heads/feat/lm-web-first-travel-20261006` が同じ SHA を返した。
- commit 後の worktree は clean。

## 制限

本番/provider state は変更していない。今回の受け入れ範囲は source と focused test までで、本番 release・natural run・公式 readback は含めていない。
