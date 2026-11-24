# 整形用LLM 第2弾の2B比較（2026-11-22）

## 仮説

第2弾のデータと学習レシピを保ったままQwen3.5-2Bへ大きくすると、本人の読み上げ50件で整形のCERと過剰な編集が減り、用語、フィラー、言い直し、無変更の保持が改善する。遅延は0.8B 4bitの手元実測値から推定し、実測値とは区別する。

## 条件

### モデルと学習

- 2B：`Qwen/Qwen3.5-2B`、Hugging Face revision `15852e8c16360a2fea060d615a32b45270f8a8fc`。モデルカードの正式名も `Qwen/Qwen3.5-2B`。
- 比較対象：第2弾 `Qwen/Qwen3.5-0.8B`、全体の追加学習、seed 0。facultyに第2弾の重みが無いため、手元の既存MLX 4bit評価結果を使う。入力IDとASRテキストの一致を確認済み。
- 学習データ：`data/text/train.jsonl` 40,000件。実ASRのtwo-pass/no-hintは各9,990件、残り30,010件は従来の加工入力。用語集、held-outの除外、混合確率は第2弾と同じ。
- 設定：1 epoch、全パラメータ、学習率 `2e-5`、cosine、実効batch 32（batch 4 × 累積8）、最大長1,024、gradient checkpointing、250 stepごとに評価・保存、seed 0、dataloader worker 4。
- 2BのTransformers設定：PyTorch 2.13.0+cu129、Transformers 5.23.0、Triton 3.7.1。Qwen3.5の構成に合わせてmultimodal model loaderを使い、gradient checkpointing中は`text_config.use_cache`を切る。これはモデル読み込みとメモリ上の差で、学習データと実効batchは変えない。
- kernel：共有wheelが届くまでの許可に従い、`flash-linear-attention` 0.6.0と`fla-core` 0.6.0をfaculty上の専用仮想環境へ導入。`causal-conv1d`は共有wheel未着のため入れていない。Transformersログでは`causal_conv1d_fn`のみ参照PyTorch実装へfallbackし、FLAのfallback警告は無い。プロジェクト依存には追加しない。
- 共有`causal-conv1d` wheel：`~/voiceime-wheels/README.txt`にはbuild status `FAIL`（exit 2）、wheelなしと記載。自分ではwheelを組み立てず、学習・評価環境にも追加していない。
- 最初のqueue launchは`exec -a`でPythonの実行名を短くし過ぎたため、仮想環境の標準ライブラリを見つけられず起動前に失敗した。`.venv/bin`内の別名に変えて再投入し、30 step確認は正常終了した。失敗ジョブではGPU計算を開始していない。
- 初回の確認：kernel未導入状態の30 step診断は正常終了し、学習時間118.9秒、0.252 step/秒だったが、2つのkernel fallback警告を検知した。GPU使用率を目標にした再試運転は行わず、環境を直して本番を開始した。
- 本番の最初の試行は共有先指定前に導入した別配布の`causal-conv1d 1.7.0+cu.12.6.torch.2.13` wheelを含む環境だったため、162/1,250 stepで停止。250 step checkpoint前で、結果には使わない。出力は削除せず`~/voiceime-work-f2b/outputs/sft2-2b-aborted-nonshared-causalconv/`へ退避し、環境からこのwheelを外した。その後、FLAのみの環境から本番を再開した。

### 評価

- 本人の読み上げ50件：`id`が`dev-user-s`で始まる発話。ASR入力と正解・用語情報をfaculty上の専用作業場所だけで処理し、音声は送らない。
- val 1,000件：`data/tts/val/manifest.jsonl`と、既存のHaas two-pass ASR出力。
- checkpointの選択はdev-userと同じ台本30件を除いた970件、最終評価は1,000件全部。台本の重複は第2弾と同じ扱い。
- 0.8Bと2Bの入力を同じID・同じASRテキストで揃える。整形結果には`apply_output_style`を適用する。
- CERは2026-11-22の`CER_EQUIVALENT_FORMS`に従い、「パーセント」と「%」、「とき」と「時」を同じとみなす。
- 指標：CERと置換・挿入・削除、用語正答率、フィラー残存率、`self_correction`と`no_change`の完全一致率、話していない用語の挿入数。過剰編集の目安としてCERの挿入・削除を別々に報告する。これらは重複しうるため、合算しない。
- 50件は発話単位で対応づけ、CER差（2B−0.8B）の10,000回bootstrap 95%区間と、改善・悪化・同点に基づく両側の正確符号検定を出す。seedは0。
- 実行系の差：0.8Bは手元MLX 4bit、2Bはfaculty Transformers/CUDA bf16・greedy。facultyに0.8BのSFT2重みが無かったための代替比較で、実行系と量子化の差が残る。Transformers評価は一括batch生成のため、MLX単発の遅延とは直接比較しない。

### 現行評価規則で再集計した0.8B基準

以下は以前の実験記録の値を転載せず、今回のmanifestと既存出力へ2026-11-22のCER同値規則で再適用した結果。

| 評価 | 件数 | CER | 用語正答 | 話していない用語の挿入 | フィラー残存 | 言い直し完全一致 | 無変更完全一致 |
| --- | ---: | --- | --- | ---: | --- | --- | --- |
| dev-user 50件 | 50/50 | 151/2,330（6.48%；置換58、挿入58、削除35） | 56/67（83.6%） | 1 | 0/98（0%） | 2/8（25.0%） | 7/8（87.5%） |
| val 1,000件 | 1,000/1,000 | 2,490/47,431（5.25%；置換766、挿入932、削除792） | 1,286/1,427（90.1%） | 42 | 6/1,608（0.37%） | 111/203（54.7%） | 79/99（79.8%） |

最初の評価出力は2Bのdev-user 50件、val 1,000件とも全件が出力長上限へ到達したため採用しない。model generation configのEOS IDは`248044`（`<|endoftext|>`）、tokenizerのEOS IDは`248046`（`<|im_end|>`）で、学習completionにはtokenizer EOSを付加している。推論側の停止条件へ両方を含め、tokenizer EOSを優先する修正を入れて再評価した。設定値は[固定revisionのmodel config](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/config.json)と[tokenizer config](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/tokenizer_config.json)にも記録されている。

## 結果

### 学習

本番のFLAのみのジョブはqueueで正常終了（rc=0）し、1 epoch・1,250 stepを完了した。best checkpointは`checkpoint-1250`、best val lossは0.16205。step 250/500/750/1,000/1,250のval lossはそれぞれ0.2828/0.2286/0.1925/0.1683/0.1620。queueの所要時間は2,323秒。`causal_conv1d_fn`は参照実装へfallbackし、FLAのfallback警告は無かった。

### 品質比較

| 評価 | 系統 | CER | 用語正答 | 話していない用語の挿入 | フィラー残存 | 言い直し完全一致 | 無変更完全一致 |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| dev-user 50件 | 0.8B MLX 4bit | 151/2,330 (6.48%; 58/58/35) | 56/67 (83.6%) | 1 | 0/98 (0%) | 2/8 (25.0%) | 7/8 (87.5%) |
| dev-user 50件 | 2B Transformers | 122/2,330 (5.24%; 37/49/36) | 58/67 (86.6%) | 1 | 0/98 (0%) | 2/8 (25.0%) | 7/8 (87.5%) |
| val 1,000件 | 0.8B MLX 4bit | 2,490/47,431 (5.25%; 766/932/792) | 1,286/1,427 (90.1%) | 42 | 6/1,608 (0.37%) | 111/203 (54.7%) | 79/99 (79.8%) |
| val 1,000件 | 2B Transformers | 2,447/47,431 (5.16%; 618/999/830) | 1,306/1,427 (91.5%) | 45 | 33/1,608 (2.05%) | 108/203 (53.2%) | 83/99 (83.8%) |

CER欄の括弧内は置換/挿入/削除の順。修正後の生成はdev-user 50件すべてEOSで終了し、valは997件がEOS、3件が出力長上限に達した。初回の誤ったEOS条件で作った出力は比較表と結論に使っていない。

### 遅延の見込み

0.8B 4bitの整形時間の手元中央値0.26秒、生成速度212 token/秒から、パラメータ数比2B/0.8B=2.5をそのまま掛けると、2B 4bitは約0.65秒、約84.8 token/秒となる。これは同じ長さ・処理条件を仮定した推測であり、2Bの実測ではない。prefill、メモリ帯域、量子化、実行系の影響はこの単純比例に含まれない。

## 分析

本人50件の対応比較では、2BのCER差は−1.24ポイント、95% bootstrap区間は[−4.50, +1.44]ポイント、正確符号検定は改善9・悪化4・同点37、両側p=0.267だった。区間は0を含み、50件では改善を確証できない。用語正答は56/67から58/67、話していない用語の挿入は1件のまま、フィラー残存は0件のまま、言い直し正答は2/8、無変更保持は7/8で変化なし。2Bでは挿入が58から49へ減った一方、削除は35から36へ1件増えた。

valではCERが5.25%から5.16%へわずかに下がり、置換が766から618へ減ったが、挿入は932から999、削除は792から830へ増えた。用語正答は1,286/1,427から1,306/1,427、無変更保持は79/99から83/99へ上がった。一方、フィラー残存は6/1,608から33/1,608、話していない用語の挿入は42から45へ増え、言い直し正答は111/203から108/203へ下がった。

したがって、この比較では2BのCERが少し低いものの、本人50件で統計的な確証はなく、過剰編集全体が減ったとは言えない。valでも置換の減少が挿入・削除の増加と相殺されており、フィラー残存の悪化も見られた。0.8BはMLX 4bit、2BはTransformers/CUDA bf16のため、モデルサイズ単独の効果としては解釈できない。

## 分かったこと

2Bの追加学習は1 epochでval loss 0.16205まで下がり、指定した学習条件を完了した。最初の評価ではmodel generation configとtokenizerのEOS ID不一致により全件を長さ上限まで生成していた。学習時に正解へ付加したtokenizer EOSも評価停止条件へ含めると、dev-userの全件とvalの997件が自然終了し、初回評価のCER悪化は採用結果ではなかった。

## 次の仮説

次は2Bのvalで増えたフィラー残存（6件から33件）と、話していない用語の挿入（42件から45件）を減らすと、CERを維持しながら編集品質が上がると仮説を置く。フィラーや用語誤挿入の例を増やすデータ変更は別実験として条件を固定し、承認後に比較する。

## 成果物

- 2B評価JSONL：`runs/formatter-2b/sft2-2b-transformers-eosfix-devuser.jsonl`、`runs/formatter-2b/sft2-2b-transformers-eosfix-val.jsonl`
- 0.8B基準JSONL：`runs/formatter-2b/sft2-0.8b-mlx4bit-devuser.jsonl`、`runs/formatter-2b/sft2-0.8b-mlx4bit-val.jsonl`
- 対応発話比較：`runs/formatter-2b/sft2-2b-devuser-paired-cer.jsonl`と`runs/formatter-2b/sft2-2b-devuser-paired-cer.json`
- 集計JSON：`runs/formatter-2b/sft2-0.8b-devuser-report.json`、`runs/formatter-2b/sft2-0.8b-val-report.json`、`runs/formatter-2b/sft2-2b-devuser-report.json`、`runs/formatter-2b/sft2-2b-val-report.json`
