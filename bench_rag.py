import sys, os, time
sys.path.insert(0, "core")
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"
from dotenv import load_dotenv; load_dotenv()

print("=" * 58)
print("RAG BREAKDOWN — từng tầng")
print("=" * 58)

# ── Pre-warm tất cả models ──────────────────────────────────
print("\nWarming up...")
from bm25_search import bm25_search
from vector_search import vector_search as vsearch
from schema_search import search_attractions, search_tickets

bm25_search("warm", top_k=1)
try: vsearch("warm", top_k=1)
except: pass
print("Warm done\n")

Q = "Co nhung tro choi cam giac manh nao?"

# 1. Schema search
t = time.perf_counter()
for _ in range(5):
    r = search_attractions(Q, max_results=5)
t1 = (time.perf_counter()-t)*200
print(f"[1] Schema search x5 avg     : {t1:.1f}ms  ({len(r)} results)")

# 2. BM25
t = time.perf_counter()
for _ in range(5):
    r2 = bm25_search(Q, top_k=10)
t2 = (time.perf_counter()-t)*200
print(f"[2] BM25 search x5 avg       : {t2:.1f}ms  ({len(r2)} chunks)")

# 3. Vector search warm
t = time.perf_counter()
for _ in range(5):
    try: r3 = vsearch(Q, top_k=10)
    except Exception as e: r3 = []; print(f"    vector err: {e}"); break
t3 = (time.perf_counter()-t)*200
print(f"[3] Vector search x5 avg     : {t3:.1f}ms  ({len(r3)} results)")

# 4. RRF merge
from retrieval_orchestrator import rrf_merge
t = time.perf_counter()
for _ in range(5):
    merged = rrf_merge([r2, r3], top_k=5)
t4 = (time.perf_counter()-t)*200
print(f"[4] RRF merge x5 avg         : {t4:.1f}ms")

# 5. Full retrieval pipeline
from retrieval_orchestrator import retrieve, build_context
t = time.perf_counter()
out = retrieve(Q, intent="hoi_tro_choi", strategy=["schema","bm25","vector"], use_vector=True)
t5 = (time.perf_counter()-t)*1000
ctx = build_context(out)
print(f"[5] Full retrieval pipeline  : {t5:.0f}ms  source={out['source']} ctx={len(ctx)}chars")

# 6. Cold load simulation (xem BGE-M3 tốn bao nhiêu)
print(f"\nBGE-M3 model size in memory:")
try:
    import vector_search as vs
    model = vs._get_model()
    params = sum(p.numel() for p in model[0].parameters()) if hasattr(model, '__iter__') else 0
    print(f"  Model loaded: yes")
except Exception as e:
    print(f"  {e}")

print("\n" + "=" * 58)
print(f"TỔNG RAG (warm):  {t1+t2+t3+t4:.0f}ms")
print(f"  Schema: {t1:.0f}ms  BM25: {t2:.0f}ms  Vector: {t3:.0f}ms  RRF: {t4:.0f}ms")
print("=" * 58)
print("\nNote: 16s trước là BGE-M3 cold load (chỉ xảy ra 1 lần)")
print("Production (server warm): chỉ còn phần trên")
