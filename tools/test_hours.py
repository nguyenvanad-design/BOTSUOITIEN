"""Test giờ mở cửa sau khi bổ sung data — FAQ path (VI/EN) + LLM path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
os.environ.setdefault("SUOITIEN_DATA",  str(ROOT / "core" / "data" / "suoitien_data_v2.json"))
os.environ.setdefault("SUOITIEN_CLEAN", str(ROOT / "core" / "data" / "suoitien_clean_v4.json"))

from faq_engine import faq_match

print("EN FAQ:", faq_match("What time does the park open?", lang="en")["answer"][:140])
print()

from chat_pipeline import chat
r = chat("Mở cửa từ mấy giờ đến mấy giờ?")
print(f"VI [{r['source']}]:", r["answer"][:250])
