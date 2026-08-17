"""Tests for halo_emulator capture path."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from halo_emulator import CaptureListener, EmulatorBrilliantMsg, HaloEmulator, HaloEvent

LUA_DIR = Path(__file__).parent / "lua"


def _start_event_callbacks(emulator, tmp_path):
    shutil.copy2(LUA_DIR / "event_callbacks.lua", tmp_path / "event_callbacks.lua")
    emulator.start("event_callbacks.lua")
    time.sleep(0.15)


def test_injected_tap_produces_envelope_with_all_required_fields(tmp_path):
    emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
    frame = EmulatorBrilliantMsg(emu)
    events: list[HaloEvent] = []

    frame._emu.connect()
    captured = CaptureListener(frame, on_event=events.append)
    _start_event_callbacks(emu, tmp_path)
    emu.inject_imu_tap()
    time.sleep(0.2)

    assert len(captured.events) == 1
    event = captured.events[0]
    envelope = event.envelope()
    assert set(envelope.keys()) >= {
        "event_id",
        "timestamp",
        "source",
        "modality",
        "payload",
        "consent_state",
        "sensitivity",
        "retention_class",
    }
    assert envelope["source"] == "halo"
    assert envelope["modality"] == "tap"
    assert isinstance(envelope["payload"], dict)
    assert "_bytes_hex" in envelope["payload"]
    assert envelope["consent_state"] == "user-confirmed"
    assert envelope["sensitivity"] == "medium"
    assert envelope["retention_class"] == "ephemeral"
    assert events[0].to_json() == json.dumps(envelope)
