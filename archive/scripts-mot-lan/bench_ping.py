import urllib.request, json, time

BASE = "http://localhost:8000"

# Test 1: Ping đơn giản
print("=== PING /health ===")
for i in range(3):
    t0 = time.perf_counter()
    urllib.request.urlopen(BASE+"/health", timeout=5).read()
    ms = (time.perf_counter()-t0)*1000
    print(f"  /health: {ms:.0f}ms")

# Test 2: Ping / root
print("\n=== PING / ===")
for i in range(3):
    t0 = time.perf_counter()
    urllib.request.urlopen(BASE+"/", timeout=5).read()
    ms = (time.perf_counter()-t0)*1000
    print(f"  /: {ms:.0f}ms")

# Test 3: Xem server log — DEV_RELOAD có bật không
import os
print("\n=== ENV CHECK ===")
print(f"  DEV_RELOAD : {os.getenv('DEV_RELOAD','0')}")
print(f"  PORT       : {os.getenv('PORT','8000')}")
