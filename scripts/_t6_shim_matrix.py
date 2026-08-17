import asyncio, httpx, os, json

BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODELS = ["google/gemini-3.5-flash", "openai/gpt-5.6-sol", "anthropic/claude-opus-5"]
PROMPTS = {
    "en_hello": "Say 'hello world' and nothing else.",
    "ko_translate": "Translate the following Korean phrase to English. Output only the English translation.\nKorean: 약 먹을 시간이야",
    "ko_bare": "Translate to English: 약 먹을 시간이야",
}

async def one(model, prompt):
    out = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
        async with c.stream("POST", f"{BASE}/chat/completions",
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"},
            json={"model":model,"stream":True,"messages":[{"role":"user","content":prompt}]}) as r:
            if r.status_code != 200:
                return f"HTTP {r.status_code}"
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        d = json.loads(line[6:])["choices"][0]["delta"].get("content","")
                        out += d
                    except Exception:
                        pass
    return out.strip() or "<EMPTY>"

async def main():
    for pname, ptext in PROMPTS.items():
        for model in MODELS:
            try:
                res = await one(model, ptext)
            except Exception as e:
                res = f"<ERR {e}>"
            print(f"[{pname} | {model}] -> {res[:80]!r}")

asyncio.run(main())
