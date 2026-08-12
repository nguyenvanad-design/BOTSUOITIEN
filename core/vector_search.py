"""
vector_search.py — Dense vector search cho Suối Tiên bot
Stack: sentence-transformers (BGE-M3) + FAISS
Index được build từ suoitien_clean_v4.json (385 docs)
"""

import json
import os
import pickle
import numpy as np
from pathlib import Path
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────
_BASE = Path(os.environ.get("SUOITIEN_BASE", Path(__file__).parent))
_DATA_PATH   = Path(os.environ.get("SUOITIEN_CLEAN", _BASE / "data" / "suoitien_clean_v4.json"))
_INDEX_DIR   = Path(os.environ.get("SUOITIEN_INDEX", _BASE / "data" / "faiss_index"))
_INDEX_FILE  = _INDEX_DIR / "index.faiss"
_META_FILE   = _INDEX_DIR / "meta.pkl"
_MODEL_NAME  = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

# ── Lazy globals ───────────────────────────────────────────────────────────────
_model  = None
_index  = None
_chunks = None   # list of {text, title, url, category, slug, chunk_id}


def _get_model():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        # Giới hạn thread CPU — tránh 1 encode chiếm hết core (tràn CPU khi nhiều request).
        # Đặt env TORCH_NUM_THREADS=2..4 trên server production.
        n_threads = int(os.environ.get("TORCH_NUM_THREADS", "0") or 0)
        if n_threads > 0:
            torch.set_num_threads(n_threads)
        # Chọn device: env EMBED_DEVICE=cpu|cuda, mặc định auto (cuda nếu có).
        device = os.environ.get("EMBED_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[vector_search] Loading model {_MODEL_NAME} on {device} "
              f"(threads={torch.get_num_threads()})...")
        _model = SentenceTransformer(_MODEL_NAME, device=device)
        print("[vector_search] Model loaded.")
    return _model


def _load_index():
    global _index, _chunks
    if _index is not None:
        return
    import faiss
    if not _INDEX_FILE.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {_INDEX_FILE}. "
            "Run: python vector_search.py --build"
        )
    _index = faiss.read_index(str(_INDEX_FILE))
    with open(_META_FILE, "rb") as f:
        _chunks = pickle.load(f)
    print(f"[vector_search] Index loaded: {_index.ntotal} vectors, {len(_chunks)} chunks")


# ── Build index ────────────────────────────────────────────────────────────────

def _chunk_doc(doc: dict, chunk_size: int = 400, overlap: int = 80) -> list[dict]:
    """Split doc text thành chunks có overlap."""
    text = doc.get("text", "").strip()
    title = doc.get("title", "")
    # Prefix title vào đầu để tăng relevance
    full = f"{title}\n{text}" if title else text
    words = full.split()
    chunks = []
    i = 0
    idx = 0
    while i < len(words):
        chunk_words = words[i: i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunks.append({
            "chunk_id":  f"{doc.get('slug','doc')}_{idx}",
            "slug":      doc.get("slug", ""),
            "title":     title,
            "url":       doc.get("url", ""),
            "category":  doc.get("category", ""),
            "text":      chunk_text,
        })
        i += chunk_size - overlap
        idx += 1
    return chunks


def build_index(force: bool = False):
    """Build FAISS index từ suoitien_clean_v4.json."""
    import faiss

    if _INDEX_FILE.exists() and not force:
        print(f"[vector_search] Index already exists at {_INDEX_FILE}. Use force=True to rebuild.")
        return

    _INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[vector_search] Loading docs from {_DATA_PATH}...")
    with open(_DATA_PATH, encoding="utf-8") as f:
        docs = json.load(f)
    print(f"[vector_search] {len(docs)} docs loaded.")

    # Chunk all docs
    all_chunks = []
    for doc in docs:
        all_chunks.extend(_chunk_doc(doc))
    print(f"[vector_search] {len(all_chunks)} chunks created.")

    # Embed
    model = _get_model()
    texts = [c["text"] for c in all_chunks]
    print(f"[vector_search] Embedding {len(texts)} chunks (this may take a while)...")
    batch_size = 64
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.append(embs)
        if (i // batch_size) % 10 == 0:
            print(f"  {i}/{len(texts)}...")
    embeddings = np.vstack(all_embeddings).astype("float32")
    print(f"[vector_search] Embeddings shape: {embeddings.shape}")

    # Build FAISS index (Inner Product = cosine since normalized)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Save
    faiss.write_index(index, str(_INDEX_FILE))
    with open(_META_FILE, "wb") as f:
        pickle.dump(all_chunks, f)
    print(f"[vector_search] Index saved: {index.ntotal} vectors → {_INDEX_FILE}")


# ── Search ─────────────────────────────────────────────────────────────────────

def vector_search(
    query: str,
    top_k: int = 8,
    category_filter: Optional[str] = None,
    score_threshold: float = 0.3,
) -> list[dict]:
    """
    Dense vector search.
    Returns list of {chunk_id, slug, title, url, category, text, score}
    """
    _load_index()
    model = _get_model()

    q_emb = model.encode([query], normalize_embeddings=True).astype("float32")

    # Search top_k * 3 then filter (để đủ sau khi lọc category)
    fetch_k = top_k * 3 if category_filter else top_k
    scores, indices = _index.search(q_emb, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        if float(score) < score_threshold:
            continue
        chunk = _chunks[idx].copy()
        chunk["score"] = float(score)
        chunk["source"] = "vector"
        if category_filter and chunk.get("category") != category_filter:
            continue
        results.append(chunk)
        if len(results) >= top_k:
            break

    return results


# ── MMR dedup (Maximal Marginal Relevance) ─────────────────────────────────────

def mmr_rerank(
    query: str,
    results: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.6,
) -> list[dict]:
    """
    Rerank results dùng MMR để giảm trùng lặp nội dung.
    lambda_param: 1.0 = pure relevance, 0.0 = pure diversity
    """
    if len(results) <= top_k:
        return results

    model = _get_model()
    texts  = [r["text"] for r in results]
    q_emb  = model.encode([query], normalize_embeddings=True)[0]
    t_embs = model.encode(texts, normalize_embeddings=True)

    selected = []
    remaining = list(range(len(results)))

    while len(selected) < top_k and remaining:
        if not selected:
            # First: pick highest relevance
            scores = [float(np.dot(q_emb, t_embs[i])) for i in remaining]
            best = remaining[int(np.argmax(scores))]
        else:
            best_score = -999
            best = remaining[0]
            for i in remaining:
                rel = float(np.dot(q_emb, t_embs[i]))
                red = max(float(np.dot(t_embs[i], t_embs[j])) for j in selected)
                score = lambda_param * rel - (1 - lambda_param) * red
                if score > best_score:
                    best_score = score
                    best = i
        selected.append(best)
        remaining.remove(best)

    return [results[i] for i in selected]


# ── CLI build ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        force = "--force" in sys.argv
        build_index(force=force)
    else:
        # Quick search test
        os.environ.setdefault("SUOITIEN_BASE", str(Path(__file__).parent))
        print("=== VECTOR SEARCH TEST ===\n")
        queries = [
            "trò chơi cảm giác mạnh cho người lớn",
            "giá vé vào cổng",
            "nhà hàng ẩm thực cung đình",
            "teambuilding cắm trại 2 ngày",
            "vương quốc cá sấu",
        ]
        for q in queries:
            print(f"Query: '{q}'")
            results = vector_search(q, top_k=3)
            for r in results:
                print(f"  [{r['score']:.3f}] [{r['category']}] {r['title'][:50]} — {r['text'][:80]}...")
            print()
