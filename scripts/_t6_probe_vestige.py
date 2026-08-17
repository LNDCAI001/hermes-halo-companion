"""Probe vestige-mcp: initialize, list tools, dump smart_ingest schema."""
from __future__ import annotations

import asyncio
import json
import os
import sys

VESTIGE_DATA_DIR = r"C:\Users\Dachi\hermes-halo-companion\vestige-store"


class MCPClient:
    def __init__(self) -> None:
        self.proc = None
        self._reader = None
        self._writer = None

    async def start(self) -> None:
        env = dict(os.environ)
        env["VESTIGE_DATA_DIR"] = VESTIGE_DATA_DIR
        self.proc = await asyncio.create_subprocess_exec(
            "cmd", "/c", "vestige-mcp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader = self.proc.stdout
        self._writer = self.proc.stdin

    async def request(self, method: str, params: dict, req_id: int) -> dict:
        line = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        self._writer.write((line + "\n").encode())
        await self._writer.drain()
        while True:
            raw = await asyncio.wait_for(self._reader.readline(), timeout=60)
            if not raw:
                raise RuntimeError("vestige-mcp closed stdout")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == req_id:
                return msg

    async def close(self) -> None:
        try:
            self.proc.terminate()
        except Exception:
            pass


async def main() -> int:
    client = MCPClient()
    await client.start()
    try:
        init = await client.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "t6-probe", "version": "1.0"},
        }, 1)
        print("INIT:", json.dumps(init, ensure_ascii=False)[:400])
        # notifications have no id; send raw (must be bytes on Windows)
        client._writer.write(
            (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
        )
        await client._writer.drain()

        tools = await client.request("tools/list", {}, 2)
        for t in tools.get("result", {}).get("tools", []):
            print("TOOL:", t["name"], "|", t.get("description", "")[:120])
            if t["name"] == "smart_ingest":
                print("SMART_INGEST_SCHEMA:", json.dumps(t.get("inputSchema", {}), indent=1)[:2000])
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
