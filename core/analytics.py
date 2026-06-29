"""
analytics.py — Analytics Dashboard data collector

Thu thập:
- Query volume theo giờ/ngày
- FAQ hit rate vs LLM rate
- Top queries, fail queries
- Latency percentiles (p50, p90, p99)
- Provider usage (grok vs anthropic vs fallback)
- Guardrail block rate

Dashboard: GET /analytics → JSON (dùng với Grafana / Metabase / custom UI)
"""
import os, json, time, sqlite3, logging, threading
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("suoitien.analytics")

DB_PATH = Path(os.getenv("SUOITIEN_BASE", "core")) / "data" / "learning.db"
_lock   = threading.Lock()

# In-memory buffer — flush vào DB mỗi 60s
_buffer: list = []
_buf_lock = threading.Lock()


def init_analytics():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         REAL NOT NULL,
                lang       TEXT,
                source     TEXT,
                tools      TEXT,
                latency_ms REAL,
                ttft_ms    REAL,
                guardrail  TEXT,
                session_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_an_ts ON analytics_events(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_an_src ON analytics_events(source);
        """)
        conn.commit()
        conn.close()


def track(lang: str, source: str, tools: list, latency_ms: float,
          ttft_ms: float = 0, guardrail: str = "", session_id: str = ""):
    """Ghi 1 event — non-blocking, buffer trước flush sau."""
    event = {
        "ts":         time.time(),
        "lang":       lang,
        "source":     source,
        "tools":      ",".join(tools) if tools else "",
        "latency_ms": latency_ms,
        "ttft_ms":    ttft_ms,
        "guardrail":  guardrail,
        "session_id": session_id,
    }
    with _buf_lock:
        _buffer.append(event)
        if len(_buffer) >= 50:
            _flush()


def _flush():
    """Flush buffer → SQLite. Gọi trong _buf_lock."""
    global _buffer
    if not _buffer:
        return
    batch = _buffer[:]
    _buffer = []
    try:
        with _lock:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.executemany("""
                INSERT INTO analytics_events
                (ts,lang,source,tools,latency_ms,ttft_ms,guardrail,session_id)
                VALUES (:ts,:lang,:source,:tools,:latency_ms,:ttft_ms,:guardrail,:session_id)
            """, batch)
            conn.commit()
            conn.close()
    except Exception:
        logger.exception("Analytics flush error")


def flush_now():
    with _buf_lock:
        _flush()


def get_dashboard(hours: int = 24) -> dict:
    """Tổng hợp metrics cho dashboard."""
    flush_now()
    since = time.time() - hours * 3600
    try:
        with _lock:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT * FROM analytics_events WHERE ts >= ? ORDER BY ts DESC
            """, (since,)).fetchall()
            conn.close()

        if not rows:
            return {"period_hours": hours, "total_queries": 0}

        total      = len(rows)
        by_source  = defaultdict(int)
        by_lang    = defaultdict(int)
        by_tool    = defaultdict(int)
        latencies  = []
        blocked    = 0

        for r in rows:
            by_source[r["source"]] += 1
            by_lang[r["lang"] or "vi"] += 1
            if r["tools"]:
                for t in r["tools"].split(","):
                    if t: by_tool[t] += 1
            if r["latency_ms"]:
                latencies.append(r["latency_ms"])
            if r["guardrail"]:
                blocked += 1

        latencies.sort()
        n = len(latencies)

        def pct(p):
            return latencies[int(n * p / 100)] if latencies else 0

        faq_rate = by_source.get("faq", 0) / total * 100

        return {
            "period_hours":   hours,
            "total_queries":  total,
            "faq_hit_rate":   f"{faq_rate:.1f}%",
            "guardrail_blocked": f"{blocked/total*100:.1f}%",
            "by_source":      dict(by_source),
            "by_lang":        dict(by_lang),
            "top_tools":      sorted(by_tool.items(), key=lambda x: -x[1])[:5],
            "latency": {
                "p50":  f"{pct(50):.0f}ms",
                "p90":  f"{pct(90):.0f}ms",
                "p99":  f"{pct(99):.0f}ms",
                "avg":  f"{sum(latencies)/n:.0f}ms" if n else "0ms",
            },
            "queries_per_hour": round(total / hours, 1),
        }
    except Exception:
        logger.exception("Analytics dashboard error")
        return {"error": "db error"}


init_analytics()
