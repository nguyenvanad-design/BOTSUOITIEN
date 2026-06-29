import urllib.request, json, time

# Dung IP truc tiep, bo qua DNS lookup
BASE = "http://127.0.0.1:8000"

tests = [
    ("FAQ fast path",   "Suoi Tien o dau?"),
    ("Gia ve",          "Gia ve vao cong bao nhieu?"),
    ("Tro choi",        "Co nhung tro choi gi?"),
    ("Combo cu the",    "Combo Kham Pha co gi?"),
    ("Teambuilding",    "Teambuilding 50 nguoi bao nhieu?"),
    ("Kien thuc chung", "Di Suoi Tien nen mac gi?"),
]

print(f"{'Loai':<22} {'Latency':>10}  {'Source':<10} Preview")
print("-" * 80)

total = 0
for label, q in tests:
    payload = json.dumps({"message": q}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    ms = (time.perf_counter() - t0) * 1000
    total += ms
    preview = data.get("answer","")[:45].replace("\n"," ")
    source  = data.get("source","?")
    flag    = " !!!" if ms > 5000 else (" !!" if ms > 2500 else "")
    print(f"{label:<22} {ms:>8.0f}ms  {source:<10} {preview}{flag}")

print("-" * 80)
print(f"{'Trung binh':<22} {total/len(tests):>8.0f}ms")
