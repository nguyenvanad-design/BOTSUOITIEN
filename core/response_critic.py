"""
response_critic.py — Response Critic + Golden Store cho Suối Tiên Bot

KIẾN TRÚC:
┌─────────────────────────────────────────────────────┐
│  GOLDEN STORE (SQLite)                              │
│  - Câu trả lời chuẩn do NGƯỜI xác nhận (👍)        │
│  - Ground truth để Critic so sánh                  │
│  - Không bao giờ bị ghi đè bởi LLM                │
└──────────────────┬──────────────────────────────────┘
                   │ so sánh
┌──────────────────▼──────────────────────────────────┐
│  RESPONSE CRITIC (LLM)                              │
│  Không chỉ chấm điểm — phân tích sâu:              │
│  1. So sánh với golden answer (nếu có)             │
│  2. Detect lỗi pattern (hallucinate/xin lỗi/sáo)  │
│  3. Đưa ra verdict: PASS / IMPROVE / REJECT        │
│  4. Ghi lỗi pattern vào ErrorPatternDB             │
└──────────────────┬──────────────────────────────────┘
                   │ feed back
┌──────────────────▼──────────────────────────────────┐
│  PATTERN LEARNER                                    │
│  - Thống kê lỗi lặp lại nhiều nhất                │
│  - Tự động thêm vào RESPONDER_SYSTEM prompt        │
│  - "Bot hay xin lỗi vô cớ" → thêm rule chặn       │
└─────────────────────────────────────────────────────┘
"""

import os
import json
import time
import sqlite3
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional
from collections import Counter

import llm_client

logger = logging.getLogger("suoitien.critic")

DB_PATH = Path(os.getenv("SUOITIEN_BASE", "core")) / "data" / "learning.db"
# RLock (không phải Lock): nhiều helper DB gọi lồng nhau — Lock thường sẽ tự
# khoá chết thread và treo toàn bộ bot (đã từng xảy ra ở critique_and_learn).
_db_lock = threading.RLock()

# ── Verdict constants ──────────────────────────────────────────────────────────
VERDICT_PASS    = "PASS"     # >= 8/10, không cần sửa
VERDICT_IMPROVE = "IMPROVE"  # 5-7/10, tự sửa được
VERDICT_REJECT  = "REJECT"   # < 5/10 hoặc có lỗi nghiêm trọng

# ── Error patterns hay gặp ─────────────────────────────────────────────────────
ERROR_PATTERNS = {
    "unnecessary_apology":  "Bot xin lỗi vô cớ dù có đủ thông tin",
    "hallucinate_price":     "Bot bịa giá không có trong Tool Results",
    "hallucinate_name":      "Bot bịa tên combo/trò chơi không có trong data",
    "too_long":              "Câu trả lời quá dài, lan man",
    "missing_key_info":      "Thiếu thông tin quan trọng khách cần",
    "wrong_language":        "Trả lời sai ngôn ngữ",
    "generic_response":      "Câu trả lời quá chung chung, không cụ thể",
    "redirect_without_info": "Chỉ đẩy về hotline mà không trả lời câu hỏi",
}


# ── Database init ──────────────────────────────────────────────────────────────
def init_critic_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            -- Golden Store: câu trả lời chuẩn do người xác nhận
            CREATE TABLE IF NOT EXISTS golden_store (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash   TEXT NOT NULL UNIQUE,
                query        TEXT NOT NULL,
                context_hash TEXT,
                answer       TEXT NOT NULL,
                source       TEXT DEFAULT 'human',  -- 'human' | 'critic_approved'
                approved_by  TEXT DEFAULT 'user_thumbsup',
                lang         TEXT DEFAULT 'vi',
                created_at   REAL NOT NULL,
                use_count    INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_golden_hash ON golden_store(query_hash);

            -- Critic log: lịch sử đánh giá chi tiết
            CREATE TABLE IF NOT EXISTS critic_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query        TEXT NOT NULL,
                answer       TEXT NOT NULL,
                verdict      TEXT NOT NULL,
                score        REAL,
                patterns     TEXT,   -- JSON list of error pattern keys
                has_golden   INTEGER DEFAULT 0,
                golden_diff  TEXT,   -- điểm khác so với golden
                answer_v2    TEXT,
                score_v2     REAL,
                lang         TEXT DEFAULT 'vi',
                created_at   REAL NOT NULL
            );

            -- Hàng chờ kiểm duyệt: 👍 của khách KHÔNG vào thẳng Golden Store
            -- (tránh người dùng vô tình/cố ý làm nhiễm dữ liệu học)
            CREATE TABLE IF NOT EXISTS golden_pending (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query        TEXT NOT NULL,
                answer       TEXT NOT NULL,
                lang         TEXT DEFAULT 'vi',
                session_id   TEXT,
                status       TEXT DEFAULT 'pending',  -- pending|approved|rejected
                created_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pending_status ON golden_pending(status);

            -- Pattern tracker: đếm lỗi để tự cải thiện prompt
            CREATE TABLE IF NOT EXISTS error_patterns (
                pattern_key  TEXT PRIMARY KEY,
                count        INTEGER DEFAULT 0,
                last_seen    REAL,
                auto_fixed   INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()


def _get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _qhash(query: str) -> str:
    return hashlib.md5(query.strip().lower().encode()).hexdigest()


# ── Golden Store API ───────────────────────────────────────────────────────────
def add_golden(query: str, answer: str, context: str = "",
               source: str = "human", lang: str = "vi"):
    """
    Thêm câu trả lời chuẩn vào Golden Store.
    Gọi khi: user bấm 👍, hoặc critic xác nhận câu trả lời xuất sắc (score >= 9.5)
    """
    with _db_lock:
        conn = _get_db()
        conn.execute("""
            INSERT INTO golden_store
                (query_hash, query, context_hash, answer, source, lang, created_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(query_hash) DO UPDATE SET
                answer     = excluded.answer,
                source     = excluded.source,
                created_at = excluded.created_at
        """, (_qhash(query), query,
              hashlib.md5(context[:200].encode()).hexdigest() if context else "",
              answer, source, lang, time.time()))
        conn.commit()
        conn.close()
    logger.info("Golden added: '%s' (source=%s)", query[:50], source)


# ── Hàng chờ kiểm duyệt (👍 của khách) ────────────────────────────────────────
def add_pending_golden(query: str, answer: str, lang: str = "vi",
                       session_id: str = "") -> int:
    """Lưu 👍 của khách vào hàng chờ — CHƯA phải câu chuẩn cho tới khi admin duyệt."""
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("""
            INSERT INTO golden_pending (query, answer, lang, session_id, created_at)
            VALUES (?,?,?,?,?)
        """, (query, answer, lang, session_id, time.time()))
        conn.commit()
        pid = cur.lastrowid
        conn.close()
    return pid


def list_pending_golden(limit: int = 50) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute("""
            SELECT id, query, answer, lang, created_at FROM golden_pending
            WHERE status='pending' ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def review_pending_golden(pending_id: int, approve: bool) -> bool:
    """Admin duyệt: approve=True → đưa vào Golden Store; False → loại bỏ."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT * FROM golden_pending WHERE id=? AND status='pending'",
            (pending_id,)).fetchone()
        if row:
            conn.execute("UPDATE golden_pending SET status=? WHERE id=?",
                         ("approved" if approve else "rejected", pending_id))
            conn.commit()
        conn.close()
    if not row:
        return False
    if approve:
        add_golden(query=row["query"], answer=row["answer"],
                   source="human", lang=row["lang"])
    return True


def get_golden(query: str) -> Optional[dict]:
    """Tìm golden answer cho query (exact match theo hash)."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT * FROM golden_store WHERE query_hash=?", (_qhash(query),)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE golden_store SET use_count=use_count+1 WHERE query_hash=?",
                (_qhash(query),)
            )
            conn.commit()
        conn.close()
    return dict(row) if row else None


def get_golden_examples(query: str, lang: str = "vi", top_k: int = 3) -> str:
    """
    Lấy golden examples tương tự để inject vào Responder.
    Ưu tiên golden store hơn self-learning vì đây là ground truth.
    """
    with _db_lock:
        conn = _get_db()
        words = [w for w in query.lower().split() if len(w) > 2][:5]
        if not words:
            conn.close()
            return ""
        cond   = " OR ".join([f"LOWER(query) LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words] + [lang, top_k]
        rows   = conn.execute(f"""
            SELECT query, answer, source FROM golden_store
            WHERE ({cond}) AND lang=?
            ORDER BY use_count DESC, created_at DESC
            LIMIT ?
        """, params).fetchall()
        conn.close()

    if not rows:
        return ""
    lines = ["CÂU TRẢ LỜI CHUẨN (đã được xác nhận — làm theo phong cách này):"]
    for r in rows:
        tag = "✓ human" if r["source"] == "human" else "✓ approved"
        lines.append(f"\nQ: {r['query']}\nA ({tag}): {r['answer'][:250]}\n")
    return "\n".join(lines)


# ── Response Critic ────────────────────────────────────────────────────────────
_CRITIC_SYSTEM = """Bạn là Response Critic chuyên đánh giá chatbot du lịch Suối Tiên.

NHIỆM VỤ: Phân tích sâu câu trả lời, không chỉ chấm điểm.

TIÊU CHÍ ĐÁNH GIÁ:
- Accuracy (3đ)    : thông tin đúng với Tool Results, không bịa giá/tên
- Helpfulness (3đ) : trả lời đúng câu hỏi, cụ thể, có ích
- Tone (2đ)        : tự nhiên, nhiệt tình, không xin lỗi vô cớ, không sáo rỗng
- Conciseness (2đ) : ngắn gọn, đúng trọng tâm

VERDICT:
- PASS    : score >= 8, không có lỗi nghiêm trọng
- IMPROVE : score 5-7 hoặc có lỗi sửa được
- REJECT  : score < 5 hoặc bịa thông tin, sai sự thật

ERROR PATTERNS (dùng đúng key):
- unnecessary_apology  : xin lỗi vô cớ khi có đủ thông tin
- hallucinate_price    : bịa giá không có trong Tool Results
- hallucinate_name     : bịa tên combo/trò chơi không có
- too_long             : quá dài, lan man
- missing_key_info     : thiếu thông tin quan trọng
- generic_response     : quá chung chung
- redirect_without_info: chỉ đẩy hotline không trả lời

Nếu có golden_answer: so sánh và chỉ ra điểm khác biệt cụ thể.

Trả về JSON DUY NHẤT:
{
  "score": 7.5,
  "verdict": "IMPROVE",
  "patterns": ["unnecessary_apology", "too_long"],
  "strengths": ["thông tin đúng"],
  "golden_diff": "golden ngắn hơn, không xin lỗi",
  "improve_instruction": "Bỏ câu xin lỗi đầu, rút ngắn còn 100 từ"
}"""


def critique(query: str, context: str, answer: str,
             lang: str = "vi") -> dict:
    """
    Critic phân tích sâu câu trả lời.
    Tự động tìm golden answer để so sánh.
    Returns: {score, verdict, patterns, strengths, golden_diff, improve_instruction}
    """
    if not llm_client.available():
        return {"score": 8.0, "verdict": VERDICT_PASS,
                "patterns": [], "strengths": [], "golden_diff": "", "improve_instruction": ""}

    # Tìm golden answer nếu có
    golden = get_golden(query)
    golden_section = ""
    if golden:
        golden_section = f"\nGOLDEN ANSWER (chuẩn do người xác nhận):\n{golden['answer']}\n"

    prompt = f"""Câu hỏi: {query}
Lang: {lang}

Tool Results (context):
{context[:800]}
{golden_section}
Câu trả lời cần đánh giá:
{answer}

Phân tích và trả về JSON."""

    try:
        raw = llm_client.complete(
            system=_CRITIC_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400, role="responder",
        ).strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        result = json.loads(raw.strip())

        # Track error patterns
        _track_patterns(result.get("patterns", []))
        return result
    except Exception:
        logger.exception("Critic error")
        return {"score": 7.5, "verdict": VERDICT_IMPROVE,
                "patterns": [], "strengths": [],
                "golden_diff": "", "improve_instruction": ""}


def _track_patterns(patterns: list):
    """Ghi nhận error patterns để thống kê và tự cải thiện prompt."""
    if not patterns:
        return
    with _db_lock:
        conn = _get_db()
        for p in patterns:
            if p in ERROR_PATTERNS:
                conn.execute("""
                    INSERT INTO error_patterns (pattern_key, count, last_seen)
                    VALUES (?, 1, ?)
                    ON CONFLICT(pattern_key) DO UPDATE SET
                        count=count+1, last_seen=excluded.last_seen
                """, (p, time.time()))
        conn.commit()
        conn.close()


def improve_with_instruction(query: str, context: str, answer: str,
                              instruction: str, lang: str = "vi") -> Optional[str]:
    """Improver nhận instruction cụ thể từ Critic thay vì tự suy."""
    if not llm_client.available() or not instruction:
        return None
    lang_note = "Tiếng Việt, xưng em, gọi anh/chị." if lang=="vi" else f"Language: {lang}"
    try:
        return llm_client.complete(
            system=f"Bạn là Tiên — tư vấn du lịch Suối Tiên. {lang_note} Viết lại câu trả lời theo hướng dẫn. Chỉ dùng thông tin từ context.",
            messages=[{"role": "user", "content":
                f"Câu hỏi: {query}\nContext: {context[:1200]}\n"
                f"Câu trả lời cũ:\n{answer}\n\n"
                f"Hướng dẫn sửa: {instruction}\n\nViết lại:"}],
            max_tokens=500, role="responder",
        ).strip()
    except Exception:
        logger.exception("Improve error")
        return None


# ── Full critique + learn loop ─────────────────────────────────────────────────
def critique_and_learn(query: str, context: str, answer: str,
                        lang: str = "vi", blocking: bool = False) -> Optional[str]:
    """
    Full loop: Critique → Improve (nếu cần) → Save golden (nếu xuất sắc).
    blocking=False: chạy background, không delay response user.
    """
    def _run():
        try:
            # Step 1: Critique
            result   = critique(query, context, answer, lang)
            verdict  = result.get("verdict", VERDICT_PASS)
            score    = result.get("score", 7.5)
            patterns = result.get("patterns", [])
            instruc  = result.get("improve_instruction", "")

            logger.info("Critic '%s': verdict=%s score=%.1f patterns=%s",
                        query[:40], verdict, score, patterns)

            answer_best = answer
            score_best  = score

            # Step 2: Improve nếu cần
            if verdict == VERDICT_IMPROVE and instruc:
                v2 = improve_with_instruction(query, context, answer, instruc, lang)
                if v2:
                    result2  = critique(query, context, v2, lang)
                    score_v2 = result2.get("score", score)
                    if score_v2 > score:
                        logger.info("Improved: %.1f→%.1f '%s'", score, score_v2, query[:40])
                        answer_best = v2
                        score_best  = score_v2
                    # Log — LẤY has_golden TRƯỚC khi giữ lock: get_golden() cũng
                    # acquire _db_lock, gọi lồng trong lock sẽ tự khoá chết thread
                    # (threading.Lock không tái nhập) → treo toàn bộ bot.
                    has_golden = 1 if get_golden(query) else 0
                    with _db_lock:
                        conn = _get_db()
                        conn.execute("""
                            INSERT INTO critic_log
                            (query,answer,verdict,score,patterns,has_golden,
                             golden_diff,answer_v2,score_v2,lang,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (query, answer, verdict, score,
                              json.dumps(patterns, ensure_ascii=False),
                              has_golden,
                              result.get("golden_diff",""),
                              v2, score_v2, lang, time.time()))
                        conn.commit()
                        conn.close()

            elif verdict == VERDICT_REJECT:
                logger.warning("REJECT answer for '%s': patterns=%s", query[:40], patterns)

            # Step 3: Lưu golden nếu xuất sắc (score >= 9.5, không có lỗi)
            if score_best >= 9.5 and not patterns:
                add_golden(query, answer_best, context,
                           source="critic_approved", lang=lang)

            return answer_best
        except Exception:
            logger.exception("critique_and_learn error")
            return answer

    if blocking:
        return _run()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return None


# ── Pattern-based prompt improvement ──────────────────────────────────────────
def get_top_error_patterns(top_n: int = 5) -> list:
    """Lấy lỗi phổ biến nhất để tự cải thiện prompt."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute("""
            SELECT pattern_key, count FROM error_patterns
            ORDER BY count DESC LIMIT ?
        """, (top_n,)).fetchall()
        conn.close()
    return [{"pattern": r["pattern_key"],
             "description": ERROR_PATTERNS.get(r["pattern_key"], ""),
             "count": r["count"]} for r in rows]


def generate_prompt_patch() -> str:
    """
    Tự động sinh thêm rule cho RESPONDER_SYSTEM
    dựa trên lỗi lặp lại nhiều nhất trong critic_log.
    """
    patterns = get_top_error_patterns(top_n=3)
    if not patterns:
        return ""

    rules = []
    for p in patterns:
        key = p["pattern"]
        if p["count"] < 3:  # Chỉ fix lỗi lặp >= 3 lần
            continue
        if key == "unnecessary_apology":
            rules.append("KHÔNG xin lỗi khi đã có đủ thông tin — trả lời thẳng")
        elif key == "hallucinate_price":
            rules.append("KHÔNG nhắc giá nếu không có trong thông tin em có — ghi 'liên hệ 1900 636 787'")
        elif key == "too_long":
            rules.append("Câu trả lời tối đa 150 từ — cắt bớt nếu quá dài")
        elif key == "generic_response":
            rules.append("Phải nêu tên cụ thể (tên combo, tên trò chơi) từ thông tin em có — không nói chung chung")
        elif key == "redirect_without_info":
            rules.append("Trả lời câu hỏi TRƯỚC rồi mới gợi ý hotline — không đẩy hotline thay cho câu trả lời")

    if not rules:
        return ""
    return "\nQUY TẮC BỔ SUNG (học từ lỗi thực tế):\n" + "\n".join(f"• {r}" for r in rules)


# ── Stats ──────────────────────────────────────────────────────────────────────
def critic_stats() -> dict:
    with _db_lock:
        conn = _get_db()
        golden_count = conn.execute("SELECT COUNT(*) FROM golden_store").fetchone()[0]
        human_golden = conn.execute(
            "SELECT COUNT(*) FROM golden_store WHERE source='human'"
        ).fetchone()[0]
        critic_total = conn.execute("SELECT COUNT(*) FROM critic_log").fetchone()[0]
        verdicts     = conn.execute("""
            SELECT verdict, COUNT(*) as n FROM critic_log GROUP BY verdict
        """).fetchall()
        top_patterns = conn.execute("""
            SELECT pattern_key, count FROM error_patterns ORDER BY count DESC LIMIT 5
        """).fetchall()
        conn.close()

    return {
        "golden_store": {
            "total":        golden_count,
            "human_approved": human_golden,
            "critic_approved": golden_count - human_golden,
        },
        "critic_log": {
            "total_evaluated": critic_total,
            "verdicts": {r["verdict"]: r["n"] for r in verdicts},
        },
        "top_error_patterns": [
            {"pattern": r["pattern_key"], "count": r["count"],
             "description": ERROR_PATTERNS.get(r["pattern_key"], "")}
            for r in top_patterns
        ],
        "prompt_patch": generate_prompt_patch() or "(none yet)",
    }


# ── Init ───────────────────────────────────────────────────────────────────────
init_critic_db()


if __name__ == "__main__":
    os.environ.setdefault("SUOITIEN_BASE", "core")
    print("=== RESPONSE CRITIC + GOLDEN STORE TEST ===\n")

    init_critic_db()
    print("✅ DB initialized")

    # Test Golden Store
    add_golden(
        query="Giá vé vào cổng bao nhiêu?",
        answer="Vé NL: **80.000đ** | TE: **40.000đ** 🎫 Mua online tại suoitien.vn tiết kiệm hơn!",
        lang="vi", source="human"
    )
    golden = get_golden("Giá vé vào cổng bao nhiêu?")
    print("✅ Golden Store:", "found" if golden else "not found")

    examples = get_golden_examples("gia ve bao nhieu", lang="vi")
    print("✅ Golden examples:", "found" if examples else "empty")

    # Test pattern tracking
    _track_patterns(["unnecessary_apology", "unnecessary_apology", "too_long"])
    stats = critic_stats()
    print("\n✅ Stats:")
    print(f"  Golden: {stats['golden_store']}")
    print(f"  Top patterns: {stats['top_error_patterns'][:2]}")
    print(f"  Prompt patch: {stats['prompt_patch'][:100]}")

    if llm_client.available():
        print("\n--- Critic test (with API) ---")
        result = critique(
            query="Có những trò chơi gì?",
            context="Go Kart, Tàu lượn SkyBounder, Đĩa xoáy Thi Thiên",
            answer="Dạ em xin lỗi anh/chị, em chưa có đủ thông tin về trò chơi ạ. Anh/chị vui lòng gọi 1900 636 787.",
            lang="vi"
        )
        print(f"  Score: {result.get('score')}")
        print(f"  Verdict: {result.get('verdict')}")
        print(f"  Patterns: {result.get('patterns')}")
        print(f"  Instruction: {result.get('improve_instruction')}")
    else:
        print("\n(Skip API test — no LLM provider available)")
