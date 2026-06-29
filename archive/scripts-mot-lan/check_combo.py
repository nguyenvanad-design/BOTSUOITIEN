import json

for f in ["core/data/suoitien_data_v2.json", "core/data/suoitien_clean_v4.json"]:
    content = open(f, encoding="utf-8").read()
    hits = content.count("Khám Phá") + content.count("Kham Pha")
    print(f"{f}:")
    print(f"  Co Kham Pha: {hits} lan")
    idx = content.find("Khám Phá")
    if idx > 0:
        ctx = content[max(0,idx-150):idx+400].replace("\n", " ")
        print("  Context:", ctx[:400])
    print()
