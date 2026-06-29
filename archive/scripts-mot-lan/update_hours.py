"""Bổ sung giờ mở cửa thật (xác minh từ web 12/06/2026) vào INFO_GIO_MO_CUA."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "core" / "data" / "suoitien_data_v2.json"

NEW_CONTENT = (
    "Giờ hoạt động Công viên Văn hóa Suối Tiên: mở cửa HÀNG NGÀY từ Thứ 2 đến "
    "Chủ nhật, 7h30 sáng – 17h00 chiều. Dịp lễ, Tết: mở sớm từ 7h00 và thường "
    "kéo dài đến tối theo chương trình lễ hội đêm. Giờ có thể điều chỉnh theo "
    "mùa sự kiện — chắc chắn nhất gọi hotline 1900 636 787. "
    "Địa chỉ: 120 Xa Lộ Hà Nội, P. Tăng Nhơn Phú, TP. Thủ Đức, TP.HCM."
)

d = json.loads(DATA.read_text(encoding="utf-8"))
updated = False
for item in d["info"]:
    if item.get("info_id") == "INFO_GIO_MO_CUA":
        item["content"] = NEW_CONTENT
        item["last_updated"] = "2026-06-12"
        item["source_slug"] = "web-research-mia.vn-bonboncar.vn"
        updated = True

if not updated:
    d["info"].append({
        "info_id": "INFO_GIO_MO_CUA",
        "topic": "gio_mo_cua",
        "title": "Giờ mở cửa Suối Tiên",
        "content": NEW_CONTENT,
        "last_updated": "2026-06-12",
        "source_slug": "web-research-mia.vn-bonboncar.vn",
    })

DATA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("Đã cập nhật INFO_GIO_MO_CUA" if updated else "Đã thêm mới INFO_GIO_MO_CUA")

# Verify qua đúng đường code bot dùng
import sys, os
sys.path.insert(0, str(ROOT / "core"))
os.environ["SUOITIEN_DATA"]  = str(DATA)
os.environ["SUOITIEN_CLEAN"] = str(ROOT / "core" / "data" / "suoitien_clean_v4.json")
from schema_search import get_opening_hours
print("\nget_opening_hours() →", get_opening_hours())
