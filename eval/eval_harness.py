"""
eval_harness.py — Benchmark Suối Tiên bot
Chạy: python eval_harness.py
Output: eval_results.json + summary table

Test categories:
  L1 - FAQ (giá vé, giờ, địa chỉ, hotline)        target >95%
  L2 - Schema (structured lookup)                   target >85%
  L3 - Complex (tổng hợp, so sánh, multi-intent)   target >75%
  L4 - Edge (typo, không dấu, OOS)                  target >60%
"""

import os
import sys
import json
import time
from pathlib import Path

# Harness nằm trong eval/ — core/ và data/ nằm ở project root
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "core"
sys.path.insert(0, str(CORE))

# Load .env TRƯỚC khi import core — planner/responder đọc
# ANTHROPIC_API_KEY ngay lúc import; thiếu key là cả run rơi về fallback.
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

os.environ.setdefault("SUOITIEN_BASE",  str(CORE))
os.environ.setdefault("SUOITIEN_DATA",  str(CORE / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(CORE / "data" / "suoitien_clean_v4.json"))

from chat_pipeline import chat

# ── Eval set ───────────────────────────────────────────────────────────────────
# Format: {id, query, category, level, must_contain, must_not_contain, check_fn}
# must_contain: list of strings — ít nhất 1 phải có trong answer
# must_not_contain: list of strings — không được có trong answer
# check_fn: optional callable(answer) -> bool

EVAL_SET = [

    # ══════════════════════════════════════════════════════════════════
    # L1 — FAQ: Giá vé
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L1_001", "level": "L1", "category": "gia_ve",
        "query": "Giá vé vào cổng bao nhiêu?",
        "must_contain": ["vé", "đ", "giá"],
        "must_not_contain": ["xin lỗi", "không tìm thấy"],
    },
    {
        "id": "L1_002", "level": "L1", "category": "gia_ve",
        "query": "gia ve vao cong bao nhieu",
        "must_contain": ["vé", "đ", "giá"],
        "must_not_contain": [],
    },
    {
        "id": "L1_003", "level": "L1", "category": "gia_ve",
        "query": "Vé trẻ em giá bao nhiêu?",
        "must_contain": ["trẻ em", "đ"],
        "must_not_contain": [],
    },
    {
        "id": "L1_004", "level": "L1", "category": "gia_ve",
        "query": "vao cong mat bao nhieu tien",
        "must_contain": ["vé", "đ"],
        "must_not_contain": [],
    },
    {
        "id": "L1_005", "level": "L1", "category": "gia_ve",
        "query": "Combo gia đình giá bao nhiêu?",
        "must_contain": ["combo", "đ"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L1 — FAQ: Giờ mở cửa
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L1_006", "level": "L1", "category": "gio_mo_cua",
        "query": "Mấy giờ mở cửa?",
        "must_contain": ["giờ", "mở"],
        "must_not_contain": [],
    },
    {
        "id": "L1_007", "level": "L1", "category": "gio_mo_cua",
        "query": "may gio dong cua",
        "must_contain": ["giờ"],
        "must_not_contain": [],
    },
    {
        "id": "L1_008", "level": "L1", "category": "gio_mo_cua",
        "query": "Công viên mở cửa lúc mấy giờ?",
        "must_contain": ["giờ"],
        "must_not_contain": [],
    },
    {
        "id": "L1_009", "level": "L1", "category": "gio_mo_cua",
        "query": "gio hoat dong cua suoi tien",
        "must_contain": ["giờ"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L1 — FAQ: Địa chỉ
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L1_010", "level": "L1", "category": "dia_chi",
        "query": "Suối Tiên ở đâu?",
        "must_contain": ["Xa Lộ Hà Nội", "Thủ Đức"],
        "must_not_contain": [],
    },
    {
        "id": "L1_011", "level": "L1", "category": "dia_chi",
        "query": "dia chi suoi tien o dau",
        "must_contain": ["Xa Lộ", "120"],
        "must_not_contain": [],
    },
    {
        "id": "L1_012", "level": "L1", "category": "dia_chi",
        "query": "Công viên nằm ở quận nào?",
        "must_contain": ["Thủ Đức"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L1 — FAQ: Liên hệ
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L1_013", "level": "L1", "category": "lien_he",
        "query": "Hotline Suối Tiên là bao nhiêu?",
        "must_contain": ["1900", "636"],
        "must_not_contain": [],
    },
    {
        "id": "L1_014", "level": "L1", "category": "lien_he",
        "query": "so dien thoai lien he",
        "must_contain": ["1900"],
        "must_not_contain": [],
    },
    {
        "id": "L1_015", "level": "L1", "category": "lien_he",
        "query": "Email liên hệ Suối Tiên?",
        "must_contain": ["suoitien", "@"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L1 — FAQ: Đường đi
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L1_016", "level": "L1", "category": "duong_di",
        "query": "Đi metro đến Suối Tiên được không?",
        "must_contain": ["metro"],
        "must_not_contain": [],
    },
    {
        "id": "L1_017", "level": "L1", "category": "duong_di",
        "query": "xe buyt den suoi tien tuyen nao",
        "must_contain": ["xe buýt", "tuyến"],
        "must_not_contain": [],
    },
    {
        "id": "L1_018", "level": "L1", "category": "duong_di",
        "query": "Bãi xe ở đâu?",
        "must_contain": ["xe"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L2 — Schema: Trò chơi cụ thể
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L2_001", "level": "L2", "category": "tro_choi",
        "query": "Go Kart ở khu nào?",
        "must_contain": ["Go Kart"],
        "must_not_contain": [],
    },
    {
        "id": "L2_002", "level": "L2", "category": "tro_choi",
        "query": "Infinity Slide là trò chơi gì?",
        "must_contain": ["Infinity Slide"],
        "must_not_contain": [],
    },
    {
        "id": "L2_003", "level": "L2", "category": "tro_choi",
        "query": "Trò chơi cảm giác mạnh có gì?",
        "must_contain": ["cảm giác mạnh"],
        "must_not_contain": [],
    },
    {
        "id": "L2_004", "level": "L2", "category": "tro_choi",
        "query": "Twin Race là gì?",
        "must_contain": ["Twin Race"],
        "must_not_contain": [],
    },
    {
        "id": "L2_005", "level": "L2", "category": "tro_choi",
        "query": "Khu vui chơi trẻ em có gì?",
        "must_contain": ["trẻ em"],
        "must_not_contain": [],
    },
    {
        "id": "L2_006", "level": "L2", "category": "tro_choi",
        "query": "Vương quốc cá sấu ở đâu?",
        "must_contain": ["cá sấu"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L2 — Schema: Nhà hàng
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L2_007", "level": "L2", "category": "nha_hang",
        "query": "Có nhà hàng nào trong công viên không?",
        "must_contain": ["nhà hàng"],
        "must_not_contain": [],
    },
    {
        "id": "L2_008", "level": "L2", "category": "nha_hang",
        "query": "Ăn trưa ở Suối Tiên ở đâu?",
        "must_contain": ["nhà hàng", "ăn"],
        "must_not_contain": [],
    },
    {
        "id": "L2_009", "level": "L2", "category": "nha_hang",
        "query": "nha hang Phu Dong co gi an",
        "must_contain": ["Phù Đổng"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L2 — Schema: Sự kiện
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L2_010", "level": "L2", "category": "su_kien",
        "query": "Hiện tại có sự kiện gì không?",
        "must_contain": ["sự kiện"],
        "must_not_contain": [],
    },
    {
        "id": "L2_011", "level": "L2", "category": "su_kien",
        "query": "Có khuyến mãi vé không?",
        "must_contain": ["khuyến mãi", "giảm", "ưu đãi"],
        "must_not_contain": [],
    },
    {
        "id": "L2_012", "level": "L2", "category": "su_kien",
        "query": "Lễ hội hè 2025 có gì?",
        "must_contain": ["lễ hội"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L2 — Schema: Teambuilding
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L2_013", "level": "L2", "category": "teambuilding",
        "query": "Teambuilding 50 người giá bao nhiêu?",
        "must_contain": ["người", "đ"],
        "must_not_contain": [],
    },
    {
        "id": "L2_014", "level": "L2", "category": "teambuilding",
        "query": "Có gói cắm trại qua đêm không?",
        "must_contain": ["cắm trại"],
        "must_not_contain": [],
    },
    {
        "id": "L2_015", "level": "L2", "category": "teambuilding",
        "query": "Tổ chức hội nghị công ty ở Suối Tiên được không?",
        "must_contain": ["hội nghị"],
        "must_not_contain": [],
    },
    {
        "id": "L2_016", "level": "L2", "category": "teambuilding",
        "query": "team building 100 nguoi co goi nao",
        "must_contain": ["gói", "100"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L2 — Schema: Farm
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L2_017", "level": "L2", "category": "farm",
        "query": "Suối Tiên Farm có gì?",
        "must_contain": ["farm", "vườn"],
        "must_not_contain": [],
    },
    {
        "id": "L2_018", "level": "L2", "category": "farm",
        "query": "Có hái trái cây không?",
        "must_contain": ["trái cây", "hái"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L3 — Complex: Multi-intent
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L3_001", "level": "L3", "category": "multi_intent",
        "query": "Giá vé bao nhiêu và mấy giờ mở cửa?",
        "must_contain": ["giờ"],
        "must_not_contain": [],
    },
    {
        "id": "L3_002", "level": "L3", "category": "multi_intent",
        "query": "2 người lớn 1 trẻ em tốn bao nhiêu và đi xe buýt được không?",
        "must_contain": ["lớn", "trẻ"],
        "must_not_contain": [],
    },
    {
        "id": "L3_003", "level": "L3", "category": "multi_intent",
        "query": "Có trò chơi gì và nhà hàng nào ngon không?",
        "must_contain": ["trò chơi", "ăn"],
        "must_not_contain": [],
    },
    {
        "id": "L3_004", "level": "L3", "category": "multi_intent",
        "query": "Teambuilding 30 người, giá bao nhiêu và cần đặt trước không?",
        "must_contain": ["người", "đặt"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L3 — Complex: So sánh
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L3_005", "level": "L3", "category": "so_sanh",
        "query": "Go Kart với Tàu Lượn cái nào mạnh hơn?",
        "must_contain": ["Go Kart", "Tàu Lượn"],
        "must_not_contain": [],
    },
    {
        "id": "L3_006", "level": "L3", "category": "so_sanh",
        "query": "Vé người lớn và vé học sinh khác nhau thế nào?",
        "must_contain": ["người lớn", "học sinh"],
        "must_not_contain": [],
    },
    {
        "id": "L3_007", "level": "L3", "category": "so_sanh",
        "query": "Khu khô và khu nước có gì khác nhau?",
        "must_contain": ["khu khô", "khu nước"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L3 — Complex: Tổng hợp
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L3_008", "level": "L3", "category": "tong_hop",
        "query": "Có bao nhiêu khu vui chơi trong công viên?",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "L3_009", "level": "L3", "category": "tong_hop",
        "query": "Liệt kê tất cả trò chơi cảm giác mạnh",
        "must_contain": ["Go Kart", "Infinity Slide"],
        "must_not_contain": [],
    },
    {
        "id": "L3_010", "level": "L3", "category": "tong_hop",
        "query": "Có những loại vé nào?",
        "must_contain": ["vé", "người lớn", "trẻ em"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L3 — Complex: Lịch trình / gợi ý
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L3_011", "level": "L3", "category": "lich_trinh",
        "query": "Gia đình 2 người lớn 2 trẻ em nên đi khu nào trước?",
        "must_contain": [],
        "must_not_contain": ["xin lỗi", "không tìm thấy"],
    },
    {
        "id": "L3_012", "level": "L3", "category": "lich_trinh",
        "query": "Đi Suối Tiên 1 ngày thì đủ không?",
        "must_contain": [],
        "must_not_contain": ["xin lỗi", "không tìm thấy"],
    },
    {
        "id": "L3_013", "level": "L3", "category": "lich_trinh",
        "query": "Trẻ 3 tuổi cao 95cm chơi được gì?",
        "must_contain": ["trẻ em", "khu"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L3 — Complex: Câu hỏi liên kết (conversation)
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L3_014", "level": "L3", "category": "lien_ket",
        "query": "Mua vé xong thì nên đi đâu trước?",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "L3_015", "level": "L3", "category": "lien_ket",
        "query": "Sau khi chơi Go Kart thì gần đó có gì?",
        "must_contain": [],
        "must_not_contain": ["xin lỗi", "không tìm thấy"],
    },

    # ══════════════════════════════════════════════════════════════════
    # L4 — Edge: Typo / không dấu
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L4_001", "level": "L4", "category": "typo",
        "query": "gia ve vao cong bao nhieu tien",
        "must_contain": ["vé", "đ"],
        "must_not_contain": [],
    },
    {
        "id": "L4_002", "level": "L4", "category": "typo",
        "query": "mk mun bit gia ve",
        "must_contain": ["vé"],
        "must_not_contain": [],
    },
    {
        "id": "L4_003", "level": "L4", "category": "typo",
        "query": "suoi tien o dau z",
        "must_contain": ["Xa Lộ", "Thủ Đức"],
        "must_not_contain": [],
    },
    {
        "id": "L4_004", "level": "L4", "category": "typo",
        "query": "co tro choi j k",
        "must_contain": ["trò chơi"],
        "must_not_contain": [],
    },
    {
        "id": "L4_005", "level": "L4", "category": "typo",
        "query": "nha hang ngon ko",
        "must_contain": ["nhà hàng"],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L4 — Edge: Ngôn ngữ khác
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L4_006", "level": "L4", "category": "multilang",
        "query": "How much is the entrance ticket?",
        "must_contain": ["ticket", "price", "đ", "000"],
        "must_not_contain": [],
    },
    {
        "id": "L4_007", "level": "L4", "category": "multilang",
        "query": "What time does the park open?",
        "must_contain": ["7", "giờ", "mở"],
        "must_not_contain": [],
    },
    {
        "id": "L4_008", "level": "L4", "category": "multilang",
        "query": "门票多少钱？",
        "must_contain": [],
        "must_not_contain": [],
    },

    # ══════════════════════════════════════════════════════════════════
    # L4 — Edge: OOS (ngoài phạm vi)
    # ══════════════════════════════════════════════════════════════════
    {
        "id": "L4_009", "level": "L4", "category": "oos",
        "query": "Từ Đà Nẵng đi Suối Tiên như thế nào?",
        "must_contain": ["Suối Tiên"],
        "must_not_contain": [],
        "check_fn_desc": "Không crash, có câu trả lời hợp lý",
    },
    {
        "id": "L4_010", "level": "L4", "category": "oos",
        "query": "Suối Tiên có nuôi gấu không?",
        "must_contain": [],
        "must_not_contain": [],
        "check_fn_desc": "Không crash, trả lời gracefully",
    },
    {
        "id": "L4_011", "level": "L4", "category": "oos",
        "query": "Thời tiết hôm nay thế nào?",
        "must_contain": ["thời tiết"],
        "must_not_contain": [],
    },
    {
        "id": "L4_012", "level": "L4", "category": "oos",
        "query": "Bạn là ai?",
        "must_contain": ["Tiên", "em"],
        "must_not_contain": [],
    },
]


# ── Evaluator ──────────────────────────────────────────────────────────────────

def evaluate_case(case: dict, verbose: bool = False) -> dict:
    """Chạy 1 test case, trả về kết quả."""
    t0 = time.perf_counter()
    try:
        result = chat(case["query"], use_faq_fast_path=True)
        answer = result["answer"]
        source = result["source"]
        tools  = result.get("tools", [])
        latency = (time.perf_counter() - t0) * 1000
        error  = None
    except Exception as e:
        answer  = ""
        source  = "error"
        tools   = []
        latency = (time.perf_counter() - t0) * 1000
        error   = str(e)

    # Check must_contain
    must_contain     = case.get("must_contain", [])
    must_not_contain = case.get("must_not_contain", [])

    ans_lower = answer.lower()
    # must_contain logic: ANY 1 keyword có = pass (không phải ALL)
    contain_hits = [kw for kw in must_contain
                    if kw.lower() in ans_lower]
    contain_miss = [kw for kw in must_contain
                    if kw.lower() not in ans_lower]
    forbidden_hits = [kw for kw in must_not_contain
                      if kw.lower() in ans_lower]

    # Pass nếu: không có must_contain OR ít nhất 1 keyword có mặt
    contain_ok = (len(must_contain) == 0) or (len(contain_hits) >= 1)

    passed = (
        contain_ok and
        len(forbidden_hits) == 0 and
        error is None and
        len(answer) > 10
    )

    out = {
        "id":             case["id"],
        "level":          case["level"],
        "category":       case["category"],
        "query":          case["query"],
        "passed":         passed,
        "answer":         answer[:300],
        "source":         source,
        "tools":          tools,
        "latency_ms":     round(latency),
        "contain_miss":   contain_miss,
        "forbidden_hits": forbidden_hits,
        "error":          error,
    }

    if verbose:
        status = "✅" if passed else "❌"
        print(f"{status} [{case['id']}] {case['query'][:50]}")
        if not passed:
            if contain_miss and not contain_hits:
                print(f"   MISS keywords: {contain_miss}")
            if forbidden_hits:
                print(f"   FORBIDDEN found: {forbidden_hits}")
            if error:
                print(f"   ERROR: {error}")
            print(f"   Answer: {answer[:150]}")
        print(f"   source={source} | tools={tools} | {latency:.0f}ms")

    return out


def run_eval(
    cases: list = None,
    verbose: bool = True,
    output_file: str = "eval_results.json",
    level_filter: str = None,   # "L1", "L2", "L3", "L4" or None = all
) -> dict:
    """Chạy toàn bộ eval set."""
    cases = cases or EVAL_SET
    if level_filter:
        cases = [c for c in cases if c["level"] == level_filter]

    print(f"\n{'='*60}")
    print(f"SUỐI TIÊN BOT EVAL — {len(cases)} cases"
          + (f" [level={level_filter}]" if level_filter else ""))
    print(f"{'='*60}\n")

    results = []
    t_total = time.perf_counter()

    for case in cases:
        r = evaluate_case(case, verbose=verbose)
        results.append(r)

    total_time = time.perf_counter() - t_total

    # ── Summary ────────────────────────────────────────────────────────────────
    levels = ["L1", "L2", "L3", "L4"]
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    overall_pass = sum(1 for r in results if r["passed"])
    overall_total = len(results)
    print(f"\nOverall: {overall_pass}/{overall_total} = {overall_pass/overall_total*100:.1f}%")
    print(f"Total time: {total_time:.1f}s | Avg latency: {sum(r['latency_ms'] for r in results)/len(results):.0f}ms\n")

    level_stats = {}
    for lvl in levels:
        lvl_results = [r for r in results if r["level"] == lvl]
        if not lvl_results:
            continue
        passed = sum(1 for r in lvl_results if r["passed"])
        total  = len(lvl_results)
        avg_ms = sum(r["latency_ms"] for r in lvl_results) / total
        target = {"L1": 95, "L2": 85, "L3": 75, "L4": 60}[lvl]
        pct    = passed / total * 100
        status = "✅" if pct >= target else "❌"
        print(f"{status} {lvl}: {passed}/{total} = {pct:.1f}% (target {target}%) | avg {avg_ms:.0f}ms")
        level_stats[lvl] = {"passed": passed, "total": total, "pct": pct, "avg_ms": avg_ms}

    # Category breakdown
    print(f"\n--- Category breakdown ---")
    cats = {}
    for r in results:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"pass": 0, "total": 0}
        cats[cat]["total"] += 1
        if r["passed"]:
            cats[cat]["pass"] += 1
    for cat, s in sorted(cats.items()):
        pct = s["pass"] / s["total"] * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"  {cat:20s} {bar} {s['pass']}/{s['total']} {pct:.0f}%")

    # Failed cases
    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n--- Failed cases ({len(failed)}) ---")
        for r in failed:
            print(f"  ❌ [{r['id']}] {r['query'][:60]}")
            if r["contain_miss"]:
                print(f"     miss: {r['contain_miss']}")
            if r["error"]:
                print(f"     error: {r['error'][:80]}")

    # Source breakdown
    sources = {}
    for r in results:
        sources[r["source"]] = sources.get(r["source"], 0) + 1
    print(f"\n--- Source distribution ---")
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {src:12s}: {cnt} ({cnt/overall_total*100:.0f}%)")

    # Save results
    output = {
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
        "total":         overall_total,
        "passed":        overall_pass,
        "pct":           round(overall_pass / overall_total * 100, 1),
        "level_stats":   level_stats,
        "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / len(results)),
        "results":       results,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved → {output_file}")
    print(f"{'='*60}\n")

    return output


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    _eval_file = os.environ.get("EVAL_FILE", "")
    if _eval_file and os.path.exists(_eval_file):
        with open(_eval_file, encoding="utf-8") as _f:
            EVAL_SET = json.load(_f)
        print(f"Loaded {len(EVAL_SET)} cases from {_eval_file}")

    parser = argparse.ArgumentParser()
    parser.add_argument("--level", "-l", default=None,
                        help="Filter level: L1, L2, L3, L4")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress per-case output")
    parser.add_argument("--output", "-o", default="eval_results.json")
    args = parser.parse_args()

    run_eval(
        verbose=not args.quiet,
        output_file=args.output,
        level_filter=args.level,
    )

