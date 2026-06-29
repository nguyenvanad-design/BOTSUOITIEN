"""Test nhanh provider Grok qua llm_client — completion, tool calling, streaming."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import llm_client
import planner

print("provider:", llm_client.get_provider())
print("model:", llm_client.resolve_model("planner"))

# Test 1: completion
out = llm_client.complete(None, [{"role": "user", "content": "Nói 'xin chào' bằng 1 từ."}], max_tokens=50)
print("completion:", repr(out))

# Test 2: tool calling với 8 tools thật của planner
calls = llm_client.call_tools(
    system="Bạn là planner cho chatbot Suối Tiên. Phân tích câu hỏi → gọi đúng tool.",
    messages=[{"role": "user", "content": "Giá vé vào cổng bao nhiêu và đi xe buýt được không?"}],
    tools=planner.PLANNER_TOOLS, max_tokens=300)
print("tool calls:", [(c["name"], list(c["input"].keys())) for c in calls])

# Test 3: streaming
chunks = list(llm_client.complete_stream(None, [{"role": "user", "content": "Đếm từ 1 đến 3."}], max_tokens=50))
print("stream chunks:", len(chunks), "->", repr("".join(chunks))[:80])
