"""
T6: Full capture-loop demo video + artifacts for the Brilliant Labs email.

Runs the complete Halo companion loop against the emulator and records it:

  1. T2/T3 pipeline  -- emulator sensor capture -> event envelope -> Vestige
     (fresh project-local store; smart_ingest via vestige-mcp)
  2. T4 meds alert   -- tap capture (confirm + double-dose) + scheduled
     reminder with the native sound primitive
  3. T5 translation  -- Korean audio (edge-tts) -> ASR (faster-whisper) ->
     English caption attempt via the local pplx shim (gemini-3.5-flash)

The video is the honest record of what works today:
  * capture -> Vestige, meds confirm/double-dose, reminder + native sound  => PASS
  * Korean ASR (faster-whisper)                                              => PASS
  * Korean -> English via the local shim                                     => FAILS
      (shim returns HTTP 200 finish_reason=stop but EMPTY content; the
       translation bridge is NOT native/functional -- the key T6 finding)
The caption scene therefore shows the ASR output plus the empty shim result,
and writes a machine-readable report.json documenting the failure.

Rendered to the 256x256 emulator framebuffer and screen-recorded to
`artifacts/t6/demo_full_loop.mp4` (imageio + bundled ffmpeg; GIF fallback).

Usage (from the workspace root, with the project venv):
    .venv/Scripts/python.exe scripts/t6_full_loop_demo.py [outdir]

Requires:
  - the pplx shim on :8123 (PPLX_SHIM_KEY env) for translation
  - edge-tts + faster-whisper (installed) for the T5 audio leg
  - vestige-mcp on PATH with VESTIGE_DATA_DIR -> project vestige-store
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

os.environ.pop("PYTHONPATH", None)

from halo_companion.controller import MedSchedule, MedsController  # noqa: E402
from halo_emulator import EmulatorBrilliantMsg, HaloEmulator  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VESTIGE_DATA_DIR = PROJECT_ROOT / "vestige-store"
SHIM_BASE = os.environ.get("PPLX_SHIM_BASE", "http://localhost:8123/v1")
SHIM_KEY = os.environ.get("PPLX_SHIM_KEY", "pplx-shim")
SHIM_MODEL = os.environ.get("PPLX_SHIM_MODEL", "google/gemini-3.5-flash")
KOREAN_PHRASE = "약 먹을 시간이야"
EXPECTED_CAPTION = "It's time to take your medicine."


# --------------------------------------------------------------------------- #
# Vestige (T3) -- write an event via vestige-mcp smart_ingest                   #
# --------------------------------------------------------------------------- #
class VestigeWriter:
    """Minimal MCP stdio client for vestige-mcp's smart_ingest tool."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        env = dict(os.environ)
        env["VESTIGE_DATA_DIR"] = str(self.data_dir)
        self.proc = await asyncio.create_subprocess_exec(
            "cmd", "/c", "vestige-mcp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

    async def _rpc(self, method: str, params: dict, req_id: int) -> dict:
        assert self.proc is not None and self.proc.stdout is not None
        assert self.proc.stdin is not None
        line = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        self.proc.stdin.write((line + "\n").encode())
        await self.proc.stdin.drain()
        while True:
            raw = await asyncio.wait_for(self.proc.stdout.readline(), timeout=60)
            if not raw:
                raise RuntimeError("vestige-mcp closed stdout")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == req_id:
                return msg

    async def ingest(self, content: str, *, source: str, tags: list[str]) -> dict:
        await self._rpc(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {},
             "clientInfo": {"name": "t6-demo", "version": "1.0"}},
            1,
        )
        self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        await self.proc.stdin.drain()
        result = await self._rpc("tools/call", {
            "name": "smart_ingest",
            "arguments": {"content": content, "source": source, "tags": tags,
                          "forceCreate": True, "node_type": "event"},
        }, 2)
        if "error" in result and result["error"]:
            raise RuntimeError(f"smart_ingest failed: {result['error']}")
        return result.get("result", {})

    async def close(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# T5 -- Korean audio -> ASR -> translation attempt via the shim                 #
# --------------------------------------------------------------------------- #
async def make_korean_audio(path: Path) -> Path:
    """Synthesize the Korean phrase with edge-tts (SunHi female voice)."""
    import edge_tts
    tts = edge_tts.Communicate(KOREAN_PHRASE, "ko-KR-SunHiNeural")
    await tts.save(str(path))
    return path


def asr_transcribe(audio_path: Path) -> tuple[str, dict]:
    """faster-whisper ASR (ko). Synchronous, CPU int8 base model."""
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), language="ko", vad_filter=True)
    korean_text = " ".join(s.text for s in segments).strip()
    return korean_text, {"source_language": info.language, "asr_model": "faster-whisper base"}


async def translate_via_shim(korean_text: str) -> dict:
    """Attempt ko->en via the local pplx shim. Returns raw result + timing."""
    import httpx

    if not korean_text:
        return {"attempted": False, "reason": "empty ASR output",
                "content": "", "status_code": None, "error": None}

    prompt = (
        "Translate the following Korean phrase to English. "
        "Output only the English translation, no quotes or explanation.\n"
        f"Korean: {korean_text}"
    )
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            async with client.stream(
                "POST", f"{SHIM_BASE}/chat/completions",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {SHIM_KEY}"},
                json={"model": SHIM_MODEL, "stream": True,
                      "messages": [{"role": "user", "content": prompt}]},
            ) as resp:
                status = resp.status_code
                caption = ""
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            delta = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                            caption += delta
                        except Exception:
                            pass
        elapsed = time.perf_counter() - t0
        return {
            "attempted": True,
            "status_code": status,
            "content": caption.strip(),
            "elapsed_s": round(elapsed, 2),
            "empty": (caption.strip() == ""),
            "error": None,
        }
    except Exception as exc:  # ReadTimeout, connection refused, etc.
        elapsed = time.perf_counter() - t0
        return {
            "attempted": True,
            "status_code": None,
            "content": "",
            "elapsed_s": round(elapsed, 2),
            "empty": True,
            "error": f"{type(exc).__name__}: {exc}",
        }


# --------------------------------------------------------------------------- #
# Main demo                                                                     #
# --------------------------------------------------------------------------- #
async def run(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    sandbox = outdir / "_sandbox"
    results: dict = {"translation_not_native": None, "scenes": {}}
    emu = HaloEmulator(sandbox_dir=sandbox, print_handler=print)
    frame = EmulatorBrilliantMsg(emu)

    ctrl = MedsController(
        frame,
        clock=lambda: datetime(2026, 8, 13, 9, 0, 0),
        schedules=[MedSchedule("aspirin", [dtime(9, 0)])],
    )
    await ctrl.start()

    # Start the video recorder (imageio mp4 via bundled ffmpeg).
    try:
        import imageio  # noqa: F401
        video_path = outdir / "demo_full_loop.mp4"
    except ImportError:
        video_path = outdir / "demo_full_loop.gif"
    emu.start_recording(fps=15)

    try:
        # ----- Scene 1: T2/T3 capture pipeline -> Vestige ------------------
        print("[t6] scene 1: capture -> Vestige")
        await ctrl.process_tap("aspirin")
        await asyncio.sleep(1.4)
        p_taken = outdir / "scene1_taken.png"
        emu.get_framebuffer().save(p_taken)
        results["scenes"]["taken"] = str(p_taken)

        # Write the sensor event to the fresh Vestige store.
        writer = VestigeWriter(VESTIGE_DATA_DIR)
        await writer.start()
        try:
            ingest = await writer.ingest(
                "took my medication at 8:14am",
                source="halo:demo",
                tags=["lifeos", "meds", "demo"],
            )
            results["vestige_ingest"] = ingest
            print(f"[t6] vestige smart_ingest -> {json.dumps(ingest, ensure_ascii=False)[:200]}")
        finally:
            await writer.close()

        # ----- Scene 2: T4 meds alert (double-dose) ------------------------
        print("[t6] scene 2: double-dose alert")
        await ctrl.process_tap("aspirin")  # 2nd capture same day
        await asyncio.sleep(1.4)
        p_double = outdir / "scene2_double_dose.png"
        emu.get_framebuffer().save(p_double)
        results["scenes"]["double_dose"] = str(p_double)

        # ----- Scene 3: T4 reminder + native sound -------------------------
        print("[t6] scene 3: scheduled reminder + sound")
        await ctrl.fire_reminder("aspirin")
        await asyncio.sleep(1.4)
        p_reminder = outdir / "scene3_reminder.png"
        emu.get_framebuffer().save(p_reminder)
        results["scenes"]["reminder"] = str(p_reminder)
        results["audio_events"] = len(ctrl.audio_events)

        # ----- Scene 4: T5 Korean translation ------------------------------
        print("[t6] scene 4: Korean voice -> English caption")
        audio = outdir / "korean_phrase.wav"
        await make_korean_audio(audio)
        # ASR runs synchronously; yield to the event loop around it.
        korean_text, asr_meta = await asyncio.to_thread(asr_transcribe, audio)
        print(f"[t6] ASR (faster-whisper) -> {korean_text!r}  ({asr_meta})")

        # Push the ASR-detected Korean onto the device display.
        # Split into short lines so it fits the 256px-wide display
        # (long Korean strings overflow/clip on one line).
        ko_lines = korean_text
        # wrap at ~8 chars per line for the 24px font on 256px width
        def _wrap(s: str, n: int = 8) -> str:
            import textwrap
            return "\n".join(textwrap.wrap(s, n) or [s])
        await ctrl._frame.send_message(
            0x0A, __import__("brilliant_msg").TxPlainText(f"ASR:\n{_wrap(ko_lines)}").pack())
        await asyncio.sleep(1.2)
        p_asr = outdir / "scene4_asr.png"
        emu.get_framebuffer().save(p_asr)
        results["scenes"]["asr"] = str(p_asr)

        # Attempt the translation through the local shim (the real bridge).
        shim = await translate_via_shim(korean_text)
        print(f"[t6] shim translate -> {json.dumps(shim, ensure_ascii=False)[:240]}")
        results["translation_not_native"] = shim

        # Render the HONEST outcome on the device: ASR worked, bridge empty.
        verdict = "TRANSLATION BRIDGE: EMPTY RESPONSE" if shim.get("empty") else f"caption: {shim.get('content')}"
        def _wrap2(s: str, n: int = 14) -> str:
            import textwrap
            return "\n".join(textwrap.wrap(s, n) or [s])
        await ctrl._frame.send_message(
            0x0A, __import__("brilliant_msg").TxPlainText(
                f"ASR ok\nKO: {_wrap2(korean_text, 7)}\nEN(bridge):\n{_wrap2(shim.get('content') or '<empty>', 14)}").pack())
        await asyncio.sleep(1.6)
        p_caption = outdir / "scene4_translate.png"
        emu.get_framebuffer().save(p_caption)
        results["scenes"]["translate"] = str(p_caption)
        results["translation"] = {"asr_korean": korean_text, "asr_meta": asr_meta, "shim": shim}

        results["artifacts"] = {
            "video": str(video_path),
            "taken": str(p_taken),
            "double_dose": str(p_double),
            "reminder": str(p_reminder),
            "asr": str(p_asr),
            "translate": str(p_caption),
            "audio": str(audio),
        }
    finally:
        emu.stop_recording(video_path)
        await ctrl.stop()

    (outdir / "report.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/t6")
    results = asyncio.run(run(outdir))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
