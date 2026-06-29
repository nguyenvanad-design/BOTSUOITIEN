"""
scan_deps.py — Phân tích dependency graph toàn project.
Chạy từ thư mục gốc (chỗ có main.py):
    python scan_deps.py
"""
import ast
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")
PY_FILES = sorted(ROOT.rglob("*.py"))
PROJECT_MODS = {f.stem: f for f in PY_FILES}

def get_imports(filepath):
    src = filepath.read_text(encoding="utf-8", errors="ignore")
    found = set()
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod in PROJECT_MODS:
                        found.add(mod)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod in PROJECT_MODS:
                        found.add(mod)
    except SyntaxError:
        pass
    return found

deps        = {f.stem: get_imports(f) for f in PY_FILES}
imported_by = defaultdict(set)
for mod, uses in deps.items():
    for used in uses:
        imported_by[used].add(mod)

# Script chạy trực tiếp bằng `python` — không bị import bởi ai
KNOWN_ENTRY = {
    # Server & setup
    "main", "build_faiss",
    # Benchmark
    "bench", "bench2", "bench3",
    # Eval suite
    "eval_harness", "gen_eval_500",
    # Test suites
    "test_regression", "test_en", "test_lang",
    # Dev tools
    "scan_deps",
}

# FastAPI router: dùng include_router() chứ không import trực tiếp
# → scanner không thấy, nhưng đây là core API — không bao giờ xóa
KNOWN_API = {"chat", "webhook", "__init__"}

entry, orphan, used = [], [], []
for mod in sorted(PROJECT_MODS):
    users = imported_by[mod]
    path  = PROJECT_MODS[mod]
    if not users:
        is_entry = (
            mod in KNOWN_ENTRY
            or mod in KNOWN_API
            or "bench" in mod
            or mod.startswith("test_")
            or mod.startswith("build_")
            or mod.startswith("gen_")
            or mod.startswith("eval_")
        )
        if is_entry:
            entry.append((mod, path))
        else:
            orphan.append((mod, path))
    else:
        used.append((mod, path, users))

W = 62
print("=" * W)
print("  DEPENDENCY ANALYSIS — SUOI TIEN BOT")
print("=" * W)

print("\n🚀 ENTRY POINTS (chay truc tiep bang python ...):")
for m, p in entry:
    print(f"   {p}")

print()
if orphan:
    print("🗑️  CO THE XOA (khong ai import, khong phai entry point):")
    for m, p in orphan:
        print(f"   {p}   <-- ORPHAN")
else:
    print("✅ Khong co file orphan!")

print("\n✅ DANG DUNG (duoc import boi it nhat 1 module):")
for m, p, users in used:
    label = str(p)
    print(f"   {label:50s} <- {', '.join(sorted(users))}")

print()
print("=" * W)
print(f"  Tong: {len(entry)} entry | {len(orphan)} orphan | {len(used)} dang dung")
print("=" * W)

if orphan:
    print("\nXoa tat ca ORPHAN (PowerShell):")
    for m, p in orphan:
        print(f"   Remove-Item \"{p}\"")
