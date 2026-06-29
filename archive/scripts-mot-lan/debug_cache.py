import urllib.request, json
BASE = "http://127.0.0.1:8000"

# Goi endpoint debug de kiem tra cache
payload = json.dumps({"message": "test cache debug"}).encode()
req = urllib.request.Request(
    BASE + "/api/chat", data=payload,
    headers={"Content-Type": "application/json"}, method="POST"
)
urllib.request.urlopen(req, timeout=10).read()

# Kiem tra truc tiep file planner dang dung
import sys, os
sys.path.insert(0, "core")
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"
from dotenv import load_dotenv
load_dotenv()

import planner
print("File:", planner.__file__)
print("Has _plan_cache:", hasattr(planner, "_plan_cache"))
print("Has _cache_get:", hasattr(planner, "_cache_get"))

if hasattr(planner, "_cache_get"):
    from planner import plan, _plan_cache
    import time
    print("\nTest cache truc tiep:")
    t0 = time.perf_counter()
    r1 = plan("Co nhung tro choi gi?", history=[])
    t1 = (time.perf_counter()-t0)*1000
    print(f"  Lan 1: {t1:.0f}ms -> {[x['tool'] for x in r1]}")
    print(f"  Cache size: {len(_plan_cache)}")
    t0 = time.perf_counter()
    r2 = plan("Co nhung tro choi gi?", history=[])
    t2 = (time.perf_counter()-t0)*1000
    print(f"  Lan 2: {t2:.0f}ms -> {'HIT' if t2 < 10 else 'MISS'}")
    print(f"  Cache size: {len(_plan_cache)}")
else:
    print("CACHE CHUA CO - planner.py cu dang duoc dung!")
    print("Kiem tra lai file:")
    import subprocess
    result = subprocess.run(
        ["findstr", "_plan_cache", "core\\planner.py"],
        capture_output=True, text=True
    )
    print(result.stdout[:300] if result.stdout else "KHONG TIM THAY _plan_cache trong file!")
