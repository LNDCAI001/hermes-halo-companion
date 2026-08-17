# halo-voice-pipeline

Korean voice -> English caption via model.

## Install

```bash
uv sync --all-packages --extra tests --extra capture
```

## Emulator smoke loop

```bash
uv run python packages/halo_voice_pipeline/src/halo_voice_pipeline/cli.py --emulator files --samples-dir packages/brilliant_msg/examples/audio
```

Place a small Korean `.wav` under `packages/brilliant_msg/examples/audio` for the smoke test.
