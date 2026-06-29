"""
guardrail.py — Safety layer cho Suối Tiên Bot

Chạy TRƯỚC khi query vào Planner và SAU khi Responder sinh câu trả lời.

Bảo vệ:
1. Prompt injection / jailbreak
2. Câu hỏi ngoài domain (tư vấn pháp lý, y tế, chính trị...)
3. PII detection (số CCCD, số thẻ tín dụng...)
4. Hallucination check trên output (giá/tên không có trong context)
5. Toxic / offensive input
"""
import re
import os
import logging
from typing import Optional

logger = logging.getLogger("suoitien.guardrail")

# ── 1. Prompt injection patterns ───────────────────────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore (previous|above|all) (instructions?|prompts?|rules?)",
        r"forget (everything|your instructions?|your rules?)",
        r"(reveal|show|print|display|repeat) (your |the )?(system ?)?(prompt|instructions?)",
        r"you are now (a |an )?(different|new|another|evil|unrestricted)",
        r"act as (if you (are|were)|a|an) .{0,40}(without|no) (restrictions?|limits?|rules?|filters?)",
        r"pretend (you (are|have no)|there (are|is) no)",
        r"(DAN|jailbreak|do anything now)",
        r"override (your |the )?(safety|restrictions?|guidelines?|rules?)",
        r"(bypass|disable|remove) (your )?(filter|safety|guardrail|restriction)",
        r"(tiết lộ|cho xem|hiện ra|in ra) (prompt|hướng dẫn hệ thống|system)",
    ]
]

# ── 2. Out-of-domain patterns ──────────────────────────────────────────────────
_OOD_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(chẩn đoán|chữa bệnh|thuốc|liều dùng|triệu chứng)",
        r"(tư vấn pháp lý|luật sư|kiện|tòa án|hợp đồng pháp)",
        r"(cổ phiếu|chứng khoán|đầu tư|crypto|bitcoin|forex)",
        r"(chính trị|bầu cử|đảng|tổng thống|thủ tướng)",
        r"(hack|crack|exploit|malware|virus|ddos)",
        r"(vũ khí|chất nổ|chất độc|ma túy)",
    ]
]

# ── 3. PII patterns ────────────────────────────────────────────────────────────
_PII_PATTERNS = [
    (re.compile(r"\b\d{9,12}\b"), "ID number"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "card number"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "email"),
]

# ── 4. Toxic patterns ──────────────────────────────────────────────────────────
_TOXIC_THRESHOLD = 3
_TOXIC_WORDS = {
    "đồ ngu", "đồ chó", "địt", "dm", "dcm", "mẹ mày", "thằng khốn",
    "fuck", "shit", "bitch", "asshole", "idiot"
}


class GuardrailResult:
    def __init__(self, passed: bool, reason: str = "", action: str = "block",
                 cleaned_query: str = ""):
        self.passed        = passed
        self.reason        = reason
        self.action        = action   # "block" | "warn" | "pass"
        self.cleaned_query = cleaned_query


def check_input(query: str, lang: str = "vi") -> GuardrailResult:
    """
    Kiểm tra input trước khi vào pipeline.
    Returns GuardrailResult — nếu passed=False thì block, không gọi LLM.
    """
    q = query.strip()
    q_lower = q.lower()

    # 1. Prompt injection
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(q):
            logger.warning("GUARDRAIL: prompt injection detected: %s", q[:80])
            return GuardrailResult(
                passed=False, action="block", reason="prompt_injection",
                cleaned_query=""
            )

    # 2. Out of domain
    for pattern in _OOD_PATTERNS:
        if pattern.search(q):
            logger.info("GUARDRAIL: out-of-domain: %s", q[:80])
            return GuardrailResult(
                passed=False, action="block", reason="out_of_domain",
                cleaned_query=""
            )

    # 3. PII — warn nhưng vẫn cho qua, strip PII
    cleaned = q
    pii_found = []
    for pattern, pii_type in _PII_PATTERNS:
        if pattern.search(q):
            pii_found.append(pii_type)
            cleaned = pattern.sub("[REDACTED]", cleaned)
    if pii_found:
        logger.info("GUARDRAIL: PII detected (%s), redacted", pii_found)
        return GuardrailResult(
            passed=True, action="warn", reason="pii_redacted",
            cleaned_query=cleaned
        )

    # 4. Toxic
    toxic_count = sum(1 for w in _TOXIC_WORDS if w in q_lower)
    if toxic_count >= _TOXIC_THRESHOLD:
        logger.warning("GUARDRAIL: toxic input: %s", q[:80])
        return GuardrailResult(
            passed=False, action="block", reason="toxic",
            cleaned_query=""
        )

    return GuardrailResult(passed=True, action="pass", cleaned_query=q)


def check_output(answer: str, context: str, lang: str = "vi") -> GuardrailResult:
    """
    Kiểm tra output sau khi Responder sinh câu trả lời.
    Phát hiện hallucination cơ bản: giá tiền trong answer có trong context không?
    """
    # Extract giá từ answer
    price_pattern = re.compile(r"(\d{2,3}[\.,]\d{3}|\d{3,})(?:đ|đồng|VND|k\b)", re.IGNORECASE)
    answer_prices = set(price_pattern.findall(answer))

    if not answer_prices or not context:
        return GuardrailResult(passed=True, action="pass")

    # Check từng giá có xuất hiện trong context không
    hallucinated = []
    for price in answer_prices:
        price_clean = price.replace(".", "").replace(",", "")
        if price_clean not in context.replace(".", "").replace(",", ""):
            hallucinated.append(price)

    if hallucinated:
        logger.warning("GUARDRAIL: possible hallucinated prices: %s", hallucinated)
        return GuardrailResult(
            passed=True, action="warn", reason=f"hallucinated_prices:{hallucinated}"
        )

    return GuardrailResult(passed=True, action="pass")


# ── Block messages theo ngôn ngữ ────────────────────────────────────────────────
BLOCK_MESSAGES = {
    "prompt_injection": {
        "vi": "Em chỉ hỗ trợ thông tin về Suối Tiên thôi anh/chị ơi! Anh/chị cần biết gì về công viên không?",
        "en": "I'm here to help with Suoi Tien information only! What would you like to know about the park?",
        "zh": "我只能提供关于水仙公园的信息。请问您想了解什么？",
        "ko": "수오이띠엔 공원 정보만 안내해 드릴 수 있어요. 무엇이 궁금하신가요?",
        "ja": "スオイティエン公園の情報のみご案内できます。何かお聞きになりたいことはありますか？",
    },
    "out_of_domain": {
        "vi": "Câu hỏi này nằm ngoài phạm vi hỗ trợ của em. Em chỉ tư vấn về Công viên Suối Tiên thôi ạ!",
        "en": "That's outside my area — I only provide information about Suoi Tien Cultural Theme Park.",
        "zh": "这超出了我的服务范围。我只提供水仙文化主题公园的相关信息。",
        "ko": "이 질문은 제 도움 범위 밖입니다. 수오이띠엔 공원 정보만 안내해 드려요.",
        "ja": "それは私のサポート範囲外です。スオイティエンテーマパークの情報のみご案内しています。",
    },
    "toxic": {
        "vi": "Anh/chị ơi, mình nói chuyện lịch sự nhé! Em vẫn sẵn sàng giúp anh/chị tìm hiểu về Suối Tiên ạ.",
        "en": "Let's keep things friendly! I'm happy to help with Suoi Tien information.",
        "zh": "请保持友好的交流方式！我很乐意为您提供水仙公园的信息。",
        "ko": "정중하게 대화해 주세요! 수오이띠엔 정보를 안내해 드릴게요.",
        "ja": "丁寧にお話しください！スオイティエンの情報をご案内します。",
    },
}

def get_block_message(reason: str, lang: str = "vi") -> str:
    base_reason = reason.split(":")[0]
    messages = BLOCK_MESSAGES.get(base_reason, BLOCK_MESSAGES["out_of_domain"])
    return messages.get(lang, messages["vi"])
