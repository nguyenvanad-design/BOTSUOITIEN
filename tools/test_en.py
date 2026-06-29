import sys
sys.path.insert(0, r'D:\VAN VIBE CODE\botsuoitien\core')
from chat_pipeline import chat
r = chat('How much is the entrance ticket?')
print('lang:', r['lang'])
print('source:', r['source'])
print('answer:', r['answer'][:200])
