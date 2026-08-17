"""CLI entrypoint for halo-voice-pipeline."""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import time
from pathlib import Path

from halo_voice_pipeline.capture_loop import CaptureLoop
from halo_voice_pipeline.config import VoicePipelineConfig
from halo_voice_pipeline.translator import KoreanVoiceTranslator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Korean voice -> English caption pipeline")
    p.add_argument("--emulator", default="files", choices=["files", "ble"], help="emulator capture mode")
    p.add_argument("--samples-dir", default=os.environ.get("VOICE_PIPELINE_SAMPLES", "./examples/audio"))
    p.add_argument("--sample", default=None, help="exact audio file to translate")
    p.add_argument("--model", default=os.environ.get("LITELLM_MODEL", "openai/gpt-4o-mini"))
    p.add_argument("--api-key", default=os.environ.get("LITELLM_API_KEY"))
    p.add_argument("--api-base", default=os.environ.get("LITELLM_API_BASE"))
    p.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "cpu"))
    return p.parse_args()


def build_config(args: argparse.Namespace) -> VoicePipelineConfig:
    config = VoicePipelineConfig(
        litellm_model=args.model,
        litellm_api_key=args.api_key,
        litellm_api_base=args.api_base,
        whisper_device=args.device,
    )
    return config


async def run(args: argparse.Namespace) -> None:
    config = build_config(args)
    translator = KoreanVoiceTranslator(config)

    try:
        if args.sample:
            caption, metadata = await translator.translate(Path(args.sample))
            print(caption)
            print(metadata)
            return

        loop = CaptureLoop(translator)
        await loop.run_emulator_files(Path(args.samples_dir))
    finally:
        await translator.close()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
