"""
schema_search.py — Deterministic schema lookup cho Suối Tiên bot
Query trực tiếp vào suoitien_data_v2.json, không cần LLM.

FIXES v2:
- Chuẩn hóa thrill_level (mixed VI/EN/int → manh/trung_binh/nhe)
- Chuẩn hóa type/zone (mixed EN/VI → chuẩn)
- Filter chiều cao / tuổi tối thiểu
- get_all mode cho câu hỏi tổng hợp
- So sánh: search_attractions_compare()
- Câu hỏi ngoài data: fallback LLM general knowledge
"""

import json
import re
import os
from pathlib import Path
from typing import Optional

# ── Load data ──────────────────────────────────────────────────────────────────
_DATA_PATH = Path(os.environ.get(
    "SUOITIEN_DATA",
    Path(__file__).parent / "data" / "suoitien_data_v2.json"
))

def _load():
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)

_DB: dict = _load()


# ── Normalize helpers ──────────────────────────────────────────────────────────
import unicodedata

def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'Khám Phá' → 'kham pha'."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

def _norm(text: str) -> str:
    return text.lower().strip()

def _match(query: str, text: str) -> bool:
    q = _strip_accents(_norm(query))
    t = _strip_accents(_norm(text))
    return q in t or any(w in t for w in q.split() if len(w) > 2)

def _score(query: str, item: dict, fields: list) -> int:
    # BUG FIX: so khớp trên bản KHÔNG DẤU — khách gõ "kham pha" vẫn match "Khám Phá"
    q_words = [w for w in _strip_accents(_norm(query)).split() if len(w) > 1]
    score = 0
    for field in fields:
        val = item.get(field)
        if not val:
            continue
        text = _strip_accents(_norm(
            str(val) if not isinstance(val, list) else " ".join(str(v) for v in val)
        ))
        for w in q_words:
            if w in text:
                score += 1
    return score

def _format_price(p) -> str:
    if p is None:
        return "liên hệ"
    if p == 0:
        return "miễn phí"
    if p < 1000:
        return f"{p * 1000:,.0f}đ"
    return f"{p:,.0f}đ"


# ── Normalize thrill_level (mixed EN/VI/int → chuẩn) ──────────────────────────
_THRILL_MAP = {
    # VI chuẩn
    "manh": "manh", "trung_binh": "trung_binh", "nhe": "nhe",
    # EN
    "high": "manh", "medium": "trung_binh", "low": "nhe",
    "strong": "manh", "mild": "nhe",
    # VI không chuẩn
    "thấp": "nhe", "trung bình": "trung_binh", "mạnh": "manh",
    # Int (1=nhe, 2=trung_binh, 3=manh)
    "1": "nhe", "2": "trung_binh", "3": "manh",
}

def _norm_thrill(val) -> str:
    if val is None:
        return None
    return _THRILL_MAP.get(str(val).lower().strip(), str(val).lower().strip())


# Normalize type về chuẩn VI
_TYPE_MAP = {
    "tro_choi": "tro_choi", "cong_trinh_van_hoa": "cong_trinh_van_hoa",
    "bieu_dien": "bieu_dien", "khu_tham_quan": "khu_tham_quan",
    "farm": "farm", "tre_em": "tre_em",
    # EN → VI
    "attraction": "tro_choi", "cultural site": "cong_trinh_van_hoa",
    "landmark": "khu_tham_quan", "aquarium": "khu_tham_quan",
    "statue": "cong_trinh_van_hoa", "transportation": "tro_choi",
    "thematic area": "khu_tham_quan", "entrance": "khu_tham_quan",
    # VI không chuẩn
    "nông trại du lịch": "farm", "nông trại - trải nghiệm thiên nhiên": "farm",
    "tượng đài": "cong_trinh_van_hoa", "tượng đài - đền thờ": "cong_trinh_van_hoa",
    "công trình lịch sử": "cong_trinh_van_hoa", "tháp": "cong_trinh_van_hoa",
    "danh lam thắng cảnh": "khu_tham_quan", "quảng trường - đền thờ": "cong_trinh_van_hoa",
    "sân khấu biểu diễn": "bieu_dien", "biểu diễn/lễ hội": "bieu_dien",
    "diễu hành": "bieu_dien", "diễu hành/lễ hội": "bieu_dien",
    "hoạt động thể thao": "tro_choi", "hoạt động": "tro_choi",
    "trải nghiệm văn hóa": "cong_trinh_van_hoa", "ẩm thực": "khu_tham_quan",
    "cổng kiến trúc": "cong_trinh_van_hoa",
}

def _norm_type(val) -> str:
    if val is None:
        return None
    return _TYPE_MAP.get(str(val).lower().strip(), str(val).lower().strip())


# Normalize zone
_ZONE_MAP = {
    "giai_tri": "giai_tri", "khu_giai_tri": "giai_tri",
    "farm": "farm", "van_hoa_tam_linh": "van_hoa_tam_linh",
    "khu_kho": "khu_kho", "khu_tham_quan": "khu_tham_quan",
    "khu_nuoc": "khu_nuoc",
    # EN/không chuẩn
    "main": "giai_tri", "central": "giai_tri", "park": "giai_tri",
    "suối tiên": "giai_tri", "khu chính": "giai_tri",
    "nông trại": "farm",
    "vương quốc các thiên tài tương lai": "giai_tri",
}

def _norm_zone(val) -> str:
    if val is None:
        return None
    return _ZONE_MAP.get(str(val).lower().strip(), str(val).lower().strip())


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def search_tickets(
    query: str = "",
    zone: str = None,
    max_results: int = 5,
    get_all: bool = False,
) -> list[dict]:
    """
    Tìm vé vào cổng.
    get_all=True: trả hết không giới hạn (cho câu hỏi tổng hợp)
    """
    results = []
    for t in _DB["tickets"]:
        if zone and t.get("zone") != zone:
            continue
        score = _score(query, t, ["name", "zone", "valid_for", "notes", "includes"]) if query else 1
        if score > 0 or not query:
            results.append((score, t))
    results.sort(key=lambda x: -x[0])
    if get_all:
        return [r[1] for r in results]
    return [r[1] for r in results[:max_results]]


def get_ticket_price(audience: str = "nguoi_lon") -> dict:
    """Lấy giá vé chuẩn."""
    standard = []
    for t in _DB["tickets"]:
        name = _norm(t.get("name", ""))
        zone = t.get("zone", "")
        if zone in ("khu_kho", "khu_nuoc", "combo") and (
            "người lớn" in name or "trẻ em" in name or "ve cong" in name
        ):
            standard.append(t)

    result = {"adult": None, "child": None, "notes": []}
    for t in standard:
        if t.get("price_adult") and t["price_adult"] > 1000:
            result["adult"] = t["price_adult"]
        if t.get("price_child") and t["price_child"] > 1000:
            result["child"] = t["price_child"]
        if t.get("notes"):
            result["notes"].append(t["notes"])
    return result


def search_attractions(
    query: str = "",
    type_filter: str = None,
    zone_filter: str = None,
    thrill_level: str = None,
    max_height_cm: int = None,      # NEW: trẻ em cao tối đa X cm
    min_height_cm: int = None,      # NEW: yêu cầu chiều cao tối thiểu
    max_age: int = None,            # NEW: độ tuổi tối đa
    min_age: int = None,            # NEW: độ tuổi tối thiểu
    extra_fee: bool = None,         # NEW: True=có phí riêng, False=không
    max_results: int = 8,
    get_all: bool = False,          # NEW: trả hết cho tổng hợp
) -> list[dict]:
    """
    Tìm khu vui chơi / trò chơi / công trình.

    Filter mới:
    - max_height_cm: phù hợp trẻ em cao dưới X cm (không yêu cầu cao hơn)
    - min_height_cm: yêu cầu chiều cao tối thiểu (tìm trò mạnh)
    - max_age / min_age: filter theo tuổi
    - extra_fee: có/không có phí riêng
    - get_all: trả hết tất cả kết quả
    """
    results = []
    for a in _DB["attractions"]:
        # Normalize fields
        a_type   = _norm_type(a.get("type"))
        a_zone   = _norm_zone(a.get("zone"))
        a_thrill = _norm_thrill(a.get("thrill_level"))
        a_height = a.get("height_min_cm")  # cm tối thiểu để chơi
        a_age    = a.get("age_min")

        # Filter type
        if type_filter and a_type != type_filter:
            continue
        # Filter zone
        if zone_filter and a_zone != zone_filter:
            continue
        # Filter thrill_level
        if thrill_level and a_thrill != _norm_thrill(thrill_level):
            continue

        # Filter chiều cao: tìm trò phù hợp trẻ em cao max_height_cm
        # → loại bỏ trò yêu cầu chiều cao cao hơn chiều cao của bé
        if max_height_cm is not None and a_height is not None:
            if a_height > max_height_cm:
                continue

        # Filter chiều cao tối thiểu: trò yêu cầu ít nhất min_height_cm
        if min_height_cm is not None and a_height is not None:
            if a_height < min_height_cm:
                continue

        # Filter tuổi tối đa (tìm trò phù hợp trẻ nhỏ)
        if max_age is not None and a_age is not None:
            if a_age > max_age:
                continue

        # Filter tuổi tối thiểu
        if min_age is not None and a_age is not None:
            if a_age < min_age:
                continue

        # Filter phí riêng
        if extra_fee is True and not a.get("extra_fee"):
            continue
        if extra_fee is False and a.get("extra_fee"):
            continue

        score = _score(query, a, ["name", "description", "highlights", "zone", "type"]) if query else 1
        if score > 0 or not query:
            results.append((score, a))

    results.sort(key=lambda x: -x[0])
    raw = [r[1] for r in results]
    # Dedup tên khi get_all
    if get_all:
        seen = set()
        out = []
        for a in raw:
            key = re.sub(r'[–\-—\s]+', ' ', a.get("name","").lower().strip())
            if key not in seen:
                seen.add(key)
                out.append(a)
        return out
    return raw[:max_results]


def search_attractions_for_child(height_cm: int, age: int = None) -> list[dict]:
    """
    Tìm trò chơi phù hợp với trẻ em theo chiều cao/tuổi.
    Dedup tên gần giống. Sort: nhẹ → trung bình → mạnh.
    """
    results = search_attractions(max_height_cm=height_cm, max_age=age, get_all=True)

    # Dedup theo tên normalize
    seen = set()
    deduped = []
    for a in results:
        key = re.sub(r'[–\-—\s]+', ' ', a.get("name", "").lower().strip())
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    # Sort: trò nhẹ lên đầu cho trẻ em
    _ORDER = {"nhe": 0, "trung_binh": 1, "manh": 2}
    deduped.sort(key=lambda a: _ORDER.get(_norm_thrill(a.get("thrill_level")), 1))
    return deduped


def dedup_attractions(results: list) -> list:
    """Dedup attractions theo tên normalize."""
    seen = set()
    out = []
    for a in results:
        key = re.sub(r'[–\-—\s]+', ' ', a.get("name", "").lower().strip())
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def search_events(
    query: str = "",
    status: str = None,
    event_type: str = None,
    max_results: int = 5,
    get_all: bool = False,
) -> list[dict]:
    """Tìm sự kiện / lễ hội / ưu đãi."""
    results = []
    for e in _DB["events"]:
        if status and e.get("status") != status:
            continue
        if event_type and e.get("type") != event_type:
            continue
        score = _score(query, e, ["name", "description", "highlights", "special_offers"]) if query else 1
        if score > 0 or not query:
            results.append((score, e))
    results.sort(key=lambda x: -x[0])
    if get_all:
        return [r[1] for r in results]
    return [r[1] for r in results[:max_results]]


def search_teambuilding(
    query: str = "",
    tb_type: str = None,
    min_capacity: int = None,
    max_capacity: int = None,
    max_results: int = 5,
    get_all: bool = False,
) -> list[dict]:
    """
    Tìm gói teambuilding / cắm trại / hội nghị.
    min_capacity: lọc gói đủ chỗ cho N người
    """
    results = []
    for p in _DB["teambuilding"]:
        if tb_type and p.get("type") != tb_type:
            continue
        # Filter sức chứa: gói phải chứa được ít nhất min_capacity người
        # Nếu capacity_max=None → không rõ giới hạn → vẫn include
        if min_capacity:
            cap_max = p.get("capacity_max")
            if cap_max is not None and cap_max < min_capacity:
                continue
        if max_capacity:
            cap_min = p.get("capacity_min")
            if cap_min is not None and cap_min > max_capacity:
                continue
        score = _score(query, p, ["name", "type", "includes", "activities"]) if query else 1
        if score > 0 or not query:
            results.append((score, p))
    results.sort(key=lambda x: -x[0])
    if get_all:
        return [r[1] for r in results]
    return [r[1] for r in results[:max_results]]


def search_restaurants(
    query: str = "",
    rest_type: str = None,
    suitable_for: str = None,
    max_results: int = 5,
    get_all: bool = False,
) -> list[dict]:
    """Tìm nhà hàng / khu ẩm thực."""
    results = []
    for r in _DB["restaurant"]:
        if rest_type and r.get("type") != rest_type:
            continue
        if suitable_for and suitable_for not in (r.get("suitable_for") or []):
            continue
        score = _score(query, r, ["name", "cuisine_type", "signature_dishes", "location_in_park"]) if query else 1
        if score > 0 or not query:
            results.append((score, r))
    results.sort(key=lambda x: -x[0])
    if get_all:
        return [r[1] for r in results]
    return [r[1] for r in results[:max_results]]


def search_info(
    query: str = "",
    topic: str = None,
    max_results: int = 3,
    get_all: bool = False,
) -> list[dict]:
    """Tìm thông tin chung: giờ mở cửa, địa chỉ, đường đi, chính sách..."""
    results = []
    for i in _DB["info"]:
        if topic and i.get("topic") != topic:
            continue
        score = _score(query, i, ["title", "content"]) if query else 1
        if score > 0 or not query:
            results.append((score, i))
    results.sort(key=lambda x: -x[0])
    if get_all:
        return [r[1] for r in results]
    return [r[1] for r in results[:max_results]]


def get_contact_info() -> dict:
    """Trả về thông tin liên hệ chuẩn."""
    contacts = search_info(topic="lien_he", max_results=5)
    phones = [i["content"] for i in contacts if re.search(r"19\d{8}|0\d{9}", i["content"])]
    emails = [i["content"] for i in contacts if "@" in i["content"]]
    return {
        "phone":   phones[0] if phones else "1900 636 787",
        "email":   emails[0] if emails else "phongkinhdoanh@suoitien.com",
        "address": "120 Xa Lộ Hà Nội, P. Tăng Nhơn Phú, TP. Thủ Đức, TP.HCM",
    }


def get_opening_hours() -> str:
    """Trả về giờ mở cửa."""
    items = search_info(topic="gio_mo_cua", max_results=1)
    if items:
        return items[0]["content"]
    return "Vui lòng liên hệ 1900 636 787 để biết giờ mở cửa."


# ── UNIFIED ENTRY POINT ────────────────────────────────────────────────────────

def schema_lookup(intent: str, query: str = "", entities: dict = None) -> dict:
    """
    Unified entry point cho retrieval_orchestrator.
    entities có thể chứa: height_cm, age, group_size, thrill_level, get_all
    """
    entities = entities or {}

    # Extract entities
    height_cm   = entities.get("height_cm")
    age         = entities.get("age")
    group_size  = entities.get("group_size")
    thrill      = entities.get("thrill_level")
    get_all     = entities.get("get_all", False)

    # Dispatch theo intent
    if intent in ("hoi_gia_ve", "hoi_ve_cong"):
        results = search_tickets(query, get_all=get_all, max_results=8)

    elif intent == "hoi_tro_choi":
        if height_cm or age:
            # Câu hỏi trẻ em theo chiều cao/tuổi
            results = search_attractions_for_child(
                height_cm=height_cm or 999,
                age=age,
            )
            if not get_all:
                results = results[:8]
        else:
            results = search_attractions(
                query,
                type_filter="tro_choi",
                thrill_level=thrill,
                get_all=get_all,
                max_results=8,
            )

    elif intent == "hoi_khu_vui_choi":
        results = search_attractions(query, get_all=get_all, max_results=10)

    elif intent == "hoi_van_hoa":
        results = search_attractions(query, type_filter="cong_trinh_van_hoa",
                                     get_all=get_all, max_results=8)

    elif intent == "hoi_farm":
        results = search_attractions(query, type_filter="farm",
                                     get_all=get_all, max_results=8)

    elif intent in ("hoi_su_kien", "hoi_uu_dai"):
        et = "uu_dai" if intent == "hoi_uu_dai" else None
        results = search_events(query, event_type=et, get_all=get_all, max_results=6)

    elif intent == "hoi_teambuilding":
        results = search_teambuilding(
            query,
            min_capacity=group_size,
            get_all=get_all,
            max_results=5,
        )

    elif intent == "hoi_nha_hang":
        results = search_restaurants(query, get_all=get_all, max_results=6)

    elif intent == "hoi_dia_chi":
        results = [{"content": get_contact_info()["address"]}]

    elif intent == "hoi_lien_he":
        results = [{"content": str(get_contact_info())}]

    elif intent == "hoi_gio_mo_cua":
        results = [{"content": get_opening_hours()}]

    elif intent in ("hoi_duong_di", "hoi_chinh_sach"):
        topic = "duong_di" if intent == "hoi_duong_di" else "chinh_sach"
        results = search_info(query, topic=topic, get_all=get_all, max_results=3)

    else:  # hoi_chung, unknown
        results = search_info(query, get_all=get_all, max_results=3)

    return {
        "intent":  intent,
        "source":  "schema",
        "count":   len(results),
        "results": results,
    }


# ── QUICK TEST ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== TEST 1: Trẻ 3 tuổi cao 95cm chơi được gì? ===")
    results = search_attractions_for_child(height_cm=95, age=3)
    print(f"Tìm được {len(results)} trò phù hợp:")
    for a in results[:8]:
        h = a.get("height_min_cm", "?")
        print(f"  {a['name'][:40]} | thrill={a.get('thrill_level')} | height_min={h}")

    print("\n=== TEST 2: Teambuilding 50 người ===")
    results = search_teambuilding(min_capacity=50, get_all=True)
    print(f"Tìm được {len(results)} gói:")
    for p in results:
        print(f"  {p['name'][:40]} | {p.get('capacity_min')}-{p.get('capacity_max')} người | {_format_price(p.get('price_per_person'))}/người")

    print("\n=== TEST 3: Tổng hợp tất cả trò chơi cảm giác mạnh ===")
    results = search_attractions(thrill_level="manh", get_all=True)
    print(f"Tổng {len(results)} trò chơi mạnh:")
    for a in results:
        print(f"  {a['name'][:40]} | zone={_norm_zone(a.get('zone'))}")

    print("\n=== TEST 4: Giá vé tổng hợp ===")
    results = search_tickets(get_all=True)
    print(f"Tổng {len(results)} loại vé")
    for t in results[:5]:
        print(f"  {t['name'][:40]} | NL={_format_price(t.get('price_adult'))} | TE={_format_price(t.get('price_child'))}")

    print("\n=== TEST 5: Trò không phí riêng ===")
    results = search_attractions(type_filter="tro_choi", extra_fee=False, max_results=5)
    print(f"Trò chơi không phí riêng:")
    for a in results:
        print(f"  {a['name'][:40]}")
