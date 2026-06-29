"""
bench_breakdown.py — Do latency tung tang rieng biet
Chay: python bench_breakdown.py
"""
import os, sys, time, json
sys.path.insert(0, "core")
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"

from dotenv import load_dotenv
load_dotenv()

def ms(t): return f"{(time.perf_counter()-t)*1000:.0f}ms"

print("=" * 55)
print("LATENCY BREAKDOWN — tung tang")
print("=" * 55)

# ── 1. Language detector ──────────────────────────────────
from language_detector import detect_lang
t = time.perf_counter()
for _ in range(10): detect_lang("Co nhung tro choi gi?")
print(f"[1] language_detector x10   : {ms(t)}  (avg {(time.perf_counter()-t)*100:.1f}ms)")

# ── 2. FAQ engine ─────────────────────────────────────────
from faq_engine import faq_match
t = time.perf_counter()
for _ in range(10): faq_match("Suoi Tien o dau?", lang="vi")
print(f"[2] faq_match hit x10       : {ms(t)}  (avg {(time.perf_counter()-t)*100:.1f}ms)")

t = time.perf_counter()
for _ in range(10): faq_match("Co nhung tro choi gi?", lang="vi")
print(f"[2] faq_match miss x10      : {ms(t)}  (avg {(time.perf_counter()-t)*100:.1f}ms)")

# ── 3. Schema search ──────────────────────────────────────
from schema_search import search_tickets, search_attractions
t = time.perf_counter()
for _ in range(5): search_tickets("combo", max_results=5)
print(f"[3] schema search_tickets x5: {ms(t)}  (avg {(time.perf_counter()-t)*200:.1f}ms)")

t = time.perf_counter()
for _ in range(5): search_attractions("tro choi cam giac manh", max_results=5)
print(f"[3] schema search_attract x5: {ms(t)}  (avg {(time.perf_counter()-t)*200:.1f}ms)")

# ── 4. BM25 search ────────────────────────────────────────
try:
    from bm25_search import bm25_search
    t = time.perf_counter()
    for _ in range(5): bm25_search("tro choi", top_k=5)
    print(f"[4] bm25_search x5          : {ms(t)}  (avg {(time.perf_counter()-t)*200:.1f}ms)")
except Exception as e:
    print(f"[4] bm25_search             : ERROR {e}")

# ── 5. Vector search (cold + warm) ───────────────────────
try:
    from vector_search import search_similar as vsearch
    t = time.perf_counter()
    vsearch("tro choi cam giac manh", top_k=5)
    print(f"[5] vector search COLD      : {ms(t)}")
    t = time.perf_counter()
    for _ in range(3): vsearch("tro choi", top_k=5)
    print(f"[5] vector search WARM x3   : {ms(t)}  (avg {(time.perf_counter()-t)*333:.1f}ms)")
except Exception as e:
    print(f"[5] vector search           : ERROR {e}")

# ── 6. Weather API ────────────────────────────────────────
try:
    from weather_service import _get_weather_raw
    t = time.perf_counter()
    r = _get_weather_raw()
    print(f"[6] weather API (no cache)  : {ms(t)}  -> {'OK' if r else 'None'}")
    t = time.perf_counter()
    r = _get_weather_raw()
    print(f"[6] weather API (cached)    : {ms(t)}")
except Exception as e:
    print(f"[6] weather API             : ERROR {e}")

# ── 7. Planner LLM (1 call) ───────────────────────────────
try:
    from planner import plan
    t = time.perf_counter()
    r = plan("Co nhung tro choi gi?", history=[])
    t1 = (time.perf_counter()-t)*1000
    print(f"[7] planner LLM cold        : {t1:.0f}ms -> {[x['tool'] for x in r]}")
    # Lan 2: phai la cache hit
    t = time.perf_counter()
    r = plan("Co nhung tro choi gi?", history=[])
    t2 = (time.perf_counter()-t)*1000
    print(f"[7] planner LLM cached      : {t2:.0f}ms {'✅ cache hit!' if t2 < 50 else '❌ cache miss'}")
    # Lan 3: query khac
    t = time.perf_counter()
    r = plan("Gia ve bao nhieu?", history=[])
    t3 = (time.perf_counter()-t)*1000
    print(f"[7] planner LLM new query   : {t3:.0f}ms -> {[x['tool'] for x in r]}")
    t = time.perf_counter()
    r = plan("Gia ve bao nhieu?", history=[])
    t4 = (time.perf_counter()-t)*1000
    print(f"[7] planner LLM cached 2    : {t4:.0f}ms {'✅ cache hit!' if t4 < 50 else '❌ cache miss'}")
except Exception as e:
    print(f"[7] planner                 : ERROR {e}")

# ── 8. Retrieval orchestrator ─────────────────────────────
try:
    from retrieval_orchestrator import retrieve, build_context
    t = time.perf_counter()
    out = retrieve("tro choi cam giac manh", intent="hoi_tro_choi",
                   strategy=["schema","bm25","vector"], use_vector=True)
    t1 = (time.perf_counter()-t)*1000
    ctx = build_context(out)
    print(f"[8] retrieval full pipeline : {t1:.0f}ms -> source={out['source']} ctx={len(ctx)}chars")
except Exception as e:
    print(f"[8] retrieval               : ERROR {e}")

# ── 9. Responder LLM ─────────────────────────────────────
try:
    from responder import respond
    t = time.perf_counter()
    r = respond("Co nhung tro choi gi?", merged_context="Test context ngan", lang="vi")
    print(f"[9] responder LLM           : {ms(t)} -> {r['source']}")
except Exception as e:
    print(f"[9] responder               : ERROR {e}")

print("=" * 55)
