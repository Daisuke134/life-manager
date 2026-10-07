# READMEの主要15エージェント — 実装前readiness仕様

目的はREADME.mdの15 user-facing Product Loopsについて、source・state・runtime・成果/公式readback・経済証拠を区別して監査し、まず既存エージェントを動作させるためのファイル/関数単位TODOを作ること。

今回の範囲はread-only観測、失敗境界のsource診断、private fixture/checkの検証、spec/plan/SSOTの更新。source修正、start/restart/apply、実業務の再送、provider mutation、credential更新、effect fence解除は行わない。safe GUI readのowner preflightは私有evidence receiptだけへ保存し、前提失敗時はgui probeを発行しない。

完了条件は、README15行とcatalog/registry/entrypointをjoin、主機能ごとの最新自然occurrence/loadedまたはconfigured release/health/receipt/costの証拠を収集、sourceで再現できる各failureを関数と期待動作へ絞り、実装者が決め直す箇所と外部必須条件を分けてTODO化し、mainへ保存すること。PID/exit0/fixtureだけを業務完了としない。未確認を0やhealthyにしない。稼働している業務は維持する。

正本READMEは現在15。旧14との差はeBook追加。Money Printer、Local/Cloud、184support jobsは追加の主要Product Loopと数えない。ハーネスMX/HA移行はこのreadiness/repair順序の後続inactive候補へ外す。他業務laneの実行中effectを中断・重複させない。
