import os, sys, time
sys.path.insert(0, "core")
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"

from dotenv import load_dotenv
load_dotenv()

from chat_pipeline import chat

tests = [
    ("FAQ fast path",   "Suoi Tien o dau?"),
    ("Gia ve",          "Gia ve vao cong bao nhieu?"),
    ("Tro choi",        "Co nhung tro choi gi?"),
    ("Combo cu the",    "Combo Kham Pha co gi?"),
    ("Teambuilding",    "Teambuilding 50 nguoi bao nhieu?"),
    ("Kien thuc chung", "Di Suoi Tien nen mac gi?"),
]

print(f"{'Loai':<22} {'Latency':>10}  {'Source':<10} {'Tools':<28} Preview")
print("-" * 100)

total = 0
for label, q in tests:
    t0 = time.perf_counter()
    r  = chat(q)
    ms = (time.perf_counter() - t0) * 1000
    total += ms
    tools   = ",".join(r["tools"]) if r["tools"] else "-"
    preview = r["answer"][:45].replace("\n", " ")
    flag    = " !!!" if ms > 3000 else (" !!" if ms > 1500 else "")
    print(f"{label:<22} {ms:>8.0f}ms  {r['source']:<10} {tools:<28} {preview}{flag}")

print("-" * 100)
print(f"{'Trung binh':<22} {total/len(tests):>8.0f}ms")
print(f"{'Tong':<22} {total:>8.0f}ms")
print()
print("Phan tich:")
print("  < 200ms   = FAQ fast path")
print("  200-800ms = Schema/retrieval")
print("  800-2500ms= Co LLM call (binh thuong)")
print("  > 3000ms  = Qua cham !!!")
