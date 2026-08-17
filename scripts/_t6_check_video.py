import sys
from pathlib import Path
p = Path("artifacts/t6/demo_full_loop.mp4")
print("size", p.stat().st_size)
with p.open("rb") as f:
    head = f.read(32)
print("magic", head[:12].hex())
# Validate with imageio-ffmpeg reader
try:
    import imageio.v2 as iio
    r = iio.get_reader(str(p))
    meta = r.get_meta_data()
    n = r.count_frames()
    print("frames", n, "fps", meta.get("fps"), "size", meta.get("size"))
    r.close()
    print("VALID MP4")
except Exception as e:
    print("reader err", e)
