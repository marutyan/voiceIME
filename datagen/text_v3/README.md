# 用語集v2の学習文と初見語評価文

`pipeline.py` は、第1版の文章生成と同じ用途・長さ・フィラー・言い直し・タグの条件を使い、用語集v2向けの学習データと `test-novel` を計画・検査します。第1版の検査処理は `datagen/text/checks.py` から再利用します。

このworktreeでは大きなデータは持たず、用語集、v1用語集、近音語ファイルは呼び出し時にパスで渡します。出力は指定した作業ディレクトリと出力ディレクトリだけに書きます。

## 入力

- `glossary-v2.jsonl`: `surface`、`readings`、`category`、`split` を持つ用語集。`style` が無い場合は表記から検査用の値を補います。
- `glossary-v2-confusables.jsonl`: `surface` と、最大5件の `confusables` 配列を持つ用語集。候補は文字列または `surface` を持つobjectです。
- v1の `glossary.jsonl`: v2とsurfaceを比較し、v1に無いheld-out語を選ぶために使います。
- `glossary-v2-excluded.txt`: 用語として扱わず、文に出る場合もカタカナ表記にする語を1行ずつ並べます。`#`で始まる行は説明として読み飛ばします。

第3弾では、v1のtrain語と、v2で新しく追加された `split: train` かつ `fame` 1・2の語だけに最低出現回数を課します。`fame` 3の語は出現回数を必須にしませんが、train語の参考や無関係な候補として使えます。`test-novel` はv2で新しく追加された `split: held-out` かつ `fame` 1・2の語から選び、trainには使いません。除外語は割当対象と辞書候補から外し、プロンプトでカタカナ表記を指示して英字表記を検査で拒否します。

## 計画

手元のPCで実行します。用語集v2のtrain語は既定で各8文分を計画します（最低5回×1.5倍の予備）。行は第1版と同じく1〜4語を含み、学習用全体の約15%は用語なし、約10%は変更なしです。さらに学習行全体の約15%で、割り当てた語を1つ用語集から外します。近音候補は各正解語につき最大5件です。train用の辞書にはheld-out語を入れません。

```bash
VOICEIME_TEXT_DATA=/path/to/voiceIME/data/text
WORK=/private/tmp/voiceime-text-v3

uv run python datagen/text_v3/pipeline.py plan \
  --glossary-v2 "$VOICEIME_TEXT_DATA/glossary-v2.jsonl" \
  --confusables "$VOICEIME_TEXT_DATA/glossary-v2-confusables.jsonl" \
  --legacy-glossary "$VOICEIME_TEXT_DATA/glossary.jsonl" \
  --excluded-terms "$VOICEIME_TEXT_DATA/glossary-v2-excluded.txt" \
  --work "$WORK" \
  --minimum-repeats 5 \
  --overgeneration 1.5 \
  --novel-count 500
```

`requests-train.jsonl` と `requests-test-novel.jsonl` が教師LLMへの要求です。`specs-*.jsonl` は条件、辞書、用語の割り当てを記録します。初見語は完成時に300〜500文残るよう、既定では最大500件を依頼します。500語はv1にないheld-out語から重複なく選びます。

`--novel-count 500 --overgeneration 1.5` では初見語の仕様を最大750件計画し、build時に検査を通った先頭500件を完成データにします。計画summaryのprompt文字数はtoken数ではありません。生成前にfaculty上の教師tokenizerでprompt token数を見積もり、要求数とともに記録します。生成後のclient出力には、成功した要求ごとの `prompt_tokens` と `completion_tokens` が残ります。

近音候補の完成版が届いたら、更新後のconfusablesを使って次のコマンドを1回実行し、別の作業ディレクトリへ計画を作り直します。既存の計画や出力は上書きしません。

```bash
uv run python datagen/text_v3/pipeline.py plan --glossary-v2 "$VOICEIME_TEXT_DATA/glossary-v2.jsonl" --confusables "$VOICEIME_TEXT_DATA/glossary-v2-confusables.jsonl" --legacy-glossary "$VOICEIME_TEXT_DATA/glossary.jsonl" --excluded-terms "$VOICEIME_TEXT_DATA/glossary-v2-excluded.txt" --work "${WORK}-confusables-final" --minimum-repeats 5 --overgeneration 1.5 --novel-count 500
```

辞書抜け行では、教師プロンプトに正解surfaceの英字表記を渡しません。読みだけを示し、話されたカタカナを正解にも残すか、明白な崩れを読みの範囲で最小限に直すよう指示します。検査では英字surfaceがtargetや辞書へ漏れていないこと、読みがspokenとtargetに残ることを確かめます。

近音語ファイルに行が無い語は候補を作り足しません。計画レポートは候補が無い語数と、辞書内のtrain候補を持つtrain語数を記録します。完成版を使った再計画は上記コマンドで実行します。

## 教師LLMへの送信と再開

vLLM OpenAI互換サーバーへ接続できる環境で実行します。base URLは `http://host:8000/v1` または `http://host:8000` の形で渡します。要求の成功行は完了ごとに出力へ追記し、再実行時は同じidを飛ばします。失敗は最大3回再試行し、最後まで失敗した要求は出力へ書かないため、同じコマンドを再実行すると再試行できます。

```bash
uv run python datagen/text_v3/client.py "$WORK/requests-train.jsonl" "$WORK/outputs-train.jsonl" \
  --base-url http://faculty:8000/v1 --concurrency 8 --retries 3
uv run python datagen/text_v3/client.py "$WORK/requests-test-novel.jsonl" "$WORK/outputs-test-novel.jsonl" \
  --base-url http://faculty:8000/v1 --concurrency 8 --retries 3
```

不足語の追加生成は、後述の `coverage-train.jsonl` を使って計画します。追加要求は元の `outputs-train.jsonl` へ追記するので、成功済みidは重複しません。

## 検査と書き出し

手元のPCで実行します。

```bash
uv run python datagen/text_v3/pipeline.py build \
  --glossary-v2 "$VOICEIME_TEXT_DATA/glossary-v2.jsonl" \
  --legacy-glossary "$VOICEIME_TEXT_DATA/glossary.jsonl" \
  --excluded-terms "$VOICEIME_TEXT_DATA/glossary-v2-excluded.txt" \
  --work "$WORK" \
  --train-outputs "$WORK/outputs-train.jsonl" \
  --novel-outputs "$WORK/outputs-test-novel.jsonl" \
  --out-dir "$WORK/built" \
  --minimum-repeats 5 \
  --novel-count 500
```

`build` は第1版の検査とsplit固有の条件に違反した行を除き、理由別の件数を `build-report.json` に記録します。残ったtrain行で各必須語の出現数を数え、5回以上ある場合だけ `train.jsonl` を完成名で書き出します。条件を満たさない場合は `train.partial.jsonl` と `coverage-train.jsonl` を残して終了コード2を返します。coverageの `accepted` はtargetにsurfaceがある件数、`spoken_assignments` は割り当てた発話件数です。欠けた語だけ追加計画を作り、出力を追記した後に新しい出力先で再度buildします。

`test-novel.jsonl` は行単位の検査に通った候補から `--novel-count` 件を選びます。初見語の重複やtrain語の正解が残る候補は除き、指定件数に届かない場合は部分データを書いて終了コード2を返します。

```bash
uv run python datagen/text_v3/pipeline.py plan \
  --glossary-v2 "$VOICEIME_TEXT_DATA/glossary-v2.jsonl" \
  --confusables "$VOICEIME_TEXT_DATA/glossary-v2-confusables.jsonl" \
  --legacy-glossary "$VOICEIME_TEXT_DATA/glossary.jsonl" \
  --excluded-terms "$VOICEIME_TEXT_DATA/glossary-v2-excluded.txt" \
  --work "$WORK" --minimum-repeats 5 --overgeneration 1.5 \
  --top-up-from "$WORK/coverage-train.jsonl"
```

`test-novel.jsonl` には `terms` と `novel_terms` を持たせます。両方に対象surfaceを記録し、推論時に `novel_terms` を `--exclude-terms` へ渡すことで、用語集に含める場合と除く場合を同じ行で比較できます。train語比率の検査対象は正解の `terms` です。音の近い候補としてglossaryに置かれたtrain語は正解語数に含めません。

### 現在の学習コードとの接続

学習用の各行は `glossary_fixed: true` を持ち、`train/formatter/train.py` は行の `glossary` をそのまま学習入力へ渡します。未指定の既存データは、従来どおり本文からの再選択と辞書の拡張を行います。辞書抜け語は行の辞書に含まれないため、学習時にも戻りません。

## 初回確認と生成量

実際の教師生成を始める前に、偽の小さな用語集と固定出力で割り当て、held-out分離、辞書抜け、近音候補、初見語の検査を確認します。v2の全件を使った計画では、`plan-summary-*.json` に要求数とprompt本文の文字数が出ます。promptのtoken数はサーバーのtokenizerに依存するため、要求ファイルにtoken数を捏造して記録しません。v1の教師出力で実測した平均を使った概算は作業報告に明記します。

### 合成音声を付けるtrain行の選択

11万件を超えるtrain文すべてに音声を付けられない場合は、音声を生成する前に `datagen/tts/select_rows.py` で部分集合を作ります。`--prioritize-terms train` は未選択の用語が多い行を先に選び、同数ならデータ中の出現行数が少ない用語を多く含む行を優先します。用語を新たに増やせなくなった後はseed付きで残りを補い、選択件数を満たします。

たとえばtrainから12,000文を選ぶ場合は、手元のPCで実行します。

```bash
uv run python datagen/tts/select_rows.py --text-dir "$WORK/built" --out "$WORK/tts-train" --count train=12000 --prioritize-terms train --seed 0
```

`input.jsonl` が合成音声の入力、`selected_ids_train.txt` が選択行の一覧です。出力した `input.jsonl` を通常のTTS処理へ渡します。`--prioritize-terms` を付けない既存splitは従来どおりseed付き無作為選択です。

合成音声の作成や6声での読み上げ自体は、このスクリプトの対象外です。`test-novel` はテキスト生成後、評価専用の6声で別途読み上げます。
