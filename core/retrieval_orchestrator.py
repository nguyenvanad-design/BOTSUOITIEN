"""
retrieval_orchestrator.py — Orchestrate retrieval pipeline
Strategy giờ đến từ LLM intent_extractor, không cần _STRATEGY map cứng.
"""

import os
import re
from pathlib import Path
from typing import Optional

from schema_search import schema_lookup, _norm_zone
from bm25_search   import bm25_search, rrf_merge
from faq_engine    import faq_match
from language_detector import detect_lang

_vector_search_fn = None

def _get_vector_search():
    global _vector_search_fn
    if _vector_search_fn is None:
        from vector_search import vector_search
        _vector_search_fn = vector_search
    return _vector_search_fn

# Category filter per intent
_CATEGORY_FILTER = {
    "hoi_tro_choi":     "attractions",
    "hoi_khu_vui_choi": "attractions",
    "hoi_van_hoa":      "culture",
    "hoi_farm":         "farm",
    "hoi_su_kien":      "events",
    "hoi_uu_dai":       "events",
    "hoi_teambuilding": "teambuilding",
    "hoi_nha_hang":     "restaurant",
    "hoi_gia_ve":       "tickets",
    "hoi_ve_cong":      "tickets",
}

# ── Intent hỏi về nội dung ĐỘNG ───────────────────────────────────────────────
# Lễ hội, ưu đãi, combo thay đổi liên tục theo chiến dịch marketing. Với nhóm
# này, bảng schema CHẮC CHẮN cũ hơn website: schema chỉ được cập nhật khi crawl
# trích xuất được entity, còn trang web đổi trước.
#
# Hậu quả khi tin schema (13/08/2026): hỏi "Combo Trải Nghiệm giá bao nhiêu?"
# → 220.000đ (bảng vé cũ), trong khi website đang bán 240.000đ. Bot còn tự bịa
# "Combo Trải Nghiệm (tức Combo Tham Quan)" để ghép cho khớp giá cũ.
#
# → Với intent động: KHÔNG cắt chunk web, và đẩy nội dung web LÊN TRƯỚC schema.
_DYNAMIC_INTENTS = {"hoi_su_kien", "hoi_uu_dai"}


def _drop_stale_campaign(chunks: list) -> list:
    """
    Loại chunk RAG là CHIẾN DỊCH ĐÃ QUA.

    Chunk trong FAISS/BM25 không có vòng đời — 47 chunk là "ưu đãi Tết",
    "Friendship Festival 2025", "Vé miễn phí 01/06/2025"... Khi câu hỏi động
    được ưu tiên lấy nội dung web, đúng những chunk cũ này nhảy lên đầu và bot
    quảng cáo "ưu đãi Ngày Phụ nữ" vào giữa tháng 8.

    Chỉ dùng cho câu hỏi ĐỘNG. Câu hỏi tĩnh vẫn cần các chunk này (khách hỏi
    "Tết năm ngoái có gì" thì vẫn nên tra được).
    """
    try:
        from content_lifecycle import year_in_text, holiday_date, _HOLIDAY_GRACE_DAYS
        from datetime import date, timedelta
    except Exception:
        # Không phán định được thì thà không đưa gì vào — xem giải thích ở cuối hàm
        return []

    today = date.today()
    kept = []
    for c in chunks or []:
        title = str(c.get("title", ""))
        text  = str(c.get("text", ""))

        # 1. Năm cũ ngay trong tiêu đề
        yr = year_in_text(title)
        if yr and yr < today.year:
            continue

        # 2. Ngày ĐĂNG BÀI in trong thân bài. Chunk "MỪNG NGÀY PHỤ NỮ VIỆT NAM"
        #    không có năm ở tiêu đề, năm 2024 nằm trong nội dung ("02/10/2024")
        #    → lọc theo tiêu đề thôi là lọt.
        pub = _publish_date(title, text)
        if pub and pub.year < today.year:
            continue

        # 3. Ngày lễ đã qua trong năm nay
        hd = holiday_date(title, today.year)
        if hd and today > hd + timedelta(days=_HOLIDAY_GRACE_DAYS):
            continue

        kept.append(c)

    if not kept:
        # TRẢ RỖNG, KHÔNG trả nguyên bản.
        #
        # Trước đây ở đây fallback về `chunks` với lý lẽ "còn hơn không có gì".
        # Lý lẽ đó SAI với câu hỏi ưu đãi: `chunks` lúc này chính là đống khuyến
        # mãi hết hạn vừa lọc ra, nên fallback = quảng cáo ưu đãi Tết vào tháng 8.
        # Khách tới nơi mới biết là mất uy tín; im lặng rồi mời gọi hotline thì
        # không. Responder đã có luật xử lý khi thiếu dữ liệu.
        return []

    # "Web mới nhất thắng" — bài mới đứng trước. Chunk không đọc được ngày giữ
    # nguyên thứ hạng liên quan (sort ổn định), chỉ xếp sau bài có ngày mới.
    kept.sort(key=lambda c: _publish_date(str(c.get("title", "")),
                                          str(c.get("text", ""))) or date.min,
              reverse=True)
    return kept


_RE_PUB_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b")


def _publish_date(title: str, text: str):
    """Ngày đăng bài — crawler giữ nguyên dòng ngày tháng của website."""
    from datetime import date as _d
    m = _RE_PUB_DATE.search(f"{title} {text[:400]}")
    if not m:
        return None
    try:
        return _d(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _is_dynamic_intent(intent: str, query: str = "") -> bool:
    if intent in _DYNAMIC_INTENTS:
        return True
    return bool(re.search(
        r"(combo|ưu đãi|uu dai|khuyến mãi|khuyen mai|giảm giá|giam gia|"
        r"đang áp dụng|dang ap dung|sự kiện|su kien|lễ hội|le hoi|"
        r"hiện tại|hien tai|đang có|dang co|tháng này|thang nay)",
        query or "", re.IGNORECASE))


# Default strategy nếu extractor không trả về
_DEFAULT_STRATEGY = {
    "hoi_gia_ve":       ["faq", "schema", "bm25"],
    "hoi_ve_cong":      ["faq", "schema", "bm25"],
    "hoi_gio_mo_cua":   ["faq", "schema"],
    "hoi_dia_chi":      ["faq", "schema"],
    "hoi_lien_he":      ["faq", "schema"],
    "hoi_duong_di":     ["faq", "schema", "vector"],
    "hoi_chinh_sach":   ["schema"],
    "hoi_tro_choi":     ["faq", "schema", "bm25", "vector"],
    "hoi_khu_vui_choi": ["faq", "schema", "bm25", "vector"],
    "hoi_van_hoa":      ["schema", "bm25", "vector"],
    "hoi_farm":         ["faq", "schema", "bm25", "vector"],
    "hoi_su_kien":      ["schema", "bm25", "vector"],
    "hoi_uu_dai":       ["schema", "bm25", "vector"],
    "hoi_teambuilding": ["faq", "schema", "bm25", "vector"],
    "hoi_nha_hang":     ["schema", "bm25", "vector"],
    "hoi_chung":        ["faq", "bm25", "vector"],
    "unknown":          ["faq", "bm25", "vector"],
}


# Tách RAG operational vs blog/SEO: loại chunk nói về công viên ĐỐI THỦ hoặc
# bài listicle SEO — tránh trộn thông tin ngoài Suối Tiên vào câu tư vấn.
_BLOG_SIGNALS = (
    "thảo cầm viên", "đầm sen", "vinpearl", "đại nam", "grand world",
    "top 10", "top 5", "top các", "so sánh với", "review chi tiết",
    "những công viên", "các khu du lịch nổi tiếng",
)


def _is_blog(chunk: dict) -> bool:
    if chunk.get("category") == "blog_seo":
        return True
    t = (chunk.get("title", "") + " " + chunk.get("text", "")[:200]).lower()
    return any(sig in t for sig in _BLOG_SIGNALS)


def _drop_blog(chunks: list) -> list:
    """Bỏ chunk blog/SEO. Nếu bỏ hết thì giữ nguyên (tránh trả rỗng)."""
    clean = [c for c in chunks if not _is_blog(c)]
    return clean if clean else chunks


def retrieve(
    query: str,
    intent: str = "unknown",
    entities: dict = None,
    strategy: list = None,      # ← từ LLM extractor
    top_k: int = 5,
    use_vector: bool = True,
) -> dict:
    """
    Unified retrieval.
    strategy ưu tiên từ LLM extractor, fallback về _DEFAULT_STRATEGY.
    """
    entities = entities or {}
    # Dùng strategy từ LLM nếu có, không thì dùng default
    strategy = strategy or _DEFAULT_STRATEGY.get(intent, ["faq", "bm25", "vector"])
    cat_filter = _CATEGORY_FILTER.get(intent)

    # ── Step 1: FAQ fast path ──────────────────────────────────────────────────
    lang = detect_lang(query)
    if "faq" in strategy:
        faq = faq_match(query, lang=lang)
        if faq:
            return {
                "source": "faq",
                "answer": faq["answer"],
                "results": [],
                "intent": intent,
                "strategy": strategy,
            }

    # ── Step 2: Schema lookup ──────────────────────────────────────────────────
    schema_results = []
    if "schema" in strategy:
        out = schema_lookup(intent, query, entities)
        schema_results = out.get("results", [])

    # ── Step 3: BM25 ──────────────────────────────────────────────────────────
    bm25_results = []
    if "bm25" in strategy:
        bm25_results = _drop_blog(bm25_search(query, top_k=top_k * 2, category_filter=cat_filter))

    # ── Step 4: Vector ─────────────────────────────────────────────────────────
    vector_results = []
    if "vector" in strategy and use_vector:
        try:
            vs = _get_vector_search()
            vector_results = _drop_blog(vs(query, top_k=top_k * 2, category_filter=cat_filter))
        except FileNotFoundError:
            pass

    # ── Step 5: Merge ──────────────────────────────────────────────────────────
    dynamic = _is_dynamic_intent(intent, query)
    if dynamic:
        bm25_results   = _drop_stale_campaign(bm25_results)
        vector_results = _drop_stale_campaign(vector_results)

    if schema_results and len(schema_results) >= 2 and not dynamic:
        text_chunks = rrf_merge([bm25_results, vector_results], top_k=3) if (bm25_results or vector_results) else []
        return {
            "source": "schema",
            "answer": None,
            "results": schema_results[:top_k],
            "chunks": text_chunks,
            "intent": intent,
            "strategy": strategy,
        }

    lists_to_merge = [l for l in [bm25_results, vector_results] if l]
    merged = rrf_merge(lists_to_merge, top_k=top_k) if lists_to_merge else []
    final  = schema_results + merged if schema_results else merged

    return {
        "source": "hybrid" if merged else ("schema" if schema_results else "fallback"),
        "answer": None,
        "results": final[:top_k],
        "chunks": merged[:top_k],
        "intent": intent,
        "strategy": strategy,
        "dynamic": dynamic,
    }


def build_context(retrieval_out: dict, max_chars: int = 3000) -> str:
    source  = retrieval_out.get("source")
    results = retrieval_out.get("results", [])
    chunks  = retrieval_out.get("chunks", [])
    intent  = retrieval_out.get("intent", "")

    if source == "faq":
        return retrieval_out.get("answer", "")

    lines = []
    total = 0
    dynamic = retrieval_out.get("dynamic", False)

    # Câu hỏi ĐỘNG (combo/ưu đãi/sự kiện): nội dung web mới nhất đứng TRƯỚC và
    # được tuyên bố là nguồn ưu tiên. Bảng schema chỉ còn vai trò tham khảo, vì
    # nó luôn chậm hơn website — nơi Suối Tiên đổi khuyến mãi liên tục.
    if dynamic and chunks:
        lines.append("=== TIN MỚI NHẤT TỪ WEBSITE SUỐI TIÊN (ƯU TIÊN DÙNG) ===")
        for c in chunks[:3]:
            entry = f"[{c.get('title', '')}]\n{c.get('text', '')[:600]}"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)
        if results:
            lines.append("\n=== DỮ LIỆU NỀN (có thể cũ hơn website) ===")
            for item in results[:3]:
                s = _fmt(item)
                if total + len(s) > max_chars:
                    break
                lines.append(s)
                total += len(s)
        return "\n\n".join(lines) if lines else ""

    if results and source == "schema":
        lines.append("=== THÔNG TIN TỪ DATABASE ===")
        for item in results:
            s = _fmt(item)
            if total + len(s) > max_chars:
                break
            lines.append(s)
            total += len(s)

        # BUG FIX: nếu schema đã có đủ kết quả, KHÔNG đưa BM25/vector chunks vào.
        # Trước đây chunks (có thể là bài blog teambuilding) bị chèn vào context
        # ngay cả khi database đã trả đúng trò chơi → LLM2 bị nhiễu, trả lời nhầm.
        # Chỉ bổ sung chunks khi schema thiếu (< 2 kết quả).
        # LƯU Ý: luật này CHỈ đúng cho câu hỏi TĨNH — nhánh dynamic ở trên đã
        # xử lý riêng, vì với ưu đãi thì bỏ web đi chính là bỏ mất tin mới.
        if len(results) >= 2:
            return "\n\n".join(lines) if lines else ""

    # Schema không đủ hoặc source != schema → dùng BM25/vector chunks
    # Nhưng phải có label rõ ràng để LLM2 biết đây là "tham khảo", không phải data chính
    chunk_list = chunks if chunks else (results if source != "schema" else [])
    if chunk_list:
        lines.append("\n=== NỘI DUNG THAM KHẢO (web/blog) ===")
        for c in chunk_list:
            cat = c.get("category", "")
            # Lọc hard: KHÔNG đưa bài blog teambuilding/general vào context
            # khi intent là tìm trò chơi/khu vui chơi
            if intent in ("hoi_tro_choi", "hoi_khu_vui_choi") and cat in (
                "teambuilding", "general", "blog", "tin_tuc"
            ):
                continue
            entry = f"[{c.get('title', '')}]\n{c.get('text', '')[:400]}"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)

    return "\n\n".join(lines) if lines else ""


# Nhãn khu vực dễ đọc (key = giá trị zone đã chuẩn hóa qua _norm_zone)
_ZONE_LABEL = {
    "giai_tri":         "Khu Giải Trí",
    "farm":             "Khu Nông Trại (Farm)",
    "van_hoa_tam_linh": "Khu Văn Hóa Tâm Linh",
    "khu_kho":          "Khu Khô",
    "khu_nuoc":         "Khu Nước",
    "khu_tham_quan":    "Khu Tham Quan",
}


def _fmt(item: dict) -> str:
    if "ticket_id" in item or "price_adult" in item:
        parts = [f"Vé: {item.get('name','')}"]
        if item.get("price_adult"): parts.append(f"NL: {item['price_adult']:,.0f}đ")
        if item.get("price_child") is not None:
            p = item["price_child"]
            parts.append(f"TE: {'miễn phí' if p==0 else f'{p:,.0f}đ'}")
        if item.get("includes"): parts.append(f"Gồm: {', '.join(item['includes'][:3])}")
        if item.get("notes"):    parts.append(f"LN: {item['notes'][:80]}")
        return " | ".join(parts)

    if "attraction_id" in item:
        parts = [f"Điểm tham quan: {item.get('name','')}"]
        zone_label = _ZONE_LABEL.get(_norm_zone(item.get("zone")))
        if zone_label:               parts.append(f"Khu vực: {zone_label}")
        if item.get("description"):  parts.append(item["description"][:150])
        if item.get("highlights"):   parts.append(f"Nổi bật: {', '.join(item['highlights'][:3])}")
        if item.get("extra_fee"):    parts.append("Phí riêng: có")
        return "\n".join(parts)

    if "event_id" in item:
        parts = [f"Sự kiện: {item.get('name','')}"]
        if item.get("date_start"):   parts.append(f"Thời gian: {item['date_start']}")
        if item.get("description"):  parts.append(item["description"][:150])
        if item.get("special_offers"): parts.append(f"Ưu đãi: {', '.join(item['special_offers'][:3])}")
        return "\n".join(parts)

    if "package_id" in item:
        parts = [f"Gói: {item.get('name','')}"]
        if item.get("duration"):          parts.append(f"TG: {item['duration']}")
        if item.get("price_per_person"):  parts.append(f"Giá/người: {item['price_per_person']:,.0f}đ")
        if item.get("includes"):          parts.append(f"Gồm: {', '.join(item['includes'][:3])}")
        return " | ".join(parts)

    if "restaurant_id" in item:
        parts = [f"Nhà hàng: {item.get('name','')}"]
        if item.get("cuisine_type"):     parts.append(f"Ẩm thực: {item['cuisine_type']}")
        if item.get("signature_dishes"): parts.append(f"Món: {', '.join(item['signature_dishes'][:3])}")
        return " | ".join(parts)

    return f"{item.get('title','')}: {item.get('content','')[:300]}"


if __name__ == "__main__":
    import os
    os.environ.setdefault("SUOITIEN_BASE", str(Path(__file__).parent))
    os.environ.setdefault("SUOITIEN_DATA",  str(Path(__file__).parent / "data" / "suoitien_data_v2.json"))
    os.environ.setdefault("SUOITIEN_CLEAN", str(Path(__file__).parent / "data" / "suoitien_clean_v4.json"))

    tests = [
        ("Suối Tiên ở đâu?",         "hoi_dia_chi",     ["faq"]),
        ("Giá vé bao nhiêu?",        "hoi_gia_ve",      ["faq","schema"]),
        ("Go Kart ở khu nào?",       "hoi_tro_choi",    ["bm25","vector"]),
        ("Nhà hàng nào ngon?",       "hoi_nha_hang",    ["schema","bm25","vector"]),
        ("Teambuilding 50 người",    "hoi_teambuilding",["faq","schema","bm25","vector"]),
    ]
    print("=== ORCHESTRATOR (LLM Router) TEST ===\n")
    for query, intent, strategy in tests:
        out = retrieve(query, intent=intent, strategy=strategy, use_vector=False)
        ctx = build_context(out)
        print(f"Q: {query}")
        print(f"   source={out['source']} | results={len(out['results'])} | strategy={out['strategy']}")
        print(f"   ctx: {ctx[:120].replace(chr(10),' ')}")
        print()
