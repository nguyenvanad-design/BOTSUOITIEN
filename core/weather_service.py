"""
weather_service.py — OpenWeatherMap integration cho Suối Tiên Bot
Lấy thời tiết thực tế tại Suối Tiên (TP. Thủ Đức, TP.HCM)
"""

import os
import time
import requests
from datetime import datetime

# API key CHỈ đọc từ env — KHÔNG hardcode key vào source code.
# Key cũ trong code đã bị lộ + trả 403; cần revoke và tạo key mới tại
# openweathermap.org, rồi set: export OWM_API_KEY=...
OWM_KEY  = os.getenv("OWM_API_KEY", "")
LAT      = 10.8415   # Suối Tiên latitude
LON      = 106.7717  # Suối Tiên longitude
LANG_OWM = "vi"      # OWM description language
UNITS    = "metric"  # Celsius

# Cache để tránh spam API (5 phút)
_cache = {"data": None, "ts": 0}
CACHE_TTL = 300  # seconds


def _get_weather_raw() -> dict | None:
    """Gọi OWM API, trả về raw JSON."""
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    url = "https://api.openweathermap.org/data/2.5/weather"
    if not OWM_KEY:
        return None  # chưa cấu hình OWM_API_KEY → bot trả lời không kèm thời tiết
    params = {
        "lat":   LAT,
        "lon":   LON,
        "appid": OWM_KEY,
        "units": UNITS,
        "lang":  LANG_OWM,
    }
    try:
        resp = requests.get(url, params=params, timeout=2)
        resp.raise_for_status()
        data = resp.json()
        _cache["data"] = data
        _cache["ts"]   = now
        return data
    except Exception as e:
        print(f"[weather] OWM error: {e}")
        return None


def _emoji(weather_id: int, icon: str) -> str:
    """Map OWM weather code → emoji."""
    if weather_id >= 800:
        return "☀️" if "d" in icon else "🌙"
    if weather_id == 800: return "☀️"
    if weather_id >= 700: return "🌫️"
    if weather_id >= 600: return "❄️"
    if weather_id >= 500: return "🌧️"
    if weather_id >= 300: return "🌦️"
    if weather_id >= 200: return "⛈️"
    return "🌤️"


def get_weather(lang: str = "vi") -> dict | None:
    """
    Lấy thời tiết hiện tại tại Suối Tiên.
    Returns dict hoặc None nếu lỗi.
    """
    raw = _get_weather_raw()
    if not raw:
        return None

    weather = raw["weather"][0]
    main    = raw["main"]
    wind    = raw.get("wind", {})
    emoji   = _emoji(weather["id"], weather.get("icon",""))

    temp      = round(main["temp"])
    feels     = round(main["feels_like"])
    humidity  = main["humidity"]
    wind_spd  = round(wind.get("speed", 0) * 3.6)  # m/s → km/h
    desc      = weather["description"].capitalize()

    # Tip theo thời tiết
    tips = {
        "vi": {
            "hot":  "☀️ Trời nóng — nhớ mang nón & kem chống nắng!",
            "rain": "🌧️ Có mưa — nhớ mang áo mưa hoặc ô!",
            "ok":   "🌤️ Thời tiết dễ chịu — thích hợp tham quan!",
        },
        "en": {
            "hot":  "☀️ Hot weather — bring sunscreen & a hat!",
            "rain": "🌧️ Rainy — bring an umbrella or raincoat!",
            "ok":   "🌤️ Nice weather — perfect for visiting!",
        },
        "zh": {
            "hot":  "☀️ 天气炎热 — 请带防晒霜和帽子！",
            "rain": "🌧️ 有雨 — 请带雨伞或雨衣！",
            "ok":   "🌤️ 天气宜人 — 非常适合游览！",
        },
        "ko": {
            "hot":  "☀️ 더운 날씨 — 선크림과 모자를 챙기세요!",
            "rain": "🌧️ 비 예보 — 우산이나 우비를 준비하세요!",
            "ok":   "🌤️ 좋은 날씨 — 방문하기 딱 좋아요!",
        },
        "ja": {
            "hot":  "☀️ 暑い天気です — 日焼け止めと帽子をお持ちください！",
            "rain": "🌧️ 雨の予報 — 傘やレインコートをご準備ください！",
            "ok":   "🌤️ 過ごしやすい天気 — 観光に最適です！",
        },
    }
    t = tips.get(lang, tips["vi"])
    if weather["id"] >= 500:
        tip = t["rain"]
    elif temp >= 35:
        tip = t["hot"]
    else:
        tip = t["ok"]

    return {
        "emoji":    emoji,
        "temp":     temp,
        "feels":    feels,
        "humidity": humidity,
        "wind_kph": wind_spd,
        "desc":     desc,
        "tip":      tip,
        "lang":     lang,
    }


def format_weather(lang: str = "vi") -> str:
    """Format thời tiết thành text cho bot response."""
    w = get_weather(lang)
    if not w:
        msgs = {
            "vi": "Không thể lấy thông tin thời tiết. Vui lòng thử lại sau.",
            "en": "Unable to fetch weather data. Please try again later.",
            "zh": "无法获取天气信息，请稍后再试。",
            "ko": "날씨 정보를 가져올 수 없습니다. 나중에 다시 시도해 주세요.",
            "ja": "天気情報を取得できません。後でもう一度お試しください。",
        }
        return msgs.get(lang, msgs["vi"])

    templates = {
        "vi": (
            f"{w['emoji']} **Thời tiết tại Suối Tiên:**\n"
            f"🌡️ **{w['temp']}°C** (cảm giác {w['feels']}°C)\n"
            f"☁️ {w['desc']}\n"
            f"💧 Độ ẩm: {w['humidity']}% | 💨 Gió: {w['wind_kph']} km/h\n\n"
            f"{w['tip']}"
        ),
        "en": (
            f"{w['emoji']} **Weather at Suoi Tien:**\n"
            f"🌡️ **{w['temp']}°C** (feels like {w['feels']}°C)\n"
            f"☁️ {w['desc']}\n"
            f"💧 Humidity: {w['humidity']}% | 💨 Wind: {w['wind_kph']} km/h\n\n"
            f"{w['tip']}"
        ),
        "zh": (
            f"{w['emoji']} **碎仙公园天气：**\n"
            f"🌡️ **{w['temp']}°C**（体感 {w['feels']}°C）\n"
            f"☁️ {w['desc']}\n"
            f"💧 湿度：{w['humidity']}% | 💨 风速：{w['wind_kph']} km/h\n\n"
            f"{w['tip']}"
        ),
        "ko": (
            f"{w['emoji']} **수오이 티엔 날씨:**\n"
            f"🌡️ **{w['temp']}°C** (체감 {w['feels']}°C)\n"
            f"☁️ {w['desc']}\n"
            f"💧 습도: {w['humidity']}% | 💨 바람: {w['wind_kph']} km/h\n\n"
            f"{w['tip']}"
        ),
        "ja": (
            f"{w['emoji']} **スオイティエンの天気：**\n"
            f"🌡️ **{w['temp']}°C**（体感 {w['feels']}°C）\n"
            f"☁️ {w['desc']}\n"
            f"💧 湿度：{w['humidity']}% | 💨 風速：{w['wind_kph']} km/h\n\n"
            f"{w['tip']}"
        ),
    }
    return templates.get(lang, templates["vi"])


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== WEATHER SERVICE TEST ===\n")
    for lang in ["vi", "en", "zh", "ko", "ja"]:
        print(f"[{lang}]")
        print(format_weather(lang))
        print()
