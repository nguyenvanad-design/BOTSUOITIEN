# BÁO GIÁ DỰ ÁN CHATBOT AI — CÔNG VIÊN VĂN HÓA DU LỊCH SUỐI TIÊN

**Bên cung cấp:** ______________________  
**Kính gửi:** Công ty CP Du lịch Văn hóa Suối Tiên  
**Ngày:** ____ / ____ / ______  
**Số báo giá:** BG-SUOITIEN-________  
**Hiệu lực báo giá:** 30 ngày

---

## 1. GIỚI THIỆU

Xây dựng trợ lý ảo AI ("bot Tiên") tư vấn du khách 24/7 cho Suối Tiên: giá vé, trò chơi, nhà hàng, sự kiện, teambuilding, chỉ đường, thời tiết — trên nhiều kênh (Website, Zalo OA, Messenger). Bot ứng dụng mô hình ngôn ngữ lớn (LLM) kết hợp truy xuất dữ liệu nội bộ (RAG), có khả năng **tự học**, **nhớ hội thoại** và **kiểm soát an toàn**.

---

## 2. GÓI DỊCH VỤ

| Hạng mục | 🥉 CƠ BẢN | 🥈 TIÊU CHUẨN | 🥇 CAO CẤP |
|---|:---:|:---:|:---:|
| Chat engine AI (hiểu ngôn ngữ tự nhiên) | ✅ | ✅ | ✅ |
| Cơ sở tri thức (vé, trò chơi, NH, sự kiện…) | ✅ | ✅ | ✅ |
| FAQ trả lời tức thì (<0.1s) | ✅ | ✅ | ✅ |
| Website Chat UI | ✅ | ✅ | ✅ |
| Hybrid RAG (tìm kiếm ngữ nghĩa BGE-M3+FAISS) | – | ✅ | ✅ |
| Đa ngôn ngữ (Việt/Anh/Trung/Hàn/Nhật) | – | ✅ | ✅ |
| Trí nhớ hội thoại + nhớ ngữ cảnh đa lượt | – | ✅ | ✅ |
| Guardrail an toàn (chống jailbreak, che PII) | – | ✅ | ✅ |
| Tích hợp Zalo OA + Messenger | – | ✅ | ✅ |
| Dashboard phân tích (analytics) | – | ✅ | ✅ |
| Thời tiết + bản đồ chỉ đường | – | – | ✅ |
| **Tự học** (self-learning + critic + golden store) | – | – | ✅ |
| Auto-updater (tự cập nhật dữ liệu từ website) | – | – | ✅ |
| Multi-LLM failover (dự phòng nhà cung cấp) | – | – | ✅ |
| **Chi phí phát triển (trọn gói)** | **70.000.000đ** | **165.000.000đ** | **280.000.000đ** |

> Hệ thống hiện tại tương ứng **gói Cao cấp**.

---

## 3. CHI TIẾT HẠNG MỤC — GÓI CAO CẤP (tham khảo)

| # | Hạng mục | Chi phí (VNĐ) |
|---|---|---:|
| 1 | Khảo sát, thiết kế kiến trúc hệ thống | 8.000.000 |
| 2 | Core Chat Engine — 2-LLM pipeline (Planner + Responder) | 25.000.000 |
| 3 | Hybrid RAG (BGE-M3 + FAISS + BM25 + orchestrator) | 30.000.000 |
| 4 | Số hóa & chuẩn hóa cơ sở tri thức Suối Tiên | 20.000.000 |
| 5 | FAQ fast-path engine | 8.000.000 |
| 6 | Đa ngôn ngữ (5 thứ tiếng) | 15.000.000 |
| 7 | Guardrail an toàn (jailbreak, PII, kiểm tra output) | 12.000.000 |
| 8 | Trí nhớ 3 tầng (session / hội thoại / dài hạn) | 15.000.000 |
| 9 | Hệ thống tự học (Self-learning + Critic + Golden Store) | 25.000.000 |
| 10 | Tools: thời tiết, bản đồ, tự đính link | 12.000.000 |
| 11 | Auto-updater (crawl sitemap, cập nhật nóng) | 15.000.000 |
| 12 | Analytics dashboard + Multi-LLM failover | 12.000.000 |
| 13 | Website Chat UI | 12.000.000 |
| 14 | Tích hợp Zalo OA | 10.000.000 |
| 15 | Tích hợp Facebook Messenger | 10.000.000 |
| 16 | Triển khai, kiểm thử, tài liệu, đào tạo vận hành | 15.000.000 |
| | **TỔNG (chưa VAT)** | **244.000.000** |
| | Ưu đãi trọn gói | −(...) |
| | **THÀNH TIỀN GÓI CAO CẤP** | **280.000.000** |

*(Giá chưa gồm VAT 8%. Chi phí có thể điều chỉnh theo phạm vi thực tế.)*

---

## 4. HẠNG MỤC MỞ RỘNG (tùy chọn, tính riêng)

| Hạng mục | Chi phí ước tính (VNĐ) |
|---|---:|
| Tích hợp **thật** CRM / Hệ thống bán vé / Odoo (đặt vé, kiểm tra tồn) | 40.000.000 – 80.000.000 |
| Đặt bàn nhà hàng / booking teambuilding online | 25.000.000 – 50.000.000 |
| Tổng đài giọng nói (voice bot) | 40.000.000 – 90.000.000 |
| App di động / widget nhúng nâng cao | theo yêu cầu |
| Bổ sung ngôn ngữ / persona thương hiệu riêng | 8.000.000 / mục |

---

## 5. CHI PHÍ VẬN HÀNH ĐỊNH KỲ (khách hàng chi trả)

| Khoản mục | Ước tính / tháng |
|---|---:|
| Token LLM (Grok/xAI) — tùy lưu lượng | 2.000.000 – 8.000.000 |
| Hosting server (GPU cho BGE-M3) | 3.000.000 – 8.000.000 |
| *(hoặc bản CPU tiết kiệm)* | 1.500.000 – 3.000.000 |
| API Bản đồ / Thời tiết | 0 – 1.000.000 |
| **Bảo trì & hỗ trợ kỹ thuật** (gói) | 5.000.000 – 15.000.000 |

> Chi phí token/hosting phụ thuộc lượng người dùng thực tế (ví dụ 10.000–50.000 lượt hỏi/tháng).

---

## 6. TIẾN ĐỘ THỰC HIỆN

| Giai đoạn | Nội dung | Thời gian |
|---|---|---|
| 1 | Khảo sát, chốt yêu cầu, số hóa dữ liệu | 1 – 2 tuần |
| 2 | Phát triển core + RAG + tri thức | 3 – 4 tuần |
| 3 | Đa kênh, đa ngôn ngữ, an toàn, tự học | 2 – 3 tuần |
| 4 | Kiểm thử, tinh chỉnh, đào tạo, go-live | 1 – 2 tuần |
| | **Tổng thời gian** | **7 – 11 tuần** |

---

## 7. ĐIỀU KHOẢN THANH TOÁN

- **Đợt 1 (40%)** — ký hợp đồng, khởi động dự án
- **Đợt 2 (30%)** — nghiệm thu bản demo (core + tri thức)
- **Đợt 3 (30%)** — nghiệm thu go-live toàn hệ thống

---

## 8. BẢO HÀNH & CAM KẾT

- **Bảo hành 12 tháng**: sửa lỗi phát sinh miễn phí.
- Bàn giao **mã nguồn + tài liệu kỹ thuật + tài liệu vận hành**.
- Đào tạo đội ngũ Suối Tiên tự cập nhật nội dung.
- Hỗ trợ kỹ thuật trong giờ hành chính; gói SLA 24/7 tính riêng.

---

## 9. GHI CHÚ

1. Giá trên là **tham khảo**, điều chỉnh theo phạm vi & yêu cầu cuối cùng.
2. Chi phí token LLM & hosting do khách hàng chi trả theo thực tế sử dụng.
3. Suối Tiên cung cấp dữ liệu nội dung (giá vé, trò chơi, sự kiện…) và tài khoản kênh (Zalo OA, Fanpage).
4. Báo giá chưa bao gồm VAT.

---

*Trân trọng cảm ơn Quý công ty. Rất mong được hợp tác cùng Suối Tiên.*
