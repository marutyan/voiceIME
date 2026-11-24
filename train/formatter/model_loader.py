"""整形器が使う因果言語モデルを、モデル設定に合うTransformersクラスで読み込む。"""

from pathlib import Path
from typing import Any

from transformers import AutoConfig, AutoModelForCausalLM


def load_formatter_model(
    model_name: str | Path,
    *,
    local_files_only: bool = False,
    **load_kwargs: Any,
) -> Any:
    """Qwen3.5のmultimodal wrapperを含め、整形用モデルを読み込む。"""
    config = AutoConfig.from_pretrained(
        model_name, local_files_only=local_files_only
    )
    model_kwargs = {**load_kwargs, "local_files_only": local_files_only}
    if (
        config.model_type == "qwen3_5"
        and "Qwen3_5ForConditionalGeneration" in (config.architectures or [])
    ):
        from transformers import AutoModelForMultimodalLM

        return AutoModelForMultimodalLM.from_pretrained(model_name, **model_kwargs)
    return AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
