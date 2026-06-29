"""
api/webhook_content.py — Nhận push event từ suoitien.vn CMS

Website gọi endpoint này khi có nội dung mới/sửa:
  POST /webhook/content
  Header: X-Webhook-Secret: <CONTENT_WEBHOOK_SECRET>
  Body: {
    "event": "post.created" | "post.updated" | "post.deleted",
    "slug": "combo-ky-quan",
    "url": "https://suoitien.vn/combo-ky-quan",
    "title": "Combo Kỳ Quan",
    "content": "nội dung HTML hoặc text...",  (optional — nếu có thì skip crawl)
    "category": "tickets" | "attractions" | "events" | ...  (optional)
  }

Tích hợp với CMS:
  WordPress: dùng plugin "WP Webhooks" hoặc custom action hook
    add_action('save_post', function($post_id) {
        wp_remote_post('https://bot.suoitien.vn/webhook/content', [...]);
    });
  Custom CMS: gọi HTTP POST khi publish/update bài

Bảo mật: verify bằng shared secret trong header X-Webhook-Secret
"""

import os
import sys
import json
import time
import logging
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("suoitien.api.webhook_content")

router = APIRouter()

CONTENT_WEBHOOK_SECRET = os.getenv("CONTENT_WEBHOOK_SECRET", "")

VALID_EVENTS = {"post.created", "post.updated", "post.deleted",
                "price.updated", "event.created", "event.updated"}


def _verify_secret(request: Request) -> bool:
    if not CONTENT_WEBHOOK_SECRET:
        logger.warning("CONTENT_WEBHOOK_SECRET chưa set — webhook content không verify")
        return True
    secret = request.headers.get("X-Webhook-Secret", "")
    return secret == CONTENT_WEBHOOK_SECRET


def _process_content_event(payload: dict):
    """
    Xử lý event từ CMS:
    1. Nếu payload có 'content' → skip crawl, extract trực tiếp
    2. Nếu không có 'content' → crawl URL rồi extract
    3. Hot-swap data + rebuild BM25
    """
    event    = payload.get("event", "")
    slug     = payload.get("slug", "")
    url      = payload.get("url", "")
    title    = payload.get("title", "")
    content  = payload.get("content", "")
    category = payload.get("category", "")

    if not slug and not url:
        logger.warning("Webhook content: thiếu slug và url")
        return

    logger.info("Content event: %s slug=%s", event, slug)

    if event == "post.deleted":
        _handle_delete(slug)
        return

    try:
        from auto_updater import (
            _crawl_url, _guess_category,
            _extract_entities_batch, _hot_swap_data
        )

        # Build doc — dùng content từ payload nếu có (nhanh hơn, không cần crawl)
        if content and len(content) > 100:
            import re
            clean = re.sub(r"<[^>]+>", " ", content)
            clean = re.sub(r"\s+", " ", clean).strip()
            cat = category or _guess_category(slug, title, clean)
            doc = {
                "url":        url or f"https://suoitien.vn/{slug}",
                "slug":       slug,
                "title":      title,
                "text":       clean[:4000],
                "char_count": len(clean),
                "category":   cat,
                "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            logger.info("Using payload content (%d chars) — skip crawl", len(clean))
        else:
            # Crawl URL nếu không có content
            target_url = url or f"https://suoitien.vn/{slug}"
            doc = _crawl_url(target_url)
            if not doc:
                logger.warning("Crawl failed for %s", target_url)
                return
            if category:
                doc["category"] = category

        # Extract entities + hot-swap
        new_entities = _extract_entities_batch([doc])
        _hot_swap_data([doc], new_entities)

        logger.info("Content update done: slug=%s category=%s entities=%s",
                    slug, doc["category"],
                    {k: len(v) for k, v in new_entities.items()})

    except Exception:
        logger.exception("Content event processing failed: slug=%s", slug)


def _handle_delete(slug: str):
    """Xóa slug khỏi clean_v4.json khi bài bị xóa."""
    try:
        from auto_updater import _CLEAN_FILE
        docs = json.loads(_CLEAN_FILE.read_text(encoding="utf-8"))
        before = len(docs)
        docs = [d for d in docs if d.get("slug") != slug]
        if len(docs) < before:
            _CLEAN_FILE.write_text(
                json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Deleted slug=%s from clean_v4", slug)
    except Exception:
        logger.exception("Delete failed: slug=%s", slug)


@router.post("/content")
async def content_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Nhận push event từ CMS.
    ACK ngay 200 — xử lý extract + hot-swap trong background.
    """
    if not _verify_secret(request):
        logger.warning("Content webhook: invalid secret")
        raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event", "")
    if event and event not in VALID_EVENTS:
        logger.info("Content webhook: ignored event=%s", event)
        return {"status": "ignored", "event": event}

    # ACK ngay — xử lý background
    background_tasks.add_task(
        run_in_threadpool, _process_content_event, payload
    )

    return {
        "status":  "queued",
        "event":   event,
        "slug":    payload.get("slug", ""),
        "message": "Đang xử lý trong background",
    }


@router.get("/content/test")
async def content_webhook_test():
    """Test endpoint — gửi event giả để kiểm tra pipeline."""
    test_payload = {
        "event":    "post.updated",
        "slug":     "test-webhook",
        "url":      "https://suoitien.vn/test-webhook",
        "title":    "Test webhook",
        "content":  "Đây là nội dung test từ webhook. Giá vé: 100.000đ người lớn.",
        "category": "tickets",
    }
    _process_content_event(test_payload)
    return {"status": "ok", "message": "Test event processed"}
