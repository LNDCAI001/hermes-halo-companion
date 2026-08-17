import asyncio, httpx, os, json

BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODEL = "google/gemini-3.5-flash"

async def stream_translate(prompt):
    out = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
        async with c.stream("POST", f"{BASE}/chat/completions",
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"},
            json={"model":MODEL,"stream":True,"messages":[{"role":"user","content":prompt}]}) as r:
            if r.status_code != 200:
                return f"HTTP {r.status_code}"
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        d = json.loads(line[6:])["choices"][0]["delta"].get("content","")
                        out += d
                    except Exception: pass
    return out.strip() or "<EMPTY>"

async def nonstream_translate(prompt):
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
        r = await c.post(f"{BASE}/chat/completions",
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"},
            json={"model":MODEL,"stream":False,"messages":[{"role":"user","content":prompt}]})
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.text[:200]}"
        j = r.json()
        return j["choices"][0]["message"]["content"].strip() or "<EMPTY>"

async def main():
    ko = "Translate the following Korean phrase to English. Output only the English translation.\nKorean: 약 먹을 시간이야"
    en = "What is 2+2? Reply with just the number."
    print("[KO stream]  ->", repr(await stream_translate(ko)))
    print("[KO nonstrm] ->", repr(await nonstream_translate(ko)))
    print("[EN stream]  ->", repr(await stream_translate(en)))

asyncio.run(main())
