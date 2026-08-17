"""Probe the pplx shim chat endpoint with raw httpx streaming.

Writes SSE chunks to a file so buffering can't swallow output.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
URL = "http://localhost:8124/v1/chat/completions"
OUT = Path("artifacts/t6/_shim_probe.txt")


async def probe(model: str, content: str, out_file) -> None:
    t0 = time.perf_counter()
    out_file.write(f"=== {model} ===\n")
    out_file.flush()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
                json={"model": model, "stream": True, "messages": [{"role": "user", "content": content}]},
            ) as resp:
                out_file.write(f"status={resp.status_code} after {time.perf_counter()-t0:.1f}s\n")
                out_file.flush()
                text = ""
                chunk_count = 0
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        payload = line[6:]
                        if payload == "[DONE]":
                            break
                        try:
                            delta = json.loads(payload)["choices"][0]["delta"].get("content", "")
                            if delta:
                                text += delta
                                chunk_count += 1
                        except Exception as exc:
                            out_file.write(f"parse err: {exc} raw={line[:120]}\n")
                out_file.write(f"RESULT: {text.strip()!r} chunks={chunk_count} total={time.perf_counter()-t0:.1f}s\n")
                out_file.flush()
    except Exception as exc:
        out_file.write(f"ERR {type(exc).__name__}: {str(exc)[:300]} after {time.perf_counter()-t0:.1f}s\n")
        out_file.flush()


async def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        await probe("google/gemini-3.5-flash", "Translate to English, one short phrase: 약 먹을 시간이야", f)
        await probe("openai/gpt-5.6-sol", "Translate to English, one short phrase: 약 먹을 시간이야", f)
    print(f"done -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
