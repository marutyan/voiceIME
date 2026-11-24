"""公式SFTへseed固定と実験用の学習制御を加える。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def patch_trainer(source: Path, destination: Path) -> tuple[str, str]:
    """公式trainerの既知の箇所へ限定patchを適用し、前後のhashを返す。"""
    original = source.read_text(encoding="utf-8")
    patched = original

    import_anchor = "import argparse\n"
    if patched.count(import_anchor) != 1:
        raise ValueError("公式trainerのimport箇所が想定と異なります")
    patched = patched.replace(import_anchor, "import argparse\nimport json\n", 1)

    audio_import_anchor = "import librosa\n"
    if patched.count(audio_import_anchor) != 1:
        raise ValueError("公式trainerのaudio import箇所が想定と異なります")
    patched = patched.replace(audio_import_anchor, "import librosa\nimport numpy as np\n", 1)

    preprocess_anchor = (
        '            "prefix_text": prefix_text,\n'
    )
    preprocess_patch = (
        '            "prefix_text": prefix_text,\n'
        '            "audio_features": ex.get("audio_features", ""),\n'
    )
    if patched.count(preprocess_anchor) != 1:
        raise ValueError("公式trainerのpreprocess箇所が想定と異なります")
    patched = patched.replace(preprocess_anchor, preprocess_patch, 1)

    keep_anchor = '    keep = {"prompt", "audio", "target", "prefix_text"}\n'
    keep_patch = '    keep = {"prompt", "audio", "target", "prefix_text", "audio_features"}\n'
    if patched.count(keep_anchor) != 1:
        raise ValueError("公式trainerのdataset列箇所が想定と異なります")
    patched = patched.replace(keep_anchor, keep_patch, 1)

    collator_audio_anchor = (
        '        audio_paths = [f["audio"] for f in features]\n'
        '        prefix_texts = [f["prefix_text"] for f in features]\n'
        '        targets = [f["target"] for f in features]\n'
        '\n'
        '        eos = self.processor.tokenizer.eos_token or ""\n'
        '        full_texts = [pfx + tgt + eos for pfx, tgt in zip(prefix_texts, targets)]\n'
        '        audios = [load_audio(p, sr=self.sampling_rate) for p in audio_paths]\n'
        '\n'
        '        full_inputs = self.processor(\n'
        '            text=full_texts,\n'
        '            audio=audios,\n'
        '            return_tensors="pt",\n'
        '            padding=True,\n'
        '            truncation=False,\n'
        '        )\n'
        '        prefix_inputs = self.processor(\n'
        '            text=prefix_texts,\n'
        '            audio=audios,\n'
        '            return_tensors="pt",\n'
        '            padding=True,\n'
        '            truncation=False,\n'
        '        )\n'
    )
    collator_audio_patch = '''        audio_paths = [f["audio"] for f in features]
        prefix_texts = [f["prefix_text"] for f in features]
        targets = [f["target"] for f in features]

        eos = self.processor.tokenizer.eos_token or ""
        full_texts = [pfx + tgt + eos for pfx, tgt in zip(prefix_texts, targets)]
        feature_paths = [f.get("audio_features", "") for f in features]
        if all(isinstance(path, str) and path for path in feature_paths):
            from qwen_asr.core.transformers_backend.processing_qwen3_asr import (
                _get_feat_extract_output_lengths,
            )

            # 全特徴配列を読む前に長さだけ調べ、不要な特徴の読込を避ける。
            sample_counts = []
            for path in feature_paths:
                with np.load(path, allow_pickle=False) as cached:
                    sample_counts.append(int(cached["sample_count"]))
            maximum_sample_count = max(sample_counts)
            hop_length = self.processor.feature_extractor.hop_length
            maximum_feature_frames = maximum_sample_count // hop_length
            cached_features = []
            cached_masks = np.zeros(
                (len(sample_counts), maximum_feature_frames), dtype=np.int64
            )
            for index, (path, sample_count) in enumerate(
                zip(feature_paths, sample_counts)
            ):
                feature_key = (
                    "reflect_features"
                    if sample_count == maximum_sample_count
                    else "zero_padded_features"
                )
                # batch内で使う側だけを読み、もう一方の配列を展開しない。
                with np.load(path, allow_pickle=False) as cached:
                    source_features = cached[feature_key]
                    feature_length = int(cached["feature_length"])
                if (
                    feature_key == "reflect_features"
                    and source_features.shape[-1] != feature_length
                ):
                    raise ValueError("cached feature length metadata is inconsistent")
                if source_features.shape[-1] < maximum_feature_frames:
                    raise ValueError(
                        "cached log-mel sequence is shorter than the batch maximum"
                    )
                cached_features.append(source_features[:, :maximum_feature_frames])
                valid_frames = min(
                    (sample_count + hop_length - 1) // hop_length,
                    maximum_feature_frames,
                )
                cached_masks[index, :valid_frames] = 1
            input_features = torch.from_numpy(np.stack(cached_features))
            feature_attention_mask = torch.from_numpy(cached_masks)
            audio_output_lengths = _get_feat_extract_output_lengths(
                feature_attention_mask.sum(-1)
            )
            full_texts = self.processor.replace_multimodal_special_tokens(
                full_texts, iter(audio_output_lengths)
            )
            prefix_texts = self.processor.replace_multimodal_special_tokens(
                prefix_texts, iter(audio_output_lengths)
            )
            full_inputs = self.processor.tokenizer(
                full_texts, padding=True, return_tensors="pt"
            )
            prefix_inputs = self.processor.tokenizer(
                prefix_texts, padding=True, return_tensors="pt"
            )
            full_inputs["input_features"] = input_features
            full_inputs["feature_attention_mask"] = feature_attention_mask
        else:
            audios = [load_audio(p, sr=self.sampling_rate) for p in audio_paths]
            full_inputs = self.processor(
                text=full_texts,
                audio=audios,
                return_tensors="pt",
                padding=True,
                truncation=False,
            )
            prefix_inputs = self.processor(
                text=prefix_texts,
                audio=audios,
                return_tensors="pt",
                padding=True,
                truncation=False,
            )
'''
    if patched.count(collator_audio_anchor) != 1:
        raise ValueError("公式trainerのcollator箇所が想定と異なります")
    patched = patched.replace(collator_audio_anchor, collator_audio_patch, 1)

    training_args_anchor = '        report_to="none",\n'
    training_args_patch = (
        '        report_to="none",\n'
        "        seed=0,\n"
        "        data_seed=0,\n"
    )
    if patched.count(training_args_anchor) != 1:
        raise ValueError("公式trainerのTrainingArguments箇所が想定と異なります")
    patched = patched.replace(training_args_anchor, training_args_patch, 1)

    training_args_config_anchor = (
        '        warmup_ratio=args_cli.warmup_ratio,\n'
    )
    training_args_config_patch = (
        '        warmup_ratio=args_cli.warmup_ratio,\n'
        '        max_steps=args_cli.max_steps,\n'
        '        max_grad_norm=args_cli.max_grad_norm,\n'
    )
    if patched.count(training_args_config_anchor) != 1:
        raise ValueError("公式trainerの学習設定箇所が想定と異なります")
    patched = patched.replace(
        training_args_config_anchor, training_args_config_patch, 1
    )

    cli_args_anchor = (
        '    p.add_argument("--warmup_ratio", type=float, default=0.02)\n'
    )
    cli_args_patch = (
        '    p.add_argument("--warmup_ratio", type=float, default=0.02)\n'
        '    p.add_argument("--max_steps", type=int, default=-1)\n'
        '    p.add_argument("--max_grad_norm", type=float, default=1.0)\n'
        '    p.add_argument("--save_final_model", type=int, default=1)\n'
        '    p.add_argument("--freeze_audio_encoder", type=int, default=0)\n'
    )
    if patched.count(cli_args_anchor) != 1:
        raise ValueError("公式trainerのCLI引数箇所が想定と異なります")
    patched = patched.replace(cli_args_anchor, cli_args_patch, 1)

    freeze_anchor = (
        "    model = asr_wrapper.model\n"
        "    processor = asr_wrapper.processor\n"
    )
    freeze_patch = (
        "    model = asr_wrapper.model\n"
        "    processor = asr_wrapper.processor\n"
        "    if args_cli.freeze_audio_encoder == 1:\n"
        '        audio_encoder = getattr(getattr(model, "thinker", None), "audio_tower", None)\n'
        "        if audio_encoder is None:\n"
        '            raise RuntimeError("Qwen3-ASR audio encoder module was not found")\n'
        "        for parameter in audio_encoder.parameters():\n"
        "            parameter.requires_grad_(False)\n"
        '        print("[training] froze thinker.audio_tower", flush=True)\n'
    )
    if patched.count(freeze_anchor) != 1:
        raise ValueError("公式trainerのmodel初期化箇所が想定と異なります")
    patched = patched.replace(freeze_anchor, freeze_patch, 1)

    callback_anchor = "\n\ndef copy_required_hf_files_for_qwen_asr"
    callback_source = '''

class NonFiniteGradientDiagnosticCallback(TrainerCallback):
    """最初のoptimizer stepで非有限勾配のparameter名を記録する。"""

    def __init__(self):
        self.checked_steps = 0

    def on_pre_optimizer_step(self, args, state, control, model=None, **kwargs):
        if self.checked_steps >= 1:
            return control
        self.checked_steps += 1
        bad_parameters = []
        for name, parameter in model.named_parameters():
            if parameter.grad is None:
                continue
            finite = torch.isfinite(parameter.grad)
            if not bool(finite.all()):
                bad_parameters.append({
                    "name": name,
                    "nonfinite_elements": int((~finite).sum().item()),
                    "gradient_elements": parameter.grad.numel(),
                })
        module_counts = {}
        for item in bad_parameters:
            module = ".".join(item["name"].split(".")[:2])
            module_counts[module] = module_counts.get(module, 0) + 1
        print(
            "[gradient-diagnostic] "
            + json.dumps(
                {
                    "optimizer_step": state.global_step + 1,
                    "max_grad_norm": args.max_grad_norm,
                    "nonfinite_parameter_count": len(bad_parameters),
                    "nonfinite_module_counts": module_counts,
                    "nonfinite_parameters": bad_parameters[:20],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return control
'''
    if patched.count(callback_anchor) != 1:
        raise ValueError("公式trainerのcallback挿入箇所が想定と異なります")
    patched = patched.replace(callback_anchor, callback_source + callback_anchor, 1)

    callbacks_anchor = (
        '        callbacks=[MakeEveryCheckpointInferableCallback(base_model_path=args_cli.model_path)],\n'
    )
    callbacks_patch = (
        '        callbacks=[\n'
        '            NonFiniteGradientDiagnosticCallback(),\n'
        '            MakeEveryCheckpointInferableCallback(base_model_path=args_cli.model_path),\n'
        '        ],\n'
    )
    if patched.count(callbacks_anchor) != 1:
        raise ValueError("公式trainerのcallback登録箇所が想定と異なります")
    patched = patched.replace(callbacks_anchor, callbacks_patch, 1)

    train_end_anchor = (
        "    else:\n"
        "        trainer.train()\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
    )
    train_end_patch = (
        "    else:\n"
        "        trainer.train()\n"
        "\n"
        "    if args_cli.save_final_model == 1:\n"
        '        final_dir = os.path.join(args_cli.output_dir, "final")\n'
        "        trainer.save_model(final_dir)\n"
        "        copy_required_hf_files_for_qwen_asr(args_cli.model_path, final_dir)\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
    )
    if patched.count(train_end_anchor) != 1:
        raise ValueError("公式trainerのtrain終了箇所が想定と異なります")
    patched = patched.replace(train_end_anchor, train_end_patch, 1)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    return (
        hashlib.sha256(original.encode("utf-8")).hexdigest(),
        hashlib.sha256(patched.encode("utf-8")).hexdigest(),
    )


def optimize_cached_feature_loading(
    source: Path, destination: Path
) -> tuple[str, str]:
    """学習済みのpatchへ、batchで使う特徴だけを読む処理を適用する。"""
    original = source.read_text(encoding="utf-8")
    old_block = '''            cached_records = []
            for path in feature_paths:
                with np.load(path, allow_pickle=False) as cached:
                    cached_records.append(
                        {
                            "reflect_features": cached["reflect_features"],
                            "zero_padded_features": cached["zero_padded_features"],
                            "sample_count": int(cached["sample_count"]),
                            "feature_length": int(cached["feature_length"]),
                        }
                    )
            maximum_sample_count = max(
                record["sample_count"] for record in cached_records
            )
            hop_length = self.processor.feature_extractor.hop_length
            maximum_feature_frames = maximum_sample_count // hop_length
            cached_features = []
            cached_masks = np.zeros(
                (len(cached_records), maximum_feature_frames), dtype=np.int64
            )
            for index, record in enumerate(cached_records):
                feature_key = (
                    "reflect_features"
                    if record["sample_count"] == maximum_sample_count
                    else "zero_padded_features"
                )
                source_features = record[feature_key]
                if (
                    record["reflect_features"].shape[-1]
                    != record["feature_length"]
                ):
                    raise ValueError("cached feature length metadata is inconsistent")
                if source_features.shape[-1] < maximum_feature_frames:
                    raise ValueError(
                        "cached log-mel sequence is shorter than the batch maximum"
                    )
                cached_features.append(source_features[:, :maximum_feature_frames])
                valid_frames = min(
                    (record["sample_count"] + hop_length - 1) // hop_length,
                    maximum_feature_frames,
                )
                cached_masks[index, :valid_frames] = 1
'''
    new_block = '''            # 最大長の決定に必要なメタデータだけを先に読み、特徴配列の重複読込を避ける。
            sample_counts = []
            for path in feature_paths:
                with np.load(path, allow_pickle=False) as cached:
                    sample_counts.append(int(cached["sample_count"]))
            maximum_sample_count = max(sample_counts)
            hop_length = self.processor.feature_extractor.hop_length
            maximum_feature_frames = maximum_sample_count // hop_length
            cached_features = []
            cached_masks = np.zeros(
                (len(sample_counts), maximum_feature_frames), dtype=np.int64
            )
            for index, (path, sample_count) in enumerate(
                zip(feature_paths, sample_counts)
            ):
                feature_key = (
                    "reflect_features"
                    if sample_count == maximum_sample_count
                    else "zero_padded_features"
                )
                # batch内で使う側だけを読み、不要な配列の展開とコピーを避ける。
                with np.load(path, allow_pickle=False) as cached:
                    source_features = cached[feature_key]
                    feature_length = int(cached["feature_length"])
                if (
                    feature_key == "reflect_features"
                    and source_features.shape[-1] != feature_length
                ):
                    raise ValueError("cached feature length metadata is inconsistent")
                if source_features.shape[-1] < maximum_feature_frames:
                    raise ValueError(
                        "cached log-mel sequence is shorter than the batch maximum"
                    )
                cached_features.append(source_features[:, :maximum_feature_frames])
                valid_frames = min(
                    (sample_count + hop_length - 1) // hop_length,
                    maximum_feature_frames,
                )
                cached_masks[index, :valid_frames] = 1
'''
    if original.count(old_block) != 1:
        raise ValueError("cached collatorが想定と異なります")
    optimized = original.replace(old_block, new_block, 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(optimized, encoding="utf-8")
    return (
        hashlib.sha256(original.encode("utf-8")).hexdigest(),
        hashlib.sha256(optimized.encode("utf-8")).hexdigest(),
    )


def main() -> None:
    """公式trainerの場所と出力pathを受け取り、patch後のhashを表示する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--optimize-cached-reader", action="store_true")
    args = parser.parse_args()
    if args.optimize_cached_reader:
        source_hash, patched_hash = optimize_cached_feature_loading(
            args.source, args.destination
        )
    else:
        source_hash, patched_hash = patch_trainer(args.source, args.destination)
    print(f"source_sha256={source_hash}")
    print(f"patched_sha256={patched_hash}")


if __name__ == "__main__":
    main()
