import asyncio, httpx, json, os, time
BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODEL = os.environ.get("PPLX_SHIM_MODEL", "google/gemini-3.5-flash")
KR = "약 먹을 시간이야"

async def main():
    prompt = ("Translate the following Korean phrase to English. "
              "Output only the English translation, no quotes or explanation.\n"
              f"Korean: {KR}")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as c:
        async with c.stream("POST", f"{BASE}/chat/completions",
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"},
            json={"model":MODEL,"stream":True,"messages":[{"role":"user","content":prompt}]}) as r:
            print("status", r.status_code, f"after {time.perf_counter()-t0:.1f}s")
            out=""
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        d=json.loads(line[6:])["choices"][0]["delta"].get("content","")
                        out+=d
                    except Exception: pass
    print("CAPTION:", out.strip(), f"({(time.perf_counter()-t0):.1f}s)")

asyncio.run(main())
