"""既存のTransformers推論器を、実験のプロセス名で起動する。"""
import runpy
import sys
from pathlib import Path

from setproctitle import setproctitle

setproctitle("voiceime-custom-formatter")
script = Path.home() / "voiceime-work-fr3/repo/train/formatter/eval_transformers.py"
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name="__main__")
