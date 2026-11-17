# Kiến trúc M6: RAG giải thích sự cố có dẫn chứng

## Phạm vi và ranh giới

M6 cung cấp truy xuất quy trình và bản giải thích tham khảo cho người dùng đã đăng nhập, có quyền truy cập shipment. Đây là dịch vụ đọc dữ liệu M3–M5; nó không ghi nhận disposition, thay đổi custody, phát hành hàng, sửa telemetry, gọi blockchain signer hay truy cập nhãn ground truth. Bản giải thích không thay thế quyết định của Quality Officer.

Luồng xử lý gồm: xác thực và kiểm tra quyền theo organization → dựng gói chứng cứ nhân quả đến `evidence_cutoff_at` → truy xuất SOP được duyệt theo phiên bản/sản phẩm/ngày → gọi provider OpenAI-compatible tùy chọn → kiểm tra schema và citation → ghi bản ghi giải thích append-only. Nếu provider bị tắt, hệ thống không giả vờ có LLM; fallback xác định chỉ bật bằng cấu hình rõ ràng và được gắn nhãn riêng.

## Kho tri thức và nguồn

`llm/corpus/approved/SOP-EXC_v1.0.md` là tài liệu mô phỏng tiếng Việt, có tuyên bố rõ không phải hướng dẫn chính thức. Nội dung lấy giới hạn và thời lượng từ policy giảng dạy đang được phê duyệt, đồng thời mô tả xử lý thiếu dữ liệu, truyền chậm, spike, lỗi cảm biến, xem xét chất lượng và lưu chứng cứ. Không thêm khẳng định quy định pháp lý hoặc an toàn sản phẩm ngoài nguồn dự án.

Mỗi tài liệu giữ ID, phiên bản, trạng thái, phạm vi loại sản phẩm, ngày hiệu lực, provenance, ngôn ngữ và SHA-256. Chia chunk xác định theo heading `##`; ID chunk ổn định theo `doc_id@version#section_id`. Bộ nạp từ chối ID trùng, tài liệu hỏng và thay đổi âm thầm nội dung của phiên bản đã ghim. Mẫu prompt injection ở `untrusted_samples/` bị loại khỏi chỉ mục.

Chỉ mục BM25 thuần, sắp xếp điểm ổn định, lọc trạng thái/phiên bản/phạm vi sản phẩm/ngày trước khi trả kết quả. Từ v2 (`bm25-v2-title25-vn-aliases`), token query bỏ dấu tiếng Việt, dùng alias query nhỏ dựa trên thuật ngữ trong SOP và trọng số tiêu đề section 2.5 lần so với body. Không đổi nội dung SOP, policy hay metadata applicability. Không tải embedding, không cần vector database, truy xuất hoạt động offline. `no_applicable_sources` vẫn phụ thuộc có từ nào khớp; chưa có ngưỡng điểm semantic đã hiệu chuẩn nên query không liên quan nhưng trùng từ chung có thể trả chunk.

## Gói chứng cứ và thời gian

Adapter chỉ truy vấn bảng vận hành. Reading phải thỏa cả `event_at <= cutoff` và `received_at <= cutoff`. Revision, gap, cảnh báo, detection, prediction và disposition chỉ được đưa vào khi thời điểm phát sinh/tạo/ghi nhận tương ứng đã tới cutoff. Xác nhận blockchain chỉ được báo nếu `confirmed_at <= cutoff`. Khoảng thiếu không được nội suy thành nhiệt độ bình thường. Outbox hiện tại không có lịch sử trạng thái đủ để dựng trạng thái lịch sử, vì vậy không trình bày trạng thái mutable của nó như sự thật tại cutoff.

Adapter không import bảng hoặc module simulator ground truth. Tài liệu chỉ được truy xuất theo product category và `procedure_version` gắn với policy shipment. Bản ghi giải thích lưu cutoff, khoảng sensor, hash prompt, phiên bản tài liệu, evidence references và kết quả kiểm citation; không lưu câu hỏi thô, system prompt đầy đủ, API key hoặc khóa ký.

## Provider, prompt và xác minh

Provider mặc định `disabled`. Cấu hình `openai_compatible` nhận base URL, model/version, API key qua environment/secret, timeout, số retry tối đa 2 và giới hạn output. Client chỉ dùng HTTP(S), không phát credential trong log, không gọi khi test trừ khi được cấu hình chủ động. Health/readiness tách trạng thái corpus khỏi provider đã cấu hình; trạng thái configured không chứng minh endpoint bên ngoài sẵn sàng.

Prompt phiên bản `m6-response-v1` phân vai system instruction tin cậy, dữ liệu có cấu trúc và SOP là dữ liệu không tin cậy, cùng câu hỏi người dùng. Model không được cấp tool. Schema Pydantic từ chối field lạ, giới hạn kích thước, buộc đầu ra phân tách facts/policy/ML/unknown/recommendations/citations và từ chối một tập cụm từ tuyên bố release/an toàn. Kiểm citation xác nhận ID nguồn được cung cấp, phiên bản policy/khoảng thời gian và quote là chuỗi con của nguồn. Kiểm tra này không chứng minh ngữ nghĩa của mọi câu là đúng; cần đánh giá người đọc.

Nếu citation hoặc cấu trúc không hợp lệ, nội dung model bị bỏ và không hiển thị như bản nháp. Fallback xác định chỉ trích xuất số đo, policy và đoạn SOP có sẵn; UI/API đánh dấu `deterministic_fallback`, không gọi nó là sinh bởi LLM. Với chứng cứ hoặc nguồn không đủ, trả trạng thái abstain/none hoặc fallback được dán nhãn.

## API và lưu vết

- `GET /api/llm/readiness`: trạng thái kho tri thức và cấu hình provider.
- `POST /api/llm/procedures/search`: tìm section theo query, phiên bản, loại sản phẩm và ngày.
- `POST /api/llm/incidents/{incident_id}/explanations`: tạo giải thích có auth/RBAC và phạm vi tổ chức.
- `GET /api/llm/incidents/{incident_id}/explanations`: lịch sử append-only trong phạm vi shipment.
- `GET /api/llm/explanations/{explanation_id}`: đọc một kết quả đã lưu trong phạm vi shipment.

Migration `0006_m6_llm_explanations` chỉ thêm bảng và trigger cấm UPDATE/DELETE. Khóa idempotency `(user, request_ref)` chặn yêu cầu lặp và xung đột nội dung. Kiểm tra quyền dùng role M5 và organization shipment hiện có.

## Đánh giá và giới hạn

`llm/eval/cases/m6-cases.jsonl` có 40 tình huống, chia đều bốn nhóm. Runner deterministic hiện đo truy xuất đúng section và lọc phiên bản/loại sản phẩm, loại tài liệu hostile khỏi index. Nó không gọi provider và không đo chất lượng câu trả lời, groundedness ngữ nghĩa, citation của câu trả lời sinh, latency hay chi phí. Các nội dung đó chỉ được báo cáo sau inference thật và review có người; không được suy ra từ test mock.

SOP là tài liệu mô phỏng cho đồ án; dữ liệu dự án chủ yếu synthetic. Tìm từ khóa có thể bỏ sót ý đồng nghĩa hoặc trả kết quả không hoàn hảo. Bộ lọc cụm từ không phải bộ kiểm chứng ngữ nghĩa. Provider bên ngoài có thể không khả dụng hoặc xử lý dữ liệu theo điều khoản riêng; cần phê duyệt dữ liệu và nhà cung cấp trước demo production-like. Không đưa bí mật vào nội dung hỏi. M5 vẫn có giới hạn trạng thái chain trong bộ nhớ theo tài liệu M5; M6 không thay đổi hoặc giải quyết giới hạn đó.

### Bằng chứng nghiệm thu cuối

Migration `0006` được xác minh `0006 (head)` trên DB của Compose project riêng `m6acceptance`. Lỗi đầu tiên là hai biến giá optional rỗng được Compose truyền thành `""`, gây lỗi parse Pydantic; validator cấu hình chuyển chuỗi rỗng thành `None`, có test hồi quy và lần migration tiếp theo hoàn tất. Chỉ backend/worker/frontend cô lập được khởi động lại; database và chain active M5 không bị thay thế. Hash container active Hardhat trước/sau giống nhau (`raw/active-chain-id-before.txt`, `raw/active-chain-id-after.txt`).

HTTP integration dùng thông tin đăng nhập từ env tạm và fixture tổng hợp trong volume cô lập. Đã kiểm tra năm role, invalid credentials/token, anonymous denial, retrieval, tạo/lấy explanation, cross-organization 404, insufficient-evidence, provider-disabled và deterministic fallback. Citation fallback qua validator; nội dung ghi rõ không do LLM tạo. Carrier request disposition/release bị backend trả 403. Đây là bằng chứng ranh giới API, không phải inference thật. Raw được lưu ở `docs/milestones/m6/raw/isolated-http-disabled-provider.json`, `isolated-http-fallback-authz.json` và `fallback-http-representative.json`.

Provider thật không được cấu hình trong môi trường này. Real-provider inference, prompt-injection behavior của model thực và semantic review **NOT RUN**. Mock provider/parser unit test không được tính là inference thật. Challenge v1 giữ kết quả 6/12 top-1, hit@3 9/12. Dùng development set riêng 27 ca để thay đổi retrieval; sau đó đóng băng v2 và chạy challenge v2 mới đúng một lần: 7/12 top-1, hit@3 11/12, MRR 0.752778, no-result insufficient 0/3, filter version/product 3/3 mỗi loại. Hai challenge khác nội dung nên không so sánh như phép đo cải thiện trực tiếp. Không điều chỉnh code sau challenge v2. Chi tiết raw và hash tại `docs/milestones/m6/raw/`.

Trong luồng provider, metadata provider/model/usage/latency được lưu ngay sau khi nhận response, trước khi validate JSON/citation. Nếu citation sai, nội dung bị loại, `source_mode=none`, `citation_verification=failed`; metadata provider vẫn cho biết request thật đã tới model và có thể giữ chi phí ước tính khi cấu hình bảng giá. Không có inference thật chạy trong nghiệm thu này. Hướng dẫn provider và opt-in nằm ở `docs/milestones/m6/real-llm-validation-setup.md`.
