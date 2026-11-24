"""Colab CLIでGPUを借りて`train.py`を実行し、学習後の重みを手元へ持ち帰ってMLXの4bitへ変換する。

手元のMacで、作業ツリーの直下から実行する。`--`の後ろは`train.py`へそのまま渡す
（`--train`、`--val`、`--glossary`、`--*-asr-run`のファイルは自動でColabへ送り、path を置き換える）。
    uv run python train/formatter/colab_train.py --name <実験名> --gpu L4 --colab-config <state.json> -- \\
        --model Qwen/Qwen3.5-0.8B --train data/text/train.jsonl --val data/text/val.jsonl --method full

学習はColabのVMの上で裏で動かし、手元からは短い`colab exec`で進み具合を定期的に確かめる
（長い1回の`exec`は接続が切れると結果を失うため）。すべての`colab`の呼び出しに手元で時間の上限を付ける。
結果は`/Users/marutyan/PrivateDev/voiceIME/models/formatter/<実験名>/`の`hf/`（Hugging Face形式）、
`mlx-4bit/`（変換後）、`train_summary.json`、`train.log`に置く。LoRAで`--save-adapter-only`を渡した場合は
`adapter/`を持ち帰り、手元の`merge_lora.py`で`hf/`へ統合する。セッションは成否によらず最後に止める。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

# 学習後の重みの置き場所（Gitの外）。
MODELS_ROOT = Path("/Users/marutyan/PrivateDev/voiceIME/models/formatter")
# 作業ツリーの直下（このファイルは train/formatter/ にある）。
REPO_ROOT = Path(__file__).resolve().parents[2]
# `train.py`の引数のうち、手元のファイルを指すためColabへ送る必要があるもの。
FILE_ARGS = ("--train", "--val", "--glossary", "--train-asr-run", "--train-asr-run-nohint", "--val-asr-run")
# Colab上の作業場所。
REMOTE_ROOT = "/content/formatter"
# コードとデータのtarの置き場所。uploadは既存のdirへしか書けないため、/content の直下に置く。
REMOTE_BUNDLE = "/content/formatter-bundle.tar.gz"
# Colabへ入れる学習用の依存。手元で動作を確かめた版に固定し、Colabの既定の版の変化で結果が変わらないようにする。
PIP_PACKAGES = "transformers==5.23.0 peft==0.22.0 accelerate rapidfuzz"
# 手元でLoRAを統合するときに一時的な環境へ入れる依存（学習と同じ版）。
LOCAL_MERGE_PACKAGES = ("torch==2.15.0", "transformers==5.23.0", "peft==0.22.0", "accelerate")
# 進み具合を確かめる間隔（秒）。
POLL_INTERVAL_S = 120
# `colab`の各操作の上限時間（秒）。接続の段階で固まることがあるため、必ず上限を付ける。
TIMEOUTS_S = {"new": 900, "upload": 1800, "start": 900, "poll": 180, "pack": 900, "download": 5400, "log": 300,
              "stop": 300}
# 学習のログが現れないまま、この回数だけ確認が続いたら起動に失敗したとみなす。
MAX_POLLS_WITHOUT_LOG = 5

# VMで依存を入れ、`train.py`を裏で起動する。終了コードは exit_code に書かれる。
REMOTE_START = r"""
import json, os, shlex, subprocess, sys, tarfile
root = os.environ["FORMATTER_ROOT"]
with tarfile.open(os.environ["FORMATTER_BUNDLE"]) as t:
    t.extractall(root, filter="data")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *os.environ["PIP_PACKAGES"].split()], check=True)
args = json.loads(os.environ["TRAIN_ARGS"])
# 語彙の大きいモデルはlogitsのメモリが大きく断片化しやすいため、拡張できる領域でGPUメモリを確保する。
env = dict(os.environ, PYTHONPATH=f"{root}/src", PYTHONUNBUFFERED="1", PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
cmd = " ".join([sys.executable, f"{root}/train/formatter/train.py", *[shlex.quote(a) for a in args]])
# 標準入出力をkernelから切り離す。つないだままだと`colab exec`が裏の処理の終了を待って戻らない。
subprocess.Popen(["bash", "-c", f"{cmd} > {root}/train.log 2>&1; echo $? > {root}/exit_code"], env=env,
                 start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL)
print("STARTED", flush=True)
"""

# VMで学習の進み具合（ログの末尾と終了コード）を表示する。
REMOTE_POLL = r"""
import os
root = "/content/formatter"
log = open(f"{root}/train.log", errors="replace").read().replace("\r", "\n").splitlines() if os.path.exists(f"{root}/train.log") else []
print("\n".join(l[:300] for l in log if "eval_loss" in l or "'loss'" in l or "Error" in l or "Traceback" in l)[-1500:])
print("TAIL:", log[-1][:300] if log else "")
status = "nolog" if not os.path.exists(f"{root}/train.log") else "running"
if os.path.exists(f"{root}/exit_code"):
    status = open(f"{root}/exit_code").read().strip()
print("STATUS:", status, flush=True)
"""

# VMで持ち帰る結果のtarを裏で作る。重みのtarは数分かかり、その間に`colab exec`の接続が切れることがあるため。
# 作り終えると pack_done ができる。
REMOTE_PACK = r"""
import os, subprocess
root = "/content/formatter"
items = [f"{src}:{arc}" for src, arc in (("out/final", "hf"), ("out/adapter", "adapter"),
         ("out/train_summary.json", "train_summary.json"), ("train.log", "train.log")) if os.path.exists(f"{root}/{src}")]
code = (
    "import tarfile, sys\n"
    "root = sys.argv[1]\n"
    "with tarfile.open(f'{root}/result.tar', 'w') as t:\n"
    "    for item in sys.argv[2:]:\n"
    "        src, arc = item.split(':')\n"
    "        t.add(f'{root}/{src}', arcname=arc)\n"
    "open(f'{root}/pack_done', 'w').write('ok')\n"
)
subprocess.Popen(["python3", "-c", code, root, *items], start_new_session=True,
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("PACKING", items, flush=True)
"""

# 結果のtarができたかを表示する。
REMOTE_PACK_POLL = r"""
import os
root = "/content/formatter"
print("PACK:", "done" if os.path.exists(f"{root}/pack_done") else "running",
      os.path.getsize(f"{root}/result.tar") if os.path.exists(f"{root}/result.tar") else 0, flush=True)
"""


def colab(config: str | None, op: str, *args: str, capture: bool = False, retries: int = 0) -> str:
    """Colab CLIを1回呼ぶ。`TIMEOUTS_S`の上限で打ち切り、失敗したら`retries`回までやり直してから例外にする。"""
    cmd = ["colab"] + (["--config", config] if config else []) + list(args)
    for attempt in range(retries + 1):
        try:
            done = subprocess.run(cmd, check=True, timeout=TIMEOUTS_S[op], capture_output=capture, text=True)
            return done.stdout if capture else ""
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            print(f"[colab_train] {op} に失敗しました（{attempt + 1}回目）: {type(error).__name__}", flush=True)
            if attempt == retries:
                raise
            time.sleep(30)
    return ""


def bundle_sources(train_args: list[str], tmp: Path) -> tuple[Path, list[str]]:
    """コードとデータをtar.gzにまとめ、`train.py`の引数のpathをColab上のpathへ置き換える。"""
    remote_args = list(train_args)
    bundle = tmp / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as t:
        t.add(REPO_ROOT / "src", arcname="src", filter=lambda i: None if "__pycache__" in i.name else i)
        t.add(REPO_ROOT / "train" / "formatter", arcname="train/formatter",
              filter=lambda i: None if "__pycache__" in i.name else i)
        for i, arg in enumerate(train_args[:-1]):
            if arg in FILE_ARGS:
                local = Path(train_args[i + 1])
                name = f"data/{arg.lstrip('-')}-{local.name}"
                t.add(local, arcname=name)
                remote_args[i + 1] = f"{REMOTE_ROOT}/{name}"
    remote_args += ["--output-dir", f"{REMOTE_ROOT}/out"]
    return bundle, remote_args


def run_remote(config: str | None, session: str, op: str, script_text: str, tmp: Path, *env: str) -> str:
    """短いPythonの処理をVMのkernelで実行し、標準出力を返す。"""
    script = tmp / f"{op}.py"
    script.write_text(script_text)
    env_args = [a for e in env for a in ("--env", e)]
    return colab(config, op, "exec", "-s", session, "-f", str(script), "--timeout", str(TIMEOUTS_S[op] - 30),
                 *env_args, capture=True, retries=1 if op == "poll" else 0)


def wait_for_training(config: str | None, session: str, tmp: Path, timeout_hours: float) -> None:
    """学習が終わるまで定期的に進み具合を表示する。失敗、または上限時間を超えたら例外にする。"""
    deadline = time.monotonic() + timeout_hours * 3600
    polls_without_log = 0
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_S)
        try:
            out = run_remote(config, session, "poll", REMOTE_POLL, tmp)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue  # 一時的な接続の失敗は次の確認でやり直す
        lines = [line for line in out.splitlines() if line.strip()]
        print(f"[colab_train] {time.strftime('%H:%M:%S')} " + " / ".join(lines[-3:]), flush=True)
        status = re.search(r"STATUS: (\S+)", out)
        if status and status.group(1) == "nolog":
            polls_without_log += 1
            if polls_without_log >= MAX_POLLS_WITHOUT_LOG:
                raise RuntimeError("学習のログが現れません（起動に失敗した）")
            continue
        if status and status.group(1) != "running":
            if status.group(1) != "0":
                raise RuntimeError(f"train.py が終了コード {status.group(1)} で終わりました")
            return
    raise TimeoutError(f"学習が{timeout_hours}時間で終わりませんでした")


def wait_for_pack(config: str | None, session: str, tmp: Path) -> None:
    """結果のtarができるまで待つ。上限を超えたら例外にする。"""
    deadline = time.monotonic() + TIMEOUTS_S["pack"]
    while time.monotonic() < deadline:
        time.sleep(20)
        try:
            out = run_remote(config, session, "poll", REMOTE_PACK_POLL, tmp)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        print(f"[colab_train] {out.strip()}", flush=True)
        if "PACK: done" in out:
            return
    raise TimeoutError("結果のtarが時間内にできませんでした")


def main() -> None:
    """セッションを作り、学習し、結果を持ち帰り、セッションを止め、必要ならLoRAを統合してMLXへ変換する。"""
    parser = argparse.ArgumentParser(description="Colabで整形用LLMを学習して手元へ持ち帰る")
    parser.add_argument("--name", required=True, help="実験名（models/formatter/<実験名>/ に保存）")
    parser.add_argument("--gpu", default="L4", choices=["T4", "L4", "G4", "A100", "H100"])
    parser.add_argument("--colab-config", help="Colab CLIのセッション状態のファイル（担当ごとに分ける）")
    parser.add_argument("--timeout-hours", type=float, default=3.0, help="学習の実行の上限時間")
    parser.add_argument("--extra-pip", default="", help="Colabへ追加で入れるパッケージ（空白区切り）")
    parser.add_argument("--skip-convert", action="store_true", help="MLXへの変換を行わない")
    parser.add_argument("train_args", nargs=argparse.REMAINDER, help="`--`の後ろに train.py の引数")
    args = parser.parse_args()
    train_args = args.train_args[1:] if args.train_args[:1] == ["--"] else args.train_args
    if "--output-dir" in train_args:
        sys.exit("--output-dir はこのスクリプトが決めるため渡さないでください")

    dest = MODELS_ROOT / args.name
    if dest.exists():
        sys.exit(f"保存先が既にあります（上書きしません）: {dest}")
    session = f"formatter-{args.name}"
    pip_packages = f"{PIP_PACKAGES} {args.extra_pip}".strip()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        bundle, remote_args = bundle_sources(train_args, tmp)
        result = tmp / "result.tar"
        try:
            colab(args.colab_config, "new", "new", "-s", session, "--gpu", args.gpu)
            colab(args.colab_config, "upload", "upload", "-s", session, str(bundle), REMOTE_BUNDLE, retries=1)
            try:
                print(run_remote(args.colab_config, session, "start", REMOTE_START, tmp,
                                 f"FORMATTER_ROOT={REMOTE_ROOT}", f"FORMATTER_BUNDLE={REMOTE_BUNDLE}",
                                 f"PIP_PACKAGES={pip_packages}", f"TRAIN_ARGS={json.dumps(remote_args)}"), flush=True)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # `colab exec`はVMの処理が終わっても応答を返さず固まることがある。起動できたかは進み具合の確認で判断する。
                print("[colab_train] start の応答がありません。進み具合の確認へ進みます", flush=True)
            wait_for_training(args.colab_config, session, tmp, args.timeout_hours)
            print(run_remote(args.colab_config, session, "pack", REMOTE_PACK, tmp), flush=True)
            wait_for_pack(args.colab_config, session, tmp)
            colab(args.colab_config, "download", "download", "-s", session, f"{REMOTE_ROOT}/result.tar", str(result),
                  retries=1)
        finally:
            # 失敗したときもログだけは持ち帰りを試み、必ずセッションを止める。
            if not result.exists():
                try:
                    colab(args.colab_config, "log", "download", "-s", session, f"{REMOTE_ROOT}/train.log",
                          str(tmp / "train.log"))
                    print((tmp / "train.log").read_text(errors="replace")[-5000:])
                except Exception as error:  # ログが無い段階の失敗もあるため、ここでは止めない
                    print(f"[colab_train] ログを持ち帰れませんでした: {type(error).__name__}")
            colab(args.colab_config, "stop", "stop", "-s", session, retries=2)
        dest.mkdir(parents=True)
        with tarfile.open(result) as t:
            t.extractall(dest, filter="data")

    print(f"学習の結果を保存しました: {dest}")
    if (dest / "adapter").exists():
        base = train_args[train_args.index("--model") + 1]
        with_args = [a for p in LOCAL_MERGE_PACKAGES for a in ("--with", p)]
        subprocess.run(["uv", "run", "--no-project", *with_args, "python", str(REPO_ROOT / "train/formatter/merge_lora.py"),
                        "--base", base, "--adapter", str(dest / "adapter"), "--out", str(dest / "hf")], check=True)
    if not args.skip_convert:
        subprocess.run([sys.executable, str(REPO_ROOT / "train/formatter/convert_to_mlx.py"), str(dest / "hf"),
                        str(dest / "mlx-4bit")], check=True)


if __name__ == "__main__":
    main()
