import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

tests = [
    ("EN short: ticket",     "ticket"),
    ("EN short: open",       "open"),
    ("EN short: food",       "food"),
    ("EN short: water park", "water park"),
    ("ZH: men piao",         "门票多少钱？"),
    ("ZH: kai men",          "几点开门？"),
    ("ZH: can ting",         "有餐厅吗？"),
    ("KO: ticket",           "입장권 가격이 얼마예요?"),
    ("KO: noli",             "놀이 기구가 있어요?"),
    ("EN: kids zone",        "Is there a kids zone?"),
    ("EN: re-enter",         "Can I re-enter?"),
    ("EN: restaurant",       "Is there a restaurant?"),
    ("VI: tro choi",         "Có những trò chơi gì?"),
]

print(f"{'Case':<25} {'TTFT':>8}  {'Source':<8} Preview")
print("-" * 80)
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
    ttft = (t_first - t0)*1000 if t_first else 0
    flag = " !!!" if ttft > 5000 else (" !!" if ttft > 2000 else "")
    preview = full[:40].replace("\n"," ")
    print(f"{label:<25} {ttft:>7.0f}ms  {source:<8} {preview}{flag}")
