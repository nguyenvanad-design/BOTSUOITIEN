"""
chat_pipeline.py — Wire Planner → Tool Executor → Responder.
v3:
- Parallel tool execution GIỮ ĐÚNG THỨ TỰ tool calls (fix: as_completed
  trả theo thứ tự hoàn thành → câu so sánh "A vs B" bị đảo context)
- Mỗi tool có timeout + try/except riêng — 1 tool fail/treo không sập request
- FAQ fast path CHỈ chạy khi chưa có history — follow-up
  ("nó ở đâu?", "vậy giá thì sao?") cần Planner đọc ngữ cảnh
- Logging
"""

import os
import time
import random
import logging
import threading
import concurrent.futures
from typing import Generator

# Tỉ lệ chạy học nền (critic/self-learning) — mỗi tin nhắn LLM tạo thêm ~1-3 Grok
# call nền → dưới tải nặng dễ bị rate-limit. Production nên đặt thấp (vd 0.1).
_LEARN_SAMPLE_RATE = float(os.getenv("SUOITIEN_LEARN_SAMPLE_RATE", "1.0"))

from language_detector import detect_lang
from planner       import plan
from tool_executor import execute_tool, merge_contexts
from responder     import respond, respond_stream

try:
    from guardrail import check_input, check_output, get_block_message
    _HAS_GUARDRAIL = True
except ImportError:
    _HAS_GUARDRAIL = False

try:
    from analytics import track as _track_analytics
    _HAS_ANALYTICS = True
except ImportError:
    _HAS_ANALYTICS = False

try:
    from long_term_memory import learn_from_conversation, build_ltm_context
    _HAS_LTM = True
except ImportError:
    _HAS_LTM = False

try:
    from memory_layer import update_memory, inject_memory_to_query, clear_memory as clear_mem
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

try:
    from self_learning import evaluate_and_learn, get_fewshot_examples
    from response_critic import critique_and_learn, get_golden_examples, generate_prompt_patch
    _HAS_LEARNING = True
    _HAS_CRITIC   = True
except ImportError:
    try:
        from self_learning import evaluate_and_learn, get_fewshot_examples
        _HAS_LEARNING = True
        _HAS_CRITIC   = False
    except ImportError:
        _HAS_LEARNING = False
        _HAS_CRITIC   = False

logger = logging.getLogger("suoitien.pipeline")

try:
    from faq_engine import faq_match
    _HAS_FAQ = True
except ImportError:
    _HAS_FAQ = False
    logger.warning("faq_engine not available — fast path disabled")

# Thread pool cho parallel tool execution
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# Timeout cho MỖI tool (giây)
_TOOL_TIMEOUT = 8.0


def _error_result(tool_call: dict) -> dict:
    """Result rỗng khi 1 tool fail — pipeline vẫn chạy tiếp với tool khác."""
    return {
        "tool":    tool_call.get("tool", "unknown"),
        "source":  "error",
        "context": "",
        "raw":     {},
        "intent":  tool_call.get("intent", "unknown"),
    }


def _execute_parallel(tool_calls: list, lang: str) -> list:
    """
    Execute nhiều tool calls song song, TRẢ KẾT QUẢ ĐÚNG THỨ TỰ tool_calls.
    1 tool lỗi/timeout → result rỗng cho tool đó, các tool khác vẫn dùng được.
    """
    if len(tool_calls) == 1:
        try:
            return [execute_tool(tool_calls[0], lang=lang)]
        except Exception:
            logger.exception("Tool %s failed", tool_calls[0].get("tool"))
            return [_error_result(tool_calls[0])]

    # Cờ huỷ dùng chung: `future.cancel()` KHÔNG dừng được future ĐANG CHẠY —
    # nó chỉ huỷ được task còn nằm trong hàng đợi. Trước đây tool timeout vẫn
    # chạy tiếp tới cùng, giữ luôn worker của pool; nhiều câu chậm liên tiếp là
    # pool cạn worker và mọi request sau đều phải xếp hàng.
    # Giờ tool tự kiểm tra cờ tại các mốc và thoát sớm.
    cancel_flag = threading.Event()
    futures = [
        _EXECUTOR.submit(execute_tool, call, lang, cancel_flag)
        for call in tool_calls
    ]

    results = []
    deadline = time.monotonic() + _TOOL_TIMEOUT
    for call, future in zip(tool_calls, futures):
        remaining = max(0.1, deadline - time.monotonic())
        try:
            results.append(future.result(timeout=remaining))
        except concurrent.futures.TimeoutError:
            logger.warning("Tool %s timed out after %.1fs", call.get("tool"), _TOOL_TIMEOUT)
            cancel_flag.set()     # báo cho MỌI tool còn chạy dừng lại
            future.cancel()       # chỉ ăn nếu task chưa được nhấc khỏi hàng đợi
            results.append(_error_result(call))
        except Exception:
            logger.exception("Tool %s failed", call.get("tool"))
            results.append(_error_result(call))
    return results


def _try_faq(query: str, lang: str, history: list, enabled: bool):
    """
    FAQ fast path — chỉ khi:
    - được bật và faq_engine import được
    - CHƯA có history (câu mở đầu). Follow-up như "nó ở đâu?" cần
      Planner đọc ngữ cảnh; FAQ regex sẽ trả lời sai (vd: địa chỉ công viên
      thay vì vị trí Go Kart đang nói tới).
    """
    if not (enabled and _HAS_FAQ) or history:
        return None
    try:
        return faq_match(query, lang=lang)
    except Exception:
        logger.exception("faq_match error — falling through to planner")
        return None


def chat(
    query: str,
    history: list = None,
    use_faq_fast_path: bool = True,
    session_id: str = "",
    **kwargs,
) -> dict:
    """
    Blocking pipeline.
    Returns: {answer, source, lang, tools, latency}
    """
    t0 = time.perf_counter()
    history = history or []
    lang = detect_lang(query)
    kwargs["session_id"] = session_id

    # Step 0: Guardrail — kiểm tra input trước pipeline
    if _HAS_GUARDRAIL:
        gr = check_input(query, lang)
        if not gr.passed:
            return {
                "answer":  get_block_message(gr.reason, lang),
                "source":  "guardrail",
                "lang":    lang,
                "tools":   [],
                "latency": (time.perf_counter() - t0) * 1000,
            }
        if gr.cleaned_query:
            query = gr.cleaned_query  # PII redacted

    # Step 0.5: Memory layer — extract entities + inject context
    session_id = kwargs.get("session_id", "")
    if _HAS_MEMORY and session_id:
        update_memory(session_id, query)
        query = inject_memory_to_query(query, session_id)

    # Step 1: FAQ fast path (chỉ câu mở đầu)
    faq_result = _try_faq(query, lang, history, use_faq_fast_path)
    if faq_result:
        return {
            "answer":  faq_result.get("answer", ""),
            "source":  "faq",
            "lang":    lang,
            "tools":   [],
            # rule ("gia_ve", "gio_mo_cua"...) — API layer dùng làm intent để
            # đính đúng link, thay vì rơi về link trang chủ chung chung.
            "rule":    faq_result.get("rule", ""),
            "latency": (time.perf_counter() - t0) * 1000,
        }

    # Step 2: Planner
    tool_calls = plan(query, history=history)

    # Planner VIẾT LẠI query cho tool ("liệt kê tất cả trò cảm giác mạnh" →
    # "trò chơi cảm giác mạnh") nên tool executor mất tín hiệu "liệt kê tất cả".
    # Kèm câu gốc để retrieval suy đúng phạm vi.
    for _c in tool_calls:
        _c.setdefault("user_query", query)

    # Step 3: Execute tools PARALLEL (giữ thứ tự)
    tool_results = _execute_parallel(tool_calls, lang=lang)

    # Step 4: Merge context
    merged_context = merge_contexts(tool_results)

    # Step 5: Few-shot — ưu tiên Golden Store > self-learning
    fewshot = ""
    if merged_context:
        try:
            if _HAS_CRITIC:
                fewshot = get_golden_examples(query, lang=lang)
            if not fewshot and _HAS_LEARNING:
                fewshot = get_fewshot_examples(query, lang=lang)
            # Inject prompt patch từ error pattern analysis
            if _HAS_CRITIC:
                patch = generate_prompt_patch()
                if patch:
                    fewshot = (fewshot + patch) if fewshot else patch
        except Exception:
            pass

    # Step 6: Responder
    response = respond(
        query=query,
        merged_context=merged_context,
        lang=lang,
        history=history,
        fewshot=fewshot,
    )

    answer = response["answer"]
    latency_ms = (time.perf_counter() - t0) * 1000

    # Step 6.5: Guardrail output check
    if _HAS_GUARDRAIL and response["source"] == "llm":
        gr_out = check_output(answer, merged_context, lang)
        if gr_out.action == "warn":
            logger.warning("Guardrail output warn: %s", gr_out.reason)

    # Step 6.8: Analytics tracking (non-blocking)
    if _HAS_ANALYTICS:
        try:
            _track_analytics(
                lang=lang, source=response["source"],
                tools=[c["tool"] for c in tool_calls] if "tool_calls" in dir() else [],
                latency_ms=latency_ms,
                session_id=session_id,
            )
        except Exception:
            pass

    # Step 6.9: Long-term memory learning
    if _HAS_LTM and session_id:
        try:
            learn_from_conversation(
                session_id, query, answer,
                [c["tool"] for c in tool_calls] if "tool_calls" in dir() else [],
                lang
            )
        except Exception:
            pass

    # Step 7: Critic + Learn async (không block response)
    # Throttle theo sample-rate — tránh nhân 3x tải Grok dưới traffic cao.
    if (merged_context and response["source"] == "llm"
            and random.random() < _LEARN_SAMPLE_RATE):
        if _HAS_CRITIC:
            critique_and_learn(query, merged_context, answer, lang, blocking=False)
        elif _HAS_LEARNING:
            evaluate_and_learn(query, merged_context, answer, lang, blocking=False)

    return {
        "answer":  answer,
        "source":  response["source"],
        "lang":    lang,
        "tools":   [c["tool"] for c in tool_calls],
        "latency": (time.perf_counter() - t0) * 1000,
    }


def chat_stream(
    query: str,
    history: list = None,
    use_faq_fast_path: bool = True,
    session_id: str = "",
) -> Generator[dict, None, None]:
    """
    Streaming pipeline — yield DICT EVENTS (v4):
        {"type": "meta",  "lang": str, "source": "faq"|"llm", "tools": [str]}
        {"type": "token", "text": str}

    v4: có session_id → nối memory layer + long-term memory + few-shot + học nền
    (trước đây stream bỏ qua các tầng này, chỉ blocking mới có).

    Dùng cho SSE endpoint trong api/chat.py.
    """
    history = history or []
    lang = detect_lang(query)

    # Step 0.5: Memory layer — extract entities + inject context
    if _HAS_MEMORY and session_id:
        try:
            update_memory(session_id, query)
            query = inject_memory_to_query(query, session_id)
        except Exception:
            pass

    # Step 1: FAQ fast path — yield meta + toàn bộ answer, không stream
    faq_result = _try_faq(query, lang, history, use_faq_fast_path)
    if faq_result:
        yield {"type": "meta", "lang": lang, "source": "faq",
               "tools": [], "rule": faq_result.get("rule", "")}
        yield {"type": "token", "text": faq_result.get("answer", "")}
        return

    # Step 2: Planner
    tool_calls = plan(query, history=history)

    # Planner VIẾT LẠI query cho tool ("liệt kê tất cả trò cảm giác mạnh" →
    # "trò chơi cảm giác mạnh") nên tool executor mất tín hiệu "liệt kê tất cả".
    # Kèm câu gốc để retrieval suy đúng phạm vi.
    for _c in tool_calls:
        _c.setdefault("user_query", query)

    # Step 3: Execute tools PARALLEL (giữ thứ tự)
    tool_results = _execute_parallel(tool_calls, lang=lang)

    # Step 4: Merge context
    merged_context = merge_contexts(tool_results)

    # Step 5: Few-shot — ưu tiên Golden Store > self-learning (giống blocking)
    fewshot = ""
    if merged_context:
        try:
            if _HAS_CRITIC:
                fewshot = get_golden_examples(query, lang=lang)
            if not fewshot and _HAS_LEARNING:
                fewshot = get_fewshot_examples(query, lang=lang)
            if _HAS_CRITIC:
                patch = generate_prompt_patch()
                if patch:
                    fewshot = (fewshot + patch) if fewshot else patch
        except Exception:
            pass

    # Meta trước token đầu tiên
    yield {"type": "meta", "lang": lang, "source": "llm",
           "tools": [c["tool"] for c in tool_calls]}

    # Step 6: STREAM từng token — user thấy chữ xuất hiện ngay
    full = []
    for text in respond_stream(
        query=query,
        merged_context=merged_context,
        lang=lang,
        history=history,
        fewshot=fewshot,
    ):
        full.append(text)
        yield {"type": "token", "text": text}

    answer = "".join(full)

    # Step 7: Long-term memory + học nền (async, sau khi stream xong)
    if _HAS_LTM and session_id:
        try:
            learn_from_conversation(
                session_id, query, answer,
                [c["tool"] for c in tool_calls], lang)
        except Exception:
            pass
    if merged_context and answer and random.random() < _LEARN_SAMPLE_RATE:
        if _HAS_CRITIC:
            critique_and_learn(query, merged_context, answer, lang, blocking=False)
        elif _HAS_LEARNING:
            evaluate_and_learn(query, merged_context, answer, lang, blocking=False)


def chat_stream_text(
    query: str,
    history: list = None,
    use_faq_fast_path: bool = True,
    session_id: str = "",
) -> Generator[str, None, None]:
    """Wrapper tương thích cũ — chỉ yield text, bỏ qua meta."""
    for event in chat_stream(query, history=history,
                             use_faq_fast_path=use_faq_fast_path,
                             session_id=session_id):
        if event["type"] == "token":
            yield event["text"]
