"""
T1 smoke test for halo_emulator on Windows.

Run with the PROJECT venv interpreter (NOT the Hermes agent venv) so PIL is not
shadowed. PYTHONPATH is intentionally cleared inside this script to confirm the
emulator works even when the caller's environment leaks a polluted sys.path.

Accepted by kanban task t_360ebf80:
  - halo_emulator imports
  - framebuffer renders as a PIL Image (256x256 RGBA)
  - inject_button_single / inject_imu_tap produce output events

Idiomatic usage note: an emulator instance must not be stop()'d and then
re-start()'d with a different script — stop() leaves a 'stop' Event in the
queue that kills the next script. Use a fresh instance per scenario, exactly
like the project's own pytest fixture does.
"""
from __future__ import annotations

import sys
import os
import time
import tempfile
from pathlib import Path

# Defeat the PIL-shadowing gotcha: strip any inherited PYTHONPATH / sys.path
# pollution so we only use the project venv's own packages.
os.environ.pop("PYTHONPATH", None)
sys.path = [p for p in sys.path if "hermes-agent" not in p.lower()]

REPO = Path(__file__).resolve().parent.parent
LUA_DIR = REPO / "packages" / "halo_emulator" / "tests" / "lua"

import PIL  # noqa: E402
from PIL import Image  # noqa: E402

from halo_emulator import HaloEmulator  # noqa: E402


def check_render() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="t1_render_"))
    emu = HaloEmulator(sandbox_dir=tmp, print_handler=print)
    draw_lua = LUA_DIR / "draw_shapes.lua"
    assert draw_lua.exists(), f"missing {draw_lua}"
    emu.load_file(draw_lua)
    emu.start("draw_shapes.lua")
    time.sleep(0.3)

    img = emu.get_framebuffer()
    assert isinstance(img, Image.Image), f"framebuffer not a PIL Image: {type(img)!r}"
    assert img.size == (256, 256), f"framebuffer size {img.size}"
    assert img.mode == "RGBA", f"framebuffer mode {img.mode}"
    extrema = img.getextrema()
    print(f"[render] framebuffer extrema={extrema}")
    assert any(hi > 0 for (_lo, hi) in extrema), "framebuffer appears blank"
    out = tmp / "framebuffer.png"
    img.save(out)
    print(f"[render] saved -> {out}")
    emu.stop()
    time.sleep(0.2)
    return out


def check_injection() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="t1_inject_"))
    emu = HaloEmulator(sandbox_dir=tmp, print_handler=print)
    cb_lua = LUA_DIR / "event_callbacks.lua"
    assert cb_lua.exists(), f"missing {cb_lua}"
    emu.load_file(cb_lua)
    emu.start("event_callbacks.lua")
    time.sleep(0.2)  # let Lua register callbacks

    emu.inject_button_single()
    emu.inject_imu_tap()
    time.sleep(0.3)

    sent = emu.get_bluetooth_sent()
    print(f"[inject] bluetooth sent bytes: {[list(b) for b in sent]}")
    joined = b"".join(sent)
    assert b"\x01" in joined, "button_single did not produce event"
    assert b"\x04" in joined, "imu_tap did not produce event"
    emu.stop()
    time.sleep(0.2)


def main() -> int:
    print(f"[smoke] python={sys.executable}")
    print(f"[smoke] PIL={PIL.__file__}")

    out = check_render()
    check_injection()

    print("[smoke] OK: imports + framebuffer PIL Image + button_single + imu_tap")
    print(f"[smoke] framebuffer artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
