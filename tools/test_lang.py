import sys
sys.path.insert(0, r'D:\VAN VIBE CODE\botsuoitien\core')
from language_detector import detect_lang
tests = ['How much is the entrance ticket?', 'What time does the park open?', '门票多少钱？', '几点开门？']
for q in tests:
    print(f'{detect_lang(q):5s} ← {q}')
