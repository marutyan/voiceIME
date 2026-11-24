#!/usr/bin/env python3
"""docs/engine-protocol.md に従って応答するXCTest用の偽認識エンジン。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def append_log(log_path: str | None, line: str) -> None:
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    log_path = os.environ.get("FAKE_ENGINE_LOG_FILE")
    crash_marker = os.environ.get("FAKE_ENGINE_CRASH_ONCE_MARKER")
    if crash_marker:
        marker_path = Path(crash_marker)
        if not marker_path.exists():
            marker_path.write_text("crashed-once\n", encoding="utf-8")
            sys.stderr.write("simulated startup crash\n")
            sys.stderr.flush()
            return 42

    behavior = os.environ.get("FAKE_ENGINE_BEHAVIOR", "normal")
    emit({"type": "ready", "asr": "fake-asr-v1", "formatter": "fake-fmt-v1"})

    sessions: dict[str, dict] = {}

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        append_log(log_path, line)
        msg = json.loads(line)
        msg_type = msg.get("type")

        if msg_type == "start":
            sid = msg["session_id"]
            sessions[sid] = {
                "app": msg.get("app", {}),
                "screen_text": msg.get("screen_text"),
                "segments": [],
            }
        elif msg_type == "segment":
            sid = msg["session_id"]
            seq = msg["seq"]
            wav_path = msg["wav_path"]
            exists = os.path.isfile(wav_path)
            size = os.path.getsize(wav_path) if exists else -1
            if sid in sessions:
                sessions[sid]["segments"].append((seq, wav_path, exists, size))
                emit({"type": "partial", "session_id": sid, "seq": seq, "text": f"区間{seq}"})
        elif msg_type == "cancel":
            sid = msg["session_id"]
            sessions.pop(sid, None)
        elif msg_type == "finish":
            sid = msg["session_id"]
            mode = msg.get("mode", "formatted")
            session = sessions.pop(sid, None)
            if session is None:
                emit({"type": "error", "session_id": sid, "message": "unknown session"})
                continue

            if behavior == "crash_on_finish":
                sys.stderr.write("simulated finish crash\n")
                sys.stderr.flush()
                return 9
            if behavior == "error_with_raw":
                emit(
                    {
                        "type": "error",
                        "session_id": sid,
                        "message": "整形タイムアウト",
                        "raw_text": "えーと 整形前の文",
                    }
                )
                continue
            if behavior == "error_without_raw":
                emit(
                    {
                        "type": "error",
                        "session_id": sid,
                        "message": "認識に失敗しました",
                    }
                )
                continue

            seqs = [str(item[0]) for item in session["segments"]]
            all_exist = all(item[2] and item[3] >= 44 for item in session["segments"])
            raw_text = " ".join(f"えーと 区間{s}" for s in seqs)
            if behavior == "format_fallback" or mode == "raw":
                emit(
                    {
                        "type": "result",
                        "session_id": sid,
                        "raw_text": raw_text,
                        "text": raw_text,
                        "format_ok": mode == "raw",
                        "asr_latency_s": 0.12,
                        "format_latency_s": 0.0,
                        "total_latency_s": 0.15,
                    }
                )
            else:
                formatted = (
                    f"整形済み({','.join(seqs)}):wav_ok={str(all_exist).lower()}"
                )
                emit(
                    {
                        "type": "result",
                        "session_id": sid,
                        "raw_text": raw_text,
                        "text": formatted,
                        "format_ok": True,
                        "asr_latency_s": 0.12,
                        "format_latency_s": 0.18,
                        "total_latency_s": 0.31,
                    }
                )
        elif msg_type == "shutdown":
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
