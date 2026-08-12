"""
auto_updater.py — Tự động check sitemap diff mỗi giờ, rebuild data khi có URL mới
Pipeline: sitemap diff → crawl URLs mới → extract entities → hot-swap data + indexes
"""

import os
import json
import time
import hashlib
import threading
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [updater] %(message)s")
log = logging.getLogger("auto_updater")

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL      = "https://suoitien.vn"
SITEMAP_URL   = f"{BASE_URL}/sitemap.xml"
CHECK_INTERVAL = 60          # phút — check sitemap mỗi 60 phút
CRAWL_DELAY   = 1.5          # giây giữa các request
# Nâng từ 10: có 35 URL đủ điều kiện crawl lại mà mỗi vòng chỉ lấy 10 → hàng đợi
# không bao giờ rút hết, và trang động luôn bị trang chính sách tĩnh chiếm chỗ.
# Hash nội dung chặn ở phía sau nên crawl nhiều không kéo theo gọi LLM nhiều.
MAX_CRAWL     = int(os.getenv("SUOITIEN_MAX_CRAWL", "25"))
MIN_CONTENT   = 200          # chars tối đa content

_BASE_DIR     = Path(os.environ.get("SUOITIEN_BASE", Path(__file__).parent))
_DATA_DIR     = _BASE_DIR / "data"
_SITEMAP_STATE = _DATA_DIR / "sitemap_state.json"  # lưu lastmod đã biết
_CLEAN_FILE   = _DATA_DIR / "suoitien_clean_v4.json"
_DATA_FILE    = _DATA_DIR / "suoitien_data_v2.json"

# LLM provider cho entity extraction
XAI_API_KEY   = os.environ.get("XAI_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_PROVIDER  = os.environ.get("LLM_PROVIDER", "").lower().strip()

def _get_extract_provider():
    if LLM_PROVIDER == "grok" and XAI_API_KEY:   return "grok"
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY: return "anthropic"
    if XAI_API_KEY:   return "grok"
    if ANTHROPIC_KEY: return "anthropic"
    return None

EXTRACT_PROVIDER = _get_extract_provider()
_GROK_MODEL = os.environ.get("SUOITIEN_GROK_MODEL", "grok-4.20-0309-non-reasoning")
EXTRACT_MODEL = {
    "grok":      os.environ.get("SUOITIEN_EXTRACT_MODEL", _GROK_MODEL),
    "anthropic": os.environ.get("SUOITIEN_EXTRACT_MODEL", "claude-haiku-4-5-20251001"),
}.get(EXTRACT_PROVIDER or "grok", _GROK_MODEL)

# ── Sitemap diff ────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Load trạng thái sitemap đã biết {url: lastmod}."""
    if _SITEMAP_STATE.exists():
        try:
            return json.loads(_SITEMAP_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SITEMAP_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_sitemap(url: str) -> list[dict]:
    """Fetch sitemap XML, trả về [{url, lastmod}]."""
    entries = []
    try:
        resp = requests.get(url, timeout=10,
                            headers={"User-Agent": "SuoiTienBot/1.0"})
        if resp.status_code != 200:
            return entries
        soup = BeautifulSoup(resp.text, "xml")

        # Sub-sitemaps
        for sitemap_tag in soup.find_all("sitemap"):
            loc = sitemap_tag.find("loc")
            if loc:
                entries.extend(_fetch_sitemap(loc.text.strip()))

        # URL entries
        for url_tag in soup.find_all("url"):
            loc     = url_tag.find("loc")
            lastmod = url_tag.find("lastmod")
            if loc:
                entries.append({
                    "url":     loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod else "",
                })
    except Exception as e:
        log.warning(f"Sitemap fetch error {url}: {e}")
    return entries


def get_new_or_updated_urls() -> list[dict]:
    """So sánh sitemap với state đã lưu → trả về URLs mới/updated."""
    state   = _load_state()
    entries = _fetch_sitemap(SITEMAP_URL)
    if not entries:
        log.warning("Sitemap empty or unreachable")
        return []

    new_entries  = []
    forced_dyn   = []
    for entry in entries:
        url     = entry["url"]
        lastmod = entry["lastmod"]

        # Skip URLs đã biết là 404
        if state.get(url) == "404":
            continue

        slug = url.rstrip("/").split("/")[-1]
        if not _is_relevant_slug(slug):
            continue

        # Mới hoàn toàn hoặc lastmod thay đổi
        if url not in state or (lastmod and state[url] != lastmod):
            new_entries.append(entry)
        elif _is_dynamic_page(slug):
            # KHÔNG tin lastmod cho trang động.
            #
            # Đo thực tế 13/08/2026 trên sitemap suoitien.vn: 367/460 URL có
            # lastmod đóng băng ở 2024-05-07 — trong đó có đúng các trang đổi
            # nhiều nhất: uu-dai-va-su-kien, uu-dai-khuyen-mai, bang-gia-1,
            # toàn bộ combo-*. Website đổi khuyến mãi mà không đụng lastmod, nên
            # chỉ dựa vào lastmod là các trang này crawl một lần rồi thôi vĩnh
            # viễn — combo 240k không bao giờ về được.
            # → Crawl lại định kỳ và so HASH NỘI DUNG để biết có đổi thật không.
            forced_dyn.append(entry)

    # Trang động lên TRƯỚC: hàng đợi cũ toàn trang chính sách tĩnh chiếm chỗ
    # (chinh-sach-thanh-toan, chinh-sach-khieu-nai...) trong khi MAX_CRAWL=10.
    new_entries.sort(key=lambda e: 0 if _is_dynamic_page(
        e["url"].rstrip("/").split("/")[-1]) else 1)

    picked = new_entries[:MAX_CRAWL]
    if len(picked) < MAX_CRAWL:
        picked += forced_dyn[: MAX_CRAWL - len(picked)]

    log.info("Sitemap: %d total, %d new/updated, %d trang động soát lại → crawl %d",
             len(entries), len(new_entries), len(forced_dyn), len(picked))
    return picked


def _is_dynamic_page(slug: str) -> bool:
    """
    Trang có nội dung đổi liên tục (bảng giá, combo, ưu đãi, tin tức).
    Những trang này phải soát lại định kỳ vì lastmod của website không đáng tin.
    """
    s = (slug or "").lower()
    return any(k in s for k in (
        "bang-gia", "gia-ve", "combo", "uu-dai", "khuyen-mai", "su-kien",
        "tin-tuc", "le-hoi", "chuong-trinh", "deal", "sale", "chon-ve",
    ))


def _content_hash(text: str) -> str:
    """Hash phần chữ đã chuẩn hoá — đổi hash nghĩa là nội dung đổi thật."""
    norm = " ".join((text or "").split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _load_content_hashes() -> dict:
    f = _DATA_DIR / "content_hashes.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_content_hashes(h: dict):
    try:
        (_DATA_DIR / "content_hashes.json").write_text(
            json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Không lưu được content_hashes: {e}")


def _is_relevant_slug(slug: str) -> bool:
    """Lọc bỏ URLs không liên quan (tuyển dụng, nội bộ, generic SEO)."""
    skip_patterns = [
        "tuyen-dung", "pho-phong", "bep-chinh",
        "dia-diem-", "khu-du-lich-", "cong-vien-nuoc",
        "loi-chuc-", "giang-sinh-", "catering-la-gi",
        "tea-break-la-gi", "slogan-", "concept-chuong",
        "dam-cuoi-bac-vang", "thao-cam-vien",
        "anh-tong-hop", "ladingpage",
    ]
    slug_lower = slug.lower()
    return not any(p in slug_lower for p in skip_patterns) and len(slug) > 3


# ── Crawl new URLs ─────────────────────────────────────────────────────────────

def _crawl_url(url: str) -> dict | None:
    """Crawl 1 URL → {url, slug, title, text, char_count, category}"""
    try:
        resp = requests.get(url, timeout=10,
                            headers={"User-Agent": "SuoiTienBot/1.0",
                                     "Accept-Language": "vi-VN"})
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script","style","nav","footer","header","aside","form"]):
            tag.decompose()

        title = soup.find("h1") or soup.find("title")
        title = title.get_text(strip=True) if title else ""

        main  = (soup.find("main") or soup.find("article") or
                 soup.find(class_=lambda c: c and any(
                     x in c for x in ["content","post","entry","page-content"]
                 )) or soup.find("body"))
        if not main:
            return None

        text = main.get_text(separator="\n", strip=True)
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        if len(text) < MIN_CONTENT:
            return None

        slug = url.rstrip("/").split("/")[-1]
        cat  = _guess_category(slug, title, text)

        return {
            "url":        url,
            "slug":       slug,
            "title":      title,
            "text":       text[:4000],
            "char_count": len(text),
            "category":   cat,
            "crawled_at": datetime.now().isoformat(),
        }
    except Exception as e:
        log.warning(f"Crawl error {url}: {e}")
        return None


# Field vòng đời do hệ thống quản lý (crawler không sinh ra) — phải bảo toàn
# khi cập nhật entity cũ, nếu không mỗi lần crawl sẽ mất trạng thái ẩn/ưu tiên.
_LIFECYCLE_FIELDS = ("is_active", "priority", "valid_from", "valid_to")


# Dấu hiệu BÀI CHIẾN DỊCH (tin khuyến mãi/sự kiện), khác với TRANG DANH MỤC vé.
# Bài "tặng 2.000 vé dịp Quốc khánh" là SỰ KIỆN, không phải một loại vé — nhưng
# slug của nó chứa "ve-cong" nên luật tickets (xét trước) cướp mất. Kết quả: tin
# 2/9 rơi vào bucket tickets, không bao giờ xuất hiện khi khách hỏi sự kiện.
_CAMPAIGN_SLUG = (
    "uu-dai", "khuyen-mai", "giam-gia", "tang-", "mung-", "chao-mung",
    "le-hoi", "su-kien", "quoc-khanh", "2-9", "30-4", "1-5", "1-6",
    "tet-", "-tet", "trung-thu", "giang-sinh", "noel", "halloween",
    "sinh-nhat", "ky-niem", "san-deal", "deal-", "flash", "sale",
    "mua-thu", "mua-he", "mua-xuan", "he-ruc-ro", "phu-nu", "8-3", "20-10",
)

# Trang DANH MỤC SẢN PHẨM có giá — bảng giá và combo. Đây là nơi giá phải được
# trích ra thành bản ghi VÉ, vì câu hỏi "Combo Trải Nghiệm giá bao nhiêu?" đi
# vào search_tickets chứ không vào search_events.
#
# "combo" bắt buộc phải có: thiếu nó thì slug `combo`, `combo-ky-quan`,
# `san-combo-suoi-tien-2026` rơi hết xuống nhánh cuối → "info", mà `info` KHÔNG
# nằm trong EXTRACT_CATS ⇒ trang combo chính thức không bao giờ được trích xuất.
# Đây chính là lý do combo 240k không bao giờ về tới bảng vé.
_TICKET_CATALOG = ("bang-gia", "chi-tiet-ve", "gia-ve", "mua-ve-online",
                   "chon-ve", "combo")


def _guess_category(slug: str, title: str, text: str) -> str:
    slug = slug.lower()

    # Xét TRƯỚC mọi luật khác: bài chiến dịch → events, trừ khi đó đúng là
    # trang bảng giá (vd "bang-gia" có thể kèm chữ "uu-dai" trong slug).
    if any(k in slug for k in _CAMPAIGN_SLUG) and \
            not any(k in slug for k in _TICKET_CATALOG):
        return "events"

    rules = [
        # "ve-" quá rộng: bắt nhầm "ve-tranh" (vẽ tranh), "ve-dep"... → dùng
        # tiền tố cụ thể hơn
        (["bang-gia","chi-tiet-ve","mua-ve","combo",
          "ve-cong","ve-vao","ve-tron-goi","ve-doan","gia-ve"], "tickets"),
        (["go-kart","infinity","twin-race","xe-tang","sky-bounder",
          "bien-tien","thuyen","phim-","nha-ma","tagada","dia-xoay",
          "vong-xoay","ghe-bay","ca-sau","vuong-quoc"], "attractions"),
        (["le-hoi","su-kien","uu-dai","khuyen-mai","tin-tuc",
          "ky-niem","ra-mat","chao-mung"], "events"),
        (["teambuilding","team-building","cam-trai","hoi-nghi",
          "ngoai-khoa","tiec-cuoi","gala"], "teambuilding"),
        (["nha-hang","am-thuc","cung-dinh","lau-","pho-lau",
          "pho-am","tram-dung-chan","sieu-thi"], "restaurant"),
        (["tuong-dai","cong-trinh","den-tho","tam-linh","van-hoa",
          "tu-linh","linh-cung","thap","quang-truong"], "culture"),
        (["farm","vuon-nho","sung-my","trai-cay","nong-nghiep"], "farm"),
        (["gio-mo-cua","dia-chi","lien-he","duong-di","chinh-sach",
          "quy-dinh","dich-vu","cam-nang","tin-tuc"], "info"),
    ]
    for keywords, cat in rules:
        if any(k in slug for k in keywords):
            return cat
    return "info"


# ── Extract entities từ new docs ───────────────────────────────────────────────

def _extract_entities_batch(new_docs: list[dict]) -> dict:
    """Extract entities từ new_docs dùng Haiku, trả về {bucket: [items]}."""
    if not EXTRACT_PROVIDER:
        log.warning("No LLM key configured — skip entity extraction")
        return {}

    if EXTRACT_PROVIDER == "grok":
        from openai import OpenAI
        client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")
        log.info(f"Extract using Grok ({EXTRACT_MODEL})")
    else:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        log.info(f"Extract using Anthropic ({EXTRACT_MODEL})")

    PROMPTS = {
        "tickets":      "Extract thông tin VÉ VÀO CỬA. JSON array: [{ticket_id,name,zone,price_adult,price_child,includes,notes,source_slug}]. CHỈ JSON.",
        "attractions":  "Extract ĐIỂM THAM QUAN/TRÒ CHƠI. JSON array: [{attraction_id,name,type,zone,description,thrill_level,extra_fee,highlights,source_slug}]. CHỈ JSON.",
        "events":       "Extract SỰ KIỆN/LỄ HỘI/ƯU ĐÃI. JSON array: [{event_id,name,type,status,date_start,description,special_offers,source_slug}]. CHỈ JSON.",
        "teambuilding": "Extract GÓI TEAMBUILDING/HỘI NGHỊ. JSON array: [{package_id,name,type,duration,price_per_person,includes,source_slug}]. CHỈ JSON.",
        "restaurant":   "Extract NHÀ HÀNG/ẨM THỰC. JSON array: [{restaurant_id,name,type,cuisine_type,signature_dishes,source_slug}]. CHỈ JSON.",
        "info":         "Extract THÔNG TIN HỮU ÍCH. JSON array: [{info_id,topic,title,content,source_slug}]. CHỈ JSON.",
    }
    CAT_MAP = {"culture":"attractions","farm":"attractions","tours":"teambuilding","kids":"attractions","policy":"info"}

    results = {}
    for doc in new_docs:
        cat    = doc.get("category","info")
        bucket = CAT_MAP.get(cat, cat)
        prompt = PROMPTS.get(bucket, PROMPTS["info"])

        try:
            content = f"{prompt}\n\nSlug: {doc['slug']}\n\n{doc['text'][:2000]}"
            if EXTRACT_PROVIDER == "grok":
                resp = client.chat.completions.create(
                    model=EXTRACT_MODEL, max_tokens=1500,
                    messages=[{"role":"user","content":content}]
                )
                raw = resp.choices[0].message.content or ""
                raw = raw.strip()
            else:
                msg = client.messages.create(
                    model=EXTRACT_MODEL, max_tokens=1500,
                    messages=[{"role":"user","content":content}]
                )
                raw = msg.content[0].text.strip()
            import re as _re
            raw = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=_re.MULTILINE).strip()
            # Fix truncated JSON: nếu bị cắt giữa chừng → thêm đóng ngoặc
            if raw.endswith(","):
                raw = raw[:-1]
            if not raw.endswith("]"):
                # Tìm item cuối hoàn chỉnh
                last_complete = raw.rfind("},")
                if last_complete > 0:
                    raw = raw[:last_complete+1] + "]"
                elif raw.count("{") > raw.count("}"):
                    raw = raw + "}]"
                else:
                    raw = raw + "]"
            items = json.loads(raw)
            if isinstance(items, list) and items:
                results.setdefault(bucket, []).extend(items)
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"Extract error {doc['slug']}: {e}")

    return results


# ── Hot-swap data ──────────────────────────────────────────────────────────────

def _sweep_lifecycle():
    """
    Đánh dấu nội dung động đã hết hạn (is_active=False) sau mỗi lần nạp dữ liệu.

    Chỉ ĐỔI CỜ, không xoá bản ghi — để còn tra cứu lịch sử và để thao tác này
    đảo ngược được. Ghi báo cáo ra data/lifecycle_sweep_report.json để soát.
    """
    try:
        import sys
        sys.path.insert(0, str(_BASE_DIR / "core"))
        from content_lifecycle import sweep, apply_sweep, build_crawl_map

        from content_lifecycle import normalize_dates

        data  = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        clean = json.loads(_CLEAN_FILE.read_text(encoding="utf-8"))

        # Chuẩn hoá ngày TRƯỚC khi phán định hạn dùng. Ngày hỏng mà nuốt im
        # lặng thì bản ghi trượt mọi luật và sống vĩnh viễn.
        date_errors = []
        for bucket, items in data.items():
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict):
                    for err in normalize_dates(it):
                        date_errors.append(f"[{bucket}] {it.get('name', '?')}: {err}")
        if date_errors:
            log.warning("Ngày không hợp lệ (%d) — đã loại bỏ:", len(date_errors))
            for e in date_errors[:10]:
                log.warning("   %s", e)

        report = sweep(data, build_crawl_map(clean))
        n = apply_sweep(data, report)
        if n:
            _DATA_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (_DATA_DIR / "lifecycle_sweep_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Lifecycle sweep: ẩn %d, hiện lại %d, không rõ ngày %d",
                 len(report["to_hide"]), len(report["to_show"]),
                 len(report["undated"]))
    except Exception as e:
        log.warning(f"Lifecycle sweep bỏ qua: {e}")


def _hot_swap_data(new_docs: list[dict], new_entities: dict):
    """
    Merge new_docs + new_entities vào files hiện tại.
    Hot-swap: không restart server, modules tự reload khi cần.
    """
    # 1. Update clean_v4.json
    try:
        existing_docs = json.loads(_CLEAN_FILE.read_text(encoding="utf-8"))
        existing_slugs = {d["slug"] for d in existing_docs}
        added_docs = 0
        for doc in new_docs:
            if doc["slug"] in existing_slugs:
                # Update existing
                for i, d in enumerate(existing_docs):
                    if d["slug"] == doc["slug"]:
                        existing_docs[i] = doc
                        break
            else:
                existing_docs.append(doc)
                added_docs += 1
        _CLEAN_FILE.write_text(json.dumps(existing_docs, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"clean_v4.json: +{added_docs} new, {len(new_docs)-added_docs} updated")
    except Exception as e:
        log.error(f"Error updating clean_v4: {e}")

    # 2. Update data_v2.json
    if new_entities:
        try:
            existing = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
            for bucket, items in new_entities.items():
                if bucket not in existing:
                    existing[bucket] = []
                # Update-by-ID: ID đã có → THAY THẾ (nội dung đổi được cập nhật),
                # ID mới → thêm. Trước đây chỉ append nên combo/giá đổi không cập nhật.
                id_field = {"tickets":"ticket_id","attractions":"attraction_id",
                            "events":"event_id","teambuilding":"package_id",
                            "restaurant":"restaurant_id","info":"info_id"}.get(bucket,"id")
                idx_by_id = {i.get(id_field,""): k for k, i in enumerate(existing[bucket])
                             if i.get(id_field,"")}
                added = updated = 0
                for item in items:
                    iid = item.get(id_field, "")
                    if iid and iid in idx_by_id:
                        old = existing[bucket][idx_by_id[iid]]
                        # Crawler KHÔNG trích xuất field vòng đời → phải giữ lại từ bản
                        # cũ, nếu không mỗi lần crawl sẽ xoá sạch is_active/priority.
                        merged = {**old, **item}
                        for keep in _LIFECYCLE_FIELDS:
                            if keep in old and keep not in item:
                                merged[keep] = old[keep]
                        existing[bucket][idx_by_id[iid]] = merged
                        updated += 1
                    else:
                        existing[bucket].append(item)
                        added += 1
                log.info(f"data_v2 {bucket}: +{added} new, {updated} updated")
            _DATA_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.error(f"Error updating data_v2: {e}")

    # 2.5 Quét vòng đời — nội dung động hết hạn thì tự ẩn.
    # Không có bước này, pipeline chỉ biết THÊM: 151 sự kiện tích tụ từ 2023,
    # và bot trả lời "hiện tại đang có Giỗ Tổ Hùng Vương" vào tháng 8.
    _sweep_lifecycle()

    # 3. Reload schema_search in-process
    try:
        import importlib, sys
        if "schema_search" in sys.modules:
            mod = sys.modules["schema_search"]
            mod._DB = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
            log.info("schema_search._DB reloaded ✅")
    except Exception as e:
        log.warning(f"Schema reload: {e}")

    # 4. Rebuild BM25 (nhanh, < 5s)
    try:
        import sys
        sys.path.insert(0, str(_BASE_DIR / "core"))
        from bm25_search import build_bm25
        build_bm25(force=True)
        # Reload BM25 in-process
        if "bm25_search" in sys.modules:
            mod = sys.modules["bm25_search"]
            mod._bm25 = None
            mod._chunks = None
            log.info("BM25 rebuilt + reloaded ✅")
    except Exception as e:
        log.warning(f"BM25 rebuild: {e}")

    # 5. Incremental FAISS update — thêm vectors mới ngay, không chờ 3h
    try:
        from vector_search_incremental import add_documents, flush_all
        add_documents(new_docs, force_flush=len(new_docs) >= 3)
        log.info("FAISS incremental update queued: %d docs", len(new_docs))
    except Exception as e:
        log.warning(f"Incremental FAISS: {e} — full rebuild at 3 AM fallback")
        log.info("FAISS full rebuild scheduled for 3 AM")


# ── Main update job ────────────────────────────────────────────────────────────

_update_lock = threading.Lock()

def run_update():
    """Job chính: check sitemap diff → crawl → extract → hot-swap."""
    if not _update_lock.acquire(blocking=False):
        log.info("Update already running, skip")
        return

    try:
        log.info("=== AUTO UPDATE START ===")
        start = time.time()

        # 1. Sitemap diff
        new_entries = get_new_or_updated_urls()
        if not new_entries:
            log.info("No new URLs found")
            return

        # 2. Crawl new URLs
        new_docs = []
        state    = _load_state()
        hashes   = _load_content_hashes()
        unchanged = 0
        for entry in new_entries:
            doc = _crawl_url(entry["url"])
            if doc:
                # So HASH nội dung: trang động crawl lại mỗi vòng, nhưng chỉ
                # đưa vào pipeline khi chữ thật sự đổi — tránh gọi LLM trích
                # xuất lại cùng một nội dung mỗi giờ (tốn token, nhiễu data).
                h   = _content_hash(doc.get("text", ""))
                old = hashes.get(entry["url"])
                state[entry["url"]] = entry["lastmod"] or "ok"
                if old == h:
                    unchanged += 1
                    log.debug("  ⏭  %s không đổi (hash %s)", doc["slug"], h)
                else:
                    hashes[entry["url"]] = h
                    new_docs.append(doc)
                    log.info("  ✅ %s [%s] %dc %s", doc["slug"], doc["category"],
                             doc["char_count"], "MỚI" if old is None else "ĐỔI NỘI DUNG")
            else:
                # Lưu 404 vào state với marker đặc biệt → skip lần sau
                state[entry["url"]] = "404"
                log.info(f"  ❌ {entry['url']}")
            time.sleep(CRAWL_DELAY)

        _save_content_hashes(hashes)
        _save_state(state)

        if not new_docs:
            log.info("Không có nội dung đổi (%d trang giữ nguyên)", unchanged)
            return

        # 3. Extract entities — chỉ categories có structured data
        EXTRACT_CATS = {"tickets", "events", "teambuilding", "restaurant"}
        extract_docs = [d for d in new_docs if d.get("category") in EXTRACT_CATS]
        if extract_docs:
            log.info(f"Extracting {len(extract_docs)}/{len(new_docs)} structured docs...")
            new_entities = _extract_entities_batch(extract_docs)
        else:
            log.info("No structured docs — skip LLM call")
            new_entities = {}

        # 4. Hot-swap
        _hot_swap_data(new_docs, new_entities)
        _save_state(state)

        elapsed = time.time() - start
        log.info(f"=== UPDATE DONE: {len(new_docs)} docs, {elapsed:.1f}s ===")

    except Exception as e:
        log.error(f"Update error: {e}")
    finally:
        _update_lock.release()


def rebuild_faiss_nightly():
    """Rebuild FAISS lúc 3h sáng — tốn time nhưng không ảnh hưởng user."""
    log.info("Nightly FAISS rebuild starting...")
    try:
        import sys
        sys.path.insert(0, str(_BASE_DIR / "core"))
        from vector_search import build_index
        build_index(force=True)
        # Reload
        if "vector_search" in sys.modules:
            mod = sys.modules["vector_search"]
            mod._index = None
            mod._chunks = None
            log.info("FAISS index rebuilt + reloaded ✅")
    except Exception as e:
        log.error(f"FAISS rebuild error: {e}")


# ── Scheduler ──────────────────────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None

def start_scheduler():
    """Khởi động APScheduler background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        timezone="Asia/Ho_Chi_Minh",
    )
    # Sitemap check mỗi 60 phút
    _scheduler.add_job(run_update, "interval", minutes=CHECK_INTERVAL,
                       id="sitemap_check", replace_existing=True)
    # FAISS rebuild mỗi đêm 3h sáng
    _scheduler.add_job(rebuild_faiss_nightly, "cron", hour=3, minute=0,
                       id="faiss_nightly", replace_existing=True)

    _scheduler.start()
    log.info(f"APScheduler started: sitemap every {CHECK_INTERVAL}m, FAISS at 03:00 ICT")

    # Chỉ run ngay nếu state trống (lần đầu) hoặc state cũ > 2 giờ
    state = _load_state()
    if not state:
        log.info("First run — crawling all URLs")
        threading.Thread(target=run_update, daemon=True).start()
    else:
        log.info(f"State has {len(state)} entries — skip startup crawl, next run in {CHECK_INTERVAL}m")
    return _scheduler


def stop_scheduler():
    """Dừng scheduler khi shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


# ── FastAPI integration ────────────────────────────────────────────────────────

def get_router():
    """FastAPI router để expose /admin/refresh endpoint."""
    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    router  = APIRouter()
    bearer  = HTTPBearer()
    def verify(creds: HTTPAuthorizationCredentials = Depends(bearer)):
        # Đọc động + KHÔNG có key mặc định (key mặc định lộ trong source)
        key = os.environ.get("ADMIN_KEY", "")
        if not key:
            raise HTTPException(status_code=503, detail="ADMIN_KEY chưa cấu hình")
        if creds.credentials != key:
            raise HTTPException(status_code=401, detail="Invalid admin key")

    @router.post("/admin/refresh")
    def manual_refresh(creds = Depends(verify)):
        """Manual trigger: force refresh ngay lập tức."""
        threading.Thread(target=run_update, daemon=True).start()
        return {"status": "refresh triggered", "ts": datetime.now().isoformat()}

    @router.get("/admin/status")
    def update_status(creds = Depends(verify)):
        """Xem trạng thái update gần nhất."""
        state = _load_state()
        return {
            "tracked_urls": len(state),
            "last_check":   max(state.values(), default="never") if state else "never",
            "data_file":    str(_DATA_FILE),
            "data_exists":  _DATA_FILE.exists(),
        }

    return router


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        entries = get_new_or_updated_urls()
        print(f"New/updated URLs: {len(entries)}")
        for e in entries[:10]:
            print(f"  {e['url']} [{e.get('lastmod','')}]")
    elif "--run" in sys.argv:
        run_update()
    else:
        print("Usage: python auto_updater.py --check | --run")
