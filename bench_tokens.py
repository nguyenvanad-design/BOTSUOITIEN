import sys, os, json
sys.path.insert(0,"core")
os.environ["SUOITIEN_DATA"]  = "core/data/suoitien_data_v2.json"
os.environ["SUOITIEN_CLEAN"] = "core/data/suoitien_clean_v4.json"
os.environ["SUOITIEN_BASE"]  = "core"
from dotenv import load_dotenv; load_dotenv()

from openai import OpenAI
client = OpenAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1")

from planner import plan, _PLANNER_SYSTEM, PLANNER_TOOLS, TOOL_RETRIEVAL_MAP
from tool_executor import execute_tool, merge_contexts
from responder import _build

queries = [
    "Gia ve vao cong bao nhieu?",
    "Co nhung tro choi gi?",
    "Teambuilding 50 nguoi gia bao nhieu?",
    "Combo Kham Pha co gi?",
]

print("%-35s %8s %9s %8s %9s %7s" % ("Query","Plan-in","Plan-out","Resp-in","Resp-out","Total"))
print("-"*85)

grand_in = grand_out = 0
oai_tools = [{"type":"function","function":{"name":t["name"],
    "description":t["description"],"parameters":t["input_schema"]}}
    for t in PLANNER_TOOLS]

for q in queries:
    # Planner
    r1 = client.chat.completions.create(
        model="grok-4.3", max_tokens=300,
        messages=[{"role":"system","content":_PLANNER_SYSTEM},
                  {"role":"user","content":q}],
        tools=oai_tools,
    )
    p_in  = r1.usage.prompt_tokens
    p_out = r1.usage.completion_tokens

    # Tools
    tool_calls = []
    for tc in (r1.choices[0].message.tool_calls or []):
        inp = json.loads(tc.function.arguments or "{}")
        cfg = TOOL_RETRIEVAL_MAP.get(tc.function.name,
              {"intent":"unknown","strategy":["bm25"]})
        tool_calls.append({"tool":tc.function.name,"input":inp,
                           "intent":cfg["intent"],"strategy":cfg["strategy"]})
    results = [execute_tool(c, lang="vi") for c in tool_calls]
    ctx = merge_contexts(results)

    # Responder
    system, messages = _build(q, ctx, "vi", [])
    r2 = client.chat.completions.create(
        model="grok-4.3", max_tokens=600,
        messages=[{"role":"system","content":system}]+messages)
    r_in  = r2.usage.prompt_tokens
    r_out = r2.usage.completion_tokens
    total = p_in+p_out+r_in+r_out
    grand_in  += p_in+r_in
    grand_out += p_out+r_out

    print("%-35s %8d %9d %8d %9d %7d" % (q[:35],p_in,p_out,r_in,r_out,total))

print("-"*85)
avg   = (grand_in+grand_out)//len(queries)
cost  = avg * 0.3 / 1_000_000
print("Trung binh : %d tokens/request" % avg)
print("Chi phi    : $%.5f/request = $%.3f/1000 req = $%.1f/1M req" % (cost,cost*1000,cost*1_000_000))
