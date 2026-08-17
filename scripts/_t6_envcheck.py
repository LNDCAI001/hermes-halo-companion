import sys
mods = ["imageio", "edge_tts", "faster_whisper", "httpx", "brilliant_msg",
        "halo_emulator", "halo_companion"]
for m in mods:
    try:
        __import__(m)
        print(f"OK   {m}")
    except Exception as e:
        print(f"FAIL {m}: {e}")
print("python", sys.executable)
