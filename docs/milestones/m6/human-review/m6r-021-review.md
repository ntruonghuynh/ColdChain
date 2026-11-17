# Phiếu review độc lập — M6R-021

**Trạng thái:** CHƯA ĐƯỢC REVIEW. Chọn một kết quả bên dưới; đừng dùng trạng thái API/citation như phán quyết semantic. Tài liệu này được tổng hợp từ bản đọc chỉ-đọc với vai trò QUALITY trong DB eval-prep. Draft append-only không bị sửa.

## Nhận diện và thời điểm

- Incident: `d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7`; mã nghiệp vụ: `INC-SIM-S11-J0123-SIM-S11-L0123-GAP-20260921T143800Z`; explanation: `49f31638-327f-4a3f-a969-435f1e2936ec`. Evidence revision: `SYS:incident/d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7:revision/1`.
- Model ghi trên draft: `gpt-6-luna`; prompt: `response_draft/v1`; source: `llm`; API status: `draft`; citation check: `passed`.
- Sensor event interval: `2026-09-21T14:08:00Z` → `2026-09-21T18:08:00Z`. Evidence cutoff: `2026-11-17T08:27:42Z`.
- SOP-EXC v1.0: effective_from `2026-11-14`, effective_to chưa đặt; incident tháng 9/2026 nên SOP v1.0 là hướng dẫn hiện hành tại cutoff, không phải SOP đã hiệu lực lúc incident.

## Claim và evidence quan sát được

**Summary draft:** Incident DATA_GAP đang OPEN đối với lô SIM-S11-J0123, cảm biến SIM-S11-L0123. Có dữ liệu thiếu từ 2026-09-21T14:38:00Z đến 17:38:00Z và các số đo sau đó ghi nhận nhiệt độ cao; M3 xác nhận phát hiện HIGH theo policy baseline. Không có dự đoán M4 tại cutoff. Đây là mô phỏng; thông tin này không quyết định tình trạng xuất kho.

**Observed claims:**

- **Claim:** Evidence cutoff: 2026-11-17T08:27:42Z; khoảng sensor được cung cấp là 2026-09-21T14:08:00Z–18:08:00Z.
  **Evidence refs:** 14 source `SYS:reading/*`; toàn bộ ID trong `../raw/m6-quality-api-review-extract-verified.json`; causal cutoff `2026-11-17T08:27:42Z`.
- **Claim:** Các số đo trước khoảng thiếu, từ 14:08 đến 14:38, nằm trong 3.2–3.5 °C. Các bản ghi được nhận trễ so với event_at; ví dụ số đo lúc 14:33 được nhận lúc 14:45:23.
  **Evidence refs:** 14 source `SYS:reading/*`; toàn bộ ID trong `../raw/m6-quality-api-review-extract-verified.json`; causal cutoff `2026-11-17T08:27:42Z`.
- **Claim:** Không có số đo trong khoảng 14:38–17:38, span 180 phút; trạng thái là UNKNOWN_REVIEW_REQUIRED, không được tính là trong ngưỡng.
  **Evidence refs:** 14 source `SYS:reading/*`; toàn bộ ID trong `../raw/m6-quality-api-review-extract-verified.json`; causal cutoff `2026-11-17T08:27:42Z`.
- **Claim:** Sau khoảng thiếu, các số đo từ 17:38 đến 18:08 nằm trong 12.0–12.3 °C; số đo lúc 17:38 được nhận lúc 17:44:39. Tất cả 14 readings trong summary được đánh dấu delayed.
  **Evidence refs:** 14 source `SYS:reading/*`; toàn bộ ID trong `../raw/m6-quality-api-review-extract-verified.json`; causal cutoff `2026-11-17T08:27:42Z`.

**Policy/M3 claims:**

- **Claim:** Theo POL-CHILL-01 phiên bản 1.0, ngưỡng cao là trên 8.0 °C liên tục ít nhất 30 phút; đây là quy tắc mô phỏng, không phải tiêu chuẩn an toàn pháp quy.
  **Evidence refs:** `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`, `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`, `SYS:policy/POL-CHILL-01@1.0`, `SYS:warning/7e77f977-d7bf-580f-99ba-22ac92940fe3`
- **Claim:** M3 ghi nhận phát hiện HIGH, nguồn POLICY_BASELINE, gồm 32 readings, từ 2026-09-21T17:38:00Z đến 20:13:00Z, peak 12.5 °C và meets_policy_duration=true. Phát hiện được ghi nhận lúc 20:29:48Z.
  **Evidence refs:** `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`, `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`, `SYS:policy/POL-CHILL-01@1.0`, `SYS:warning/7e77f977-d7bf-580f-99ba-22ac92940fe3`
- **Claim:** Đầu khoảng phát hiện kề khoảng UNKNOWN; thời lượng quan sát liên tục xung quanh khoảng thiếu là giới hạn dưới. Không thể kết luận diễn biến nhiệt độ trong khoảng thiếu.
  **Evidence refs:** `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`, `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`, `SYS:policy/POL-CHILL-01@1.0`, `SYS:warning/7e77f977-d7bf-580f-99ba-22ac92940fe3`

**M4 advisory:**

- Không có dự đoán advisory M4 trong evidence tại cutoff.

**Unknowns / evidence còn thiếu:**

- Nhiệt độ thực tế trong khoảng 14:38–17:38 không được biết từ evidence; không thể nội suy từ các số đo hai phía.
- Nguyên nhân của khoảng mất dữ liệu và của các số đo cao chưa được xác định.
- Không có disposition M5 trong evidence được cung cấp.
- Cần thêm: Bằng chứng bổ sung có thể làm rõ diễn biến trong khoảng thiếu và nguyên nhân mất dữ liệu; hiện chưa có trong evidence được cung cấp.

## Mốc event_at / received_at mẫu (UTC)

| event_at | received_at | °C | cutoff check | reading reference |
|---|---|---:|---|---|
| 2026-09-21T14:33:00+00:00 | 2026-09-21T14:45:23+00:00 | 3.2 | received trước cutoff | `SYS:reading/c2e1db9b-0ab2-55da-8005-ba99065ae524` |
| 2026-09-21T17:38:00+00:00 | 2026-09-21T17:44:39+00:00 | 12.3 | received trước cutoff | `SYS:reading/7e5b583a-a1ab-5893-be01-be43101a39b0` |
| 2026-09-21T18:08:00+00:00 | 2026-09-21T18:14:19+00:00 | 12.0 | received trước cutoff | `SYS:reading/200b98e8-a924-59ef-920d-46f730807081` |

Ví dụ trên không thay thế kiểm tra đủ 14 readings và causal rule: event_at/received_at khác nhau; chỉ bản ghi nhận trước hoặc đúng cutoff mới có sẵn tại cutoff.

## Citation của draft: SOP và evidence

Citation ID/quote đã qua kiểm tra máy đối với source set; điều này không chứng minh semantic entailment. Các citation policy/M3 là evidence claim; các citation SOP là hướng dẫn thủ tục. Đối chiếu từng claim với section/version:

### `SOP-EXC@1.0#DELAYED_OCEAN`
- **Claim gắn citation:** Phân biệt thời điểm đo với thời điểm nhận; không kết luận nhiệt độ trong thời gian chưa nhận được số liệu.
- **Quote được lưu:** “- Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`).
- Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó.
- Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.”


### `SOP-EXC@1.0#HIGH_EXCURSION`
- **Claim gắn citation:** Tóm tắt số đo và M3; khoảng thiếu làm gián đoạn chuỗi quan sát và khi kề UNKNOWN, thời lượng quan sát được là giới hạn dưới.
- **Quote được lưu:** “- Tóm tắt các số đo quan sát được, thời điểm đo, thời điểm nhận, khoảng sự kiện và kết quả detector M3.
- Đối chiếu đúng policy đang gắn với lô hàng. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức cao khi số đo lớn hơn 8.0 °C liên tục ít nhất 30 phút; các khoảng thiếu làm gián đoạn chuỗi quan sát.
- Nếu sự kiện kề khoảng UNKNOWN, nói rõ thời lượng quan sát được là giới hạn dưới; không khẳng định diễn biến trong khoảng trống.
- Chuyển phần quyết định cho Quality Officer theo workflow M5.”


## Các vấn đề cần đánh giá

Ca DATA_GAP: khoảng UNKNOWN 14:38–17:38Z kéo dài 180 phút. Không có M4 advisory trong evidence; vắng mặt không phải dự đoán âm hoặc bằng chứng an toàn. Reviewer xác nhận claim M3 sau gap và giới hạn dữ liệu.

- Có claim nào nói hoặc ngụ ý thiếu telemetry = nhiệt độ an toàn?
- Mốc thời gian, số đo, M3 và uncertainty có khớp evidence?
- Citation có hỗ trợ claim procedural về mặt ngữ nghĩa?
- Văn phong có rõ cho operator không?
- Quality Officer có giữ quyền disposition/release độc quyền?

**Quyết định do chủ dự án báo cáo (provenance: `OWNER_REPORTED`):** `PASS` (ghi nguyên văn; không phải kết luận review độc lập đã được xác minh).

**Ghi chú bổ sung của chủ dự án:** None provided.

**Reviewer ID / vai trò:** NOT PROVIDED.

**reviewed_at (UTC):** NOT PROVIDED.

**recorded_at (UTC):** `2026-11-17T15:22:00Z` (thời điểm ghi nhận trong worksheet; không phải thời điểm review).

**Rationale do reviewer cung cấp:** NOT PROVIDED.

**Evidence references do reviewer lựa chọn/xác nhận:** NOT PROVIDED. Các source/evidence refs có sẵn ở trên được giữ nguyên như dữ liệu hệ thống ban đầu; chúng không được quy là bằng chứng do reviewer chọn hoặc xác nhận.

**Trạng thái nghiệm thu kỹ thuật hiệu lực:** `NOT_ESTABLISHED_PENDING_REVIEW_METADATA_AND_SUPPORTING_EVIDENCE`. Quyết định `OWNER_REPORTED PASS` không tự động đóng các finding hoặc thay thế bằng chứng review còn thiếu.

**Rationale và evidence/citation refs của reviewer:** NOT PROVIDED.
