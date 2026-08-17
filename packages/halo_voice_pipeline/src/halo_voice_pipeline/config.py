"""Configuration for the Korean voice translation pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VoicePipelineConfig:
    """Configuration options for the voice pipeline."""

    litellm_model: str = "openai/gpt-4o-mini"
    litellm_api_key: str | None = field(default_factory=lambda: os.environ.get("LITELLM_API_KEY"))
    litellm_api_base: str | None = field(default_factory=lambda: os.environ.get("LITELLM_API_BASE"))
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    source_language: str = "ko"
    target_language: str = "en"
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_format: str = "wav"
    log_level: str = "INFO"
    temp_dir: Path = field(default_factory=lambda: Path(os.environ.get("VOICE_PIPELINE_TEMP", "./tmp/voice_pipeline")))
    max_audio_duration_s: float = 60.0

    def ensure_temp_dir(self) -> Path:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self.temp_dir
