import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("TEST STREAMING SSE")
print("=" * 60)

tests = [
    ("FAQ fast path",   "Suoi Tien o dau?"),
    ("Gia ve",          "Gia ve vao cong bao nhieu?"),
    ("Tro choi",        "Co nhung tro choi gi?"),
    ("Combo",           "Combo Kham Pha co gi?"),
]

for label, q in tests:
    payload = json.dumps({"message": q}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    t_first_token = None
    full_text = ""
    meta = {}
    events = []

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            buf = ""
            for chunk in resp:
                line = chunk.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    ev = json.loads(raw)
                    events.append(ev["type"])
                    if ev["type"] == "meta":
                        meta = ev
                    elif ev["type"] == "token":
                        if t_first_token is None:
                            t_first_token = time.perf_counter()
                        full_text += ev.get("text", "")
                except:
                    pass

        t_total = (time.perf_counter() - t0) * 1000
        t_ttft  = (t_first_token - t0) * 1000 if t_first_token else 0

        print(f"\n[{label}]")
        print(f"  TTFT (time to first token) : {t_ttft:.0f}ms")
        print(f"  Total                      : {t_total:.0f}ms")
        print(f"  Source                     : {meta.get('source','?')}")
        print(f"  Events                     : {events[:8]}")
        print(f"  Preview                    : {full_text[:60].replace(chr(10),' ')}")

    except Exception as e:
        print(f"\n[{label}] ERROR: {e}")

print("\n" + "=" * 60)
print("TTFT < 100ms  = FAQ streaming ok")
print("TTFT < 1000ms = LLM streaming ok (user nhin thay chu som)")
print("TTFT > 3000ms = Co van de")
print("=" * 60)
