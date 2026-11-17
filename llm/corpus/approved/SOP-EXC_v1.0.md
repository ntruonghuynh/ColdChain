---
doc_id: SOP-EXC
title: Quy trình mô phỏng giải thích cảnh báo và tập hợp bằng chứng
version: "1.0"
status: teaching_approved
procedure_version: SOP-EXC v1.0
product_categories:
  - CHILLED_2_8C
effective_from: "2026-11-14"
effective_to: null
language: vi
origin: "Nhóm dự án biên soạn từ POL-CHILL-01 v1.0 và hợp đồng M3/M5 trong repository"
approval_scope: "Chỉ được dùng trong đồ án mô phỏng; không phải phê duyệt vận hành, lâm sàng hay quy định"
---

# Quy trình mô phỏng phục vụ đồ án – không phải hướng dẫn vận hành chính thức.

Tài liệu này hỗ trợ giải thích sự kiện trong hệ thống mô phỏng. Nguồn quy tắc nhiệt độ duy nhất là policy `POL-CHILL-01` phiên bản `1.0`; không tự đặt ngưỡng hoặc thời lượng mới. Nội dung không thay thế tư vấn chất lượng, quy trình khách hàng, yêu cầu pháp lý hoặc quyết định của người có thẩm quyền.

## Theo dõi bình thường [MONITORING]

- Trình bày số đo cùng `event_at` và `received_at`; nêu rõ khoảng dữ liệu được dùng.
- Chỉ mô tả là quan sát được khi bản ghi đã được hệ thống nhận trước thời điểm giải thích.
- Không suy rộng kết luận cho khoảng thời gian không có số đo.
- Tình trạng giám sát hoặc điểm ML là thông tin hỗ trợ, không phải kết luận chất lượng.

## Sự kiện nhiệt độ cao [HIGH_EXCURSION]

- Tóm tắt các số đo quan sát được, thời điểm đo, thời điểm nhận, khoảng sự kiện và kết quả detector M3.
- Đối chiếu đúng policy đang gắn với lô hàng. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức cao khi số đo lớn hơn 8.0 °C liên tục ít nhất 30 phút; các khoảng thiếu làm gián đoạn chuỗi quan sát.
- Nếu sự kiện kề khoảng UNKNOWN, nói rõ thời lượng quan sát được là giới hạn dưới; không khẳng định diễn biến trong khoảng trống.
- Chuyển phần quyết định cho Quality Officer theo workflow M5.

## Sự kiện nhiệt độ thấp [LOW_EXCURSION]

- Tóm tắt số đo và bằng chứng M3 trong khoảng sự kiện, nêu rõ mốc nhận dữ liệu.
- Đối chiếu policy đang gắn với lô. Với `POL-CHILL-01 v1.0`, policy ghi nhận mức thấp khi số đo nhỏ hơn 2.0 °C liên tục ít nhất 15 phút; khoảng thiếu không được nội suy.
- Nêu bằng chứng còn thiếu và chuyển đánh giá cho Quality Officer.

## Một điểm đo bất thường [ISOLATED_SPIKE]

- Phân biệt một số đo đơn lẻ với incident được policy baseline xác nhận.
- Có thể nêu cảnh báo chất lượng cảm biến hoặc so sánh với số đo lân cận nếu các bản ghi đó có sẵn tại cutoff.
- Không tự bỏ số đo, tự sửa dữ liệu, hoặc khẳng định đó là lỗi cảm biến nếu chưa có bằng chứng hệ thống.

## Thiếu quan sát và khoảng UNKNOWN [MISSING_TELEMETRY]

- Hiển thị khoảng trống là UNKNOWN và ghi rõ dữ liệu không đủ để kết luận nhiệt độ trong khoảng đó.
- Không điền giá trị, không nội suy để xác nhận an toàn và không dùng “không có cảnh báo” làm bằng chứng an toàn.
- Nêu thời điểm nhận số liệu gần nhất và bằng chứng cần thu thập thêm.

## Truyền dữ liệu trễ hoặc vùng biển [DELAYED_OCEAN]

- Phân biệt thời điểm logger đo (`event_at`) và thời điểm hệ thống nhận (`received_at`).
- Chỉ đưa số đo vào giải thích lịch sử khi `received_at` không sau cutoff; bản ghi đến muộn hơn không được coi như đã biết trước đó.
- Nếu dữ liệu được đệm rồi tải lên, nói rõ độ trễ quan sát được; không kết luận về nhiệt độ trong thời gian chưa nhận được số liệu.

## Cảm biến lỗi hoặc số đo không chắc chắn [SENSOR_UNCERTAINTY]

- Nêu cảnh báo M3/M4 liên quan như bằng chứng riêng biệt, kèm phiên bản và thời điểm.
- Điểm ML chỉ là advisory. Không diễn giải điểm số thành quyết định RELEASE hoặc QUARANTINE.
- Nếu cảm biến, thời gian hoặc bối cảnh chưa đủ để diễn giải, trả trạng thái thiếu bằng chứng.

## Tập hợp bằng chứng và lưu vết [EVIDENCE_AUDIT]

- Liệt kê nguồn hệ thống và section SOP thực sự được cung cấp cho lần giải thích; giữ ID, phiên bản và hash.
- Không bịa trích dẫn. Trích dẫn quy trình phải chỉ đúng section và đoạn văn bản trong nguồn đã truy xuất.
- Không sửa incident, reading, disposition, custody, outbox hay lịch sử audit.

## Rà soát Quality và trạng thái workflow [QUALITY_REVIEW]

- Incident mở hoặc dữ liệu thiếu được trình bày để người có thẩm quyền xem xét theo workflow hiện hành.
- Chỉ người có vai trò QUALITY được ủy quyền ghi disposition RELEASE hoặc QUARANTINE; thao tác kho chỉ được thực hiện sau RELEASE đã được xác nhận theo M5.
- Bản giải thích, lời khuyên, trạng thái blockchain hoặc dự đoán ML không thay thế phê duyệt của Quality Officer.
- Quyết định RELEASE trong prototype không phải bảo đảm pháp lý, lâm sàng hoặc an toàn sản phẩm.
