import time, platform
from photon_ai.slicer import slice_huge_file_surgical
from photon_ai.engine import TinyCodeEngine

sample = "def fetch(url: str) -> dict:\n    return requests.get(url).json()\n"
open("sample_bench.py", "w").write("def pad(x): return x\n" * 150 + sample)

t0 = time.perf_counter()
ctx, bfn = slice_huge_file_surgical("sample_bench.py", 151)
s_ms = (time.perf_counter() - t0) * 1000

eng = TinyCodeEngine()
t1 = time.perf_counter()
fix = eng.generate_patch("py", "NameError: name 'requests' is not defined", ctx, bfn)
d_ms = (time.perf_counter() - t1) * 1000

print(f"CPU: {platform.machine()} | Slicer: {s_ms:.2f} ms | Patch Time: {d_ms:.1f} ms")
print("Valid:", "import requests" in fix)
