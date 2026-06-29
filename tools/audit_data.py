"""So sánh cấu trúc + số lượng entry giữa các file data JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = [
    "data/suoitien_new.json",
    "data/suoitien_merged.json",
    "data/suoitien_data_v1.json",
    "data/suoitien_data_v2.json",
    "core/data/suoitien_data_v2.json",
    "data/suoitien_clean_v4.json",
    "core/data/suoitien_clean_v4.json",
    "data/extract_progress.json",
    "suoitien_schema_v1.json",
]

def describe(obj, depth=0):
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if isinstance(v, list):
                parts.append(f"{k}[{len(v)}]")
            elif isinstance(v, dict) and depth == 0:
                inner = ", ".join(f"{k2}[{len(v2)}]" if isinstance(v2, list) else k2
                                  for k2, v2 in list(v.items())[:8])
                parts.append(f"{k}{{{inner}}}")
            else:
                parts.append(k)
        return ", ".join(parts[:12])
    if isinstance(obj, list):
        return f"list[{len(obj)}]"
    return type(obj).__name__

for f in FILES:
    p = ROOT / f
    if not p.exists():
        print(f"--- {f}: KHÔNG TỒN TẠI")
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"--- {f} ({p.stat().st_size//1024}KB)")
        print(f"    {describe(data)}")
    except Exception as e:
        print(f"--- {f}: LỖI PARSE — {e}")
