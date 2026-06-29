"""
memory_layer.py — Conversation Memory Layer cho Suối Tiên Bot

Giải quyết vấn đề: user nói "Tôi có 4 người lớn" rồi sau hỏi
"Tính giá vé giúp tôi" — bot phải nhớ "4 người lớn".

Hiện tại: session_store đã lưu history (messages), nhưng chưa
extract entities có cấu trúc từ history.

Memory layer này:
1. Extract entities quan trọng từ history (group_size, ages, preferences)
2. Inject vào query để Planner có context đầy đủ
3. Tương thích với session_store hiện tại (không thay thế)

Production upgrade path:
- Hiện tại: in-memory dict (đủ cho ~1000 session đồng thời)
- Scale up: swap sang Redis với 2 dòng code
"""
import re
import threading
from typing import Optional

_memory: dict = {}
_lock = threading.Lock()


# ── Entity extractors ──────────────────────────────────────────────────────────

def _extract_group_size(text: str) -> Optional[int]:
    patterns = [
        r"(\d+)\s*(?:người lớn|nguoi lon|adults?)",
        r"(\d+)\s*(?:người|nguoi|people|person|khách|khach)",
        r"(?:nhóm|nhom|đoàn|doan|group)\s*(?:of\s*)?(\d+)",
        r"(\d+)\s*(?:thành viên|thanh vien|members?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 10000:
                return n
    return None


def _extract_children(text: str) -> Optional[int]:
    patterns = [
        r"(\d+)\s*(?:trẻ em|tre em|em bé|em be|children|kids?|bé)",
        r"(\d+)\s*(?:con|child)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 100:
                return n
    return None


def _extract_height(text: str) -> Optional[int]:
    patterns = [
        r"(\d+)\s*cm",
        r"(\d+[.,]\d+)\s*m(?:ét|et)?\b",
        r"cao\s+(\d+)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", ".")
            n = float(val)
            if n > 3:
                return int(n)
            else:
                return int(n * 100)
    return None


def _extract_age(text: str) -> Optional[int]:
    patterns = [
        r"(\d+)\s*(?:tuổi|tuoi|years? old|yo\b)",
        r"(?:bé|be|con|trẻ)\s+(\d+)\s*(?:tuổi|tuoi)?",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 120:
                return n
    return None


def _extract_date(text: str) -> Optional[str]:
    patterns = [
        r"(?:thứ\s+\w+|chủ nhật|chu nhat|saturday|sunday|weekend|cuối tuần|cuoi tuan)",
        r"ngày\s+(\d{1,2})[/\-.](\d{1,2})",
        r"(\d{1,2})[/\-.](\d{1,2})",
        r"(?:hôm nay|hom nay|today|tomorrow|ngày mai|ngay mai)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def update_memory(session_id: str, user_message: str):
    """
    Extract entities từ user message và cập nhật memory cho session.
    Gọi sau mỗi user turn, trước khi Planner chạy.
    """
    entities = {}

    gs = _extract_group_size(user_message)
    if gs:
        entities["group_size"] = gs

    ch = _extract_children(user_message)
    if ch is not None:
        entities["children"] = ch

    ht = _extract_height(user_message)
    if ht:
        entities["height_cm"] = ht

    ag = _extract_age(user_message)
    if ag is not None:
        entities["age"] = ag

    dt = _extract_date(user_message)
    if dt:
        entities["visit_date"] = dt

    if entities:
        with _lock:
            if session_id not in _memory:
                _memory[session_id] = {}
            _memory[session_id].update(entities)


def get_memory(session_id: str) -> dict:
    """Lấy memory của session."""
    with _lock:
        return dict(_memory.get(session_id, {}))


def clear_memory(session_id: str):
    """Xóa memory khi session reset."""
    with _lock:
        _memory.pop(session_id, None)


def inject_memory_to_query(query: str, session_id: str) -> str:
    """
    Inject memory context vào query để Planner có đủ thông tin.
    VD: "Tính giá vé giúp tôi" + memory{group_size:4}
    → "Tính giá vé giúp tôi [Context: 4 người lớn]"
    """
    mem = get_memory(session_id)
    if not mem:
        return query

    parts = []
    if "group_size" in mem:
        parts.append(f"{mem['group_size']} người")
    if "children" in mem:
        parts.append(f"{mem['children']} trẻ em")
    if "height_cm" in mem:
        parts.append(f"cao {mem['height_cm']}cm")
    if "age" in mem:
        parts.append(f"{mem['age']} tuổi")
    if "visit_date" in mem:
        parts.append(f"ngày {mem['visit_date']}")

    if not parts:
        return query

    context_note = f" [Thông tin từ hội thoại: {', '.join(parts)}]"
    return query + context_note


def memory_stats() -> dict:
    with _lock:
        return {
            "active_sessions": len(_memory),
            "sessions":        list(_memory.keys())[:10],
        }


# ── Test ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("s1", "Tôi có 4 người lớn và 2 trẻ em",      {"group_size": 4, "children": 2}),
        ("s1", "Bé cao 110cm",                          {"height_cm": 110}),
        ("s2", "Nhóm 50 người teambuilding",            {"group_size": 50}),
        ("s3", "Con tôi 3 tuổi",                        {"age": 3}),
        ("s3", "Chúng tôi đi cuối tuần",                {"visit_date": "cuối tuần"}),
    ]
    passed = 0
    for sid, msg, expected in tests:
        update_memory(sid, msg)
        mem = get_memory(sid)
        ok = all(mem.get(k) == v for k, v in expected.items())
        passed += ok
        print(f"  {'✅' if ok else '❌'} '{msg}' → {mem}")

    print(f"\n{passed}/{len(tests)} passed")

    q = inject_memory_to_query("Tính giá vé giúp tôi", "s1")
    print(f"\nInjected query: {q}")
