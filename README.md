# Hermes Halo Companion

**A Hermes-owned companion for the Brilliant Labs Halo AR glasses** — capture at the sensor level, remember with Vestige, act with meds alerts and translation. Built against the real `halo_emulator` (Lua 5.3, 256×256 virtual display) — **no hardware purchase needed** to develop and demo.

## What it does (v8 demo, ship-ready)

A 26.4s full-loop demo: capture → Vestige memory write → meds double-dose alert with sound → **Korean ASR "약 먹을 시간이야" with correct Hangul rendering** → **live translation "It's time to take your medicine"** on the 256×256 display.

- **Capture**: voice / IMU / button events from Halo (audio, photo, tap)
- **Memory**: `vestige-store/` — FSRS-6 forgetting curve, surprise gating, retroactive backfill, dreams
- **Meds alert**: double-dose detection + reminder + sound (`lua/meds_alert.lua`)
- **Korean pipeline**: correct UTF-8 handling (fixed the emulator's mojibake + Malgun font rendering)

## Architecture

- **Path C**: Halo as a Hermes-managed peripheral — NO dependency on Noa/Narrative's opaque memory (their "memory" is stateless prompt-context injection; we own the store)
- `packages/halo_companion/` — our code (meds controller, Lua alert script, tests)
- `packages/halo_voice_pipeline/` — voice pipeline
- Vendored SDK: `brilliant_ble` / `brilliant_msg` / `brilliant_sdk` / `halo_emulator` (patched: display font + UTF-8 fixes)
- `vestige-store/` — the memory (system of record)

## Run

```bash
uv sync --all-packages
uv run pytest packages/brilliant_msg/tests/   # hardware-free tests
# full demo:
uv run python scripts/t6_full_loop_demo.py    # or use halo-emulator REPL: halo-emulator ./app/
```

## Why

Neurodivergent-first design (ADHD/ASD): meds double-dose alerts, steering-not-overwhelming, pull-first attention policy, max-help default with privacy mode. This is the LifeOS wearable peripheral — ambient context (what's happening) feeding a sovereign memory companion.

## Status

Pre-interview build (2026-08-13). Ship-ready demo: `artifacts/t6-v8/demo_full_loop.mp4`. Stage-2 planned: NeuroSkill BCI (EEG focus/emotion state) as the brain-state layer.

## License

MIT (our code). Vendored SDK packages retain their original licenses.
