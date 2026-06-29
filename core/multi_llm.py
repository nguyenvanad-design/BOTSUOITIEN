"""
multi_llm.py — Multi-LLM Fallback Router

Priority: Grok 4.3 → Anthropic Haiku → FAQ-only mode
- Grok chết → tự động chuyển Anthropic
- Anthropic cũng chết → trả lời bằng FAQ + context thô
- Cost routing: câu đơn giản (FAQ miss) → Haiku, câu phức tạp → Grok
"""
import os, time, logging
from typing import Optional

logger = logging.getLogger("suoitien.multi_llm")

XAI_API_KEY       = os.getenv("XAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Health state per provider
_health = {"grok": True, "anthropic": True}
_fail_count = {"grok": 0, "anthropic": 0}
_last_fail  = {"grok": 0.0, "anthropic": 0.0}
FAIL_THRESHOLD  = 3      # lỗi 3 lần → mark unhealthy
RECOVERY_SECS   = 120    # thử lại sau 2 phút

PROVIDER_ORDER = ["grok", "anthropic"]

MODELS = {
    "grok":      os.getenv("SUOITIEN_GROK_MODEL",      "grok-4.20-0309-non-reasoning"),
    "anthropic": os.getenv("SUOITIEN_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
}


def _is_healthy(provider: str) -> bool:
    if _health[provider]:
        return True
    if time.time() - _last_fail[provider] > RECOVERY_SECS:
        logger.info("Retrying provider: %s", provider)
        _health[provider] = True
        _fail_count[provider] = 0
        return True
    return False


def _mark_fail(provider: str):
    _fail_count[provider] += 1
    _last_fail[provider]   = time.time()
    if _fail_count[provider] >= FAIL_THRESHOLD:
        _health[provider] = False
        logger.warning("Provider %s marked unhealthy after %d failures",
                       provider, _fail_count[provider])


def _mark_ok(provider: str):
    _fail_count[provider] = 0
    _health[provider]     = True


def _get_client(provider: str):
    if provider == "grok" and XAI_API_KEY:
        from openai import OpenAI
        return OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")
    if provider == "anthropic" and ANTHROPIC_API_KEY:
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return None


def chat_completion(messages: list, system: str = "", max_tokens: int = 600,
                    tools: list = None, tool_choice=None) -> tuple[str, str]:
    """
    Gọi LLM với fallback tự động.
    Returns: (response_text, provider_used)
    """
    for provider in PROVIDER_ORDER:
        if not _is_healthy(provider):
            continue
        client = _get_client(provider)
        if not client:
            continue
        try:
            if provider == "grok":
                oai_msgs = ([{"role": "system", "content": system}] if system else []) + messages
                kwargs   = {"model": MODELS[provider], "max_tokens": max_tokens,
                            "messages": oai_msgs}
                if tools:
                    kwargs["tools"]       = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                resp = client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                _mark_ok(provider)
                return text.strip(), provider
            else:
                kwargs = {"model": MODELS[provider], "max_tokens": max_tokens,
                          "messages": messages}
                if system:
                    kwargs["system"] = system
                if tools:
                    kwargs["tools"]       = tools
                    kwargs["tool_choice"] = {"type": "any"}
                resp = client.messages.create(**kwargs)
                text = resp.content[0].text.strip()
                _mark_ok(provider)
                return text, provider
        except Exception as e:
            logger.warning("Provider %s failed: %s", provider, str(e)[:100])
            _mark_fail(provider)

    # All providers down → FAQ-only fallback
    logger.error("All LLM providers unavailable — FAQ-only mode")
    return "", "fallback"


def stream_completion(messages: list, system: str = "", max_tokens: int = 600):
    """Streaming với fallback. Yield (chunk, provider)."""
    for provider in PROVIDER_ORDER:
        if not _is_healthy(provider):
            continue
        client = _get_client(provider)
        if not client:
            continue
        try:
            if provider == "grok":
                oai_msgs = ([{"role": "system", "content": system}] if system else []) + messages
                stream = client.chat.completions.create(
                    model=MODELS[provider], max_tokens=max_tokens,
                    messages=oai_msgs, stream=True)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta, provider
                _mark_ok(provider)
                return
            else:
                with client.messages.stream(
                    model=MODELS[provider], max_tokens=max_tokens,
                    system=system, messages=messages
                ) as stream:
                    for text in stream.text_stream:
                        yield text, provider
                _mark_ok(provider)
                return
        except Exception as e:
            logger.warning("Stream provider %s failed: %s", provider, str(e)[:100])
            _mark_fail(provider)
    yield "", "fallback"


def health_status() -> dict:
    return {
        p: {"healthy": _health[p], "fail_count": _fail_count[p],
            "model": MODELS[p], "has_key": bool(_get_client(p))}
        for p in PROVIDER_ORDER
    }
