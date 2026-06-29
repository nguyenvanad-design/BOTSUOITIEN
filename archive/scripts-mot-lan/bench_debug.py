import urllib.request, json, time

BASE = "http://localhost:8000"

# Test 1: FAQ cold vs warm
print("=== FAQ WARM-UP TEST ===")
for i in range(3):
    payload = json.dumps({"message": "Suoi Tien o dau?"}).encode()
    req = urllib.request.Request(BASE+"/api/chat", data=payload,
          headers={"Content-Type":"application/json"}, method="POST")
    t0 = time.perf_counter()
    urllib.request.urlopen(req, timeout=10).read()
    ms = (time.perf_counter()-t0)*1000
    print(f"  Lan {i+1}: {ms:.0f}ms")

# Test 2: Health check model status
print("\n=== HEALTH CHECK ===")
with urllib.request.urlopen(BASE+"/health", timeout=5) as r:
    print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))

# Test 3: LLM time breakdown
print("\n=== LLM LATENCY x3 ===")
for i in range(3):
    payload = json.dumps({"message": "Gia ve combo bao nhieu?"}).encode()
    req = urllib.request.Request(BASE+"/api/chat", data=payload,
          headers={"Content-Type":"application/json"}, method="POST")
    t0 = time.perf_counter()
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    ms = (time.perf_counter()-t0)*1000
    print(f"  Lan {i+1}: {ms:.0f}ms | source={data['source']}")
