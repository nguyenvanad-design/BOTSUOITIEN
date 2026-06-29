import urllib.request, json, time, sys
sys.path.insert(0, "core")
import os
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"
from dotenv import load_dotenv; load_dotenv()

BASE = "http://127.0.0.1:8000"

def ask_stream(q, sid="bench"):
    payload = json.dumps({"message": q, "session_id": sid}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    t_first = None
    full = ""
    with urllib.request.urlopen(req, timeout=30) as resp:
        for chunk in resp:
            line = chunk.decode("utf-8").strip()
            if not line.startswith("data:"): continue
            raw = line[5:].strip()
            if raw == "[DONE]": break
            try:
                ev = json.loads(raw)
                if ev["type"] == "token":
                    if t_first is None: t_first = time.perf_counter()
                    full += ev.get("text","")
            except: pass
    total = (time.perf_counter()-t0)*1000
    ttft  = (t_first - t0)*1000 if t_first else total
    return ttft, total, full

print("=" * 62)
print("LATENCY BREAKDOWN — RAG vs LLM vs Total")
print("=" * 62)

from planner import plan
from tool_executor import execute_tool, merge_contexts
from retrieval_orchestrator import retrieve, build_context
from responder import respond

queries = [
    ("FAQ hit",        "Suối Tiên ở đâu?"),
    ("Schema only",    "Combo Khám Phá có gì?"),
    ("BM25+Vector",    "Có những trò chơi cảm giác mạnh nào?"),
    ("Multi-tool",     "Thời tiết hôm nay và nên mặc gì?"),
    ("Complex",        "Teambuilding 50 người giá bao nhiêu?"),
]

print(f"\n{'Query':<28} {'Planner':>9} {'RAG':>8} {'Responder':>11} {'TTFT':>8} {'Total':>8}")
print("-" * 80)

for label, q in queries:
    # 1. Planner
    t0 = time.perf_counter()
    try:
        tool_calls = plan(q, history=[])
        t_plan = (time.perf_counter()-t0)*1000
    except Exception as e:
        print(f"{label:<28}  ERROR plan: {e}")
        continue

    # 2. RAG (execute tools)
    t0 = time.perf_counter()
    try:
        results = [execute_tool(tc, lang="vi") for tc in tool_calls]
        merged  = merge_contexts(results)
        t_rag   = (time.perf_counter()-t0)*1000
    except Exception as e:
        t_rag = 0; merged = ""
        print(f"  RAG error: {e}")

    # 3. Responder (blocking, no stream)
    t0 = time.perf_counter()
    try:
        resp = respond(q, merged_context=merged, lang="vi", history=[])
        t_resp = (time.perf_counter()-t0)*1000
    except Exception as e:
        t_resp = 0

    # 4. TTFT qua HTTP stream (thực tế user thấy)
    ttft, total_http, _ = ask_stream(q)

    total_direct = t_plan + t_rag + t_resp
    print(f"{label:<28} {t_plan:>7.0f}ms {t_rag:>7.0f}ms {t_resp:>9.0f}ms  "
          f"{ttft:>6.0f}ms {total_http:>6.0f}ms")

print("-" * 80)
print("Planner = LLM1 tool calling (Grok)")
print("RAG     = schema search + BM25 + vector + merge")
print("Responder = LLM2 response gen (Grok)")
print("TTFT    = time to first token qua HTTP stream")
print("Total   = full response time qua HTTP")
