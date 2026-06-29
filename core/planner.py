"""
planner.py — LLM1: Planner dùng tool calling để hiểu intent + quyết định retrieval
Thay hoàn toàn rule-based intent_extractor.
LLM tự hiểu mọi cách diễn đạt → gọi đúng tool → không bao giờ "ngu".
"""

import time
import logging

import llm_client
from prompts import PLANNER_SYSTEM as _PLANNER_SYSTEM

logger = logging.getLogger("suoitien.planner")

# Simple TTL cache — câu hỏi lặp lại không gọi LLM lần 2
import hashlib, threading
_plan_cache: dict = {}
_plan_cache_lock = threading.Lock()
_PLAN_CACHE_TTL = 300
_PLAN_CACHE_MAX = 200

def _cache_key(query: str, history: list) -> str:
    # Chỉ cache theo query — tool selection không đổi dù có history hay không.
    # Follow-up ("nó ở đâu") tự nhiên có query khác → cache key khác → không bị nhầm.
    return hashlib.md5(query.strip().lower().encode()).hexdigest()

def _cache_get(key: str):
    with _plan_cache_lock:
        e = _plan_cache.get(key)
        if e and (time.time() - e["ts"]) < _PLAN_CACHE_TTL:
            return e["value"]
        if e:
            del _plan_cache[key]
    return None

def _cache_set(key: str, value):
    with _plan_cache_lock:
        if len(_plan_cache) >= _PLAN_CACHE_MAX:
            oldest = min(_plan_cache, key=lambda k: _plan_cache[k]["ts"])
            del _plan_cache[oldest]
        _plan_cache[key] = {"value": value, "ts": time.time()}

# ── LLM qua adapter 1 cửa (core/llm_client.py) ────────────────────────────────
# Provider (grok|gemini|anthropic) + model chọn bằng env trong .env — KHÔNG còn
# client/SDK riêng ở đây. Giữ 2 biến dưới chỉ để log/tương thích.
PROVIDER   = llm_client.get_provider() or ""
MODEL_NAME = llm_client.resolve_model("planner") if PROVIDER else ""

# ── Tool definitions ────────────────────────────────────────────────────────────
# Mỗi tool = 1 loại câu hỏi. LLM đọc description → tự chọn đúng tool.
# Không cần keyword, không cần rule — LLM hiểu ngữ nghĩa tự nhiên.

PLANNER_TOOLS = [
    {
        "name": "search_tickets",
        "description": (
            "Tìm thông tin giá vé vào cổng Suối Tiên. Dùng khi khách hỏi về: "
            "giá vé, vé bao nhiêu tiền, phí vào cổng, vé người lớn, vé trẻ em, "
            "combo gia đình, vé nhóm, mua vé ở đâu, đặt vé online, vé có bao gồm gì. "
            "Ví dụ: 'vào công viên mất tiền không', '2 người lớn 1 trẻ bao nhiêu', "
            "'giá cho học sinh', 'vé có kèm trò chơi không'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                },
                "group_type": {
                    "type": "string",
                    "enum": ["adult", "child", "student", "family", "group", "all"],
                    "description": "Loại nhóm khách nếu đề cập, mặc định 'all'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_attractions",
        "description": (
            "Tìm thông tin điểm tham quan, trò chơi, khu vui chơi trong Suối Tiên. "
            "Dùng khi khách hỏi về: trò chơi cảm giác mạnh, khu nào vui, "
            "Go Kart, tàu lượn, Infinity Slide, Twin Race, xe tăng, "
            "khu trẻ em, khu văn hóa, đình chùa, nông trại, thú, vườn thú, "
            "có gì chơi, nên đi đâu trước, mấy khu tham quan. "
            "Ví dụ: 'trò chơi nào mạnh nhất', 'khu nào phù hợp trẻ nhỏ', "
            "'Go Kart ở đâu', 'có mấy khu vui chơi'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                },
                "category": {
                    "type": "string",
                    "enum": ["rides", "culture", "farm", "kids", "all"],
                    "description": "Loại điểm tham quan nếu rõ"
                },
                "height_cm": {
                    "type": "integer",
                    "description": "Chiều cao của trẻ em tính bằng cm nếu đề cập. VD: '1m2' → 120, '95cm' → 95"
                },
                "age": {
                    "type": "integer",
                    "description": "Tuổi của trẻ em nếu đề cập"
                },
                "get_all": {
                    "type": "boolean",
                    "description": "True khi câu hỏi yêu cầu liệt kê tất cả / có bao nhiêu / kể hết"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_restaurants",
        "description": (
            "Tìm thông tin nhà hàng, ẩm thực trong Suối Tiên. "
            "Dùng khi khách hỏi về: ăn uống, nhà hàng nào ngon, món đặc trưng, "
            "buffet, lẩu, hải sản, đặt bàn, ăn trưa ở đâu, giá ăn, "
            "Cung Đình Tửu, Thiên Hương, nhà hàng nổi. "
            "Ví dụ: 'ăn trưa ở đây có gì', 'nhà hàng nào có buffet', "
            "'đặt bàn được không', 'ăn hải sản ở đâu ngon'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_events",
        "description": (
            "Tìm thông tin sự kiện, lễ hội, chương trình biểu diễn, ưu đãi tại Suối Tiên. "
            "Dùng khi khách hỏi về: sự kiện sắp tới, lễ hội hè, show diễn, "
            "khuyến mãi, giảm giá, combo ưu đãi, voucher, sự kiện cuối tuần. "
            "Ví dụ: 'hè này có gì đặc biệt', 'sự kiện tháng 6', "
            "'có khuyến mãi không', 'cuối tuần có show gì'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_teambuilding",
        "description": (
            "Tìm thông tin gói teambuilding, tổ chức đoàn, hội nghị, cắm trại tại Suối Tiên. "
            "Dùng khi khách hỏi về: teambuilding, đặt tour đoàn, tổ chức sự kiện công ty, "
            "cắm trại, hội trại, giá đoàn, gói nhóm, bao nhiêu người. "
            "Ví dụ: 'teambuilding 50 người giá bao nhiêu', 'có gói đoàn không', "
            "'tổ chức sinh nhật công ty', 'cắm trại qua đêm được không'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                },
                "group_size": {
                    "type": "integer",
                    "description": "Số người trong đoàn nếu đề cập"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_park_info",
        "description": (
            "Lấy thông tin chung về công viên: địa chỉ, giờ mở cửa, hotline, "
            "chính sách, nội quy, hoàn vé, bãi giữ xe. "
            "Dùng khi khách hỏi: ở đâu, mấy giờ mở, mấy giờ đóng, "
            "số điện thoại, liên hệ, website, chính sách hoàn vé, "
            "được mang đồ ăn vào không, quy định ăn mặc. "
            "Ví dụ: 'Suối Tiên ở quận mấy', 'đóng cửa lúc mấy giờ', "
            "'hotline bao nhiêu', 'được mang pet vào không'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                },
                "info_type": {
                    "type": "string",
                    "enum": ["address", "hours", "contact", "policy", "parking", "general"],
                    "description": "Loại thông tin cần"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_directions",
        "description": (
            "Cung cấp hướng dẫn đường đến Suối Tiên hoặc chỉ đường GPS. "
            "Dùng khi khách hỏi: đi như thế nào, xe buýt số mấy, metro, "
            "từ quận X đi bao lâu, có xe đưa đón không, bãi giữ xe ở đâu, "
            "grab đến được không, đường đi từ trung tâm. "
            "Ví dụ: 'từ quận 1 đi bao xa', 'có xe buýt không', "
            "'đi metro được không', 'chỗ để xe ở đâu'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                },
                "from_location": {
                    "type": "string",
                    "description": "Điểm xuất phát nếu khách đề cập"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_weather",
        "description": (
            "Lấy thông tin thời tiết tại Suối Tiên. "
            "Dùng khi khách hỏi: thời tiết hôm nay, trời có mưa không, "
            "nên đi ngày nào, thời tiết cuối tuần, nhiệt độ, "
            "có nên mang áo mưa không. "
            "Ví dụ: 'hôm nay trời có nắng không', 'thứ 7 thời tiết thế nào', "
            "'nên đi hôm nào đẹp trời'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi gốc của khách"
                }
            },
            "required": ["query"]
        }
    }
]

# ── Map tool name → retrieval config ───────────────────────────────────────────
TOOL_RETRIEVAL_MAP = {
    "search_tickets":      {"intent": "hoi_gia_ve",      "strategy": ["faq", "schema"]},
    "search_attractions":  {"intent": "hoi_tro_choi",    "strategy": ["schema", "bm25", "vector"]},
    "search_restaurants":  {"intent": "hoi_nha_hang",    "strategy": ["schema", "bm25", "vector"]},
    "search_events":       {"intent": "hoi_su_kien",     "strategy": ["schema", "bm25", "vector"]},
    "search_teambuilding": {"intent": "hoi_teambuilding","strategy": ["faq", "schema", "bm25", "vector"]},
    "get_park_info":       {"intent": "hoi_gio_mo_cua",  "strategy": ["faq", "schema"]},
    "get_directions":      {"intent": "hoi_duong_di",    "strategy": ["faq", "schema", "vector"]},
    "get_weather":         {"intent": "hoi_chung",       "strategy": ["faq"]},
}


def plan(query: str, history: list = None, retries: int = 2) -> list[dict]:
    """
    LLM1 Planner: nhận query + history → trả về list tool calls.
    Mỗi item: {"tool": str, "input": dict, "intent": str, "strategy": list}
    history: [{role, content}, ...] — conversation context
    """
    history = history or []
    ck = _cache_key(query, history)
    cached = _cache_get(ck)
    if cached:
        logger.debug("Planner cache hit: %s", query[:40])
        return cached

    if not llm_client.available():
        logger.warning("LLM provider unavailable — using fallback plan")
        return _fallback_plan(query)

    # Build messages với history (tối đa 6 turns gần nhất để tránh token bloat)
    recent_history = history[-6:] if len(history) > 6 else history
    messages = list(recent_history) + [{"role": "user", "content": query}]

    for attempt in range(retries + 1):
        try:
            raw_calls = llm_client.call_tools(
                system=_PLANNER_SYSTEM,
                messages=messages,
                tools=PLANNER_TOOLS,
                max_tokens=300,
                role="planner",
            )
            tool_calls = []
            for c in raw_calls:
                retrieval_cfg = TOOL_RETRIEVAL_MAP.get(c["name"], {
                    "intent": "unknown", "strategy": ["faq", "bm25", "vector"]
                })
                tool_calls.append({
                    "tool":     c["name"],
                    "input":    c["input"],
                    "intent":   retrieval_cfg["intent"],
                    "strategy": retrieval_cfg["strategy"],
                })

            if tool_calls:
                _cache_set(ck, tool_calls)
                return tool_calls

        except Exception:
            logger.exception("Planner error (attempt %d/%d)", attempt + 1, retries + 1)
            if attempt < retries:
                time.sleep(0.3)

    # Fallback nếu LLM fail
    logger.warning("Planner failed after %d attempts — using fallback plan", retries + 1)
    return _fallback_plan(query)


def _fallback_plan(query: str) -> list[dict]:
    """Fallback đơn giản khi LLM không gọi được."""
    return [{
        "tool":     "get_park_info",
        "input":    {"query": query, "info_type": "general"},
        "intent":   "hoi_chung",
        "strategy": ["faq", "bm25", "vector"],
    }]


# ── CLI test ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "Giá vé vào cổng bao nhiêu?",
        "Vào công viên mất tiền không?",
        "Go Kart ở khu nào?",
        "Có nhà hàng buffet không?",
        "Mấy giờ đóng cửa?",
        "Teambuilding 50 người giá bao nhiêu?",
        "Hè này có sự kiện gì không, và thời tiết thế nào?",
        "2 người lớn 1 trẻ em tốn bao nhiêu và đi xe buýt được không?",
        "mk mún bít gia ve va di nhu nao",
    ]

    print(f"=== PLANNER TEST (provider={PROVIDER or 'NONE'}, model={MODEL_NAME or '-'}) ===\n")
    for q in tests:
        calls = plan(q)
        print(f"Q: {q}")
        for c in calls:
            print(f"   → {c['tool']} | intent={c['intent']} | strategy={c['strategy']}")
            if c["input"].get("group_size"):
                print(f"     group_size={c['input']['group_size']}")
        print()
