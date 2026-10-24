# 動機づけ面接から何を再利用するか — 追加の一次資料調査

2026-10-24 UTC。既存の[追加評価資産note](2026-10-23-additional-behavior-evaluation-reuse.md)へ加える有限調査。21件分を要求した3検索から候補を探し、以下の一次資料を選択読取した。21件の全文精読や網羅的systematic reviewとはしない。Firecrawlの先行credit制限を繰り返さず、接続済みExaと公開著者資料・GitHub APIを使った。検索使用料はUNKNOWN。資料取得・静的解析で、新provider推論や人への配信はない。

## 1. Intrinsic AI: 短期の動機と行動の違いが分かる研究

Conrado Eiroa-Solans / Michael Inzlicht、[原著 DOI10.1016/j.chbr.2025.100882](https://doi.org/10.1016/j.chbr.2025.100882)。[著者の掲載ページ](https://michaelinzlicht.com/publications/articles-chapters/tag/prosociality)から[著者配布PDF](https://michael-inzlicht.squarespace.com/s/Testing-an-AI-powered-motivational-interviewing-system.pdf)を取得。8ページ、2,049,169 bytes、SHA-256 `07d1efa777de6fe18dd96a1c28b0b13d2dcb41dd7f79beade693e2c799781f41`。本文Methods/Results/Limitations/Data availabilityを読んだ。保存本文のAvailable onlineは2025-11-19、検索metadataは2025-11-20、巻表示は21 (2026)。日付の出典差を保持する。別研究として二重計上しない。

- Methods §7.2の実装はGPT-4へのprompt engineering。8段階のMI scaffold、一度に一質問、therapist-in-the-loopでsystem prompt/guardrailsを調整する。要旨の「tuned」を重み学習と断定しない。active controlは同じGPT-4との自由対話、sessionは15分。
- §7.1ではbaseline315、介入時244、follow-up212、除外後の解析234/203と記載。要旨のN=237とは一致しない。原因未解決のまま併記し、237を全解析の分母へ使わない。人数だけからrandomization/全ITT分母を補完しない。
- §8.1の直後のMI ruler差はimportance b=0.60、confidence b=0.53、readiness b=0.73。24時間後は有意差を確認せず、trait motivationや§8.2のcharity effort課題でも改善を確認しなかった。非有意を同等性や「効果が絶対にない」と読まない。著者も小さい効果の不在を示す検出力は不十分とする。
- 行動課題は64回の自己/charity向け努力選択で、64人ではない。実生活での継続的支援・苦しみ低減・臨床効果を測ったものではない。広いprosocial目標と限定した課題の不一致も著者の限界にある。
- 本文はCC BY4。data/codeは[OSF c6kvq](https://osf.io/c6kvq/)、preregistrationは[AsPredicted](https://aspredicted.org/5t4g-d4q6.pdf)を案内するが、今回のOSF node/files APIは401、prereg PDFは403。案内を見たことと、実package/license/事前登録内容の確認・再現を分ける。公開本文のlicenseを未取得data/codeへ継承しない。

**Managerへの判断:** active control、直後/追跡、自己報告/行動課題、endpointに対応した目標を借りる。今は研究参照と独自解説に使用し、未取得dataを新training corpusにしない。反復介入なら効くという仮説も未実証のまま残す。

## 2. CAMI: 再発明しなくてよい判断の分解

Yizhe Yangらの[ACL2025論文](https://aclanthology.org/2025.acl-long.1024/)の要旨と[著者repo](https://github.com/IzzetYoung/CAMI)のREADME/選択sourceを確認。repo READMEの短い著者列と、公式論文の全著者列を同一と仮定しない。論文全文・全repo監査・動作再現ではない。

固定commit `831954a206865eed6ffadd140c3bb34316d4b24a`。全tree一覧を取得し、READMEと次の4 Python filesを取得、AST parseした。import・API呼出し・retriever download・client profileの読取はしていない。

| source | SHA-256 | 静的に確認した役割 |
|---|---|---|
| [generate.py](https://github.com/IzzetYoung/CAMI/blob/831954a206865eed6ffadd140c3bb34316d4b24a/generate.py) | `831403bd7bbf3aee7e5a4f42bf65fc340b2e8f2a35832695cffe06ea61462ff8` | profileごとにcounselor/client/envを構成し、対話simulationを繰り返す |
| [agents/counselor.py](https://github.com/IzzetYoung/CAMI/blob/831954a206865eed6ffadd140c3bb34316d4b24a/agents/counselor.py) | `1fa1153b0e34f75fc2836c0cbf27bd364fed9890a615ead5f18d4d37f077eec2` | infer_state / explore / select_strategy / generate / refine / replyを分離。OpenAI API clientとbackoffを含む |
| [agents/client.py](https://github.com/IzzetYoung/CAMI/blob/831954a206865eed6ffadd140c3bb34316d4b24a/agents/client.py) | `f3242902121f0dbbf3508aeef62e6e83ed85d60bd157e596b6d55154836a9f08` | simulated client。人の実際の反応のgoldではない |
| [agents/env.py](https://github.com/IzzetYoung/CAMI/blob/831954a206865eed6ffadd140c3bb34316d4b24a/agents/env.py) | `8b8e868fadaa8ae268bb8b042eb27cc59b331552607375d4cb949bf1a53b1682` | bounded-turnの交互対話とheuristic終了。保存の存在や終了文字列は人の行動完了ではない |

READMEのSTARはstate inference→topic exploration→strategy selection→response generation/ranking。主にprecontemplation/contemplation/preparationを扱い、simulated clientsとexpert/automatic評価を使う。現実のmaintenanceや苦しみの軽減を証明したとはしない。tree一覧には明示LICENSE fileを確認できず、sourceの商用コピー/配布許諾は未確認。

**Managerへの判断:** まず設計参照。自作の万能trainerや無制限の新multi-agent runtimeを増やさない。判断分解や評価項目は学べるが、codeをコピーした・稼働中・独自modelへ統合済みとは言わない。既存の資源上限/UNKNOWN/STOP/独立観測契約を捨てて上流driverをそのまま実行しない。

## 3. MI-TAGS: 会話の質を測る候補

Ben Cohen / Moreah Zisquit / Stav Yosef / Doron Friedman / Kfir Barの[ACL2024論文ページ](https://aclanthology.org/2024.lrec-main.1017/)と[著者repo README](https://github.com/Advanced-Reality-Lab/MI-TAGS)を確認。論文要旨は242のdemonstration transcripts、MITI4.2 therapist codes/global scores、CLEAR1.0 client tagsを説明する。実患者242人の改善RCTではない。

repoはsample CSVとfull datasetのaccess-requestを案内する。full package・rights・人物/session split・scorerは今回未確認。単なるMITI分類を持続的行動や便益のgoldへ置換しない。**Managerへの判断:** 会話品質の部分eval候補。用語/設計を学ぶ段階で、full dataの使用や新たなアクセス申請は行わない。

## 4. 再利用の順序と書籍への接続

既存Costello再現は「意見の本人報告」、新numeric LoRAは「その数値予測」、Intrinsic AIは「動機と行動の乖離」、CAMI/MI-TAGSは「対話設計と品質proxy」を担当する。異なるendpointを一つの順位や「説得力」に合算しない。

1. 今回の資料から[独自の無料実習章](../articles/2026-10-24-motivation-is-not-behavior-ja.md)を書く。本文の転載・未取得datasetの再配布はしない。
2. [既存numeric計画](../plans/2026-10-24-costello-numeric-forecast.md)の別G7比較を完了し、改善しなければ陰性結果を公開する。会話介入modelの性能へ読み替えない。
3. U004の既存v2 protocolで、本人が選ぶ具体的行動、行動機会・観測方法・比較・追跡・負担/害を対応付ける。今回の論文だけで実人数/期間を決めない。
4. 会話品質evalが必要になった用途だけ、各資料のrights/split/費用を確認して部分採用する。全benchmarkがそろうまで公開研究再現を止めず、未成立dataを架空採用しない。

これはネット上の全選択肢を調べ終えたという宣言ではない。未取得artifactと未解決分母を明記し、設計や結論を変える追加証拠が出れば更新する。
