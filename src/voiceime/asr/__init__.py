"""ASRの候補を共通の形（音声→文字、用語集のヒントは任意）で呼び出して比べるためのパッケージ。

各方式の実装は`base.Transcriber`の形にそろえ、`systems.SYSTEMS`に名前で登録する。
実行は`python -m voiceime.asr.run`で行い、結果を`docs/PLAN.md`の推論結果の形式で保存する。
"""
