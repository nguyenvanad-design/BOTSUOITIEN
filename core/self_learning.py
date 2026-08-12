"""
self_learning.py — Hệ thống tự học cho Suối Tiên Bot

FLOW:
  User hỏi
    ↓
  Pipeline trả lời v1 (như bình thường)
    ↓
  Evaluator LLM chấm điểm v1 (async, không block user)
    ↓
  Nếu điểm < threshold → Improver LLM tự sửa → v2
    ↓
  Lưu (query + context + answer_best + score) vào SQLite
    ↓
  Few-shot retriever: lấy top-K ví dụ tốt nhất inject vào Responder
    ↓
  Bot ngày càng trả lời tốt hơn theo domain Suối Tiên

TÍCH HỢP:
  - responder.py: gọi get_fewshot_examples() để lấy few-shot
  - chat_pipeline.py: sau khi có answer, gọi evaluate_and_learn() async
  - auto_updater.py: cron job rebuild few-shot index mỗi đêm

DATABASE: SQLite (core/data/learning.db)
  Bảng qa_pairs: id, query, context, answer, score, created_at, lang
  Bảng eval_log: id, qa_id, evaluator_score, issues, improved, created_at
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

import llm_client

logger = logging.getLogger("suoitien.self_learning")

# ── Config ────────────────────────────────────────────────────────────────────
SCORE_THRESHOLD    = 7.0   # < 7/10 → tự sửa
FEWSHOT_TOP_K      = 3     # số ví dụ inject vào Responder
MIN_SCORE_FOR_SAVE = 8.0   # chỉ lưu ví dụ tốt làm few-shot
MAX_FEWSHOT_CHARS  = 1200  # giới hạn token few-shot trong prompt

DB_PATH = Path(os.getenv("SUOITIEN_BASE", "core")) / "data" / "learning.db"

# ── Database ──────────────────────────────────────────────────────────────────
# RLock để helper DB gọi lồng nhau không tự khoá chết thread (xem response_critic)
_db_lock = threading.RLock()

def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tạo schema nếu chưa có."""
    with _db_lock:
        conn = _get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS qa_pairs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash  TEXT NOT NULL,
                query       TEXT NOT NULL,
                context     TEXT,
                answer      TEXT NOT NULL,
                score       REAL NOT NULL,
                lang        TEXT DEFAULT 'vi',
                created_at  REAL NOT NULL,
                improved    INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_score ON qa_pairs(score DESC);
            CREATE INDEX IF NOT EXISTS idx_hash  ON qa_pairs(query_hash);

            CREATE TABLE IF NOT EXISTS eval_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                query           TEXT NOT NULL,
                answer_v1       TEXT NOT NULL,
                score_v1        REAL,
                issues          TEXT,
                answer_v2       TEXT,
                score_v2        REAL,
                improved        INTEGER DEFAULT 0,
                lang            TEXT DEFAULT 'vi',
                created_at      REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()


def _query_hash(query: str) -> str:
    return hashlib.md5(query.strip().lower().encode()).hexdigest()


def save_qa(query: str, context: str, answer: str,
            score: float, lang: str = "vi", improved: bool = False):
    """Lưu cặp Q&A tốt vào database."""
    with _db_lock:
        conn = _get_db()
        conn.execute("""
            INSERT INTO qa_pairs (query_hash, query, context, answer, score, lang, created_at, improved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (_query_hash(query), query, context[:2000], answer,
              score, lang, time.time(), int(improved)))
        conn.commit()
        conn.close()


def get_fewshot_examples(query: str, lang: str = "vi", top_k: int = FEWSHOT_TOP_K) -> str:
    """
    Lấy K ví dụ Q&A tốt nhất tương tự query hiện tại.
    Dùng BM25 đơn giản trên SQLite FTS hoặc keyword match.
    Trả về string để inject vào Responder system prompt.
    """
    try:
        with _db_lock:
            conn = _get_db()
            # Lấy top examples theo score, filter theo lang
            # Simple approach: full-text LIKE match trên query words
            words = [w for w in query.lower().split() if len(w) > 2]
            if not words:
                conn.close()
                return ""

            # Build LIKE conditions
            conditions = " OR ".join([f"LOWER(query) LIKE ?" for _ in words[:5]])
            params = [f"%{w}%" for w in words[:5]] + [lang, MIN_SCORE_FOR_SAVE, top_k]

            rows = conn.execute(f"""
                SELECT query, answer, score FROM qa_pairs
                WHERE ({conditions})
                  AND lang = ?
                  AND score >= ?
                ORDER BY score DESC
                LIMIT ?
            """, params).fetchall()
            conn.close()

        if not rows:
            return ""

        lines = ["VÍ DỤ TRẢ LỜI TỐT TRƯỚC ĐÂY (tham khảo phong cách):"]
        total_chars = 0
        for row in rows:
            entry = f"\nQ: {row['query']}\nA: {row['answer'][:300]}\n"
            if total_chars + len(entry) > MAX_FEWSHOT_CHARS:
                break
            lines.append(entry)
            total_chars += len(entry)

        return "\n".join(lines) if len(lines) > 1 else ""

    except Exception:
        logger.exception("get_fewshot_examples error")
        return ""


# ── Evaluator ─────────────────────────────────────────────────────────────────
_EVAL_SYSTEM = """\
Bạn là evaluator chất lượng câu trả lời chatbot du lịch Suối Tiên.
Đánh giá câu trả lời theo thang 1-10 dựa trên:
- Accuracy (3đ): thông tin đúng với context, không bịa
- Helpfulness (3đ): trả lời đúng câu hỏi, có ích cho khách
- Tone (2đ): tự nhiên, thân thiện, không sáo rỗng, không xin lỗi vô cớ
- Conciseness (2đ): ngắn gọn, đúng trọng tâm, không lan man

Trả về JSON DUY NHẤT, không có markdown:
{"score": 8.5, "issues": ["issue1", "issue2"], "strengths": ["str1"]}

issues: danh sách vấn đề cụ thể (rỗng nếu không có)
strengths: điểm mạnh cụ thể"""

def evaluate(query: str, context: str, answer: str, lang: str = "vi") -> dict:
    """
    LLM tự đánh giá câu trả lời.
    Returns: {"score": float, "issues": list, "strengths": list}
    """
    if not llm_client.available():
        return {"score": 8.0, "issues": [], "strengths": []}

    prompt = f"""Câu hỏi: {query}

Context (tool results):
{context[:1000]}

Câu trả lời cần đánh giá:
{answer}

Ngôn ngữ: {lang}

Đánh giá và trả về JSON."""

    try:
        raw = llm_client.complete(
            system=_EVAL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, role="responder",
        ).strip()
        # Strip markdown nếu có
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        logger.exception("Evaluator error")
        return {"score": 7.5, "issues": [], "strengths": []}


# ── Improver ──────────────────────────────────────────────────────────────────
_IMPROVE_SYSTEM = """\
Bạn là Tiên — nhân viên tư vấn du lịch Suối Tiên. Nhiệm vụ: viết lại câu trả lời tốt hơn.

Yêu cầu:
- Sửa đúng các vấn đề được chỉ ra
- Giữ thông tin chính xác từ context
- Tự nhiên, ngắn gọn, nhiệt tình — không sáo rỗng, không xin lỗi vô cớ
- Không thêm thông tin không có trong context
- Tối đa 250 từ"""

def improve(query: str, context: str, answer_v1: str,
            issues: list, lang: str = "vi") -> Optional[str]:
    """
    LLM tự sửa câu trả lời dựa trên issues từ evaluator.
    Returns: answer_v2 hoặc None nếu lỗi
    """
    if not llm_client.available() or not issues:
        return None

    lang_note = "Trả lời tiếng Việt, xưng em, gọi anh/chị." if lang == "vi" else f"Reply in {lang}."

    prompt = f"""{lang_note}

Câu hỏi: {query}

Context:
{context[:1500]}

Câu trả lời cũ (cần sửa):
{answer_v1}

Vấn đề cần sửa:
{chr(10).join(f'- {i}' for i in issues)}

Viết câu trả lời mới tốt hơn:"""

    try:
        return llm_client.complete(
            system=_IMPROVE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600, role="responder",
        ).strip()
    except Exception:
        logger.exception("Improver error")
        return None


# ── Main learning loop ─────────────────────────────────────────────────────────
def evaluate_and_learn(
    query: str,
    context: str,
    answer: str,
    lang: str = "vi",
    blocking: bool = False,
) -> Optional[str]:
    """
    Pipeline tự học — gọi sau khi đã trả lời user.

    blocking=False (default): chạy trong background thread, không block response
    blocking=True: chạy sync, trả về answer tốt nhất (dùng cho testing)

    Returns: answer tốt nhất (v1 hoặc v2) nếu blocking=True, else None
    """
    def _run():
        try:
            # Step 1: Evaluate v1
            eval_result = evaluate(query, context, answer, lang)
            score_v1    = eval_result.get("score", 7.0)
            issues      = eval_result.get("issues", [])

            logger.info("Eval '%s': score=%.1f issues=%s",
                        query[:40], score_v1, issues[:2])

            answer_best = answer
            score_best  = score_v1
            improved    = False

            # Step 2: Improve nếu điểm thấp và có issues
            if score_v1 < SCORE_THRESHOLD and issues:
                answer_v2 = improve(query, context, answer, issues, lang)
                if answer_v2:
                    # Evaluate v2 để xác nhận thực sự tốt hơn
                    eval_v2   = evaluate(query, context, answer_v2, lang)
                    score_v2  = eval_v2.get("score", score_v1)

                    if score_v2 > score_v1:
                        logger.info("Improved: %.1f → %.1f for '%s'",
                                    score_v1, score_v2, query[:40])
                        answer_best = answer_v2
                        score_best  = score_v2
                        improved    = True
                    else:
                        logger.info("Improve did not help: %.1f → %.1f", score_v1, score_v2)

                    # Log eval
                    with _db_lock:
                        conn = _get_db()
                        conn.execute("""
                            INSERT INTO eval_log
                            (query, answer_v1, score_v1, issues, answer_v2, score_v2, improved, lang, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)
                        """, (query, answer, score_v1, json.dumps(issues, ensure_ascii=False),
                              answer_v2, score_v2, int(improved), lang, time.time()))
                        conn.commit()
                        conn.close()

            # Step 3: Lưu nếu đủ tốt
            if score_best >= MIN_SCORE_FOR_SAVE:
                save_qa(query, context, answer_best, score_best, lang, improved)
                logger.info("Saved QA: score=%.1f improved=%s query='%s'",
                            score_best, improved, query[:40])

            return answer_best

        except Exception:
            logger.exception("evaluate_and_learn error")
            return answer

    if blocking:
        return _run()
    else:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return None


# ── Stats ──────────────────────────────────────────────────────────────────────
def learning_stats() -> dict:
    """Thống kê hệ thống tự học."""
    try:
        with _db_lock:
            conn = _get_db()
            total    = conn.execute("SELECT COUNT(*) FROM qa_pairs").fetchone()[0]
            avg_score= conn.execute("SELECT AVG(score) FROM qa_pairs").fetchone()[0]
            improved = conn.execute("SELECT COUNT(*) FROM qa_pairs WHERE improved=1").fetchone()[0]
            evals    = conn.execute("SELECT COUNT(*) FROM eval_log").fetchone()[0]
            top3     = conn.execute("""
                SELECT query, score FROM qa_pairs
                ORDER BY score DESC LIMIT 3
            """).fetchall()
            conn.close()

        return {
            "total_examples": total,
            "avg_score":      round(avg_score or 0, 2),
            "improved_count": improved,
            "total_evals":    evals,
            "top_examples":   [{"query": r["query"][:50], "score": r["score"]} for r in top3],
        }
    except Exception:
        return {"error": "DB not initialized"}


# ── Init on import ─────────────────────────────────────────────────────────────
init_db()


# ── Quick test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.environ.setdefault("SUOITIEN_BASE", "core")

    print("=== SELF-LEARNING SYSTEM TEST ===\n")

    # Test DB init
    init_db()
    print("✅ DB initialized:", DB_PATH)

    # Test save & retrieve
    save_qa(
        query="Giá vé vào cổng bao nhiêu?",
        context="Vé người lớn: 80.000đ, trẻ em: 40.000đ",
        answer="Vé vào cổng Suối Tiên: NL 80.000đ, TE 40.000đ 🎫",
        score=9.0, lang="vi"
    )
    examples = get_fewshot_examples("gia ve bao nhieu", lang="vi")
    print("✅ Few-shot retrieval:", "✓ found" if examples else "✗ empty")
    print(examples[:200] if examples else "")

    # Test stats
    stats = learning_stats()
    print("\n✅ Stats:", stats)

    # Test evaluate (cần LLM provider)
    if llm_client.available():
        print("\n--- Evaluator test ---")
        result = evaluate(
            query="Giá vé vào cổng bao nhiêu?",
            context="Vé NL: 80.000đ, TE: 40.000đ",
            answer="Dạ vé vào cổng Suối Tiên hiện tại là 80 nghìn cho người lớn và 40 nghìn cho bé ạ. Anh/chị có muốn biết thêm không ạ?",
            lang="vi"
        )
        print(f"Score: {result.get('score')}")
        print(f"Issues: {result.get('issues')}")

        print("\n--- Full learn loop (blocking) ---")
        result2 = evaluate_and_learn(
            query="Có những trò chơi gì?",
            context="Go Kart, Tàu lượn SkyBounder, Đĩa xoáy...",
            answer="Dạ em xin lỗi ạ, em chưa có thông tin về trò chơi. Anh/chị vui lòng gọi 1900 636 787.",
            lang="vi", blocking=True
        )
        print(f"Best answer: {result2[:100] if result2 else 'None'}...")
    else:
        print("\n(Skip evaluator test — no LLM provider available)")
