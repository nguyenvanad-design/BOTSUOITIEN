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
import logging
import asyncio
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
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from api.chat            import router as chat_router
from api.webhook         import router as webhook_router
from api.webhook_content import router as content_router


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
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning(
            "ANTHROPIC_API_KEY chưa set — Planner/Responder sẽ chạy fallback "
            "(chất lượng trả lời giảm mạnh)!"
        )
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

# CORS: production nên giới hạn origin thật qua env, vd:
#   export CORS_ORIGINS="https://suoitien.vn,https://chat.suoitien.vn"
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    index_dir = CORE_DIR / "data" / "faiss_index"
    components["faiss_index"] = "ok" if (index_dir / "index.faiss").exists() else "missing"
    components["bm25_index"]  = "ok" if (index_dir / "bm25.pkl").exists()    else "missing"

    # API keys
    components["anthropic_key"] = "ok" if os.getenv("ANTHROPIC_API_KEY") else "missing"
    components["owm_key"] = "ok" if os.getenv("OWM_API_KEY") else "missing (weather disabled)"
    components["content_webhook_secret"] = "ok" if os.getenv("CONTENT_WEBHOOK_SECRET") else "missing (webhook not secured)"

    overall = "ok" if components["anthropic_key"] == "ok" else "degraded"
    return {"status": overall, "components": components}


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    dev_reload = os.getenv("DEV_RELOAD", "0") == "1"
    print(f"\n🚀 Suối Tiên Bot đang chạy tại http://localhost:{port}")
    print(f"   Docs: http://localhost:{port}/docs"
          f"   (reload={'ON' if dev_reload else 'OFF'})\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev_reload)
