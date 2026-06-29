"""
api/chat.py — Chat endpoint với streaming SSE support.
v3:
- Stream endpoint nhận event "meta" từ pipeline → intent/source THẬT
  (trước đây hardcode "unknown"/"llm" → build_links sai, done event báo sai)
- Không leak nội dung exception ra client (chỉ log server-side)
- Logging
"""

import sys
import uuid
import json
import time
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from chat_pipeline     import chat as _chat, chat_stream as _chat_stream
from session_store     import get_history, add_turn, clear_session, store_stats
from link_service      import build_links, format_links_markdown
from language_detector import detect_lang

logger = logging.getLogger("suoitien.api.chat")

router = APIRouter()


class ChatRequest(BaseModel):
    message:    str           = Field(..., min_length=1, max_length=500)
    session_id: Optional[str] = None
    use_llm:    bool          = True
    reset:      bool          = False


class ChatResponse(BaseModel):
    answer:     str
    intent:     str
    source:     str
    session_id: str


# ── Blocking pipeline (dùng chung cho /chat và webhook) ───────────────────────
def _pipeline(message: str, session_id: str, use_llm: bool = True) -> dict:
    history = get_history(session_id)

    result = _chat(query=message, history=history, use_faq_fast_path=True)

    answer = result["answer"]
    intent = result["tools"][0] if result["tools"] else (
        "faq" if result["source"] == "faq" else "unknown"
    )
    source = result["source"]
    lang   = result["lang"]

    if use_llm:
        links = build_links(intent, [], source, lang)
        if links:
            answer += format_links_markdown(links)

    add_turn(session_id, message, answer, intent)

    return {"answer": answer, "intent": intent,
            "source": source, "session_id": session_id}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if req.reset:
        clear_session(session_id)
    try:
        return ChatResponse(**_pipeline(req.message, session_id, req.use_llm))
    except Exception:
        # Log đầy đủ server-side; KHÔNG leak chi tiết exception ra client
        logger.exception("Chat pipeline error (session=%s)", session_id)
        raise HTTPException(
            status_code=500,
            detail="Hệ thống đang bận, anh/chị vui lòng thử lại sau ít phút nhé!",
        )


# ── Streaming SSE endpoint ─────────────────────────────────────────────────────
@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """
    Server-Sent Events streaming endpoint.
    Client nhận token ngay khi LLM generate — không cần chờ toàn bộ response.

    SSE format:
        data: {"type":"token","text":"Em "}
        data: {"type":"token","text":"xin "}
        ...
        data: {"type":"done","session_id":"xxx","intent":"search_tickets","source":"llm","latency":2300}
        data: [DONE]
    """
    session_id = req.session_id or str(uuid.uuid4())
    if req.reset:
        clear_session(session_id)

    def generate():
        history  = get_history(session_id)
        full_ans = []
        t0       = time.perf_counter()
        intent   = "unknown"
        source   = "llm"
        lang     = "vi"

        try:
            for event in _chat_stream(
                query=req.message,
                history=history,
                use_faq_fast_path=True,
            ):
                if event["type"] == "meta":
                    # Pipeline báo intent/source THẬT trước token đầu tiên
                    source = event.get("source", "llm")
                    lang   = event.get("lang", "vi")
                    tools  = event.get("tools", [])
                    intent = tools[0] if tools else (
                        "faq" if source == "faq" else "unknown"
                    )
                    continue

                # token event
                chunk = event.get("text", "")
                if not chunk:
                    continue
                full_ans.append(chunk)
                data = json.dumps({"type": "token", "text": chunk},
                                  ensure_ascii=False)
                yield f"data: {data}\n\n"

            answer  = "".join(full_ans)
            latency = int((time.perf_counter() - t0) * 1000)

            # Attach links — giờ dùng intent/source thật từ meta
            links = build_links(intent, [], source, lang)
            if links:
                link_text = format_links_markdown(links)
                yield ("data: "
                       + json.dumps({"type": "token", "text": link_text},
                                    ensure_ascii=False)
                       + "\n\n")
                answer += link_text

            # Lưu session sau khi stream xong
            add_turn(session_id, req.message, answer, intent)

            done = json.dumps({
                "type":       "done",
                "session_id": session_id,
                "intent":     intent,
                "source":     source,
                "latency":    latency,
            })
            yield f"data: {done}\n\n"
            yield "data: [DONE]\n\n"

        except Exception:
            logger.exception("Stream pipeline error (session=%s)", session_id)
            err = json.dumps({
                "type": "error",
                "message": "Hệ thống đang bận, vui lòng thử lại sau.",
            }, ensure_ascii=False)
            yield f"data: {err}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",  # tắt nginx buffering
            # CORS đã có middleware ở main.py — không hardcode "*" ở đây
        },
    )


# ── Utils ──────────────────────────────────────────────────────────────────────
@router.get("/chat/test")
def chat_test(q: str = "Suối Tiên ở đâu?"):
    session_id = str(uuid.uuid4())
    return _pipeline(q, session_id, use_llm=True)


@router.get("/chat/stats")
def chat_stats():
    return store_stats()


@router.delete("/chat/session/{session_id}")
def reset_session(session_id: str):
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}
