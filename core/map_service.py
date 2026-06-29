"""
map_service.py — Google Maps integration cho Suối Tiên Bot
- Embed map iframe (Google Maps)
- Directions link + static info
- Khi có Google Maps API key → dùng Places/Directions API
"""

import os

GMAPS_KEY   = os.getenv("GOOGLE_MAPS_KEY", "")
PLACE_ID    = "ChIJb1Gm0MkodTERq2oPDO7HQCA"  # Suối Tiên Place ID
LAT         = 10.8415
LON         = 106.7717
ADDRESS     = "120 Xa Lộ Hà Nội, P. Tăng Nhơn Phú, TP. Thủ Đức, TP.HCM"
MAPS_LINK   = f"https://maps.google.com/?q={LAT},{LON}"
EMBED_URL   = f"https://maps.google.com/maps?q={LAT},{LON}&z=16&output=embed"

# Metro line 1 station gần nhất
METRO_STATION = "Suối Tiên (ga cuối Metro số 1)"
METRO_LINK    = "https://maps.app.goo.gl/suoitien"


def get_map_url() -> str:
    """Trả về Google Maps URL."""
    if GMAPS_KEY:
        return f"https://www.google.com/maps/place/?q=place_id:{PLACE_ID}"
    return MAPS_LINK


def get_embed_html(width: str = "100%", height: str = "300") -> str:
    """Trả về iframe HTML để nhúng vào UI."""
    if GMAPS_KEY:
        src = f"https://www.google.com/maps/embed/v1/place?key={GMAPS_KEY}&q=place_id:{PLACE_ID}&zoom=16"
    else:
        src = EMBED_URL
    return (
        f'<iframe src="{src}" width="{width}" height="{height}" '
        f'style="border:0;border-radius:12px;" allowfullscreen loading="lazy"></iframe>'
    )


def format_directions(lang: str = "vi") -> str:
    """Format hướng dẫn đường đến theo ngôn ngữ."""
    maps_link  = get_map_url()
    maps_label = {
        "vi": "📍 Xem bản đồ",
        "en": "📍 View on Maps",
        "zh": "📍 查看地图",
        "ko": "📍 지도 보기",
        "ja": "📍 地図を見る",
    }

    templates = {
        "vi": (
            f"📍 **Địa chỉ:** {ADDRESS}\n\n"
            f"**🚇 Metro số 1 (sắp khai thác):** Ga cuối tuyến là ga Suối Tiên, ngay trước cổng công viên.\n\n"
            f"**🚌 Xe buýt:** Tuyến 19 (Bến Thành – Suối Tiên), tuyến 53\n\n"
            f"**🚗 Xe máy/Ô tô:** Theo Xa Lộ Hà Nội hướng Thủ Đức, đến số 120.\n"
            f"Bãi đỗ xe rộng, miễn phí trong khuôn viên.\n\n"
            f"[{maps_label['vi']}]({maps_link})"
        ),
        "en": (
            f"📍 **Address:** {ADDRESS}\n\n"
            f"**🚇 Metro Line 1 (now open):** Take the metro to the last stop **Suoi Tien** — "
            f"the park entrance is right in front of you! Buy tickets at the station kiosks.\n\n"
            f"**🚌 Bus:** Route **19** (Ben Thanh – Suoi Tien), Route **53**\n\n"
            f"**🚗 Car/Motorbike:** Follow Hanoi Highway toward Thu Duc District, stop at No. **120**.\n"
            f"**Free parking** available inside the park.\n\n"
            f"[{maps_label['en']}]({maps_link})"
        ),
        "zh": (
            f"📍 **地址：** {ADDRESS}\n\n"
            f"**🚇 地铁1号线（已开通）：** 乘地铁至终点站 **碎仙站** — 出站即是公园入口！"
            f"可在站内自动售票机购票。\n\n"
            f"**🚌 公共汽车：** **19路**（滨城 – 碎仙），**53路**\n\n"
            f"**🚗 自驾：** 沿河内大道方向前往守德区，到 **120号** 停车。\n"
            f"园区内提供**免费**停车位。\n\n"
            f"[{maps_label['zh']}]({maps_link})"
        ),
        "ko": (
            f"📍 **주소:** {ADDRESS}\n\n"
            f"**🚇 메트로 1호선 (개통):** 종점 **수오이티엔역**에서 하차 — 바로 앞이 공원 입구! "
            f"역 내 자동발매기에서 승차권 구매 가능.\n\n"
            f"**🚌 버스:** **19번** (벤탄 – 수오이티엔), **53번**\n\n"
            f"**🚗 자동차/오토바이:** 하노이 대로를 따라 투득구 방향, **120번지**에서 정차.\n"
            f"원내 **무료** 주차 가능.\n\n"
            f"[{maps_label['ko']}]({maps_link})"
        ),
        "ja": (
            f"📍 **住所：** {ADDRESS}\n\n"
            f"**🚇 メトロ1号線（開通済み）：** 終点 **スオイティエン駅** で下車 — すぐ目の前が公園入口！"
            f"駅の自動券売機でチケットを購入できます。\n\n"
            f"**🚌 バス：** **19番**（ベンタン – スオイティエン）、**53番**\n\n"
            f"**🚗 車/バイク：** ハノイ通りをトゥードゥク区方面へ進み、**120番地**で停車。\n"
            f"園内に**無料**駐車場あり。\n\n"
            f"[{maps_label['ja']}]({maps_link})"
        ),
    }
    return templates.get(lang, templates["vi"])


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== MAP SERVICE TEST ===\n")
    print("Maps URL:", get_map_url())
    print()
    for lang in ["vi", "en", "zh"]:
        print(f"[{lang}]")
        print(format_directions(lang))
        print()
