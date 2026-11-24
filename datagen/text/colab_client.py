"""Colab上のvLLMサーバーへ依頼のJSONLを並列に送り、出力をJSONLへ追記する。

実行場所：Colab VMの上（`colab_server.sh` でサーバーを起動した後に nohup で動かす）。
途中で止まっても再開できるよう、出力済みのidは読み飛ばし、1件終わるごとに追記する。

使い方：python colab_client.py <依頼.jsonl または .jsonl.gz> <出力.jsonl> [--concurrency 128]
依頼のファイルは同じシステムプロンプトを繰り返すため、アップロードの上限を超えないようgzipで圧縮して渡せる。
依頼の各行：{"id", "messages", "temperature", "top_p", "top_k", "max_tokens", "seed"}
出力の各行：{"id", "text", "finish_reason", "prompt_tokens", "completion_tokens"}
"""

import argparse
import asyncio
import gzip
import json
import time
from pathlib import Path

from openai import AsyncOpenAI


async def run_one(client: AsyncOpenAI, req: dict) -> dict:
    """依頼1件をサーバーへ送り、出力の行を返す。思考モードは使わない。"""
    resp = await client.chat.completions.create(
        model="teacher",
        messages=req["messages"],
        temperature=req.get("temperature", 1.0),
        top_p=req.get("top_p", 0.95),
        max_tokens=req.get("max_tokens", 4096),
        seed=req.get("seed"),
        extra_body={"top_k": req.get("top_k", 64), "chat_template_kwargs": {"enable_thinking": False}},
    )
    choice = resp.choices[0]
    return {
        "id": req["id"],
        "text": choice.message.content,
        "finish_reason": choice.finish_reason,
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests")
    parser.add_argument("output")
    parser.add_argument("--concurrency", type=int, default=128)
    args = parser.parse_args()

    out_path = Path(args.output)
    done = set()
    if out_path.exists():
        done = {json.loads(l)["id"] for l in out_path.open() if l.strip()}
    opener = gzip.open if args.requests.endswith(".gz") else open
    with opener(args.requests, "rt", encoding="utf-8") as f:
        reqs = [json.loads(l) for l in f if l.strip()]
    todo = [r for r in reqs if r["id"] not in done]
    print(f"total={len(reqs)} done={len(done)} todo={len(todo)}", flush=True)

    client = AsyncOpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY", timeout=1800)
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()
    n_ok = n_err = out_tokens = 0
    with out_path.open("a", encoding="utf-8") as f:

        async def worker(req: dict) -> None:
            nonlocal n_ok, n_err, out_tokens
            async with sem:
                try:
                    row = await run_one(client, req)
                except Exception as e:  # 失敗した依頼は記録して次へ進み、再実行で拾う
                    n_err += 1
                    print(f"error id={req['id']}: {e!r}", flush=True)
                    return
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                n_ok += 1
                out_tokens += row["completion_tokens"]
                if n_ok % 50 == 0:
                    dt = time.time() - t0
                    print(f"progress ok={n_ok} err={n_err} elapsed={dt:.0f}s out_tok/s={out_tokens / dt:.0f}", flush=True)

        await asyncio.gather(*(worker(r) for r in todo))
    dt = time.time() - t0
    print(f"finished ok={n_ok} err={n_err} elapsed={dt:.0f}s out_tokens={out_tokens}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
