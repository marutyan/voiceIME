"""Colab上で動いているvLLMサーバーを止め、colab_server.sh で起動し直す。

実行場所：Colab VMの上（手元から `colab exec -f` で渡す）。サーバーの設定を変えたときに使う。
"""

import signal
import subprocess
import time
from pathlib import Path

# vllm serve の本体のプロセスだけを探す（このスクリプト自身や検索のシェルは対象にしない）
pids = [
    int(line.split()[1])
    for line in subprocess.run(["ps", "aux"], capture_output=True, text=True).stdout.splitlines()
    if "/usr/local/bin/vllm serve" in line
]
for pid in pids:
    subprocess.run(["kill", f"-{signal.SIGINT.value}", str(pid)])
for _ in range(60):
    used = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True
    ).stdout.strip()
    if int(used) < 1000:
        break
    time.sleep(2)
log = Path("/content/vllm_server.log")
if log.exists():
    log.rename(f"/content/vllm_server_{int(time.time())}.log")
subprocess.Popen("bash /content/colab_server.sh > /content/server_start.log 2>&1", shell=True)
print(f"stopped {pids}, gpu_mem_used_before_restart={used}MiB, restarting")
