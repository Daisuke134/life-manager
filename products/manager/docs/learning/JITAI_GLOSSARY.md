# L004 — JITAIとHeartStepsの介入設計要素

**出典（原著）：** Nahum-Shani et al. (2018) https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/ ; HeartSteps Klasnja et al. https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ ; Murphy lab MRT FAQ https://people.seas.harvard.edu/~samurphy/JITAI_MRT/faq.html

## 介入は「予測」と別物

JITAI (Just-in-Time Adaptive Intervention) は、対象の状態が変わる中で、必要な支援を適切な時点で選ぶ**介入設計**の枠組み。Managerの汎用介入の設計参考にはなるが、HeartStepsの個人宛メッセージや個人情報の収集をManager本体に取り込むという意味ではない。

| 用語（正確な英語） | HeartSteps原著の対応 | Managerの将来対応（設計仮説） |
|---|---|---|
| decision point | 1日5つの活動提案判断時点 | 公的な需要・資源が変わり、許可された行動の再検討が適切な時点 |
| availability | 運転中など通知すべきでない状況を除く条件 | 介入権限、時間、相手の同意、容量、安全性の判定 |
| intervention option | no suggestion / walking suggestion / anti-sedentary suggestion | NO_ACTION、認可された寄付資源の調整、共有環境改善 |
| tailoring variable | 場所・天候など、提案を文脈に合わせる観測変数 | 公開された環境・供給・需給の観測値（個人の非公開情報ではない） |
| decision rule | 利用可能性と状況から取る選択肢を定める規則 | 公開根拠、実行権限、費用、害から候補を選ぶルール |
| proximal outcome | 提案直後30分の歩数 | 介入直後に外部データで確認できる変化 |
| distal outcome | 長期的な健康・活動量などの目標 | 苦しみやリスクの持続的改善（別の検証が必要） |

### 実験内の具体的な割合

HeartStepsの歩行提案部分は、**available（介入可能）な decision point** で `P(no suggestion)=0.4`, `P(walking)=0.3`, `P(anti-sedentary)=0.3` と無作為化した。1日5時点、近接アウトカムは介入後30分の歩数。**unavailable時点は、無作為化で「no suggestion」を割り付けた比較群ではない。**

### 注意

- 現実の人間へ無断で個別のメッセージや行動変容を仕掛けない。
- `NO_ACTION` を候補として残す。予測だけで実行する許可は生じない。
- これから作るMRTコードは実在のHeartSteps参加者データではなく、論文の構造を模した完全に架空のデータ。
