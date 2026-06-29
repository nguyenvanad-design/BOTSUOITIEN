import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
TID = "test_cache_session"

def ask(q):
    payload = json.dumps({"message": q, "session_id": TID}).encode()
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

q = "Co nhung tro choi gi?"
print(f"Query: {q}")
for i in range(4):
    t = ask(q)
    hit = "CACHE HIT" if t < 500 else "cold/miss"
    print(f"  Lan {i+1}: {t:.0f}ms  {hit}")
