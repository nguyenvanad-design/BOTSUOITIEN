"""
tool_executor.py — Bridge giữa Planner tool calls và retrieval modules.
Nhận list tool calls từ planner → gọi đúng retrieval → trả raw data cho responder.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional

# ── Lazy imports để tránh circular / startup cost ──────────────────────────────
_retrieval_orchestrator = None
_weather_service        = None
_map_service            = None
_faq_engine             = None


def _get_orchestrator():
    global _retrieval_orchestrator
    if _retrieval_orchestrator is None:
        from retrieval_orchestrator import retrieve, build_context
        _retrieval_orchestrator = (retrieve, build_context)
    return _retrieval_orchestrator


def _get_weather():
    global _weather_service
    if _weather_service is None:
        try:
            from weather_service import get_weather
            _weather_service = get_weather
        except ImportError:
            _weather_service = lambda: {"error": "weather_service not available"}
    return _weather_service


def _get_map():
    global _map_service
    if _map_service is None:
        try:
            from map_service import get_directions_text
            _map_service = get_directions_text
        except ImportError:
            _map_service = lambda lang="vi": None
    return _map_service


def _get_faq():
    global _faq_engine
    if _faq_engine is None:
        try:
            from faq_engine import faq_match
            _faq_engine = faq_match
        except ImportError:
            _faq_engine = lambda q, lang="vi": None
    return _faq_engine


# ── Intent override per tool (fine-tune retrieval) ─────────────────────────────
_INTENT_OVERRIDE = {
    "search_tickets":      "hoi_gia_ve",
    "search_attractions":  "hoi_tro_choi",
    "search_restaurants":  "hoi_nha_hang",
    "search_events":       "hoi_su_kien",
    "search_teambuilding": "hoi_teambuilding",
    "get_park_info":       "hoi_gio_mo_cua",
    "get_directions":      "hoi_duong_di",
    "get_weather":         "hoi_chung",
}

# ── Category filter per tool ───────────────────────────────────────────────────
_CATEGORY_MAP = {
    "search_tickets":      "tickets",
    "search_attractions":  "attractions",
    "search_restaurants":  "restaurant",
    "search_events":       "events",
    "search_teambuilding": "teambuilding",
    "get_park_info":       None,
    "get_directions":      None,
    "get_weather":         None,
}


class _ToolCancelled(Exception):
    """Tool bị huỷ vì một tool khác trong cùng lượt đã timeout."""


def execute_tool(tool_call: dict, lang: str = "vi", cancel_flag=None) -> dict:
    """
    Thực thi 1 tool call từ planner.

    Args:
        tool_call: {"tool": str, "input": dict, "intent": str, "strategy": list}
        lang: ngôn ngữ detect được từ query

    Returns:
        {
            "tool": str,
            "source": str,          # faq | schema | hybrid | weather | map | fallback
            "context": str,         # text để feed vào LLM2 responder
            "raw": dict,            # raw retrieval output (debug)
            "intent": str,
        }
    """
    tool_name = tool_call["tool"]
    tool_input = tool_call.get("input", {})
    query = tool_input.get("query", "")
    intent = tool_call.get("intent", _INTENT_OVERRIDE.get(tool_name, "unknown"))
    strategy = tool_call.get("strategy", ["faq", "bm25", "vector"])

    def _abort_if_cancelled(moc: str):
        """Thoát sớm khi lượt chat đã bỏ cuộc — kết quả lúc này không ai dùng."""
        if cancel_flag is not None and cancel_flag.is_set():
            raise _ToolCancelled(f"{tool_name} huỷ tại {moc}")

    _abort_if_cancelled("bắt đầu")

    # ── Special tools: weather ─────────────────────────────────────────────────
    if tool_name == "get_weather":
        get_weather = _get_weather()
        try:
            weather_data = get_weather(lang)
        except TypeError:
            weather_data = get_weather()
        except Exception:
            weather_data = None
        try:
            if isinstance(weather_data, dict) and "error" not in weather_data:
                ctx = _format_weather(weather_data, lang)
            else:
                ctx = ""
        except Exception:
            ctx = ""
        return {"tool": tool_name, "source": "weather", "context": ctx,
                "raw": {}, "intent": intent}

    # ── Special tools: directions ──────────────────────────────────────────────
    if tool_name == "get_directions":
        # FAQ trước (thường có địa chỉ + hướng dẫn)
        faq_match = _get_faq()
        faq_result = faq_match(query, lang=lang)
        if faq_result:
            return {"tool": tool_name, "source": "faq",
                    "context": faq_result.get("answer", ""),
                    "raw": faq_result, "intent": intent}

        # Map service
        get_directions_text = _get_map()
        try:
            map_ctx = get_directions_text(lang=lang)
        except Exception:
            map_ctx = None

        # Hybrid: map text + retrieval
        retrieve, build_context = _get_orchestrator()
        out = retrieve(query, intent=intent, strategy=["faq", "schema", "vector"])
        ctx_parts = []
        if map_ctx:
            ctx_parts.append(map_ctx)
        retrieval_ctx = build_context(out)
        if retrieval_ctx:
            ctx_parts.append(retrieval_ctx)

        return {"tool": tool_name, "source": "hybrid",
                "context": "\n\n".join(ctx_parts),
                "raw": out, "intent": intent}

    # ── Default: retrieval pipeline ────────────────────────────────────────────
    retrieve, build_context = _get_orchestrator()

    # Inject entities từ tool input vào retrieval
    entities = {}
    if "group_type" in tool_input:
        entities["age_group"] = tool_input["group_type"]
    if "group_size" in tool_input:
        entities["group_size"] = tool_input["group_size"]
    if "category" in tool_input:
        entities["category"] = tool_input["category"]
    if "from_location" in tool_input:
        entities["location"] = tool_input["from_location"]
    if "height_cm" in tool_input:
        entities["height_cm"] = tool_input["height_cm"]
    if "age" in tool_input:
        entities["age"] = tool_input["age"]
    if "get_all" in tool_input:
        entities["get_all"] = tool_input["get_all"]

    # Suy phạm vi/độ mạo hiểm từ CÂU GỐC của khách — planner viết lại query cho
    # tool nên hay đánh rơi "liệt kê tất cả" / "cảm giác mạnh".
    user_query = tool_call.get("user_query") or query
    if user_query:
        try:
            from schema_search import _infer_get_all, _infer_thrill
            if not entities.get("get_all") and _infer_get_all(user_query):
                entities["get_all"] = True
            if not entities.get("thrill_level"):
                _t = _infer_thrill(user_query)
                if _t:
                    entities["thrill_level"] = _t
        except Exception:
            pass   # suy đoán là bonus — hỏng thì vẫn chạy như cũ

    # Mốc chặn ngay trước bước nặng nhất (vector search + đọc index)
    _abort_if_cancelled("trước retrieval")

    out = retrieve(
        query=query,
        intent=intent,
        entities=entities,
        strategy=strategy,
        use_vector=True,
    )

    _abort_if_cancelled("sau retrieval")

    # FAQ fast path — context là string trực tiếp
    if out.get("source") == "faq":
        return {"tool": tool_name, "source": "faq",
                "context": out.get("answer", ""),
                "raw": out, "intent": intent}

    ctx = build_context(out)
    return {
        "tool":    tool_name,
        "source":  out.get("source", "fallback"),
        "context": ctx,
        "raw":     out,
        "intent":  intent,
    }


def execute_all(tool_calls: list[dict], lang: str = "vi") -> list[dict]:
    """
    Thực thi tất cả tool calls từ planner.
    Trả về list results theo thứ tự tương ứng.
    """
    results = []
    for call in tool_calls:
        result = execute_tool(call, lang=lang)
        results.append(result)
    return results


def merge_contexts(tool_results: list[dict]) -> str:
    """
    Gộp context từ nhiều tool results thành 1 string cho LLM2.
    FAQ results được ưu tiên để lên đầu.
    """
    faq_parts    = []
    other_parts  = []

    for r in tool_results:
        ctx = r.get("context", "").strip()
        if not ctx:
            continue
        if r.get("source") == "faq":
            faq_parts.append(ctx)
        else:
            # Label theo tool để LLM2 dễ hiểu
            label = _tool_label(r["tool"])
            other_parts.append(f"=== {label} ===\n{ctx}")

    all_parts = faq_parts + other_parts
    return "\n\n".join(all_parts)


def _tool_label(tool_name: str) -> str:
    labels = {
        "search_tickets":      "THÔNG TIN VÉ",
        "search_attractions":  "ĐIỂM THAM QUAN & TRÒ CHƠI",
        "search_restaurants":  "NHÀ HÀNG & ẨM THỰC",
        "search_events":       "SỰ KIỆN & ƯU ĐÃI",
        "search_teambuilding": "TEAMBUILDING & ĐẶT ĐOÀN",
        "get_park_info":       "THÔNG TIN CÔNG VIÊN",
        "get_directions":      "ĐƯỜNG ĐI & VỊ TRÍ",
        "get_weather":         "THỜI TIẾT",
    }
    return labels.get(tool_name, tool_name.upper())


def _format_weather(data: dict, lang: str = "vi") -> str:
    """Format weather data thành text."""
    temp = data.get("temp", "?")
    desc = data.get("description", "")
    humidity = data.get("humidity", "?")
    feels_like = data.get("feels_like", "?")

    if lang == "vi":
        return (f"Thời tiết hiện tại tại Suối Tiên: {desc}, "
                f"nhiệt độ {temp}°C (cảm giác như {feels_like}°C), "
                f"độ ẩm {humidity}%.")
    elif lang == "en":
        return (f"Current weather at Suoi Tien: {desc}, "
                f"temperature {temp}°C (feels like {feels_like}°C), "
                f"humidity {humidity}%.")
    else:
        return f"{desc}, {temp}°C, {humidity}%"


# ── CLI test ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from pathlib import Path

    os.environ.setdefault("SUOITIEN_BASE", str(Path(__file__).parent))
    os.environ.setdefault("SUOITIEN_DATA",
        str(Path(__file__).parent / "data" / "suoitien_data_v2.json"))
    os.environ.setdefault("SUOITIEN_CLEAN",
        str(Path(__file__).parent / "data" / "suoitien_clean_v4.json"))

    test_calls = [
        {
            "tool":     "search_tickets",
            "input":    {"query": "Giá vé bao nhiêu?", "group_type": "family"},
            "intent":   "hoi_gia_ve",
            "strategy": ["faq", "schema"],
        },
        {
            "tool":     "search_attractions",
            "input":    {"query": "Trò chơi cảm giác mạnh có gì?"},
            "intent":   "hoi_tro_choi",
            "strategy": ["schema", "bm25", "vector"],
        },
        {
            "tool":     "get_park_info",
            "input":    {"query": "Mấy giờ đóng cửa?", "info_type": "hours"},
            "intent":   "hoi_gio_mo_cua",
            "strategy": ["faq"],
        },
    ]

    results = execute_all(test_calls, lang="vi")
    merged  = merge_contexts(results)

    for r in results:
        print(f"Tool: {r['tool']} | source={r['source']}")
        print(f"  ctx: {r['context'][:150].replace(chr(10),' ')}")
        print()

    print("=== MERGED CONTEXT ===")
    print(merged[:500])
