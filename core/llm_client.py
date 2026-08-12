"""
llm_client.py — Adapter 1 cửa cho LLM provider (Anthropic Claude / Google Gemini).

Chọn provider:
- env LLM_PROVIDER=anthropic|gemini (ép cứng, ưu tiên cao nhất)
- không set → tự động: có GEMINI_API_KEY → gemini, ngược lại có
  ANTHROPIC_API_KEY → anthropic

Cả 3 nơi gọi LLM (planner, responder, auto_updater) đều đi qua module này —
đổi provider chỉ cần đổi .env, không sửa code.

Format chung dùng chuẩn Anthropic, adapter tự convert cho Gemini:
- messages: [{"role": "user"|"assistant", "content": str}]
- tools   : [{"name", "description", "input_schema"}]   (JSON Schema)

Lưu ý: key đọc ĐỘNG (os.getenv trong hàm) chứ không cache lúc import —
tránh lặp lại bug .env load sau khi module đã import.
"""

import os
import logging
import threading
from collections import defaultdict
from typing import Generator, Optional

logger = logging.getLogger("suoitien.llm")

# ── Token usage tracking — đọc từ field `usage` của API response ───────────────
_usage_lock = threading.Lock()
USAGE: dict = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0})


def _track(role: str, input_tokens, output_tokens):
    with _usage_lock:
        u = USAGE[role]
        u["calls"]  += 1
        u["input"]  += int(input_tokens or 0)
        u["output"] += int(output_tokens or 0)


def get_usage() -> dict:
    """Snapshot usage theo role: {role: {calls, input, output}}."""
    with _usage_lock:
        return {k: dict(v) for k, v in USAGE.items()}


def reset_usage():
    with _usage_lock:
        USAGE.clear()

# Grok (xAI) dùng API tương thích Anthropic SDK → đi chung code path anthropic
_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini":    "gemini-2.5-flash",
    "grok":      os.getenv("SUOITIEN_GROK_MODEL", "grok-4.20-0309-non-reasoning"),
}

_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "grok":      "XAI_API_KEY",
}

_MODEL_PREFIX = {"anthropic": "claude", "gemini": "gemini", "grok": "grok"}

# Thứ tự auto-detect khi không ép LLM_PROVIDER
_AUTO_ORDER = ["grok", "gemini", "anthropic"]

_clients: dict = {}  # provider -> client instance (lazy)


# ── Provider selection ──────────────────────────────────────────────────────────

def get_provider() -> Optional[str]:
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced in _DEFAULT_MODELS:
        return forced
    for p in _AUTO_ORDER:
        if os.getenv(_KEY_ENV[p]):
            return p
    return None


def available() -> bool:
    p = get_provider()
    return bool(p and os.getenv(_KEY_ENV[p]))


def resolve_model(role: str) -> str:
    """
    role: planner | responder | updater.
    Env SUOITIEN_<ROLE>_MODEL override — chỉ nhận nếu khớp provider hiện tại
    (tránh để sót model claude trong env khi đã chuyển sang gemini/grok).
    """
    provider = get_provider() or "anthropic"
    env_model = os.getenv(f"SUOITIEN_{role.upper()}_MODEL", "").strip()
    if env_model:
        if env_model.startswith(_MODEL_PREFIX[provider]):
            return env_model
        logger.warning("Bỏ qua SUOITIEN_%s_MODEL=%s — không khớp provider %s",
                       role.upper(), env_model, provider)
    return _DEFAULT_MODELS[provider]


# Timeout + retry cho mỗi LLM call — tránh 1 call chậm (rate-limit) treo cả request.
# Env: SUOITIEN_LLM_TIMEOUT (giây, default 30), SUOITIEN_LLM_RETRIES (default 1)
_LLM_TIMEOUT = float(os.getenv("SUOITIEN_LLM_TIMEOUT", "30"))
_LLM_RETRIES = int(os.getenv("SUOITIEN_LLM_RETRIES", "1"))


def _client(provider: str):
    if provider not in _clients:
        if provider == "gemini":
            from google import genai
            _clients[provider] = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        elif provider == "grok":
            import anthropic
            _clients[provider] = anthropic.Anthropic(
                api_key=os.getenv("XAI_API_KEY"),
                base_url="https://api.x.ai",
                timeout=_LLM_TIMEOUT,
                max_retries=_LLM_RETRIES,
            )
        else:
            import anthropic
            _clients[provider] = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=_LLM_TIMEOUT,
                max_retries=_LLM_RETRIES,
            )
    return _clients[provider]


# ── Gemini helpers ──────────────────────────────────────────────────────────────

def _to_gemini_contents(messages: list):
    from google.genai import types
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=str(m["content"]))]))
    return contents


def _gemini_config(system: Optional[str], max_tokens: int, tools: Optional[list] = None):
    from google.genai import types
    cfg: dict = {
        "max_output_tokens": max_tokens,
        # gemini-2.5-flash mặc định BẬT thinking — tắt để giảm latency + token
        "thinking_config": types.ThinkingConfig(thinking_budget=0),
    }
    if system:
        cfg["system_instruction"] = system
    if tools:
        decls = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters_json_schema=t["input_schema"],
            )
            for t in tools
        ]
        cfg["tools"] = [types.Tool(function_declarations=decls)]
        cfg["tool_config"] = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY")
        )
    return types.GenerateContentConfig(**cfg)


# ── Public API ──────────────────────────────────────────────────────────────────

def _coerce_inputs(tools: list, calls: list[dict]) -> list[dict]:
    """
    Ép kiểu tool input theo input_schema. Một số provider (Grok) trả số
    dạng string ("50" thay vì 50) → so sánh số ở downstream sẽ crash.
    Giá trị không ép được → bỏ khỏi input (an toàn hơn giữ rác).
    """
    schemas = {t["name"]: t["input_schema"].get("properties", {}) for t in tools}
    for call in calls:
        props = schemas.get(call["name"], {})
        for key, val in list(call["input"].items()):
            typ = props.get(key, {}).get("type")
            try:
                if typ == "integer" and not isinstance(val, int):
                    call["input"][key] = int(float(val))
                elif typ == "number" and not isinstance(val, (int, float)):
                    call["input"][key] = float(val)
                elif typ == "boolean" and isinstance(val, str):
                    call["input"][key] = val.strip().lower() in ("true", "1", "yes")
            except (ValueError, TypeError):
                logger.warning("Bỏ tool input %s=%r — không ép được kiểu %s",
                               key, val, typ)
                del call["input"][key]
    return calls


def call_tools(system: str, messages: list, tools: list,
               max_tokens: int = 300, role: str = "planner") -> list[dict]:
    """
    Tool calling — trả về [{"name": str, "input": dict}].
    [] nếu model không gọi tool nào (vd: chat xã giao).
    """
    provider = get_provider()
    model = resolve_model(role)

    if provider == "gemini":
        resp = _client("gemini").models.generate_content(
            model=model,
            contents=_to_gemini_contents(messages),
            config=_gemini_config(system, max_tokens, tools=tools),
        )
        um = resp.usage_metadata
        _track(role, um.prompt_token_count,
               (um.candidates_token_count or 0) + (um.thoughts_token_count or 0))
        calls = [{"name": fc.name, "input": dict(fc.args or {})}
                 for fc in (resp.function_calls or [])]
        return _coerce_inputs(tools, calls)

    # anthropic / grok — chung Anthropic SDK
    resp = _client(provider).messages.create(
        model=model, max_tokens=max_tokens, system=system,
        tools=tools, tool_choice={"type": "any"}, messages=messages,
    )
    _track(role, resp.usage.input_tokens, resp.usage.output_tokens)
    calls = [{"name": b.name, "input": dict(b.input)}
             for b in resp.content if b.type == "tool_use"]
    return _coerce_inputs(tools, calls)


def complete(system: Optional[str], messages: list,
             max_tokens: int = 1000, role: str = "responder") -> str:
    """Text completion — blocking, trả về str đã strip."""
    provider = get_provider()
    model = resolve_model(role)

    if provider == "gemini":
        resp = _client("gemini").models.generate_content(
            model=model,
            contents=_to_gemini_contents(messages),
            config=_gemini_config(system, max_tokens),
        )
        um = resp.usage_metadata
        _track(role, um.prompt_token_count,
               (um.candidates_token_count or 0) + (um.thoughts_token_count or 0))
        return (resp.text or "").strip()

    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    msg = _client(provider).messages.create(**kwargs)
    _track(role, msg.usage.input_tokens, msg.usage.output_tokens)
    return msg.content[0].text.strip()


def complete_stream(system: Optional[str], messages: list,
                    max_tokens: int = 1000,
                    role: str = "responder") -> Generator[str, None, None]:
    """Text completion — streaming, yield từng text chunk."""
    provider = get_provider()
    model = resolve_model(role)

    if provider == "gemini":
        stream = _client("gemini").models.generate_content_stream(
            model=model,
            contents=_to_gemini_contents(messages),
            config=_gemini_config(system, max_tokens),
        )
        um = None
        for chunk in stream:
            if chunk.usage_metadata:
                um = chunk.usage_metadata
            if chunk.text:
                yield chunk.text
        if um:
            _track(role, um.prompt_token_count,
                   (um.candidates_token_count or 0) + (um.thoughts_token_count or 0))
        return

    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    if provider == "grok":
        # xAI không gửi field `index` trong SSE events → helper .stream()
        # của Anthropic SDK crash khi accumulate. Dùng raw stream thay thế.
        in_tok = out_tok = 0
        for event in _client(provider).messages.create(**kwargs, stream=True):
            if event.type == "message_start":
                in_tok = event.message.usage.input_tokens
            elif event.type == "message_delta":
                out_tok = getattr(event.usage, "output_tokens", out_tok)
            elif event.type == "content_block_delta":
                text = getattr(event.delta, "text", None)
                if text:
                    yield text
        _track(role, in_tok, out_tok)
        return

    with _client(provider).messages.stream(**kwargs) as s:
        for text in s.text_stream:
            yield text
        final = s.get_final_message()
        _track(role, final.usage.input_tokens, final.usage.output_tokens)


# ── CLI test ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    print(f"Provider : {get_provider()}")
    print(f"Available: {available()}")
    print(f"Planner  : {resolve_model('planner')}")
    print(f"Responder: {resolve_model('responder')}")

    if available():
        out = complete(None, [{"role": "user", "content": "Nói 'xin chào' bằng 1 từ."}],
                       max_tokens=50)
        print(f"Test call: {out!r}")
