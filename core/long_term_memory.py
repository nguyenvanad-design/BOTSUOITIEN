"""
long_term_memory.py — Long-term User Memory

Session memory (memory_layer.py): entities trong 1 hội thoại (group_size, age...)
Long-term memory (file này): preference và lịch sử của user qua nhiều lần visit

Lưu:
- preferred_lang, preferred_attractions, past_queries
- visit_count, last_visit, known_group_size
- booking_history (nếu có Tool Hub)

Storage: SQLite (swap Redis khi scale)
Key: user_id = session_id của platform (zalo_xxx, fb_xxx, web_xxx)
TTL: 180 ngày
"""
import os, json, time, sqlite3, logging, threading
from pathlib import Path

logger = logging.getLogger("suoitien.ltm")

DB_PATH  = Path(os.getenv("SUOITIEN_BASE", "core")) / "data" / "learning.db"
_lock    = threading.Lock()
TTL_DAYS = 180


def _db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_ltm():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = _db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id      TEXT PRIMARY KEY,
                profile      TEXT NOT NULL DEFAULT '{}',
                visit_count  INTEGER DEFAULT 1,
                first_visit  REAL,
                last_visit   REAL,
                updated_at   REAL
            )
        """)
        conn.commit()
        conn.close()


def get_profile(user_id: str) -> dict:
    if not user_id or user_id.startswith("user_"):
        return {}
    with _lock:
        conn = _db()
        row  = conn.execute(
            "SELECT * FROM user_memory WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
    if not row:
        return {}
    try:
        return {**json.loads(row["profile"]),
                "visit_count": row["visit_count"],
                "last_visit":  row["last_visit"]}
    except Exception:
        return {}


def update_profile(user_id: str, updates: dict):
    if not user_id or user_id.startswith("user_"):
        return
    now = time.time()
    with _lock:
        conn = _db()
        row  = conn.execute(
            "SELECT profile, visit_count FROM user_memory WHERE user_id=?",
            (user_id,)
        ).fetchone()
        if row:
            profile = json.loads(row["profile"])
            profile.update(updates)
            conn.execute("""
                UPDATE user_memory
                SET profile=?, visit_count=visit_count+1, last_visit=?, updated_at=?
                WHERE user_id=?
            """, (json.dumps(profile, ensure_ascii=False),
                  now, now, user_id))
        else:
            conn.execute("""
                INSERT INTO user_memory (user_id,profile,visit_count,first_visit,last_visit,updated_at)
                VALUES (?,?,1,?,?,?)
            """, (user_id, json.dumps(updates, ensure_ascii=False), now, now, now))
        conn.commit()
        conn.close()


def learn_from_conversation(user_id: str, query: str, answer: str,
                             tools: list, lang: str):
    """Extract insights từ 1 turn → update long-term profile."""
    if not user_id or user_id.startswith("user_"):
        return
    updates = {"preferred_lang": lang}

    # Học sở thích từ tools được gọi
    if "search_attractions" in tools:
        updates.setdefault("interests", [])
    if "search_teambuilding" in tools:
        updates["is_corporate"] = True
    if "search_tickets" in tools:
        updates["checked_tickets"] = True

    # Học ngôn ngữ ưa thích
    if lang != "vi":
        updates["preferred_lang"] = lang

    update_profile(user_id, updates)


def build_ltm_context(user_id: str) -> str:
    """Sinh context string để inject vào Responder prompt."""
    profile = get_profile(user_id)
    if not profile:
        return ""
    parts = []
    if profile.get("visit_count", 0) > 1:
        parts.append(f"khách đã ghé {profile['visit_count']} lần")
    if profile.get("is_corporate"):
        parts.append("quan tâm teambuilding/doanh nghiệp")
    if profile.get("preferred_lang", "vi") != "vi":
        parts.append(f"ngôn ngữ: {profile['preferred_lang']}")
    if not parts:
        return ""
    return f"[Khách quen: {', '.join(parts)}]"


init_ltm()
