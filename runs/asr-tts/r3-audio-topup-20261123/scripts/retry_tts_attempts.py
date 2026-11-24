#!/usr/bin/env python3
"""1件のTTSを、それまでと重ならない試行番号で再生成する。"""

import sys

import synthesize as tts


def main() -> None:
    """声・速さ・長さの条件をそのまま使い、試行番号だけ先へ進める。"""
    offset = int(sys.argv.pop(1))
    synthesize_rows = tts.synthesize_rows
    build_record = tts.build_record

    def retry_single(engine, rows, plans, args, attempt):
        """1件の再試行に限り、元のseed導出処理へ続きの番号を渡す。"""
        if len(rows) != 1:
            raise ValueError("試行番号を継続できるのは1件の再生成のみ")
        return synthesize_rows(engine, rows, plans, args, attempt + offset)

    def record_attempt(row, plan, duration_s, attempt):
        """metadataに元のseed導出と同じ試行番号を記録する。"""
        return build_record(row, plan, duration_s, attempt + offset)

    tts.synthesize_rows = retry_single
    tts.build_record = record_attempt
    tts.main()


if __name__ == "__main__":
    main()
