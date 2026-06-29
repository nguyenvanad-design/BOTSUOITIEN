# Archive — file cũ, KHÔNG được code sử dụng

Dữ liệu bot đang dùng nằm ở **`core/data/`** (nguồn duy nhất, auto_updater tự cập nhật):
- `core/data/suoitien_data_v2.json` — structured data (env `SUOITIEN_DATA`)
- `core/data/suoitien_clean_v4.json` — text chunks cho BM25/vector (env `SUOITIEN_CLEAN`)

## Nội dung archive

| File | Là gì |
|---|---|
| `data-pipeline-2026-06-01/suoitien_new.json` | Crawl thô 80 docs (bước 1) |
| `data-pipeline-2026-06-01/suoitien_merged.json` | Gộp 456 docs (bước 2) — **dữ liệu crawl gốc, cần nếu rebuild pipeline** |
| `data-pipeline-2026-06-01/extract_progress.json` | Tiến độ extract LLM (bước 3) |
| `data-pipeline-2026-06-01/suoitien_data_v1.json` | Structured data bản 1 (chưa dedupe) |
| `data-pipeline-2026-06-01/suoitien_data_v2.json` | Structured data bản 2 ngày 01/06 — đã LỖI THỜI so với core/data |
| `data-pipeline-2026-06-01/suoitien_clean_v4.json` | Chunks bản 01/06 — đã LỖI THỜI so với core/data |
| `suoitien_schema_v1.json` | Định nghĩa schema lúc build pipeline (tài liệu tham khảo) |
| `eval_results.json` | Kết quả eval 65 câu ngày 02/06 (bị nhiễm bug thiếu API key — đừng tin số) |

Kết quả eval hiện hành nằm ở `eval/eval_results_500_grok.json` (12/06, 89.2%).

## Bổ sung 12/06 (đợt dọn toàn hệ thống)

| Thư mục/File | Là gì |
|---|---|
| `benchmarks-cu/bench*.py` | 3 bản benchmark cũ trong core — `tools/bench_breakdown.py` đã thay thế |
| `scripts-mot-lan/` | Script debug/verify dùng 1 lần đã xong việc (debug cache 10-11/06, fix teambuilding, update giờ mở cửa...) |
| `eval_results_500.json` | Kết quả eval 500 câu ngày 02/06 — bị nhiễm bug thiếu API key (76.2% KHÔNG phản ánh thực lực) |
