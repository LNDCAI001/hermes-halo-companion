"""
Meds companion host controller.

Owns the *stateful* logic for the Halo meds feature:

  * double-dose detection — the 2nd "taking meds" capture for a given med on a
    given day yields "You already took this today" instead of a confirmation.
  * reminder scheduling — at each med's configured times the host pushes
    "Time to take [med]" to the device and triggers the native sound primitive.

The device side (``lua/meds_alert.lua``) only renders text on the 256x256
display and invokes ``frame.speaker`` (a native primitive). It reports back the
text it rendered (``MSG_TEXT_ECHO``) and when the sound primitive fired
(``MSG_AUDIO``) so the host — and tests — can observe both behaviors on the
emulator framebuffer / BLE log.

The controller is transport-agnostic: it talks to the device through an
``EmulatorBrilliantMsg``-shaped adapter (the same object used for real Halo
hardware via ``BrilliantMsg``), so switching to hardware needs no logic changes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from brilliant_msg import TxPlainText

from halo_emulator import EmulatorBrilliantMsg

LOG = logging.getLogger(__name__)

# Message codes shared with lua/meds_alert.lua
TEXT_FLAG = 0x0A        # host -> device: plain text (TxPlainText protocol)
MSG_TAP = 0x20          # device -> host: user tapped to confirm a capture
MSG_AUDIO = 0x21        # device -> host: native sound primitive fired
MSG_TEXT_ECHO = 0x22    # device -> host: exact text now on the display
MSG_REMINDER = 0xFE     # host -> device: show reminder (med name follows)
MSG_RESET = 0xFF        # host -> device: return to idle

_LUA_DIR = Path(__file__).resolve().parent.parent.parent / "lua"
LUA_APP_PATH = _LUA_DIR / "meds_alert.lua"

DEFAULT_MED = "meds"


# --------------------------------------------------------------------------- #
# Schedule + state                                                            #
# --------------------------------------------------------------------------- #

class MedSchedule:
    """A med's daily reminder times, with next-due computation."""

    def __init__(self, name: str, times: list[time]) -> None:
        self.name = name
        self.times: list[time] = sorted(set(times))

    def next_due(self, now: datetime) -> datetime | None:
        """Next reminder at/after *now*, looking today then tomorrow.

        Returns ``None`` only if the med has no configured times.
        """
        for t in self.times:
            cand = datetime.combine(now.date(), t)
            if cand >= now:
                return cand
        if self.times:
            return datetime.combine(now.date() + timedelta(days=1), self.times[0])
        return None


@dataclass
class CaptureResult:
    med: str
    day: date
    count_today: int
    is_double_dose: bool
    display_text: str


class MedsState:
    """Per-(med, day) capture tracking. Decides double-dose responses."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}

    def record_capture(self, med: str, day: date | None = None) -> CaptureResult:
        day = day or date.today()
        key = (med, day)
        self._counts[key] = self._counts.get(key, 0) + 1
        count = self._counts[key]

        if count == 1:
            display_text = f"Taken:\n{med}"
            is_double = False
        else:
            display_text = "You already\ntook this\ntoday"
            is_double = True

        return CaptureResult(
            med=med,
            day=day,
            count_today=count,
            is_double_dose=is_double,
            display_text=display_text,
        )

    def taken_today(self, med: str, day: date | None = None) -> int:
        day = day or date.today()
        return self._counts.get((med, day), 0)

    def reset_day(self, med: str | None = None, day: date | None = None) -> None:
        """Test/utility helper: forget captures for a med (or all) on a day."""
        day = day or date.today()
        if med is None:
            for k in list(self._counts):
                if k[1] == day:
                    del self._counts[k]
        else:
            self._counts.pop((med, day), None)

    def clear_all(self) -> int:
        """Delete all capture records. Returns the number of records cleared."""
        count = len(self._counts)
        self._counts.clear()
        return count

    def all_records(self) -> dict[tuple[str, date], int]:
        """Return a snapshot of all capture records (for inspection/export)."""
        return dict(self._counts)


# --------------------------------------------------------------------------- #
# Controller                                                                  #
# --------------------------------------------------------------------------- #

class MedsController:
    """Drives the meds feature against an emulator (or real Halo) adapter."""

    def __init__(
        self,
        frame: EmulatorBrilliantMsg,
        *,
        default_med: str = DEFAULT_MED,
        schedules: list[MedSchedule] | None = None,
        clock: Callable[[], datetime] | None = None,
        lua_app_path: Path = LUA_APP_PATH,
        privacy_mode: bool = False,
    ) -> None:
        self._frame = frame
        self._default_med = default_med
        self._schedules = schedules or []
        self._clock = clock or datetime.now
        self._lua_app_path = lua_app_path
        self._privacy_mode = privacy_mode

        self._state = MedsState()
        self._recent_med: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._last_fired: tuple[datetime, str] | None = None

        # Observability (populated by device -> host messages)
        self.audio_events: list[datetime] = []
        self.last_displayed: str | None = None
        self.tap_count = 0

    @property
    def privacy_mode(self) -> bool:
        """Whether privacy mode is active (suppresses med names on display)."""
        return self._privacy_mode

    @privacy_mode.setter
    def privacy_mode(self, value: bool) -> None:
        self._privacy_mode = value

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Connect, upload libs + app, register handlers, mark running."""
        self._loop = asyncio.get_running_loop()
        await self._frame.connect()

        # Standard brilliant_msg libs the Lua app requires.
        await self._frame.upload_stdlua_libs(lib_names=["data", "plain_text"])
        await self._frame.upload_frame_app(
            local_filename=str(self._lua_app_path),
            frame_filename="meds_alert.lua",
        )
        self._frame.attach_print_response_handler()
        await self._frame.start_frame_app(
            frame_app_name="meds_alert", await_print=True
        )

        self._frame.register_data_response_handler(self, [MSG_TAP], self._on_tap)
        self._frame.register_data_response_handler(self, [MSG_AUDIO], self._on_audio)
        self._frame.register_data_response_handler(
            self, [MSG_TEXT_ECHO], self._on_text_echo
        )
        self._running = True

    async def stop(self) -> None:
        self._running = False
        try:
            await self._frame.stop_frame_app()
            await self._frame.disconnect()
        except Exception as exc:  # pragma: no cover - best effort teardown
            LOG.warning("Error during meds controller stop: %s", exc)

    # ---- host actions -----------------------------------------------------

    async def process_tap(self, med: str | None = None) -> CaptureResult:
        """A 'taking meds' capture happened (tap detected). Update state and
        push the right display text to the device."""
        med = med or self._recent_med or self._default_med
        result = self._state.record_capture(med, day=self._today())
        display_text = result.display_text
        if self._privacy_mode:
            # Suppress med names: replace the med name with "[PRIVATE]"
            display_text = display_text.replace(med, "[PRIVATE]")
        await self._frame.send_message(
            TEXT_FLAG, TxPlainText(display_text).pack()
        )
        return result

    async def fire_reminder(self, med: str) -> None:
        """Scheduled push: show 'Time to take [med]' + play the sound cue."""
        self._recent_med = med
        display_med = "[PRIVATE]" if self._privacy_mode else med
        await self._frame.send_message(
            MSG_REMINDER, display_med.encode("utf-8")
        )

    async def reset_display(self) -> None:
        await self._frame.send_message(MSG_RESET, b"")

    def clear_all_data(self) -> int:
        """Delete all capture records from the in-memory state.

        This clears the meds tracking state (double-dose counters, schedules).
        Returns the number of records cleared. For persistent Vestige store
        deletion, use the Vestige MCP delete API separately.
        """
        return self._state.clear_all()

    # ---- reminder scheduler -----------------------------------------------

    async def run_scheduler(self, stop_after: float | None = None) -> None:
        """Fire reminders at their scheduled times until stopped.

        Parameters
        ----------
        stop_after:
            If set, run at most this many *real* seconds (used by tests /
            demos). Schedule times come from the injectable clock, so the
            deadline is measured with ``time.monotonic()`` to stay in real
            time. If ``None`` (production), runs until :meth:`stop` is called.
        """
        import time as _time

        deadline = (
            _time.monotonic() + stop_after if stop_after is not None else None
        )

        while self._running:
            if deadline is not None and _time.monotonic() >= deadline:
                return

            now = self._clock()
            nxt = self._next_due(now)
            if nxt is None:
                # Nothing scheduled; idle briefly then re-check.
                await asyncio.sleep(0.2)
                continue

            wait = (nxt - now).total_seconds()
            if wait > 0:
                # Cap the wait at 0.2 s so the deadline is re-checked promptly.
                await asyncio.sleep(max(0.0, min(wait, 0.2)))
                continue

            # Due now: fire it. Guard against the (frozen-clock) case where a
            # schedule repeatedly reports the same time as due.
            due_key = (nxt, self._med_for_due(nxt))
            if due_key == self._last_fired:
                await asyncio.sleep(0.05)
                continue
            self._last_fired = due_key
            await self.fire_reminder(nxt_med_name := self._med_for_due(nxt))

    # ---- internals --------------------------------------------------------

    def _today(self) -> date:
        return self._clock().date()

    def _next_due(self, now: datetime) -> datetime | None:
        best: datetime | None = None
        for sched in self._schedules:
            d = sched.next_due(now)
            if d is not None and (best is None or d < best):
                best = d
        return best

    def _med_for_due(self, when: datetime) -> str:
        for sched in self._schedules:
            if sched.next_due(when) == when:
                return sched.name
        return self._default_med

    # ---- device -> host handlers (called from the Lua thread) -------------

    def _on_tap(self, _data: bytes) -> None:
        if self._loop is None:
            return
        self.tap_count += 1
        asyncio.run_coroutine_threadsafe(self.process_tap(), self._loop)

    def _on_audio(self, _data: bytes) -> None:
        self.audio_events.append(self._clock())

    def _on_text_echo(self, data: bytes) -> None:
        # First byte is MSG_TEXT_ECHO; the rest is the rendered text.
        self.last_displayed = bytes(data[1:]).decode("utf-8", errors="replace")
