---
title: Hermes Halo Companion — Project Seed
created: 2026-08-13
type: project-seed
status: pre-interview
---

# Purpose

Dedicated folder + dedicated yesmem project (scoped to this directory) for
building the Hermes-owned Halo companion — the adapter the Brilliant Labs
build-partner email (`career-ops/outreach/brilliant-labs-build-partner-2026-08-13.md`)
references. This folder is meant to become Caide's "secondary brain" for this
build specifically: everything about how he wants to interact with the
glasses, what should be logged, and the resulting design decisions live here,
separate from the wiki/career-ops/sovereign-testbench projects.

**Council directive this project executes (from the datasheet, §8):**
> "ACTION NOW (all 3 models): build + benchmark against the emulator (Lua
> runtime, renders 256×256 display in software) — no hardware purchase needed
> to build the Hermes integration surface. Buy only after 30-45 days of
> first-wave reviews + Korean smoke test."

This is **Path C**: Halo as a Hermes-managed peripheral, no dependency on
Noa/Narrative's opaque memory. Build target: `noa-playground` emulator, not
physical hardware.

## What's already speced (don't re-derive — pull from the datasheet)

Full source: `sovereign-testbench/research/lifeos-brilliant-perplexity-datasheet-2026-08-08.md` §8.

### ⚠️ EMULATOR CORRECTION (2026-08-13, repo-verified)

**`noa-playground` is NOT a hardware emulator.** Its README is literally two lines: a web demo of the next-gen Noa cloud service, gated behind a preview key (`index.html` + `js/`, no Lua runtime). Do NOT build against it.

**The real emulator is `halo_emulator`** — a Python package (`halo-emulator` on PyPI) inside the `brilliant_sdk` monorepo (`brilliant_sdk/python/packages/halo_emulator/`):
- Full **Lua 5.3 runtime** via `lupa` — runs unmodified Halo Lua scripts
- **256×256 virtual display** — all `frame.*` drawing primitives, palette, text, bitmaps
- **Event injection** — `inject_bluetooth_data()`, `inject_button_single/double/long()`, `inject_imu_tap()` — thread-safe
- **Interactive REPL** — `halo-emulator ./app/` (pygame window + Python REPL; Space/D/L/T = button/IMU keys)
- **Headless mode** — `halo-emulator ./app/ --headless`
- **Sandboxed filesystem** — `frame.file.*` against a real dir
- **Test-friendly** — framebuffer as PIL Image, BLE sends captured
- **Paired examples** — `examples/paired_*.py` show host-side (brilliant-ble/msg) ⇄ emulator interaction

Reference clones live at `reference/` (noa-playground, brilliant_sdk, noa-assistant, noa-flutter — shallow clones, 2026-08-13).

**Build stack (verified):** `brilliant-ble` (BLE transport, bleak) + `brilliant-msg` (rich message types: sprites, text, audio, IMU, photos, clicks) + `halo_emulator` (device side). Windows: Python 3.x + uv; `uv sync --all-packages` in `brilliant_sdk/python`.

**Noa relationship (open, user's words):** noa-assistant = self-hostable AI server (BYO-key: conversational AI, photo convos, voice transcription, web search) — separate from the memory question. noa-flutter = the Noa mobile app. Whether to override / work with / supplement Noa's own memory (Narrative) is still an open interview question.

**Architecture:**
```
Halo (mics/camera/display/bone audio) ⇅ BLE via brilliant-ble + brilliant-msg
→ Windows Halo Gateway (Python, local, owns pairing/reconnects)
→ Hermes Orchestrator (LiteLLM :4000 router, Korean ASR→translation→caption,
   consent/attention-policy engine, memory classifier, Obsidian/LifeOS stores)
→ LifeOS Memory Router: ephemeral buffer (minutes-hours, encrypted) / daily-ops /
   long-term (user-approved only) / deep-research (provenance)
→ sovereign-testbench regression/privacy/hallucination gates
```

**Event envelope (opus-5, council-agreed):**
```
{event_id, timestamp, source=halo, modality, transcript/summary, entities,
 confidence, consent_scope, sensitivity, raw_media_hash, retention_class}
```

**Memory boundary:** Halo receives minimum active context only. API keys,
transcripts, embeddings, memory graph stay on Windows. Store
summaries+provenance, NOT raw audio/video.

**ADHD/ASD attention policy (already decided, not open):** pull-first, no
proactive interruptions by default; rate limits + quiet hours; one-action-at-
a-time display; physical/voice stop.

**4 memory surfaces (kimi-k3 report):** Daily ops (immediate sync of approved
structured records) / Long-term (user-confirmed only) / Deep research (never
auto-populate from ambient) / Wearable peripheral (local queue first, strict
retention + selective promotion).

## What's genuinely open — the interview this project needs

An **architect agent** should interview Caide directly on these before a
project map gets written, using whatever skills fit (system-design + the
existing datasheet as grounding, not a blank-slate interview):

1. **Interaction model** — how does Caide actually want to talk to the
   glasses day-to-day? Voice-only? Display glances? What triggers a capture
   vs. passive standby?
2. **Logging scope** — beyond the event envelope schema above, what
   *categories* of life-event does he want logged (meds, meetings, ideas,
   research threads, social context) and at what granularity?
3. **Consent/retention specifics** — the policy says "user-confirmed only"
   for long-term promotion; what does the actual confirmation UX look like
   day-to-day (end-of-day review? real-time prompt? weekly digest)?
4. **Emulator build scope** — what's the smallest real slice to build first
   against `noa-playground`: a BLE-less software loopback? Full gateway with
   fake sensor input? Pick a v0 target.
5. **Octopus methodology application** — which design decisions in this
   project are worth running through the council/ralph-loop verification
   pattern (proven method, see datasheet §10) vs. just building?

## Process (as Caide specified)

1. This seed file exists so a fresh session/agent has full context with zero
   re-derivation.
2. An architect-style agent interviews Caide against the open questions
   above, using the existing research as grounding rather than starting
   blank.
3. Output: a project map (this project's own `PROJECT_MAP.md`, not yet
   created).
4. Either continue in Claude (this session/project), or do the build in
   Hermes and bring it back to Claude for verification — either path is
   fine, this file is the handoff surface either way.
5. Apply Octopus methodology (ralph loop + MoA council, `research-method
   comparison` in datasheet §10) for verifying non-trivial design decisions
   during the build, same as the original Halo research.

## Related

- `career-ops/outreach/brilliant-labs-build-partner-2026-08-13.md` — the
  email this project is meant to eventually back up with a working adapter
- `sovereign-testbench/research/lifeos-brilliant-perplexity-datasheet-2026-08-08.md` — full research corpus (§8 = the architecture this project builds)
- `wiki/handoffs/brilliant-labs-outreach-handoff-2026-08-13.md`
- `wiki/concepts/lifeos-vs-caides-lifeos-and-hermes-integration-2026-08-12.md`
