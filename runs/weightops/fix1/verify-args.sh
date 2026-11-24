# 学習と同じデータ引数で検査を走らせる（GPUは使わない）。第1引数は結果の出力先、第2・第3は元行と拡張行。
source "$HOME/voiceime-work-wops/rsi1/faculty-env.sh"
FIX="$WORK/fix1"
export PYTHONPATH="$FIX:$PYTHONPATH" CUDA_VISIBLE_DEVICES=""
MODEL0="$FR3/hf-cache/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17"
cd "$FIX"
exec -a voiceime-wops-fix-verify nice "$PY" verify_dynamic.py "$1" \
  --model "$MODEL0" --disable-cudnn-sdp \
  --train "$2" --augmentation "$3" \
  --train-asr-run-nohint "$D_INPUT/train-runs/first-pass.jsonl" \
  --train-asr-run-combined "$D_INPUT/train-runs/segment-merge.jsonl" \
  --train-asr-run-qwen "$D_INPUT/train-runs/qwen06-hypothesis.jsonl" \
  --train-glossary-run "$D_INPUT/train-runs/formatter-glossary.jsonl" \
  --input-passes multiasr --allow-partial-asr --asr-noise-prob 1.0 --user-punct-prob 0.5 \
  --val "$FR3/inputs/val-select.jsonl" \
  --val-asr-run-nohint "$D_INPUT/val-runs/first-pass.jsonl" \
  --val-asr-run-combined "$D_INPUT/val-runs/segment-merge.jsonl" \
  --val-asr-run-qwen "$D_INPUT/val-runs/qwen06-hypothesis.jsonl" \
  --val-glossary-run "$D_INPUT/val-runs/formatter-glossary.jsonl" \
  --glossary "$D_INPUT/legacy/training-glossary.jsonl" \
  --method full --epochs 2 --learning-rate 2e-5 --batch-size 16 --grad-accum 2 --max-length 1024 \
  --eval-steps 250 --dataloader-workers 16 --gradient-checkpointing \
  --glossary-drop-prob 0 --max-distractors 8 --seed 0 --output-dir /tmp/voiceime-wops-verify-unused
