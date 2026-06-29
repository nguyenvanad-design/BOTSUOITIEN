import time, os, sys
sys.path.insert(0, r'D:\VAN VIBE CODE\botsuoitien\core')
os.environ['SUOITIEN_DATA'] = r'D:\VAN VIBE CODE\botsuoitien\core\data\suoitien_data_v2.json'

# Lần 1 - cold
from chat_pipeline import chat
t0 = time.perf_counter()
r = chat('gia ve vao cong bao nhieu')
print(f'Cold run: {(time.perf_counter()-t0)*1000:.0f}ms | source={r["source"]}')

# Lần 2 - warm
t1 = time.perf_counter()
r = chat('gia ve vao cong bao nhieu')
print(f'Warm run: {(time.perf_counter()-t1)*1000:.0f}ms')

# Lần 3 - câu khác
t2 = time.perf_counter()
r = chat('may gio dong cua')
print(f'FAQ run:  {(time.perf_counter()-t2)*1000:.0f}ms | source={r["source"]}')
