"""OpenAI互換のvLLMへ文章生成要求を送り、成功行を逐次保存する。"""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _endpoint(base_url: str) -> str:
    """vLLMのbase URLからchat completionsのendpointを作る。"""
    base = base_url.rstrip("/")
    return base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"


def _post_request(
    endpoint: str,
    request: dict[str, Any],
    model: str,
    api_key: str | None,
    timeout: float,
) -> dict[str, Any]:
    """教師LLMへ1要求を送り、出力文とtoken数を返す。"""
    payload = {
        "model": model,
        "messages": request["messages"],
        "temperature": request.get("temperature", 1.0),
        "top_p": request.get("top_p", 0.95),
        "max_tokens": request.get("max_tokens", 4000),
        "top_k": request.get("top_k", 64),
        "seed": request.get("seed"),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(http_request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    choice = result["choices"][0]
    usage = result.get("usage") or {}
    return {
        "id": request["id"],
        "text": choice["message"].get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }


async def _run_one(
    endpoint: str,
    request: dict[str, Any],
    model: str,
    api_key: str | None,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    """一時的な通信・サーバーエラーを指数間隔で再試行する。"""
    for attempt in range(retries + 1):
        try:
            return await asyncio.to_thread(_post_request, endpoint, request, model, api_key, timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as error:
            if attempt >= retries:
                raise RuntimeError(type(error).__name__) from error
            await asyncio.sleep(min(2**attempt, 30))
    raise AssertionError("retry loop ended unexpectedly")


def _read_requests(path: Path) -> list[dict[str, Any]]:
    """JSONLまたはgzip JSONLの要求を読む。"""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _read_done(path: Path) -> set[str]:
    """出力済み要求idを読み、再開時に成功済みの要求を飛ばす。"""
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: 出力JSONLが壊れています。再開前に末尾を修復してください") from error
            if isinstance(row.get("id"), str):
                done.add(row["id"])
    return done


async def run(
    requests_path: Path,
    output_path: Path,
    base_url: str,
    model: str,
    concurrency: int,
    retries: int,
    timeout: float,
    api_key: str | None = None,
) -> None:
    """成功済みidを再利用し、残りの要求を並列に実行して逐次追記する。"""
    if concurrency < 1 or retries < 0:
        raise ValueError("concurrencyは1以上、retriesは0以上が必要です")
    # asyncio.to_threadの既定worker数では、指定した同時要求数に届かないことがある。
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="text-v3-client")
    )
    requests = _read_requests(requests_path)
    done = _read_done(output_path)
    pending = [request for request in requests if request["id"] not in done]
    print(f"total={len(requests)} done={len(done)} todo={len(pending)}", flush=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    endpoint = _endpoint(base_url)
    started = time.monotonic()
    successes = 0
    failures = 0

    with output_path.open("a", encoding="utf-8") as output:
        async def worker(request: dict[str, Any]) -> None:
            nonlocal successes, failures
            async with semaphore:
                try:
                    row = await _run_one(endpoint, request, model, api_key, timeout, retries)
                except RuntimeError as error:
                    failures += 1
                    print(f"failed id={request['id']} after retries ({error})", flush=True)
                    return
                async with write_lock:
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    output.flush()
                    successes += 1
                    if successes % 50 == 0:
                        elapsed = max(time.monotonic() - started, 0.001)
                        print(f"progress ok={successes} failed={failures} elapsed={elapsed:.0f}s", flush=True)

        await asyncio.gather(*(worker(request) for request in pending))
    elapsed = max(time.monotonic() - started, 0.001)
    print(f"finished ok={successes} failed={failures} elapsed={elapsed:.0f}s", flush=True)
    if failures:
        raise SystemExit(2)


def main() -> None:
    """vLLM接続、並列数、再試行、再開用ファイルをCLIから受け取る。"""
    parser = argparse.ArgumentParser(description="vLLM OpenAI互換サーバーへ生成要求を送る")
    parser.add_argument("requests", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url", required=True, help="例: http://faculty:8000/v1")
    parser.add_argument("--model", default="teacher")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--retries", type=int, default=3, help="初回送信後に再試行する回数")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY"))
    args = parser.parse_args()
    asyncio.run(
        run(
            args.requests,
            args.output,
            args.base_url,
            args.model,
            args.concurrency,
            args.retries,
            args.timeout,
            args.api_key,
        )
    )


if __name__ == "__main__":
    main()
