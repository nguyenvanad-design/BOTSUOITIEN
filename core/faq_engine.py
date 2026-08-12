"""
faq_engine.py — Rule-based fast path cho Suối Tiên bot (v3)
Xử lý câu hỏi thường gặp KHÔNG NHẬP NHẰNG mà không cần LLM.
Latency mục tiêu: < 50ms

Thay đổi v3 (fix false-positive):
1. Word boundary cho tiếng Việt — "doan" KHÔNG còn match "doanh nghiệp",
   "trời" không match khi nằm trong từ khác.
2. Mỗi rule có BLOCKERS — nếu query nhắc tới chủ thể cụ thể
   (Go Kart, nhà hàng, teambuilding...) → bỏ qua FAQ, đẩy về Planner.
3. Gate đa ý: nếu query match >= 2 rule khác nhau hoặc quá dài
   → trả None, để Planner tách thành nhiều tool call.
4. Bỏ các rule mơ hồ (trò chơi, farm, teambuilding, "trời/mưa/nắng" trần)
   — Planner + schema search trả lời tốt hơn nhiều so với câu canned.
5. Lang-aware: rule chỉ chạy đúng ngôn ngữ khai báo; handler nhận lang
   thống nhất (fix bug lambda nuốt mất tham số lang).
"""

import re
import sys, os
import unicodedata

sys.path.insert(0, os.path.dirname(__file__))

from weather_service import format_weather
from map_service     import format_directions, get_map_url
from schema_search import (
    get_contact_info,
    get_opening_hours,
    search_tickets,
    _format_price,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm_query(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt bằng unicodedata."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


# Ký tự "chữ" cho tiếng Việt (gồm cả có dấu). Dùng lookaround thay \b
# vì \b của re không hiểu chữ có dấu một cách đáng tin cậy.
_W = r"0-9a-zà-ỹ"

def _kw(*phrases: str) -> re.Pattern:
    """
    Build regex match BẤT KỲ phrase nào, có word boundary 2 đầu.
    VD: _kw("đoàn") sẽ match "đi theo đoàn" nhưng KHÔNG match "doanh nghiệp"
    (sau khi bỏ dấu: "doan" + lookahead thấy "h" → fail).
    """
    alts = "|".join(re.escape(p) for p in phrases)
    return re.compile(
        rf"(?<![{_W}])(?:{alts})(?![{_W}])",
        re.IGNORECASE,
    )


def _hit(pattern: re.Pattern, q: str, q_norm: str):
    """Search trên cả bản có dấu lẫn không dấu."""
    return pattern.search(q) or pattern.search(q_norm)


# ── Handlers — TẤT CẢ nhận (match, lang) thống nhất ───────────────────────────

_CONTACT = None  # lazy load

def _contact():
    global _CONTACT
    if not _CONTACT:
        _CONTACT = get_contact_info()
    return _CONTACT


def _ans_dia_chi(m, lang="vi"):
    c = _contact()
    maps_url = get_map_url()
    if lang == "en":
        return (f"📍 **Suoi Tien address:**\n{c['address']}\n\n"
                f"📞 Hotline: **{c['phone']}**\n📧 Email: {c['email']}\n\n"
                f"[📍 View on map]({maps_url})")
    if lang == "zh":
        return (f"📍 **水仙文化公园地址：**\n{c['address']}\n\n"
                f"📞 热线：**{c['phone']}**\n📧 邮箱：{c['email']}\n\n"
                f"[📍 查看地图]({maps_url})")
    if lang == "ko":
        return (f"📍 **수오이띠엔 주소：**\n{c['address']}\n\n"
                f"📞 핫라인：**{c['phone']}**\n📧 이메일：{c['email']}\n\n"
                f"[📍 지도 보기]({maps_url})")
    if lang == "ja":
        return (f"📍 **スオイティエン住所：**\n{c['address']}\n\n"
                f"📞 ホットライン：**{c['phone']}**\n📧 メール：{c['email']}\n\n"
                f"[📍 地図を見る]({maps_url})")
    return (f"📍 **Địa chỉ Suối Tiên:**\n{c['address']}\n\n"
            f"📞 Hotline: **{c['phone']}**\n📧 Email: {c['email']}\n\n"
            f"[📍 Xem bản đồ]({maps_url})")


def _ans_lien_he(m, lang="vi"):
    c = _contact()
    if lang == "en":
        return (f"**Suoi Tien contact info:**\n"
                f"📞 Hotline: **{c['phone']}**\n📧 Email: {c['email']}\n📍 {c['address']}")
    if lang == "zh":
        return (f"**水仙公园联系方式：**\n"
                f"📞 热线：**{c['phone']}**\n📧 邮箱：{c['email']}\n📍 {c['address']}")
    if lang == "ko":
        return (f"**수오이띠엔 연락처：**\n"
                f"📞 핫라인：**{c['phone']}**\n📧 이메일：{c['email']}\n📍 {c['address']}")
    if lang == "ja":
        return (f"**スオイティエン連絡先：**\n"
                f"📞 ホットライン：**{c['phone']}**\n📧 メール：{c['email']}\n📍 {c['address']}")
    return (f"**Thông tin liên hệ Suối Tiên:**\n"
            f"📞 Hotline: **{c['phone']}**\n📧 Email: {c['email']}\n📍 {c['address']}")


def _ans_gio_mo_cua(m, lang="vi"):
    _HOURS = {
        "vi": "Thứ 2 – Chủ Nhật: **7h30 – 17h00**. Dịp lễ/Tết: từ **7h00** đến khi hết khách.",
        "en": "Mon – Sun: **7:30 AM – 5:00 PM**. Holidays/Tet: from **7:00 AM** until the last guest.",
        "zh": "周一至周日：**7:30 – 17:00**。节假日/春节：**7:00** 起至最后一位游客。",
        "ko": "월–일: **오전 7시 30분 – 오후 5시**. 명절/설: **오전 7시**부터 마지막 손님까지.",
        "ja": "月–日：**7:30～17:00**。祝日/旧正月：**7:00**から最後のお客様まで。",
    }
    hours = _HOURS.get(lang, _HOURS["vi"])
    if lang == "en":
        return (f"🕗 **Suoi Tien opening hours:**\n{hours}\n\n"
                f"💡 For exact times call **1900 636 787** or check suoitien.vn")
    if lang == "zh":
        return (f"🕗 **水仙公园开放时间：**\n{hours}\n\n"
                f"💡 请致电 **1900 636 787** 或访问 suoitien.vn 获取最新信息")
    if lang == "ko":
        return (f"🕗 **수오이띠엔 운영시간：**\n{hours}\n\n"
                f"💡 정확한 시간은 **1900 636 787**로 전화하거나 suoitien.vn을 확인해주세요")
    if lang == "ja":
        return (f"🕗 **スオイティエン営業時間：**\n{hours}\n\n"
                f"💡 正確な時間は **1900 636 787** またはsuoitien.vnでご確認ください")
    return (f"🕗 **Giờ mở cửa Suối Tiên:**\n{hours}\n\n"
            f"💡 Để chắc chắn nhất, anh/chị gọi **1900 636 787** hoặc xem tại suoitien.vn nhé!")


def _ans_gia_ve(m, lang="vi"):
    tickets = search_tickets(max_results=10)
    std_adult = next((t for t in tickets if "người lớn" in t["name"].lower()
                      and t.get("price_adult") and t["price_adult"] > 10000), None)
    std_child = next((t for t in tickets if "trẻ em" in t["name"].lower()
                      and t.get("price_child") and t["price_child"] > 10000), None)
    # Combo là GIÁ CHIẾN DỊCH, đổi liên tục. FAQ là câu trả lời soạn sẵn gửi
    # thẳng cho khách (17% lưu lượng), không qua LLM và không qua tầng ưu tiên
    # nội dung web — nên nó từng công bố combo 220.000đ trong khi website đang
    # bán 240.000đ. Chỉ liệt kê combo CHỨNG MINH ĐƯỢC còn hiệu lực; combo không
    # có ngày thì dẫn khách sang trang chính thức thay vì đọc giá có thể sai.
    _combo_all = [t for t in tickets if "combo" in t["name"].lower()
                  and (t.get("price_adult") or t.get("price_child"))]
    try:
        from content_lifecycle import is_confidently_current
        combo = [t for t in _combo_all if is_confidently_current(t, "tickets")]
    except Exception:
        combo = []
    combo_uncertain = bool(_combo_all) and not combo

    # Data không khớp format mong đợi → đừng trả câu rỗng, để Planner lo
    if not std_adult and not std_child and not combo:
        return None

    # Nhãn theo ngôn ngữ — trước đây chỉ dịch dòng 💡, phần giá vẫn tiếng Việt
    L = {
        "vi": ("🎫 **Giá vé vào cổng Suối Tiên:**", "Người lớn", "Trẻ em",
               "**Combo tiết kiệm:**", "NL", "TE"),
        "en": ("🎫 **Suoi Tien entrance ticket prices:**", "Adult", "Child",
               "**Value combos:**", "Adult", "Child"),
        "zh": ("🎫 **碎仙公园门票价格：**", "成人", "儿童",
               "**优惠套票：**", "成人", "儿童"),
        "ko": ("🎫 **수오이띠엔 입장권 가격:**", "성인", "어린이",
               "**패키지 할인:**", "성인", "어린이"),
        "ja": ("🎫 **スオイティエン入場券料金：**", "大人", "子供",
               "**お得なコンボ：**", "大人", "子供"),
    }
    title, lbl_adult, lbl_child, lbl_combo, ca, cc = L.get(lang, L["vi"])

    lines = [f"{title}\n"]
    if std_adult:
        lines.append(f"• {lbl_adult}: **{_format_price(std_adult['price_adult'])}**")
    if std_child:
        lines.append(f"• {lbl_child}: **{_format_price(std_child['price_child'])}**")
    # Vé người cao tuổi — chỉ nêu ĐÚNG những gì có trong dữ liệu (giá + ghi chú).
    # KHÔNG tự suy ra ngưỡng tuổi: dữ liệu không ghi tuổi, trước đây LLM bịa
    # "trên 60 tuổi" → sai lệch chính sách.
    senior = next((t for t in tickets
                   if t.get("price_senior") and "cao tuổi" in t["name"].lower()), None)
    if senior and lang == "vi":
        note = str(senior.get("notes") or "").strip()
        line = f"• Người cao tuổi: **{_format_price(senior['price_senior'])}**"
        if note:
            line += f" ({note})"
        lines.append(line)

    if combo:
        lines.append(f"\n{lbl_combo}")
        for c in combo[:3]:
            pa = _format_price(c.get("price_adult"))
            pc = _format_price(c.get("price_child"))
            lines.append(f"• {c['name']}: {ca} {pa} / {cc} {pc}")
    elif combo_uncertain:
        # Có combo trong dữ liệu nhưng không xác minh được còn hiệu lực →
        # dẫn sang trang chính thức, KHÔNG đọc giá có thể đã cũ.
        _combo_note = {
            "vi": "\n🎁 **Combo ưu đãi** thay đổi theo từng đợt — anh/chị xem giá "
                  "mới nhất tại **suoitien.vn/bang-gia** hoặc gọi **1900 636 787** nhé!",
            "en": "\n🎁 **Combo deals** change seasonally — please check "
                  "**suoitien.vn/bang-gia** or call **1900 636 787** for current prices.",
            "zh": "\n🎁 **套票优惠**会不定期调整，请查看 **suoitien.vn/bang-gia** "
                  "或致电 **1900 636 787** 获取最新价格。",
            "ko": "\n🎁 **콤보 할인**은 시기별로 변경됩니다. **suoitien.vn/bang-gia** "
                  "또는 **1900 636 787**로 최신 가격을 확인해 주세요.",
            "ja": "\n🎁 **コンボ割引**は時期により変わります。**suoitien.vn/bang-gia** "
                  "または **1900 636 787** で最新価格をご確認ください。",
        }
        lines.append(_combo_note.get(lang, _combo_note["vi"]))
    tips = {
        "vi": "\n💡 Đặt vé online tại **suoitien.vn** để nhận ưu đãi tốt nhất!",
        "en": "\n💡 Book online at **suoitien.vn** for the best deals!",
        "zh": "\n💡 在 **suoitien.vn** 在线购票享受最优惠价格！",
        "ko": "\n💡 **suoitien.vn**에서 온라인 구매 시 최대 할인 혜택을 받으세요！",
        "ja": "\n💡 **suoitien.vn**でオンライン購入が最もお得です！",
    }
    lines.append(tips.get(lang, tips["vi"]))
    return "\n".join(lines)


def _ans_duong_di(m, lang="vi"):
    return format_directions(lang)


def _ans_mua_ve_online(m, lang="vi"):
    return (
        "🛒 **Mua vé online Suối Tiên:**\n\n"
        "• Website: **suoitien.vn**\n"
        "• Ứng dụng: Tìm 'Suối Tiên' trên App Store / CH Play\n"
        "• Hotline: **1900 636 787**\n\n"
        "💡 Mua online thường có giá ưu đãi hơn mua tại quầy!"
    )


def _ans_xe_bus(m, lang="vi"):
    return (
        "🚌 **Xe buýt đến Suối Tiên:**\n\n"
        "Các tuyến xe buýt đi qua Xa Lộ Hà Nội dừng gần Suối Tiên:\n"
        "• Tuyến **19**: Bến Thành — Suối Tiên\n"
        "• Tuyến **53**: Chợ Lớn — Bến xe Miền Đông\n\n"
        "🚇 **Metro số 1** (Bến Thành — Suối Tiên) cũng là lựa chọn tiện lợi!\n\n"
        "📞 Hotline: **1900 636 787**"
    )


def _ans_gui_xe(m, lang="vi"):
    return (
        "🚗 **Gửi xe tại Suối Tiên:**\n\n"
        "Suối Tiên có bãi đỗ xe rộng rãi cho cả xe máy và ô tô.\n"
        "📍 Bãi xe nằm tại cổng vào: 120 Xa Lộ Hà Nội, P. Tăng Nhơn Phú.\n\n"
        "📞 Chi tiết phí giữ xe: **1900 636 787**"
    )


def _ans_weather(m, lang="vi"):
    return format_weather(lang)


def _ans_map(m, lang="vi"):
    return format_directions(lang)


# ── Rule table ─────────────────────────────────────────────────────────────────
# Mỗi rule:
#   name     : id rule (debug)
#   patterns : list regex (match bất kỳ → trigger)
#   blockers : regex — nếu match → KHÔNG dùng FAQ, đẩy về Planner
#   require  : regex — nếu có, query PHẢI match thêm cái này mới trigger
#   langs    : set ngôn ngữ rule được phép chạy (None = mọi ngôn ngữ)
#   handler  : fn(match, lang) -> str | None

# Các chủ thể cụ thể trong công viên — nếu khách hỏi kèm những từ này,
# câu trả lời canned chung chung sẽ SAI → để Planner tra data.
_SPECIFIC_SUBJECT = _kw(
    "trò chơi", "tro choi", "trò", "game", "go kart", "gokart", "kart",
    "tàu lượn", "tau luon", "slide", "infinity", "twin race", "xe tăng", "xe tang",
    "thủy cung", "thuy cung", "biển", "bien", "phim",
    "nhà hàng", "nha hang", "buffet", "ăn", "an uong", "món", "mon",
    "teambuilding", "team building", "đoàn", "doan", "cắm trại", "cam trai",
    "sự kiện", "su kien", "lễ hội", "le hoi", "show", "biểu diễn", "bieu dien",
    "farm", "vườn", "vuon", "khu",
    "toilet", "wc", "vệ sinh", "ve sinh", "quầy", "quay", "cổng nào", "cong nao",
    # Món ăn / đồ mua: "Lẩu ... ở đâu trong công viên?" từng bị FAQ địa chỉ
    # cướp mất vì có đủ "ở đâu" + "công viên" → trả về địa chỉ Suối Tiên.
    "lẩu", "lau", "phở", "cơm", "com", "gỏi", "goi", "bánh", "banh",
    "nước ép", "nuoc ep", "sinh tố", "sinh to", "trà", "tra", "cà phê", "ca phe",
    "kem", "đồ uống", "do uong", "hải sản", "hai san", "nướng", "nuong",
    "lưu niệm", "luu niem", "quà", "qua", "sạc", "sac", "atm", "gửi đồ", "gui do",
)

_RULES = [
    {
        "name": "dia_chi",
        "patterns": [_kw("địa chỉ", "dia chi", "tọa lạc", "toa lac",
                         "nằm ở đâu", "nam o dau", "ở đâu", "o dau",
                         "chỗ nào", "cho nao", "quận nào", "quan nao",
                         "where is", "address", "located",
                         "地址", "在哪", "怎么去", "位置",
                         "어디", "위치", "주소",
                         "住所", "どこ", "場所")],
        # "ở đâu" rất rộng → chỉ nhận khi rõ là hỏi về CÔNG VIÊN
        "require": _kw("suối tiên", "suoi tien", "công viên", "cong vien",
                       "khu du lịch", "khu du lich", "địa chỉ", "dia chi",
                       "address", "park"),
        "blockers": _SPECIFIC_SUBJECT,
        "langs": {"vi", "en", "zh", "ko", "ja"},
        "handler": _ans_dia_chi,
    },
    {
        "name": "lien_he",
        "patterns": [_kw("liên hệ", "lien he", "hotline", "số điện thoại",
                         "so dien thoai", "sđt", "sdt", "email", "contact",
                         "phone number")],
        "blockers": None,
        "langs": {"vi", "en", "zh", "ko", "ja"},
        "handler": _ans_lien_he,
    },
    {
        "name": "gio_mo_cua",
        "patterns": [
            _kw("giờ mở cửa", "gio mo cua", "giờ đóng cửa", "gio dong cua",
                "giờ hoạt động", "gio hoat dong", "giờ làm việc", "gio lam viec",
                "opening hours", "what time",
                "开门", "几点", "开放时间", "开放",
                "몇 시", "개장", "운영 시간",
                "開園", "何時"),
            re.compile(rf"(?:mấy giờ|may gio)\s+(?:mở|mo|đóng|dong)", re.IGNORECASE),
            re.compile(rf"(?:mở|mo|đóng|dong)\s+cửa\s+(?:lúc|luc|mấy|may)", re.IGNORECASE),
        ],
        # Hỏi giờ của show/sự kiện cụ thể → Planner
        "blockers": _kw("show", "biểu diễn", "bieu dien", "sự kiện", "su kien",
                        "lễ", "le hoi", "trò", "tro", "nhà hàng", "nha hang"),
        "langs": {"vi", "en", "zh", "ko", "ja"},
        "handler": _ans_gio_mo_cua,
    },
    {
        # Đặt TRƯỚC gia_ve vì "mua vé online" cũng chứa "mua vé"
        "name": "mua_ve_online",
        "patterns": [_kw("mua vé online", "mua ve online", "đặt vé", "dat ve",
                         "book vé", "book ve", "mua trực tuyến", "mua truc tuyen",
                         "mua vé ở đâu", "mua ve o dau", "mua vé trước", "mua ve truoc")],
        "blockers": None,
        "langs": {"vi"},
        "handler": _ans_mua_ve_online,
    },
    {
        "name": "gia_ve",
        "patterns": [_kw("giá vé", "gia ve", "vé bao nhiêu", "ve bao nhieu",
                         "phí vào cổng", "phi vao cong", "vé vào cổng", "ve vao cong",
                         "giá vào cổng", "gia vao cong", "bao nhiêu tiền", "bao nhieu tien",
                         "mất tiền không", "mat tien khong",
                         "门票", "票价", "多少钱", "입장료", "얼마",
                         "入場料", "いくら")],
        # Hỏi giá của thứ cụ thể (trò chơi, nhà hàng, combo đoàn...) → Planner
        "blockers": _SPECIFIC_SUBJECT,
        "langs": {"vi", "en", "zh", "ko", "ja"},
        "handler": _ans_gia_ve,
    },
    {
        "name": "xe_bus",
        "patterns": [_kw("xe buýt", "xe buyt", "xe bus", "tuyến buýt", "tuyen buyt",
                         "tuyến bus", "tuyen bus", "buýt số", "buyt so", "bus số", "bus so")],
        "blockers": None,
        "langs": {"vi"},
        "handler": _ans_xe_bus,
    },
    {
        "name": "duong_di",
        "patterns": [_kw("đường đi", "duong di", "cách đi", "cach di",
                         "cách đến", "cach den", "làm sao đến", "lam sao den",
                         "đi bằng gì", "di bang gi", "hướng dẫn đến", "huong dan den",
                         "di chuyển", "di chuyen", "metro", "how to get")],
        "blockers": None,
        "langs": None,  # handler đã lang-aware
        "handler": _ans_duong_di,
    },
    {
        "name": "gui_xe",
        "patterns": [_kw("gửi xe", "gui xe", "giữ xe", "giu xe", "đậu xe", "dau xe",
                         "bãi xe", "bai xe", "bãi đỗ", "bai do", "parking",
                         "phí gửi xe", "phi gui xe")],
        "blockers": None,
        "langs": {"vi", "en", "zh", "ko", "ja"},
        "handler": _ans_gui_xe,
    },
    {
        "name": "thoi_tiet",
        # Bỏ "trời/mưa/nắng" trần — quá mơ hồ ("trò chơi ngoài trời"...)
        "patterns": [_kw("thời tiết", "thoi tiet", "nhiệt độ", "nhiet do",
                         "dự báo", "du bao", "weather", "forecast",
                         "天气", "温度", "天気", "날씨")],
        "blockers": None,
        "langs": None,  # handler đã lang-aware
        "handler": _ans_weather,
    },
    {
        "name": "ban_do",
        "patterns": [_kw("bản đồ", "ban do", "google map", "google maps", "map",
                         "chỉ đường", "chi duong", "directions", "地图", "地図", "지도")],
        "blockers": None,
        "langs": None,  # handler đã lang-aware
        "handler": _ans_map,
    },
]

# Query quá dài thường đa ý / có ngữ cảnh phức tạp → để Planner xử lý
_MAX_FAQ_WORDS = 14


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def faq_match(query: str, lang: str = "vi") -> dict | None:
    """
    Kiểm tra query có match FAQ rule không. Match cả có dấu lẫn không dấu.

    Trả None (→ chuyển cho Planner) khi:
    - Query dài quá _MAX_FAQ_WORDS từ
    - Match >= 2 rule khác nhau (câu đa ý)
    - Rule bị blocker chặn (nhắc tới chủ thể cụ thể)
    - Rule không hỗ trợ ngôn ngữ của khách
    - Handler trả None (data không đủ)
    """
    q = query.strip()
    if not q:
        return None
    if len(q.split()) > _MAX_FAQ_WORDS:
        return None

    q_norm = _norm_query(q)

    matched = []  # [(rule, match_obj)]
    for rule in _RULES:
        if rule["langs"] is not None and lang not in rule["langs"]:
            continue
        if rule["blockers"] is not None and _hit(rule["blockers"], q, q_norm):
            continue
        if rule.get("require") is not None and not _hit(rule["require"], q, q_norm):
            continue
        for pattern in rule["patterns"]:
            m = _hit(pattern, q, q_norm)
            if m:
                matched.append((rule, m))
                break

    if not matched:
        return None

    # Câu đa ý (match nhiều rule) → Planner tách tool call tốt hơn
    if len(matched) >= 2:
        return None

    rule, m = matched[0]
    answer = rule["handler"](m, lang=lang)
    if not answer:
        return None

    return {
        "source": "faq",
        "answer": answer,
        "rule":   rule["name"],
        "lang":   lang,
    }


# ── QUICK TEST ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.environ.setdefault("SUOITIEN_DATA",
        str(os.path.join(os.path.dirname(__file__), "data", "suoitien_data_v2.json")))

    # (query, lang, expected: tên rule hoặc None)
    test_cases = [
        # Phải MATCH
        ("Suối Tiên ở đâu vậy?",               "vi", "dia_chi"),
        ("Địa chỉ công viên?",                  "vi", "dia_chi"),
        ("Số điện thoại liên hệ?",              "vi", "lien_he"),
        ("Mấy giờ mở cửa?",                     "vi", "gio_mo_cua"),
        ("Giá vé vào cổng bao nhiêu?",          "vi", "gia_ve"),
        ("Vào công viên mất tiền không?",       "vi", "gia_ve"),
        ("Mua vé online ở đâu?",                "vi", "mua_ve_online"),
        ("Có xe buýt nào đến không?",           "vi", "xe_bus"),
        ("Đi metro đến Suối Tiên được không?",  "vi", "duong_di"),
        ("Gửi xe máy ở đâu?",                   "vi", "gui_xe"),
        ("Thời tiết hôm nay thế nào?",          "vi", "thoi_tiet"),
        ("Cho xin bản đồ công viên",            "vi", "ban_do"),
        ("What's the weather today?",           "en", "thoi_tiet"),

        # KHÔNG được match (trước đây là false positive)
        ("Go Kart giá bao nhiêu?",              "vi", None),  # giá trò cụ thể
        ("Go Kart ở đâu?",                      "vi", None),  # vị trí trong park
        ("Đoạn đường đến Suối Tiên xa không?",  "vi", None),  # "doan" ≠ đoàn
        ("Tư vấn cho doanh nghiệp 50 người",    "vi", None),  # "doanh" ≠ đoàn
        ("Trò chơi ngoài trời có gì?",          "vi", None),  # "trời" ≠ thời tiết
        ("Ăn trưa ở khu nào ngon?",             "vi", None),  # nhà hàng → Planner
        ("Show biểu diễn mấy giờ bắt đầu?",     "vi", None),  # giờ show ≠ giờ mở cửa
        ("Nhà hàng nào có buffet?",             "vi", None),
        ("Giá vé bao nhiêu và đi xe buýt nào?", "vi", None),  # đa ý → Planner
        ("门票多少钱？",                          "zh", None),  # zh → LLM trả lời
    ]

    print("=== FAQ ENGINE v3 TEST ===\n")
    passed = 0
    for q, lang, expected in test_cases:
        result = faq_match(q, lang=lang)
        got = result["rule"] if result else None
        ok = got == expected
        passed += ok
        status = "✅" if ok else "❌"
        print(f"{status} [{lang}] '{q}' → {got} (expected {expected})")
    print(f"\n{passed}/{len(test_cases)} passed")
