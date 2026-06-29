"""
test_regression.py — Bộ test hồi quy cho Suối Tiên bot.
Chạy OFFLINE — không cần API key, không cần BM25/FAISS index.

Kiểm tra 3 nhóm lỗi đã từng có:
1. FAQ false-positive (regex không boundary, rule quá rộng)
2. FAQ false-negative (câu hợp lệ phải vào fast path)
3. Pipeline: parallel execution giữ thứ tự + cô lập lỗi từng tool

Chạy: python test_regression.py
"""

import os
import sys
from pathlib import Path

_BASE = Path(__file__).parent
os.environ.setdefault("SUOITIEN_BASE",  str(_BASE))
os.environ.setdefault("SUOITIEN_DATA",  str(_BASE / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(_BASE / "data" / "suoitien_clean_v4.json"))
sys.path.insert(0, str(_BASE))

PASS = FAIL = 0

def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


# ════════════════════════════════════════════════════════════════════════════
# Nhóm 1+2: FAQ routing
# ════════════════════════════════════════════════════════════════════════════
print("\n── FAQ ENGINE ──────────────────────────────────────────")
from faq_engine import faq_match

# (query, lang, expected_rule hoặc None)
FAQ_CASES = [
    # ── Phải MATCH đúng rule ──
    ("Suối Tiên ở đâu vậy?",                  "vi", "dia_chi"),
    ("Cho em xin địa chỉ công viên",          "vi", "dia_chi"),
    ("Suối Tiên nằm ở quận nào?",             "vi", "dia_chi"),
    ("Số điện thoại liên hệ?",                "vi", "lien_he"),
    ("Hotline bao nhiêu?",                    "vi", "lien_he"),
    ("Email của công viên là gì?",            "vi", "lien_he"),
    ("Mấy giờ mở cửa?",                       "vi", "gio_mo_cua"),
    ("Giờ hoạt động của công viên?",          "vi", "gio_mo_cua"),
    ("Công viên đóng cửa lúc mấy giờ?",       "vi", "gio_mo_cua"),
    ("Giá vé vào cổng bao nhiêu?",            "vi", "gia_ve"),
    ("Vào công viên mất tiền không?",         "vi", "gia_ve"),
    ("gia ve bao nhieu",                      "vi", "gia_ve"),       # không dấu
    ("Mua vé online ở đâu?",                  "vi", "mua_ve_online"),
    ("Đặt vé trước được không?",              "vi", "mua_ve_online"),
    ("Có xe buýt nào đến không?",             "vi", "xe_bus"),
    ("Tuyến bus số mấy đi Suối Tiên?",        "vi", "xe_bus"),
    ("Đi metro đến Suối Tiên được không?",    "vi", "duong_di"),
    ("Cách đi đến Suối Tiên từ quận 1?",      "vi", "duong_di"),
    ("Gửi xe máy ở đâu?",                     "vi", "gui_xe"),
    ("Bãi xe có rộng không?",                 "vi", "gui_xe"),
    ("Thời tiết hôm nay thế nào?",            "vi", "thoi_tiet"),
    ("Cho xin bản đồ công viên",              "vi", "ban_do"),
    ("What's the weather today?",             "en", "thoi_tiet"),
    ("What time does the park open?",         "en", "gio_mo_cua"),

    # ── KHÔNG được match (false positive cũ) ──
    ("Go Kart giá bao nhiêu?",                "vi", None),  # giá trò cụ thể → planner
    ("Vé trò chơi Infinity Slide bao nhiêu?", "vi", None),
    ("Go Kart ở đâu?",                        "vi", None),  # vị trí TRONG park
    ("Thủy cung ở chỗ nào?",                  "vi", None),
    ("Đoạn đường đến Suối Tiên xa không?",    "vi", None),  # "doan" ≠ "đoàn"
    ("Tư vấn cho doanh nghiệp 50 người",      "vi", None),  # "doanh" ≠ "đoàn"
    ("Trò chơi ngoài trời có gì?",            "vi", None),  # "trời" ≠ thời tiết
    ("Hôm nay nắng quá, có trò trong nhà không?", "vi", None),
    ("Ăn trưa ở khu nào ngon?",               "vi", None),  # nhà hàng → planner
    ("Nhà hàng nào có buffet?",               "vi", None),
    ("Show biểu diễn mấy giờ bắt đầu?",       "vi", None),  # giờ show ≠ giờ mở cửa
    ("Teambuilding 50 người giá bao nhiêu?",  "vi", None),  # → planner + schema
    ("Khu trẻ em có gì chơi?",                "vi", None),
    ("Giá vé bao nhiêu và đi xe buýt nào tới?","vi", None), # đa ý → planner tách
    ("门票多少钱？",                            "zh", "gia_ve"),  # zh → FAQ handles,  # zh → LLM responder
    ("입장권 가격이 얼마예요?",                  "ko", "gia_ve"),  # ko → FAQ handles
]

for q, lang, expected in FAQ_CASES:
    result = faq_match(q, lang=lang)
    got = result["rule"] if result else None
    check(f"[{lang}] '{q}' → {got}", got == expected,
          f"(expected {expected})")


# ════════════════════════════════════════════════════════════════════════════
# Nhóm 3: Pipeline — thứ tự + cô lập lỗi
# ════════════════════════════════════════════════════════════════════════════
print("\n── PIPELINE: PARALLEL EXECUTION ────────────────────────")
import time as _time
import chat_pipeline
from chat_pipeline import _execute_parallel, _try_faq

# Mock execute_tool: tool đầu chạy CHẬM hơn tool sau → as_completed cũ sẽ đảo
def _mock_exec(call, lang="vi"):
    name = call["tool"]
    if name == "slow":
        _time.sleep(0.4)
    if name == "boom":
        raise RuntimeError("tool exploded")
    if name == "hang":
        _time.sleep(60)
    return {"tool": name, "source": "mock", "context": f"ctx-{name}",
            "raw": {}, "intent": "test"}

_orig = chat_pipeline.execute_tool
chat_pipeline.execute_tool = _mock_exec

calls = [{"tool": "slow", "intent": "t"}, {"tool": "fast", "intent": "t"}]
res = _execute_parallel(calls, lang="vi")
check("Giữ thứ tự khi tool đầu chậm hơn (A vs B không bị đảo)",
      [r["tool"] for r in res] == ["slow", "fast"],
      f"got {[r['tool'] for r in res]}")

calls = [{"tool": "boom", "intent": "t"}, {"tool": "fast", "intent": "t"}]
res = _execute_parallel(calls, lang="vi")
check("1 tool raise exception → không sập, tool khác vẫn có context",
      res[0]["source"] == "error" and res[1]["context"] == "ctx-fast")

chat_pipeline._TOOL_TIMEOUT = 0.5
calls = [{"tool": "hang", "intent": "t"}, {"tool": "fast", "intent": "t"}]
t0 = _time.monotonic()
res = _execute_parallel(calls, lang="vi")
elapsed = _time.monotonic() - t0
check("1 tool treo → timeout cô lập, không raise TimeoutError ra ngoài",
      res[0]["source"] == "error" and res[1]["context"] == "ctx-fast" and elapsed < 5,
      f"elapsed={elapsed:.1f}s sources={[r['source'] for r in res]}")
chat_pipeline._TOOL_TIMEOUT = 8.0
chat_pipeline.execute_tool = _orig

print("\n── PIPELINE: FAQ GATE ──────────────────────────────────")
r = _try_faq("Suối Tiên ở đâu?", "vi", history=[], enabled=True)
check("Câu mở đầu hợp lệ → đi FAQ fast path", r is not None and r["rule"] == "dia_chi")

history = [{"role": "user", "content": "Go Kart có vui không?"},
           {"role": "assistant", "content": "Go Kart rất vui ạ!"}]
r = _try_faq("nó ở đâu vậy?", "vi", history=history, enabled=True)
check("Follow-up có history → KHÔNG đi FAQ (để Planner đọc ngữ cảnh)", r is None)

r = _try_faq("Suối Tiên ở đâu?", "vi", history=[], enabled=False)
check("use_faq_fast_path=False → bỏ qua FAQ", r is None)


# ════════════════════════════════════════════════════════════════════════════
# Nhóm 4: Responder offline behavior
# ════════════════════════════════════════════════════════════════════════════
print("\n── RESPONDER (offline) ─────────────────────────────────")
import responder
from prompts import FALLBACK_MESSAGE

out = responder.respond("hỏi gì đó", merged_context="", lang="vi", history=None)
check("Không context + không history → fallback message",
      out["source"] == "fallback" and out["answer"] == FALLBACK_MESSAGE["vi"])

out = responder.respond("hỏi", merged_context="", lang="ja", history=None)
check("Fallback đúng ngôn ngữ (ja)", out["answer"] == FALLBACK_MESSAGE["ja"])

system, messages = responder._build("câu hỏi", "CONTEXT", "en", [])
check("Builder chèn đúng language instruction (không còn bug {{lang_note}})",
      "English" in system and "{lang_note}" not in system)
check("Builder gắn Tool Results vào user message",
      "Tool Results:\nCONTEXT" in messages[-1]["content"])

chunks = list(responder.respond_stream("q", merged_context="", lang="vi", history=None))
check("Stream không context → yield đúng 1 fallback",
      chunks == [FALLBACK_MESSAGE["vi"]])


# ════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*56}\nKẾT QUẢ: {PASS} passed / {FAIL} failed / {PASS+FAIL} total")
sys.exit(1 if FAIL else 0)
