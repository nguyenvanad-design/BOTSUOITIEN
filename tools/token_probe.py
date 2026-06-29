"""
token_probe.py — Mổ xẻ token: bot gọi LLM mấy lần / 1 câu, token đi đâu.
Đo bằng field `usage` thật từ API (không ước lượng).
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
os.environ.setdefault("SUOITIEN_BASE",  str(ROOT / "core"))
os.environ.setdefault("SUOITIEN_DATA",  str(ROOT / "core" / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(ROOT / "core" / "data" / "suoitien_clean_v4.json"))

import llm_client
from language_detector import detect_lang
from planner import plan, PLANNER_TOOLS
from prompts import PLANNER_SYSTEM, RESPONDER_SYSTEM
from tool_executor import execute_all, merge_contexts
from responder import respond

# ── Kích thước prompt tĩnh (gửi lại MỖI call) ──────────────────────────────────
tools_json = json.dumps(PLANNER_TOOLS, ensure_ascii=False)
print("=== PROMPT TĨNH (gửi lại mỗi call) ===")
print(f"PLANNER_SYSTEM   : {len(PLANNER_SYSTEM):>6,} chars")
print(f"PLANNER_TOOLS (8): {len(tools_json):>6,} chars")
print(f"RESPONDER_SYSTEM : {len(RESPONDER_SYSTEM):>6,} chars")

QUERIES = [
    "Trò chơi cảm giác mạnh nào hay nhất?",          # 1 tool, schema search
    "Giá vé bao nhiêu và có nhà hàng buffet không?", # đa ý → 2 tools
    "Teambuilding 50 người giá bao nhiêu?",          # entity extraction
]

print("\n=== ĐO THỰC TẾ TỪNG CÂU ===")
for q in QUERIES:
    llm_client.reset_usage()
    lang = detect_lang(q)

    tool_calls = plan(q)
    u1 = llm_client.get_usage().get("planner", {"calls": 0, "input": 0, "output": 0})

    results = execute_all(tool_calls, lang=lang)
    merged  = merge_contexts(results)

    resp = respond(query=q, merged_context=merged, lang=lang)
    u2 = llm_client.get_usage().get("responder", {"calls": 0, "input": 0, "output": 0})

    total = u1["input"] + u1["output"] + u2["input"] + u2["output"]
    print(f"\nQ: {q}")
    print(f"  Planner  : {u1['calls']} call | in={u1['input']:>5,} out={u1['output']:>4,}"
          f" | tools={[c['tool'] for c in tool_calls]}")
    print(f"  Context  : {len(merged):,} chars (retrieval → nhét vào responder)")
    print(f"  Responder: {u2['calls']} call | in={u2['input']:>5,} out={u2['output']:>4,}")
    print(f"  TỔNG     : {total:,} tokens")
