"""Tests for the voice pipeline package."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from halo_voice_pipeline.config import VoicePipelineConfig
from halo_voice_pipeline.translator import TranslationError


def test_config_defaults():
    config = VoicePipelineConfig()
    assert config.source_language == "ko"
    assert config.target_language == "en"
    assert config.whisper_device == "cpu"


def test_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_PIPELINE_TEMP", str(tmp_path / "custom_temp"))
    monkeypatch.setenv("LITELLM_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("LITELLM_API_BASE", "https://example.invalid/v1")
    config = VoicePipelineConfig(
        litellm_model=os.environ["LITELLM_MODEL"],
        litellm_api_base=os.environ["LITELLM_API_BASE"],
    )
    assert config.litellm_model == "openai/gpt-4o"
    assert config.litellm_api_base == "https://example.invalid/v1"
    assert config.ensure_temp_dir() == tmp_path / "custom_temp"


@pytest.mark.asyncio
async def test_translator_rejects_missing_audio(tmp_path):
    from halo_voice_pipeline.translator import KoreanVoiceTranslator

    translator = KoreanVoiceTranslator(VoicePipelineConfig())
    with pytest.raises(Exception):
        await translator.translate(tmp_path / "nonexistent.wav")


@pytest.mark.asyncio
async def test_translator_translate_bytes(monkeypatch, tmp_path):
    from halo_voice_pipeline.translator import KoreanVoiceTranslator

    sample = tmp_path / "tone.wav"
    sample.write_bytes(b"RIFF" + b"\x00" * 100)

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            class Segment:
                text = "안녕"

            class Info:
                language = "ko"

            return [Segment()], Info()

    class FakeResponse:
        class Choice:
            message = type("Message", (), {"content": "Hello"})

        choices = [Choice()]

    async def fake_completion(*args, **kwargs):
        return FakeResponse()

    import halo_voice_pipeline.translator as translator_module
    monkeypatch.setattr(translator_module, "WhisperModel", FakeModel)
    monkeypatch.setattr(translator_module, "acompletion", fake_completion)

    translator = KoreanVoiceTranslator(VoicePipelineConfig())
    caption, metadata = await translator.translate(sample)
    assert caption == "Hello"
    assert metadata["korean_text"] == "안녕"
    assert metadata["source_language"] == "ko"
