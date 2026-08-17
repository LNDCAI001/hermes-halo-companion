import asyncio, httpx, os, json

BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODELS = ["google/gemini-3.5-flash", "openai/gpt-5.6-sol", "anthropic/claude-opus-5"]

async def raw_nonstream(model, prompt):
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
        r = await c.post(f"{BASE}/chat/completions",
            headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},
            json={"model":model,"stream":False,"messages":[{"role":"user","content":prompt}]})
        return r.status_code, r.text

async def main():
    for model in MODELS:
        try:
            sc, txt = await raw_nonstream(model, "Reply with the single word: CAT")
            print(f"\n===== {model}  HTTP {sc} =====")
            print(txt[:600])
        except Exception as e:
            print(f"\n===== {model}  ERR {type(e).__name__}: {e}")

asyncio.run(main())
