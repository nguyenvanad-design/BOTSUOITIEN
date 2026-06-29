"""
vector_search_incremental.py — Incremental FAISS index update

Thay vì full rebuild lúc 3h sáng (bot có thể trả lời sai 3 tiếng),
module này cho phép thêm vectors mới vào index NGAY KHI có data mới.

Cách dùng:
  from vector_search_incremental import add_documents
  add_documents([{"slug": "combo-moi", "text": "...", "title": "..."}])

Chiến lược:
  - Index chính: faiss_index/index.faiss (đọc bởi vector_search.py)
  - Buffer: danh sách docs mới chưa embed
  - Khi buffer >= BUFFER_THRESHOLD hoặc được trigger → embed + merge vào index chính
  - Full rebuild vẫn chạy 3h sáng để defragment và re-normalize

Production upgrade: swap FAISS → Qdrant/Weaviate để có real incremental update
mà không cần lock. Hiện tại dùng threading.Lock để đảm bảo thread-safe.
"""

import os
import json
import time
import pickle
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("suoitien.vector_incremental")

_BASE      = Path(os.environ.get("SUOITIEN_BASE", Path(__file__).parent))
_INDEX_DIR = _BASE / "data" / "faiss_index"
_BUFFER_F  = _INDEX_DIR / "incremental_buffer.json"

BUFFER_THRESHOLD = 5   # Embed ngay khi có 5 docs mới
_buffer: list = []
_buffer_lock = threading.Lock()


def _load_buffer() -> list:
    if _BUFFER_F.exists():
        try:
            return json.loads(_BUFFER_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_buffer(buf: list):
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    _BUFFER_F.write_text(json.dumps(buf, ensure_ascii=False), encoding="utf-8")


def add_documents(docs: list[dict], force_flush: bool = False):
    """
    Thêm docs mới vào buffer. Nếu buffer đủ lớn → flush vào index.

    docs: list of {"slug", "title", "text", "category"}
    force_flush: flush ngay không đợi threshold
    """
    global _buffer
    with _buffer_lock:
        _buffer.extend(docs)
        _save_buffer(_buffer)
        logger.info("Incremental buffer: %d docs queued", len(_buffer))

        if len(_buffer) >= BUFFER_THRESHOLD or force_flush:
            _flush_buffer()


def _flush_buffer():
    """
    Embed buffer docs và merge vào FAISS index.
    Gọi trong _buffer_lock context.
    """
    global _buffer
    if not _buffer:
        return

    try:
        import faiss
        import numpy as np
        from vector_search import _get_model, _load_index, _INDEX_FILE, _CHUNKS_FILE

        logger.info("Flushing %d docs to FAISS index...", len(_buffer))

        model = _get_model()
        index, chunks = _load_index()

        new_chunks = []
        texts_to_embed = []
        for doc in _buffer:
            text = f"{doc.get('title', '')} {doc.get('text', '')[:500]}"
            texts_to_embed.append(text)
            new_chunks.append({
                "chunk_id":  f"inc_{doc.get('slug', '')}_{int(time.time())}",
                "slug":      doc.get("slug", ""),
                "title":     doc.get("title", ""),
                "text":      doc.get("text", "")[:800],
                "category":  doc.get("category", "info"),
                "source":    "incremental",
            })

        # Embed
        embeddings = model.encode(
            texts_to_embed,
            normalize_embeddings=True,
            batch_size=8,
            show_progress_bar=False,
        )
        vecs = np.array(embeddings, dtype="float32")

        # Merge vào index
        index.add(vecs)
        chunks.extend(new_chunks)

        # Save
        faiss.write_index(index, str(_INDEX_FILE))
        with open(str(_CHUNKS_FILE), "wb") as f:
            pickle.dump(chunks, f)

        # Reload in-process
        import sys
        if "vector_search" in sys.modules:
            vs = sys.modules["vector_search"]
            vs._index  = index
            vs._chunks = chunks
            logger.info("FAISS index updated in-process: %d total vectors", index.ntotal)

        # Clear buffer
        _buffer = []
        _save_buffer([])
        logger.info("Incremental flush done: +%d vectors", len(new_chunks))

    except Exception:
        logger.exception("Incremental flush failed")


def flush_all():
    """Force flush toàn bộ buffer — gọi từ webhook/updater."""
    with _buffer_lock:
        _flush_buffer()


def buffer_status() -> dict:
    with _buffer_lock:
        return {
            "buffer_size":      len(_buffer),
            "threshold":        BUFFER_THRESHOLD,
            "will_flush_at":    BUFFER_THRESHOLD,
        }


# ── Init: load buffer từ disk khi module import ────────────────────────────────
_buffer = _load_buffer()
if _buffer:
    logger.info("Incremental buffer restored: %d docs pending", len(_buffer))
