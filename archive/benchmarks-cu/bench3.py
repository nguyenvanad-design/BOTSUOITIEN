import time, os, sys
sys.path.insert(0, r'D:\VAN VIBE CODE\botsuoitien\core')
os.environ['SUOITIEN_DATA'] = r'D:\VAN VIBE CODE\botsuoitien\core\data\suoitien_data_v2.json'

# Test 1: FAQ engine có match không
from faq_engine import faq_match
tests = ['may gio dong cua', 'mấy giờ đóng cửa', 'gio mo cua', 'dia chi o dau', 'gia ve']
for q in tests:
    r = faq_match(q)
    print(f'FAQ {"HIT" if r else "MISS"}: {q}')

print()

# Test 2: vector_search model có bị reload không
from vector_search import _model, _index
print(f'Model cached: {_model is not None}')
print(f'Index cached: {_index is not None}')
