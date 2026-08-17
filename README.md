# Hermes Halo Companion

**A Hermes-owned companion for the Brilliant Labs Halo AR glasses** — capture at the sensor level, remember with Vestige, act with meds alerts and translation. Built against the real `halo_emulator` (Lua 5.3, 256×256 virtual display) — **no hardware purchase needed** to develop and demo.

## What it does (v8 demo, ship-ready)

A 26.4s full-loop demo: capture → Vestige memory write → meds double-dose alert with sound → **Korean ASR "약 먹을 시간이야" with correct Hangul rendering** → **live translation "It's time to take your medicine"** on the 256×256 display.

- **Capture**: voice / IMU / button events from Halo (audio, photo, tap) — each event carries `consent_state`, `sensitivity`, and `retention_class` metadata
- **Memory**: `vestige-store/` — FSRS-6 forgetting curve, surprise gating, retroactive backfill, dreams. Store is project-isolated via `VESTIGE_DATA_DIR`
- **Meds alert**: double-dose detection + reminder + sound (`lua/meds_alert.lua`)
- **Privacy mode**: `controller.privacy_mode = True` suppresses med names on the device display (shows `[PRIVATE]` instead). Toggle at runtime.
- **Data deletion**: `controller.clear_all_data()` wipes all in-memory capture records. For persistent Vestige store deletion, use the Vestige MCP `smart_delete` API.
- **Korean pipeline**: correct UTF-8 handling (fixed the emulator's mojibake + Malgun font rendering)

## What it does NOT do (honest boundaries)

- **No NeuroSkill BCI integration** — Stage-2 planned, not implemented
- **No hardware-dependent features** — everything runs against the emulator
- **Translation bridge is not native** — the pplx shim returns empty content; ASR works, translation does not (documented in `artifacts/t6-v8/report.json`)
- **No persistent privacy mode** — privacy mode is in-memory only; restarting the controller resets it
- **No user-facing deletion UI** — `clear_all_data()` is a programmatic API, not a user prompt

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

Pre-interview build (2026-08-13). Ship-ready demo: `artifacts/t6-v8/demo_full_loop.mp4`. Stage-2 planned: NeuroSkill BCI (EEG focus/emotion state) as the brain-state layer — **not yet implemented**.

## License

MIT (our code). Vendored SDK packages retain their original licenses.
