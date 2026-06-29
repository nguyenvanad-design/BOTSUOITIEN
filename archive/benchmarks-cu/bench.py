import time, os
from pathlib import Path
_BASE = Path(__file__).parent
os.environ.setdefault('SUOITIEN_DATA',  str(_BASE / 'data' / 'suoitien_data_v2.json'))
os.environ.setdefault('SUOITIEN_CLEAN', str(_BASE / 'data' / 'suoitien_clean_v4.json'))
os.environ.setdefault('SUOITIEN_BASE',  str(_BASE))

from language_detector import detect_lang
from planner import plan
from tool_executor import execute_tool, merge_contexts
from responder import respond

query = 'gia ve vao cong bao nhieu'

t0 = time.perf_counter()
lang = detect_lang(query)
print(f'detect_lang: {(time.perf_counter()-t0)*1000:.0f}ms')

t1 = time.perf_counter()
tool_calls = plan(query)
print(f'planner: {(time.perf_counter()-t1)*1000:.0f}ms | tools={[c["tool"] for c in tool_calls]}')

t2 = time.perf_counter()
tool_results = [execute_tool(c, lang=lang) for c in tool_calls]
print(f'execute_tools: {(time.perf_counter()-t2)*1000:.0f}ms')

t3 = time.perf_counter()
ctx = merge_contexts(tool_results)
print(f'merge_context: {(time.perf_counter()-t3)*1000:.0f}ms | ctx_len={len(ctx)}')

t4 = time.perf_counter()
resp = respond(query, ctx, lang=lang)
print(f'responder: {(time.perf_counter()-t4)*1000:.0f}ms')

print(f'TOTAL: {(time.perf_counter()-t0)*1000:.0f}ms')
