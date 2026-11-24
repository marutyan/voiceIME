# facultyでのTTS生成準備

## 目的

Colabで行ったTTS生成をfacultyのH100へ移す。Colabと同じTTSコード、依存パッケージ、声、入力行ごとの割り当てを使い、GPU実行の前後に使用状況を確認する。

## 環境

facultyの作業場所は ~/voiceime-work-tts/。datagen/tts/faculty_setup.sh が、setup_colab.sh と同じIrodori-TTS commit（f01c08cd40c0afa62a862439a5de12f6dcf62054）、Qwen TTS 0.1.1、PyTorch 2.11.0（CUDA 12.8 wheel）をuvで用意する。Irodori環境はIrodoriのlockfileどおりPyTorch 2.10.0+cu128、Qwen環境は2.11.0+cu128。モデル重みとuv/Hugging Faceのキャッシュもこの作業場所に置き、ダウンロード時に解決した各Hugging Face revisionをmodel-revisions.tsvへ記録する。

Qwen TTSの話者埋め込みはSoX実行ファイルを必要とする。facultyにSoXが無かったため、SoX 14.4.2を公式配布元のソースからビルドし、~/voiceime-work-tts/tools/sox/に置く。システム全体にはインストールしない。

今回facultyで解決したmodel revision:

- Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign: 5ecdb67327fd37bb2e042aab12ff7391903235d3
- Qwen/Qwen3-TTS-12Hz-1.7B-Base: fd4b254389122332181a7c3db7f27e918eec64e3
- Aratako/Irodori-TTS-v4.1-Small: 2b28324dc263ed5e6638b3cf3dd94c82ead07b4b
- Aratako/Semantic-DACVAE-Japanese-32dim: 47376ee24834d7a05a48ebabfe3cde29b3c5e214

参照音声は手元のdata/pilot-tts/voices/にある30本をfacultyのvoices/へコピーする。新たに声を設計すると音声が変わるため、既存の参照音声をそのまま使う。SoXソースはSourceForgeの14.4.2配布物で、SHA256はb45f598643ffbd8e363ff24d61166ccec4836fea6d3888881b8df53e3bb55f6c。

## facultyへの配置と環境準備

以下は手元のMacでリポジトリのルートから実行する。

    ssh -o ControlMaster=no -o ControlPath=none faculty 'mkdir -p ~/voiceime-work-tts/datagen/tts ~/voiceime-work-tts/voices ~/voiceime-work-tts/inputs ~/voiceime-work-tts/outputs'
    scp -O -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10 datagen/tts/faculty_setup.sh datagen/tts/faculty_run.sh datagen/tts/synthesize.py datagen/tts/make_voices.py datagen/tts/voices.json faculty:voiceime-work-tts/datagen/tts/
    scp -O -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10 data/pilot-tts/voices/*.wav faculty:voiceime-work-tts/voices/
    head -n 20 data/text/pilot.jsonl | ssh -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10 faculty 'cat > ~/voiceime-work-tts/inputs/pilot-20.jsonl'

本番用の入力は、手元のMacから同じ作業場所のinputs/へ送る。

    scp -O -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10 data/text/<入力>.jsonl faculty:voiceime-work-tts/inputs/

セットアップはfacultyでバックグラウンド実行する。

    cd ~/voiceime-work-tts
    nohup bash datagen/tts/faculty_setup.sh > setup.log 2>&1 < /dev/null &

手元から状態を見るときは、接続に時間上限を付ける。

    timeout 20 ssh -o ControlMaster=no -o ControlPath=none faculty 'tail -n 30 ~/voiceime-work-tts/setup.log'

## 生成と再開

faculty上で `faculty_run.sh <入力JSONL> <出力先> <CUDA_VISIBLE_DEVICES> <GPUごとのworker数> [既定split]` を実行する。第3引数はGPU番号のカンマ区切りで、GPUを複数指定すると行を分割する。毎回 `nvidia-smi` で空きGPUを確認し、その番号を指定する。

    cd ~/voiceime-work-tts
    nvidia-smi
    BATCH_SIZE=32 nohup bash datagen/tts/faculty_run.sh inputs/train.jsonl outputs/train 3 1 > outputs/train.log 2>&1 < /dev/null &

入力、出力、参照音声は `~/voiceime-work-tts/` の中に限る。スクリプトも生成直前に `nvidia-smi` を実行し、選択GPUに計算プロセス、512MiBを超える使用メモリ、またはGPU負荷があれば中止する。空きGPUが複数ある場合は `1,3` のように指定できる。既定batch sizeは16。200件で試した条件では `BATCH_SIZE=32` が最速だった。

同じ入力、worker数、batch size、seedなら同じ出力先で再実行すると、各workerのparts/から続ける。これらの条件を変える速度比較では、別の出力先を使う。生成後に全workerの記録をまとめ、manifestと速度（wall time、音声時間、RTF）を出力する。途中終了しても生成済みのWAVと記録は残る。

## 手元への持ち帰り

以下は手元のMacでリポジトリのルートから実行する。<名前>は既存データを上書きしない新しい名前にする。

    mkdir -p data/tts/<名前>
    rsync -av --progress -e 'ssh -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10' faculty:voiceime-work-tts/outputs/<名前>/ data/tts/<名前>/

## 2026-11-21の確認結果と制約

- `data/text/pilot.jsonl` は200件で、すべて `test-synth`。先頭20件で動作確認し、速度条件は同じ200件で比較した。
- 先頭20件は92秒、音声247.1秒、RTF 0.372。既存 `data/tts/test-synth/` のmanifestとspeaker、spoken_text、speed、intonationが全件一致。WAVは20件すべて16kHz、モノラル、16bit PCM。
- 200件・seed 0のbatch size 16/24/32の各出力を既存manifestと比較し、speaker、spoken_text、source、TTS model ID、speed、intonationが全件一致。3条件ともWAVは200件すべて16kHz、モノラル、16bit PCM。失敗・未生成は0件。
- 速度比較（同じ200件、GPUごと1 worker）：

  | batch size | 壁時計時間 | 出力音声 | 全体RTF | Irodori RTF | Qwen RTF |
  | ---: | ---: | ---: | ---: | ---: | ---: |
  | 16 | 302秒 | 2,584.3秒 | 0.117 | 0.030 | 0.871 |
  | 24 | 339秒 | 2,578.4秒 | 0.131 | 0.029 | 1.003 |
  | 32 | 232秒 | 2,582.7秒 | 0.090 | 0.028 | 0.667 |

  batch size 32が最速で、16より約23%、24より約32%短かった。100件の試験ではQwen割当が13件しかなく、batch size 16/32とも1 batchだったため差が出なかった。200件ではQwen割当29件となり、batch size 32の差を測れた。別の100件試験では1 GPUに2 workerを載せると235秒かかり、1 workerの211秒より約11%遅かった。

- batch size 16、1 workerで同じ出力先を再実行し、partsの87件（ja）と13件（multi）がすべて完了済みとして再生成を飛ばすことを確認した。再開確認の壁時計時間は1秒。
- TTS試験は空きを確認したGPU1とGPU3で実施し、各実行後にTTSプロセスがなく選択GPUのメモリが0MiBになったことを確認した。GPU1のVLLM、GPU2のQwen3-ASR学習、試験後にGPU3で始まった別プロセスは停止していない。
- IrodoriではSoXから参照音声を48kHzから44.1kHzへ変換する警告が出たが、生成は失敗せず、最終WAVは16kHzだった。Qwenでは `flash-attn` がない警告が出てPyTorch経路へフォールバックした。前回Colabのログにも同じ警告があり、追加の依存は導入していない。
- facultyの環境はIrodori-TTS commit `f01c08cd40c0afa62a862439a5de12f6dcf62054`、Qwen TTS 0.1.1、Qwen環境のPyTorch 2.11.0+cu128、Irodori環境のPyTorch 2.10.0+cu128。SoX 14.4.2、uv 0.13.5。今回のQwen環境は前回記録と主要パッケージ（PyTorch 2.11.0+cu128、transformers 4.57.3、qwen-tts 0.1.1など）が一致した。4つのHugging Face revisionは `~/voiceime-work-tts/model-revisions.tsv` と上記のrevision一覧に記録した。
- `setup_colab.sh` と既存の `tts_meta.jsonl` はHugging Faceのmodel revisionを保存していない。facultyでは同じmodel IDを使い、今回取得したrevisionを固定したが、前回のColab実行とweightのcommitが同一かは確認できない。
- 前回の全実行は11,990件で約2時間40分（L4 49分、A100 108分）。A100のログはQwen RTF 0.196、Irodori RTF 0.060だった。今回最速のH100条件はQwen RTF 0.667、Irodori RTF 0.028で、Qwenは約3.4倍遅くIrodoriは約2.1倍速い。主なQwenパッケージ版は前回と一致したが、weight revisionは不明のため差の原因を特定できない。
- 前回train 10,000件はIrodori音声26.30時間、Qwen音声5.63時間。今回の最速RTFを当てはめるとIrodoriは約0.75時間、Qwenは約3.76時間で、二つのTTSを同時に動かす本スクリプトではQwen側が全体時間を決める。10,000件の目安は約3.8時間（前回の文長・Qwen比率を仮定）。前回の10,000件の件数比例値約2時間13分より約1.7倍長い。第3弾の文長とQwen比率で変わる。
- **本番生成前に、今回固定したHugging Face revisionを採用してよいかPMの判断が必要。** 前回と同一weightを保証できず、速度比較も同一weight条件ではない。
