"""
link_service.py — Attach relevant links vào bot responses
- FAQ/schema: link tĩnh theo intent
- RAG/hybrid: link từ source_slug của docs
- Attractions + Restaurants: có link riêng từng item
"""

BASE_URL = "https://suoitien.vn"

# ── Full attraction & restaurant maps (auto-generated từ data_v2) ──────────────
ATT_MAP = {
    "Suối Tiên Farm": "https://suoitien.vn/suoi-tien-farm-3",
    "Farm Nho Mầu Đơn - Nho Ngón Tay": "https://suoitien.vn/suoi-tien-farm",
    "Farm Sung Mỹ": "https://suoitien.vn/suoi-tien-farm",
    "Farm Dừa": "https://suoitien.vn/suoi-tien-farm",
    "Sân Khấu Thực Cảnh Dưới Nước - Khí Phách Rồng Tiên": "https://suoitien.vn/ky-niem-30-nam-suoi-tien-ra-mat-san-khau-thuc-canh-duoi-nuoc-dac-sac",
    "Sky Bounder – Người chinh phục bầu trời": "https://suoitien.vn/sky-bounder-cu-twist-khong-the-bo-lo-he-nay",
    "Bí mật rừng phù thủy": "https://suoitien.vn/bi-mat-rung-phu-thuy",
    "Vườn Hồng Socola Indo - Suối Tiên Farm": "https://suoitien.vn/kham-pha-vuon-hong-socola-indo-sai-qua-giua-long-thanh-pho",
    "Suối Tiên Farm - Vườn Nho Nhật Bản": "https://suoitien.vn/top-nhung-loai-nho-nhat-ban-dang-duoc-ua-chuong-nhat-tai-viet-nam",
    "Tour Du Lịch Hướng Nghiệp - Khám Phá Ngành Du Lịch & Quản Lý Công Viên Giải Trí": "https://suoitien.vn/tour-du-lich-huong-nghiep-tai-suoi-tien-hanh-trinh-kham-pha-tuong-lai",
    "Tour Du Lịch Hướng Nghiệp - Trải Nghiệm Ngành F&B Như Một Quản Lý Thực Thụ": "https://suoitien.vn/tour-du-lich-huong-nghiep-tai-suoi-tien-hanh-trinh-kham-pha-tuong-lai",
    "Vườn Nho Mẫu Đơn Suối Tiên Farm": "https://suoitien.vn/tham-quan-mien-phi-vuon-nho-mau-don-suoi-tien-farm-giua-long-sai-gon",
    "Biển Tiên Đồng - Ngọc Nữ": "https://suoitien.vn/bien-tien-dong",
    "Phong Linh Điểu Cảnh - Vương quốc cá sấu": "https://suoitien.vn/bien-tien-dong-ngoc-nu-dai-duong-huyen-thoai-giua-long-sai-gon",
    "Sky Bounder - Người chinh phục bầu trời": "https://suoitien.vn/bien-tien-dong-ngoc-nu",
    "Vũ điệu tagada - phi cơ - ghế bay": "https://suoitien.vn/bien-tien-dong-ngoc-nu",
    "Mát Lạnh Nước Ép Sung Mỹ Suối Tiên Farm": "https://suoitien.vn/mat-lanh-nuoc-ep-sung-my-suoi-tien-farm",
    "Cung Vàng Điện Ngọc": "https://suoitien.vn/cung-vang-dien-ngoc",
    "Sung Mỹ Camy - Vườn Trái Cây Suối Tiên Farm": "https://suoitien.vn/sung-my-camy-cua-suoi-tien-farm-vao-mua-thu-hoach",
    "Khám phá vũ trụ huyền bí - VR GAME": "https://suoitien.vn/vikham-pha-vu-tru-huyen-biend-vienkham-pha-vu-tru-huyen-biend-en",
    "Lâu Đài Tuyết": "https://suoitien.vn/lau-dai-tuyet",
    "Lâu Đài Pháp Thuật": "https://suoitien.vn/lau-dai-phap-thuat",
    "Thủy Cung": "https://suoitien.vn/thuy-cung",
    "Tinh Tú Thiên Hà - The Nebula": "https://suoitien.vn/suoi-tien-ra-mat-cong-trinh-moi-tinh-tu-thien-ha-the-nebula",
    "Farm Nho Mẫu Đơn": "https://suoitien.vn/farm-nho-mau-don-sap-vao-mua-thu-hoach-chao-don-quy-du-khach",
    "Suối Tiên Farm - Vườn Sung Mỹ": "https://suoitien.vn/vi-sao-sung-my-suoi-tien-farm-duoc-nhieu-nguoi-chon-mua",
    "Vườn Sung Mỹ": "https://suoitien.vn/sung-my-tai-suoi-tien-farm-co-gi-dac-biet",
    "Vườn Nho Chất Lượng Sài Gòn": "https://suoitien.vn/vuon-nho-chat-luong-sai-gon-tai-suoi-tien-farm",
    "Biển Tiên Đồng Ngọc Nữ": "https://suoitien.vn/bien-tien-dong-ngoc-nu",
    "Phong Linh Điêu Cảnh - Vương quốc cá sấu": "https://suoitien.vn/bien-tien-dong-ngoc-nu",
    "Vườn Nho Suối Tiên Farm": "https://suoitien.vn/tham-quan-trai-nghiem-hai-trai-tai-vuon-nho-suoi-tien-farm-o-sai-gon",
    "Vườn Sung Mỹ Suối Tiên Farm": "https://suoitien.vn/tham-quan-trai-nghiem-hai-trai-tai-vuon-nho-suoi-tien-farm-o-sai-gon",
    "Vườn Dừa Xiêm Suối Tiên Farm": "https://suoitien.vn/tham-quan-trai-nghiem-hai-trai-tai-vuon-nho-suoi-tien-farm-o-sai-gon",
    "VUI CHƠI THÍCH MÊ - MIỄN 100% VÉ VÀO CỔNG CHO TRẺ EM TRONG NGÀY 1/6": "https://suoitien.vn/vui-choi-thich-me-mien-100-ve-vao-cong-cho-tre-em-trong-ngay-16-",
    "Thủy Cung - Công viên Văn hóa Suối Tiên": "https://suoitien.vn/thuy-cung-o-sai-gon",
    "Công trình văn hóa lịch sử": "https://suoitien.vn/trai-nghiem-dac-biet",
    "Công trình văn hóa tâm linh": "https://suoitien.vn/trai-nghiem-dac-biet",
    "Suối Tiên Farm - Du lịch xanh": "https://suoitien.vn/trai-nghiem-dac-biet",
    "Đu dây qua hồ": "https://suoitien.vn/du-day-qua-ho",
    "Tinh Tú Thiên Hà": "https://suoitien.vn/tinh-tu-thien-ha-1",
    "Quảng Trường Kim Lân Sơn Xuất Thế": "https://suoitien.vn/tu-linh-hoi-tu",
    "Tứ Linh Hội Tụ": "https://suoitien.vn/tu-linh-hoi-tu",
    "Long Hoa Thiên Bảo": "https://suoitien.vn/tu-linh-hoi-tu",
    "Giếng Tiên - Bình Nước Cam Lộ": "https://suoitien.vn/tu-linh-hoi-tu",
    "Thánh Tượng Quán Thế Âm Thiên Thủ Thiên Nhãn": "https://suoitien.vn/thanh-tuong-quan-the-am-thien-thu-thien-nhan",
    "Tứ Linh Thiên Trụ": "https://suoitien.vn/tu-linh-thien-tru",
    "Linh Cung Thập Nhị Giáp": "https://suoitien.vn/linh-cung-thap-nhi-giap",
    "Quảng Trường - Đền Thờ Quốc Tổ Hùng Vương": "https://suoitien.vn/quang-truong-den-tho-quoc-to-hung-vuong",
    "Cây Ước Nguyện": "https://suoitien.vn/cay-uoc-nguyen",
    "Long Hoa Hội": "https://suoitien.vn/long-hoa-hoi-rong-dai-400m",
    "Hồ Long Quy Ẩn Thủy": "https://suoitien.vn/ho-long-quy-an-thuy",
    "Cụm tượng Đinh Bộ Lĩnh - Đền thờ Đinh Tiên Hoàng": "https://suoitien.vn/cum-tuong-dinh-bo-linh-den-tho-dinh-tien-hoang",
    "Tượng Đài Thánh Gióng": "https://suoitien.vn/tuong-dai-thanh-giong",
    "Tượng Đài Trần Hưng Đạo": "https://suoitien.vn/tuong-dai-tran-hung-dao",
    "Tượng Đài Hai Bà Trưng": "https://suoitien.vn/tuong-dai-hai-ba-trung",
    "Cổng Thiên Tiên Môn": "https://suoitien.vn/cong-thien-tien-mon",
    "Thiên Đăng Bảo Tháp": "https://suoitien.vn/thien-dang-bao-thap",
    "Bút Tích Cố Tổng Bí Thư Nguyễn Văn Linh": "https://suoitien.vn/but-tich-co-tong-bi-thu-nguyen-van-linh",
    "Đại Bồ Đề Quang Minh Cảnh": "https://suoitien.vn/dai-bo-de-quang-minh-canh",
    "Sung Mỹ Suối Tiên Farm": "https://suoitien.vn/sung-my",
    "Ngựa phi nước đại": "https://suoitien.vn/ngua-phi-nuoc-dai",
    "Du thuyền thiên nga": "https://suoitien.vn/du-thuyen-thien-nga",
    "Massage Cá": "https://suoitien.vn/massage-ca",
    "Vũ Điệu Tagada": "https://suoitien.vn/vu-dieu-tagada-phi-co-ghe-bay",
    "Phi Cơ": "https://suoitien.vn/vu-dieu-tagada-phi-co-ghe-bay",
    "Ghế Bay": "https://suoitien.vn/vu-dieu-tagada-phi-co-ghe-bay",
    "Đĩa xoáy thiên hà": "https://suoitien.vn/dia-xoay-thien-ha",
    "Đĩa Bay Hành Tinh Lạ": "https://suoitien.vn/dia-bay-hanh-tinh-la",
    "Vòng xoay vũ trụ": "https://suoitien.vn/vong-xoay-vu-tru",
    "Thuyền Bay": "https://suoitien.vn/thuyen-bay",
    "Thuyền Rồng": "https://suoitien.vn/thuyen-rong",
    "Công nghệ phim 12D": "https://suoitien.vn/cong-nghe-phim-12d",
    "Ngôi nhà ma": "https://suoitien.vn/ngoi-nha-ma",
    "Đại Cung Phụng Hoàng Tiên": "https://suoitien.vn/dai-cung-phung-hoang-tien",
    "Công nghệ phim 9D": "https://suoitien.vn/cong-nghe-phim-9d",
    "Kỳ Lân Cung": "https://suoitien.vn/ky-lan-cung",
    "Đường Hầm Xuyên Lòng Đất": "https://suoitien.vn/duong-ham-xuyen-long-dat",
    "Vương Quốc Cá Sấu - Giang Sơn Bách Thú": "https://suoitien.vn/phong-linh-dieu-canh-vuong-quoc-ca-sau",
    "Phong Linh Điểu Cảnh": "https://suoitien.vn/phong-linh-dieu-canh-vuong-quoc-ca-sau",
    "Xạ Thủ Thần Công": "https://suoitien.vn/xa-thu-than-cong",
    "Đấu trường cung thủ": "https://suoitien.vn/dau-truong-cung-thu",
    "Du Thuyền Tứ Linh": "https://suoitien.vn/du-thuyen-tu-linh",
    "Xe Tăng – Hành Trình Chiến Xa": "https://suoitien.vn/-xe-tang-hanh-trinh-chien-xa",
    "Go Kart – Đường Đua Tốc Độ": "https://suoitien.vn/go-kart-duong-dua-toc-do",
    "Infinity Slide – Đường Trượt Vô Cực": "https://suoitien.vn/infinity-slide-duong-truot-vo-cuc",
    "Twin Race - Đường Trượt Đua Thần Tốc": "https://suoitien.vn/twin-race-duong-truot-dua-than-toc"
}

REST_MAP = {
    "Nhà hàng Suối Tiên": "https://suoitien.vn/dich-vu-to-chuc-sinh-nhat",
    "Nhà hàng Phù Đổng 4": "https://suoitien.vn/chuoi-nha-hang-phu-dong",
    "Nhà hàng Hùng Vương (Phù Đổng 5)": "https://suoitien.vn/chuoi-nha-hang-phu-dong",
    "Nhà hàng Tiên Ngư": "https://suoitien.vn/nha-hang-tien-ngu",
    "Phố Ẩm thực": "https://suoitien.vn/pho-am-thuc",
    "Suối Tiên Food Station": "https://suoitien.vn/nha-hang-thu-duc",
    "Nhà hàng Bát Giác": "https://suoitien.vn/nha-hang-bat-giac",
    "Âm Cung Đệ Nhất Cung Đình Tửu": "https://suoitien.vn/cung-dinh-tuu",
    "Trạm dừng chân Suối Tiên": "https://suoitien.vn/dich-vu-tram-dung-chan",
    "Phố Lẩu Đêm": "https://suoitien.vn/dich-vu-tram-dung-chan"
}


# ── Static links per intent ────────────────────────────────────────────────────
_INTENT_LINKS = {
    "hoi_gia_ve": [
        {"label": "🎫 Bảng giá vé",        "url": f"{BASE_URL}/bang-gia"},
        {"label": "🛒 Mua vé online",       "url": f"{BASE_URL}/chon-ve"},
    ],
    "hoi_ve_cong": [
        {"label": "🛒 Mua vé online",       "url": f"{BASE_URL}/chon-ve"},
        {"label": "🎫 Bảng giá vé",        "url": f"{BASE_URL}/bang-gia"},
    ],
    "hoi_gio_mo_cua": [
        {"label": "ℹ️ Thông tin tham quan", "url": f"{BASE_URL}/thong-tin"},
    ],
    "hoi_dia_chi": [
        {"label": "📍 Xem bản đồ",          "url": "https://maps.google.com/?q=10.8415,106.7717"},
        {"label": "ℹ️ Liên hệ",            "url": f"{BASE_URL}/lien-he"},
    ],
    "hoi_lien_he": [
        {"label": "📞 Liên hệ",             "url": f"{BASE_URL}/lien-he"},
    ],
    "hoi_duong_di": [
        {"label": "📍 Xem bản đồ",          "url": "https://maps.google.com/?q=10.8415,106.7717"},
        {"label": "🚇 Metro số 1",          "url": "https://metrohcmc.vn"},
    ],
    "hoi_chinh_sach": [
        {"label": "📋 Chính sách",          "url": f"{BASE_URL}/quy-dinh-dat-ve"},
    ],
    "hoi_tro_choi": [
        {"label": "🎢 Khu vui chơi",        "url": f"{BASE_URL}/vui-choi-giai-tri"},
        {"label": "🎫 Mua vé",              "url": f"{BASE_URL}/chon-ve"},
    ],
    "hoi_khu_vui_choi": [
        {"label": "🎢 Khu vui chơi",        "url": f"{BASE_URL}/vui-choi-giai-tri"},
    ],
    "hoi_van_hoa": [
        {"label": "🏛️ Văn hóa tâm linh",   "url": f"{BASE_URL}/cong-trinh-van-hoa-tam-linh-1"},
    ],
    "hoi_farm": [
        {"label": "🌿 Suối Tiên Farm",      "url": f"{BASE_URL}/suoi-tien-farm-du-lich-xanh"},
    ],
    "hoi_su_kien": [
        {"label": "🎉 Sự kiện & Ưu đãi",   "url": f"{BASE_URL}/tin-tuc"},
        {"label": "📅 Lịch sự kiện",        "url": f"{BASE_URL}/uu-dai-va-su-kien"},
    ],
    "hoi_uu_dai": [
        {"label": "🎁 Ưu đãi hiện tại",    "url": f"{BASE_URL}/uu-dai-va-su-kien"},
        {"label": "🛒 Mua vé combo",        "url": f"{BASE_URL}/chon-ve"},
    ],
    "hoi_teambuilding": [
        {"label": "🏕️ Teambuilding",       "url": f"{BASE_URL}/dich-vu"},
        {"label": "📞 Liên hệ đặt lịch",   "url": f"{BASE_URL}/lien-he"},
    ],
    "hoi_nha_hang": [
        {"label": "🍜 Ẩm thực",            "url": f"{BASE_URL}/am-thuc"},
        {"label": "🏛️ Cung Đình Tửu",     "url": f"{BASE_URL}/cung-dinh-tuu"},
    ],
    "hoi_chung": [
        {"label": "🌐 Website Suối Tiên",  "url": BASE_URL},
    ],
}

_LABEL_MAP = {
    "en": {
        "🎫 Bảng giá vé": "🎫 Ticket Prices", "🛒 Mua vé online": "🛒 Buy Tickets",
        "📍 Xem bản đồ": "📍 View on Maps", "ℹ️ Thông tin tham quan": "ℹ️ Visit Info",
        "ℹ️ Liên hệ": "ℹ️ Contact", "📞 Liên hệ": "📞 Contact Us",
        "🚇 Metro số 1": "🚇 Metro Line 1", "📋 Chính sách": "📋 Policies",
        "🎢 Khu vui chơi": "🎢 Attractions", "🎫 Mua vé": "🎫 Buy Tickets",
        "🏛️ Văn hóa tâm linh": "🏛️ Cultural Sites", "🌿 Suối Tiên Farm": "🌿 Farm",
        "🎉 Sự kiện & Ưu đãi": "🎉 Events & Offers", "📅 Lịch sự kiện": "📅 Schedule",
        "🎁 Ưu đãi hiện tại": "🎁 Current Offers", "🛒 Mua vé combo": "🛒 Combo Tickets",
        "🏕️ Teambuilding": "🏕️ Team Building", "📞 Liên hệ đặt lịch": "📞 Book Package",
        "🍜 Ẩm thực": "🍜 Dining", "🏛️ Cung Đình Tửu": "🏛️ Cung Dinh Tuu",
        "🌐 Website Suối Tiên": "🌐 Official Website",
    },
    "zh": {
        "🎫 Bảng giá vé": "🎫 票价表", "🛒 Mua vé online": "🛒 在线购票",
        "📍 Xem bản đồ": "📍 查看地图", "ℹ️ Thông tin tham quan": "ℹ️ 参观信息",
        "ℹ️ Liên hệ": "ℹ️ 联系方式", "📞 Liên hệ": "📞 联系我们",
        "🚇 Metro số 1": "🚇 地铁1号线", "🎢 Khu vui chơi": "🎢 游乐区",
        "🎫 Mua vé": "🎫 购票", "🏛️ Văn hóa tâm linh": "🏛️ 文化古迹",
        "🌿 Suối Tiên Farm": "🌿 农场体验", "🎉 Sự kiện & Ưu đãi": "🎉 活动与优惠",
        "🎁 Ưu đãi hiện tại": "🎁 当前优惠", "🛒 Mua vé combo": "🛒 套票购买",
        "🏕️ Teambuilding": "🏕️ 团队活动", "📞 Liên hệ đặt lịch": "📞 预约咨询",
        "🍜 Ẩm thực": "🍜 餐饮", "🏛️ Cung Đình Tửu": "🏛️ 宫廷酒楼",
        "🌐 Website Suối Tiên": "🌐 官方网站",
    },
    "ko": {
        "🎫 Bảng giá vé": "🎫 입장권 가격", "🛒 Mua vé online": "🛒 온라인 티켓",
        "📍 Xem bản đồ": "📍 지도 보기", "ℹ️ Liên hệ": "ℹ️ 연락처",
        "📞 Liên hệ": "📞 문의하기", "🚇 Metro số 1": "🚇 지하철 1호선",
        "🎢 Khu vui chơi": "🎢 놀이시설", "🎫 Mua vé": "🎫 티켓 구매",
        "🌿 Suối Tiên Farm": "🌿 팜 체험", "🎉 Sự kiện & Ưu đãi": "🎉 이벤트 & 혜택",
        "🎁 Ưu đãi hiện tại": "🎁 현재 혜택", "🏕️ Teambuilding": "🏕️ 팀빌딩",
        "📞 Liên hệ đặt lịch": "📞 예약 문의", "🍜 Ẩm thực": "🍜 식당",
        "🌐 Website Suối Tiên": "🌐 공식 웹사이트",
    },
    "ja": {
        "🎫 Bảng giá vé": "🎫 料金表", "🛒 Mua vé online": "🛒 オンライン購入",
        "📍 Xem bản đồ": "📍 地図を見る", "ℹ️ Liên hệ": "ℹ️ 連絡先",
        "📞 Liên hệ": "📞 お問い合わせ", "🚇 Metro số 1": "🚇 メトロ1号線",
        "🎢 Khu vui chơi": "🎢 アトラクション", "🎫 Mua vé": "🎫 チケット購入",
        "🌿 Suối Tiên Farm": "🌿 ファーム体験", "🎉 Sự kiện & Ưu đãi": "🎉 イベント＆特典",
        "🎁 Ưu đãi hiện tại": "🎁 キャンペーン", "🏕️ Teambuilding": "🏕️ チームビルディング",
        "📞 Liên hệ đặt lịch": "📞 予約・お問い合わせ", "🍜 Ẩm thực": "🍜 レストラン",
        "🌐 Website Suối Tiên": "🌐 公式ウェブサイト",
    },
}


def get_item_link(name: str) -> dict | None:
    """Tìm link cho attraction/restaurant theo tên."""
    # Exact match
    if name in ATT_MAP:
        return {"label": f"🔗 {name[:35]}", "url": ATT_MAP[name]}
    if name in REST_MAP:
        return {"label": f"🍜 {name[:35]}", "url": REST_MAP[name]}
    # Partial match
    name_lower = name.lower()
    for k, v in ATT_MAP.items():
        if name_lower in k.lower() or k.lower() in name_lower:
            return {"label": f"🔗 {k[:35]}", "url": v}
    for k, v in REST_MAP.items():
        if name_lower in k.lower() or k.lower() in name_lower:
            return {"label": f"🍜 {k[:35]}", "url": v}
    return None


# API layer truyền TÊN TOOL của planner (vd "search_tickets") làm intent, trong khi
# _INTENT_LINKS dùng khoá "hoi_*" → link rơi về trang chủ. Map lại cho đúng nhóm.
_TOOL_TO_INTENT = {
    "search_tickets":      "hoi_gia_ve",
    "search_attractions":  "hoi_tro_choi",
    "search_restaurants":  "hoi_nha_hang",
    "search_events":       "hoi_su_kien",
    "search_teambuilding": "hoi_teambuilding",
    "get_park_info":       "hoi_gio_mo_cua",
    "get_directions":      "hoi_duong_di",
    "get_weather":         "hoi_chung",
    "faq":                 "hoi_chung",
}


def get_intent_links(intent: str, lang: str = "vi") -> list[dict]:
    intent = _TOOL_TO_INTENT.get(intent, intent)
    # FAQ trả rule dạng "gia_ve"/"gio_mo_cua" → khớp khoá "hoi_gia_ve"...
    if intent not in _INTENT_LINKS and f"hoi_{intent}" in _INTENT_LINKS:
        intent = f"hoi_{intent}"
    links = _INTENT_LINKS.get(intent, _INTENT_LINKS.get("hoi_chung", []))
    label_map = _LABEL_MAP.get(lang, {})
    return [{"label": label_map.get(l["label"], l["label"]), "url": l["url"]} for l in links]


def get_slug_links(results: list[dict], max_links: int = 2) -> list[dict]:
    seen = set()
    links = []
    for item in results:
        # Try to get link from ATT_MAP/REST_MAP by name first
        name = item.get("name","").strip()
        if name:
            link = get_item_link(name)
            if link and link["url"] not in seen:
                seen.add(link["url"])
                links.append(link)
                if len(links) >= max_links: break
                continue
        # Fallback to source_slug
        slug = item.get("source_slug") or item.get("slug","")
        title = item.get("title") or name
        if slug and slug not in seen:
            seen.add(slug)
            url = f"{BASE_URL}/{slug}"
            links.append({"label": f"🔗 {title[:35]}" if title else f"🔗 {slug}", "url": url})
        if len(links) >= max_links: break
    return links


def build_links(intent: str, results: list[dict], source: str,
                lang: str = "vi", max_total: int = 3) -> list[dict]:
    if source in ("faq", "schema"):
        # For schema with named items, add their specific links
        item_links = []
        for item in results[:2]:
            name = item.get("name","").strip()
            if name:
                link = get_item_link(name)
                if link: item_links.append(link)
        if item_links:
            intent_links = get_intent_links(intent, lang)[:1]
            all_links = item_links + intent_links
        else:
            all_links = get_intent_links(intent, lang)
    else:
        slug_links   = get_slug_links(results, max_links=max_total - 1)
        intent_links = get_intent_links(intent, lang)[:1]
        all_links    = slug_links + intent_links

    # Dedup
    seen_urls = set()
    final = []
    for link in all_links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            final.append(link)
    return final[:max_total]


def format_links_markdown(links: list[dict]) -> str:
    if not links: return ""
    return "\n\n" + " • ".join(f"[{l['label']}]({l['url']})" for l in links)


if __name__ == "__main__":
    print("=== LINK SERVICE TEST ===\n")
    # Test item lookup
    for name in ["Go Kart – Đường Đua Tốc Độ", "Cung Đình Tửu", "Infinity Slide", "Vương Quốc Cá Sấu"]:
        link = get_item_link(name)
        print(f"  {name:40s} → {link}")
    print()
    # Test build_links
    tests = [
        ("hoi_gia_ve", "vi", "faq", []),
        ("hoi_tro_choi", "en", "schema", [{"name":"Go Kart – Đường Đua Tốc Độ"}]),
        ("hoi_nha_hang", "zh", "schema", [{"name":"Cung Đình Tửu"}]),
    ]
    for intent, lang, source, results in tests:
        links = build_links(intent, results, source, lang)
        print(f"[{intent}][{lang}][{source}]")
        for l in links: print(f"  → {l['label']} : {l['url']}")
        print()
