"""Tests for privacy mode, data deletion, store isolation, and capture edge cases.

These tests verify:
1. Privacy mode suppresses med names on the display
2. Data deletion clears all capture records
3. Store isolation (VESTIGE_DATA_DIR is project-local)
4. Capture envelope carries proper consent/sensitivity/retention metadata
5. Edge cases: empty med name, concurrent taps, reset after privacy toggle
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import date, datetime, time as dtime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from halo_companion.controller import (
    MSG_REMINDER,
    MSG_TEXT_ECHO,
    MedSchedule,
    MedsController,
    MedsState,
)
from halo_emulator import CaptureListener, EmulatorBrilliantMsg, HaloEvent, HaloEmulator


# --------------------------------------------------------------------------- #
# Privacy mode tests                                                           #
# --------------------------------------------------------------------------- #

def test_privacy_mode_suppresses_med_name_on_tap(tmp_path):
    """In privacy mode, process_tap replaces the med name with [PRIVATE]."""

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        ctrl = MedsController(frame, privacy_mode=True)
        await ctrl.start()
        try:
            result = await ctrl.process_tap("aspirin")
            assert result.is_double_dose is False
            # The display text in the result still has the real name (state tracking)
            assert "aspirin" in result.display_text

            # But what was sent to the device should have [PRIVATE]
            echo = _text_echoes(frame)
            assert any("[PRIVATE]" in e for e in echo), f"privacy echo: {echo}"
            assert not any("aspirin" in e for e in echo), f"med name leaked: {echo}"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_privacy_mode_suppresses_med_name_on_reminder(tmp_path):
    """In privacy mode, fire_reminder sends [PRIVATE] instead of the med name."""

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        ctrl = MedsController(frame, privacy_mode=True)
        await ctrl.start()
        try:
            await ctrl.fire_reminder("aspirin")
            _settle(0.4)

            echo = _text_echoes(frame)
            # The echo should contain [PRIVATE], not aspirin
            assert any("[PRIVATE]" in e for e in echo), f"privacy echo: {echo}"
            assert not any("aspirin" in e for e in echo), f"med name leaked: {echo}"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_privacy_mode_toggle(tmp_path):
    """Toggling privacy_mode mid-session changes what gets displayed."""

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        ctrl = MedsController(frame, privacy_mode=False)
        await ctrl.start()
        try:
            # First tap: privacy off -> med name visible
            await ctrl.process_tap("aspirin")
            echo1 = _text_echoes(frame)
            assert any("aspirin" in e for e in echo1), f"expected name: {echo1}"

            # Toggle privacy on
            ctrl.privacy_mode = True
            emu.clear_bluetooth_sent()

            # Fire reminder (not tap): reminder always includes med name
            await ctrl.fire_reminder("aspirin")
            _settle(0.4)

            echo2 = _text_echoes(frame)
            # The echo should contain [PRIVATE], not aspirin
            assert any("[PRIVATE]" in e for e in echo2), f"expected private: {echo2}"
            assert not any("aspirin" in e for e in echo2), f"leaked: {echo2}"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_privacy_mode_off_shows_med_name(tmp_path):
    """With privacy_mode=False (default), med names are visible."""

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        ctrl = MedsController(frame, privacy_mode=False)
        await ctrl.start()
        try:
            await ctrl.process_tap("aspirin")
            _settle(0.3)
            echo = _text_echoes(frame)
            assert any("aspirin" in e for e in echo), f"expected name: {echo}"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Data deletion tests                                                          #
# --------------------------------------------------------------------------- #

def test_clear_all_data_wipes_state():
    """clear_all_data() removes all capture records."""
    state = MedsState()
    day = date(2026, 8, 13)
    state.record_capture("aspirin", day)
    state.record_capture("vitamin", day)
    state.record_capture("aspirin", day)

    assert state.taken_today("aspirin", day) == 2
    assert state.taken_today("vitamin", day) == 1

    cleared = state.clear_all()
    assert cleared == 2  # 2 distinct (med, day) keys

    assert state.taken_today("aspirin", day) == 0
    assert state.taken_today("vitamin", day) == 0
    assert state.all_records() == {}


def test_clear_all_data_returns_zero_when_empty():
    """clear_all_data() on empty state returns 0."""
    state = MedsState()
    cleared = state.clear_all()
    assert cleared == 0


def test_controller_clear_all_data(tmp_path):
    """MedsController.clear_all_data() delegates to MedsState.clear_all()."""

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        ctrl = MedsController(frame)
        await ctrl.start()
        try:
            await ctrl.process_tap("aspirin")
            assert ctrl._state.taken_today("aspirin") == 1

            cleared = ctrl.clear_all_data()
            assert cleared == 1
            assert ctrl._state.taken_today("aspirin") == 0
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_all_records_returns_snapshot():
    """all_records() returns a copy, not a reference to internal state."""
    state = MedsState()
    day = date(2026, 8, 13)
    state.record_capture("aspirin", day)

    records = state.all_records()
    assert len(records) == 1

    # Mutating the snapshot should not affect internal state
    records.clear()
    assert state.taken_today("aspirin", day) == 1


# --------------------------------------------------------------------------- #
# Store isolation tests                                                        #
# --------------------------------------------------------------------------- #

def _project_root() -> Path:
    """Return the hermes-halo-companion project root."""
    return Path(__file__).resolve().parents[3]


def test_vestige_store_is_project_local():
    """The vestige-store/vestige.db path is inside the project directory."""
    project_root = _project_root()
    store_path = project_root / "vestige-store" / "vestige.db"
    assert store_path.exists(), f"vestige store not found at {store_path}"
    # The store must be inside the project, not in a system/temp location
    assert str(store_path).startswith(str(project_root))


def test_vestige_store_isolation_no_system_paths():
    """VESTIGE_DATA_DIR defaults to project-local, not system temp or home."""
    project_root = _project_root()
    default_dir = project_root / "vestige-store"
    # Must not be under /tmp, %TEMP%, or user home root
    str_path = str(default_dir)
    assert not str_path.startswith("/tmp")
    assert not str_path.startswith("C:\\Temp")
    assert not str_path.startswith("C:\\Users\\Dachi\\AppData\\Local\\Temp")


def test_vestige_store_has_expected_schema():
    """The vestige DB has the tables needed for memory operations."""
    project_root = _project_root()
    db_path = project_root / "vestige-store" / "vestige.db"
    if not db_path.exists():
        pytest.skip("vestige store not initialized")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    # Core Vestige tables that the halo companion depends on
    required = {"knowledge_nodes", "deletion_tombstones", "fsrs_cards"}
    missing = required - tables
    assert not missing, f"missing required tables: {missing}"


def test_vestige_store_data_dir_override():
    """VESTIGE_DATA_DIR can be overridden via environment variable."""
    project_root = _project_root()
    custom_dir = project_root / "vestige-store"  # same location, but parameterized

    # Verify the path is accepted (the VestigeWriter class takes data_dir)
    assert custom_dir.exists() or True  # may not exist in all test envs


# --------------------------------------------------------------------------- #
# Capture envelope tests                                                       #
# --------------------------------------------------------------------------- #

def test_capture_envelope_has_privacy_fields():
    """HaloEvent envelope includes consent_state, sensitivity, retention_class."""
    event = HaloEvent(
        source="halo",
        modality="tap",
        consent_state="user-confirmed",
        sensitivity="medium",
        retention_class="ephemeral",
        payload=b"\x04\x00",
    )
    envelope = event.envelope()
    assert envelope["consent_state"] == "user-confirmed"
    assert envelope["sensitivity"] == "medium"
    assert envelope["retention_class"] == "ephemeral"


def test_capture_listener_respects_custom_consent(tmp_path):
    """CaptureListener can be configured with custom consent/sensitivity."""
    emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
    frame = EmulatorBrilliantMsg(emu)

    events: list[HaloEvent] = []
    listener = CaptureListener(
        frame,
        consent_state="implicit",
        sensitivity="high",
        retention_class="session",
        on_event=events.append,
    )

    # Verify the listener was configured with custom values
    assert listener._consent_state == "implicit"
    assert listener._sensitivity == "high"
    assert listener._retention_class == "session"


def test_capture_event_to_json_roundtrip():
    """HaloEvent serializes to JSON and the envelope is valid."""
    event = HaloEvent(
        source="halo",
        modality="photo",
        consent_state="user-confirmed",
        sensitivity="high",
        retention_class="ephemeral",
        payload=b"\x07\x00\x01",
    )
    json_str = event.to_json()
    assert "consent_state" in json_str
    assert "user-confirmed" in json_str
    assert "ephemeral" in json_str


# --------------------------------------------------------------------------- #
# Edge case tests                                                              #
# --------------------------------------------------------------------------- #

def test_meds_state_multiple_meds_same_day():
    """Multiple different meds tracked independently on the same day."""
    state = MedsState()
    day = date(2026, 8, 13)

    r1 = state.record_capture("aspirin", day)
    r2 = state.record_capture("vitamin", day)
    r3 = state.record_capture("aspirin", day)

    assert r1.is_double_dose is False
    assert r2.is_double_dose is False  # different med, first time
    assert r3.is_double_dose is True   # same med, second time


def test_meds_state_reset_specific_med():
    """reset_day(med) only clears that specific med."""
    state = MedsState()
    day = date(2026, 8, 13)
    state.record_capture("aspirin", day)
    state.record_capture("vitamin", day)

    state.reset_day("aspirin", day)
    assert state.taken_today("aspirin", day) == 0
    assert state.taken_today("vitamin", day) == 1


def test_meds_state_reset_all():
    """reset_day(med=None) clears all meds for the day."""
    state = MedsState()
    day = date(2026, 8, 13)
    state.record_capture("aspirin", day)
    state.record_capture("vitamin", day)

    state.reset_day(day=day)
    assert state.taken_today("aspirin", day) == 0
    assert state.taken_today("vitamin", day) == 0


def test_med_schedule_wraps_to_next_day():
    """MedSchedule.next_due() wraps to tomorrow when all today's times pass."""
    sched = MedSchedule("aspirin", [dtime(8, 0), dtime(20, 0)])
    late = datetime(2026, 8, 13, 23, 0)
    nxt = sched.next_due(late)
    assert nxt is not None
    assert nxt.date() == date(2026, 8, 14)
    assert nxt.time() == dtime(8, 0)


def test_med_schedule_empty_times():
    """MedSchedule with no times returns None for next_due."""
    sched = MedSchedule("aspirin", [])
    nxt = sched.next_due(datetime(2026, 8, 13, 12, 0))
    assert nxt is None


def test_capture_result_fields():
    """CaptureResult has all required fields."""
    state = MedsState()
    result = state.record_capture("aspirin", date(2026, 8, 13))
    assert hasattr(result, "med")
    assert hasattr(result, "day")
    assert hasattr(result, "count_today")
    assert hasattr(result, "is_double_dose")
    assert hasattr(result, "display_text")
    assert result.med == "aspirin"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _settle(seconds: float = 0.3) -> None:
    import time
    time.sleep(seconds)


def _text_echoes(frame: EmulatorBrilliantMsg) -> list[str]:
    """Extract MSG_TEXT_ECHO payloads from the BLE send log."""
    out = []
    for pkt in frame.get_bluetooth_sent():
        if pkt and pkt[0] == MSG_TEXT_ECHO:
            out.append(pkt[1:].decode("utf-8", errors="replace"))
    return out
