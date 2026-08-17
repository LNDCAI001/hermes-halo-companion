"""Convert captured Halo audio bytes to usable WAV/PCM input for translation."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import numpy as np
from pydub import AudioSegment

from halo_voice_pipeline.translator import KoreanVoiceTranslator


class HaloAudioAdapter:
    """Adapt Halo-style audio payloads into translator inputs."""

    def __init__(self, translator: KoreanVoiceTranslator, *, on_caption=None) -> None:
        self.translator = translator
        self.on_caption = on_caption

    async def process_bytes(self, data: bytes, *, filename: str = "capture.wav") -> None:
        if not data:
            return
        wav_bytes = self._normalize(data)
        try:
            caption, metadata = await self.translator.translate_bytes(wav_bytes, suffix=".wav")
        except Exception as exc:
            print(f"[halo-audio] translation failed: {exc}")
            return
        if self.on_caption:
            self.on_caption(caption, metadata)
        else:
            print(f"[halo-audio] {filename}: {caption}")

    async def process_file(self, path: Path | str) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        caption, metadata = await self.translator.translate(path)
        if self.on_caption:
            self.on_caption(caption, metadata)
        else:
            print(f"[halo-audio] {path.name}: {caption}")

    def _normalize(self, data: bytes) -> bytes:
        if len(data) < 8:
            raise ValueError("audio payload too short")
        header = data[:8]
        if header.startswith(b"RIFF") or header.startswith(b"OggS"):
            return data

        try:
            audio = AudioSegment.from_raw(
                io.BytesIO(data),
                sample_width=2,
                frame_rate=16000,
                channels=1,
                format="s16le",
            )
            buffer = io.BytesIO()
            buffer.name = "capture.wav"
            audio.export(buffer, format="wav")
            return buffer.getvalue()
        except Exception as exc:
            raise ValueError(f"unsupported audio payload: {exc}") from exc

    async def test_with_korean_sample(self) -> str:
        samples = sorted(Path("./examples/audio").glob("*.wav"))
        if not samples:
            samples = sorted(Path("./examples/audio").glob("*.pcm"))
        if not samples:
            raise FileNotFoundError("no audio samples found")
        caption, metadata = await self.translator.translate(samples[0])
        print(f"[halo-audio] sample={samples[0].name} caption={caption} metadata={metadata}")
        return caption
