"""一時的な確認（commitしない）：Colabで公式のHaas-ASRに同じ音声を認識させ、結果をJSONに保存する。"""

import glob
import json
import os
import subprocess
import sys
import time

HAAS_COMMIT = "acc614f68769dcbfae9dba96b48439c4a66295af"

t0 = time.time()
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", f"haas-asr @ git+https://github.com/third-intelligence/Haas-ASR.git@{HAAS_COMMIT}"],
    check=True,
)
print("install", time.time() - t0, flush=True)

import torch  # noqa: E402

import haas_asr  # noqa: E402

files = sorted(glob.glob("/content/wav/*.wav"))
audio = [haas_asr.load_audio(f) for f in files]
results = {"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__}
for name, dtype in (("float32", torch.float32), ("auto", "auto")):
    try:
        model = haas_asr.load_model("third-intelligence/Haas-ja-v1.0", dtype=dtype)
        out = model.transcribe(audio, batch_size=1)
        results[name] = {os.path.basename(f): h.text.strip() for f, h in zip(files, out)}
        del model
        torch.cuda.empty_cache()
    except Exception as e:  # 型によってはT4で動かないため、失敗を記録して続ける
        results[name] = repr(e)
    print(name, "done", time.time() - t0, flush=True)
json.dump(results, open("/content/haas_official.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(results, ensure_ascii=False, indent=1))
