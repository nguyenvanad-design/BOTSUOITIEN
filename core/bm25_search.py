"""
bm25_search.py — BM25 keyword search cho Suối Tiên bot
Stack: rank-bm25
Dùng cho: tên trò chơi cụ thể, tên khu, tên sự kiện, mã vé
"""

import json
import os
import pickle
import re
from pathlib import Path
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────
_BASE      = Path(os.environ.get("SUOITIEN_BASE", Path(__file__).parent))
_DATA_PATH = Path(os.environ.get("SUOITIEN_CLEAN", _BASE / "data" / "suoitien_clean_v4.json"))
_BM25_FILE = Path(os.environ.get("SUOITIEN_INDEX", _BASE / "data" / "faiss_index")) / "bm25.pkl"

# ── Lazy globals ───────────────────────────────────────────────────────────────
_bm25   = None
_chunks = None


# ── Vietnamese tokenizer (simple) ─────────────────────────────────────────────

_STOP_VI = {
    "và", "của", "có", "là", "được", "cho", "với", "trong", "tại", "về",
    "các", "những", "này", "đó", "một", "hai", "ba", "không", "hay",
    "rất", "cũng", "như", "khi", "đến", "từ", "theo", "thì", "nên",
    "bởi", "vì", "nếu", "để", "mà", "còn", "đã", "sẽ", "đang", "lên",
    "xuống", "ra", "vào", "lại", "thêm", "qua", "sau", "trước", "bên",
    "trên", "dưới", "giữa", "ngoài", "trong", "hơn", "nhất", "hết",
}

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    # Giữ số và chữ, bỏ ký tự đặc biệt
    tokens = re.findall(r"[a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ0-9]+", text)
    return [t for t in tokens if t not in _STOP_VI and len(t) > 1]


# ── Build ──────────────────────────────────────────────────────────────────────

def _chunk_doc(doc: dict, chunk_size: int = 300, overlap: int = 60) -> list[dict]:
    text  = doc.get("text", "").strip()
    title = doc.get("title", "")
    full  = f"{title}\n{text}" if title else text
    words = full.split()
    chunks = []
    i = 0
    idx = 0
    while i < len(words):
        chunk_text = " ".join(words[i: i + chunk_size])
        chunks.append({
            "chunk_id": f"{doc.get('slug','doc')}_{idx}",
            "slug":     doc.get("slug", ""),
            "title":    title,
            "url":      doc.get("url", ""),
            "category": doc.get("category", ""),
            "text":     chunk_text,
        })
        i += chunk_size - overlap
        idx += 1
    return chunks


def build_bm25(force: bool = False):
    """Build BM25 index từ suoitien_clean_v4.json."""
    from rank_bm25 import BM25Okapi

    if _BM25_FILE.exists() and not force:
        print(f"[bm25] Index exists at {_BM25_FILE}. Use force=True to rebuild.")
        return

    _BM25_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"[bm25] Loading docs from {_DATA_PATH}...")
    with open(_DATA_PATH, encoding="utf-8") as f:
        docs = json.load(f)

    all_chunks = []
    for doc in docs:
        all_chunks.extend(_chunk_doc(doc))
    print(f"[bm25] {len(all_chunks)} chunks created.")

    tokenized = [_tokenize(c["text"]) for c in all_chunks]
    bm25 = BM25Okapi(tokenized)

    with open(_BM25_FILE, "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": all_chunks}, f)
    print(f"[bm25] Index saved → {_BM25_FILE}")


def _load_bm25():
    global _bm25, _chunks
    if _bm25 is not None:
        return
    if not _BM25_FILE.exists():
        raise FileNotFoundError(
            f"BM25 index not found at {_BM25_FILE}. "
            "Run: python bm25_search.py --build"
        )
    with open(_BM25_FILE, "rb") as f:
        data = pickle.load(f)
    _bm25   = data["bm25"]
    _chunks = data["chunks"]
    print(f"[bm25] Index loaded: {len(_chunks)} chunks")


# ── Search ─────────────────────────────────────────────────────────────────────

def bm25_search(
    query: str,
    top_k: int = 8,
    category_filter: Optional[str] = None,
    score_threshold: float = 0.1,
) -> list[dict]:
    """
    BM25 keyword search.
    Returns list of {chunk_id, slug, title, url, category, text, score}
    """
    _load_bm25()

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = _bm25.get_scores(tokens)

    # Pair (score, idx), sort descending
    pairs = sorted(enumerate(scores), key=lambda x: -x[1])

    results = []
    for idx, score in pairs:
        if score < score_threshold:
            break
        chunk = _chunks[idx].copy()
        chunk["score"] = float(score)
        chunk["source"] = "bm25"
        if category_filter and chunk.get("category") != category_filter:
            continue
        results.append(chunk)
        if len(results) >= top_k:
            break

    return results


# ── Reciprocal Rank Fusion ─────────────────────────────────────────────────────

def rrf_merge(
    ranked_lists: list[list[dict]],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion — merge kết quả từ nhiều retriever.
    ranked_lists: [vector_results, bm25_results, ...]
    k: RRF constant (default 60)
    Returns merged + deduped list sorted by RRF score.
    """
    rrf_scores: dict[str, float] = {}
    chunk_map:  dict[str, dict]  = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            cid = item.get("chunk_id", item.get("slug", str(rank)))
            rrf_scores[cid]  = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            # Keep item with highest original score if seen twice
            if cid not in chunk_map or item.get("score", 0) > chunk_map[cid].get("score", 0):
                chunk_map[cid] = item

    merged = sorted(rrf_scores.items(), key=lambda x: -x[1])
    results = []
    for cid, rrf_score in merged[:top_k]:
        item = chunk_map[cid].copy()
        item["rrf_score"] = rrf_score
        results.append(item)
    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    os.environ.setdefault("SUOITIEN_BASE", str(Path(__file__).parent))

    if "--build" in sys.argv:
        build_bm25(force="--force" in sys.argv)
    else:
        print("=== BM25 SEARCH TEST ===\n")
        queries = [
            "Go Kart đường đua tốc độ",
            "Infinity Slide đường trượt",
            "Cung Đình Tửu nhà hàng",
            "vé cổng người lớn giá",
            "teambuilding cắm trại",
        ]
        for q in queries:
            print(f"Query: '{q}'")
            results = bm25_search(q, top_k=3)
            for r in results:
                print(f"  [{r['score']:.3f}] [{r['category']}] {r['title'][:50]}")
            print()
