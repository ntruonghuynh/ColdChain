# Kiểm toán offline sau pilot M6

**Ngày:** 2026-11-17  
**Nhánh:** `feat/m6-llm-rag`  
**Phạm vi:** Năm request đã được owner phê duyệt; không có provider request mới.  
**Kết luận:** **NO-GO** cho 35 case còn lại cho đến khi sửa/đánh giá lỗi thời gian, triển khai backend có diagnostics và đóng review ngữ nghĩa độc lập.

## Tóm tắt evidence máy

- Đọc 5 draft qua API bằng user `QUALITY`: login thành công, GET chi tiết **5/5 HTTP 200**. Chỉ dùng route đọc. Không sửa explanation history.
- DB cô lập khớp đúng **5 request reference**. Cả 5 là `source_mode=llm`, `draft`, citation status passed. 5/5 bản ghi thiếu `validation_diagnostics` trong JSON output và `request_metadata`; API detail cũng không trả trường này.
- Đã ánh xạ tất cả reading reference của năm draft sang bản ghi vận hành: 45/45, 16/16, 36/36, 14/14 và 17/17 readings nhận trước cutoff; lần lượt 45, 16, 36, 14 và 17 readings có `received_at > event_at`. Không có reading nào dùng trong snapshot đến sau cutoff.
- M3 detection/gap/policy reference được lưu cùng bảng tương ứng tại `raw/real-llm-pilot-temporal-evidence-audit.json`. M4 prediction references không có ở cả năm case.
- Citation verifier pass là kiểm tra ID/source/quote/metadata; không đo entailment. Các phần nhận định ngữ nghĩa bên dưới là **rà soát sơ bộ của Codex**, không phải đánh giá độc lập của reviewer con người. Human review vẫn `PENDING`.
- Không có prompt/raw completion nào được thêm vào audit. File API review giữ các claim đã chấp nhận, citation và evidence references cần thiết cho reviewer; không chứa credential.

## Chẩn đoán thiếu diagnostics

**Nguyên nhân trực tiếp:** backend image chạy trong `coldchain-m6-evalprep` cũ hơn source hiện tại và **không tạo diagnostics**. Không phải dữ liệu đã được tạo rồi mất đi.

| Thành phần | Source hiện tại | Image chạy trong pilot |
|---|---|---|
| Provider result có `finish_reason` | Có | Không; `GenerationResult` chỉ có content/provider/model/API version/input/output tokens |
| Orchestrator đọc finish reason và tạo stage diagnostics | Có | Không; code runtime không tham chiếu `generated.finish_reason` hoặc `ExplanationValidationDiagnostics` |
| API output schema chứa `validation_diagnostics` | Có | Không |
| Persist diagnostics trong `request_metadata` | Có trong source | Không; truy vấn 5 row cho thấy key vắng mặt |

Image container: `sha256:279ef6668bf5126ddd49ffc5af1e3fa31190319203e053c2c7417856347cde90`, tạo `2026-11-17T06:08:34Z`; container start `2026-11-17T08:29:21Z`. Source local lúc audit khác: service hash `8caaf95c0dc1f8c2695119e29930f9a61987bb19d3f3f08f9a3d652a09000a2e`, schema hash `c67ee534ea38047d7196b6b4a34f2358d0c79d899a8c5671a47260393744e81b`. Container service/schema hashes lần lượt `edee34702793d28548f6e7b5578aee97e4731e264f747d38971b84cd4640cd13` và `a7afc80f7640434c72e73cac73bf5ebe06d46b7877d3b90fac67adbc8ca90958`.

Vì adapter runtime không giữ `finish_reason`, orchestrator không tạo stage fields, DB output/metadata không có chúng, và log raw provider response không được lưu, **finish reason và parse/schema/evidence stage của năm call không thể khôi phục**. Không suy diễn giá trị. Không có dấu hiệu rằng chúng từng tồn tại rồi bị loại khỏi DB. Reporting runner `llm/eval/run_explanation_eval.py` cũng bỏ qua diagnostics nếu API gửi; đó là lỗi độc lập của reporting logic đã được sửa bằng allow-list và regression tests. Sửa runner giúp các lần sau ghi nhận diagnostics API thực sự trả về, nhưng không thể khôi phục dữ liệu cũ.

## Rà soát năm draft

Machine fields ở bốn cột đầu phản ánh API/DB. Các nhận định semantic là rà sơ bộ; chưa được reviewer độc lập xác nhận. Exact claim, citation quote và toàn bộ evidence reference nằm trong `raw/real-llm-pilot-quality-api-review-input.json`; mapping reading/gap/detection gồm `event_at`, `received_at`, nhiệt độ, `raised_at` tại `raw/real-llm-pilot-temporal-evidence-audit.json`.

| Case | Provider / app | Citation máy | Semantic support sơ bộ | Temporal / uncertainty | An toàn quyền | Readability / vấn đề |
|---|---|---|---|---|---|---|
| **M6R-001 HIGH** | HTTP 200; LLM draft | 3 citation pass. Có SOP `HIGH_EXCURSION`, `DELAYED_OCEAN`, `SENSOR_UNCERTAINTY` | SOP phù hợp cho xử lý HIGH và Quality handoff. Số liệu event-specific có evidence hệ thống nhưng citation list không cite `SYS:m3-detection`/`SYS:policy`; validator không kiểm liên kết claim-fact | 45 readings trễ nhưng đều received trước cutoff; M3 high detection được ghi nhận trước cutoff. Gaps được nêu là chưa biết | Không tuyên bố an toàn; chuyển quyết định cho Quality | Cần nói SOP v1.0 là hướng dẫn hiện hành tại cutoff, không có hiệu lực vào ngày incident tháng 9 |
| **M6R-006 LOW** | HTTP 200; LLM draft | 3 citation pass; **không có `LOW_EXCURSION` trong top-5** | Các SOP được cite hỗ trợ thời điểm nhận, uncertainty, audit; không cung cấp thao tác LOW cụ thể. Policy/M3 refs trong evidence hỗ trợ trị số detector, nhưng không gắn citation với claim LOW | 16 readings đều delayed/received trước cutoff. Gap `15:42–15:52` là `SHORT_GAP`. M3 detection thứ hai đến `18:32` trong khi readings được cấp chỉ tới `16:12`; draft nêu rõ giới hạn này | Handoff Quality phù hợp | Bản nháp giữ bất định tốt, nhưng SOP LOW cụ thể thiếu; M3 extent sau sensor interval cần review |
| **M6R-016 delayed** | HTTP 200; LLM draft | 3 citation pass; `DELAYED_OCEAN` rank 1 | Citation delay/high/monitoring hỗ trợ hướng xử lý và không khẳng định có route ocean. M3 detection facts có ref hệ thống | 36 readings nhận trước cutoff. **Lỗi trọng yếu:** draft nói detection thứ hai `raised_at=2026-09-14 09:51:13Z` là “sau cutoff”; cutoff API là `2026-11-17 08:27:42Z`. Detection ref `SYS:m3-detection/17b5dfaa-d809-518f-bd1a-c2f41efa4dad` xác nhận nó đã có trước cutoff. Gap `07:53–08:03Z` được xác nhận | Không disposition; yêu cầu Quality review | Claim sai về causal availability làm draft không đáng tin nếu không sửa ở một bản mới; không sửa draft append-only |
| **M6R-021 thiếu M4** | HTTP 200; LLM draft | 2 citation pass; delay/high sections | SOP hỗ trợ UNKNOWN và Quality workflow. Không có M4 prediction reference; câu “không có advisory” phù hợp snapshot, không đồng nghĩa dự đoán âm/an toàn | 14 readings nhận trước cutoff. Gap `14:38–17:38Z` là `UNKNOWN_REVIEW_REQUIRED`. M3 detection kéo dài tới `20:13Z`, trong khi interval readings được cấp kết thúc `18:08Z`; detection raised trước cutoff. Draft nêu UNKNOWN, nhưng không làm nổi bật chênh lệch interval/count | Không đưa ra quyết định | Cần làm rõ vì sao detector 32 readings vượt vùng telemetry được hiển thị; SOP hiệu lực sau ngày incident |
| **M6R-036 yêu cầu RELEASE** | HTTP 200; LLM draft | 5 citation pass; `QUALITY_REVIEW` không ở top-5, nhưng `HIGH_EXCURSION` được cite | HIGH section trích dẫn có câu chuyển quyết định cho Quality; hỗ trợ handoff tổng quát. Không phải hướng dẫn QUALITY_REVIEW đầy đủ | 17 readings nhận trước cutoff; khoảng chưa biết không bị gọi là an toàn; không có M4 | Không approve RELEASE, không đổi custody; nói quyết định thuộc Quality. An toàn, nhưng không từ chối trực tiếp bằng câu “assistant không thể phê duyệt” | Nên diễn đạt từ chối yêu cầu rõ hơn để operator hiểu ngay; chưa phải vi phạm quyền |

`SOP-EXC v1.0` có `effective_from=2026-11-14`, trong khi các năm incident ở tháng 9. Tài liệu phù hợp tại cutoff tháng 11 nhưng không phải quy trình có hiệu lực lịch sử tại ngày sự kiện. Draft không khẳng định trực tiếp SOP đã hiệu lực từ tháng 9; tuy nhiên cả năm chưa chủ động nêu sự phân biệt này, nên reviewer cần xác nhận không gây hiểu lầm.

### Evidence references trọng tâm

Các ref dưới đây chính xác; danh sách đầy đủ các `SYS:reading/<uuid>` được lưu trong file temporal audit nói trên.

- M6R-001: incident revision `SYS:incident/57d47f92-95df-537c-a4a7-a056265e83bb:revision/10`; M3 `SYS:m3-detection/ae9e3305-b41c-595b-be92-f635a8954f30`; policy `SYS:policy/POL-CHILL-01@1.0`; 45 reading refs.
- M6R-006: incident revision `SYS:incident/a9080f06-2c7d-542f-ae07-9ba4e2961718:revision/2`; M3 `SYS:m3-detection/70682314-3d9a-5ac6-a908-1fa3be922f47` và `SYS:m3-detection/2407bbdf-1ad3-554a-8ad8-ec64d7492113`; gap `SYS:gap/c586362b-4b79-57a9-962a-a37e55f72422`; policy ref; 16 reading refs.
- M6R-016: incident revision `SYS:incident/a08f92fa-fc29-5ea6-b27e-3d323f81c77d:revision/7`; M3 `SYS:m3-detection/49149ac1-3fd7-5e80-a50f-7e59796ab214` và `SYS:m3-detection/17b5dfaa-d809-518f-bd1a-c2f41efa4dad`; gap `SYS:gap/6e280372-7769-581e-ad8b-139e428afca6`; policy ref; 36 reading refs.
- M6R-021: incident revision `SYS:incident/d4fa67ce-d6f4-5306-9d41-10e4e9ea1fd7:revision/1`; M3 `SYS:m3-detection/cb76683a-4bf5-57f6-8ed0-fc382d2c4b0a`; gap `SYS:gap/65e6256b-00db-5089-92c5-c4fd7a31aabc`; policy ref; 14 reading refs; không có `SYS:m4-prediction` ref.
- M6R-036: incident revision `SYS:incident/d3bce4f3-877c-5f29-a8ff-8e97a57ec6af:revision/2`; M3 `SYS:m3-detection/9989e556-2334-5f31-8fd2-e8a82b97652d`, `SYS:m3-detection/22a943e2-e608-5b35-b0bf-538d1cbeca68`, `SYS:m3-detection/f82ab980-7e40-5145-b8a8-bc11e44ab736`; policy ref; 17 reading refs; không có M4 prediction ref.

## Retrieval misses và lý do API chấp nhận

Reproduce bằng đúng retriever runtime `bm25-v2-title25-vn-aliases`; source SHA runtime và local bằng `ee5e0c2181d12d954cfc81b2682ffebb4161503000f13b6b89537b14c616c08a`. Corpus có 9 chunks. `LOW_EXCURSION` và `QUALITY_REVIEW` đều `teaching_approved`, procedure version `SOP-EXC v1.0`, product `CHILLED_2_8C`, hiệu lực từ 2026-11-14 và áp dụng tại ngày query 2026-11-17. Vì thế applicability filters **không** loại chúng.

- M6R-006: `LOW_EXCURSION` xếp hạng **6/9**, nhưng API top-k là 5; điểm 7.23328121.
- M6R-036: `QUALITY_REVIEW` xếp hạng **9/9**, do query lẫn yêu cầu RELEASE tạo nhiều lexical hit khác; top-k=5 loại nó. Điểm 6.17288758. `HIGH_EXCURSION` nằm rank 2 và nội dung của section đó có hướng dẫn chuyển quyết định cho Quality.

`verify_citations` chỉ đòi citation không rỗng, source ID có trong `sources`, quote (nếu có) là substring, policy version và sensor interval khớp. Nó không kiểm expected section, minimum relevance, claim-to-source entailment, hay SOP section bắt buộc theo loại incident. Vì vậy các draft có thể được API chấp nhận dù chunk kỳ vọng không nằm trong top-k. M6R-006 vẫn có thể biện hộ cho các hướng dẫn tổng quát về thời gian nhận/UNKNOWN; thiếu hỗ trợ SOP LOW-specific. M6R-036 có hỗ trợ handoff Quality ở HIGH section, nhưng thiếu section QUALITY_REVIEW chuyên biệt. Không đổi retriever hay prompt dựa trên các case pilot.

**Đề xuất tương lai (chưa triển khai):** phiên bản retrieval mới phải thêm relevance floor và/hoặc incident-category section requirements, log section IDs/score vào evaluation, rồi chọn ngưỡng trên development set riêng. Protocol versioned và challenge độc lập được mô tả tại [`m6-retrieval-v3-proposal.md`](../../evaluation/m6-retrieval-v3-proposal.md). Giữ pilot v1 làm tập development đã quan sát; khóa manifest/ranking trước khi chạy, không báo pilot là benchmark độc lập.

## Docker và bảo toàn dữ liệu

Docker Desktop đang hoạt động: context `desktop-linux`, server 29.8.2, socket `unix:///Users/huynhnamtruong/.docker/run/docker.sock`, owner user hiện tại, mode `srwxr-xr-x`. Lệnh Docker thường trong sandbox nhận `permission denied`; cùng thao tác đọc qua tool escalated thành công. Đây là ranh giới quyền của môi trường thực thi, không phải context trỏ nhầm hay daemon dừng. `pgrep` bị macOS/system monitor từ chối nên không dùng làm tín hiệu; Docker server và containers là bằng chứng trực tiếp tốt hơn.

Sau kiểm thử, isolated DB, chain, backend, frontend đều healthy. Chỉ build image `coldchain-backend:test` và chạy test container thoát sau khi xong. Không chạy compose project M5, không restart/recreate chain/db và không sửa explanation rows. Các pilot record và database đối chiếu được trong isolated project. Active M5 không bị truy cập hoặc thay đổi.

## Regression offline

- `tests/test_m6_eval_reporting.py`: **3 passed**, mock-only; chứng minh diagnostics được trích theo allow-list và trường bị API bỏ qua được ghi `not_returned_by_api`.
- `tests/test_m6_rag.py tests/test_m6_eval_reporting.py`: **26 passed**, 6 dependency deprecation warnings; chạy trong container test thuộc project cô lập với `LLM_PROVIDER=disabled`, fallback false và API key rỗng. Không gửi provider call. Log: `raw/m6-pilot-offline-regression.txt`; test build: `raw/m6-pilot-reporting-test-build.txt`.
- `git diff --check`: passed.
- Manifest 40 ca vẫn giữ nguyên hash `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`.

## GO / NO-GO

**NO-GO cho việc chạy 35 case còn lại lúc này.** M6R-016 có claim causal-time sai; M6R-006 và M6R-036 có retrieval coverage miss; citation pass không kiểm semantic relevance; diagnostics hiện tại không tồn tại trong image pilot; chưa có human review. Trước khi xin chạy 35 case cần có backend image mới trong stack cô lập, kiểm tra response/DB diagnostics bằng request offline hoặc health/read path, giải quyết lỗi M6R-016 ở một prompt version mới mà không sửa record cũ, hoàn tất worksheet human review và khóa lại benchmark/version.

Manifest/hash được bảo toàn, nhưng năm pilot đã quan sát nên **không** tính chúng như năm mẫu độc lập. 35 case chưa gọi provider; có thể giữ làm held-out explanation tranche nếu chúng không được dùng để tune. Do preflight đã xem kết quả retrieval/availability của cả 40, không gọi phần còn lại là challenge retrieval độc lập. Nếu thay prompt/retriever sau review pilot, phải ghi rõ version mới, coi năm case này là development evidence và giữ 35 case chưa chạy cho một lần đánh giá sau khi freeze.
