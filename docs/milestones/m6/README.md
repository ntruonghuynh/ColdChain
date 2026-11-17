# Milestone 6 – RAG giải thích sự cố (bản nghiệm thu kỹ thuật)

## Kết quả triển khai

M6 bổ sung kho SOP mô phỏng có phiên bản, ingestion/chunking ổn định, chỉ mục lexical BM25, bộ dựng evidence theo thời điểm, provider OpenAI-compatible tùy cấu hình, fallback deterministic tùy chọn, kiểm schema/citation, API có xác thực/phân quyền và bảng audit append-only. Provider mặc định tắt; base stack không cần API key hoặc tải model. Không sửa quy tắc M3, model/threshold M4, workflow/contract M5 hoặc policy được duyệt.

Thiết kế chi tiết ở [`docs/design/m6-rag-architecture.md`](../../design/m6-rag-architecture.md). Tài liệu SOP [`SOP-EXC_v1.0.md`](../../../llm/corpus/approved/SOP-EXC_v1.0.md) được đánh dấu rõ: “Quy trình mô phỏng phục vụ đồ án – không phải hướng dẫn vận hành chính thức.” Nó dựa trên policy giảng dạy hiện hữu và ranh giới Quality Officer M5.

## Đánh giá 40 tình huống

Danh sách kiểm thử: [`m6-cases.jsonl`](../../../llm/eval/cases/m6-cases.jsonl). Có 40 ca, 10 ca mỗi nhóm: vận hành/đủ chứng cứ, thiếu dữ liệu, chứng cứ xung đột, chỉ dẫn đối kháng. Runner [`run_40_cases.py`](../../../llm/eval/run_40_cases.py) chỉ kiểm tra truy xuất section đích, từ chối phiên bản và loại sản phẩm sai, đồng thời loại sample độc hại khỏi corpus. Runner **không gọi LLM**.

Kết quả lần chạy cuối được lưu trong `raw/40-case-retrieval-check.json` và `raw/40-case-retrieval-check.txt`. Chỉ số nội dung sinh, citation sinh, semantic groundedness, xử lý abstention của model, latency và chi phí là `NOT RUN` khi chưa cấu hình/gọi provider thật và chưa có review người. Không kết luận chất lượng LLM từ các phép kiểm deterministic này.

## Provider và demo

Đặt `LLM_PROVIDER=openai_compatible`, `LLM_MODEL`, `LLM_API_BASE_URL` và `LLM_API_KEY` trong môi trường local được bảo vệ. Không commit `.env` hoặc secret. Có thể dùng endpoint tương thích OpenAI Chat Completions nội bộ/local. Cần endpoint HTTPS cho dịch vụ bên ngoài, timeout hữu hạn; số lần retry bị chặn tối đa 2. Mặc định `LLM_PROVIDER=disabled`, `LLM_FALLBACK_ENABLED=false`. Nếu bật fallback, API phải ghi `source_mode=deterministic_fallback`; không được gọi đây là câu trả lời LLM.

Luồng demo: đăng nhập user có quyền trên shipment → gọi `/api/llm/incidents/{id}/explanations` với cutoff rõ ràng → kiểm chứng `evidence_references`, `document_versions`, `citation_verification`, `source_mode` và disclaimer → thử cutoff thiếu dữ liệu để thấy abstain → gọi yêu cầu trái quyền bằng user khác và xác nhận bị từ chối. Endpoint này không gọi các API disposition/release.

## Bằng chứng kiểm thử

Lệnh backend/generator chính thức chạy trong Docker profile test, dùng database `coldchain_test` riêng. Báo cáo trước ghi **314 passed, 6 deselected** (`raw/backend-generator-tests-final.txt`). Sau khi thêm marker M9 và test cấu hình optional mới, kết quả nghiệm thu cuối là **310 passed, 11 deselected, 0 failed, 6 cảnh báo deprecation**; log mới là `raw/backend-generator-tests-acceptance-final.txt` và đây là lần chạy có ranh giới seed rõ ràng nhất. Test M6 độc lập trước đó: **15 passed, 0 failed** (`raw/m6-targeted-tests-final.txt`). Test container không gọi chain service.

```sh
docker compose --profile test run --rm --build backend-tests
```

Đánh giá retrieval có **40/40 hit section đích**, từ chối phiên bản sai 40/40 và loại loại sản phẩm sai 40/40. Corpus có 1 tài liệu, 9 chunks; sample tấn công không được index. Raw: `raw/40-case-retrieval-check.json` và `.txt`. Lần chạy ban đầu đạt 34/40; sáu truy vấn trong fixture không chứa từ khóa có trong section mục tiêu. Fixture được chỉnh lại để mô tả đúng chủ đề truy xuất, còn chuỗi tấn công được giữ riêng như input không tin cậy. Lần chạy ban đầu được lưu riêng ở `raw/40-case-retrieval-initial-run.json`; kết quả 40/40 là kiểm tra nội bộ trên fixture đã hiệu chỉnh, không phải đánh giá độc lập.

Frontend regression: **24 test passed**; `npm run typecheck` thành công; `npm run build` thành công (2,132 module được bundle). Log ở `raw/frontend-tests.txt`, `raw/frontend-typecheck.txt`, `raw/frontend-build.txt`.

Kiểm tra `docker compose --profile test config --quiet`, `git diff --check`, AST parse **112 file Python**, và build runtime Docker qua `docker compose build migrate` thành công (`raw/backend-runtime-image-build.txt`). Lệnh build ở lần review trước chỉ build image. Lúc đó API M6 mới được kiểm qua TestClient và chưa rollout vào DB đang chạy. Ở nghiệm thu cuối, migration/API được xác minh bổ sung trong project cô lập `m6acceptance`; chi tiết, migration `0006 (head)` và API HTTP thực tế được ghi tại phần “Bổ sung nghiệm thu cuối” bên dưới. Stack M5 đang hoạt động tiếp tục không bị rollout/restart.

Manifest kho SOP ghi nhận 1 document/9 chunks, SHA-256 tài liệu `537ed44eef6286c1f92c17981d9eb38156fed0a682a1d5ef140bd9e5464ae27d`; file manifest SHA-256 `d8fb302c90ffe8118530278615ebd3c45edfe627076ec2299c4954aa00711037` (lệnh tạo: `raw/index-build.txt`).

## Ranh giới dữ liệu và bảo mật

- Chỉ dữ liệu quan sát M3, detection, prediction M4 advisory, policy và sự kiện M5 có sẵn trước cutoff mới vào context.
- Reading phải đồng thời có `event_at` và `received_at` không vượt cutoff; không nội suy gap.
- Không dùng simulator ground truth trong API/vận hành.
- Lịch sử explanation chỉ thêm; không lưu secret hay prompt/question đầy đủ.
- SOP, metadata, câu hỏi và trích đoạn là input không tin cậy; không có tool/credential cho phép thay đổi workflow.
- Citation ID/phiên bản/quote được kiểm tra tự động; kiểm tra ID không chứng minh mọi phát biểu đúng về ngữ nghĩa.
- Không ghi giải thích lên blockchain và không quyết định release/quarantine.

## Giới hạn / trạng thái nghiệm thu

Không có inference thật nếu không cấu hình endpoint/secret; không báo cáo số đo chất lượng ngôn ngữ hoặc latency thật khi chưa chạy provider. Kho tri thức hiện chỉ có một SOP mô phỏng, không phải tập SOP chính thức đa khách hàng. Kiểm tra prompt injection chỉ bao phủ test xác định và ranh giới kiến trúc; không chứng minh miễn nhiễm với mọi tấn công. UI dashboard M7 chưa nằm trong phạm vi. Trạng thái chain persistence M5 vẫn deferred như tài liệu M5 mô tả.

Các cảnh báo backend là deprecation từ Starlette/httpx và websockets của dependency hiện hữu; không làm test thất bại. PDF assignment gốc không trích xuất được bằng công cụ có sẵn trong môi trường (thiếu converter/thư viện tương thích); yêu cầu được đối chiếu với `docs/requirements-analysis.md` đã chuẩn hóa. Không có key/provider thật được cấu hình hoặc gọi. Chưa có đánh giá người cho groundedness/ngữ nghĩa.

**Sai lệch quy trình seed cần chủ dự án biết:** lần chạy hồi quy đầy đủ đầu tiên đã vô tình thực thi test generator determinism hiện hữu, test này tham số hóa cả các seed được bảo lưu 22/33/44/55/66. Test không đọc dataset đánh giá đã commit hoặc metric M9, nhưng có thực thi generator với các seed đó; đây là sai lệch so với lệnh “không truy cập seed”. Lần chạy cuối loại trừ riêng test parametrized này (`-k not test_eval10_canonical_and_reserved_seeds_generate_200_journeys_reproducibly`). Không có tuning M6 hoặc đọc kết quả đánh giá từ các seed. Sai lệch được ghi lại để owner quyết định có cần cách ly thêm.

**Trạng thái kỹ thuật:** implementation và regression tự động đã hoàn tất; đánh giá câu trả lời bằng inference thật và rollout migration/API lên stack đang chạy còn chờ cấu hình nhà cung cấp và review/triển khai có kiểm soát. Đây không phải xác nhận chất lượng LLM production. Mọi chỉ số provider/chất lượng không chạy giữ `NOT RUN`.

## Kiểm tra offline sau pilot và an toàn triển khai

Đợt này **không gọi provider**, không chạy 35 case còn lại, không sửa manifest/pilot draft, không restart M5 và không đổi image tag dùng chung.

- M6 backend cô lập được build dưới tag riêng `coldchain-backend:m6-evalprep`, sau đó chỉ service backend được recreate với `--no-deps`. Backend healthy; HTTP readiness báo runtime `m6-post-pilot-temporal-v3`, prompt `response_draft/v3`, output schema `explanation-content/v2`, provider adapter `openai-chat-completions/v1`, retriever production `bm25-v2-title25-vn-aliases`, corpus 9 chunks. Readiness ghi model cấu hình `gpt-6-luna` và provider `configured`; đây không phải bằng chứng đã gửi provider call.
- HTTP health trả migration `0006` ở đúng head. Isolated PostgreSQL giữ 5 explanation rows; M6 chain vẫn block `0x1`. M5 backend/DB/chain/frontend không đổi container IDs và vẫn healthy; M5 chain đọc được block `0x4a7`. Evidence chi tiết trong [`deployment-safety-and-m5-image-recovery.md`](deployment-safety-and-m5-image-recovery.md) và thư mục `raw/`.
- Image gốc của M5 backend (`sha256:f2ad35…`), chain (`sha256:810125…`) và frontend (`sha256:4dc629…`) đều không còn trong local image store; shared `coldchain-backend:local` tiếp tục trỏ M6 `sha256:0decfeed…`. Có candidate `coldchain-backend:m5-recovery-isolated` với app `0.1.0`, milestone M5, migration head `0005`, và các file source đã so khớp commit `8c9bad1…`; chưa kiểm đầy đủ dependencies/integration nên chưa được coi là an toàn hoặc byte-identical. Candidate chain/frontend chưa được kiểm source. **Không retag/recreate M5.** Cần owner approval trước mọi tag restoration hoặc triển khai M5.
- Compose config hiện hành resolve các tag riêng cho M6; test guard tự động ngăn service config quay về `:local`/`:test`. Các container chain/frontend M6 hiện tại chưa được thay thế và vẫn có image ref `:local`; giữ nguyên để tránh mất chain state. Lần rollout M6 đầy đủ sau này cần kế hoạch riêng cho chain.
- So sánh Compose đã resolve (chỉ lưu images/ports/volumes, loại toàn bộ secrets): M5 dùng project `coldchain`, port `8545`/`3000`; M6 dùng project `coldchain-m6-evalprep`, port `18549`/`3107`; Postgres không publish host port. Named volumes có cùng logical names nhưng Compose prefix theo project. Raw: `raw/m5-m6-compose-safe-projection.json`.
- Regression Docker-based sau remediation: **35 passed, 0 failed, 6 cảnh báo deprecation**, `raw/m6-deployment-offline-regression.txt`. Kiểm thử provider bị disable; bao gồm test mocked provider, persistence/API diagnostics, temporal cutoff/UTC/SOP, fail-closed timestamp contradiction/schema/citation, readiness version fields và Compose tag isolation. Pytest trực tiếp trên host không khởi động do thiếu FastAPI; Docker test image đã chạy thành công.
- Runtime diagnostics đã được kiểm ở API readiness và qua tests persistence/serialization: finish reason và các stage parse/schema/evidence/citation được giữ allow-listed; raw output/prompt/secret không được đưa vào report. Readiness còn ghi prompt/schema hashes và component versions. Evaluation runner phân biệt runtime, prompt, schema, adapter, retrieval, model và manifest version; không bịa stage data cho năm record lịch sử.
- Manifest v1 vẫn có canonical SHA-256 `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`. Năm pilot là historical evidence; 35 explanation calls **NOT RUN**. Retrieval preflight 40 case đã từng được quan sát, vì vậy 35 case không phải retrieval challenge độc lập. Owner đã báo cáo PASS cho cả năm; provenance được ghi `OWNER_REPORTED`, nhưng reviewer identity, rationale, reviewed_at và reviewer-selected evidence refs chưa được cung cấp nên independent substantiation **NOT ESTABLISHED**. M6R-016 còn known material temporal contradiction; M6R-006/M6R-036 còn retrieval/semantic support gaps.

**Quyết định hiện tại: NO-GO** cho khôi phục tag/deploy M5, cho pilot provider M6 mới, và cho acceptance cuối M6. M5 cần owner quyết định sau khi candidate được kiểm tra cô lập và kế hoạch triển khai/rollback được thống nhất. Owner-reported PASS không tự thay thế reviewer identity/rationale/evidence còn thiếu. Pilot M6 mới và version-freeze chờ khép lại `KNOWN_MATERIAL_TEMPORAL_CONTRADICTION`, xử lý hoặc disposition retrieval gaps có căn cứ, và có review evidence có thể kiểm chứng. M6 acceptance còn chờ xác nhận semantic support và đánh giá giới hạn temporal validator.

## Bổ sung nghiệm thu cuối

### Sự cố truy cập seed dành riêng cho M9

Trong lần hồi quy trước M6, test determinism của generator đã gọi generator với các seed 22, 33, 44, 55 và 66. Đây là sai lệch quy trình và được ghi nhận, không xóa hay thay thế bằng seed khác. Kiểm tra mã sau sự cố cho thấy test tạo đầu ra dưới `tmp_path` trong test container dùng `--rm` và mount repository chỉ đọc; test so fingerprint/manifest, không đưa kết quả, nhãn, metric hay feature đó vào M4, lựa chọn model, retrieval hoặc đánh giá M6. Mã M6 dùng fixture tại `llm/eval/cases/m6-cases.jsonl` và corpus SOP; evidence adapter chỉ truy vấn bảng vận hành, không import/query ground-truth. Không chạy lại các seed này để xác minh.

Đã gắn marker `m9_evaluation` cho test generator/manifest và kiểm tra giao thức đánh giá liên quan. Cấu hình pytest mặc định loại marker đó bằng `-m 'not m9_evaluation'`; lệnh hồi quy phát triển tiêu chuẩn vì vậy không thực thi nhóm M9. Test generator còn lại chạy riêng duy nhất seed 11, ghi vào `tmp_path`, rồi so byte với bộ dữ liệu canonical mà không ghi vào thư mục dữ liệu canonical. Bằng chứng seed 11: `raw/seed11-determinism-only.txt`. Test phát triển cuối: **310 passed, 11 deselected**, `raw/backend-generator-tests-acceptance-final.txt`.

### Độ tin cậy retrieval và bộ đánh giá 40 ca

Hai kết quả lịch sử vẫn được giữ: 34/40 ở lần đầu và 40/40 sau khi chỉnh sáu câu hỏi fixture. Cả hai chỉ là phép thử retrieval; không phải phép đánh giá chất lượng câu trả lời LLM, groundedness ngữ nghĩa hay factual accuracy. Xem các raw kết quả hiện có `raw/40-case-retrieval-initial-run.json` và `raw/40-case-retrieval-check.json`.

Để kiểm tra độc lập, trước khi chạy đã lưu SHA-256 của bộ challenge mới tại `raw/retrieval-challenge-input-sha256.txt`; chạy đúng một lần với `llm/eval/challenge/m6-retrieval-challenge-v1.jsonl`, không chỉnh ranking rule hay wording sau kết quả. Kết quả: top-1 đúng **6/12**, hit@3 **9/12**, MRR **0.6111**; trong 3 cặp có cả target và distractor được trả về, target đứng trước **1/3**. Ba ca không đủ nguồn trả rỗng **3/3**, phiên bản sai bị từ chối **3/3**, sai loại sản phẩm bị từ chối **3/3**. Đây là mẫu nhỏ, lexical BM25 nhạy với từ dùng trong câu hỏi; xếp hạng top-1 yếu hơn kết quả tuned. Raw: `raw/retrieval-challenge-results.json` và `.txt`. Kết quả challenge không được dùng để tune.

Bộ 40 ca hiện hành và runner cũ đo section đích, version và product filtering; không phát sinh câu trả lời. Runner HTTP mới `llm/eval/run_explanation_eval.py` nối case đã chuẩn bị với incident có sẵn, giới hạn tối đa 40, loại bỏ/khử secret khi lưu, và yêu cầu flag `--confirm-provider-calls` cùng cấu hình API/token/incident map. Dry-run mặc định ghi `provider_invoked=false`, `status=DRY_RUN` tại `raw/explanation-eval-dry-run.json`; đây không phải inference. Các metric semantic, procedural human review, factual accuracy của output sinh và latency provider tiếp tục là **NOT RUN**.

### Provider và kiểm thử API HTTP

Không có endpoint hoặc model nào được cấu hình trong môi trường làm việc; readiness được kiểm tra mà không in secret và provider đang disabled. Không phát sinh lời gọi provider thật, không có inference trả phí, không dùng mock/fallback để báo là LLM thật. Để chạy: cấu hình `LLM_PROVIDER=openai_compatible`, `LLM_MODEL`, `LLM_API_BASE_URL`, `LLM_API_KEY` ở môi trường local bảo vệ; cung cấp `M6_EVAL_API_BASE_URL`, `M6_EVAL_BEARER_TOKEN`, incident map; dùng endpoint OpenAI-compatible cục bộ hoặc bên ngoài được phê duyệt. Batch đánh giá yêu cầu chủ dự án opt-in rõ ràng qua `--confirm-provider-calls`.

Migration 0006 và API đã được triển khai lên **Compose project cô lập `m6acceptance`**, với volume riêng `m6acceptance_pgdata`, `m6acceptance_chain-deployments` và cổng frontend 3337/chain 18547. M6 backend image được build lại; migration `0001`–`0006` cùng seed dữ liệu tham chiếu chạy thành công ở DB mới. Không rollout vào project đang hoạt động, không restart chain/database hiện có; active chain container ID trước/sau được ghi trong `raw/active-chain-id-before.txt` và `raw/active-docker-status-final.txt`. Chain cô lập, backend, worker, frontend và PostgreSQL đều healthy; deployment là job một lần exited 0. Lần `up` đầu tiên của isolated project phát hiện lỗi khởi động: Compose chuyển giá LLM tùy chọn rỗng thành chuỗi rỗng, Pydantic từ chối parse `float | None`. Đã sửa Settings để chuẩn hóa `""` thành `None` và thêm regression test. Migration chạy lại thủ công thành công; container job cũ còn trạng thái exited 1 là bằng chứng của lần lỗi đầu, không phải trạng thái migration hiện tại. Log lỗi ban đầu: `raw/isolated-migration-error.txt`; bản build mới và test cấu hình được lưu riêng.

HTTP thực tế tới `http://127.0.0.1:3337` dùng fixture shipment/incident tổng hợp chỉ trong DB cô lập. Năm role SHIPPER/CARRIER/QUALITY/WAREHOUSE/ADMIN đăng nhập thành công; password sai và token không hợp lệ bị 401; anonymous retrieval bị 401; authenticated procedure search trả section phù hợp; cross-organization incident bị che bằng 404; history được tạo/đọc; provider-disabled response ghi `source_mode=none`; fixture thiếu số đo trả `insufficient_evidence`. Khi chỉ bật deterministic fallback trong isolated project, giải thích có số đo và thiếu evidence trả `source_mode=deterministic_fallback`, citation validation `passed`, disclaimer nêu đây không phải nội dung LLM, và không có câu “safe” trong summary/observations. Carrier bị 403 khi gọi workflow disposition/release. Bằng chứng HTTP đã khử secret: `raw/isolated-http-disabled-provider.json`, `raw/isolated-http-fallback-authz.json`, `raw/fallback-http-representative.json`. Tất cả kết quả fallback/mocked nếu có chỉ được báo là deterministic fallback/mocked.

Unit test citation xác nhận ID không có trong source set và quote giả bị từ chối (`test_m6_citation_verification_rejects_fabricated_id_and_quote`). Kiểm tra HTTP fallback chứng minh citation được trả đã qua validator, nhưng không thay thế kiểm thử end-to-end provider thật. API giải thích chỉ đọc dữ liệu và thêm audit explanation; không có quyền gọi disposition/release, thay đổi custody hay signer. ML vẫn chỉ tư vấn. Fixture HTTP cô lập không làm thay đổi shipment/incident lịch sử của project đang chạy.

### Kiểm thử và giới hạn nghiệm thu

- Backend/generator tiêu chuẩn: **310 passed, 11 M9-marked deselected**, 6 cảnh báo deprecation; raw `raw/backend-generator-tests-acceptance-final.txt`.
- Frontend: **24 passed**, TypeScript `typecheck` passed, production build thành công; raw `raw/frontend-tests-acceptance-final.txt`, `raw/frontend-typecheck-acceptance-final.txt`, `raw/frontend-build-acceptance-final.txt`.
- Migration 0006: thành công trong DB cô lập; API HTTP M6 kiểm tra trên backend đang chạy trong project cô lập, không phải active M5 stack.
- Smoke Compose cô lập: **6/6** kiểm tra route frontend, proxy, health/migration, teaching policy, backend outage và recovery; log `raw/isolated-smoke-final.json` / `.txt`. Script M1 nguyên bản không chạy vì nó hạ toàn project `coldchain`; đã kiểm tra tương đương trực tiếp chỉ trong `m6acceptance`.
- Independent retrieval challenge: đạt các tỷ lệ nêu trên nhưng chỉ 12 ca relevance và 3 ca cho mỗi nhóm filter; không phải benchmark đại diện.
- Inference thật và semantic evaluation của 40 generated answers: **NOT RUN**, chờ endpoint/model và opt-in rõ ràng của owner.
- Active M5 chain, PostgreSQL, lịch sử blockchain và signed audit không bị reset/recreate hoặc sửa. M5 chain vẫn in-memory; M6 không xử lý giới hạn disaster recovery đó.

**Khuyến nghị:** chấp nhận M6 về triển khai kỹ thuật/API và kiểm soát dữ liệu với điều kiện ghi nhận độc lập retrieval còn yếu ở top-1, không có inference thật và semantic review, và migration/API chỉ được xác minh trên Compose cô lập. Không coi 40/40 retrieval tuned là bằng chứng chất lượng LLM. Chủ dự án nên xem xét challenge retrieval cùng các giới hạn trên trước khi chấp nhận chất lượng giải thích.

## Bổ sung: xác minh provider thật và retrieval v2

### Trạng thái provider

Kiểm tra `.env` theo dạng chỉ báo có/không, không in giá trị model hoặc secret: `LLM_PROVIDER` local hiện là provider không được hỗ trợ (`anthropic`), model có giá trị nhưng `LLM_API_BASE_URL` và `LLM_API_KEY` không có. Adapter chỉ chấp nhận `disabled` hoặc `openai_compatible`; isolated stack trước đó cũng ở trạng thái `disabled`. Không có endpoint/model hợp lệ, bearer token cho evaluation hoặc owner opt-in trong phiên này. Vì thế real inference sáu case và batch 40 ca đều **NOT RUN**; không có request tới provider, mock/fallback không được tính thành inference thật.

Biến cấu hình, hosted/local endpoint, cách tách project/cổng để bảo vệ M5, lệnh batch có cờ opt-in và incident map được ghi tại [`real-llm-validation-setup.md`](real-llm-validation-setup.md). Trước inference thật, owner cần chọn endpoint/model, đặt key bằng secret manager/local environment, đảm bảo payload được phép gửi, chuẩn bị fixture + map trong DB cô lập và phê duyệt rõ ngân sách. Không thay đổi JWT hoặc audit signing secret.

Harness 40 ca được cập nhật để gọi retrieval API riêng trước explanation, ghi expected section rank, phân biệt provider call attempted / response received / answer accepted, citation rejection, provider failure và latency provider so với latency HTTP. Khi chạy thật, factual accuracy, semantic groundedness và procedural correctness vẫn phải có human review; auto phrase scan không thay thế người đánh giá.

### Development tuning và challenge độc lập mới

Giữ nguyên challenge v1 và raw cũ: **6/12 top-1, hit@3 9/12, MRR 0.6111**. Không chạy lại hoặc dùng challenge v1 để tune. Development fixture mới 27 ca được chạy trước chỉnh sửa: top-1 **20/27**, hit@3 **25/27**, MRR **0.830247** (`raw/retrieval-dev-v1-baseline.json`). Các lỗi chủ yếu là truy vấn không dấu, cách gọi khác với SOP và section title bị body dài lấn điểm.

Thay đổi nhỏ trong `bm25-v2-title25-vn-aliases`: accent-folding cho query, alias hữu hạn bám thuật ngữ SOP và tăng trọng số title 2.5 lần. Không thay corpus/policy. Cùng dev set sau thay đổi đạt top-1 **24/27**, hit@3 **26/27**, MRR **0.935185** (`raw/retrieval-dev-v1-revised.json`). Đây là kết quả trên development data, không phải benchmark độc lập. Cấu hình đóng băng và hash nằm tại [`m6-retrieval-v2-manifest.json`](../../evaluation/m6-retrieval-v2-manifest.json).

Sau khi đóng băng v2, challenge mới được băm trước rồi chạy một lần, không tuning tiếp: `llm/eval/challenge/m6-retrieval-challenge-v2.jsonl`. Kết quả **7/12 top-1**, **11/12 hit@3**, **MRR 0.752778**; target đứng trước distractor **7/9** cặp đủ điều kiện. Filter version sai và product sai đều **3/3**. Ba query insufficient-source trả no-result **0/3**: BM25 vẫn trả section do trùng từ phổ thông; hiện chưa có relevance threshold được hiệu chuẩn. Challenge v2 khác hẳn v1, vì vậy không tuyên bố metric đã cải thiện so với v1. Không sửa code hoặc query sau kết quả này. Raw, hash input và manifest tại `raw/retrieval-challenge-v2.{json,txt}`, `raw/retrieval-challenge-v2-input-sha256.txt` và `docs/evaluation/m6-retrieval-v2-manifest.json`.

### Kết luận cho giai đoạn này

RAG, retrieval cục bộ và các API giữ được hành vi đã kiểm trước đó; retrieval v2 giúp truy vấn dev tiếng Việt/không dấu nhưng challenge mới còn cho thấy ranking/rejection chưa đáng tin cậy với query không liên quan. Citation ID/quote giả bị từ chối bởi validator test; metadata của provider được giữ lại ngay cả khi nội dung bị loại để không che request hoặc chi phí. Không có provider thật nên các metric generated-answer, provider latency/availability và semantic review là **NOT RUN**.

**Khuyến nghị nghiệm thu M6:** có thể chấp nhận hạ tầng kỹ thuật với điều kiện ghi nhận retrieval challenge mới còn yếu (đặc biệt insufficient-source 0/3), real LLM chưa xác minh, và 40-case chỉ có retrieval fixtures/dry-run. Chưa chấp nhận chất lượng giải thích LLM như đã được xác thực. Cần một vòng development có ngưỡng relevance được kiểm định, challenge độc lập mới và inference thật có owner opt-in trước khi nâng mức kết luận.

### Xác minh offline sau response provider HTTP 200 bị từ chối

Điều chỉnh trạng thái của báo cáo trước: sau đó đã có một request OpenAI-compatible HTTP 200, theo evidence `docs/evaluation/m6-real-llm-one-call-55343690a58d4.json`. Provider response không được application chấp nhận (`source_mode=none`); đây không phải thành công inference/application. Evidence cũ thiếu `finish_reason` và raw generated text đã bị loại bỏ, do đó nguyên nhân cụ thể giữa completion truncation, JSON, schema và citation không thể xác định. Không retry request này.

Bản offline bổ sung trong lần rà soát tiếp theo phân tách provider status, `finish_reason`, parse, schema, citation và evidence, ghi token usage cùng category an toàn nhưng không lưu prompt/response chưa xác minh. Với GPT-6 Luna, adapter chuyển sang strict JSON Schema Chat Completions; Pydantic vẫn kiểm tra giới hạn cục bộ, và citation verification vẫn độc lập/bắt buộc. Prompt v2 loại trùng lặp 45 bản ghi giữa evidence và source map; 14.225 token cũ không thể phân bổ chính xác theo thành phần vì không lưu prompt/tokenizer breakdown. SOP hiện phân biệt hướng dẫn hiện hành tại evidence cutoff và phiên bản có hiệu lực tại incident time.

Các ca mock/local bao gồm `finish_reason=length`, malformed/incomplete JSON, schema mismatch, ID citation không được truy xuất, quote không khớp, citation hợp lệ, provider success nhưng application rejection và sensor evidence hợp lệ dù thiếu dữ liệu liên lạc. Đây không phải inference thật. Targeted M6 regression chạy trong Compose project cô lập với `LLM_PROVIDER=disabled`: **23 passed, 6 dependency deprecation warnings**; log `docs/evaluation/m6-real-validation-offline-tests.txt`. Không có provider request nào được gửi trong lần kiểm tra offline. Chỉ cân nhắc một request provider mới sau owner approval riêng.

### Kết quả một request thật sau phê duyệt mới

Owner đã phê duyệt đúng một request mới; không retry các request cũ. Backend isolated được cập nhật bằng image có tag riêng, chỉ recreate backend với `--no-deps`; DB/chain isolated giữ nguyên. Preflight xác nhận key trong backend khớp file `.env.m6-real-llm` nhưng không in key, file bị Git ignore, QUALITY login hợp lệ, migration `0006` ở head, retries 0, fallback false. Evidence snapshot có 45 readings, 48 references, incident revision 1 và các section SOP áp dụng, bao gồm `HIGH_EXCURSION`.

Provider/model/config tương thích đã hoạt động tới inference: GPT-6 Luna trả HTTP 200 với model `gpt-6-luna`; prompt v2 dùng 9.450 input tokens. Completion chạm trần 1.200 tokens và `finish_reason=length`. Parser báo `completion_limit_reached`; schema và citation stages `not_run`, `citation_verification=not_applicable`. Ứng dụng fail-closed: `source_mode=none`, `explanation_status=insufficient_evidence`, không có citation/content chưa xác minh. Evidence references của response khớp snapshot trước request. Diagnostics an toàn được lưu, raw completion/prompt không được lưu. Đây là provider-call success nhưng application-validation failure, không phải explanation thành công.

Raw đã khử nội dung: `docs/evaluation/m6-real-llm-validation-one-call.json`. Output cap 1.200 được xác nhận chưa đủ cho request này. Không có request nào khác được gửi; mọi lần thử tiếp theo cần tăng cap có kiểm soát và owner approval mới.

### Chuẩn bị và kết quả request tiếp theo

Sau lỗi `completion_limit_reached`, đặt `LLM_MAX_OUTPUT_TOKENS=3200` chỉ trong `.env.m6-real-llm` đã Git-ignore. Backend cô lập xác nhận cap mới cùng `gpt-6-luna`, strict JSON Schema, `reasoning_effort=none`, zero retries và disabled fallback; active M5 backend/container không đổi. Mock payload xác nhận `max_completion_tokens=3200`, đủ 9 trường schema và các trường citation bắt buộc. Response cấu trúc tối thiểu serialize thành 313 ký tự; không thể bảo đảm output ngôn ngữ dài sẽ luôn vừa 3.200 token.

M6 + config tests: **28 passed, 6 dependency deprecation warnings**, log `docs/evaluation/m6-real-llm-3200-offline-tests.txt`. Evidence/SOP/QUALITY preflight trùng snapshot gần nhất (45 readings, 48 refs, evidence hash không đổi, HIGH_EXCURSION SOP có trong kết quả). Sau phê duyệt riêng, request ref `M6-REAL-VALIDATION-3200-90963f4153b34039b78413a9ed1fd737` được gửi đúng một lần. Provider trả HTTP 200, `finish_reason=stop`, 9.450 input tokens, 2.405 output tokens, latency 19.989 ms. Ứng dụng chấp nhận `source_mode=llm`, `explanation_status=draft`; parse/schema/evidence/citation stages passed, 13 citation được verifier xác nhận thuộc source set. Evidence references khớp snapshot. Record đã khử text tại `docs/evaluation/m6-real-llm-validation-3200-one-call.json`; request plan cập nhật tại `docs/evaluation/m6-real-llm-3200-pending-request.json`. Không có 40-case batch hoặc request tiếp theo.

Đối chiếu nội dung với snapshot: số đo, M3 detection, policy version/threshold, cutoff, SOP effective date, không có M4 prediction/M5 disposition và quyết định chỉ thuộc Quality Officer đều khớp. Không diễn đạt nhiệt độ chưa biết thành an toàn. Summary có một câu tự hỏi rồi tự sửa về reading time/cutoff; kết luận đúng nhưng diễn đạt gây hiểu nhầm. Đây là đối chiếu của agent, chưa phải independent human semantic review; draft lưu append-only nên không sửa nội dung lịch sử.

### Regression sau thay đổi cuối

- M6 RAG backend tests: **17 passed**, 6 dependency deprecation warnings; includes a mock-only API path that rejects fabricated citations while retaining call metadata; raw `raw/m6-rag-tests-real-validation.txt`. This is not real inference.
- Evaluator mặc định: `DRY_RUN`, 40 case, `provider_invoked=false`; raw `raw/explanation-eval-dry-run-final.json` / `.txt`.
- Stack `m6acceptance`: backend runtime build xong và chỉ backend service được recreate; DB/worker/frontend/chain cô lập không bị restart. Authenticated HTTP trả retrieval API version `bm25-v2-title25-vn-aliases` với `MONITORING` ở rank 1 cho query không dấu. Fallback HTTP trả `source_mode=deterministic_fallback`, `provider=disabled`, citation `passed`; raw `raw/isolated-http-retrieval-v2.json`.
- Retrieval config file hashes sau challenge vẫn khớp manifest (`retrieval.py` `ee5e0c…c08a`, API `llm.py` `9b7f3b…3841`); không có chỉnh retrieval sau challenge v2.
- `git diff --check` passed. Không chạy lại full suite M1–M5 trong lượt này; log full suite 310 passed ở acceptance trước vẫn được giữ, và M6-specific tests đã chạy lại sau các thay đổi liên quan.

## Chuẩn bị review người và đánh giá provider thật (2026-11-17)

### Bản giải thích đã được chấp nhận

Đã đọc draft qua luồng API chỉ đọc đã xác thực bằng tài khoản QUALITY: login, history và detail đều HTTP 200. Draft `5aa50674-416b-4eeb-956c-8cff8f02514f` vẫn append-only, `source_mode=llm`, `draft`; schema/evidence/citation validation pass. Có 13 citations, 48 evidence references và 45 reading references. Ghi chú đã khử nội dung tại `raw/accepted-explanation-human-review-prep.json`; checklist người rà soát tại `raw/accepted-explanation-human-review-checklist.md`. Tóm tắt chứa một câu hỏi tu từ rồi tự đính chính về cutoff, gây khó hiểu; không sửa bản ghi. Verifier kiểm ID/quote không chứng minh semantic entailment. Human semantic review vẫn chưa thực hiện.

### Tách loại đánh giá

- Fixture `llm/eval/cases/m6-cases.jsonl`: retrieval fixture đã được chỉnh câu hỏi; lịch sử **34/40** lần đầu và **40/40** sau khi sửa sáu query chỉ đo truy xuất.
- Challenge retrieval độc lập v1: top-1 **6/12**, hit@3 **9/12**, MRR **0,6111**.
- Challenge retrieval độc lập v2: top-1 **7/12**, hit@3 **11/12**, MRR **0,752778**; no-result cho query thiếu nguồn **0/3**. Không dùng challenge này để chỉnh prompt/retriever.
- Runner 40 ca cũ là DRY_RUN/retrieval-only; không đánh giá câu trả lời sinh. Một real-provider draft thành công hiện có là một mẫu duy nhất, không đại diện accuracy.
- Citation ID/quote validation là kiểm tra máy; sự hỗ trợ ngữ nghĩa, tính đúng sự thật và clarity cần reviewer độc lập. Không có human score nào được giả định.

### Manifest và preflight riêng

Đã đóng băng manifest v1 tại `docs/evaluation/m6-real-explanation-manifest-v1.json`, hash nội dung (không gồm trường hash) `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`. Nó có 40 case ID, 40 incident UUID/business references khác nhau và 40 shipment khác nhau. Pilot đề xuất là `M6R-001`, `M6R-008`, `M6R-016`, `M6R-021`, `M6R-036`; 35 case còn lại chỉ chạy sau phê duyệt riêng. Incident map: `docs/evaluation/m6-real-explanation-incident-map-v1.json`.

Preflight chạy trong Compose project mới `coldchain-m6-evalprep`, DB volume `coldchain-m6-evalprep_pgdata`, frontend port 3107 và chain riêng port 18549. Import chỉ đọc release seed-11 vào DB cô lập; causal M3 replay không đổi mở 146 incident trên 200 shipment, 37.536 evaluation và 1.007 revisions. 40 case được chọn có incident/shipment duy nhất, evidence package đủ theo adapter, QUALITY history GET 40/40 HTTP 200. 40 truy vấn SOP được kiểm: 38 có nguồn teaching-approved phù hợp; hai trường hợp chủ đích sai product/version trả no applicable source. Case-level raw ở `raw/seed11-40-case-preflight.json`. DB khác `m6acceptance` và stack M5 không được gộp hoặc sửa. Route/ocean metadata không có trong evidence package; ca delayed yêu cầu model không tự kết luận tuyến biển nếu nguồn được phép không cung cấp.

M4 prediction và M5 disposition rows trong DB eval prep đều bằng 0; các case kỳ vọng nói rõ prediction/disposition không có, không bịa dữ kiện. Tất cả package hiện có evidence cho incident, vì vậy “thiếu bằng chứng” trong manifest là thiếu căn cứ cho claim cụ thể (ví dụ nhiệt độ trong gap hoặc nguyên nhân), không phải status `insufficient_evidence` toàn package. Tỷ lệ status API `insufficient_evidence` chưa được kiểm tra bằng một incident không có bất kỳ source nào. Revisions được xem ở snapshot cutoff; việc loại revision phát sinh sau cutoff tiếp tục được bảo đảm bởi test causal hiện hành, nhưng replay seed-11 không tạo timestamp `created_at` phân biệt giữa nhiều revisions trong cùng một transaction. Ocean route không được suy ra từ route metadata simulator.

### Kế hoạch token và approval gate

Một mẫu đã thành công trước đây dùng 9.450 input và 2.405 output token; đây chỉ là một điểm tham khảo. Dự toán dùng 12.000 input/case và cap output 3.200: pilot 5 call ~60.000 input, tối đa 16.000 output; 35 case ~420.000 input, tối đa 112.000 output; full 40 ~480.000 input, tối đa 128.000 output. Input là ước lượng, không phải giới hạn; không ước lượng tiền khi chưa xác nhận giá hiện hành. Mọi lỗi, truncation và abstention giữ trong mẫu số theo rubric trong manifest.

Isolated backend readiness báo provider `configured`, model `gpt-6-luna`, retries 0, fallback tắt; startup/readiness không gửi provider request. Kết quả và metadata đã khử secret ở `raw/real-llm-eval-readiness.json`. Kế hoạch 5 request cụ thể, request refs, UUID và cutoff tại `raw/real-llm-pilot-pending-approval.json`. Khi ghi phần chuẩn bị này, trạng thái là `PREPARED_NOT_SENT_WAITING_OWNER_APPROVAL`; sau đó owner phê duyệt và đúng năm call đã được thực hiện như phần kết quả bên dưới. 35 call còn lại cần approval thứ hai.

### Regression offline

M6 backend/retrieval/citation regressions trong test service cô lập, với `LLM_PROVIDER=disabled` và API key rỗng: **23 passed, 7 dependency/cache warnings**, log `raw/real-eval-preparation-m6-tests.txt`. Có health HTTP 200 và readiness chỉ đọc; không gọi OpenAI. Canonical seed-11 files, policy, M4 artifacts, active M5 database/chain, signed audit records và accepted explanation không bị sửa. Không dùng reserved seed 22/33/44/55/66.

**Trạng thái:** hạ tầng và manifest sẵn sàng cho owner review/approval pilot; chưa có kết quả 5-case provider, semantic human review hay 40-case generation. Đây chưa phải bằng chứng chất lượng tổng thể của LLM.

### Kết quả pilot real-LLM 5 ca sau phê duyệt owner

Owner đã phê duyệt đúng năm request trong pilot; năm request được gửi tuần tự một lần/case qua project Docker cô lập `coldchain-m6-evalprep`. Không gửi thêm request nào. Kết quả đã khử nội dung nằm tại `raw/real-llm-pilot-result.json`, đối chiếu evidence pre-call tại `raw/real-llm-pilot-precall-snapshot.json` và hậu kiểm tại `raw/real-llm-pilot-postcall-consistency.json`. Private key, prompt và văn bản giải thích không được ghi vào các báo cáo này.

| Case | HTTP | Provider/model | Kết quả API | Citation đã kiểm tra | Input/output token | API latency |
|---|---:|---|---|---:|---:|---:|
| M6R-001 | 200 | OpenAI-compatible / `gpt-6-luna` | `llm`, `draft` | 3 | 14.045 / 1.338 | 14,148 ms |
| M6R-006 | 200 | OpenAI-compatible / `gpt-6-luna` | `llm`, `draft` | 3 | 7.805 / 1.356 | 13,354 ms |
| M6R-016 | 200 | OpenAI-compatible / `gpt-6-luna` | `llm`, `draft` | 3 | 12.730 / 1.336 | 12,446 ms |
| M6R-021 | 200 | OpenAI-compatible / `gpt-6-luna` | `llm`, `draft` | 2 | 6.992 / 1.096 | 10,110 ms |
| M6R-036 | 200 | OpenAI-compatible / `gpt-6-luna` | `llm`, `draft` | 5 | 7.763 / 1.123 | 11,355 ms |
| **Tổng** | **5/5** |  | **5/5 draft được API chấp nhận** | **16** | **49.335 / 6.249** | **12,446 ms median API latency** |

Các response đều có `citation_verification=passed`; mọi citation IDs/quotes được báo là thuộc source set đã cung cấp. Hash tham chiếu evidence sau request khớp snapshot trước request ở **5/5**. Cả năm draft có disclaimer QUALITY. Phrase scan tĩnh không phát hiện câu an toàn bị cấm (5/5); đây không phải review ngữ nghĩa. Case M6R-016 chỉ có bằng chứng delayed reading/gap/warning trong source ứng dụng, không có route hay record kết nối độc lập nên không được xem là xác minh tuyến ocean.

**Hạn chế quan trọng của log:** container backend dùng cho năm call không trả hoặc lưu các trường `provider_finish_reason` và diagnostics theo từng bước. Vì vậy báo cáo ghi provider response và application-accepted draft dựa trên HTTP 200 cùng `source_mode=llm`, `draft`, citation pass; `finish_reason`, trạng thái parse riêng, schema riêng và evidence validator riêng là **không được runtime này ghi nhận**, không suy đoán là đã đo trực tiếp. Đây là lỗi observability cần sửa trước benchmark chính thức. Không có raw completion nên không thể tiến hành review lại semantic từng phát biểu từ artifact này.

Preflight retrieval phát hiện hai coverage miss: M6R-006 không lấy section `LOW_EXCURSION`, M6R-036 không lấy `QUALITY_REVIEW`. Citation validator đã xác minh các citation trả về có trong source set, nhưng sanitized log không giữ section ID từng citation; do đó chưa thể xác nhận các citation đó hỗ trợ đúng chủ đề LOW hoặc quyền QUALITY. Các miss không được dùng để tune hoặc đổi query sau pilot. Yêu cầu review người và/hoặc một lần chạy test offline có lưu section IDs đã được xác thực cần hoàn tất trước khi kết luận procedural quality.

Pilot không phải đánh giá 40 ca. Năm ca không đại diện độ chính xác, groundedness, semantic relevance, latency phân phối hay mức an toàn. Human factual/semantic/procedural review vẫn **NOT REVIEWED**. 35 ca còn lại **NOT RUN** và cần phê duyệt riêng. Không thay đổi prompt, retrieval, schema, policy hay model sau pilot. Active M5 chain/database được bảo toàn; chỉ project DB/chain cô lập được dùng. Docker daemon hiện không cho phép truy cập (`permission denied`), nên không thực hiện thêm truy vấn hậu kiểm trực tiếp trong lượt ghi báo cáo này; báo cáo dựa trên raw API result đã lưu và snapshot trước call.

**Trạng thái:** có bằng chứng cho 5 provider response thật và 5 draft được API chấp nhận, nhưng M6 chưa được nghiệm thu về chất lượng ngôn ngữ. Cần khắc phục observability, review độc lập các draft qua luồng API đã xác thực và xử lý coverage gap retrieval trong development set trước khi xin phê duyệt cho 35 ca.

## Kiểm toán offline sau pilot

Kiểm toán chi tiết tại [`post-pilot-audit.md`](post-pilot-audit.md); worksheet từng case tại `raw/real-llm-pilot-case-review-worksheet.md`; raw API QUALITY claims, exact evidence references, temporal reconciliation, diagnostics và Docker facts ở thư mục `raw/`. Kết luận mới nhất: diagnostics **không được tạo** bởi image pilot cũ (không phải chỉ bị reporter bỏ sót); API/DB 5/5 không có trường diagnostics. Reporting runner cũng có thiếu sót độc lập và đã được sửa/test. Reviewer phát hiện claim M6R-016 gán detection ngày 14/9 là sau cutoff ngày 17/11. M6R-006 `LOW_EXCURSION` (rank 6) và M6R-036 `QUALITY_REVIEW` (rank 9) bị top-k=5 cắt; applicability filters không loại. Kế hoạch retrieval v3 được tách riêng tại `docs/evaluation/m6-retrieval-v3-proposal.md`; chưa triển khai hoặc tune trên pilot. Human semantic review vẫn chờ người đánh giá. **NO-GO** cho 35 case cho đến khi các vấn đề trên được xử lý và phiên bản được khóa lại. Manifest hash vẫn nguyên trạng; năm pilot không còn là mẫu độc lập.
## Remediation offline sau audit pilot (2026-11-17)

Phương án khôi phục image M5, evidence metadata, lệnh Compose chỉ đọc và rollback gate được ghi riêng tại [`deployment-safety-and-m5-image-recovery.md`](deployment-safety-and-m5-image-recovery.md). Compose M6 yêu cầu image tag và project name riêng để fail closed khi thiếu cấu hình; historical Compose M5 giữ nguyên trong Git commit M5.

Không gửi provider request nào và không chạy 35 case còn lại. Năm pilot vẫn là bằng chứng lịch sử; diagnostics bị thiếu trong runtime cũ không được dựng lại. Manifest v1 giữ hash canonical `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244` (JSON canonical, trường hash loại khỏi digest).

### Runtime và diagnostics

Image backend được build từ source hiện tại và chỉ backend trong project cô lập `coldchain-m6-evalprep` được recreate với `--no-deps`. `/api/llm/readiness` hiện trả runtime `m6-post-pilot-temporal-v3`, prompt `response_draft/v3`, retriever `bm25-v2-title25-vn-aliases`, model cấu hình `gpt-6-luna`; readiness không gọi provider. DB vẫn có 5 explanation records trước/sau; chain cô lập giữ block `0x1`; DB, chain, frontend còn healthy. Test mocked xác nhận response serialization và persistence diagnostics trong output/API record/request metadata. Chẩn đoán lịch sử của năm draft vẫn vắng mặt.

Evaluation runner giờ cho phép manifest version, runtime, prompt, provider/model, retrieval version và temporal stage diagnostics; raw completion, prompt, credentials không được sao chép. Metadata không suy đoán `finish_reason` hay stage cũ.

### Hàng rào thời gian

Evidence adapter chuẩn hóa cutoff có timezone về UTC; vẫn lọc riêng `event_at <= cutoff` và `received_at <= cutoff`. Bản package bổ sung facts UTC có source reference cho incident/revision, readings, M3 detections, gaps, warnings, M4/M5 timestamps, ngày hiệu lực SOP và chênh lệch detection-window/latest-observation. Prompt v3 đưa facts máy tính trước vào model, phân biệt thời điểm SOP hiệu lực ở incident so với cutoff.

Schema mới có `temporal_claims`; validator so khớp reference/field/timestamp/relation với facts và từ chối mâu thuẫn cutoff hẹp, rõ ràng. Fixture tái tạo lỗi M6R-016 bị từ chối. Kiểm tra này **không phát hiện mọi lỗi diễn đạt tự nhiên**; cấu trúc và citation hợp lệ không thay thế reviewer đọc claim. Draft đã lưu trước đó không bị sửa.

### Retrieval

Không đổi production retrieval v2. `LOW_EXCURSION` rank 6/9 và `QUALITY_REVIEW` rank 9/9 trong pilot do top-k=5; metadata vẫn applicable. Đây là ranking miss. Development v1: BM25 v2 24/27 top-1, 26/27 hit@3, MRR 0.935185, khớp raw revised trước đó. Prototype intent v3 đạt đúng các số đó, không cải thiện; 15/27 query được intent duy nhất. Đây chỉ là phép thử development đã biết, không độc lập, không dùng pilot như validation. Đề xuất retrieval v3, tradeoff và raw nằm ở [`m6-retrieval-v3-proposal.md`](../../evaluation/m6-retrieval-v3-proposal.md) cùng `raw/retrieval-bm25-v3-intent-dev-only.json`. Citations vẫn được kiểm độc lập; semantic entailment còn cần con người.

### Evidence và kiểm thử

- Human-review worksheet năm case có claim groups, evidence refs và citations per claim tại `raw/real-llm-pilot-case-review-worksheet.md` và `raw/real-llm-pilot-quality-api-review-input.json`. Trạng thái của mọi judgment ngữ nghĩa vẫn `CHƯA REVIEW`; không tự động đánh dấu đạt.
- Kế hoạch riêng cho toàn package thiếu evidence và thiếu M4/M5 là [`supplemental-evaluation-plan-v1.md`](supplemental-evaluation-plan-v1.md), ngoài manifest v1.
- Targeted offline M6: **31 passed, 6 cảnh báo deprecation**; gồm temporal safeguard, M6 RAG/API, provider mock, persistence và evaluation diagnostics. Provider bị disable trong lệnh; log `raw/m6-post-pilot-offline-tests.txt`. First run bắt expected-value fixture sai UTC; log được giữ ở `raw/m6-post-pilot-offline-tests-first-run.txt`. Bản cuối thêm ca timestamp thiếu/ngây thơ và cả 31 test đều qua.
- Readiness, service health, 5-row count và chain height được ghi ở `raw/m6-post-pilot-runtime-and-preservation.json`. Không gọi Compose project M5; DB và chain M5 giữ nguyên container IDs đã ghi nhận; không chạy full M0–M5 suite.
- **Giới hạn Docker tag cần xử lý trước khi recreate M5:** build đầu dùng tag dùng chung `coldchain-backend:local`. M5 backend đang chạy vẫn dùng immutable image ID cũ và không bị recreate, nhưng image ID đó không còn trong image store để gắn lại tag. M6 hiện đã chuyển sang tag riêng `coldchain-backend:m6-evalprep`; tag chung `coldchain-backend:local` vẫn trỏ M6 runtime image. Không recreate M5 Compose cho tới khi owner khôi phục đúng M5 image/tag. Đây là ảnh hưởng tag local, không phải thay đổi dữ liệu hay container đang chạy.

### Quyết định

**NO-GO cho pilot mới ở thời điểm hiện tại.** Hàng rào UTC và diagnostics đã được triển khai, nhưng cần human review độc lập năm draft, rà soát code/review temporal false-positive/false-negative, và đóng băng runtime+prompt/schema trước khi xin chạy một pilot mới nhỏ. Prototype retrieval chưa nâng metric development; cần tập development mới để quyết định intent/relevance threshold. Không chạy 35 case, không sửa manifest/hash và không sửa năm bản ghi append-only.

## Bổ sung: candidate M5 cô lập và chuẩn bị freeze M6 (2026-11-17)

Candidate M5 được kiểm thử trong Compose project độc lập `coldchain-m5-validation-8c9bad1-20261117`, trên fixture synthetic mới, ports/volumes/secrets/project riêng. Backend suite **229 passed**, Hardhat **6 passed**, health/frontend endpoint **4/4 HTTP 200**; workflow API xác minh 7 business references, reconciliation `7/7 MATCH`, signed audit hợp lệ và role/transition sai bị từ chối. Chi tiết và giới hạn provenance ở [`deployment-safety-and-m5-image-recovery.md`](deployment-safety-and-m5-image-recovery.md), raw summary [`m5-candidate-validation-summary.json`](raw/m5-candidate-validation-summary.json). Kết quả cho phép owner review candidate cô lập; không chứng minh binary identity với image M5 gốc.

M6 Compose tag guard được kiểm độc lập trên YAML: 8 service image refs cần biến rõ ràng; tag M6 tách khỏi tags M5; không có `container_name` hay external volumes. Raw [`m6-compose-tag-guard-offline.txt`](raw/m6-compose-tag-guard-offline.txt). `docker compose ... config --images` resolve tags riêng `coldchain-backend:m6-evalprep`, `coldchain-backend:m6-evalprep-test`, `coldchain-chain:m6-evalprep`, `coldchain-frontend:m6-evalprep`.

Đề xuất freeze có source manifest hash, runtime image ID, prompt/schema/retriever/adapter/evaluation runner versions, cấu hình output 3.200/retry 0/fallback off và manifest v1 hash tại [`m6-release-candidate-freeze-proposal.json`](m6-release-candidate-freeze-proposal.json). Trạng thái **PROPOSED_NOT_FROZEN** do source worktree dirty và vấn đề temporal/retrieval/semantic review còn mở. Manifest v1 không đổi; năm pilot giữ nguyên; 35 ca **NOT RUN**; không có provider request mới.

Worksheet review người vẫn chưa có đánh giá tại [`real-llm-pilot-human-review-packet.md`](real-llm-pilot-human-review-packet.md). M6R-016 temporal error và retrieval misses M6R-006/M6R-036 được nêu riêng. Không tự động đánh dấu semantic support đạt.

Trong lượt kiểm tra cuối, Docker CLI báo `permission denied` tại socket context `desktop-linux`; do đó không build lại test image, chạy Docker tests hoặc xác nhận lại trạng thái hiện thời của container. Host pytest cũng bị chặn do `eth_account` thiếu trong backend venv. Standalone YAML/config assertions đã qua; targeted Docker regression trước đó có **35 passed**, nhưng không tính là chạy lại trong lượt này. Xem chi tiết giới hạn trong deployment-safety doc và raw.

### Khuyến nghị hiện tại

- M5 candidate recovery readiness: **GO để owner review kết quả cô lập**, không phải phê duyệt triển khai.
- M5 production tag restoration: **NO-GO**; image gốc không có và binary rollback chính xác không khả dụng. Cần approval tường minh trước mọi thay đổi tag/container.
- M6 pilot provider mới: **NO-GO** cho tới khi hoàn tất human review và freeze tái lập được.
- M6 release acceptance: **NO-GO**; semantic review chưa xong, temporal error lịch sử và retrieval misses còn mở, 35 ca chưa chạy.

## Bổ sung: phiếu operator review và regression offline đã chạy (2026-11-17)

Năm phiếu ngắn, riêng theo ca được lập từ bản đọc QUALITY chỉ-đọc; từng phiếu đặt claim cạnh các source refs, các mốc `event_at`/`received_at`, cutoff và citation/quote SOP. Mỗi phiếu để trống PASS/FAIL/NEEDS_MORE_EVIDENCE, reviewer ID, thời gian và rationale. Index: [`human-review/README.md`](human-review/README.md); hồ sơ chi tiết mở rộng: [`real-llm-pilot-human-review-packet.md`](real-llm-pilot-human-review-packet.md). Các concern nổi bật gồm lỗi temporal M6R-016, retrieval miss M6R-006/M6R-036, semantic support chưa được con người xác nhận, và readability cần reviewer đánh giá. Không sửa bản ghi explanation đã chấp nhận.

Kiểm kê 209 thay đổi Git, nhóm sáu phần và commit plan được ghi tại [`git-change-audit-and-commit-plan.md`](git-change-audit-and-commit-plan.md). Không có file staged. Private `.env` files không được commit; request question, full QUALITY extract và raw LLM evidence được đánh dấu để giữ trong vùng truy cập hạn chế cho tới khi owner duyệt phạm vi chia sẻ.

Sau khi dùng quyền truy cập Docker được cấp cho kiểm tra cô lập, test image M6 riêng được build thành `coldchain-backend:m6-evalprep-test` (`sha256:27fb66…`) và chạy đúng 5 test file M6: **35 passed, 6 deprecation warnings**. Provider bị disable, retries 0, không có provider call. Runtime readiness trong backend M6 đang chạy và test image đều khớp runtime `m6-post-pilot-temporal-v3`, prompt v3/hash `e1bc…`, schema v2/hash `9a11…`, adapter `openai-chat-completions/v1`, retriever `bm25-v2-title25-vn-aliases`; test image báo provider `not_configured`. SHA-256 của 7 file RAG/validation quan trọng trong runtime container khớp worktree. Tuy nhiên image không gắn Git source-revision label và worktree dirty, nên không khẳng định provenance của mọi file là một commit sạch. Raw: [`m6-offline-regression-current.txt`](raw/m6-offline-regression-current.txt), [`m6-offline-runtime-and-test-image-comparison.json`](raw/m6-offline-runtime-and-test-image-comparison.json).

Docker build ban đầu bị sandbox chặn ghi vào `~/.docker/buildx/activity`; sau bước review quyền truy cập, build và test chạy được bằng context hiện có, không dùng sudo. M5 container IDs đọc lại vẫn là backend `490e729589f7`, worker `3719d773c93c`, chain `ab2856a5aa55`, frontend `a92ba138453c`, DB `a79299b74fdb`, đều healthy; không có M5 deployment/tag/volume mutation. Không kiểm tra lại chain height trong lượt này.

### Quyết định cập nhật

- **M5 candidate recovery:** GO để owner review kết quả cô lập; không phải triển khai production.
- **M5 production tag restoration:** NO-GO; image gốc không còn để rollback chính xác, cần approval owner riêng cho mọi mutation.
- **M6 small real-provider pilot mới:** **NO-GO hiện tại**, kể cả sau khi hồ sơ được bàn giao; trước đó cần hoàn tất human review, quyết định rõ hai retrieval miss, và khóa build/source provenance. Không có provider call trong lượt này.
- **M6 acceptance:** NO-GO; semantic review vẫn chờ, lỗi thời gian lịch sử cần đánh giá/ghi nhận, retrieval coverage chưa đóng và 35 provider case là NOT RUN.
