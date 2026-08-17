"""Acceptance tests for T4: meds double-dose alert + scheduled reminder.

Both behaviors are verified end-to-end against the emulator framebuffer:

1. **Double-dose**: after a first "taking meds" capture for the day, a second
   capture shows "You already took this today" on the 256x256 display instead
   of a confirmation.
2. **Reminder**: a scheduled push shows "Time to take [med]" on the display,
   fires the native sound primitive (observed via the MSG_AUDIO device->host
   message), and renders the amber title.

The Lua app under test is ``halo_companion/lua/meds_alert.lua`` running on the
real HaloEmulator Lua 5.3 runtime. The host controller (``MedsController``)
drives it through ``EmulatorBrilliantMsg`` exactly like it would on hardware.

Text-on-framebuffer verification is a pixel-template match: the expected string
is rendered with the *same* PIL default font the emulator's ``DisplayBuffer``
uses, and we assert a high fraction of the expected glyph pixels are actually
lit (within a color tolerance) at the (x, y) the Lua app drew them at.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from halo_companion.controller import (
    MSG_AUDIO,
    MSG_TEXT_ECHO,
    MedSchedule,
    MedsController,
)
from halo_emulator import EmulatorBrilliantMsg, HaloEmulator

AMBER = (255, 200, 0)  # 0xFFC800 reminder title
WHITE = (255, 255, 255)


@pytest.fixture
def emulator(tmp_path: Path):
    emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
    yield emu
    if emu.is_running():
        emu.stop()


def _settle(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def _text_echoes(frame: EmulatorBrilliantMsg) -> list[str]:
    """Extract MSG_TEXT_ECHO payloads from the BLE send log."""
    out = []
    for pkt in frame.get_bluetooth_sent():
        if pkt and pkt[0] == MSG_TEXT_ECHO:
            out.append(pkt[1:].decode("utf-8", errors="replace"))
    return out


def _expected_glyph_pixels(text: str, x: int, y: int) -> list[tuple[int, int]]:
    """Render *text* with the emulator's default font; return lit pixel coords.

    The emulator's ``DisplayBuffer.text()`` draws with
    ``ImageDraw.text((x - 1, y - 1), ...)`` using ``ImageFont.load_default()``.
    Mirror that exactly so the template matches the framebuffer.
    """
    font = ImageFont.load_default()
    probe = Image.new("RGBA", (256, 256), (0, 0, 0, 255))
    draw = ImageDraw.Draw(probe)
    draw.text((x - 1, y - 1), text, fill=(255, 255, 255, 255), font=font)
    px = probe.load()
    return [(cx, cy) for cy in range(256) for cx in range(256) if px[cx, cy][0] > 200]


def _assert_text_rendered(img: Image.Image, text: str, x: int, y: int, color=WHITE, min_frac: float = 0.5) -> None:
    """Assert *text* is visibly rendered at (x, y) on the framebuffer."""
    glyphs = _expected_glyph_pixels(text, x, y)
    assert glyphs, f"expected text {text!r} produced no reference glyphs"
    tol = 90
    px = img.load()
    lit = sum(
        1
        for (cx, cy) in glyphs
        if abs(px[cx, cy][0] - color[0]) < tol
        and abs(px[cx, cy][1] - color[1]) < tol
        and abs(px[cx, cy][2] - color[2]) < tol
    )
    frac = lit / len(glyphs)
    assert frac >= min_frac, (
        f"text {text!r} at ({x},{y}) only {frac:.0%} of {len(glyphs)} glyph pixels lit "
        f"(color={color})"
    )


async def _boot_controller(tmp_path: Path) -> tuple[HaloEmulator, EmulatorBrilliantMsg, MedsController]:
    """Start the meds Lua app on a fresh emulator and return the trio."""
    emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
    frame = EmulatorBrilliantMsg(emu)
    ctrl = MedsController(frame, clock=lambda: datetime(2026, 8, 13, 9, 0, 0))
    await ctrl.start()
    return emu, frame, ctrl


# --------------------------------------------------------------------------- #
# Double-dose                                                                 #
# --------------------------------------------------------------------------- #

def test_double_dose_second_capture_shows_alert(tmp_path):
    """2nd 'taking meds' capture in a day -> 'You already took this today'."""

    async def scenario():
        emu, frame, ctrl = await _boot_controller(tmp_path)
        try:
            # First capture: confirmation ("Taken:\naspirin" at y=30 / y=60)
            first = await ctrl.process_tap("aspirin")
            assert first.count_today == 1
            assert first.is_double_dose is False
            assert "Taken" in first.display_text
            _settle()

            echo1 = _text_echoes(frame)
            assert any("Taken" in e for e in echo1), f"first capture echo: {echo1}"
            img1 = emu.get_framebuffer()
            assert img1.size == (256, 256)
            _assert_text_rendered(img1, "Taken:", 10, 30)
            _assert_text_rendered(img1, "aspirin", 10, 60)

            # Second capture same day: double-dose alert (3 lines at y=30/60/90)
            emu.clear_bluetooth_sent()
            second = await ctrl.process_tap("aspirin")
            assert second.count_today == 2
            assert second.is_double_dose is True
            assert "already" in second.display_text.lower()
            _settle()

            echo2 = _text_echoes(frame)
            assert any("already" in e.lower() for e in echo2), f"2nd echo: {echo2}"
            img2 = emu.get_framebuffer()
            _assert_text_rendered(img2, "You already", 10, 30)
            _assert_text_rendered(img2, "took this", 10, 60)
            _assert_text_rendered(img2, "today", 10, 90)
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_double_dose_does_not_trigger_across_days(tmp_path):
    """A capture on a different day is a fresh dose, not a double-dose."""

    async def scenario():
        emu, frame, ctrl = await _boot_controller(tmp_path)
        try:
            await ctrl.process_tap("vitamin")
            _settle(0.2)
            emu.clear_bluetooth_sent()

            # Advance the controller's clock to the next day.
            ctrl._clock = lambda: datetime(2026, 8, 14, 9, 0, 0)
            result = await ctrl.process_tap("vitamin")
            assert result.count_today == 1
            assert result.is_double_dose is False
            _settle()
            echo = _text_echoes(frame)
            assert any("Taken" in e for e in echo), f"next-day echo: {echo}"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Reminder                                                                    #
# --------------------------------------------------------------------------- #

def test_reminder_shows_text_and_fires_audio(tmp_path):
    """Scheduled push -> 'Time to take [med]' on display + native sound fired."""

    async def scenario():
        emu, frame, ctrl = await _boot_controller(tmp_path)
        try:
            await ctrl.fire_reminder("aspirin")
            _settle(0.4)

            echo = _text_echoes(frame)
            assert any("Time to take aspirin" in e for e in echo), f"echo: {echo}"

            img = emu.get_framebuffer()
            # Lua layout: title (30,30) amber; "Time to take" (20,80); med (30,120)
            _assert_text_rendered(img, "Reminder", 30, 30, color=AMBER)
            _assert_text_rendered(img, "Time to take", 20, 80)
            _assert_text_rendered(img, "aspirin", 30, 120)

            # Audio: the Lua app invoked the native speaker primitive.
            sent = frame.get_bluetooth_sent()
            assert any(p[0] == MSG_AUDIO for p in sent), (
                f"audio msg missing: {[list(p) for p in sent]}"
            )
            assert ctrl.audio_events, "controller never saw MSG_AUDIO"
        finally:
            await ctrl.stop()

    asyncio.run(scenario())


def test_scheduler_fires_reminder_at_due_time(tmp_path):
    """run_scheduler() fires the reminder at the configured time (injectable clock)."""

    events: list[str] = []
    t0 = datetime(2026, 8, 13, 8, 0, 0)
    clock_state = {"now": t0}

    def fake_clock() -> datetime:
        return clock_state["now"]

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        sched = MedSchedule("aspirin", [dtime(8, 30)])
        ctrl = MedsController(frame, schedules=[sched], clock=fake_clock)

        orig_fire = ctrl.fire_reminder

        async def spy_fire(med: str) -> None:
            events.append(med)
            await orig_fire(med)

        ctrl.fire_reminder = spy_fire  # type: ignore[method-assign]

        await ctrl.start()
        try:
            task = asyncio.create_task(ctrl.run_scheduler(stop_after=5))
            # Advance clock past due and let the scheduler wake.
            for _ in range(30):
                await asyncio.sleep(0.05)
                clock_state["now"] = clock_state["now"] + timedelta(minutes=1)
            await task
        finally:
            await ctrl.stop()

        assert "aspirin" in events, f"scheduler never fired: {events}"
        assert len(events) == 1, f"scheduler fired repeatedly: {events}"

    asyncio.run(scenario())


def test_scheduler_does_not_fire_before_due_time(tmp_path):
    """No reminder fires until the schedule's time arrives."""

    events: list[str] = []
    t0 = datetime(2026, 8, 13, 8, 0, 0)
    clock_state = {"now": t0}

    def fake_clock() -> datetime:
        return clock_state["now"]

    async def scenario():
        emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
        frame = EmulatorBrilliantMsg(emu)
        sched = MedSchedule("aspirin", [dtime(9, 0)])
        ctrl = MedsController(frame, schedules=[sched], clock=fake_clock)

        orig_fire = ctrl.fire_reminder

        async def spy_fire(med: str) -> None:
            events.append(med)
            await orig_fire(med)

        ctrl.fire_reminder = spy_fire  # type: ignore[method-assign]

        await ctrl.start()
        try:
            # Run scheduler with a deadline that never reaches 09:00.
            task = asyncio.create_task(ctrl.run_scheduler(stop_after=0.6))
            for _ in range(6):
                await asyncio.sleep(0.05)
                clock_state["now"] = clock_state["now"] + timedelta(minutes=5)
            await task
        finally:
            await ctrl.stop()

        assert events == [], f"scheduler fired too early: {events}"

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Pure unit tests (no emulator)                                               #
# --------------------------------------------------------------------------- #

def test_meds_state_unit():
    from halo_companion.controller import MedsState

    state = MedsState()
    day = datetime(2026, 8, 13).date()
    r1 = state.record_capture("aspirin", day)
    r2 = state.record_capture("aspirin", day)
    assert r1.is_double_dose is False and r1.count_today == 1
    assert r2.is_double_dose is True and r2.count_today == 2
    assert r2.display_text == "You already\ntook this\ntoday"


def test_med_schedule_next_due():
    sched = MedSchedule("aspirin", [dtime(8, 30), dtime(20, 0)])
    now = datetime(2026, 8, 13, 9, 0)
    nxt = sched.next_due(now)
    assert nxt == datetime(2026, 8, 13, 20, 0)
    late = datetime(2026, 8, 13, 21, 0)
    assert sched.next_due(late) == datetime(2026, 8, 14, 8, 30)
