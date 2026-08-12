"""
main.py — FastAPI entry point cho Suối Tiên Bot
Khởi động server, load tất cả components, expose API endpoints.

v3:
- load_dotenv() — tự load .env khi khởi động, không cần set key tay
- lifespan thay @app.on_event (deprecated)
- /health check ANTHROPIC_API_KEY + OWM_API_KEY (bỏ GEMINI — không dùng)
- logging.basicConfig để log của planner/responder/pipeline hiện ra
- FileResponse neo theo BASE_DIR (chạy từ thư mục nào cũng được)
- reload điều khiển bằng env DEV_RELOAD (mặc định tắt — production safe)
"""

import os
import sys
import time
import logging
import asyncio
import threading
from pathlib import Path
from contextlib import asynccontextmanager

# Load .env TRƯỚC MỌI THỨ — để ANTHROPIC_API_KEY có mặt khi các module import
from dotenv import load_dotenv
load_dotenv()

# Đảm bảo core/ trong sys.path
BASE_DIR = Path(__file__).parent
CORE_DIR = BASE_DIR / "core"
sys.path.insert(0, str(CORE_DIR))

# Set env vars TRƯỚC khi import core modules
os.environ.setdefault("SUOITIEN_BASE",  str(CORE_DIR))
os.environ.setdefault("SUOITIEN_DATA",  str(CORE_DIR / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(CORE_DIR / "data" / "suoitien_clean_v4.json"))

# Logging — các module core (suoitien.planner, suoitien.responder,
# suoitien.pipeline...) dùng logging; không config thì log biến mất.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
logger = logging.getLogger("suoitien.main")

import uvicorn
from auto_updater import start_scheduler, stop_scheduler, get_router as get_admin_router
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.chat            import router as chat_router
from api.webhook         import router as webhook_router
from api.webhook_content import router as content_router


# ── Chỉ mục tìm kiếm ──────────────────────────────────────────────────────────
_INDEX_DIR   = CORE_DIR / "data" / "faiss_index"
_FAISS_FILE  = _INDEX_DIR / "index.faiss"
_BM25_FILE   = _INDEX_DIR / "bm25.pkl"


def index_status() -> dict:
    return {"faiss": _FAISS_FILE.exists(), "bm25": _BM25_FILE.exists()}


def _ensure_index():
    """
    Chỉ mục KHÔNG nằm trong Git (sinh lại được từ data), nên bản clone sạch sẽ
    thiếu. Trước đây `_warmup()` nuốt exception ⇒ bot vẫn khởi động bình thường
    nhưng MẤT HẲN RAG mà không ai biết — tệ hơn là không chạy được.
    Ở đây tự dựng lại; dựng không xong thì dừng hẳn thay vì chạy câm.
    """
    st = index_status()
    if all(st.values()):
        return
    missing = [k for k, v in st.items() if not v]
    logger.warning("Thiếu chỉ mục %s — đang dựng lại từ dữ liệu...", missing)
    try:
        if not st["bm25"]:
            from bm25_search import build_bm25
            build_bm25(force=True)
            logger.info("BM25 đã dựng xong ✓")
        if not st["faiss"]:
            from build_faiss import main as build_faiss_main
            build_faiss_main()
            logger.info("FAISS đã dựng xong ✓")
    except Exception:
        logger.exception("Dựng chỉ mục thất bại")

    st = index_status()
    if not all(st.values()):
        raise RuntimeError(
            "Thiếu chỉ mục tìm kiếm: "
            + ", ".join(k for k, v in st.items() if not v)
            + ". Chạy `python core/build_faiss.py` rồi khởi động lại. "
              "Đặt SUOITIEN_ALLOW_NO_INDEX=1 để chạy không có RAG (chất lượng giảm mạnh)."
        )


# ── Lifespan (thay cho @app.on_event đã deprecated) ────────────────────────────
def _warmup():
    """Warmup BGE-M3 + FAISS — tránh cold load ~8s ở request đầu tiên."""
    try:
        from vector_search import _get_model, _load_index
        _load_index()   # load FAISS index vào RAM
        _get_model()    # load BGE-M3 vào VRAM/RAM
        logger.info("BGE-M3 + FAISS warmed up ✓")
    except Exception as e:
        logger.warning("Warmup warning: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    # Kiểm ĐÚNG provider đang dùng, không phải mặc định Anthropic: hệ thống
    # chạy Grok thì thiếu ANTHROPIC_API_KEY là bình thường.
    try:
        from llm_client import get_provider
        _prov = (get_provider() or "").lower()
    except Exception:
        _prov = ""
    _key_env = {"grok": "XAI_API_KEY", "gemini": "GOOGLE_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY"}.get(_prov, "ANTHROPIC_API_KEY")
    if not os.getenv(_key_env):
        logger.warning(
            "%s chưa set (provider=%s) — Planner/Responder sẽ chạy fallback "
            "(chất lượng trả lời giảm mạnh)!", _key_env, _prov or "?"
        )

    if os.getenv("SUOITIEN_ALLOW_NO_INDEX", "").strip() not in ("1", "true", "yes"):
        _ensure_index()
    else:
        logger.warning("SUOITIEN_ALLOW_NO_INDEX bật — chạy không cần chỉ mục, RAG có thể tắt")

    start_scheduler()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _warmup)
    yield
    # ── shutdown ──
    stop_scheduler()


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Suối Tiên Bot API",
    version="1.1.0",
    description="Chatbot tư vấn du lịch Công viên Văn hóa Suối Tiên",
    lifespan=lifespan,
)

# CORS — FAIL-CLOSED. Mặc định cũ là "*": bất kỳ website nào cũng gọi được API
# AI của mình, mà mỗi request tốn ~5.100 token. Giao diện chat chạy cùng origin
# với server nên không cần CORS; chỉ khi nhúng lên tên miền khác mới phải khai.
#   export CORS_ORIGINS="https://suoitien.vn,https://chat.suoitien.vn"
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env == "*":
    _cors_origins = ["*"]
    logger.warning("CORS_ORIGINS='*' — MỌI website gọi được API. Chỉ dùng khi thử nghiệm!")
elif _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost:5002", "http://127.0.0.1:5002"]
    logger.warning("CORS_ORIGINS chưa cấu hình — chỉ cho phép localhost. "
                   "Đặt CORS_ORIGINS trước khi nhúng lên tên miền thật.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rate limit ────────────────────────────────────────────────────────────────
# API AI mở công khai mà không giới hạn thì ai cũng đốt được ví: mỗi câu hỏi
# tốn ~5.100 token Grok. Cửa sổ trượt trong bộ nhớ — đủ cho triển khai 1 worker
# (đúng cấu hình khuyến nghị vì mỗi tiến trình nạp BGE-M3 ~2,2GB).
_RATE_LIMIT   = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))    # req/phút mỗi IP
_RATE_WINDOW  = 60.0
_rate_hits: dict = {}
_rate_lock = threading.Lock()
_RATE_PATHS = ("/api/chat", "/api/feedback", "/api/chat-image")


def _client_ip(request: Request) -> str:
    # Sau reverse proxy thì IP thật nằm ở X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if not any(path.startswith(p) for p in _RATE_PATHS):
        return await call_next(request)

    ip  = _client_ip(request)
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_WINDOW]
        if len(hits) >= _RATE_LIMIT:
            retry = int(_RATE_WINDOW - (now - hits[0])) + 1
            _rate_hits[ip] = hits
            logger.warning("Rate limit: %s vượt %d req/phút trên %s",
                           ip, _RATE_LIMIT, path)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry)},
                content={"detail": "Anh/chị gửi hơi nhanh, đợi em một chút nhé! 😊"},
            )
        hits.append(now)
        _rate_hits[ip] = hits
        # Dọn IP nguội để dict không phình vô hạn
        if len(_rate_hits) > 10000:
            for k in [k for k, v in _rate_hits.items()
                      if not v or now - v[-1] > _RATE_WINDOW]:
                _rate_hits.pop(k, None)
    return await call_next(request)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(chat_router,    prefix="/api")
app.include_router(get_admin_router())
app.include_router(webhook_router, prefix="/webhook")
app.include_router(content_router, prefix="/webhook")


# ── UI ────────────────────────────────────────────────────────────────────────
_UI_FILE = BASE_DIR / "chat_ui.html"

@app.get("/ui")
def ui():
    if not _UI_FILE.exists():
        raise HTTPException(status_code=404, detail="chat_ui.html not found")
    return FileResponse(_UI_FILE)


# ── Health check ───────────────────────────────────────────────────────────────
# ── Admin auth ────────────────────────────────────────────────────────────────
# Các endpoint quản trị/ghi dữ liệu PHẢI có ADMIN_KEY. Không dùng key mặc định
# nữa — key mặc định lộ trong source = ai cũng ghi được vào Golden Store.
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=True)


def require_admin(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    key = os.getenv("ADMIN_KEY", "")
    if not key:
        raise HTTPException(status_code=503,
                            detail="ADMIN_KEY chưa cấu hình — endpoint quản trị bị khoá")
    if creds.credentials != key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@app.get("/")
def health():
    return {"status": "ok", "bot": "Suối Tiên Bot", "version": "1.1.0"}


@app.get("/analytics")
def analytics_dashboard(hours: int = 24, _=Depends(require_admin)):
    """Analytics dashboard — query volume, latency, FAQ rate..."""
    try:
        from analytics import get_dashboard
        return get_dashboard(hours=hours)
    except Exception as e:
        return {"error": str(e)}


@app.get("/analytics/llm")
def llm_health(_=Depends(require_admin)):
    """Trạng thái các LLM provider."""
    try:
        from multi_llm import health_status
        return health_status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/hub/status")
def hub_status(_=Depends(require_admin)):
    """Trạng thái Tool Hub (Booking/CRM/Odoo)."""
    try:
        from tool_hub import hub_status
        return hub_status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/learning")
def learning_stats(_=Depends(require_admin)):
    """Thống kê hệ thống tự học."""
    try:
        from self_learning import learning_stats
        return learning_stats()
    except Exception as e:
        return {"error": str(e)}


@app.get("/critic")
def critic_stats_endpoint(_=Depends(require_admin)):
    """Thống kê Response Critic + Golden Store."""
    try:
        from response_critic import critic_stats
        return critic_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/golden")
async def add_golden_endpoint(request: Request, _=Depends(require_admin)):
    """Thêm câu trả lời chuẩn vào Golden Store (human feedback)."""
    try:
        from response_critic import add_golden
        data = await request.json()
        add_golden(
            query=data["query"],
            answer=data["answer"],
            context=data.get("context",""),
            source="human",
            lang=data.get("lang","vi"),
        )
        return {"status": "ok", "message": "Đã thêm vào Golden Store"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/health")
def health_detail():
    """Chi tiết trạng thái các components."""
    components = {}

    # Data files
    data_path  = Path(os.environ["SUOITIEN_DATA"])
    clean_path = Path(os.environ["SUOITIEN_CLEAN"])
    components["data_v2"]  = "ok" if data_path.exists()  else "missing"
    components["clean_v4"] = "ok" if clean_path.exists() else "missing"

    # Index files
    _st = index_status()
    components["faiss_index"] = "ok" if _st["faiss"] else "missing"
    components["bm25_index"]  = "ok" if _st["bm25"]  else "missing"

    # API key — kiểm ĐÚNG provider đang chạy. Trước đây luôn kiểm
    # ANTHROPIC_API_KEY trong khi hệ thống chạy Grok ⇒ health sai cả hai chiều:
    # báo "degraded" dù mọi thứ ổn, và báo "ok" dù chỉ mục đã mất.
    try:
        from llm_client import get_provider
        provider = (get_provider() or "").lower()
    except Exception:
        provider = ""
    key_env = {"grok": "XAI_API_KEY", "gemini": "GOOGLE_API_KEY",
               "anthropic": "ANTHROPIC_API_KEY"}.get(provider, "ANTHROPIC_API_KEY")
    components["llm_provider"] = provider or "unknown"
    components["llm_key"] = "ok" if os.getenv(key_env) else f"missing ({key_env})"

    components["owm_key"] = "ok" if os.getenv("OWM_API_KEY") else "missing (weather disabled)"
    components["content_webhook_secret"] = "ok" if os.getenv("CONTENT_WEBHOOK_SECRET") else "missing (webhook not secured)"
    components["admin_key"] = "ok" if os.getenv("ADMIN_KEY") else "missing (admin endpoints disabled)"
    components["cors_origins"] = ",".join(_cors_origins)
    components["rate_limit_per_min"] = _RATE_LIMIT

    # Thành phần BẮT BUỘC để trả lời đúng: thiếu bất kỳ cái nào là degraded.
    # Chỉ mục mất nghĩa là mất RAG — bot vẫn nói được nhưng nói theo trí nhớ LLM.
    critical = {
        "llm_key":     components["llm_key"] == "ok",
        "faiss_index": _st["faiss"],
        "bm25_index":  _st["bm25"],
        "data_v2":     components["data_v2"] == "ok",
        "clean_v4":    components["clean_v4"] == "ok",
    }
    failed = [k for k, v in critical.items() if not v]
    overall = "ok" if not failed else "degraded"
    body = {"status": overall, "components": components}
    if failed:
        body["degraded_because"] = failed
    # 503 để load balancer / uptime check phát hiện được, thay vì luôn 200
    return JSONResponse(status_code=200 if overall == "ok" else 503, content=body)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    dev_reload = os.getenv("DEV_RELOAD", "0") == "1"
    print(f"\n🚀 Suối Tiên Bot đang chạy tại http://localhost:{port}")
    print(f"   Docs: http://localhost:{port}/docs"
          f"   (reload={'ON' if dev_reload else 'OFF'})\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev_reload)
