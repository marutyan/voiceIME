"""認識エンジンをCLIから起動する。"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import redirect_stdout
from pathlib import Path

from voiceime.asr.systems import GLOSSARY_BACKENDS, MODELS, asr_hint_format, build_transcriber
from voiceime.engine import FORMATTER_INPUTS, RecognitionEngine, TWO_PASS_POLICIES
from voiceime.formatter.glossary import load_glossary, load_term_list


# リポジトリの最上位。既定のモデルと用語集の置き場所を決めるために使う。
REPO_ROOT = Path(__file__).resolve().parents[3]
# アプリの設定と履歴の置き場所（`docs/engine-protocol.md`の「設定と保存先」）。
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "voiceIME"
# アプリが引数なしでエンジンを起動したときに使う既定値。採用中のASRと整形LLMをここだけで決める。
DEFAULT_ASR = "haas-ja-v1.0-speechcpp-q8_0"
# 整形LLMへ渡す用語一覧の既定の上限。合成音声の初見語が20語の378/500から412/500へ増え、本人の録音50件では差が誤差の内側だった。
DEFAULT_FORMATTER_MAX_GLOSSARY = 48

# 初回認識と並行に動かす補助ASR。整形LLMが3つの認識結果を受け取る形式（d）の入力に必要。
DEFAULT_AUX_ASR = "qwen3-asr-0.6b-8bit"
DEFAULT_FORMATTER = (
    REPO_ROOT / "models" / "formatter" / "sft3-d-qwen3.5-0.8b-fullscratch" / "mlx-4bit"
)
DEFAULT_HISTORY = APP_SUPPORT_DIR / "history.jsonl"


def _default_glossaries() -> list[Path]:
    """学習用の用語集に、存在する本人用の用語集（リポジトリとアプリの置き場所）を足した一覧を返す。"""
    candidates = [
        REPO_ROOT / "data" / "text" / "glossary.jsonl",
        REPO_ROOT / "data" / "user" / "glossary.jsonl",
        APP_SUPPORT_DIR / "glossary.jsonl",
    ]
    return [path for path in candidates if path.exists()]


def _arguments() -> argparse.Namespace:
    """エンジン起動に必要なASR、整形器、用語集、履歴の引数を読む。省略時は採用中の既定値を使う。"""
    parser = argparse.ArgumentParser(description="JSON Linesで音声区間を認識し整形する")
    parser.add_argument(
        "--asr", default=DEFAULT_ASR, choices=sorted(MODELS), help="`voiceime.asr.systems.MODELS`の名前"
    )
    parser.add_argument(
        "--aux-asr",
        default=DEFAULT_AUX_ASR,
        choices=[*sorted(MODELS), "none"],
        help="初回認識と並行に動かして用語選択の手掛かりを補う補助ASR（`voiceime.asr.systems.MODELS`の名前。noneで無効）",
    )
    parser.add_argument(
        "--formatter-input",
        default="d",
        choices=FORMATTER_INPUTS,
        help="整形LLMへ渡す入力の形式。text: 採否後の1文 / d: 1回目・採否後・補助ASRの3つ（`--aux-asr`が必要）",
    )
    parser.add_argument(
        "--formatter-max-glossary",
        type=int,
        default=DEFAULT_FORMATTER_MAX_GLOSSARY,
        help="整形LLMへ渡す用語一覧の上限件数",
    )
    parser.add_argument(
        "--formatter", default=str(DEFAULT_FORMATTER), help="MLXの重みのパス、rules、またはnone"
    )
    parser.add_argument(
        "--glossary",
        nargs="+",
        type=Path,
        default=None,
        help="用語集JSONLまたはJSON配列（複数可。省略時は学習用と存在する本人用の用語集）",
    )
    parser.add_argument(
        "--exclude-terms",
        type=Path,
        default=None,
        help="用語集から除く用語の一覧ファイル（1行1語）。ASRのヒントにも整形の参考にも渡さない",
    )
    parser.add_argument(
        "--glossary-alt-readings",
        type=Path,
        help="用語選択の照合専用の追加読みJSONL。省略時は元の用語集の読みを使う",
    )
    parser.add_argument("--history", default=DEFAULT_HISTORY, type=Path, help="履歴を書き足すJSONL")
    parser.add_argument(
        "--asr-hint-mode",
        choices=("none", "static", "two-pass"),
        default="two-pass",
        help="ASR用語ヒントを使わない、用語集から固定で選ぶ、初回認識後に選び直す",
    )
    parser.add_argument(
        "--two-pass-policy",
        choices=TWO_PASS_POLICIES,
        default="segment-merge",
        help="always、読みが近い場合だけ再認識する、読みの類似度が下がれば初回を採る、読みと対応するヒント語だけ区間ごとに採る",
    )
    parser.add_argument(
        "--expand-abbreviation-readings",
        action="store_true",
        help="英字略語と数字を含む用語の一字読みを用語集へ補う",
    )
    args = parser.parse_args()
    if args.aux_asr == "none":
        # 補助ASRが無いと3入力の形式は作れないので、採否後の1文だけを渡す形式へ戻す。
        args.aux_asr = None
        args.formatter_input = "text"
    if args.glossary is None:
        args.glossary = _default_glossaries()
    if not args.glossary:
        parser.error("用語集が見つかりません。--glossaryで指定してください")
    args.history.parent.mkdir(parents=True, exist_ok=True)
    return args


def main() -> None:
    """選択された既存モデルを読み込み、ready後に標準入出力でプロトコルを処理する。"""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _arguments()
    spec = MODELS[args.asr]
    transcriber = None
    aux_transcriber = None
    engine = None
    try:
        excluded_terms = load_term_list(args.exclude_terms) if args.exclude_terms else None
        glossary = load_glossary(
            *args.glossary,
            exclude_terms=excluded_terms,
            expand_abbreviation_readings=args.expand_abbreviation_readings,
            alt_readings_path=args.glossary_alt_readings,
        )
        with redirect_stdout(sys.stderr):
            transcriber = build_transcriber(spec, "greedy")
            aux_transcriber = (
                build_transcriber(MODELS[args.aux_asr], "greedy")
                if args.aux_asr
                else None
            )
            formatter_kind = "rules" if args.formatter == "rules" else "none" if args.formatter == "none" else "model"
            formatter = None
            formatter_name = args.formatter
            if formatter_kind == "model":
                from voiceime.formatter.engine import MlxFormatter

                formatter = MlxFormatter(args.formatter, use_prefix_cache=True)
                formatter_name = Path(args.formatter).name
        engine = RecognitionEngine(
            transcriber=transcriber,
            glossary=glossary,
            formatter_kind=formatter_kind,
            formatter=formatter,
            history_path=args.history,
            asr_name=args.asr,
            formatter_name=formatter_name,
            asr_accepts_glossary=spec.backend in GLOSSARY_BACKENDS,
            asr_hint_mode=args.asr_hint_mode,
            asr_hint_format=asr_hint_format(spec),
            two_pass_policy=args.two_pass_policy,
            aux_transcriber=aux_transcriber,
            formatter_input=args.formatter_input,
            formatter_max_glossary=args.formatter_max_glossary,
        )
        engine.serve(sys.stdin, sys.stdout)
    except Exception as error:
        if engine is None:
            for target in (transcriber, aux_transcriber):
                close_transcriber = getattr(target, "close", None)
                if callable(close_transcriber):
                    try:
                        close_transcriber()
                    except Exception:
                        pass
        logging.exception("認識エンジンを起動できませんでした")
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
