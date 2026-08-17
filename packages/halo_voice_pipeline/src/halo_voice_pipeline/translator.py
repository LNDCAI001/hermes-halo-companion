"""Korean ASR and translation through a model-backed pipeline."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import numpy as np
from faster_whisper import WhisperModel
from litellm import acompletion

from halo_voice_pipeline.config import VoicePipelineConfig


class VoicePipelineError(Exception):
    """Base pipeline error."""


class ASRError(VoicePipelineError):
    """ASR stage failed."""


class TranslationError(VoicePipelineError):
    """Translation stage failed."""


class KoreanVoiceTranslator:
    """Convert Korean audio to English text via ASR + translation."""

    def __init__(self, config: VoicePipelineConfig | None = None) -> None:
        self.config = config or VoicePipelineConfig()
        self._asr_model: WhisperModel | None = None

    @property
    def asr_model(self) -> WhisperModel:
        if self._asr_model is None:
            self._asr_model = WhisperModel(
                self.config.whisper_model,
                device=self.config.whisper_device,
                compute_type=self.config.whisper_compute_type,
            )
        return self._asr_model

    async def translate(self, audio_path: Path | str) -> tuple[str, dict[str, Any]]:
        """Return English caption and stage timing/result metadata."""
        start = time.perf_counter()
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise ASRError(f"audio not found: {audio_path}")

        segments, info = self.asr_model.transcribe(
            str(audio_path),
            language=self.config.source_language,
            task="transcribe",
            vad_filter=True,
        )
        korean_text = " ".join(segment.text for segment in segments).strip()
        asr_duration = time.perf_counter() - start

        metadata: dict[str, Any] = {
            "source_language": info.language,
            "asr_duration_s": round(asr_duration, 4),
        }

        if not korean_text:
            metadata["translation_duration_s"] = 0.0
            metadata["english_text"] = ""
            return "", metadata

        translation_start = time.perf_counter()
        english_text = await self._translate_text(korean_text)
        metadata["translation_duration_s"] = round(time.perf_counter() - translation_start, 4)
        metadata["korean_text"] = korean_text
        metadata["english_text"] = english_text
        return english_text, metadata

    async def _translate_text(self, korean_text: str) -> str:
        system_prompt = (
            "You are a professional Korean-to-English translator. "
            "Preserve meaning, tone, and domain-specific wording. "
            "Output only the English translation, without explanations."
        )
        try:
            response = await acompletion(
                model=self.config.litellm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": korean_text},
                ],
                api_key=self.config.litellm_api_key,
                api_base=self.config.litellm_api_base,
            )
            english_text = (response.choices[0].message.content or "").strip()
            if not english_text:
                raise TranslationError("empty translation output")
            return english_text
        except Exception as exc:
            raise TranslationError(f"translation failed: {exc}") from exc

    async def translate_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> tuple[str, dict[str, Any]]:
        temp_dir = self.config.ensure_temp_dir()
        temp_path = temp_dir / f"asr_input_{int(time.time() * 1000)}{suffix}"
        temp_path.write_bytes(audio_bytes)
        try:
            return await self.translate(temp_path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    async def close(self) -> None:
        if self._asr_model is not None:
            self._asr_model = None
