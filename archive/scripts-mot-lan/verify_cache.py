import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

print("=" * 55)
print("VERIFY PLANNER CACHE")
print("=" * 55)

def ask_stream(q):
    payload = json.dumps({"message": q}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    t_first = None
    with urllib.request.urlopen(req, timeout=30) as resp:
        for chunk in resp:
            line = chunk.decode("utf-8").strip()
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw == "[DONE]": break
                try:
                    ev = json.loads(raw)
                    if ev["type"] == "token" and t_first is None:
                        t_first = time.perf_counter()
                except: pass
    return (t_first - t0) * 1000 if t_first else 0

tests = [
    "Co nhung tro choi gi?",
    "Combo Kham Pha co gi?",
    "Teambuilding 50 nguoi bao nhieu?",
]

for q in tests:
    print(f"\nQuery: {q}")
    t1 = ask_stream(q)
    print(f"  Lan 1 (cold)   : {t1:.0f}ms")
    t2 = ask_stream(q)
    print(f"  Lan 2 (cached) : {t2:.0f}ms  {'CACHE HIT' if t2 < 500 else 'cache miss'}")
    t3 = ask_stream(q)
    print(f"  Lan 3 (cached) : {t3:.0f}ms  {'CACHE HIT' if t3 < 500 else 'cache miss'}")

print("\n" + "=" * 55)
print("< 500ms lan 2/3 = cache hoat dong")
print("= ~same lan 1   = cache chua hoat dong")
print("=" * 55)
