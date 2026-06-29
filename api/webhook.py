"""
api/webhook.py — Webhook handlers cho Zalo OA, Messenger, Web widget
Tích hợp conversation history qua session_id = user_id của platform.

v3:
- _pipeline (blocking LLM 2-5s) chạy qua threadpool — KHÔNG chặn event loop
  (trước đây async endpoint gọi sync pipeline trực tiếp → cả server đứng hình)
- Zalo/FB: ACK 200 NGAY, xử lý + reply trong background task
  (platform yêu cầu ACK nhanh; chờ pipeline xong dễ bị retry → bot trả lời đúp)
- Verify chữ ký webhook (FB X-Hub-Signature-256, Zalo X-ZEvent-Signature)
  khi có secret — chặn kẻ lạ POST giả tin nhắn
- Fix bug reset web widget: history lưu key "web_{id}" nhưng clear key trần
- httpx.AsyncClient dùng chung (connection pool) thay vì tạo mới mỗi tin nhắn
"""

import os
import sys
import json
import uuid
import hmac
import hashlib
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional

from api.chat import _pipeline
from session_store import clear_session

logger = logging.getLogger("suoitien.api.webhook")

router = APIRouter()

ZALO_OA_TOKEN   = os.getenv("ZALO_OA_TOKEN", "")
ZALO_APP_ID     = os.getenv("ZALO_APP_ID", "")
ZALO_APP_SECRET = os.getenv("ZALO_APP_SECRET", "")
FB_PAGE_TOKEN   = os.getenv("FB_PAGE_TOKEN", "")
FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "suoitien_verify_2026")
FB_APP_SECRET   = os.getenv("FB_APP_SECRET", "")

USE_LLM = bool(os.getenv("ANTHROPIC_API_KEY"))

# ── Shared HTTP client (connection pool, tạo 1 lần) ────────────────────────────
_http: httpx.AsyncClient | None = None

def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=10)
    return _http


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_fb_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Messenger: X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app_secret, body).
    Không set FB_APP_SECRET → bỏ qua (log warning 1 lần lúc import).
    """
    if not FB_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        FB_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header[len("sha256="):], expected)


def _verify_zalo_signature(raw_body: bytes, signature_header: str,
                           timestamp: str) -> bool:
    """
    Zalo OA: X-ZEvent-Signature = 'mac=' + SHA256(appId + body + timestamp + secret).
    Không set ZALO_APP_ID/SECRET → bỏ qua.
    """
    if not (ZALO_APP_SECRET and ZALO_APP_ID):
        return True
    if not signature_header:
        return False
    mac = signature_header[len("mac="):] if signature_header.startswith("mac=") \
          else signature_header
    raw = (ZALO_APP_ID.encode() + raw_body
           + str(timestamp).encode() + ZALO_APP_SECRET.encode())
    expected = hashlib.sha256(raw).hexdigest()
    return hmac.compare_digest(mac, expected)


if not FB_APP_SECRET:
    logger.warning("FB_APP_SECRET chưa set — webhook Messenger KHÔNG verify chữ ký")
if not (ZALO_APP_SECRET and ZALO_APP_ID):
    logger.warning("ZALO_APP_ID/SECRET chưa set — webhook Zalo KHÔNG verify chữ ký")


# ── Background processing ──────────────────────────────────────────────────────
# Pipeline blocking 2-5s → chạy trong threadpool, ACK platform ngay lập tức.

async def _process_and_reply(platform: str, user_id: str, message: str):
    """Chạy pipeline trong threadpool rồi gửi reply về platform."""
    try:
        result = await run_in_threadpool(
            _pipeline, message,
            session_id=f"{platform}_{user_id}",
            use_llm=USE_LLM,
        )
        answer = result["answer"]
        if platform == "zalo" and ZALO_OA_TOKEN:
            await _zalo_send(user_id, answer)
        elif platform == "fb" and FB_PAGE_TOKEN:
            await _fb_send(user_id, answer)
        logger.info("[%s] replied to %s (intent=%s, %d chars)",
                    platform, user_id, result["intent"], len(answer))
    except Exception:
        logger.exception("[%s] process_and_reply failed for %s", platform, user_id)


# ══════════════════════════════════════════════════════════════════════
# ZALO
# ══════════════════════════════════════════════════════════════════════

async def _zalo_send(user_id: str, text: str):
    url     = "https://openapi.zalo.me/v3.0/oa/message/cs"
    payload = {"recipient": {"user_id": user_id}, "message": {"text": text[:2000]}}
    headers = {"access_token": ZALO_OA_TOKEN, "Content-Type": "application/json"}
    try:
        resp = await _client().post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning("Zalo send failed: %s %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("Zalo send error for user %s", user_id)


@router.post("/zalo")
async def zalo_webhook(request: Request):
    raw  = await request.body()
    data = json.loads(raw or b"{}")

    # Verify chữ ký (nếu có secret)
    sig = request.headers.get("X-ZEvent-Signature", "")
    ts  = data.get("timestamp", "")
    if not _verify_zalo_signature(raw, sig, ts):
        logger.warning("Zalo webhook: invalid signature — rejected")
        raise HTTPException(status_code=403, detail="Invalid signature")

    if data.get("event_name", "") != "user_send_text":
        return {"status": "ignored"}

    user_id = data.get("sender", {}).get("id", "")
    message = data.get("message", {}).get("text", "").strip()
    if not message or not user_id:
        return {"status": "empty"}

    # ACK ngay — xử lý + reply trong background (Zalo yêu cầu phản hồi nhanh)
    asyncio.create_task(_process_and_reply("zalo", user_id, message))
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════
# MESSENGER
# ══════════════════════════════════════════════════════════════════════

async def _fb_send(recipient_id: str, text: str):
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text[:2000]}}
    try:
        resp = await _client().post(
            url, json=payload,
            params={"access_token": FB_PAGE_TOKEN},  # token qua params, không nhét vào URL string
        )
        if resp.status_code != 200:
            logger.warning("FB send failed: %s %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("FB send error for user %s", recipient_id)


@router.get("/messenger")
async def messenger_verify(request: Request):
    params    = request.query_params
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == FB_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/messenger")
async def messenger_webhook(request: Request):
    raw  = await request.body()

    # Verify chữ ký (nếu có secret)
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_fb_signature(raw, sig):
        logger.warning("Messenger webhook: invalid signature — rejected")
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = json.loads(raw or b"{}")
    if data.get("object") != "page":
        return {"status": "ignored"}

    # ACK ngay, xử lý từng tin trong background — FB retry nếu phản hồi chậm >20s
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id", "")
            message   = event.get("message", {})

            if message.get("is_echo") or "text" not in message:
                continue
            text = message["text"].strip()
            if not text or not sender_id:
                continue

            asyncio.create_task(_process_and_reply("fb", sender_id, text))

    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════
# WEB WIDGET
# ══════════════════════════════════════════════════════════════════════

class WebChatRequest(BaseModel):
    message:    str
    session_id: Optional[str] = None
    reset:      bool          = False

class WebChatResponse(BaseModel):
    answer:     str
    intent:     str
    source:     str
    session_id: str


@router.post("/web", response_model=WebChatResponse)
async def web_webhook(req: WebChatRequest):
    session_id = req.session_id or str(uuid.uuid4())

    if req.reset:
        # FIX: history lưu dưới key "web_{session_id}" — trước đây clear key trần
        # nên reset không bao giờ có tác dụng
        clear_session(f"web_{session_id}")

    # Pipeline blocking → threadpool, không chặn event loop
    result = await run_in_threadpool(
        _pipeline, req.message,
        session_id=f"web_{session_id}",
        use_llm=USE_LLM,
    )
    return WebChatResponse(
        answer     = result["answer"],
        intent     = result["intent"],
        source     = result["source"],
        session_id = session_id,
    )
