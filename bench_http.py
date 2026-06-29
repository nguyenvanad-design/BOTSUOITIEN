import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

tests = [
    ("FAQ fast path",   "Suoi Tien o dau?"),
    ("Gia ve",          "Gia ve vao cong bao nhieu?"),
    ("Tro choi",        "Co nhung tro choi gi?"),
    ("Combo",           "Combo Kham Pha co gi?"),
    ("Teambuilding",    "Teambuilding 50 nguoi bao nhieu?"),
    ("Kien thuc chung", "Di Suoi Tien nen mac gi?"),
]

print(f"{'Loai':<22} {'Latency':>10}  {'Source':<10} Preview")
print("-" * 80)

total = 0
for label, q in tests:
    payload = json.dumps({"message": q}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    t_first = None
    full = ""
    source = "?"
    with urllib.request.urlopen(req, timeout=30) as resp:
        for chunk in resp:
            line = chunk.decode("utf-8").strip()
            if not line.startswith("data:"): continue
            raw = line[5:].strip()
            if raw == "[DONE]": break
            try:
                ev = json.loads(raw)
                if ev["type"] == "meta": source = ev.get("source","?")
                elif ev["type"] == "token":
                    if t_first is None: t_first = time.perf_counter()
                    full += ev.get("text","")
            except: pass
    ms = (time.perf_counter() - t0) * 1000
    ttft = (t_first - t0) * 1000 if t_first else ms
    total += ttft
    flag = " !!!" if ttft > 5000 else (" !!" if ttft > 2500 else "")
    preview = full[:45].replace("\n"," ")
    print(f"{label:<22} TTFT:{ttft:>6.0f}ms  {source:<10} {preview}{flag}")

print("-" * 80)
print(f"{'Trung binh TTFT':<22} {total/len(tests):>6.0f}ms")
