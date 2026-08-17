"""
T4 meds-alert demo: boots the meds Lua app on the emulator, runs a capture
(double-dose) and a reminder, and saves the framebuffer PNGs as artifacts.

Usage:
    PYTHONPATH= .venv/Scripts/python.exe scripts/t4_meds_alert_demo.py [outdir]

Accepts:
  - double-dose: 2nd "taking meds" capture in a day -> "You already took this today"
  - reminder:    scheduled push -> "Time to take [med]" + native sound fired
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

os.environ.pop("PYTHONPATH", None)

from halo_companion.controller import MedSchedule, MedsController  # noqa: E402
from halo_emulator import EmulatorBrilliantMsg, HaloEmulator  # noqa: E402


async def run(outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    emu = HaloEmulator(sandbox_dir=outdir / "_sandbox", print_handler=print)
    frame = EmulatorBrilliantMsg(emu)
    ctrl = MedsController(
        frame,
        clock=lambda: datetime(2026, 8, 13, 9, 0, 0),
        schedules=[MedSchedule("aspirin", [dtime(9, 0)])],
    )
    await ctrl.start()
    artifacts: list[Path] = []
    try:
        # 1) first capture -> confirmation
        await ctrl.process_tap("aspirin")
        time.sleep(0.4)
        p1 = outdir / "meds_taken.png"
        emu.get_framebuffer().save(p1)
        artifacts.append(p1)
        print(f"[t4] capture #1 -> {p1}")

        # 2) second capture same day -> double-dose alert
        await ctrl.process_tap("aspirin")
        time.sleep(0.4)
        p2 = outdir / "meds_double_dose.png"
        emu.get_framebuffer().save(p2)
        artifacts.append(p2)
        print(f"[t4] capture #2 (double-dose) -> {p2}")

        # 3) scheduled reminder -> "Time to take aspirin" + audio
        await ctrl.fire_reminder("aspirin")
        time.sleep(0.4)
        p3 = outdir / "meds_reminder.png"
        emu.get_framebuffer().save(p3)
        artifacts.append(p3)
        print(f"[t4] reminder -> {p3}")

        audio = len(ctrl.audio_events)
        print(f"[t4] audio events observed: {audio}")
        if audio == 0:
            print("[t4] WARNING: native sound primitive never fired")
    finally:
        await ctrl.stop()
    return artifacts


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/t4")
    artifacts = asyncio.run(run(outdir))
    print(f"[t4] OK: {len(artifacts)} framebuffer artifacts")
    for a in artifacts:
        print(f"    {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
