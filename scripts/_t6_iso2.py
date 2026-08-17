import importlib.util as u
for m in ["deep_translator","argostranslate","googletrans","translate","papago"]:
    print(m, "OK" if u.find_spec(m) else "missing")
# Also test gemini with pure English to isolate empty-content cause
import asyncio, httpx, json, os
BASE=os.environ.get("PPLX_SHIM_BASE","http://localhost:8123/v1")
KEY=os.environ.get("PPLX_SHIM_KEY","pplx-shim")
async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0,connect=10.0)) as c:
        async with c.stream("POST", f"{BASE}/chat/completions",
            headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},
            json={"model":"google/gemini-3.5-flash","stream":True,
                  "messages":[{"role":"user","content":"Reply with only the word: CAT"}]}) as r:
            out=""
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line!="data: [DONE]":
                    try: out+=json.loads(line[6:])["choices"][0]["delta"].get("content","")
                    except: pass
            print("ENGLISH PROMPT ->", repr(out.strip()))
asyncio.run(main())
