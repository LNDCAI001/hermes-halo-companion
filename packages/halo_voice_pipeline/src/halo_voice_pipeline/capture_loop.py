"""Capture audio from a Halo device or emulator and translate Korean speech to English."""

from __future__ import annotations

import asyncio
import os
from typing import Callable

from halo_voice_pipeline.translator import KoreanVoiceTranslator, VoicePipelineConfig


class CaptureLoop:
    """Run the voice capture loop."""

    def __init__(
        self,
        translator: KoreanVoiceTranslator,
        on_caption: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.translator = translator
        self.on_caption = on_caption
        self._running = False

    async def run_emulator(self, emulator) -> None:
        """Run the pipeline against a HaloEmulator instance."""
        if hasattr(emulator, "inject_audio_file") and callable(emulator.inject_audio_file):
            await self._process_emulator_file(emulator)
            return

        if hasattr(emulator, "inject_bluetooth_data") and callable(emulator.inject_bluetooth_data):
            await self._process_emulator_ble(emulator)
            return

        raise TypeError("unsupported emulator interface")

    async def run_emulator_files(self, samples_dir: Path) -> None:
        """Run the pipeline against sample audio files in *samples_dir*."""
        files = sorted(samples_dir.glob("*.wav"))
        if not files:
            files = sorted(samples_dir.glob("*.pcm"))
        if not files:
            files = sorted(samples_dir.glob("*.lc3"))

        for audio_file in files:
            caption, metadata = await self.translator.translate(audio_file)
            if self.on_caption:
                self.on_caption(caption, metadata)
            else:
                print(f"[capture] {audio_file.name}: {caption}")

    async def _process_emulator_file(self, emulator) -> None:
        """Use an emulator-side helper if available."""
        sample_root = Path(os.environ.get("VOICE_PIPELINE_SAMPLES", "./examples/audio"))
        await self.run_emulator_files(sample_root)

    async def _process_emulator_ble(self, emulator) -> None:
        """Process audio bytes received via emulator BLE stub."""
        received = emulator.get_bluetooth_sent()
        for payload in received:
            if not payload:
                continue
            try:
                caption, metadata = await self.translator.translate_bytes(payload)
            except Exception as exc:
                print(f"[capture] translation failed: {exc}")
                continue
            if self.on_caption:
                self.on_caption(caption, metadata)
            else:
                print(f"[capture] {caption}")

    async def run_device(
        self,
        *,
        device_name: str | None = None,
        wake_on_audio: bool = False,
        max_clips: int | None = None,
    ) -> None:
        """Run the pipeline against a physical Halo device."""
        try:
            from brilliant_msg import BrilliantMsg, RxAudio
        except ImportError as exc:
            raise VoicePipelineError("brilliant_msg is required for device capture") from exc

        from halo_voice_pipeline.halo_audio_adapter import HaloAudioAdapter

        frame = BrilliantMsg()
        adapter = HaloAudioAdapter(self.translator, on_caption=self.on_caption)
        clips_processed = 0

        try:
            await frame.connect(name=device_name)
            if frame.type.name != "HALO":
                raise VoicePipelineError("device is not Halo")

            await frame.print_short_text("Voice...")
            await frame.upload_stdlua_libs(lib_names=["data", "code"])

            rx_audio = RxAudio(streaming=True)
            audio_queue = await rx_audio.attach(frame)
            await frame.start_frame_app()

            self._running = True
            while self._running and (max_clips is None or clips_processed < max_clips):
                raw = await audio_queue.get()
                if raw is None:
                    continue
                await adapter.process_bytes(bytes(raw), filename=f"clip_{clips_processed}.wav")
                clips_processed += 1

        finally:
            self._running = False
            try:
                rx_audio.detach(frame)
            except Exception:
                pass
            try:
                await frame.stop_frame_app()
            except Exception:
                pass
            await frame.disconnect()
