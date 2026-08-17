import asyncio, httpx, os

BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
MODEL = os.environ.get("PPLX_SHIM_MODEL", "google/gemini-3.5-flash")

async def main():
    prompt = "Translate the following Korean phrase to English. Output only the English translation.\nKorean: 약 먹을 시간이야"
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as c:
        async with c.stream("POST", f"{BASE}/chat/completions",
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"},
            json={"model":MODEL,"stream":True,"messages":[{"role":"user","content":prompt}]}) as r:
            print("STATUS", r.status_code, "CT", r.headers.get("content-type"))
            buf = b""
            n = 0
            async for chunk in r.aiter_raw():
                buf += chunk
                n += 1
                if n <= 12:
                    print(f"--- chunk {n} ---")
                    print(chunk[:400].decode("utf-8", "replace"))
            print(f"TOTAL chunks={n} bytes={len(buf)}")
            # Save full raw
            with open("artifacts/t6/_raw_shim.txt","wb") as f:
                f.write(buf)

asyncio.run(main())
