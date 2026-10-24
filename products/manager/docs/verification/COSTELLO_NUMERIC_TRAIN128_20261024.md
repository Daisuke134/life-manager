# Costello numeric train128 — actual training and frozen adapter

2026-10-24 UTC。数値自己報告の予測を学ぶ一回のprivate SFTの実結果。新しい説得文の生成、本人への介入、便益、モデル採用の証明ではない。[固定設計と計画](../plans/2026-10-24-costello-numeric-forecast.md)を参照。

## 実行前に固定したもの

- Source: `4fa063bc7f30d2b67d03a7852ddfb7ef8588ddc4`。
- Design SHA-256: `f9010431cc7dd4a2edfda9db901fb7265986c032a125ad0f725f291f0180d6ca`。入力は事前confidenceと割付条件だけ。旧final16は読取・再利用・再採点していない。
- Native config SHA-256: `60faf5e2cf8bf9ce3adefae8470efe956d94c40159ed872056901229392f3230`。別のroot admission SHA-256: `1a98cee09634b9d664a343d8508de4ad443eaa62cc5e080101148df30b9006ad`。
- Qwen3-0.6B、標準PEFT/TRL、rank8、q_proj/v_proj、alpha8、dropout0、seed42、batch1/accum4、1epoch、learning rate0.0002。学習128件。新trainerを作らず既存completion mask/save検証を再利用した。
- focused15 testsのRED/GREEN、fresh whole-source reviewのfinding0、local1198 tests/skip5を確認。実sourceの[公式CI](https://github.com/Daisuke134/life-manager/actions/runs/40093904273)は1172 tests/skip6で成功。公式環境の任意NumPy/SciPy不足により27件のmoduleが一つのskipとなり、localとの差26件がある。新規15件は公式でも実行した。
- stdlib canaryで起動shell終了後も監視が継続し、native子のwait/reapとdurable terminalが残ることを確認した。native学習は900秒・own-group sampled RSS5GiB上限、一attemptだけを別受入した。全A09の評価実行条件を一括受入したものではない。

## 観測した終了

| 項目 | 実測 |
|---|---|
| native monitor開始→終了 | 2026-10-24 12:31:55.037523→12:36:05.829128 UTC |
| elapsed / sampled peak own-group RSS | 250.792秒 / 2,358,620,160 bytes |
| native status / return code | EXITED_SUCCESS / 0 |
| wait / PID / process group | reaped=true / absent=true / remaining=[] |
| training receipt | COMPLETED、128 rows、global_step32、optimizer opportunities32 |
| finite gradient実検査 | 32回、すべてfinite |
| trainable parameters / saved tensors | 1,146,880 / 112 |
| retry / resume / extension | 0 / 0 / 0 |

native receipt SHA-256は`d61b9deb5ae3230d326b58ff7e727a17a02f0fde1d48bf7132beabcff3d5cffb`。monitor terminal SHA-256は`ef0ce2206f18907aa2d952dcf105cd4b49ad6e71cb5d95bc9610304063875fae`、戻り後のoperator terminalは`6b4efc658a26e4be84813f19068924a2fd29532629125de84741e4acf86f042f`。operator shim自身のreapはNOT_CLAIMED。旧SafetyBenchのouter-reap未成立を修正・上書きしたものではない。

## 評価前の保存・独立検査

rootは12:36:51.840301 UTCに、単一artifactの11ファイルのbytes/SHAとprivate ACLを照合して固定した。adapter safetensorsは4,602,248 bytes、SHA-256 `1bc93b7a3c99d4d9b9a01e4d1f95a48797e134a432652d268316fb92b02f1862`。model scoreによる選別はない。

別の検査では保存adapterだけを開き、112 tensors / 1,146,880 elementsがすべてFP32・finite、56個のLoRA B tensorsが標準zero-B初期値とは異なることを確認した。base/tokenizer loadやmodel forwardはしていない。native内の実初期cloneとの比較は112 tensorsの変化を報告するが、この独立検査で全112個の初期差分を再構築したとはしない。

生データ、weights、実行設定、署名でないoperator assertions、ログと完全inventoryはGit外のprivate実行記録に保持する。hashは一致確認であり、第三者や人間による承認の暗号学的証明ではない。

## まだ判定していないこと

新base/adapterの予測・評価はNOT_RUN、性能改善はUNKNOWN、採用はHOLD。費用はUNKNOWNで、新規有料provider・計算契約は追加していない。U004のparticipants0/interventions0、tasks.jsonの85 done /18 todo /10 skippedは変えない。

次は固定artifactに対する別G7評価。generation callerとtests、実sourceのreview/CI、時間/RAM・終了監視と別freezeを先に成立させ、同じ全割付分母でbase/adapter/統計baselineを比較する。無改善ならこの候補をHOLDとして閉じ、同じevaluationへretuneしない。
