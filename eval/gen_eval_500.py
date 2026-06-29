"""
gen_eval_500.py — Generate 500 eval cases từ suoitien_data_v2.json
Chạy: python gen_eval_500.py
Output: eval/eval_500.json

Distribution:
  L1 FAQ:          100 cases (20%)
  L2 Schema:       200 cases (40%)
  L3 Complex:       80 cases (16%)
  L4 Edge/typo:     80 cases (16%)
  L4 Multilang:     40 cases  (8%)
  Total:           500 cases
"""

import json
import random
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent
_data_env = os.environ.get("SUOITIEN_DATA")
DATA_PATH = Path(_data_env) if _data_env else BASE / "core" / "data" / "suoitien_data_v2.json"

with open(DATA_PATH, encoding="utf-8") as f:
    DATA = json.load(f)

random.seed(42)
cases = []
_id = 0

def _id_next(prefix):
    global _id
    _id += 1
    return f"{prefix}_{_id:04d}"


# ── Helpers ────────────────────────────────────────────────────────────────────
def case(id_, level, category, query, must_contain=None, must_not_contain=None):
    return {
        "id":              id_,
        "level":           level,
        "category":        category,
        "query":           query,
        "must_contain":    must_contain or [],   # ANY 1 keyword phải có (không phải ALL)
        "must_not_contain": must_not_contain or ["xin lỗi, không tìm thấy", "lỗi hệ thống"],
    }

def fmt_price(p):
    if not p: return None
    if p == 0: return "miễn phí"
    return f"{p:,.0f}"


# ══════════════════════════════════════════════════════════════════════════════
# L1 — FAQ (100 cases)
# ══════════════════════════════════════════════════════════════════════════════

# Giá vé — 25 cases
gia_ve_queries = [
    ("Giá vé vào cổng bao nhiêu?",          ["vé", "đ"]),
    ("Vé người lớn giá mấy?",               ["người lớn", "đ"]),
    ("Vé trẻ em bao nhiêu tiền?",           ["trẻ em", "đ"]),
    ("Phí vào cổng là bao nhiêu?",          ["vé", "đ"]),
    ("gia ve vao cong bao nhieu",            ["vé", "đ"]),
    ("ve vao cong het bao nhieu tien",       ["vé", "đ"]),
    ("Mua vé hết bao nhiêu?",               ["vé", "đ"]),
    ("Vào Suối Tiên tốn bao nhiêu?",        ["vé", "đ"]),
    ("Combo gia đình giá bao nhiêu?",        ["combo", "đ"]),
    ("Vé học sinh có không?",               ["học sinh", "vé"]),
    ("Có vé giảm giá không?",               ["vé", "giảm"]),
    ("Trẻ em mấy tuổi thì miễn phí?",       ["miễn phí", "trẻ em"]),
    ("Vé khu nước giá bao nhiêu?",          ["vé", "đ"]),
    ("Vé khu khô bao nhiêu tiền?",          ["vé", "đ"]),
    ("Có combo 2 khu không?",               ["combo", "vé"]),
    ("ticket price",                        ["ticket", "price"]),
    ("how much is the entrance fee",        ["ticket", "price"]),
    ("Giá vé có bao gồm tất cả trò không?", ["vé", "bao gồm"]),
    ("Vé online rẻ hơn vé tại cổng không?", ["vé", "online"]),
    ("Có vé tháng hoặc vé năm không?",      ["vé"]),
    ("Vé nhóm đoàn có giảm không?",         ["vé", "đoàn"]),
    ("Vé ưu đãi cho người cao tuổi không?", ["vé"]),
    ("Mua vé ở đâu?",                       ["vé", "mua"]),
    ("Đặt vé online ở đâu?",               ["vé", "online", "suoitien"]),
    ("book ve o dau",                        ["vé"]),
]
for q, mc in gia_ve_queries:
    cases.append(case(_id_next("L1"), "L1", "gia_ve", q, mc))

# Giờ mở cửa — 20 cases
gio_queries = [
    ("Mấy giờ mở cửa?",                    ["giờ"]),
    ("Mấy giờ đóng cửa?",                  ["giờ"]),
    ("may gio mo cua",                       ["giờ"]),
    ("may gio dong cua",                     ["giờ"]),
    ("Giờ hoạt động Suối Tiên?",            ["giờ"]),
    ("Cuối tuần mở cửa mấy giờ?",          ["giờ"]),
    ("Chủ nhật có mở cửa không?",           ["mở"]),
    ("Ngày lễ có mở cửa không?",            ["mở"]),
    ("gio mo cua suoi tien",                 ["giờ"]),
    ("open time",                            ["open", "time"]),
    ("what time does it open",               ["open", "time"]),
    ("Mở cửa từ mấy giờ đến mấy giờ?",    ["giờ"]),
    ("Buổi tối có mở không?",               ["giờ"]),
    ("Sáng sớm mấy giờ vào được?",         ["giờ"]),
    ("Đến lúc mấy giờ thì vào không được?", ["giờ"]),
    ("Hôm nay mở cửa không?",              ["mở"]),
    ("Thứ 2 có mở cửa không?",             ["mở"]),
    ("Giờ bán vé?",                         ["giờ"]),
    ("gio hoat dong",                        ["giờ"]),
    ("closing time",                         ["time", "close"]),
]
for q, mc in gio_queries:
    cases.append(case(_id_next("L1"), "L1", "gio_mo_cua", q, mc))

# Địa chỉ — 15 cases
dia_chi_queries = [
    ("Suối Tiên ở đâu?",                   ["Xa Lộ", "Thủ Đức"]),
    ("Địa chỉ Suối Tiên?",                 ["Xa Lộ", "120"]),
    ("Suối Tiên ở quận mấy?",              ["Thủ Đức"]),
    ("dia chi suoi tien",                   ["Xa Lộ"]),
    ("suoi tien o dau",                     ["Xa Lộ"]),
    ("Công viên nằm ở đâu?",               ["Xa Lộ"]),
    ("Suối Tiên cách trung tâm bao xa?",   ["Xa Lộ"]),
    ("Địa điểm Suối Tiên?",               ["Xa Lộ"]),
    ("Where is Suoi Tien?",                 ["Xa Lộ", "Ho Chi Minh"]),
    ("location of Suoi Tien park",          ["Xa Lộ"]),
    ("Suối Tiên ở TP.HCM không?",         ["Thủ Đức", "HCM"]),
    ("Cách quận 1 bao xa?",               ["Xa Lộ"]),
    ("Ở đường nào?",                       ["Xa Lộ"]),
    ("Số nhà bao nhiêu?",                  ["120"]),
    ("cho nao",                             ["Xa Lộ"]),
]
for q, mc in dia_chi_queries:
    cases.append(case(_id_next("L1"), "L1", "dia_chi", q, mc))

# Liên hệ — 15 cases
lien_he_queries = [
    ("Hotline Suối Tiên?",                 ["1900", "636"]),
    ("Số điện thoại liên hệ?",            ["1900"]),
    ("so dien thoai suoi tien",             ["1900"]),
    ("Email Suối Tiên?",                   ["suoitien", "@"]),
    ("Gọi cho Suối Tiên số nào?",         ["1900"]),
    ("hotline",                             ["1900"]),
    ("lien he",                             ["1900"]),
    ("Contact Suoi Tien?",                  ["1900"]),
    ("phone number",                        ["1900"]),
    ("Liên hệ đặt vé?",                   ["1900"]),
    ("Liên hệ teambuilding?",             ["1900"]),
    ("Website Suối Tiên?",                 ["suoitien"]),
    ("so dt suoi tien",                     ["1900"]),
    ("Fanpage Suối Tiên?",                 ["suoitien"]),
    ("Zalo Suối Tiên?",                    ["1900", "suoitien"]),
]
for q, mc in lien_he_queries:
    cases.append(case(_id_next("L1"), "L1", "lien_he", q, mc))

# Đường đi — 15 cases
duong_di_queries = [
    ("Đi metro đến Suối Tiên được không?", ["metro"]),
    ("Xe buýt nào đến Suối Tiên?",        ["xe buýt", "tuyến"]),
    ("xe buyt den suoi tien",               ["xe buýt"]),
    ("Từ quận 1 đi Suối Tiên bao lâu?",  ["Xa Lộ"]),
    ("Đi Grab đến Suối Tiên được không?", ["Xa Lộ"]),
    ("Bãi giữ xe ở đâu?",                ["xe", "bãi"]),
    ("gui xe o dau",                        ["xe"]),
    ("Có bãi đỗ xe ô tô không?",          ["xe"]),
    ("Phí giữ xe bao nhiêu?",             ["xe"]),
    ("Metro số mấy đến Suối Tiên?",       ["metro"]),
    ("duong di den suoi tien",              ["Xa Lộ"]),
    ("How to get to Suoi Tien?",            ["Xa Lộ", "metro"]),
    ("directions to Suoi Tien",             ["Xa Lộ"]),
    ("Cách đi từ sân bay Tân Sơn Nhất?",  ["Xa Lộ"]),
    ("Chạy xe máy đến Suối Tiên đường nào?", ["Xa Lộ"]),
]
for q, mc in duong_di_queries:
    cases.append(case(_id_next("L1"), "L1", "duong_di", q, mc))

# Đảm bảo đủ 100 L1
print(f"L1 so far: {len([c for c in cases if c['level']=='L1'])}")


# ══════════════════════════════════════════════════════════════════════════════
# L2 — Schema (200 cases)
# ══════════════════════════════════════════════════════════════════════════════

# Từ attractions data — 80 cases
attractions = DATA["attractions"]
tro_choi = [a for a in attractions if "tro_choi" in str(a.get("type","")).lower()
            or a.get("thrill_level") in ["manh","trung_binh","nhe","high","1","2","3"]]
tro_choi = list({a["name"]: a for a in tro_choi}.values())  # dedup

att_query_templates = [
    ("{name} là trò chơi gì?",              ["{name}"]),
    ("{name} ở khu nào?",                   ["{name}"]),
    ("{name} có cảm giác mạnh không?",       ["{name}"]),
    ("Trò {name} dành cho ai?",             ["{name}"]),
    ("Chơi {name} có phải trả thêm tiền không?", ["{name}"]),
]
for a in random.sample(tro_choi, min(16, len(tro_choi))):
    tmpl = random.choice(att_query_templates)
    q = tmpl[0].replace("{name}", a["name"])
    mc = [kw.replace("{name}", a["name"]) for kw in tmpl[1]]
    cases.append(case(_id_next("L2"), "L2", "tro_choi_specific", q, mc))

# General attraction queries — 30 cases
att_general = [
    ("Trò chơi cảm giác mạnh có gì?",      ["cảm giác mạnh"]),
    ("Khu vui chơi trẻ em có gì?",          ["trẻ em"]),
    ("Có trò chơi nào cho người già không?", ["trò chơi"]),
    ("Trò chơi nào không cần trả thêm tiền?", ["trò chơi"]),
    ("Khu nước có gì chơi?",               ["khu nước"]),
    ("Khu khô có gì chơi?",                ["khu"]),
    ("Infinity Slide là gì?",               ["Infinity Slide"]),
    ("Go Kart ở đâu?",                      ["Go Kart"]),
    ("Twin Race như thế nào?",              ["Twin Race"]),
    ("Xe Tăng ở khu nào?",                 ["Xe Tăng"]),
    ("Có trò chơi VR không?",              ["VR"]),
    ("Phim 12D là gì?",                    ["12D"]),
    ("Vương quốc cá sấu có gì?",           ["cá sấu"]),
    ("Khu văn hóa tâm linh có gì?",        ["văn hóa"]),
    ("Có bao nhiêu trò chơi cảm giác mạnh?", ["trò chơi"]),
    ("Trò chơi nào phù hợp cả gia đình?",  ["trò chơi"]),
    ("Co tro choi gi vui",                  ["trò chơi"]),
    ("tro choi manh nhat la gi",            ["trò chơi"]),
    ("Khu Mega Zone có gì?",               ["Mega Zone"]),
    ("tiNiWorld là gì?",                   ["tiNiWorld"]),
    ("Suối Tiên Farm có gì tham quan?",    ["Farm"]),
    ("Vườn nho ở đâu?",                   ["vườn nho"]),
    ("Có hái trái cây không?",             ["trái cây", "hái"]),
    ("Câu cá sấu được không?",             ["cá sấu"]),
    ("Đình thần ở đâu?",                   ["đình"]),
    ("Chùa trong Suối Tiên?",             ["chùa"]),
    ("Tượng Quan Thế Âm ở đâu?",          ["Quan Thế Âm"]),
    ("Đền Hùng Vương ở đâu?",             ["Hùng Vương"]),
    ("Có show diễn không?",               ["diễn", "biểu diễn"]),
    ("Có diễu hành không?",               ["diễu hành"]),
]
for q, mc in att_general:
    cases.append(case(_id_next("L2"), "L2", "tro_choi", q, mc))

# Từ restaurant data — 40 cases
restaurants = DATA["restaurant"]
rest_names = [r["name"] for r in restaurants]

rest_templates = [
    ("Nhà hàng {name} có gì ăn?",         ["{name}"]),
    ("{name} ở đâu trong công viên?",      ["{name}"]),
    ("{name} có đặt bàn trước không?",     ["{name}"]),
    ("Giá ăn ở {name} khoảng bao nhiêu?", ["{name}"]),
]
for r in random.sample(restaurants, min(10, len(restaurants))):
    tmpl = random.choice(rest_templates)
    q = tmpl[0].replace("{name}", r["name"])
    mc = [kw.replace("{name}", r["name"]) for kw in tmpl[1]]
    cases.append(case(_id_next("L2"), "L2", "nha_hang_specific", q, mc))

rest_general = [
    ("Có nhà hàng nào trong công viên không?", ["nhà hàng"]),
    ("Ăn trưa ở Suối Tiên ở đâu?",         ["nhà hàng", "ăn"]),
    ("Có buffet không?",                    ["nhà hàng"]),
    ("Nhà hàng nào ngon nhất?",            ["nhà hàng"]),
    ("Cung Đình Tửu có gì ăn?",            ["Cung Đình Tửu"]),
    ("Có nhà hàng hải sản không?",         ["nhà hàng"]),
    ("Ăn chay được không?",               ["nhà hàng"]),
    ("Giá ăn khoảng bao nhiêu?",          ["nhà hàng"]),
    ("Có quán ăn nhanh không?",           ["nhà hàng", "ăn"]),
    ("nha hang Phu Dong co gi",            ["Phù Đổng"]),
    ("Đặt bàn trước được không?",          ["nhà hàng", "đặt"]),
    ("Nhà hàng mở cửa đến mấy giờ?",      ["nhà hàng", "giờ"]),
    ("Có phục vụ tiệc cưới không?",        ["nhà hàng"]),
    ("Nhà hàng nổi có không?",            ["nhà hàng"]),
    ("Biển Tiên Đồng Ngọc Nữ có gì?",    ["Biển Tiên"]),
    ("nha hang nao vua tui",               ["nhà hàng"]),
    ("an uong o suoi tien",                ["nhà hàng"]),
    ("Có nước ép sung mỹ không?",         ["sung mỹ"]),
    ("Có thức ăn chay không?",            ["nhà hàng"]),
    ("Phố ẩm thực ở đâu?",               ["ẩm thực"]),
]
for q, mc in rest_general:
    cases.append(case(_id_next("L2"), "L2", "nha_hang", q, mc))

# Từ events data — 30 cases
events = DATA["events"]
event_names = [e["name"] for e in events if e.get("status") in ["upcoming","ongoing"]]

event_general = [
    ("Có sự kiện gì sắp tới không?",       ["sự kiện"]),
    ("Hiện tại có chương trình gì không?", ["sự kiện", "chương trình"]),
    ("Lễ hội hè có gì?",                  ["lễ hội"]),
    ("Có khuyến mãi vé không?",           ["khuyến mãi", "ưu đãi"]),
    ("Ưu đãi tháng này là gì?",           ["ưu đãi"]),
    ("Bốn Mùa Lễ Hội là gì?",            ["Bốn Mùa Lễ Hội"]),
    ("Friendship Festival là gì?",         ["Friendship Festival"]),
    ("Có sự kiện cuối tuần không?",        ["sự kiện"]),
    ("Lễ hội mùa hè 2025?",              ["lễ hội"]),
    ("Có show âm nhạc không?",            ["sự kiện", "show"]),
    ("su kien sap toi",                    ["sự kiện"]),
    ("co khuyen mai gi ko",                ["khuyến mãi"]),
    ("Trung Thu Suối Tiên có gì?",        ["Trung Thu"]),
    ("Tết Suối Tiên có gì?",             ["lễ hội"]),
    ("Hè này Suối Tiên có gì đặc biệt?",  ["sự kiện"]),
]
for q, mc in event_general:
    cases.append(case(_id_next("L2"), "L2", "su_kien", q, mc))

# Từ teambuilding data — 30 cases
tb_data = DATA["teambuilding"]

tb_queries = [
    ("Teambuilding 50 người giá bao nhiêu?",     ["người", "đ"]),
    ("Có gói cắm trại không?",                   ["cắm trại"]),
    ("Tổ chức hội nghị được không?",             ["hội nghị"]),
    ("Gói team building 1 ngày?",                ["team building"]),
    ("team building 100 nguoi co goi nao",        ["người"]),
    ("Cắm trại 2 ngày 1 đêm giá bao nhiêu?",    ["cắm trại", "đ"]),
    ("Có tổ chức tiệc cưới không?",             ["tiệc cưới"]),
    ("Sảnh hội nghị sức chứa bao nhiêu?",        ["hội nghị", "người"]),
    ("Teambuilding cho trường học?",             ["team building"]),
    ("Gala dinner ở Suối Tiên?",               ["gala"]),
    ("Dịch vụ âm thanh ánh sáng có không?",    ["âm thanh"]),
    ("Thuê phòng hội thảo?",                   ["hội thảo"]),
    ("Diamond Palace sức chứa bao nhiêu?",      ["Diamond"]),
    ("Có tổ chức sinh nhật công ty không?",     ["team building"]),
    ("Liên hệ đặt teambuilding?",              ["1900", "teambuilding"]),
]
for q, mc in tb_queries:
    cases.append(case(_id_next("L2"), "L2", "teambuilding", q, mc))

# Tickets specific — 20 cases
ticket_queries = [
    ("Vé combo Kỳ Quan gồm những gì?",          ["combo", "vé"]),
    ("Vé siêu trải nghiệm bao gồm gì?",         ["vé"]),
    ("Vé học sinh giỏi được giảm bao nhiêu?",   ["học sinh"]),
    ("Vé miễn phí trẻ em ngày nào?",           ["miễn phí", "trẻ em"]),
    ("Vé vào khu nước riêng có không?",         ["vé", "khu nước"]),
    ("Vé tháng 6 có ưu đãi không?",            ["vé"]),
    ("Combo Suối Tiên + Bình Quới?",           ["combo"]),
    ("Vé taxi nội khu là gì?",                 ["taxi", "vé"]),
    ("Vé có hiệu lực bao lâu?",               ["vé"]),
    ("Vé mua online có được hoàn không?",      ["vé"]),
]
for q, mc in ticket_queries:
    cases.append(case(_id_next("L2"), "L2", "gia_ve_specific", q, mc))

print(f"L2 so far: {len([c for c in cases if c['level']=='L2'])}")


# ══════════════════════════════════════════════════════════════════════════════
# L3 — Complex (80 cases)
# ══════════════════════════════════════════════════════════════════════════════

complex_queries = [
    # Multi-intent
    ("Giá vé bao nhiêu và mấy giờ mở cửa?",                ["vé", "giờ"]),
    ("2 người lớn 1 trẻ em tốn bao nhiêu và đi xe buýt được không?", ["người lớn", "xe buýt"]),
    ("Có trò chơi gì và nhà hàng nào ngon?",               ["trò chơi", "nhà hàng"]),
    ("Teambuilding 30 người và cần đặt trước không?",       ["người", "đặt"]),
    ("Giờ mở cửa và bãi giữ xe ở đâu?",                   ["giờ", "xe"]),
    ("Vé combo có gì và giá bao nhiêu?",                   ["combo", "đ"]),
    ("Có sự kiện gì và thời tiết thế nào?",               ["sự kiện"]),
    ("Ăn ở đâu và có trò chơi trẻ em không?",            ["nhà hàng", "trẻ em"]),
    ("Đường đi và giá vé?",                               ["Xa Lộ", "vé"]),
    ("Có khuyến mãi và mấy giờ bán vé?",                 ["khuyến mãi", "vé"]),

    # So sánh
    ("Go Kart với Tàu Lượn cái nào mạnh hơn?",            ["Go Kart", "Tàu Lượn"]),
    ("Vé người lớn và vé học sinh khác nhau thế nào?",    ["người lớn", "học sinh"]),
    ("Khu khô và khu nước có gì khác nhau?",              ["khu"]),
    ("Infinity Slide và Twin Race cái nào hơn?",           ["Infinity Slide", "Twin Race"]),
    ("Cắm trại 1 ngày và 2 ngày giá khác nhau thế nào?", ["cắm trại"]),
    ("Mua vé online và tại cổng khác nhau gì?",          ["vé", "online"]),
    ("Khu farm và khu văn hóa tâm linh khác nhau gì?",   ["farm", "văn hóa"]),
    ("Gói TB 20 người và 50 người giá khác nhau?",       ["người"]),

    # Tổng hợp
    ("Có bao nhiêu khu vui chơi trong công viên?",        ["khu"]),
    ("Liệt kê tất cả trò chơi cảm giác mạnh",            ["Go Kart", "Infinity Slide"]),
    ("Có những loại vé nào?",                             ["vé", "người lớn", "trẻ em"]),
    ("Tất cả nhà hàng trong Suối Tiên?",                 ["nhà hàng"]),
    ("Có bao nhiêu gói teambuilding?",                    ["gói"]),
    ("Liệt kê các sự kiện đang diễn ra",                 ["sự kiện"]),
    ("Tất cả khu tham quan?",                            ["khu"]),
    ("Có bao nhiêu nhà hàng?",                           ["nhà hàng"]),

    # Lịch trình / gợi ý
    ("Gia đình 2 người lớn 2 trẻ em nên đi khu nào?",   ["khu"]),
    ("Đi Suối Tiên 1 ngày thì đủ không?",               []),
    ("Trẻ 3 tuổi cao 95cm chơi được gì?",               ["trẻ em"]),
    ("Nên đi Suối Tiên vào ngày nào?",                  []),
    ("Buổi sáng nên tham quan khu nào?",                ["khu"]),
    ("Lịch trình 1 ngày lý tưởng tại Suối Tiên?",      ["khu"]),
    ("Trẻ 10 tuổi thích gì ở Suối Tiên?",             ["trẻ em", "trò chơi"]),
    ("Người cao tuổi nên tham quan khu nào?",           ["khu"]),

    # Câu hỏi khó / liên kết
    ("Mua vé xong thì nên đi đâu trước?",              ["khu"]),
    ("Sau khi chơi Go Kart thì gần đó có gì?",         []),
    ("Ăn trưa xong nên làm gì?",                       []),
    ("Nếu trời mưa thì chơi ở đâu?",                  ["khu"]),
    ("Buổi tối còn gì chơi không?",                   []),
    ("Đi xe máy có vào được không?",                   ["xe"]),

    # Điều kiện / filter
    ("Trò chơi nào không cần trả thêm tiền?",          ["trò chơi"]),
    ("Trò chơi nào phù hợp cả gia đình?",             ["trò chơi"]),
    ("Khu nào phù hợp người sợ độ cao?",              ["khu"]),
    ("Có trò chơi cho người khuyết tật không?",        []),
    ("Trò chơi nào mở cả ngày?",                      ["trò chơi"]),
    ("Nhà hàng nào có chỗ ngồi ngoài trời?",         ["nhà hàng"]),
    ("Gói teambuilding nào phù hợp công ty 200 người?", ["người"]),
    ("Vé nào rẻ nhất?",                               ["vé", "đ"]),

    # Câu hỏi vùng miền
    ("Từ Đà Nẵng vào Suối Tiên đi như thế nào?",      ["Suối Tiên"]),
    ("Từ Hà Nội đến Suối Tiên?",                      ["Suối Tiên"]),
    ("Từ sân bay đến Suối Tiên bao lâu?",             ["Xa Lộ"]),
    ("Từ Bình Dương đi Suối Tiên?",                   ["Xa Lộ"]),
    ("Từ quận 7 đến Suối Tiên?",                     ["Xa Lộ"]),

    # Chính sách
    ("Chính sách hoàn vé như thế nào?",               ["vé"]),
    ("Có được mang thức ăn vào không?",               []),
    ("Có được mang pet vào không?",                   []),
    ("Quy định ăn mặc vào công viên?",               []),
    ("Vé mua rồi có đổi không?",                     ["vé"]),

    # Thời tiết
    ("Thời tiết hôm nay thế nào?",                    ["thời tiết"]),
    ("Trời có mưa không?",                            []),
    ("Có nên mang áo mưa không?",                    []),
    ("Nên đi ngày nào đẹp trời?",                    []),

    # Bot identity
    ("Bạn là ai?",                                    ["Tiên", "em"]),
    ("Tên bạn là gì?",                               ["Tiên"]),
    ("Bot này làm được gì?",                          ["em"]),

    # Tiếng Anh / đa ngôn ngữ
    ("Can I bring food inside?",                       []),
    ("Is there a kids zone?",                          ["kids", "trẻ em"]),
    ("How many restaurants are there?",               ["restaurant"]),
    ("What rides are available?",                     ["ride", "trò chơi"]),
    ("Is teambuilding available?",                    ["team"]),
    ("Do you have combo tickets?",                    ["combo", "ticket"]),

    # OOS nhưng cần graceful
    ("Suối Tiên có nuôi gấu không?",                  []),
    ("Có khách sạn gần Suối Tiên không?",            []),
    ("Vé máy bay đi Suối Tiên?",                     []),
]

for q, mc in complex_queries:
    level = "L3"
    cat = "complex"
    if "vs" in q.lower() or "khác nhau" in q or "hơn" in q:
        cat = "so_sanh"
    elif "tất cả" in q or "bao nhiêu" in q or "liệt kê" in q:
        cat = "tong_hop"
    elif "lịch trình" in q or "nên đi" in q or "trước" in q:
        cat = "lich_trinh"
    cases.append(case(_id_next("L3"), level, cat, q, mc))

print(f"L3 so far: {len([c for c in cases if c['level']=='L3'])}")


# ══════════════════════════════════════════════════════════════════════════════
# L4 — Edge cases (80 cases typo + 40 multilang)
# ══════════════════════════════════════════════════════════════════════════════

typo_no_diacritic = [
    ("gia ve vao cong bao nhieu tien",      ["vé", "đ"]),
    ("mk mun bit gia ve",                   ["vé"]),
    ("suoi tien o dau z",                   ["Xa Lộ"]),
    ("co tro choi j k",                     ["trò chơi"]),
    ("nha hang ngon ko",                    ["nhà hàng"]),
    ("may gio mo cua vay",                  ["giờ"]),
    ("xe buyt so may den suoi tien",        ["xe buýt"]),
    ("co khuyen mai ve ko",                 ["khuyến mãi", "vé"]),
    ("dich vu team building",               ["team building"]),
    ("co su kien gi k",                     ["sự kiện"]),
    ("gui xe o dau",                        ["xe"]),
    ("duong di den suoi tien",              ["Xa Lộ"]),
    ("dat ve o dau",                        ["vé"]),
    ("ve tre em bao nhieu",                 ["trẻ em", "đ"]),
    ("an uong o suoi tien",                 ["nhà hàng"]),
    ("tro choi cam giac manh",              ["cảm giác mạnh"]),
    ("gio dong cua la may gio",             ["giờ"]),
    ("so dt suoi tien la bao nhieu",        ["1900"]),
    ("co nhieu khu choi ko",               ["khu"]),
    ("vao cong mat bao nhiu",              ["vé", "đ"]),
    ("go kart o khu nao vay",              ["Go Kart"]),
    ("co buffet k",                        ["nhà hàng"]),
    ("cam trai qua dem duoc ko",           ["cắm trại"]),
    ("tren web mua ve duoc k",             ["vé", "online"]),
    ("may gio ban ve",                     ["giờ"]),
    ("thoi tiet hom nay",                  ["thời tiết"]),
    ("co giam gia cho hoc sinh k",         ["học sinh"]),
    ("co cho oto khong",                   ["xe"]),
    ("farm o dau",                         ["farm"]),
    ("van hoa tam linh khu nao",           ["văn hóa"]),
    # Thêm typo nặng hơn
    ("gia veee bao nhiu",                  ["vé"]),
    ("suoii tien o dauuu",                 ["Xa Lộ"]),
    ("co tro chioi gi vii",               ["trò chơi"]),
    ("nha haang nao ngon",                ["nhà hàng"]),
    ("may giooo mo cua",                  ["giờ"]),
    ("ve nguoi lon gia la",               ["người lớn", "đ"]),
    ("combo gia dinh",                    ["combo"]),
    ("taxi noi khu la gi",               ["taxi"]),
    ("khu nuoc co gi",                   ["khu nước"]),
    ("di metro duoc k",                  ["metro"]),
    # Telex / VNI input
    ("gia ve vao coong",                 ["vé"]),
    ("may gio` mo? cua?",               ["giờ"]),
    ("dia chi? suoi tien",               ["Xa Lộ"]),
    ("so dt lien he",                    ["1900"]),
    ("go kart la gi",                    ["Go Kart"]),
    # Rất ngắn
    ("vé",                              ["vé"]),
    ("giờ",                             ["giờ"]),
    ("địa chỉ",                         ["Xa Lộ"]),
    ("hotline",                         ["1900"]),
    ("trò chơi",                        ["trò chơi"]),
    ("nhà hàng",                        ["nhà hàng"]),
    ("teambuilding",                    ["team building"]),
    ("sự kiện",                         ["sự kiện"]),
    ("farm",                            ["farm"]),
    ("combo",                           ["combo"]),
    ("parking",                         ["xe"]),
    ("metro",                           ["metro"]),
    ("bus",                             ["xe buýt"]),
    ("map",                             []),
    ("wifi",                            []),
    ("toilet",                          []),
    ("atm",                             []),
    ("voucher",                         ["vé", "khuyến mãi"]),
    ("refund",                          ["vé"]),
    ("discount",                        ["giảm", "ưu đãi"]),
    ("family package",                  ["combo"]),
    ("kids",                            ["trẻ em"]),
    ("senior",                          ["vé"]),
    ("student",                         ["học sinh"]),
    ("group",                           ["đoàn", "vé"]),
    ("overnight",                       ["cắm trại"]),
    ("wedding",                         ["tiệc cưới"]),
    ("conference",                      ["hội nghị"]),
    ("restaurant",                      ["nhà hàng"]),
    ("food",                            ["nhà hàng", "ăn"]),
    ("ride",                            ["trò chơi"]),
    ("show",                            ["sự kiện", "biểu diễn"]),
    ("ticket",                          ["vé"]),
    ("open",                            ["giờ"]),
    ("close",                           ["giờ"]),
    ("price",                           ["đ"]),
    ("address",                         ["Xa Lộ"]),
]

for q, mc in typo_no_diacritic[:80]:
    cases.append(case(_id_next("L4"), "L4", "typo_edge", q, mc))

# Multilang — 40 cases
multilang_queries = [
    ("How much is the entrance ticket?",   ["ticket", "price"]),
    ("What time does the park open?",      ["open", "time"]),
    ("Is there a kids zone?",              ["trẻ em"]),
    ("How to get there?",                  ["Xa Lộ"]),
    ("Any promotions?",                    ["ưu đãi"]),
    ("What rides are available?",          ["trò chơi"]),
    ("Is there a restaurant?",             ["nhà hàng"]),
    ("Can I book online?",                 ["vé", "online"]),
    ("Is teambuilding available?",         ["team"]),
    ("What is the address?",               ["Xa Lộ"]),
    ("门票多少钱？",                          ["票", "vé", "ticket"]),
    ("几点开门？",                           ["点", "giờ", "time"]),
    ("有什么好玩的？",                        ["游", "trò chơi", "ride"]),
    ("怎么去水仙公园？",                      ["路", "Xa Lộ", "xa lo"]),
    ("有餐厅吗？",                           ["餐", "nhà hàng", "restaurant"]),
    ("입장료가 얼마예요?",                   ["티켓", "vé", "ticket"]),
    ("몇 시에 문을 열어요?",                 ["시", "giờ", "time"]),
    ("어떻게 가요?",                        ["Xa Lộ"]),
    ("놀이 기구가 있어요?",                  ["놀이", "trò chơi"]),
    ("식당이 있어요?",                      ["식당", "nhà hàng", "restaurant"]),
    ("入場料はいくらですか？",                 ["チケット", "vé", "ticket"]),
    ("何時に開きますか？",                    ["時", "giờ", "time"]),
    ("どうやって行きますか？",                 ["Xa Lộ"]),
    ("アトラクションは何がありますか？",        ["アトラクション", "trò chơi"]),
    ("レストランはありますか？",               ["レストラン", "nhà hàng", "restaurant"]),
    # Mixed
    ("ticket giá bao nhiêu",              ["vé", "đ"]),
    ("open mấy giờ",                     ["giờ"]),
    ("combo price",                      ["combo"]),
    ("family ticket",                    ["vé"]),
    ("kids playground",                  ["trẻ em"]),
    ("parking lot",                      ["xe"]),
    ("food court",                       ["nhà hàng"]),
    ("water park",                       ["khu nước"]),
    ("thrill rides",                     ["cảm giác mạnh"]),
    ("wedding venue",                    ["tiệc cưới"]),
    ("team building package",            ["team building"]),
    ("discount voucher",                 ["ưu đãi"]),
    ("group booking",                    ["đoàn", "vé"]),
    ("overnight camping",                ["cắm trại"]),
    ("cultural tour",                    ["văn hóa"]),
]

for q, mc in multilang_queries[:40]:
    cases.append(case(_id_next("L4"), "L4", "multilang", q, mc))


# ══════════════════════════════════════════════════════════════════════════════
# Bổ sung đủ 500 cases
# ══════════════════════════════════════════════════════════════════════════════

extra_l1 = [
    # Giá vé thêm
    ("Có vé VIP không?",                           ["vé"]),
    ("Vé tặng kèm gì không?",                     ["vé"]),
    ("Vé nhóm từ bao nhiêu người?",               ["vé", "người"]),
    ("Có vé dành cho em bé không?",               ["vé", "trẻ em"]),
    ("Vé sử dụng trong bao lâu?",                 ["vé"]),
    ("Mua vé trực tiếp tại cổng được không?",     ["vé"]),
    ("Có app mua vé không?",                      ["vé", "app"]),
    ("Vé điện tử hay vé giấy?",                  ["vé"]),
    ("Có thẻ thành viên không?",                  ["vé"]),
    ("Giá vé ngày thường và cuối tuần khác không?", ["vé"]),
    # Giờ thêm
    ("Last entry mấy giờ?",                       ["giờ"]),
    ("Mấy giờ bán vé cuối?",                     ["giờ"]),
    ("Có mở cửa 365 ngày không?",                ["mở"]),
    ("Tết có mở cửa không?",                     ["mở"]),
    ("Giờ cao điểm là lúc nào?",                 ["giờ"]),
]

extra_l2 = [
    # Attractions thêm
    ("Có trò chơi nào cho người mang thai không?", ["trò chơi"]),
    ("Trò chơi nào có giới hạn cân nặng?",        ["trò chơi"]),
    ("Xe tăng chạy ở đâu?",                       ["Xe Tăng"]),
    ("Đĩa xoáy thiên hà là gì?",                 ["Đĩa xoáy"]),
    ("Ngôi nhà ma có đáng sợ không?",            ["Ngôi nhà ma"]),
    ("Phim 9D khác phim 12D như thế nào?",        ["phim"]),
    ("Kỳ Lân Cung là gì?",                       ["Kỳ Lân"]),
    ("Có khu nước trượt không?",                 ["khu nước"]),
    ("EDM Ocean là gì?",                          ["EDM"]),
    ("Đu dây qua hồ có nguy hiểm không?",        ["đu dây"]),
    # TB thêm
    ("Gói 1 ngày teambuilding bao nhiêu tiền?",  ["đ", "team building"]),
    ("Có cho thuê địa điểm tổ chức sự kiện không?", ["sự kiện"]),
    ("Sức chứa tối đa Diamond Palace?",          ["Diamond"]),
    ("Có phục vụ tiệc tất niên không?",          ["tiệc"]),
    ("Liên hệ bộ phận sự kiện?",               ["1900"]),
    # Events thêm
    ("Có sự kiện nào cho trẻ em không?",         ["sự kiện", "trẻ em"]),
    ("Lịch sự kiện tháng 7?",                   ["sự kiện"]),
    ("Có ưu đãi sinh nhật không?",              ["ưu đãi"]),
    ("Chương trình nào đang diễn ra?",           ["sự kiện"]),
    ("Có sự kiện âm nhạc không?",              ["sự kiện"]),
    # Restaurant thêm  
    ("Cung Đình Tửu chuyên món gì?",            ["Cung Đình Tửu"]),
    ("Nhà hàng Tiên Ngư có gì?",               ["Tiên Ngư"]),
    ("Phố ẩm thực có món gì đặc trưng?",       ["ẩm thực"]),
    ("Có quán cà phê trong công viên không?",  ["nhà hàng"]),
    ("Có bán đồ lưu niệm không?",             ["nhà hàng"]),
]

extra_l3 = [
    ("Đi với nhóm bạn 10 người nên làm gì?",    ["khu", "trò chơi"]),
    ("Học sinh đi dã ngoại thì có gói nào?",    ["team building", "vé"]),
    ("Cặp đôi nên đi khu nào?",               ["khu"]),
    ("Người sợ nước có gì chơi?",             ["khu"]),
    ("Đi Suối Tiên buổi sáng hay chiều?",      []),
    ("Có cần đặt vé trước không?",            ["vé"]),
    ("Vào cổng rồi có thể ra ngoài ăn được không?", ["vé"]),
    ("Đi một mình có vui không?",             []),
    ("Nên mặc gì khi đi Suối Tiên?",         []),
    ("Mang theo tiền mặt hay thẻ?",           []),
    ("Có wifi trong công viên không?",        []),
    ("Có cho thuê áo phao không?",           []),
    ("Có dịch vụ chụp ảnh không?",          []),
    ("Có xe điện trong công viên không?",    ["taxi"]),
    ("Mất đồ thì liên hệ ai?",              ["1900"]),
    ("Có phòng thay đồ không?",             []),
    ("Có tủ khóa để đồ không?",            []),
    ("Trẻ em bao nhiêu tuổi chơi được Go Kart?", ["Go Kart"]),
    ("Người cao bao nhiêu mới được chơi Tàu Lượn?", ["Tàu Lượn"]),
    ("Có hướng dẫn viên tiếng Anh không?",  []),
    ("Bản đồ công viên ở đâu?",            []),
    ("Có ứng dụng điện thoại không?",       []),
    ("Bao lâu thì tham quan hết?",          []),
    ("Nên bắt đầu từ khu nào?",            ["khu"]),
    ("Khu nào đông nhất?",                 ["khu"]),
    ("Trò nào cần xếp hàng lâu nhất?",    ["trò chơi"]),
]

extra_l4 = [
    ("ve may gio choi duoc",              ["giờ"]),
    ("co cho thue ao phao k",            []),
    ("wifi free ko",                     []),
    ("locker co k",                      []),
    ("dich vu chup anh",                 []),
    ("map cua cong vien",                []),
    ("huong dan vien tieng anh",         []),
    ("cho thue xe day tre em",           []),
    ("nha ve sinh o dau",               []),
    ("cay ATM o dau",                   []),
    ("有寄存柜吗？",                       []),
    ("有地图吗？",                          []),
    ("有英文导游吗？",                       []),
    ("화장실이 어디예요?",                  []),
    ("짐을 맡길 수 있어요?",               []),
    ("コインロッカーはありますか？",          []),
    ("地図はありますか？",                   []),
    ("Is there free wifi?",              []),
    ("Where is the toilet?",            []),
    ("Can I rent a stroller?",          []),
    ("Is there an ATM?",               []),
    ("Do you have a map?",             []),
    ("Any English speaking guide?",     []),
    ("Can I re-enter?",                ["vé"]),
    ("Is photography allowed?",        []),
]

for q, mc in extra_l1:
    cases.append(case(_id_next("L1"), "L1", "gia_ve", q, mc))
for q, mc in extra_l2:
    cases.append(case(_id_next("L2"), "L2", "schema_extra", q, mc))
for q, mc in extra_l3:
    cases.append(case(_id_next("L3"), "L3", "complex_extra", q, mc))
for q, mc in extra_l4:
    cases.append(case(_id_next("L4"), "L4", "edge_extra", q, mc))


# Fill đủ 500
fill_cases = [
    ("Có nhà vệ sinh trong công viên không?",     [], "L4", "edge_extra"),
    ("Trẻ sơ sinh vào được không?",              ["trẻ em"], "L2", "schema_extra"),
    ("Có xe lăn cho người khuyết tật không?",    [], "L2", "schema_extra"),
    ("Suối Tiên có bao nhiêu hecta?",           [], "L3", "complex_extra"),
    ("Lịch sử Suối Tiên?",                      ["Suối Tiên"], "L3", "complex_extra"),
    ("Ai là chủ Suối Tiên?",                    [], "L3", "complex_extra"),
    ("Suối Tiên thành lập năm nào?",            [], "L3", "complex_extra"),
    ("Co cho thue xe dap khong",                [], "L4", "edge_extra"),
    ("ban do cong vien o dau",                  [], "L4", "edge_extra"),
]
for q, mc, lvl, cat in fill_cases:
    cases.append(case(_id_next(lvl), lvl, cat, q, mc))
# ── Final stats & save ─────────────────────────────────────────────────────────
from collections import Counter
level_dist = Counter(c["level"] for c in cases)
cat_dist   = Counter(c["category"] for c in cases)

print(f"\n{'='*50}")
print(f"TOTAL CASES: {len(cases)}")
print(f"Level distribution: {dict(level_dist)}")
print(f"\nCategory distribution:")
for cat, cnt in sorted(cat_dist.items(), key=lambda x: -x[1]):
    print(f"  {cat:30s}: {cnt}")

# Save
OUT_PATH = Path(os.environ.get("EVAL_OUT", str(BASE / "eval" / "eval_500.json")))
OUT_PATH.parent.mkdir(exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(cases, f, ensure_ascii=False, indent=2)
print(f"\nSaved → {OUT_PATH}")
