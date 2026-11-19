# Kịch bản demo ColdChain trong lớp (khoảng 7 phút)

## Chuẩn bị trước giờ trình bày

- Chạy bản demo cục bộ riêng, nhập seed 11 và replay theo [hướng dẫn cài đặt](huong-dan-cai-dat.md). Tài khoản lớp học chỉ dùng nếu đã bật `LOCAL_DEMO_MODE=true` trước lần seed đầu.
- Kịch bản ocean cần chuẩn bị bằng lệnh CLI sau trong database demo riêng; lệnh ghi thêm shipment mô phỏng và chạy lại cùng source có tính ổn định:

  ```bash
  docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean --source SIM-S11-J0154
  docker compose --profile tools run --rm data-tools python -m app.monitoring summary
  ```

- Các kịch bản disposition/release tạo business record nếu xác nhận. Chỉ chạy trong DB disposable dành riêng cho phần trình diễn mutation, sau khi chủ trì chấp thuận dữ liệu chuẩn bị. Không thực hiện trên M5/M6 hiện hữu. Kịch bản audit confirmed transaction và M6 citation cần dữ liệu đã được chuẩn bị hợp lệ trong project demo khác; fresh seed không đảm bảo có các bản ghi này.
- Không gọi prediction scoring hoặc LLM generation trong kịch bản. Không tạo citation/chain event giả.

## Lời dẫn theo cảnh

| Thời lượng | Cảnh, trang và thao tác | Lời dẫn / điều cần quan sát |
|---|---|---|
| 0:00–0:35 | **Giới thiệu — Overview**. Mở `/`, chỉ trạng thái backend, DB, migration và policy. | “ColdChain mô phỏng theo dõi chuỗi lạnh từ telemetry đến review. Dữ liệu là mô phỏng; policy là quy tắc giảng dạy, không phải chứng nhận quy định.” Nếu API chưa sẵn sàng, dừng trình diễn và kiểm tra health. |
| 0:35–1:10 | **Chuyến bình thường — Shipments → Temperature Monitoring**. Chọn một shipment seed 11 đã có dữ liệu, xem chart. | “Đường nằm trong policy chỉ mô tả observations đã nhận. Nó không chứng minh khoảng trống là an toàn.” Dùng shipment không có incident nếu danh sách cho thấy. Nếu không có, chuyển ngay tới shipment có sẵn và nói rõ không còn normal example được xác nhận. |
| 1:10–1:55 | **HIGH/LOW — Excursion Queue → Incident Details**. Lọc excursions, mở incident có nhãn `HIGH` hoặc `LOW`. | Chỉ dải 2–8°C, event interval, duration, detector/policy version và evidence. Policy fixture: HIGH >8°C ít nhất 30 phút, LOW <2°C ít nhất 15 phút. Đây là baseline M3. Nếu không thấy cả hai loại, chỉ trình bày incident đang có; không tạo incident thủ công. |
| 1:55–2:45 | **Ocean gap — Temperature Monitoring/Incident Details**. Mở shipment có prefix `DEMO-OCEAN-`; xem gap và timeline/revisions. | “Mất liên lạc làm freshness giảm: CURRENT → STALE → UNKNOWN; UNKNOWN không có nghĩa safe. Dữ liệu đến muộn dùng received time khác event time, có thể bổ sung HIGH và revision.” Mốc đã quan sát trong fixture là outage khoảng 14.13 giờ; trạng thái chuyển khoảng 7.52 phút và 15.02 phút. Nếu ocean data chưa chuẩn bị, bỏ qua cảnh và mô tả đây là setup CLI, không giả lập trên browser. |
| 2:45–3:25 | **Review evidence — Quality Review**, đăng nhập `quality`. Chọn shipment có open incident, đọc references và evidence; không cần submit trong bản read-only. | “QUALITY xem evidence và đưa ra disposition riêng. Backend kiểm tra toàn bộ prerequisite.” Nếu trình diễn thật disposition, chỉ trên DB disposable và sau xác nhận rõ ràng; chọn RELEASE/QUARANTINE, nhập rationale/reference, rà soát confirm. Đây tạo dữ liệu M5, vì vậy không thuộc read-only rehearsal. |
| 3:25–3:55 | **Từ chối trái quyền — Audit History**, đăng nhập `quality` rồi giải thích vì sao thao tác kiểm tra signed audit ADMIN-only không xuất hiện. Để thể hiện phản hồi thật của backend, chạy `python3 scripts/deployment_smoke.py` trong terminal demo đã cấu hình. | Smoke helper thực hiện login local và GET ADMIN-only audit verification, kỳ vọng HTTP 403 với QUALITY; đây là lệnh chỉ đọc. UI ẩn control theo role nhưng backend vẫn enforce độc lập. Không tạo disposition chỉ để gây lỗi quyền. Nếu helper chưa có cấu hình, mô tả kết quả đã kiểm chứng trong deployment handover, không giả vờ đã chạy live. |
| 3:55–4:25 | **Physical release — Incident Details**, đăng nhập `warehouse`. Chỉ sau backend xác nhận QUALITY RELEASE, xem gate release. | “Quyết định RELEASE của QUALITY không tự động xuất hàng; WAREHOUSE có quyền physical release riêng.” Chỉ submit trong DB disposable và sau xác nhận. Nếu chưa có disposition hợp lệ, kỳ vọng backend chặn prerequisite; không giả vờ release thành công. |
| 4:25–5:05 | **Audit — Audit History**, đăng nhập user; nhập business reference đã tồn tại để verify. ADMIN có thể chạy reconciliation/verify signed audit (GET). | Quan sát pending/confirmed, attempts, tx hash, audit status nếu có. Fresh import có thể có 0 confirmed transaction và các incident outbox pending; pending không tự chứng minh chain lỗi. Worker retry tự chạy; UI không có nút retry. Nếu reference không tồn tại, dùng empty/not found state. |
| 5:05–5:45 | **M4 — Temperature Monitoring**, xem model readiness card, không bấm scoring API. | “Model ready chỉ có nghĩa model nạp được, chưa phải prediction. Giao diện không tự score; thiếu evidence là UNKNOWN, advisory không cho phép release.” Nếu model unavailable, trình bày trạng thái unavailable thay vì kết luận an toàn. |
| 5:45–6:30 | **M6 — Incident Details**, mở explanation history đã có sẵn (nếu được chuẩn bị). | Xem status, model/source, cutoff, SOP `source_id`/version/quote/evidence refs, validation và unknowns. Citation validation không chứng minh semantic correctness. Fresh DB thường không có explanation; empty state là đúng. Không gọi provider hoặc tạo explanation trong lúc trình chiếu. |
| 6:30–7:00 | **Kết luận — Overview**. | Tóm tắt luồng quan sát → detector → evidence → QUALITY → WAREHOUSE → audit. Nhấn mạnh bản demo giữ UNKNOWN khi thiếu evidence và mọi decision vẫn được backend role/prerequisite checks bảo vệ. |

## Phân biệt trình diễn đã kiểm chứng và cần chuẩn bị

- **Đã kiểm chứng trên triển khai cô lập:** seed 11 có 200 journeys; replay trước ocean có 105 `TEMPERATURE_EXCURSION`, 41 `DATA_GAP`; ocean replay cho progression stale/unknown/current và delayed backfill/revision. Dashboard đọc health, shipment, incident evidence, model readiness, ledger/audit GET; xác thực trả 401 nếu chưa đăng nhập và 403 với role không đủ quyền.
- **Cần dữ liệu/role chuẩn bị:** Quality disposition và WAREHOUSE release là workflow có ghi DB; chỉ chạy trên DB disposable tách biệt. Signed audit verification/Reconciliation cần quyền ADMIN và state phù hợp.
- **Không mặc định có trên fresh DB:** confirmed blockchain business transaction, stored M6 explanation/citation. Không tạo dữ liệu giả để lấp empty state.
- **Chỉ có qua CLI/API nội bộ hiện tại:** dataset import/replay/ocean scenario và M4 scoring; không nói browser có nút replay, prediction history hay blockchain retry.
