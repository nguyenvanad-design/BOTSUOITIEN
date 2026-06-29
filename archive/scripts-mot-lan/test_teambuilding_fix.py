"""Verify fix: câu teambuilding với group_size từng crash khi Grok trả string."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
os.environ.setdefault("SUOITIEN_BASE",  str(ROOT / "core"))
os.environ.setdefault("SUOITIEN_DATA",  str(ROOT / "core" / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(ROOT / "core" / "data" / "suoitien_clean_v4.json"))

from chat_pipeline import chat

for q in ["Teambuilding 50 người giá bao nhiêu?",
          "team building 100 nguoi co goi nao",
          "Trẻ 3 tuổi cao 95cm chơi được gì?"]:
    r = chat(q)
    ok = r["source"] != "fallback" and len(r["answer"]) > 30
    print(f"{'OK ' if ok else 'FAIL'} [{r['source']}] {q}")
    print(f"     {r['answer'][:120]}...")
