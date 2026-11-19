# Hướng dẫn sử dụng ColdChain

ColdChain là ứng dụng giảng dạy với hành trình và cảm biến mô phỏng. Các giới hạn nhiệt độ dưới đây là policy trong phần mềm, không phải tiêu chuẩn pháp lý. Thiếu dữ liệu luôn là `UNKNOWN`, không phải bằng chứng hàng hóa an toàn.

## Đăng nhập và quyền

Mở `http://127.0.0.1:3000/login` (thay cổng nếu đã đổi). Nhập username/password. Với database mới đã bật local demo mode: `quality/123`, `warehouse/123`, `carrier/123`, `shipper/123`, `admin/123`. Đầu trang hiển thị tên và role cùng nút Sign out. Token Bearer chỉ lưu trong bộ nhớ trình duyệt; reload có thể yêu cầu đăng nhập lại. Sign out xóa phiên hiện tại.

`401 Unauthorized` nghĩa là chưa đăng nhập hoặc phiên hết hạn; đăng nhập lại. `403 Forbidden` nghĩa là đã xác thực nhưng role không được phép. Việc ẩn nút trên UI không thay thế kiểm tra quyền ở backend. Chỉ `QUALITY` quyết định disposition. `WAREHOUSE` thực hiện physical release riêng sau khi backend xác nhận QUALITY RELEASE và prerequisite. `ADMIN` được dùng thao tác reconciliation/verify audit dành riêng.

## Tổng quan các màn hình

| Trang | Đường dẫn | Vai trò phù hợp |
|---|---|---|
| Overview | `/` | Mọi người |
| Shipments | `/shipments` | Mọi người |
| Temperature Monitoring | `/temperature` | Mọi người |
| Excursion Queue | `/excursions` | Mọi người |
| Incident Details | `/incidents/:incidentId` | Mọi người; một số thao tác theo role |
| Quality Review | `/quality-review` | Đọc cho người đã đăng nhập; disposition chỉ QUALITY |
| Audit History | `/audit` | Người đã đăng nhập; một số kiểm tra chỉ ADMIN |
| System Settings | `/settings` | Mọi người |

### Overview

**Mục đích:** tóm tắt trạng thái hệ thống. Các ô cho biết kết nối API, trạng thái database và migration, số shipment, quyền release theo role, policy đang hoạt động và nhóm tính năng được backend công bố. Đây là chỉ báo service/readiness; một service healthy không chứng minh mọi workflow đã có dữ liệu hoặc đã được end-to-end xác minh.

**Cách dùng:** mở `/`, đọc API/database trước, rồi chọn Shipments hoặc Temperature Monitoring. Kỳ vọng có trạng thái kết nối và phiên bản migration. Trên DB mới, số shipment có thể bằng 0 cho tới khi nhập fixture. Lỗi API/network thường xuất hiện dưới dạng unavailable; kiểm tra `/api/health` và Docker logs. Màn hình không nhập dữ liệu hay thay policy.

### Shipments

**Mục đích:** duyệt danh sách tối đa 25 dòng mỗi trang. Bảng hiển thị mã shipment, route, trạng thái hành trình, nguồn dữ liệu và thời điểm tạo. Dùng Previous/Next nếu có trang khác; không có bộ lọc tìm kiếm riêng.

**Cách dùng:** chọn mã shipment để mở Temperature Monitoring cho shipment đó. Đây là simulated journey, không đại diện lô hàng thật. Kỳ vọng trang kế tiếp tải timeline và trạng thái dữ liệu; nếu không có shipment, nhập fixture theo hướng dẫn cài đặt. Màn hình chỉ đọc.

### Temperature Monitoring

**Mục đích:** xem telemetry theo thời gian và so sánh với teaching policy. Chọn một trong tối đa 500 shipment, nhập `View as of (UTC, processing time)` rồi chọn Apply hoặc Now để đổi mốc đánh giá. Nhập giờ UTC; giao diện gửi mốc này như timestamp UTC.

Biểu đồ gồm đường nhiệt độ và dải policy 2–8°C. Vạch ngoài dải có thể liên quan `HIGH` hoặc `LOW`; detector baseline yêu cầu vượt ngưỡng đủ lâu mới tạo incident. Khoảng thiếu dữ liệu được để trống, không nối thành đường an toàn; phần đuôi chưa nhận có thể hatch. Các thẻ khác hiển thị status, thời điểm event/receipt mới nhất, monitoring window, gap đã xác nhận, observed runs, cảnh báo chất lượng, phiên bản policy/detector và liên kết incidents.

- `CURRENT`: có dữ liệu đủ mới tại mốc xem.
- `STALE`: đã quá ngưỡng freshness nhưng chưa tới ngưỡng UNKNOWN.
- `UNKNOWN`: không đủ dữ liệu để kết luận, gồm gap dài.
- `NOT_STARTED` / `ENDED`: ngoài khoảng theo dõi của hành trình.

`event_at` là lúc cảm biến đo; `received_at` là lúc server nhận. Nếu receipt đến trễ, hai mốc khác nhau và revision evidence sau đó có thể đổi cách diễn giải. Ví dụ ocean demo đã xác minh có outage khoảng 14.13 giờ; trạng thái đi từ CURRENT sang STALE khoảng 7.52 phút rồi UNKNOWN khoảng 15.02 phút. Khi backfill đến, incident HIGH có thể được phát hiện và evidence được revision. Đây là ví dụ trong fixture mô phỏng.

Màn hình gọi model readiness M4 dạng GET, không tự chấm prediction. Thiếu shipment/telemetry hiển thị unavailable/unknown. Đừng diễn giải `UNKNOWN` là safe. Chart không sửa telemetry hoặc policy.

### Excursion Queue

**Mục đích:** xem open incident và gap cần điều tra. Có bộ lọc All open, Temperature excursions, Data gaps; shipment filter có thể được truyền từ liên kết. Danh sách phân trang 25 item, hiển thị incident ID, shipment, khoảng event-time, observed duration/direction hoặc span không có data, basis và raised time. Summary có thể gồm cả evidence superseded; danh sách làm việc tập trung open incidents.

**Cách dùng:** chọn một incident để mở Incident Details; ưu tiên incident HIGH/LOW confirmed, gap kéo dài, hoặc evidence mới/revision cần rà soát. `HIGH`, `LOW`, `DATA_GAP` là phân loại; gap không đồng nghĩa đo được nhiệt độ ngoài giới hạn. Nếu queue trống, có thể chưa import/replay hoặc chưa có incident mở. Không có thao tác đóng incident trên trang này. Evidence mới có thể supersede đánh giá trước mà không xóa history.

### Incident Details

**Mục đích:** tập hợp evidence theo incident. Trang hiển thị Facts (shipment/sensor, khoảng event, peak nếu có, continuity/gap), thời điểm raised theo processing time, evidence receipt time, detection policy/version, detector/config và timeline revision. Warnings về data quality không nhất thiết là incident riêng; nearby gaps và trạng thái superseded giúp hiểu bằng chứng đầy đủ hơn.

Đọc revision theo thứ tự: bản mới thêm bằng chứng, bản trước vẫn tồn tại trong append-only history. Dữ liệu đến trễ có thể đổi nhận định; không xóa bản ghi cũ. UNKNOWN, stale, hoặc evidence chưa đủ phải được giữ rõ ràng.

Phần M6 liệt kê explanation đã lưu, trạng thái, source mode/provider/model, prompt version, evidence cutoff, khoảng sensor, policy/SOP version, validation, summary, SOP citations (`source_id`, version, quote), evidence refs và unknown/evidence needed. Citation validation xác nhận quy tắc cấu trúc/nguồn của ứng dụng; nó không chứng minh mọi câu sinh ra đúng về ngữ nghĩa. Nếu không có explanation, empty state là bình thường. Mở incident chỉ GET history/detail, không tự gọi LLM hoặc tạo explanation.

Nếu đăng nhập `WAREHOUSE`, trang có thể cho yêu cầu physical release khi backend xác nhận QUALITY RELEASE và điều kiện cần thiết. Chỉ xác nhận có chủ ý; backend quyết định, lỗi prerequisite/403 được hiển thị. Đây là mutation thật, không dùng trong kiểm tra read-only.

### Quality Review

**Mục đích:** xem evidence shipment/open incidents và thực hiện quyết định QUALITY khi được giao quyền. Màn hình tải danh sách incidents/shipments; chọn nhóm shipment để xem evidence, revision, gaps và liên kết chi tiết. Màn hình gom incident refs đang mở để gửi cùng disposition.

Chỉ user role `QUALITY` có form. Chọn `RELEASE` hoặc `QUARANTINE`, nhập business reference và rationale; bấm submit rồi rà soát hộp xác nhận trước khi quyết định. Khi xác nhận, backend kiểm tra role, references, prerequisite và quy tắc nghiệp vụ, rồi mới ghi quyết định. Thành công chỉ khi API phản hồi xác nhận; lỗi prereq/authorization hiển thị. Nếu incident refs vượt giới hạn UI, submit bị khóa; không suy diễn quyết định từ trình duyệt.

`QUALITY RELEASE` là quyết định chất lượng; nó chưa phải thao tác đưa hàng ra khỏi kho. User `WAREHOUSE` riêng biệt yêu cầu physical release trên Incident Details sau khi điều kiện backend đạt. Không dùng `admin` thay role QUALITY/WAREHOUSE. Người không có quyền có thể đọc phần được phép nhưng POST sẽ bị 403.

UI hiện tập trung review/disposition; đăng ký shipment và custody là API workflow, chưa có đủ màn hình browser tương ứng. Không tạo disposition khi demo read-only.

### Audit History

**Mục đích:** đọc ledger blockchain và signed database audit. Bảng hiển thị transaction status, business reference, loại sự kiện, retry attempts, last error, tx hash/block/time khi có; audit list hiển thị signed entries/verification context. Pending có nghĩa đang chờ/được retry, không tự chứng minh lỗi blockchain. Fresh DB có thể không có confirmed chain transaction.

Người đã đăng nhập có thể nhập business reference để chạy GET verification. `ADMIN` mới thấy các thao tác reconciliation chain và verify signed audit; đây là kiểm tra GET/read-only, backend vẫn áp role. Trang không có nút retry và không tạo blockchain record. Nếu rỗng, hãy kiểm tra data setup/workflow; không tạo fake transaction để lấp trang.

### System Settings

Trang này chỉ đọc runtime metadata, policy đang áp dụng, version, danh sách service/feature, trạng thái sẵn sàng và role/credential flags được backend công bố. Không có form chỉnh policy hay cấu hình. Policy teaching hiện tại là 2–8°C; ngưỡng excursion và gap xem glossary/policy documentation. Không sửa `.env` bằng controls của trang; việc config cần chỉnh local `.env` và khởi động lại services phù hợp.

## M4 — ML advisory

M4 dùng Random Forest đóng băng `coldchain-rf-v1.0.0`; baseline M3 và ML advisory là hai cơ chế khác nhau. Baseline áp điều kiện threshold/duration; model ước lượng theo feature đã huấn luyện. Model readiness cho biết model có sẵn, không phải prediction đã chạy. Giao diện hiện chỉ hiển thị readiness; không có prediction-history view và không tự POST scoring. API scoring yêu cầu hành động tường minh và có thể ghi lịch sử. `INSUFFICIENT_EVIDENCE` phải hiểu `UNKNOWN`; prediction không thể cho phép disposition/release.

## M6 — RAG và giải thích

RAG (Retrieval-Augmented Generation) truy xuất tài liệu SOP được duyệt để làm nguồn cho explanation. Bản ghi đã lưu gắn status, model/source mode, mốc evidence cutoff, versions và citation có quote/source/evidence refs. Cần xem uncertainty, evidence conflict và mục evidence cần bổ sung cùng với summary. Citation validation không phải xác nhận độc lập rằng nội dung sinh đúng hoàn toàn.

Provider có thể bị tắt; khi đó readiness/provider status sẽ nói chưa cấu hình. Trang chỉ đọc explanation đã lưu, không sinh mới lúc mở incident. DB mới thường chưa có explanation hay SOP citation để xem. Không cần cấu hình API key để duyệt các empty/read-only state.

## Tình huống và giới hạn

- Giao diện dashboard không cung cấp toàn bộ registration/custody, ocean replay, prediction-history hay blockchain retry.
- Audit và M6 history phụ thuộc dữ liệu được tạo trước; DB mới có thể empty.
- Read-only GET cần đăng nhập ở các trang được bảo vệ; thao tác mutation cần role riêng và xác nhận.
- Dữ liệu là mô phỏng, không dùng làm hồ sơ vận hành thực.

## Thuật ngữ

| Thuật ngữ | Giải thích ngắn |
|---|---|
| Cold chain | Chuỗi vận chuyển cần duy trì điều kiện nhiệt độ |
| Shipment | Một chuyến/lô hàng mô phỏng |
| Sensor / Reading | Cảm biến / một lần ghi nhiệt độ |
| Excursion | Khoảng thời gian nhiệt vượt policy |
| HIGH / LOW | Vượt phía trên / thấp hơn giới hạn policy đủ điều kiện |
| DATA_GAP | Khoảng thiếu quan sát được hệ thống phân loại |
| UNKNOWN | Chưa đủ bằng chứng để kết luận |
| STALE / CURRENT | Dữ liệu cũ / dữ liệu đủ mới tại thời điểm xem |
| Evidence | Dữ liệu và nguồn dùng để đánh giá |
| Revision | Phiên bản đánh giá/evidence được nối thêm |
| Superseded | Bị bằng chứng mới thay thế trong cách nhìn hiện tại; lịch sử cũ còn nguyên |
| Disposition | Quyết định QUALITY như RELEASE hoặc QUARANTINE |
| Quarantine | Giữ lô để điều tra/xử lý thêm |
| Release | Quyết định QUALITY cho phép qua bước tiếp theo; physical release là việc riêng của WAREHOUSE |
| Baseline | Detector threshold cố định M3 |
| ML advisory | Gợi ý dự báo M4; không phải quyền quyết định |
| RAG | Tạo nội dung có truy xuất tài liệu nguồn |
| SOP | Quy trình thao tác chuẩn được duyệt |
| Citation | Trích dẫn nguồn/đoạn SOP gắn với explanation |
| Blockchain | Ledger chain cục bộ lưu một số business events |
| Audit | Dấu vết có chữ ký về thay đổi/hoạt động |
| Reconciliation | Đối chiếu trạng thái chain với outbox/business record |
| Event time | Thời điểm cảm biến ghi nhận sự kiện |
| Received time | Thời điểm backend nhận dữ liệu |
