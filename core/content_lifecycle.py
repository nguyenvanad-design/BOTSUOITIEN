"""
content_lifecycle.py — Vòng đời nội dung TĨNH vs ĐỘNG cho Suối Tiên bot.

BỐI CẢNH
--------
Lễ hội, ngày lễ, combo, khuyến mãi là dữ liệu ĐỘNG — Suối Tiên đổi liên tục để
hút khách. Pipeline crawl cũ chỉ biết THÊM, không bao giờ biết BỎ, nên data tích
tụ từ 2023 tới nay: 151 sự kiện, 79/80 sự kiện "đang bật" không có ngày kết thúc.
Hậu quả thật (13/08/2026): hỏi "hiện tại có sự kiện gì" → bot trả "Giỗ Tổ Hùng
Vương" (tháng 4).

NGUYÊN TẮC — ĐẢO NGƯỢC MẶC ĐỊNH
-------------------------------
Cũ : nội dung mặc định CÒN hiệu lực, trừ khi bị đánh dấu hết hạn.
Mới: nội dung ĐỘNG mặc định KHÔNG được coi là "đang áp dụng", trừ khi chứng minh
     được còn hạn. "Không biết ngày kết thúc" = "không dám khẳng định", chứ
     không phải "còn mãi mãi".

Nội dung TĨNH (địa chỉ, giờ, giá niêm yết, trò chơi, nhà hàng) KHÔNG áp dụng
luật này — chúng không có hạn dùng.

CHUỖI SUY LUẬN HẠN DÙNG (dừng ở tín hiệu đầu tiên tìm được)
-----------------------------------------------------------
1. date_end / valid_to ghi rõ        → dùng luôn
2. Năm trong tên/slug < năm nay      → hết hạn ("Tết Xuyên Không 2025")
3. Sự kiện gắn NGÀY LỄ đã qua        → hết hạn ("Giỗ Tổ" hỏi vào tháng 8)
4. date_start + TTL                  → hết hạn nếu quá TTL
5. crawled_at + TTL                  → hết hạn nếu quá TTL
6. Không còn tín hiệu nào            → UNDATED: vẫn cho hiện nhưng responder
                                       phải nói rõ "vui lòng xác nhận lại"

TTL mặc định 45 ngày — khớp nhịp marketing theo mùa/tháng của Suối Tiên.
"""

import re
import os
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TTL_DAYS = int(os.getenv("SUOITIEN_DYNAMIC_TTL_DAYS", "45"))

# Trạng thái trả về
CURRENT = "current"    # còn hiệu lực — được nói là "đang áp dụng"
EXPIRED = "expired"    # hết hạn — không được trả cho khách
UNDATED = "undated"    # không xác định được — hiện nhưng phải hedge
STATIC  = "static"     # không có vòng đời

# Bucket luôn là nội dung động
_DYNAMIC_BUCKETS = {"events"}

# Slug/tên cho thấy đây là khuyến mãi có thời hạn, kể cả nằm trong bucket tĩnh
_PROMO_SIGNAL = re.compile(
    r"(uu-dai|ưu đãi|khuyen-mai|khuyến mãi|giam-gia|giảm giá|deal|"
    r"tang-|tặng |mung-|mừng |sinh-nhat|sinh nhật|combo|le-hoi|lễ hội|"
    r"tet-|tết |mua-thu|mùa thu|mua-he|mùa hè|flash|sale)",
    re.IGNORECASE)

# Ngày lễ cố định (tháng, ngày) — sự kiện gắn với lễ đã qua thì hết hiệu lực.
# Lễ âm lịch lấy tháng dương gần đúng, đủ để phân biệt "đã qua hẳn hay chưa".
_HOLIDAY_DATE = {
    "tết nguyên đán": (2, 10), "tết ": (2, 10), "tet ": (2, 10),
    "xuân": (2, 10), "giao thừa": (2, 10),
    "giỗ tổ": (4, 18), "gio to": (4, 18), "hùng vương": (4, 18),
    "30/4": (4, 30), "giải phóng": (4, 30),
    "1/5": (5, 1), "quốc tế lao động": (5, 1),
    "1/6": (6, 1), "quốc tế thiếu nhi": (6, 1), "thiếu nhi": (6, 1),
    "vu lan": (8, 25),
    "8/3": (3, 8), "quốc tế phụ nữ": (3, 8),
    "valentine": (2, 14), "14/2": (2, 14),
    "20/10": (10, 20), "phụ nữ việt nam": (10, 20), "phu nu viet nam": (10, 20),
    "20/11": (11, 20), "nhà giáo": (11, 20), "nha giao": (11, 20),
    "quốc khánh": (9, 2), "quoc khanh": (9, 2), "2/9": (9, 2),
    "trung thu": (9, 20), "trăng": (9, 20),
    "halloween": (10, 31),
    "giáng sinh": (12, 24), "giang sinh": (12, 24), "noel": (12, 24),
    "christmas": (12, 24),
    "tất niên": (12, 31), "năm mới": (1, 1), "new year": (1, 1),
}

# Sau khi lễ qua bao nhiêu ngày thì chắc chắn coi là hết
_HOLIDAY_GRACE_DAYS = 14


# ── Tiện ích ──────────────────────────────────────────────────────────────────
def parse_date(v, strict: bool = False) -> Optional[date]:
    """
    Đọc ngày từ nhiều định dạng lẫn lộn trong data:
    '2026-04-26', '22/04/2026', '26/4/2026', '2026-06-02T16:34:45.754660'

    strict=True: giá trị có vẻ là ngày nhưng KHÔNG hợp lệ thì ném ValueError
    thay vì trả None. Dùng lúc NẠP dữ liệu để bắt lỗi ngay tại nguồn.

    Data thật đang chứa `2026-02-29` (2026 không nhuận) và `"2008"` (chỉ có
    năm). Trả None âm thầm nghĩa là bản ghi trượt hết mọi luật hạn dùng và
    sống mãi — sai sót ở khâu nhập liệu biến thành sự kiện không bao giờ hết hạn.
    """
    if not v:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s or s.lower() in ("none", "null", "n/a", ""):
        return None

    def _fail(msg: str):
        if strict:
            raise ValueError(f"Ngày không hợp lệ: {v!r} — {msg}")
        return None

    # ISO (có thể kèm giờ)
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return _fail("ngày/tháng không tồn tại (vd 29/02 năm không nhuận)")
    # DD/MM/YYYY hoặc D/M/YYYY
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return _fail("ngày/tháng không tồn tại")
    # Chỉ có năm ("2008") — không đủ để tính hạn dùng
    if re.fullmatch(r"(19|20)\d\d", s):
        return _fail("chỉ có năm, thiếu ngày/tháng")
    return _fail("không nhận dạng được định dạng")


def normalize_dates(record: dict, on_error=None) -> list:
    """
    Chuẩn hoá mọi trường ngày của 1 bản ghi về ISO. Trả danh sách lỗi tìm được.
    Giá trị hỏng bị XOÁ khỏi record để không giả vờ là dữ liệu hợp lệ.
    """
    errors = []
    for field in ("date_start", "date_end", "valid_from", "valid_to"):
        raw = record.get(field)
        if raw in (None, ""):
            continue
        try:
            d = parse_date(raw, strict=True)
        except ValueError as e:
            errors.append(f"{field}={raw!r}: {e}")
            record.pop(field, None)
            if on_error:
                on_error(record, field, raw, str(e))
            continue
        if d:
            record[field] = d.isoformat()
    return errors


def year_in_text(*texts) -> Optional[int]:
    """Năm gần nhất tìm thấy trong tên/slug — '...2025' là dấu hiệu mạnh."""
    years = []
    for t in texts:
        if not t:
            continue
        years += [int(y) for y in re.findall(r"\b(20\d\d)\b", str(t))]
    return max(years) if years else None


def holiday_date(text: str, year: int) -> Optional[date]:
    """Ngày dương gần đúng của lễ được nhắc trong text, theo năm cho trước."""
    if not text:
        return None
    low = str(text).lower()
    for kw, (mo, da) in _HOLIDAY_DATE.items():
        if kw in low:
            try:
                return date(year, mo, da)
            except ValueError:
                return None
    return None


def _is_campaign(name: str, slug: str = "") -> bool:
    """
    Đây có phải chiến dịch có thời hạn (lễ hội, ưu đãi, combo mùa) không?
    Chỉ chiến dịch mới bị TTL. Nội dung thường trực nằm nhầm trong bucket
    events (trò chơi, show, món ăn) phải được giữ nguyên.

    CHỈ XÉT TÊN, KHÔNG XÉT SLUG. Trò "Go Kart" được nhắc trong bài
    "san-combo-suoi-tien-2026" nên slug chứa "combo"; xét slug thì Go Kart bị
    coi là chiến dịch khuyến mãi và hết hạn sau 45 ngày. Slug là bài viết
    NGUỒN, không phải danh tính của bản ghi. Tham số slug giữ lại cho tương
    thích chữ ký hàm, cố ý không dùng.
    """
    if _PROMO_SIGNAL.search(name or ""):
        return True
    if year_in_text(name):
        return True
    return holiday_date(name or "", 2000) is not None


def is_dynamic(record: dict, bucket: str) -> bool:
    """
    Bản ghi này có vòng đời (động) hay là thông tin nền (tĩnh)?

    CẢNH BÁO — KHÔNG dùng `source_slug` để phân loại. Đó là URL BÀI VIẾT mà
    entity được trích ra, không phải danh tính của entity. Trò chơi "Sky Bounder"
    và "Nhà Hàng Bát Giác" được mô tả trong bài "...loạt ưu đãi hè..." nên slug
    chứa "uu-dai" — phân loại theo slug sẽ coi hạ tầng công viên là khuyến mãi
    có hạn và ẩn mất. Chỉ tin TÊN của chính bản ghi.
    """
    if bucket in _DYNAMIC_BUCKETS:
        return True
    if bucket == "tickets":
        # Vé thường (Vé người lớn 180k) là giá NIÊM YẾT — không có hạn dùng.
        # Chỉ vé khuyến mãi mới là nội dung động.
        return bool(record.get("is_promo")) or bool(
            _PROMO_SIGNAL.search(str(record.get("name", ""))))
    # attractions / restaurant / teambuilding / info = hạ tầng công viên,
    # tồn tại quanh năm → không bao giờ tự hết hạn.
    return False


# ── Phán định hạn dùng ────────────────────────────────────────────────────────
def evaluate(record: dict, bucket: str = "events",
             today: Optional[date] = None,
             crawled_at=None) -> Tuple[str, str]:
    """
    Trả về (trạng_thái, lý_do). Trạng thái ∈ current | expired | undated | static.
    KHÔNG sửa record — chỉ phán định, để nơi gọi tự quyết.
    """
    today = today or date.today()

    if not is_dynamic(record, bucket):
        return STATIC, "nội dung tĩnh, không có hạn dùng"

    name = str(record.get("name", ""))
    # KHÔNG dùng source_slug ở bất kỳ luật nào: đó là URL bài viết nguồn, không
    # phải danh tính bản ghi. Đã hai lần mắc bẫy này — lần đầu suýt ẩn "Vé người
    # lớn 180k", lần sau ẩn nhầm trò "Go Kart" và món "Lẩu phụng ô trái dừa".
    slug = ""

    # 1. Ngày kết thúc ghi rõ — tín hiệu mạnh nhất
    end = parse_date(record.get("date_end") or record.get("valid_to"))
    if end:
        if end < today:
            return EXPIRED, f"đã kết thúc {end.isoformat()}"
        return CURRENT, f"còn hạn tới {end.isoformat()}"

    # 2. Năm trong tên/slug thuộc quá khứ
    yr = year_in_text(name, slug)
    if yr and yr < today.year:
        return EXPIRED, f"tên ghi năm {yr}"

    # 3. Gắn với ngày lễ đã qua trong năm nay
    hd = holiday_date(f"{name} {slug}", today.year)
    if hd and today > hd + timedelta(days=_HOLIDAY_GRACE_DAYS):
        return EXPIRED, f"lễ {hd.isoformat()} đã qua"

    # TTL chỉ áp cho CHIẾN DỊCH có thời hạn, không áp cho nội dung thường trực.
    # Bucket `events` lẫn nhiều thứ bị phân loại nhầm: trò chơi "Go Kart",
    # "Mega Zone", show "Sơn Tinh - Thủy Tinh", thậm chí món "Lẩu phụng ô trái
    # dừa" đều nằm trong events. Chúng tồn tại quanh năm — hết TTL mà ẩn đi là
    # xoá mất thông tin thật của công viên khỏi RAG.
    #
    # CHỈ áp cho bucket events. Vé đã gắn cờ is_promo THÌ ĐƯƠNG NHIÊN là chiến
    # dịch, dù tên trơn như "Vé người lớn" (đó chính là vé 120k của trang ưu
    # đãi 20%). Bỏ sót ở đây là vé khuyến mãi hết hạn sống lại và đè giá niêm yết.
    if bucket == "events" and not _is_campaign(name, slug):
        return UNDATED, "nội dung thường trực nằm nhầm trong events — không đặt hạn"

    # Khuyến mãi mà không xác định được hạn thì KHÔNG được coi là còn áp dụng —
    # không có chương trình giảm giá nào vô thời hạn.
    if bucket == "tickets" and record.get("is_promo") and not parse_date(crawled_at) \
            and not parse_date(record.get("date_start") or record.get("valid_from")):
        return EXPIRED, "vé khuyến mãi không xác định được thời hạn"

    # 4. Ngày bắt đầu + TTL
    start = parse_date(record.get("date_start") or record.get("valid_from"))
    if start:
        limit = start + timedelta(days=TTL_DAYS)
        if today > limit:
            return EXPIRED, f"bắt đầu {start.isoformat()}, quá TTL {TTL_DAYS} ngày"
        return CURRENT, f"bắt đầu {start.isoformat()}, trong TTL"

    # 5. Thời điểm crawl + TTL
    cr = parse_date(crawled_at)
    if cr:
        limit = cr + timedelta(days=TTL_DAYS)
        if today > limit:
            return EXPIRED, f"crawl {cr.isoformat()}, quá TTL {TTL_DAYS} ngày"
        return CURRENT, f"crawl {cr.isoformat()}, trong TTL"

    # 6. Không còn tín hiệu nào
    return UNDATED, "không có bất kỳ ngày nào — không khẳng định được"


def is_current(record: dict, bucket: str = "events",
               today: Optional[date] = None, crawled_at=None) -> bool:
    """Có được phép trả cho khách như nội dung đang áp dụng không?"""
    state, _ = evaluate(record, bucket, today, crawled_at)
    return state in (CURRENT, STATIC, UNDATED)


def is_confidently_current(record: dict, bucket: str = "events",
                           today: Optional[date] = None, crawled_at=None) -> bool:
    """Chặt hơn: chỉ True khi CHỨNG MINH được còn hạn. Dùng cho câu hỏi
    'hiện tại đang có gì' — nơi nói sai là mất uy tín với khách."""
    state, _ = evaluate(record, bucket, today, crawled_at)
    return state in (CURRENT, STATIC)


# ── Quét toàn bộ data ─────────────────────────────────────────────────────────
def build_crawl_map(clean_docs: list) -> dict:
    """{slug: crawled_at} lấy từ suoitien_clean_v4.json."""
    out = {}
    for d in clean_docs or []:
        s = d.get("slug")
        if s and d.get("crawled_at"):
            out[s] = d["crawled_at"]
    return out


def sweep(data: dict, crawl_map: dict = None,
          today: Optional[date] = None) -> dict:
    """
    Duyệt toàn bộ data, trả BÁO CÁO — KHÔNG tự sửa file.

    Luôn trả kèm danh sách chi tiết những gì sẽ bị ẩn, để soát ngược trước khi
    áp dụng. Bài học 28/06/2026: một migration "ẩn dữ liệu cũ" từng ẩn nhầm
    Combo Mùa Thu — nội dung MỚI NHẤT — vì không ai kiểm ngược danh sách.
    """
    today     = today or date.today()
    crawl_map = crawl_map or {}
    report = {"today": today.isoformat(), "ttl_days": TTL_DAYS,
              "to_hide": [], "to_show": [], "undated": [], "counts": {}}

    for bucket, items in (data or {}).items():
        if not isinstance(items, list):
            continue
        c = {CURRENT: 0, EXPIRED: 0, UNDATED: 0, STATIC: 0}
        for it in items:
            if not isinstance(it, dict):
                continue
            cr = crawl_map.get(it.get("source_slug"))
            state, reason = evaluate(it, bucket, today, cr)
            c[state] += 1
            rid  = it.get("event_id") or it.get("ticket_id") or it.get("id")
            name = str(it.get("name", ""))[:70]
            active_now = it.get("is_active") is not False
            entry = {"bucket": bucket, "id": rid, "name": name, "reason": reason}
            if state == EXPIRED and active_now:
                report["to_hide"].append(entry)
            elif state == CURRENT and not active_now:
                report["to_show"].append(entry)
            elif state == UNDATED and active_now:
                report["undated"].append(entry)
        report["counts"][bucket] = c

    return report


def _dedup_key(record: dict) -> str:
    """Khoá so trùng: tên đã bỏ dấu câu/khoảng trắng, cắt 60 ký tự đầu."""
    return re.sub(r"[^a-z0-9]+", "", str(record.get("name") or "").lower())[:60]


def _dedup_rank(record: dict, bucket: str) -> tuple:
    """
    Bản ghi nào ĐÁNG GIỮ hơn khi trùng tên. Số càng lớn càng được giữ.

    Ưu tiên bản có NGÀY RÕ RÀNG: bản crawl thô thường thiếu date_end và thiếu
    cả is_active, nên nếu chỉ so điểm khớp chữ thì bản thô đè mất bản đã biên
    tập. Đó là lý do "Quốc khánh 2/9 tặng 2.000 vé" trả về đúng nội dung nhưng
    sai bản ghi: 2 bản crawl xếp trên bản chuẩn có ngày hiệu lực.
    """
    return (
        1 if record.get("date_end") or record.get("valid_to") else 0,
        1 if record.get("date_start") or record.get("valid_from") else 0,
        1 if record.get("is_active") is True else 0,
        1 if record.get("priority") is not None else 0,
        len(str(record.get("description") or "")),
    )


def dedup(data: dict, buckets=("events", "tickets")) -> list:
    """
    Ẩn bản ghi TRÙNG TÊN, giữ lại bản đầy đủ nhất. Trả danh sách bị ẩn để soát.

    Crawl lại cùng một trang qua nhiều đường (sitemap, CMS push, bài tổng hợp)
    sinh ra nhiều bản ghi khác ID cho cùng một nội dung. Update-by-ID không gộp
    được vì ID khác nhau, còn TTL không giết được vì chúng đều mới.
    """
    hidden = []
    for bucket in buckets:
        items = data.get(bucket) or []
        groups: dict = {}
        for it in items:
            if not isinstance(it, dict) or it.get("is_active") is False:
                continue
            k = _dedup_key(it)
            if k:
                groups.setdefault(k, []).append(it)
        for k, group in groups.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda r: _dedup_rank(r, bucket), reverse=True)
            for extra in group[1:]:
                extra["is_active"] = False
                extra["expired_by"] = "duplicate"
                hidden.append({
                    "bucket": bucket,
                    "id": extra.get("event_id") or extra.get("ticket_id") or extra.get("id"),
                    "name": str(extra.get("name", ""))[:70],
                    "reason": f"trùng với {group[0].get('event_id') or group[0].get('ticket_id')}",
                })
    return hidden


def apply_sweep(data: dict, report: dict) -> int:
    """Áp dụng báo cáo vào data (in-place). Trả số bản ghi đã đổi."""
    hide = {(e["bucket"], e["id"]) for e in report.get("to_hide", [])}
    show = {(e["bucket"], e["id"]) for e in report.get("to_show", [])}
    n = 0
    for bucket, items in (data or {}).items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            rid = it.get("event_id") or it.get("ticket_id") or it.get("id")
            if (bucket, rid) in hide:
                it["is_active"] = False
                it["expired_by"] = "content_lifecycle"
                n += 1
            elif (bucket, rid) in show:
                it["is_active"] = True
                it.pop("expired_by", None)
                n += 1
    return n
