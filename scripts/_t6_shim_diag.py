import asyncio, httpx, os, json

BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODEL = "google/gemini-3.5-flash"

async def probe(model, prompt, max_tokens=None):
    body = {"model":model,"stream":False,"messages":[{"role":"user","content":prompt}]}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
        r = await c.post(f"{BASE}/chat/completions",
            headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},
            json=body)
        j = r.json()
        ch = j["choices"][0]
        usage = j.get("usage", {})
        return (r.status_code,
                repr(ch["message"]["content"][:80]),
                usage.get("completion_tokens"),
                ch.get("finish_reason"))

async def main():
    # long-answer prompt, no max_tokens (default) vs explicit large max_tokens
    long_prompt = "List 10 Korean cities and their English names. Be verbose."
    print("default  :", await probe(MODEL, long_prompt))
    print("maxtok500:", await probe(MODEL, long_prompt, 500))
    print("short def :", await probe(MODEL, "Say CAT"))
    print("short mx50:", await probe(MODEL, "Say CAT", 50))

asyncio.run(main())
