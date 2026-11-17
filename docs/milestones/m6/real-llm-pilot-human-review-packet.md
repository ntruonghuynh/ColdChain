# Phiếu review con người — năm draft pilot M6

**Mục đích:** packet được lập từ bản ghi đã đọc qua API chỉ-đọc bằng tài khoản QUALITY trong isolated eval-prep. Không gọi LLM/provider và không sửa record append-only. Đây là công cụ review; chưa có kết luận PASS/FAIL nào được điền.

**Đọc đúng vai trò của thông tin:** sensor/M3/M4/M5 IDs là evidence vận hành; `citations` trong draft chủ yếu là SOP guidance. Citation ID/quote hợp lệ không chứng minh semantic entailment. Các diễn giải dưới đây chưa được reviewer phê duyệt.

Phiếu operator-readable theo từng ca đã tách tại [`human-review/README.md`](human-review/README.md); dùng các phiếu đó để ghi kết quả độc lập. Tài liệu hiện tại giữ phần claim/evidence chi tiết và bảng timestamp mở rộng.

**SOP hiện tại:** SOP-EXC v1.0, effective_from `2026-11-14`, effective_to chưa đặt; 5 sự kiện xảy ra tháng 9/2026. Tại ngày giải thích/cutoff 2026-11-17, SOP v1.0 hiện hành; không được mô tả nó như SOP đã có hiệu lực lúc sự kiện tháng 9.

**Đường đọc:** `QUALITY POST /api/auth/login` → `GET /api/llm/incidents/{id}/explanations` → `GET /api/llm/explanations/{explanation_id}`. Cả năm record trả HTTP 200, `source_mode=llm`, `explanation_status=draft`, `citation_verification=passed`; đây không phải phán quyết ngữ nghĩa.

## M6R-001

- Incident `57d47f92-95df-537c-a4a7-a056265e83bb`; record `71e6fd35-0ea2-476d-bba5-fc545a928b76`; incident ref `INC-SIM-S11-J0177-SIM-S11-L0177-TEX-H-20260902T215900Z`.
- Cutoff `2026-11-17T08:27:42Z`; sensor event-time interval `2026-09-02T21:29:00Z` → `2026-09-03T01:09:00Z`; `48` evidence references; SOP `SOP-EXC v1.0`; policy `1.0`.
- Machine status: source `llm`, status `draft`, citation check `passed`, model `gpt-6-luna`, prompt `response_draft/v1`. Human review chưa đánh dấu.

### Claim excerpts từ draft và kiểm tra evidence

**Tóm tắt:**
- Incident nhiệt độ cao của lô SIM-S11-J0177 còn OPEN tại cutoff 2026-11-17T08:27:42+00:00. Theo dữ liệu được cung cấp, 33 số đo nằm trong khoảng M3 2026-09-02 21:59–2026-09-03 00:39 UTC; M3 xác nhận đạt thời lượng theo POL-CHILL-01 v1.0. Đây là quy tắc mô phỏng, không phải tiêu chuẩn an toàn pháp quy. Không có tư vấn M4 hay disposition M5 được cung cấp; quyết định xử lý thuộc Quality Officer có thẩm quyền.

**Quan sát:**
- Khoảng sensor được cung cấp là 2026-09-02 21:29 đến 2026-09-03 01:09 UTC, với chu kỳ ghi nhận 5 phút. Tóm tắt cho biết 45/45 bản ghi bị trễ; mọi bản ghi liệt kê đều có received_at không sau cutoff.
- Các số đo hiển thị tăng từ 7.9°C lúc 21:54 lên 8.8°C lúc 21:59; mức cao nhất là 12.7°C lúc 23:24. Sau đó, số đo giảm còn 8.8°C lúc 00:39 và xuống 7.5°C lúc 00:44.
- Mỗi số đo có received_at muộn hơn event_at; độ trễ quan sát được thay đổi giữa các bản ghi. Ví dụ, số đo 11.3°C lúc 22:24 được nhận lúc 22:38:23 UTC.
- Các số đo được cung cấp cho thấy trạng thái cửa CLOSED; đây chỉ là quan sát metadata và không xác định nguyên nhân sự kiện.

**Kết quả policy/M3:**
- M3 phát hiện HIGH theo POLICY_BASELINE: 33 readings, từ 21:59 đến 00:39 UTC, đỉnh 12.7°C, meets_policy_duration=true; phát hiện được ghi nhận lúc 00:52:16 UTC.
- POL-CHILL-01 v1.0 cho nhóm CHILLED_2_8C đặt giới hạn cao 8.0°C và thời lượng tối thiểu 30 phút. Khoảng M3 kéo dài 160 phút theo mốc sự kiện, vượt thời lượng tối thiểu; đây là kết quả detector theo policy, không phải kết luận an toàn sản phẩm.
- Incident có trạng thái OPEN tại cutoff; dữ liệu ghi nhận không có disposition M5.

**Advisory M4:**
- Không có dự đoán hay advisory M4 nào trong evidence được cung cấp.

**Yếu tố có thể liên quan:**
- Các số đo đều đến trễ; dữ liệu chỉ xác nhận độ trễ truyền/nhận quan sát được, không chứng minh nguyên nhân thay đổi nhiệt độ.
- Không có bằng chứng được cung cấp xác nhận nguyên nhân sự kiện; trạng thái cửa CLOSED không đủ để xác định nguyên nhân.

**Bước đề xuất:**
- Để Quality Officer có thẩm quyền xem xét evidence và quyết định theo workflow M5; phần giải thích này không đưa ra quyết định RELEASE hoặc QUARANTINE. Citation: SOP-EXC@1.0#HIGH_EXCURSION.

**Điều chưa biết:**
- Không thể xác định chính xác diễn biến nhiệt độ giữa các thời điểm ghi nhận, hoặc trước khi dữ liệu đến hệ thống; không nội suy khoảng giữa các bản ghi.
- Không có evidence về nguyên nhân, đánh giá chất lượng sản phẩm, hay quyết định M5 tại cutoff.

**Evidence hệ thống:** `SYS:incident/57d47f92-95df-537c-a4a7-a056265e83bb:revision/10`; `SYS:m3-detection/ae9e3305-b41c-595b-be92-f635a8954f30`; `SYS:policy/POL-CHILL-01@1.0`; toàn bộ source refs, gồm reading refs, nằm trong `raw/m6-quality-api-review-extract-verified.json`.

**Claim → evidence map để reviewer xác nhận:**

| Nhóm claim trong draft | Nguồn cần đối chiếu |
|---|---|
| Sensor facts, event/received time | 45 reading refs trong API extract; các mốc mẫu và từng `event_at`/`received_at` ở bảng bên dưới |
| M3 detector / policy | `SYS:m3-detection/ae9e3305-b41c-595b-be92-f635a8954f30`; `SYS:policy/POL-CHILL-01@1.0` |
| Incident status/revision | `SYS:incident/57d47f92-95df-537c-a4a7-a056265e83bb:revision/10`; payload không có disposition M5 reference |
| Khoảng missing/unknown | không có M3 gap ref; đối chiếu readings hai phía, không suy diễn trong gap |
| M4 advisory | Không có `SYS:m4-prediction` reference trong evidence payload; absence không phải negative prediction |
| SOP bước xử lý | `SOP-EXC@1.0#DELAYED_OCEAN`; `SOP-EXC@1.0#HIGH_EXCURSION`; `SOP-EXC@1.0#SENSOR_UNCERTAINTY`; xem claim và quote chính xác ngay dưới đây |


**Mẫu thời gian sensor từ temporal audit (UTC):**

| event_at | received_at | °C | cutoff check | source ref |
|---|---|---:|---|---|
| 2026-09-02T21:54:00+00:00 | 2026-09-02T22:07:58+00:00 | 7.9 | received trước cutoff | `SYS:reading/fdc2c32a-57fd-5156-bb63-bacda00f8564` |
| 2026-09-02T21:59:00+00:00 | 2026-09-02T22:07:58+00:00 | 8.8 | received trước cutoff | `SYS:reading/e13f7846-6f53-5f5c-9570-6adf8d8f92fe` |
| 2026-09-02T22:24:00+00:00 | 2026-09-02T22:38:23+00:00 | 11.3 | received trước cutoff | `SYS:reading/0339216f-bf32-55b2-b57a-b279c115ecae` |
| 2026-09-02T23:24:00+00:00 | 2026-09-02T23:37:38+00:00 | 12.7 | received trước cutoff | `SYS:reading/f64c643c-7d8f-527a-905f-3c161b90beb2` |
| 2026-09-03T00:39:00+00:00 | 2026-09-03T00:52:16+00:00 | 8.8 | received trước cutoff | `SYS:reading/ba103cca-1adf-51ea-8bb2-738c98e84bd8` |
| 2026-09-03T00:44:00+00:00 | 2026-09-03T00:52:16+00:00 | 7.5 | received trước cutoff | `SYS:reading/ba1a4254-7a87-5b82-b559-d0b092daad8d` |

**M3 detection evidence:**
- `SYS:m3-detection/ae9e3305-b41c-595b-be92-f635a8954f30` HIGH 2026-09-02T21:59:00+00:00–2026-09-03T00:39:00+00:00; raised `2026-09-03T00:52:16+00:00`; `raised_by_cutoff=True`; 33 readings; peak 12.7°C.

### Citation procedure riêng với evidence sensor

- `SOP-EXC@1.0#DELAYED_OCEAN` — claim của draft: Phân biệt thời điểm đo và thời điểm nhận; chỉ coi bản ghi đã nhận trước cutoff là lịch sử có thể dùng, và không kết luận nhiệt độ trong khoảng chưa có số liệu nhận được.
  - Quote đã lưu/được kiểm: - Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`). - Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó. - Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.
- `SOP-EXC@1.0#HIGH_EXCURSION` — claim của draft: Đối chiếu detector với policy gắn cho lô hàng; chuyển quyết định xử lý cho Quality Officer theo workflow M5.
  - Quote đã lưu/được kiểm: - Tóm tắt các số đo quan sát được, thời điểm đo, thời điểm nhận, khoảng sự kiện và kết quả detector M3. - Đối chiếu đúng policy đang gắn với lô hàng. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức cao khi số đo lớn hơn 8.0 °C liên tục ít nhất 30 phút; các khoảng thiếu làm gián đoạn chuỗi quan sát. - Nếu sự kiện kề khoảng UNKNOWN, nói rõ thời lượng quan sát được là giới hạn dưới; không khẳng định diễn biến trong khoảng trống. - Chuyển phần quyết định cho Quality Officer theo workflow M5.
- `SOP-EXC@1.0#SENSOR_UNCERTAINTY` — claim của draft: Advisory ML, nếu có, là bằng chứng riêng biệt và không quyết định RELEASE hoặc QUARANTINE; khi bối cảnh chưa đủ phải nêu thiếu bằng chứng.
  - Quote đã lưu/được kiểm: - Nêu cảnh báo M3/M4 liên quan như bằng chứng riêng biệt, kèm phiên bản và thời điểm. - Điểm ML chỉ là advisory. Không diễn giải điểm số thành quyết định RELEASE hoặc QUARANTINE. - Nếu cảm biến, thời gian hoặc bối cảnh chưa đủ để diễn giải, trả trạng thái thiếu bằng chứng.

### Điểm reviewer cần đánh giá

SOP là hướng dẫn hiện hành tại thời điểm giải thích; chưa có SOP v1.0 hiệu lực lúc sự kiện tháng 9. Reviewer cần tách hướng dẫn hiện hành khỏi căn cứ lịch sử. Không có M4 prediction reference.
- Đọc claim cạnh đúng event_at, received_at, detector/policy evidence; không coi gap hoặc advisory vắng mặt là bằng chứng an toàn.
- Đánh giá riêng SOP citation có hỗ trợ claim cụ thể về thủ tục không; citation check tự động chỉ xác minh ID/quote.

**Kết luận reviewer (chọn một):** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE`

**Reviewer identity/role:** ____________________    **Thời điểm review (UTC):** ____________________

**Rationale và evidence/citation cụ thể:**

____________________________________________________________________________

____________________________________________________________________________

## M6R-006

- Incident `a9080f06-2c7d-542f-ae07-9ba4e2961718`; record `1b44ad60-8ded-4c22-a7cc-49c51091ca2d`; incident ref `INC-SIM-S11-J0112-SIM-S11-L0112-TEX-L-20260902T152200Z`.
- Cutoff `2026-11-17T08:27:42Z`; sensor event-time interval `2026-09-02T14:52:00Z` → `2026-09-02T16:12:00Z`; `22` evidence references; SOP `SOP-EXC v1.0`; policy `1.0`.
- Machine status: source `llm`, status `draft`, citation check `passed`, model `gpt-6-luna`, prompt `response_draft/v1`. Human review chưa đánh dấu.

### Claim excerpts từ draft và kiểm tra evidence

**Tóm tắt:**
- Incident nhiệt độ thấp đang OPEN cho lô SIM-S11-J0112, cảm biến SIM-S11-L0112. Tại cutoff 2026-11-17T08:27:42+00:00, dữ liệu cho thấy các số đo thấp hơn giới hạn policy và hai phát hiện M3 đáp ứng thời lượng policy; có một khoảng thiếu dữ liệu nên không thể xác định nhiệt độ trong khoảng đó. Không có advisory M4 hoặc disposition M5 được cung cấp. Quyết định nghiệp vụ thuộc Quality Officer được ủy quyền.

**Quan sát:**
- Khoảng sensor được cung cấp: 2026-09-02 14:52–16:12 UTC; 16/16 số đo được đánh dấu delayed. Các bản ghi được nêu trong evidence có received_at không sau cutoff.
- Trong dãy số đo, nhiệt độ giảm từ 2.1°C lúc 15:17 xuống 1.9°C lúc 15:22 và tiếp tục ở dưới 2.0°C trong các số đo đến 15:42; giá trị thấp nhất trong khoảng dữ liệu được cung cấp là 0.6°C lúc 15:57 và 16:12.
- Tại thời điểm 15:42 có số đo 1.2°C; kế tiếp là số đo lúc 15:52 ở 0.7°C. Không có số đo trong khoảng 15:42–15:52; hệ thống ghi nhận SHORT_GAP, không tính thời gian này là trong ngưỡng.
- Các bản ghi trong chuỗi được liệt kê có door_state CLOSED. Đây là quan sát, không xác định nguyên nhân.

**Kết quả policy/M3:**
- Policy gắn với lô: POL-CHILL-01 v1.0, khoảng 2.0–8.0°C; ngưỡng thời lượng LOW là 15 phút. Đây là quy tắc mô phỏng, không phải tiêu chuẩn an toàn pháp quy.
- M3 phát hiện LOW đầu tiên: 15:22–15:42 UTC, 5 readings, peak_c 1.0°C, meets_policy_duration=true; được ghi nhận lúc 15:56:04 UTC.
- M3 phát hiện LOW thứ hai: 15:52–18:32 UTC, 33 readings, peak_c 0.2°C, meets_policy_duration=true; được ghi nhận lúc 18:40:47 UTC. Mốc kết thúc vượt sensor_interval_end_at 16:12 UTC của phần readings được cung cấp, nên không thể kiểm chứng toàn bộ phát hiện này bằng readings hiện có.
- Incident revision 2 có extent 15:22–15:42 UTC và trạng thái OPEN tại cutoff.

**Yếu tố có thể liên quan:**
- Độ trễ truyền dữ liệu là yếu tố quan sát được; không có bằng chứng đủ để xác nhận nó gây ra excursion.
- Các số đo ambient khoảng 38.6–39.6°C được ghi trong evidence, nhưng không chứng minh nguyên nhân của nhiệt độ sản phẩm thấp.

**Bước đề xuất:**
- Theo SOP, phân biệt event_at và received_at, và không kết luận nhiệt độ trong thời gian chưa có dữ liệu.
- Chuyển đánh giá và quyết định theo workflow cho Quality Officer được ủy quyền; phần giải thích này không đưa ra quyết định release hoặc quarantine.

**Bằng chứng còn thiếu:**
- Readings và metadata tương ứng cho khoảng sau 16:12 UTC để đối chiếu phát hiện M3 thứ hai.
- Đánh giá của Quality Officer và bằng chứng chất lượng liên quan nếu cần xác định ảnh hưởng đối với sản phẩm.

**Điều chưa biết:**
- Nhiệt độ thực tế trong khoảng thiếu 15:42–15:52 UTC không được biết; không nội suy từ hai đầu khoảng.
- Readings sau 16:12 UTC không có trong danh sách readings của evidence, dù M3 phát hiện thứ hai kéo dài đến 18:32 UTC.
- Nguyên nhân của nhiệt độ thấp và ảnh hưởng đối với sản phẩm chưa được xác định từ evidence được cung cấp.
- Không có disposition M5 hoặc dự đoán advisory M4 tại cutoff.

**Evidence hệ thống:** `SYS:gap/c586362b-4b79-57a9-962a-a37e55f72422`; `SYS:incident/a9080f06-2c7d-542f-ae07-9ba4e2961718:revision/2`; `SYS:m3-detection/2407bbdf-1ad3-554a-8ad8-ec64d7492113`; `SYS:m3-detection/70682314-3d9a-5ac6-a908-1fa3be922f47`; `SYS:policy/POL-CHILL-01@1.0`; toàn bộ source refs, gồm reading refs, nằm trong `raw/m6-quality-api-review-extract-verified.json`.

**Claim → evidence map để reviewer xác nhận:**

| Nhóm claim trong draft | Nguồn cần đối chiếu |
|---|---|
| Sensor facts, event/received time | 16 reading refs trong API extract; các mốc mẫu và từng `event_at`/`received_at` ở bảng bên dưới |
| M3 detector / policy | `SYS:m3-detection/70682314-3d9a-5ac6-a908-1fa3be922f47`; `SYS:m3-detection/2407bbdf-1ad3-554a-8ad8-ec64d7492113`; `SYS:policy/POL-CHILL-01@1.0` |
| Incident status/revision | `SYS:incident/a9080f06-2c7d-542f-ae07-9ba4e2961718:revision/2`; payload không có disposition M5 reference |
| Khoảng missing/unknown | `SYS:gap/c586362b-4b79-57a9-962a-a37e55f72422`; đối chiếu readings hai phía, không suy diễn trong gap |
| M4 advisory | Không có `SYS:m4-prediction` reference trong evidence payload; absence không phải negative prediction |
| SOP bước xử lý | `SOP-EXC@1.0#DELAYED_OCEAN`; `SOP-EXC@1.0#SENSOR_UNCERTAINTY`; `SOP-EXC@1.0#EVIDENCE_AUDIT`; xem claim và quote chính xác ngay dưới đây |


**Mẫu thời gian sensor từ temporal audit (UTC):**

| event_at | received_at | °C | cutoff check | source ref |
|---|---|---:|---|---|
| 2026-09-02T15:17:00+00:00 | 2026-09-02T15:25:38+00:00 | 2.1 | received trước cutoff | `SYS:reading/d8f8624b-37ea-51ca-bc8c-0b4b0f86abfd` |
| 2026-09-02T15:22:00+00:00 | 2026-09-02T15:25:38+00:00 | 1.9 | received trước cutoff | `SYS:reading/9f55ccf0-2eeb-5f5d-ae02-61ff56804eee` |
| 2026-09-02T15:42:00+00:00 | 2026-09-02T15:56:04+00:00 | 1.2 | received trước cutoff | `SYS:reading/d3d87ca3-75a2-54cb-a8a8-e7a26beb72a7` |
| 2026-09-02T15:52:00+00:00 | 2026-09-02T15:56:04+00:00 | 0.7 | received trước cutoff | `SYS:reading/e3e4ce66-bbb8-5e30-a8dd-e66731e9bf13` |
| 2026-09-02T16:12:00+00:00 | 2026-09-02T16:25:22+00:00 | 0.6 | received trước cutoff | `SYS:reading/3a1cea8b-1c32-593c-96ea-5828d9eaf639` |

**M3 detection evidence:**
- `SYS:m3-detection/70682314-3d9a-5ac6-a908-1fa3be922f47` LOW 2026-09-02T15:22:00+00:00–2026-09-02T15:42:00+00:00; raised `2026-09-02T15:56:04+00:00`; `raised_by_cutoff=True`; 5 readings; peak 1.0°C.
- `SYS:m3-detection/2407bbdf-1ad3-554a-8ad8-ec64d7492113` LOW 2026-09-02T15:52:00+00:00–2026-09-02T18:32:00+00:00; raised `2026-09-02T18:40:47+00:00`; `raised_by_cutoff=True`; 33 readings; peak 0.2°C.

**M3 gap evidence:**
- `SYS:gap/c586362b-4b79-57a9-962a-a37e55f72422` SHORT_GAP 2026-09-02T15:42:00+00:00–2026-09-02T15:52:00+00:00; raised `2026-09-02T15:56:04+00:00`.

### Citation procedure riêng với evidence sensor

- `SOP-EXC@1.0#DELAYED_OCEAN` — claim của draft: Phải tách thời điểm đo và thời điểm nhận; không suy luận nhiệt độ trong khoảng chưa nhận được số liệu.
  - Quote đã lưu/được kiểm: - Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`). - Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó. - Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.
- `SOP-EXC@1.0#SENSOR_UNCERTAINTY` — claim của draft: Advisory ML chỉ là tư vấn; khi thông tin chưa đủ phải nêu thiếu bằng chứng.
  - Quote đã lưu/được kiểm: - Nêu cảnh báo M3/M4 liên quan như bằng chứng riêng biệt, kèm phiên bản và thời điểm. - Điểm ML chỉ là advisory. Không diễn giải điểm số thành quyết định RELEASE hoặc QUARANTINE. - Nếu cảm biến, thời gian hoặc bối cảnh chưa đủ để diễn giải, trả trạng thái thiếu bằng chứng.
- `SOP-EXC@1.0#EVIDENCE_AUDIT` — claim của draft: Không sửa incident hay lịch sử audit; chỉ trích dẫn nguồn và section thực sự được cung cấp.
  - Quote đã lưu/được kiểm: - Liệt kê nguồn hệ thống và section SOP thực sự được cung cấp cho lần giải thích; giữ ID, phiên bản và hash. - Không bịa trích dẫn. Trích dẫn quy trình phải chỉ đúng section và đoạn văn bản trong nguồn đã truy xuất. - Không sửa incident, reading, disposition, custody, outbox hay lịch sử audit.

### Điểm reviewer cần đánh giá

LOW_EXCURSION bị xếp hạng 6/9, ngoài top_k=5. Draft trích DELAYED_OCEAN, SENSOR_UNCERTAINTY, EVIDENCE_AUDIT; chưa có SOP LOW-specific. M3 phát hiện thứ hai kết thúc 18:32Z, nhưng sensor evidence dừng 16:12Z. Không có M4 prediction reference.
- Đọc claim cạnh đúng event_at, received_at, detector/policy evidence; không coi gap hoặc advisory vắng mặt là bằng chứng an toàn.
- Đánh giá riêng SOP citation có hỗ trợ claim cụ thể về thủ tục không; citation check tự động chỉ xác minh ID/quote.

**Kết luận reviewer (chọn một):** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE`

**Reviewer identity/role:** ____________________    **Thời điểm review (UTC):** ____________________

**Rationale và evidence/citation cụ thể:**

____________________________________________________________________________

____________________________________________________________________________

## M6R-016

- Incident `a08f92fa-fc29-5ea6-b27e-3d323f81c77d`; record `b8f6bf55-fd27-400c-9c20-cda186e8e3e8`; incident ref `INC-SIM-S11-J0062-SIM-S11-L0062-TEX-H-20260914T055300Z`.
- Cutoff `2026-11-17T08:27:42Z`; sensor event-time interval `2026-09-14T05:23:00Z` → `2026-09-14T08:23:00Z`; `42` evidence references; SOP `SOP-EXC v1.0`; policy `1.0`.
- Machine status: source `llm`, status `draft`, citation check `passed`, model `gpt-6-luna`, prompt `response_draft/v1`. Human review chưa đánh dấu.

### Claim excerpts từ draft và kiểm tra evidence

**Tóm tắt:**
- Incident nhiệt độ cao của lô SIM-S11-J0062 vẫn OPEN tại cutoff 2026-11-17T08:27:42+00:00. M3 ghi nhận một đợt HIGH đủ thời lượng theo policy POL-CHILL-01 v1.0; khoảng thiếu 07:53–08:03 không được coi là trong ngưỡng. Không có quyết định chất lượng trong evidence.

**Quan sát:**
- Khoảng sensor được khai báo: 2026-09-14 05:23–08:23; khoảng cách lấy mẫu là 5 phút. Tóm tắt có 36 bản ghi, tất cả đều được nhận trễ so với event_at.
- Trong các bản ghi đã nhận trước cutoff, nhiệt độ tăng từ 4.2°C lúc event_at 05:23 (received_at 05:36:10) lên mức cao nhất 11.3°C lúc event_at 07:43 (received_at 07:50:41).
- Bản ghi event_at 07:53, 11.2°C, được nhận lúc 08:06:26; đây là điểm cuối của khoảng incident được nêu trong revision 7.
- Có khoảng thiếu 07:53–08:03, bracketing span 600 giây, trạng thái SHORT_GAP; cảnh báo được raised lúc 08:06:26.

**Kết quả policy/M3:**
- M3 detection 49149ac1-3fd7-5e80-a50f-7e59796ab214 ghi nhận HIGH từ event_at 05:53 đến 07:53, 25 readings, peak 11.3°C và meets_policy_duration=true; raised lúc 08:06:26.
- Policy POL-CHILL-01 v1.0 (hash 73f757e24319791dd6cb8200cf1863aac362d97d6ef32fe01bfa89566b5e0a96) ghi ngưỡng cao >8.0°C liên tục ít nhất 30 phút. Incident revision 7 bao phủ 05:53–07:53 và đang OPEN tại cutoff.
- Một detection M3 khác bắt đầu 08:03, raised lúc 09:51:13—sau cutoff—nên không được xem là phát hiện đã có tại cutoff.

**Yếu tố có thể liên quan:**
- Các bản ghi cho thấy nhiệt độ môi trường tăng và trạng thái cửa được báo là CLOSED; đây chỉ là số liệu đi kèm, không xác nhận nguyên nhân excursion.
- Độ trễ nhận dữ liệu và khoảng thiếu đã được quan sát, nhưng không có bằng chứng độc lập xác nhận nguyên nhân của chúng.

**Bước đề xuất:**
- Chuyển hồ sơ và dữ liệu liên quan cho Quality Officer theo workflow M5 để đánh giá; phần giải thích này không đưa ra quyết định RELEASE/QUARANTINE hoặc thay đổi custody.

**Bằng chứng còn thiếu:**
- Hồ sơ độc lập về tuyến vận chuyển và kết nối/logger để làm rõ độ trễ và khoảng thiếu.
- Đánh giá và disposition chính thức của Quality Officer được ủy quyền.

**Điều chưa biết:**
- Không thể xác định nhiệt độ thực tế trong khoảng thiếu 07:53–08:03; không nội suy và không thể coi thiếu telemetry là an toàn.
- Không có hồ sơ độc lập về tuyến vận chuyển hoặc kết nối để giải thích độ trễ/thiếu dữ liệu.
- Không có disposition M5 tại cutoff; chất lượng sản phẩm và quyết định xử lý lô chưa được xác định.

**Evidence hệ thống:** `SYS:gap/6e280372-7769-581e-ad8b-139e428afca6`; `SYS:incident/a08f92fa-fc29-5ea6-b27e-3d323f81c77d:revision/7`; `SYS:m3-detection/17b5dfaa-d809-518f-bd1a-c2f41efa4dad`; `SYS:m3-detection/49149ac1-3fd7-5e80-a50f-7e59796ab214`; `SYS:policy/POL-CHILL-01@1.0`; toàn bộ source refs, gồm reading refs, nằm trong `raw/m6-quality-api-review-extract-verified.json`.

**Claim → evidence map để reviewer xác nhận:**

| Nhóm claim trong draft | Nguồn cần đối chiếu |
|---|---|
| Sensor facts, event/received time | 36 reading refs trong API extract; các mốc mẫu và từng `event_at`/`received_at` ở bảng bên dưới |
| M3 detector / policy | `SYS:m3-detection/49149ac1-3fd7-5e80-a50f-7e59796ab214`; `SYS:m3-detection/17b5dfaa-d809-518f-bd1a-c2f41efa4dad`; `SYS:policy/POL-CHILL-01@1.0` |
| Incident status/revision | `SYS:incident/a08f92fa-fc29-5ea6-b27e-3d323f81c77d:revision/7`; payload không có disposition M5 reference |
| Khoảng missing/unknown | `SYS:gap/6e280372-7769-581e-ad8b-139e428afca6`; đối chiếu readings hai phía, không suy diễn trong gap |
| M4 advisory | Không có `SYS:m4-prediction` reference trong evidence payload; absence không phải negative prediction |
| SOP bước xử lý | `SOP-EXC@1.0#DELAYED_OCEAN`; `SOP-EXC@1.0#HIGH_EXCURSION`; `SOP-EXC@1.0#MONITORING`; xem claim và quote chính xác ngay dưới đây |


**Mẫu thời gian sensor từ temporal audit (UTC):**

| event_at | received_at | °C | cutoff check | source ref |
|---|---|---:|---|---|
| 2026-09-14T05:23:00+00:00 | 2026-09-14T05:36:10+00:00 | 4.2 | received trước cutoff | `SYS:reading/66051d42-e33c-5b74-8ec6-de3cebab4693` |
| 2026-09-14T05:53:00+00:00 | 2026-09-14T06:06:06+00:00 | 8.3 | received trước cutoff | `SYS:reading/6e7b332d-dbf7-5c1a-9344-358bdfc780f9` |
| 2026-09-14T07:43:00+00:00 | 2026-09-14T07:50:41+00:00 | 11.3 | received trước cutoff | `SYS:reading/088c3b11-1bd4-540d-8073-9b937ac359b1` |
| 2026-09-14T07:53:00+00:00 | 2026-09-14T08:06:26+00:00 | 11.2 | received trước cutoff | `SYS:reading/78222d84-cd04-51b3-b5a4-299efbc6ba57` |
| 2026-09-14T08:03:00+00:00 | 2026-09-14T08:06:26+00:00 | 11.0 | received trước cutoff | `SYS:reading/68146019-28a8-5ed9-b439-4e87bf1cd4c4` |
| 2026-09-14T08:23:00+00:00 | 2026-09-14T08:35:12+00:00 | 10.9 | received trước cutoff | `SYS:reading/a1812e8e-8bf6-5b61-8fd4-37e68b70a0c2` |

**M3 detection evidence:**
- `SYS:m3-detection/49149ac1-3fd7-5e80-a50f-7e59796ab214` HIGH 2026-09-14T05:53:00+00:00–2026-09-14T07:53:00+00:00; raised `2026-09-14T08:06:26+00:00`; `raised_by_cutoff=True`; 25 readings; peak 11.3°C.
- `SYS:m3-detection/17b5dfaa-d809-518f-bd1a-c2f41efa4dad` HIGH 2026-09-14T08:03:00+00:00–2026-09-14T09:33:00+00:00; raised `2026-09-14T09:51:13+00:00`; `raised_by_cutoff=True`; 19 readings; peak 11.4°C.

**M3 gap evidence:**
- `SYS:gap/6e280372-7769-581e-ad8b-139e428afca6` SHORT_GAP 2026-09-14T07:53:00+00:00–2026-09-14T08:03:00+00:00; raised `2026-09-14T08:06:26+00:00`.

### Citation procedure riêng với evidence sensor

- `SOP-EXC@1.0#DELAYED_OCEAN` — claim của draft: Tách thời điểm đo và thời điểm nhận; chỉ dùng bản ghi đã nhận trước cutoff và không kết luận nhiệt độ trong thời gian chưa có số liệu.
  - Quote đã lưu/được kiểm: - Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`). - Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó. - Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.
- `SOP-EXC@1.0#HIGH_EXCURSION` — claim của draft: Diễn giải đúng policy và nêu rõ khoảng thiếu làm gián đoạn chuỗi quan sát; quyết định thuộc Quality Officer.
  - Quote đã lưu/được kiểm: - Tóm tắt các số đo quan sát được, thời điểm đo, thời điểm nhận, khoảng sự kiện và kết quả detector M3. - Đối chiếu đúng policy đang gắn với lô hàng. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức cao khi số đo lớn hơn 8.0 °C liên tục ít nhất 30 phút; các khoảng thiếu làm gián đoạn chuỗi quan sát. - Nếu sự kiện kề khoảng UNKNOWN, nói rõ thời lượng quan sát được là giới hạn dưới; không khẳng định diễn biến trong khoảng trống. - Chuyển phần quyết định cho Quality Officer theo workflow M5.
- `SOP-EXC@1.0#MONITORING` — claim của draft: Không suy rộng kết luận cho thời gian không có số đo; advisory ML nếu có không phải kết luận chất lượng.
  - Quote đã lưu/được kiểm: - Trình bày số đo cùng `event_at` và `received_at`; nêu rõ khoảng dữ liệu được dùng. - Chỉ mô tả là quan sát được khi bản ghi đã được hệ thống nhận trước thời điểm giải thích. - Không suy rộng kết luận cho khoảng thời gian không có số đo. - Tình trạng giám sát hoặc điểm ML là thông tin hỗ trợ, không phải kết luận chất lượng.

### Điểm reviewer cần đánh giá

LỖI THỜI GIAN ĐÃ XÁC NHẬN: draft viết detection M3 thứ hai raised_at=2026-09-14T09:51:13Z là sau cutoff 2026-11-17T08:27:42Z. Thực tế timestamp này ở trước cutoff. Draft append-only không được sửa. QUALITY reviewer đánh giá mức trọng yếu và ảnh hưởng độ tin cậy. Không có M4 prediction reference.
- Đọc claim cạnh đúng event_at, received_at, detector/policy evidence; không coi gap hoặc advisory vắng mặt là bằng chứng an toàn.
- Đánh giá riêng SOP citation có hỗ trợ claim cụ thể về thủ tục không; citation check tự động chỉ xác minh ID/quote.

**Kết luận reviewer (chọn một):** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE`

**Reviewer identity/role:** ____________________    **Thời điểm review (UTC):** ____________________

**Rationale và evidence/citation cụ thể:**

____________________________________________________________________________

____________________________________________________________________________

## M6R-021

- Incident `d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7`; record `49f31638-327f-4a3f-a969-435f1e2936ec`; incident ref `INC-SIM-S11-J0123-SIM-S11-L0123-GAP-20260921T143800Z`.
- Cutoff `2026-11-17T08:27:42Z`; sensor event-time interval `2026-09-21T14:08:00Z` → `2026-09-21T18:08:00Z`; `19` evidence references; SOP `SOP-EXC v1.0`; policy `1.0`.
- Machine status: source `llm`, status `draft`, citation check `passed`, model `gpt-6-luna`, prompt `response_draft/v1`. Human review chưa đánh dấu.

### Claim excerpts từ draft và kiểm tra evidence

**Tóm tắt:**
- Incident DATA_GAP đang OPEN đối với lô SIM-S11-J0123, cảm biến SIM-S11-L0123. Có dữ liệu thiếu từ 2026-09-21T14:38:00Z đến 17:38:00Z và các số đo sau đó ghi nhận nhiệt độ cao; M3 xác nhận phát hiện HIGH theo policy baseline. Không có dự đoán M4 tại cutoff. Đây là mô phỏng; thông tin này không quyết định tình trạng xuất kho.

**Quan sát:**
- Evidence cutoff: 2026-11-17T08:27:42Z; khoảng sensor được cung cấp là 2026-09-21T14:08:00Z–18:08:00Z.
- Các số đo trước khoảng thiếu, từ 14:08 đến 14:38, nằm trong 3.2–3.5 °C. Các bản ghi được nhận trễ so với event_at; ví dụ số đo lúc 14:33 được nhận lúc 14:45:23.
- Không có số đo trong khoảng 14:38–17:38, span 180 phút; trạng thái là UNKNOWN_REVIEW_REQUIRED, không được tính là trong ngưỡng.
- Sau khoảng thiếu, các số đo từ 17:38 đến 18:08 nằm trong 12.0–12.3 °C; số đo lúc 17:38 được nhận lúc 17:44:39. Tất cả 14 readings trong summary được đánh dấu delayed.

**Kết quả policy/M3:**
- Theo POL-CHILL-01 phiên bản 1.0, ngưỡng cao là trên 8.0 °C liên tục ít nhất 30 phút; đây là quy tắc mô phỏng, không phải tiêu chuẩn an toàn pháp quy.
- M3 ghi nhận phát hiện HIGH, nguồn POLICY_BASELINE, gồm 32 readings, từ 2026-09-21T17:38:00Z đến 20:13:00Z, peak 12.5 °C và meets_policy_duration=true. Phát hiện được ghi nhận lúc 20:29:48Z.
- Đầu khoảng phát hiện kề khoảng UNKNOWN; thời lượng quan sát liên tục xung quanh khoảng thiếu là giới hạn dưới. Không thể kết luận diễn biến nhiệt độ trong khoảng thiếu.

**Advisory M4:**
- Không có dự đoán advisory M4 trong evidence tại cutoff.

**Bước đề xuất:**
- Chuyển việc đánh giá incident cho Quality Officer theo workflow M5; phần giải thích này không đưa ra quyết định RELEASE/QUARANTINE hoặc thay đổi custody/workflow.

**Bằng chứng còn thiếu:**
- Bằng chứng bổ sung có thể làm rõ diễn biến trong khoảng thiếu và nguyên nhân mất dữ liệu; hiện chưa có trong evidence được cung cấp.

**Điều chưa biết:**
- Nhiệt độ thực tế trong khoảng 14:38–17:38 không được biết từ evidence; không thể nội suy từ các số đo hai phía.
- Nguyên nhân của khoảng mất dữ liệu và của các số đo cao chưa được xác định.
- Không có disposition M5 trong evidence được cung cấp.

**Evidence hệ thống:** `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`; `SYS:incident/d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7:revision/1`; `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`; `SYS:policy/POL-CHILL-01@1.0`; toàn bộ source refs, gồm reading refs, nằm trong `raw/m6-quality-api-review-extract-verified.json`.

**Claim → evidence map để reviewer xác nhận:**

| Nhóm claim trong draft | Nguồn cần đối chiếu |
|---|---|
| Sensor facts, event/received time | 14 reading refs trong API extract; các mốc mẫu và từng `event_at`/`received_at` ở bảng bên dưới |
| M3 detector / policy | `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`; `SYS:policy/POL-CHILL-01@1.0` |
| Incident status/revision | `SYS:incident/d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7:revision/1`; payload không có disposition M5 reference |
| Khoảng missing/unknown | `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`; đối chiếu readings hai phía, không suy diễn trong gap |
| M4 advisory | Không có `SYS:m4-prediction` reference trong evidence payload; absence không phải negative prediction |
| SOP bước xử lý | `SOP-EXC@1.0#DELAYED_OCEAN`; `SOP-EXC@1.0#HIGH_EXCURSION`; xem claim và quote chính xác ngay dưới đây |


**Mẫu thời gian sensor từ temporal audit (UTC):**

| event_at | received_at | °C | cutoff check | source ref |
|---|---|---:|---|---|
| 2026-09-21T14:33:00+00:00 | 2026-09-21T14:45:23+00:00 | 3.2 | received trước cutoff | `SYS:reading/c2e1db9b-0ab2-55da-8005-ba99065ae524` |
| 2026-09-21T17:38:00+00:00 | 2026-09-21T17:44:39+00:00 | 12.3 | received trước cutoff | `SYS:reading/7e5b583a-a1ab-5893-be01-be43101a39b0` |
| 2026-09-21T18:08:00+00:00 | 2026-09-21T18:14:19+00:00 | 12.0 | received trước cutoff | `SYS:reading/200b98e8-a924-59ef-920d-46f730807081` |

**M3 detection evidence:**
- `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a` HIGH 2026-09-21T17:38:00+00:00–2026-09-21T20:13:00+00:00; raised `2026-09-21T20:29:48+00:00`; `raised_by_cutoff=True`; 32 readings; peak 12.5°C.

**M3 gap evidence:**
- `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc` UNKNOWN_REVIEW_REQUIRED 2026-09-21T14:38:00+00:00–2026-09-21T17:38:00+00:00; raised `2026-09-21T17:44:39+00:00`.

### Citation procedure riêng với evidence sensor

- `SOP-EXC@1.0#DELAYED_OCEAN` — claim của draft: Phân biệt thời điểm đo với thời điểm nhận; không kết luận nhiệt độ trong thời gian chưa nhận được số liệu.
  - Quote đã lưu/được kiểm: - Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`). - Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó. - Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.
- `SOP-EXC@1.0#HIGH_EXCURSION` — claim của draft: Tóm tắt số đo và M3; khoảng thiếu làm gián đoạn chuỗi quan sát và khi kề UNKNOWN, thời lượng quan sát được là giới hạn dưới.
  - Quote đã lưu/được kiểm: - Tóm tắt các số đo quan sát được, thời điểm đo, thời điểm nhận, khoảng sự kiện và kết quả detector M3. - Đối chiếu đúng policy đang gắn với lô hàng. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức cao khi số đo lớn hơn 8.0 °C liên tục ít nhất 30 phút; các khoảng thiếu làm gián đoạn chuỗi quan sát. - Nếu sự kiện kề khoảng UNKNOWN, nói rõ thời lượng quan sát được là giới hạn dưới; không khẳng định diễn biến trong khoảng trống. - Chuyển phần quyết định cho Quality Officer theo workflow M5.

### Điểm reviewer cần đánh giá

Khoảng UNKNOWN 14:38–17:38Z không có số đo và không chứng minh nhiệt độ an toàn. M3 detection được raised 20:29:48Z trước cutoff. Không có M4 prediction reference; sự vắng mặt không phải negative prediction.
- Đọc claim cạnh đúng event_at, received_at, detector/policy evidence; không coi gap hoặc advisory vắng mặt là bằng chứng an toàn.
- Đánh giá riêng SOP citation có hỗ trợ claim cụ thể về thủ tục không; citation check tự động chỉ xác minh ID/quote.

**Kết luận reviewer (chọn một):** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE`

**Reviewer identity/role:** ____________________    **Thời điểm review (UTC):** ____________________

**Rationale và evidence/citation cụ thể:**

____________________________________________________________________________

____________________________________________________________________________

## M6R-036

- Incident `d3bce4f3-877c-5f29-a8ff-8e97a57ec6af`; record `1c3df718-3f6e-4340-9395-79272f7f88f1`; incident ref `INC-SIM-S11-J0009-SIM-S11-L0009-TEX-L-20260915T235700Z`.
- Cutoff `2026-11-17T08:27:42Z`; sensor event-time interval `2026-09-15T23:27:00Z` → `2026-09-16T00:47:00Z`; `22` evidence references; SOP `SOP-EXC v1.0`; policy `1.0`.
- Machine status: source `llm`, status `draft`, citation check `passed`, model `gpt-6-luna`, prompt `response_draft/v1`. Human review chưa đánh dấu.

### Claim excerpts từ draft và kiểm tra evidence

**Tóm tắt:**
- Incident nhiệt độ thấp của lô SIM-S11-J0009, cảm biến SIM-S11-L0009, đang OPEN tại cutoff 2026-11-17T08:27:42Z. Bằng chứng ghi nhận các số đo dưới ngưỡng 2.0°C và M3 xác nhận một khoảng LOW đáp ứng thời lượng policy. Không có tư vấn M4 hoặc disposition M5 tại cutoff. Đây không phải quyết định RELEASE/QUARANTINE.

**Quan sát:**
- Khoảng sensor được cung cấp: 2026-09-15T23:27:00Z–2026-09-16T00:47:00Z; 17/17 bản ghi có received_at không sau cutoff. Tất cả các bản ghi đều trễ so với event_at.
- Các số đo nằm trong khoảng 1.7–2.1°C; những giá trị dưới 2.0°C được ghi tại 23:27, 23:37, 23:57, 00:02, 00:07, 00:12 và 00:17Z. Door state được ghi CLOSED.
- Incident extent được ghi là 2026-09-15T23:57:00Z–2026-09-16T00:17:00Z; incident mở lúc 00:15:30Z, revision 2 được nâng lúc 00:30:08Z.

**Kết quả policy/M3:**
- Policy gắn với dữ liệu là POL-CHILL-01 v1.0, cho nhóm CHILLED_2_8C; ngưỡng thấp ghi là 2.0°C và thời lượng tối thiểu cho excursion thấp là 15 phút.
- M3 có ba phát hiện LOW: hai phát hiện trước đó không đạt thời lượng policy; phát hiện 23:57–00:17Z, gồm 5 readings với peak_c 1.7, đạt thời lượng policy. Đây là kết quả detector, không phải đánh giá an toàn sản phẩm.
- Policy là quy tắc mô phỏng dùng cho giảng dạy, không phải tiêu chuẩn an toàn quy định.

**Advisory M4:**
- Không có dự đoán advisory M4 trong evidence tại cutoff.

**Yếu tố có thể liên quan:**
- Nhiệt độ môi trường ghi nhận âm trong các bản ghi; đây chỉ là yếu tố có thể liên quan, chưa xác nhận là nguyên nhân của excursion.

**Bước đề xuất:**
- Quality Officer được ủy quyền xử lý quyết định theo workflow M5; phần giải thích này không thay đổi custody hoặc trạng thái workflow.

**Bằng chứng còn thiếu:**
- Đánh giá/định đoạt của Quality Officer nếu cần kết luận nghiệp vụ.
- Bằng chứng bổ sung về nguyên nhân hoặc điều kiện bảo quản nếu cần xác định nguyên nhân incident.

**Điều chưa biết:**
- Số liệu đến trễ; không thể dùng thời điểm nhận để khẳng định hệ thống đã biết số đo tại thời điểm event_at.
- Không thể suy ra nhiệt độ giữa các lần đo hoặc ngoài khoảng sensor được cung cấp; không nội suy và không coi khoảng thiếu telemetry là an toàn.
- Nguyên nhân của excursion và tình trạng sản phẩm chưa được evidence xác nhận.

**Evidence hệ thống:** `SYS:incident/d3bce4f3-877c-5f29-a8ff-8e97a57ec6af:revision/2`; `SYS:m3-detection/22a943e2-e608-5b35-b0bf-538d1cbeca68`; `SYS:m3-detection/9989e556-2334-5f31-8fd2-e8a82b97652d`; `SYS:m3-detection/f82ab980-7e40-5145-b8a8-bc11e44ab736`; `SYS:policy/POL-CHILL-01@1.0`; toàn bộ source refs, gồm reading refs, nằm trong `raw/m6-quality-api-review-extract-verified.json`.

**Claim → evidence map để reviewer xác nhận:**

| Nhóm claim trong draft | Nguồn cần đối chiếu |
|---|---|
| Sensor facts, event/received time | 17 reading refs trong API extract; các mốc mẫu và từng `event_at`/`received_at` ở bảng bên dưới |
| M3 detector / policy | `SYS:m3-detection/22a943e2-e608-5b35-b0bf-538d1cbeca68`; `SYS:m3-detection/f82ab980-7e40-5145-b8a8-bc11e44ab736`; `SYS:m3-detection/9989e556-2334-5f31-8fd2-e8a82b97652d`; `SYS:policy/POL-CHILL-01@1.0` |
| Incident status/revision | `SYS:incident/d3bce4f3-877c-5f29-a8ff-8e97a57ec6af:revision/2`; payload không có disposition M5 reference |
| Khoảng missing/unknown | không có M3 gap ref; đối chiếu readings hai phía, không suy diễn trong gap |
| M4 advisory | Không có `SYS:m4-prediction` reference trong evidence payload; absence không phải negative prediction |
| SOP bước xử lý | `SOP-EXC@1.0#DELAYED_OCEAN`; `SOP-EXC@1.0#SENSOR_UNCERTAINTY`; `SOP-EXC@1.0#HIGH_EXCURSION`; xem claim và quote chính xác ngay dưới đây |


**Mẫu thời gian sensor từ temporal audit (UTC):**

| event_at | received_at | °C | cutoff check | source ref |
|---|---|---:|---|---|
| 2026-09-15T23:27:00+00:00 | 2026-09-15T23:30:22+00:00 | 1.7 | received trước cutoff | `SYS:reading/8a02e2c2-86ad-5a5f-9fb9-19cf0c1988fb` |
| 2026-09-15T23:57:00+00:00 | 2026-09-15T23:59:25+00:00 | 1.9 | received trước cutoff | `SYS:reading/9f2f3a62-9ff4-5189-b27d-3baa95e2813c` |
| 2026-09-16T00:17:00+00:00 | 2026-09-16T00:30:08+00:00 | 1.9 | received trước cutoff | `SYS:reading/8684fe95-06ff-5727-9052-ee3700293d78` |
| 2026-09-16T00:22:00+00:00 | 2026-09-16T00:30:08+00:00 | 2.0 | received trước cutoff | `SYS:reading/3855e140-5ba5-5a36-b5ea-e2b910366095` |

**M3 detection evidence:**
- `SYS:m3-detection/22a943e2-e608-5b35-b0bf-538d1cbeca68` LOW 2026-09-15T23:22:00+00:00–2026-09-15T23:27:00+00:00; raised `2026-09-15T23:44:05+00:00`; `raised_by_cutoff=True`; 2 readings; peak 1.7°C.
- `SYS:m3-detection/f82ab980-7e40-5145-b8a8-bc11e44ab736` LOW 2026-09-15T23:37:00+00:00–2026-09-15T23:37:00+00:00; raised `2026-09-15T23:44:05+00:00`; `raised_by_cutoff=True`; 1 readings; peak 1.8°C.
- `SYS:m3-detection/9989e556-2334-5f31-8fd2-e8a82b97652d` LOW 2026-09-15T23:57:00+00:00–2026-09-16T00:17:00+00:00; raised `2026-09-16T00:30:08+00:00`; `raised_by_cutoff=True`; 5 readings; peak 1.7°C.

### Citation procedure riêng với evidence sensor

- `SYS:policy/POL-CHILL-01@1.0` — claim của draft: Định danh policy, phiên bản, ngưỡng và thời lượng excursion thấp; policy có tuyên bố giới hạn là quy tắc mô phỏng.
  - Quote đã lưu/được kiểm: [không có quote trong citation]
- `SYS:m3-detection/9989e556-2334-5f31-8fd2-e8a82b97652d` — claim của draft: M3 ghi nhận phát hiện LOW từ 23:57 đến 00:17Z, đạt thời lượng policy, với 5 readings và peak 1.7°C.
  - Quote đã lưu/được kiểm: [không có quote trong citation]
- `SOP-EXC@1.0#DELAYED_OCEAN` — claim của draft: Phân biệt event_at với received_at và không kết luận nhiệt độ trong thời gian chưa nhận được số liệu.
  - Quote đã lưu/được kiểm: - Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`).
- `SOP-EXC@1.0#SENSOR_UNCERTAINTY` — claim của draft: Advisory không thay thế quyết định RELEASE hoặc QUARANTINE; thiếu bằng chứng cần được nêu rõ.
  - Quote đã lưu/được kiểm: - Điểm ML chỉ là advisory. Không diễn giải điểm số thành quyết định RELEASE hoặc QUARANTINE.
- `SOP-EXC@1.0#HIGH_EXCURSION` — claim của draft: Quyết định được chuyển cho Quality Officer theo workflow M5.
  - Quote đã lưu/được kiểm: - Chuyển phần quyết định cho Quality Officer theo workflow M5.

### Điểm reviewer cần đánh giá

QUALITY_REVIEW bị xếp hạng 9/9, ngoài top_k=5. Có cited HIGH_EXCURSION nhưng incident là LOW. Reviewer cần xác nhận section thực sự hỗ trợ quyết định QUALITY. Draft không có M4 prediction reference; việc thiếu M4 không phải dự đoán an toàn.
- Đọc claim cạnh đúng event_at, received_at, detector/policy evidence; không coi gap hoặc advisory vắng mặt là bằng chứng an toàn.
- Đánh giá riêng SOP citation có hỗ trợ claim cụ thể về thủ tục không; citation check tự động chỉ xác minh ID/quote.

**Kết luận reviewer (chọn một):** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE`

**Reviewer identity/role:** ____________________    **Thời điểm review (UTC):** ____________________

**Rationale và evidence/citation cụ thể:**

____________________________________________________________________________

____________________________________________________________________________

## Kiểm tra chung trước khi ký

- [ ] `event_at` và `received_at` được mô tả riêng; thời điểm nhận sau cutoff không được dùng như thông tin đã biết trước cutoff.
- [ ] Không có gap/delayed telemetry nào diễn đạt thành nhiệt độ an toàn.
- [ ] M3 facts/revisions đúng với reference, time window và cutoff.
- [ ] M4 prediction được tách advisory; không có record không có nghĩa score âm/an toàn.
- [ ] SOP v1.0 effective 2026-11-14 được gọi là hướng dẫn hiện hành tại cutoff, không phải quy trình đã hiệu lực cho sự kiện tháng 9.
- [ ] Procedural citation có semantic support cho claim gắn với nó.
- [ ] Chỉ QUALITY được ủy quyền quyết định RELEASE/QUARANTINE; draft không đổi custody/warehouse workflow.

**Trạng thái tổng:** `[ ] PASS` · `[ ] FAIL` · `[ ] NEEDS_MORE_EVIDENCE` — chưa được tự động chọn.
**Reviewer identity/role:** ____________________    **Thời điểm:** ____________________
**Rationale tổng:** ____________________________________________________________
