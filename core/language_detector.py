"""
language_detector.py — Detect ngôn ngữ từ user query
Hỗ trợ: vi (Vietnamese), en (English), zh (Chinese), ko (Korean)
Strategy: rule-based trước (nhanh), LLM fallback nếu không chắc
"""

import re
import os
from typing import Optional

SUPPORTED_LANGS = {"vi", "en", "zh", "ko", "ja"}
DEFAULT_LANG    = "vi"

# ── Unicode ranges ─────────────────────────────────────────────────────────────
_ZH_RE  = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")          # CJK
_KO_RE  = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")  # Hangul
_JA_RE  = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")                  # Hiragana/Katakana
_VI_RE  = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]", re.IGNORECASE)

# Vietnamese common words — CÓ DẤU và KHÔNG DẤU (khách VN hay gõ không dấu)
_VI_WORDS = {
    # có dấu
    "và","của","có","là","được","cho","với","trong","tại","về","các","những",
    "này","đó","một","không","hay","rất","cũng","như","khi","đến","từ","theo",
    "ở","đâu","bao","nhiêu","gì","sao","thế","nào","đi","chơi","vé","giá","hỏi",
    "mình","em","anh","chị","bạn","xin","cảm","ơn","người","lớn","trẻ","giờ",
    "mở","cửa","đường","mua","đặt","liên","hệ","muốn","cần","ăn","uống","xe","buýt",
    # không dấu (bản gõ nhanh)
    "cua","co","la","duoc","voi","cac","nhung","nay","mot","khong","nhu","den",
    "dau","nhieu","gi","the","nao","di","choi","ve","gia","hoi","minh","anh","chi",
    "ban","xin","cam","on","nguoi","lon","tre","gio","mo","cua","duong","mua","dat",
    "lien","he","muon","can","an","uong","xe","buyt","may","con","het","toi","o",
}
_EN_WORDS = {
    "the","is","are","was","were","have","has","do","does","will","would",
    "can","could","how","what","where","when","who","why","which","please",
    "ticket","tickets","price","open","close","game","games","food","tour","visit","fun","park","ride","rides","show","shows","kids","children","family","water","pool","map","hotel","book","booking","buy","entrance","entrance","resort","attraction","attractions",
    "i","you","we","they","he","she","it","my","your","our",
    "hello","hi","hey","thanks","thank","yes","hours","cost","much","get","there","here","near",
}
_ZH_WORDS = {"吗","的","了","是","有","在","我","你","他","她","们","这","那","票","价","玩"}
_KO_WORDS = {"이","가","을","를","은","는","의","에","에서","으로","로","와","과","도","만"}
_JA_WORDS = {"の","は","が","を","に","で","と","も","な","か","です","ます","ある","いる"}


def detect_lang(text: str) -> str:
    """
    Detect ngôn ngữ từ text.
    Returns: 'vi' | 'en' | 'zh' | 'ko'
    """
    text = text.strip()
    if not text:
        return DEFAULT_LANG

    # Score theo script
    zh_count = len(_ZH_RE.findall(text))
    ko_count = len(_KO_RE.findall(text))
    vi_count = len(_VI_RE.findall(text))

    # Script-based detection (high confidence)
    total_chars = max(len(text), 1)
    ja_count = len(_JA_RE.findall(text))
    if ko_count / total_chars > 0.15:
        return "ko"
    if ja_count / total_chars > 0.1:
        return "ja"
    if zh_count / total_chars > 0.15:
        return "zh"
    if vi_count / total_chars > 0.08:
        return "vi"

    # Word-based detection
    words = set(re.findall(r"[a-zA-ZÀ-ỹ]+", text.lower()))
    vi_score = len(words & _VI_WORDS)
    en_score = len(words & _EN_WORDS)

    # Short query (1-2 words) toàn Latin, KHÔNG khớp từ VN nào, có tín hiệu EN → EN
    # VD: "ticket", "open", "food", "show", "ride", "water park"
    latin_words = [w for w in words if w.isascii()]
    if len(words) <= 3 and latin_words and vi_score == 0 and en_score > 0:
        return "en"

    # Bot ưu tiên tiếng Việt: EN chỉ thắng khi ÁP ĐẢO (nhiều từ EN hơn từ VN),
    # tránh 1 từ VN không dấu trùng từ chức năng EN ("he"=hệ, "the"=thế) lật sang EN.
    if en_score > vi_score:
        return "en"
    if vi_score > 0:
        return "vi"

    # Không rõ tín hiệu — mặc định tiếng Việt (khách chủ yếu là người Việt)
    return DEFAULT_LANG


# ── Response templates per language ───────────────────────────────────────────
LANG_CONFIG = {
    "vi": {
        "name": "Tiếng Việt",
        "system_suffix": "Trả lời bằng tiếng Việt.",
        "fallback": "Xin lỗi, mình chưa tìm thấy thông tin phù hợp. Vui lòng gọi **1900 636 787** hoặc truy cập **suoitien.vn**!",
        "greeting": "Xin chào! Tôi là trợ lý của Suối Tiên. Bạn cần hỗ trợ gì?",
        "error": "Không thể kết nối. Vui lòng gọi 1900 636 787.",
        "quick_replies": [
            ("🎫 Giá vé", "Giá vé vào cổng là bao nhiêu?"),
            ("🎢 Trò chơi", "Có những trò chơi gì?"),
            ("🍜 Ẩm thực", "Nhà hàng nào ngon?"),
            ("🚇 Đường đi", "Đi metro đến Suối Tiên được không?"),
            ("🌤️ Thời tiết", "Thời tiết hôm nay ở Suối Tiên?"),
            ("🏕️ Teambuilding", "Có gói teambuilding không?"),
        ],
    },
    "en": {
        "name": "English",
        "system_suffix": "Reply in English. Keep it friendly and concise.",
        "fallback": "Sorry, I couldn't find relevant information. Please call **1900 636 787** or visit **suoitien.vn**!",
        "greeting": "Hello! I'm Suoi Tien's assistant. How can I help you?",
        "error": "Cannot connect to server. Please call 1900 636 787.",
        "quick_replies": [
            ("🎫 Ticket Price", "How much is the entrance ticket?"),
            ("🎢 Attractions", "What attractions are available?"),
            ("🍜 Dining", "What restaurants are there?"),
            ("🚇 Directions", "How do I get to Suoi Tien?"),
            ("🌤️ Weather", "What's the weather like today?"),
            ("🏕️ Team Building", "Do you have team building packages?"),
        ],
    },
    "zh": {
        "name": "中文",
        "system_suffix": "请用中文回答。保持友好简洁。",
        "fallback": "抱歉，暂时找不到相关信息。请致电 **1900 636 787** 或访问 **suoitien.vn**！",
        "greeting": "您好！我是碎仙公园的助手。有什么可以帮助您？",
        "error": "无法连接服务器。请致电 1900 636 787。",
        "quick_replies": [
            ("🎫 门票价格", "门票多少钱？"),
            ("🎢 游乐设施", "有哪些游乐设施？"),
            ("🍜 餐饮", "有哪些餐厅？"),
            ("🚇 交通指南", "如何前往碎仙公园？"),
            ("🌤️ 天气", "今天天气怎么样？"),
            ("🏕️ 团队活动", "有团队建设套餐吗？"),
        ],
    },
    "ko": {
        "name": "한국어",
        "system_suffix": "한국어로 답변해 주세요. 친절하고 간결하게.",
        "fallback": "죄송합니다. 관련 정보를 찾을 수 없습니다. **1900 636 787**로 전화하거나 **suoitien.vn**을 방문해 주세요!",
        "greeting": "안녕하세요! 수오이 티엔 공원 안내원입니다. 무엇을 도와드릴까요?",
        "error": "서버에 연결할 수 없습니다. 1900 636 787로 전화해 주세요.",
        "quick_replies": [
            ("🎫 입장권 가격", "입장권 가격이 얼마예요?"),
            ("🎢 놀이시설", "어떤 놀이시설이 있나요?"),
            ("🍜 식당", "어떤 식당이 있나요?"),
            ("🚇 오시는 길", "수오이 티엔까지 어떻게 가나요?"),
            ("🌤️ 날씨", "오늘 날씨는 어떤가요?"),
            ("🏕️ 팀빌딩", "팀빌딩 패키지가 있나요?"),
        ],
    },
    "ja": {
        "name": "日本語",
        "system_suffix": "日本語で回答してください。親切で簡潔に。",
        "fallback": "申し訳ありません。該当する情報が見つかりませんでした。**1900 636 787**にお電話いただくか、**suoitien.vn**をご覧ください！",
        "greeting": "こんにちは！スオイティエン公園のアシスタントです。何かお手伝いできますか？",
        "error": "サーバーに接続できません。1900 636 787にお電話ください。",
        "quick_replies": [
            ("🎫 入場券", "入場券はいくらですか？"),
            ("🎢 アトラクション", "どんなアトラクションがありますか？"),
            ("🍜 レストラン", "どんなレストランがありますか？"),
            ("🚇 アクセス", "スオイティエンへの行き方は？"),
            ("🌤️ 天気", "今日の天気はどうですか？"),
            ("🏕️ チームビルディング", "チームビルディングのパッケージはありますか？"),
        ],
    },
}

def get_lang_config(lang: str) -> dict:
    return LANG_CONFIG.get(lang, LANG_CONFIG["vi"])


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("Giá vé bao nhiêu?", "vi"),
        ("How much is the ticket?", "en"),
        ("门票多少钱？", "zh"),
        ("입장권 가격이 얼마예요?", "ko"),
        ("Go Kart ở đâu?", "vi"),
        ("What time does it open?", "en"),
        ("有哪些游乐设施？", "zh"),
        ("어떤 놀이시설이 있나요?", "ko"),
        ("hello how are you", "en"),
        ("入場券はいくらですか？", "ja"),
        ("どんなアトラクションがありますか？", "ja"),
    ]
    print("=== LANGUAGE DETECTOR TEST ===\n")
    for text, expected in tests:
        detected = detect_lang(text)
        status = "✅" if detected == expected else "❌"
        print(f"{status} '{text[:35]:35s}' → {detected} (expected {expected})")
