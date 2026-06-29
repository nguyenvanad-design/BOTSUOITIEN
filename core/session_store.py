"""
session_store.py — In-memory conversation history
Lưu lịch sử hội thoại theo session_id.
Sau này swap sang Redis chỉ cần đổi backend, interface giữ nguyên.
"""

import time
import threading
from collections import defaultdict, deque
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_TURNS       = 10     # số lượt hội thoại giữ lại mỗi session
SESSION_TTL     = 1800   # giây — session hết hạn sau 30 phút không hoạt động
MAX_SESSIONS    = 5000   # giới hạn tổng số session trong memory


class SessionStore:
    """In-memory session store. Thread-safe (lock) cho single-process FastAPI."""

    def __init__(self, max_turns=MAX_TURNS, ttl=SESSION_TTL, max_sessions=MAX_SESSIONS):
        self.max_turns    = max_turns
        self.ttl          = ttl
        self.max_sessions = max_sessions
        # {session_id: {"history": deque, "last_active": float}}
        self._store: dict = {}
        self._lock = threading.Lock()

    def _evict_expired(self):
        """Xóa các session hết hạn."""
        now     = time.time()
        expired = [sid for sid, s in self._store.items() if now - s["last_active"] > self.ttl]
        for sid in expired:
            del self._store[sid]

    def _ensure_capacity(self):
        """Nếu quá giới hạn, xóa session cũ nhất."""
        if len(self._store) >= self.max_sessions:
            oldest = min(self._store.items(), key=lambda x: x[1]["last_active"])
            del self._store[oldest[0]]

    def get_history(self, session_id: str) -> list[dict]:
        """
        Lấy lịch sử hội thoại của session.
        Returns: list of {role, content} — format chuẩn Anthropic messages API
        """
        with self._lock:
            self._evict_expired()
            session = self._store.get(session_id)
            if not session:
                return []
            return list(session["history"])

    def add_turn(self, session_id: str, user_msg: str, bot_msg: str, intent: str = ""):
        """Thêm 1 lượt hội thoại vào session."""
        with self._lock:
            self._evict_expired()
            self._add_turn_unlocked(session_id, user_msg, bot_msg)

    def _add_turn_unlocked(self, session_id: str, user_msg: str, bot_msg: str):
        if session_id not in self._store:
            self._ensure_capacity()
            self._store[session_id] = {
                "history":     deque(maxlen=self.max_turns * 2),  # *2 vì mỗi turn = 2 msg
                "last_active": time.time(),
            }

        session = self._store[session_id]
        session["history"].append({"role": "user",      "content": user_msg})
        session["history"].append({"role": "assistant", "content": bot_msg})
        session["last_active"] = time.time()

    def clear(self, session_id: str):
        """Xóa lịch sử session (reset conversation)."""
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]

    def stats(self) -> dict:
        with self._lock:
            self._evict_expired()
            return {
                "active_sessions": len(self._store),
                "max_sessions":    self.max_sessions,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────
_store = SessionStore()

def get_history(session_id: str) -> list[dict]:
    return _store.get_history(session_id)

def add_turn(session_id: str, user_msg: str, bot_msg: str, intent: str = ""):
    _store.add_turn(session_id, user_msg, bot_msg, intent)

def clear_session(session_id: str):
    _store.clear(session_id)

def store_stats() -> dict:
    return _store.stats()
