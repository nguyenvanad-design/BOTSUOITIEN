"""
responder.py — LLM2: Format câu trả lời đẹp từ tool results.
Persona bot "Tiên" — hướng dẫn viên trẻ, xưng em, gọi anh/chị.
Hỗ trợ 5 ngôn ngữ: VI / EN / ZH / KO / JA.

v3:
- Prompt lấy từ prompts.py (1 nguồn duy nhất)
- Xóa _build_messages chết (có bug {{lang_note}}) → 1 builder dùng chung
- Client Anthropic tạo 1 lần ở module level
- Stream: chỉ yield fallback nếu CHƯA yield gì (tránh chèn fallback giữa câu)
- Logging thay vì nuốt lỗi im lặng
"""

import time
import logging
from typing import Generator

import llm_client
from prompts import RESPONDER_SYSTEM, LANG_INSTRUCTION, FALLBACK_MESSAGE

logger = logging.getLogger("suoitien.responder")

# ── LLM qua adapter 1 cửa (core/llm_client.py) ────────────────────────────────
# Provider + model chọn bằng env trong .env — không còn client/SDK riêng ở đây.
PROVIDER   = llm_client.get_provider() or ""
MODEL_NAME = llm_client.resolve_model("responder") if PROVIDER else ""


def _fallback(lang: str) -> str:
    return FALLBACK_MESSAGE.get(lang, FALLBACK_MESSAGE["vi"])


def _build(query: str, merged_context: str, lang: str,
           history: list, fewshot: str = "") -> tuple[str, list]:
    """Build (system, messages) — dùng chung cho blocking & stream mode."""
    lang_note = LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["vi"])
    system = f"{lang_note}\n\n{RESPONDER_SYSTEM}"

    # Inject few-shot examples nếu có (từ self-learning database)
    if fewshot:
        system += f"\n\n{fewshot}"

    messages = list(history or [])
    user_content = f"Câu hỏi của khách: {query}"
    if merged_context:
        user_content += ("\n\n--- THÔNG TIN NỘI BỘ (chỉ để em tham khảo, TUYỆT ĐỐI "
                         "KHÔNG nhắc/trích tên mục này với khách) ---\n"
                         f"{merged_context}")
    user_content += ("\n\nTrả lời khách tự nhiên, ấm áp như nhân viên đang biết việc — "
                     "KHÔNG nhắc bất kỳ từ nội bộ nào ở trên.")
    messages.append({"role": "user", "content": user_content})
    return system, messages


def respond(
    query: str,
    merged_context: str,
    lang: str = "vi",
    history: list = None,
    retries: int = 2,
    fewshot: str = "",
) -> dict:
    """
    LLM2 Responder — blocking mode.
    Returns: {"answer": str, "source": str, "lang": str}
    """
    if not merged_context and not history:
        return {"answer": _fallback(lang), "source": "fallback", "lang": lang}

    if not llm_client.available():
        logger.warning("No LLM provider — returning raw context")
        return {"answer": merged_context or _fallback(lang),
                "source": "no_api_key", "lang": lang}

    system, messages = _build(query, merged_context, lang, history, fewshot)

    for attempt in range(retries + 1):
        try:
            text = llm_client.complete(
                system=system, messages=messages,
                max_tokens=600, role="responder")
            return {"answer": text.strip(), "source": "llm", "lang": lang}
        except Exception:
            logger.exception("Responder error (attempt %d)", attempt + 1)
            if attempt < retries:
                time.sleep(0.5)

    return {"answer": merged_context[:800] if merged_context else _fallback(lang),
            "source": "fallback", "lang": lang}


def respond_stream(
    query: str,
    merged_context: str,
    lang: str = "vi",
    history: list = None,
    fewshot: str = "",
) -> Generator[str, None, None]:
    """
    LLM2 Responder — streaming mode. Yield từng text chunk.
    Dùng cho SSE endpoint.
    """
    if not merged_context and not history:
        yield _fallback(lang)
        return

    if not llm_client.available():
        logger.warning("No LLM provider — streaming raw context")
        yield merged_context or _fallback(lang)
        return

    system, messages = _build(query, merged_context, lang, history, fewshot)

    emitted = False
    try:
        for text in llm_client.complete_stream(
            system=system, messages=messages,
            max_tokens=600, role="responder"):
            if text:
                emitted = True
                yield text
    except Exception:
        logger.exception("Responder stream error")
        if not emitted:
            yield _fallback(lang)
