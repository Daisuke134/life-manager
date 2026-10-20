# Life Manager demo・プロモーションの撮影台本

文案/shot list。動画本体は未制作。実画面の撮影は実装できたshotから行い、友人3人の参加を待たない。比較事例・模倣する仕組みはsource-mapを参照する。

## 30秒縦動画（X/Instagram）

| 時間 | 画面/取得元 | 字幕・話す内容 | 真実の条件 |
|---|---|---|---|
| 0–4秒 | 実際の日次メール | 「毎回指示しなくても、今日進めた仕事がメールで届く。」 | 実受信。mockなら画面上に開発イメージと表示 |
| 4–8秒 | `/maritime`のメール登録 | 「入口はメール。目標・予算の入力は必須にしない。」 | 動く登録画面。個人emailはマスク |
| 8–15秒 | 自律cycleの生成物/公開URL | 「Managerが仕事を選び、商品づくりと次の作業を進める。」 | 実際の同tenant occurrence。手操作した部分は隠さない |
| 15–23秒 | 成果物とprovider receipt、費用欄 | 「実行したことと、確認できた売上・費用を分けて報告。」 | 売上未取得は未確認。founder実績を新利用者の売上にしない |
| 23–30秒 | メール+公開URL | 「Life Manager。無料pilotをメールで試す。」 | trialの範囲とリンクが実際に一致 |

hookは一つの成果、構成は入口→行動→証拠→CTA。無音でも分かる大きな字幕。架空の残高、売上ticker、利用者testimonialを足さない。

## 約2分の審査demo（公式指定ではない）

1. 0–15秒: 一文説明。「自ら仕事と優先順位を決め、仕事を継続し、結果を日次メールで報告するManager」。
2. 15–35秒: 新規メール登録と同意、起動。goal/budget/Telegram入力なし。
3. 35–65秒: Maritime上のloaded release、同じrepoの既存factoryが動くこと、生成物/公開結果。
4. 65–90秒: 同じtenant・occurrenceのprovider receipt、確認できた売上/費用、未確認項目。
5. 90–110秒: 実日次メール、次wake、停止入口。公開APIにsecretは出さない。
6. 110–120秒: 実測利用者数、初週の改善一件、試せるURL。利用者がまだ0なら0と確認できた範囲を正直に示し、feedbackを捏造しない。

## 素材と保存

- 実行時は`hyperframes`→該当video skillを読んで既存CLI/rendererを使う。新renderer/音声基盤を作らない。
- source動画・字幕・音声・final MP4は既存content object storeに保存し、本書にはartifact referenceとSHAだけを追加する。
- 30秒9:16、審査版16:9は同じcaptureを再利用する。機微情報のマスクを確認してから書き出す。
- 審査が最小録画/URLで受付可能なら先に提出し、豪華な編集版を待たない。
