# 進捗

| 日付 | 作業 | 状態 | 担当 | メモ |
| --- | --- | --- | --- | --- |
| 2026-11-20 | 計画とPython環境の作成 | 完了 | PM | `docs/PLAN.md` |
| 2026-11-20 | 評価指標モジュール（`src/voiceime/eval/`） | 完了 | Codex | mainへ統合 |
| 2026-11-20 | macOS標準ASRと録音のSwiftコマンド（`tools/apple-speech/`） | 完了 | Antigravity、修正はOpus | DictationTranscriberの空出力を修正、mainへ統合 |
| 2026-11-20 | 用語集と文章データの生成（教師LLM、Colab） | 実行中 | Opus `textgen` | 上限60 CU |
| 2026-11-20 | 合成音声の読み上げ基盤（Colab） | 実行中 | Opus `tts` | 上限30 CU |
| 2026-11-20 | 手元のASR候補の比較基盤 | 実行中 | Opus `asr` | |
| 2026-11-20 | 整形用LLMの推論基盤と学習スクリプト | 完了 | Opus `formatter` | 本番学習の候補はQwen3.5-0.8BとSarashina2.2-1B。記録は`docs/experiments/2026-11-20-formatter-zeroshot.md` |
| 2026-11-20 | 計画の批判的な確認 | 完了 | Fable | 指摘を`docs/PLAN.md`へ反映 |
| 2026-11-20 | アプリ本体（Swift、`app/`） | 実行中 | Antigravity（Neon） | worktree `feat/app`。表示はメニューバーのアイコンだけ |
| 2026-11-20 | 認識エンジン（Python、`src/voiceime/engine/`） | 実行中 | Codex | worktree `feat/engine`。通信形式は`docs/engine-protocol.md` |

## 未決の判断

- 誤認識で漢字になった用語（「CUDA」→「空打」）は、読みとの曖昧一致で用語集から拾えない（ASRの出力で取りこぼしが0%→22%）。ASRを選んだ後、漢字を読みに直して照合する方法を試す。
- 学習に渡す用語集は、held-out-termsを除いたtrain分だけにする。
- フィラーの一覧は、整形の系（`src/voiceime/formatter/rules.py`）と評価（`src/voiceime/eval/`）で別々に持つ。系を評価の定義へ合わせ込まないため。

## モデル選定（2026-11-20の調査）

- 教師LLM：Gemma 4 26B-A4B-it（Apache 2.0）。文章データの生成で使用中。PLaMoはライセンス上、出力で学習したモデルも派生物となるため教師に使わない。
- 整形LLMの本番学習の候補：Qwen3.5-0.8B（速度の基準）、LFM2.5-1.2B-JP-202606（日本語に調整済み、年間売上1,000万ドル以上の組織は商用不可）、Gemma 4 E2B-it（日本語の指示追従が最良、速度は要実測）。
- ASRの候補の追加測定：Qwen3-ASR 0.6B/1.7B、Granite Speech 5.0 2B、Nemotron 3.5 ASR streaming 0.6B、Haas-ja-v1.0（2026-10-30公開、Parakeetと同じ構造）。

## OpenHinoVoice（MIT）から取り入れる点

- ASR候補にHaas-ja-v1.0をspeech.cpp（Metal、GGUF）で加える。
- 用語集を3段で使う：ASRへのkeyword（`表記=読み`）、整形LLMへの参考情報、明示した別表記だけの確定置換。
- 整形の出力検査（入力に対する長さ比、前置きやコードブロックの拒否）。失敗したら整形前の文を使う。
- アプリでは、録音中に無音（約600ms）で区切って先に認識し、キーを離した後は最後の区間だけを処理する。貼り付け前に宛先（アプリとフォーカスのある部品）を照合し、クリップボードは全typeを写して戻す。

## ASRの選定（2026-11-20、dev-sayとpilot-ttsでの暫定比較）

- 採用：Haas-ja-v1.0 Q8_0（speech.cpp、Metal）＋用語集のkeyword。10秒の発話で0.11秒、読み揃えCERはWhisper turbo＋用語集に近く（dev-say 14.0、pilot 9.3）、用語の英字表記一致は84%で全候補中最高。記録は`docs/experiments/2026-11-20-asr-newmodels.md`。
- 精度だけならQwen3-ASR 1.7B 8bit＋用語集が最良だが0.81秒かかる。比較の基準として残す。
- 遅延の目安は、ASR 0.1秒＋整形0.2〜0.4秒になる。
- 次に測ること：用語集を500語渡す条件での誤挿入、`keywords_guard`と`keywords_alpha`の調整、test-synthと本人の録音での精度。
- ディスクの空きを確保するため、比較で外した重み（kotoba-whisper、WhisperKit、large-v3の4bit）と、学習の配管確認用の重みを削除した（再作成の手順は各実験記録にある）。

## 2026-11-21 01:40時点

- 合成音声の本番：train 9,990件（31.9時間）、val 1,000件、test-synth 1,000件。約14.2 CU。A100へ移して約2時間40分で完了。
- 本人の録音（dev-user）100件を収録。自由発話50件と台本からずれた8件の正解文は、本人の確認待ち（`data/dev-user/review.md`）。
- 整形LLMの第1弾（Qwen3.5-0.8Bの全パラメータ学習、入力はHaasの癖をまねた加工文）：
  - val（合成、200件）：CER 1.8%、用語97.8%、言い直し72%。
  - dev-userの読み上げ50件（Haas＋two-passの実出力を入力）：CER 31.0%（整形なし）→ 8.8%、用語77.6%、フィラー残存1.0%、言い直し12.5%。整形は0.23秒、全体で中央値0.46秒。
  - 言い直しが本人の声で低いのは、本物のHaasがフィラーを多く残す（本人の声で82%）ことと加工が合っていないためと推測。第2弾で、合成音声をHaasで認識した実出力を学習入力にする。
- LFM2.5-1.2B-JPの第1弾を学習中。その後Gemma 4 E2B。
- 合成音声の運転スクリプト（`datagen/tts/colab_run.sh`）は共通の`colab` Skillより前に作られたため独自の安全処理を持つ。次にColabで動かすスクリプトは`colab` Skillの`colab_lib.sh`を使う。

## 2026-11-21 07:30時点：整形LLMの第2弾

- 第2弾（Qwen3.5-0.8B、全パラメータ、入力は合成音声のHaas two-passの実出力＋実測の癖に合わせた加工）。記録は`docs/experiments/2026-11-21-formatter-sft2.md`。
  - val（Haasの実出力1,000件）：CER 8.51%→5.37%、用語83.5%→90.1%、言い直し39%→53%。
  - dev-userの読み上げ50件：CER 8.75%→7.34%（差の95%区間 −3.04〜+0.09）、用語77.6%→83.6%、フィラー0.0%。言い直しは8件しかなく判断できない。整形0.21秒。
- 第1弾の比較（dev-user読み上げ50件）：Qwen 8.75%、LFM2.5 9.22%（整形0.34秒）、Gemma 4 E2B 9.40%（整形0.41秒、用語80.6%）。LFMは外す。
- 本人の自由発話50件では、第2弾が2件で生成が崩れた（「、」や「その、」の繰り返し）。出力の検査が句読点の連続と語句の繰り返しを捉えず、そのまま通っていた。検査と生成の打ち切りを追加中。
- 用語集に無い語を、音の近い無関係な用語に置き換える誤りがある（「ハンガリアマッチング」→「HellaSwag」）。本人用の用語集と、学習で音の近い無関係な語を混ぜることで対策する。
- エンジンは引数なしで起動すると、Haas Q8_0、第2弾の整形LLM、学習用と本人用の用語集、`~/Library/Application Support/voiceIME/history.jsonl`を使う。
