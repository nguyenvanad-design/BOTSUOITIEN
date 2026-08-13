"""
build_faiss.py — Build FAISS index cho Suối Tiên bot từ suoitien_data_v2.json
Chạy 1 lần: python build_faiss.py
Output: data/faiss_index/index.faiss + meta.pkl
"""

import json
import os
import pickle
import time
import numpy as np
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent
DATA_PATH  = Path(os.environ.get("SUOITIEN_DATA",  BASE / "data" / "suoitien_data_v2.json"))
INDEX_DIR  = Path(os.environ.get("SUOITIEN_INDEX", BASE / "data" / "faiss_index"))
MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")


# ── Convert entities → flat text chunks ────────────────────────────────────────
def build_chunks(data: dict) -> list[dict]:
    chunks = []

    def active(item: dict, bucket: str) -> bool:
        if item.get("is_active") is False:
            return False
        try:
            from content_lifecycle import is_current
            return is_current(item, bucket)
        except Exception:
            return True

    def text_list(value) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("name") or item.get("description")
                if text:
                    out.append(str(text))
        return out

    def add(chunk_id, category, title, text):
        if not text.strip():
            return
        chunks.append({
            "chunk_id": chunk_id,
            "category": category,
            "title":    title,
            "text":     f"{title}\n{text}".strip(),
        })

    # Tickets
    for t in data.get("tickets", []):
        if not active(t, "tickets"):
            continue
        parts = []
        if t.get("price_adult"):
            parts.append(f"Giá người lớn: {t['price_adult']:,.0f}đ")
        if t.get("price_child") is not None:
            p = t["price_child"]
            parts.append(f"Giá trẻ em: {'miễn phí' if p == 0 else f'{p:,.0f}đ'}")
        if t.get("price_senior") is not None:
            p = t["price_senior"]
            parts.append(f"Giá người cao tuổi: {'miễn phí' if p == 0 else f'{p:,.0f}đ'}")
        if t.get("zone"):
            parts.append(f"Khu: {t['zone']}")
        if t.get("height_restriction"):
            parts.append(f"Chiều cao: {t['height_restriction']}")
        if t.get("includes"):
            parts.append(f"Bao gồm: {', '.join(t['includes'])}")
        if t.get("valid_for"):
            parts.append(f"Áp dụng: {t['valid_for']}")
        if t.get("notes"):
            parts.append(f"Ghi chú: {t['notes']}")
        add(t["ticket_id"], "tickets", t.get("name", "Vé"), ". ".join(parts))

    # Attractions
    for a in data.get("attractions", []):
        if not active(a, "attractions"):
            continue
        parts = []
        if a.get("description"):
            parts.append(a["description"])
        if a.get("zone"):
            parts.append(f"Khu: {a['zone']}")
        if a.get("type"):
            parts.append(f"Loại: {a['type']}")
        if a.get("thrill_level"):
            parts.append(f"Độ mạo hiểm: {a['thrill_level']}")
        if a.get("age_min"):
            parts.append(f"Tuổi tối thiểu: {a['age_min']}")
        if a.get("height_min_cm"):
            parts.append(f"Chiều cao tối thiểu: {a['height_min_cm']}cm")
        if a.get("duration_minutes"):
            parts.append(f"Thời gian: {a['duration_minutes']} phút")
        if a.get("highlights"):
            parts.append(f"Nổi bật: {', '.join(a['highlights'][:5])}")
        if a.get("extra_fee"):
            amt = a.get("extra_fee_amount", "có phí riêng")
            parts.append(f"Phí riêng: {amt}")
        add(a["attraction_id"], "attractions",
            a.get("name", "Điểm tham quan"), ". ".join(parts))

    # Events
    for e in data.get("events", []):
        if not active(e, "events"):
            continue
        parts = []
        if e.get("description"):
            parts.append(e["description"])
        if e.get("type"):
            parts.append(f"Loại: {e['type']}")
        if e.get("status"):
            parts.append(f"Trạng thái: {e['status']}")
        if e.get("date_start"):
            parts.append(f"Từ: {e['date_start']}")
        if e.get("date_end"):
            parts.append(f"Đến: {e['date_end']}")
        if e.get("target_audience"):
            parts.append(f"Đối tượng: {', '.join(text_list(e['target_audience'])[:3])}")
        if e.get("special_offers"):
            try:
                from schema_search import _active_special_offers
                offers = _active_special_offers(e)
            except Exception:
                offers = text_list(e["special_offers"])
            if offers:
                parts.append(f"Ưu đãi: {', '.join(offers[:5])}")
        if e.get("highlights"):
            parts.append(f"Nổi bật: {', '.join(e['highlights'][:5])}")
        add(e["event_id"], "events", e.get("name", "Sự kiện"), ". ".join(parts))

    # Teambuilding
    for tb in data.get("teambuilding", []):
        if not active(tb, "teambuilding"):
            continue
        parts = []
        if tb.get("type"):
            parts.append(f"Loại: {tb['type']}")
        if tb.get("duration"):
            parts.append(f"Thời gian: {tb['duration']}")
        mn = tb.get("capacity_min")
        mx = tb.get("capacity_max")
        if mn or mx:
            parts.append(f"Sức chứa: {mn or '?'}-{mx or '?'} người")
        if tb.get("price_per_person"):
            parts.append(f"Giá/người: {tb['price_per_person']:,.0f}đ")
        if tb.get("price_package"):
            parts.append(f"Giá gói: {tb['price_package']:,.0f}đ")
        if tb.get("includes"):
            parts.append(f"Bao gồm: {', '.join(tb['includes'][:5])}")
        if tb.get("activities"):
            parts.append(f"Hoạt động: {', '.join(tb['activities'][:5])}")
        if tb.get("contact"):
            parts.append(f"Liên hệ: {tb['contact']}")
        add(tb["package_id"], "teambuilding",
            tb.get("name", "Gói teambuilding"), ". ".join(parts))

    # Restaurant
    for r in data.get("restaurant", []):
        if not active(r, "restaurant"):
            continue
        parts = []
        if r.get("cuisine_type"):
            parts.append(f"Ẩm thực: {r['cuisine_type']}")
        if r.get("location_in_park"):
            parts.append(f"Vị trí: {r['location_in_park']}")
        if r.get("price_range"):
            parts.append(f"Giá: {r['price_range']}")
        if r.get("signature_dishes"):
            parts.append(f"Món đặc trưng: {', '.join(r['signature_dishes'][:5])}")
        if r.get("capacity_pax"):
            parts.append(f"Sức chứa: {r['capacity_pax']} khách")
        if r.get("suitable_for"):
            parts.append(f"Phù hợp: {', '.join(r['suitable_for'][:3])}")
        if r.get("opening_hours"):
            parts.append(f"Giờ mở: {r['opening_hours']}")
        if r.get("booking_required"):
            parts.append("Cần đặt bàn trước")
        add(r["restaurant_id"], "restaurant",
            r.get("name", "Nhà hàng"), ". ".join(parts))

    # Info
    for info in data.get("info", []):
        if not active(info, "info"):
            continue
        add(info["info_id"], "info",
            info.get("title", "Thông tin"),
            info.get("content", ""))

    return chunks


# ── Main build ─────────────────────────────────────────────────────────────────
def main(force: bool = False):
    import faiss
    from sentence_transformers import SentenceTransformer

    index_file = INDEX_DIR / "index.faiss"
    meta_file  = INDEX_DIR / "meta.pkl"

    if index_file.exists() and not force:
        print(f"[build_faiss] Index đã tồn tại tại {index_file}")
        print("[build_faiss] Dùng --force để rebuild.")
        return

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"[build_faiss] Loading {DATA_PATH}...")
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # Build chunks
    chunks = build_chunks(data)
    print(f"[build_faiss] {len(chunks)} chunks | breakdown: "
          + " | ".join(f"{c}={sum(1 for x in chunks if x['category']==c)}"
                       for c in ["tickets","attractions","events","teambuilding","restaurant","info"]))

    # Load model
    print(f"[build_faiss] Loading model {MODEL_NAME}...")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME)
    print(f"[build_faiss] Model loaded ({time.time()-t0:.1f}s)")

    # Embed
    texts = [c["text"] for c in chunks]
    print(f"[build_faiss] Embedding {len(texts)} chunks...")
    t1 = time.time()
    all_embs = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embs.append(embs)
        print(f"  {min(i+batch_size, len(texts))}/{len(texts)}", end="\r")

    embeddings = np.vstack(all_embs).astype("float32")
    print(f"\n[build_faiss] Embedding done ({time.time()-t1:.1f}s) | shape={embeddings.shape}")

    # Build index
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    print(f"[build_faiss] FAISS index: {index.ntotal} vectors, dim={dim}")

    # Save
    faiss.write_index(index, str(index_file))
    with open(meta_file, "wb") as f:
        pickle.dump(chunks, f)

    idx_kb  = index_file.stat().st_size / 1024
    meta_kb = meta_file.stat().st_size / 1024
    print(f"\n[build_faiss] ✅ DONE")
    print(f"  index.faiss : {idx_kb:.0f} KB  → {index_file}")
    print(f"  meta.pkl    : {meta_kb:.0f} KB  → {meta_file}")

    # Quick search test
    print("\n[build_faiss] Quick search test:")
    test_queries = [
        "trò chơi cảm giác mạnh",
        "giá vé vào cổng",
        "nhà hàng ngon",
        "teambuilding 50 người",
        "thời tiết đi chơi",
    ]
    for q in test_queries:
        q_emb = model.encode([q], normalize_embeddings=True).astype("float32")
        scores, indices = index.search(q_emb, 3)
        print(f"\n  Q: '{q}'")
        for score, idx in zip(scores[0], indices[0]):
            c = chunks[idx]
            print(f"    [{score:.3f}] [{c['category']:12}] {c['title'][:50]}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    main(force=force)
