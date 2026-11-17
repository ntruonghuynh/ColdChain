# Cấu hình và chạy xác minh LLM thật cho M6

## Trạng thái hiện tại

Adapter hiện hỗ trợ đúng hai giá trị `LLM_PROVIDER`: `disabled` và `openai_compatible`. File `.env` local hiện đặt một provider khác, có tên model nhưng không có `LLM_API_BASE_URL` hoặc `LLM_API_KEY`; giá trị provider đó không được adapter hỗ trợ. Readiness của stack cô lập gần nhất là `provider_status=not_configured`. Không có request đến nhà cung cấp được gửi trong giai đoạn này.

## Biến môi trường của ứng dụng

| Biến | Bắt buộc / ý nghĩa |
|---|---|
| `LLM_PROVIDER` | `openai_compatible` để bật adapter; `disabled` giữ provider tắt |
| `LLM_MODEL` | Tên model chính xác mà endpoint nhận |
| `LLM_API_BASE_URL` | URL gốc OpenAI Chat Completions-compatible; client tự nối `/chat/completions`, ví dụ URL gốc kết thúc bằng `/v1` |
| `LLM_API_KEY` | Key qua environment cho endpoint cần Bearer auth; có thể để trống nếu endpoint local không dùng auth |
| `LLM_TIMEOUT_S` | Timeout request; adapter giới hạn trong 1–120 giây |
| `LLM_MAX_RETRIES` | Số retry, adapter giới hạn tối đa 2; đặt `0` để không retry |
| `LLM_MAX_OUTPUT_TOKENS` | Giới hạn token đầu ra, service giới hạn tối đa 4096 |
| `LLM_FALLBACK_ENABLED` | Đặt `false` trong real-provider validation để lỗi provider không bị che bằng fallback |
| `LLM_PRICE_INPUT_PER_MTOK_USD` | Giá input mỗi triệu token; tùy chọn, để trống nếu chưa xác định |
| `LLM_PRICE_OUTPUT_PER_MTOK_USD` | Giá output mỗi triệu token; tùy chọn, để trống nếu chưa xác định |

Ví dụ cho dịch vụ hosted tương thích (thay bằng endpoint/model đã được owner duyệt):

```dotenv
LLM_PROVIDER=openai_compatible
LLM_MODEL=<model-id-cua-nha-cung-cap>
LLM_API_BASE_URL=https://<host-da-duoc-duyet>/v1
LLM_API_KEY=<nap-tu-secret-manager-hoac-shell-local>
LLM_TIMEOUT_S=30
LLM_MAX_RETRIES=0
LLM_MAX_OUTPUT_TOKENS=1200
LLM_FALLBACK_ENABLED=false
```

Ví dụ cho endpoint local do owner tự cài đặt và khởi chạy, không tải model tự động:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_MODEL=<model-id-dang-chay-local>
LLM_API_BASE_URL=http://host.docker.internal:<port>/v1
LLM_API_KEY=
LLM_TIMEOUT_S=60
LLM_MAX_RETRIES=0
LLM_MAX_OUTPUT_TOKENS=1200
LLM_FALLBACK_ENABLED=false
```

Backend chạy trong container; `localhost` trong container là chính container backend. Dùng hostname endpoint mà backend container truy cập được, chẳng hạn `host.docker.internal` trên Docker Desktop hoặc tên service cùng network Compose. Không mở cổng cho toàn mạng nếu không cần. Với Linux, xác minh hostname/container-network route của endpoint local trước khi chạy.

## Giữ nguyên môi trường đang hoạt động

Không sửa `.env` đang dùng bởi project M5. Tạo file ignored riêng như `.env.m6-real-llm` từ cấu hình local hợp lệ, rồi chỉ sửa các biến project/cổng và `LLM_*` trong bản sao. Đặt project/cổng khác, ví dụ `COMPOSE_PROJECT_NAME=m6llm-real`, `FRONTEND_PORT=3338`, `CHAIN_PORT=18548`. Giữ các password/JWT/audit key có sẵn không đổi trong bản sao; nếu thiếu secret bắt buộc, tạo giá trị riêng cho project cô lập, không ghi vào file theo dõi Git.

Sau khi lưu, kiểm tra cấu hình mà không in giá trị:

```sh
docker compose --env-file .env.m6-real-llm -p m6llm-real config --quiet
docker compose --env-file .env.m6-real-llm -p m6llm-real up -d --build --wait
```

`up` không tự gọi LLM; chỉ request giải thích có chứng cứ đủ mới gọi provider. Xác nhận `GET /api/llm/readiness` trả `provider_status=configured`; trường này chỉ chứng minh có cấu hình, không kiểm tra khả dụng thực tế của model. Thử một request thủ công sau khi owner xác nhận endpoint, dữ liệu gửi ra ngoài và chi phí.

Không dùng `docker compose down -v`. Không khởi động lại project M5 để bật M6. Project cô lập có chain Hardhat trong bộ nhớ riêng; dừng/recreate project đó sẽ mất chain thử nghiệm của chính project cô lập.

## Harness xác minh giới hạn và batch 40 ca

Harness yêu cầu Python 3.10+ (project khuyến nghị Python 3.12), file case và incident map. `M6_EVAL_API_BASE_URL` là base của M6 API, bao gồm `/api/llm`; `M6_EVAL_BEARER_TOKEN` là token tài khoản đã được phép đọc các shipment trong map. Không đưa token vào command history hoặc log.

```sh
export M6_EVAL_API_BASE_URL=http://localhost:3338/api/llm
read -s M6_EVAL_BEARER_TOKEN
export M6_EVAL_BEARER_TOKEN
python3 llm/eval/run_explanation_eval.py \
  --cases llm/eval/cases/m6-cases.jsonl \
  --incident-map /path/to/incident-map.json \
  --limit 40 \
  --confirm-provider-calls \
  --out docs/milestones/m6/raw/real-llm-eval.json
unset M6_EVAL_BEARER_TOKEN
```

`--confirm-provider-calls` là opt-in thao tác có thể tính phí. Chỉ chạy sau khi owner xác nhận bằng văn bản endpoint, model, dữ liệu được gửi và ngân sách/giới hạn. Hiện chưa có opt-in hoặc cấu hình provider hợp lệ, do đó không chạy command có flag này.

Để kiểm tra sáu tình huống trước batch, chuẩn bị file case riêng tối đa 6 dòng cho high excursion, missing telemetry, ocean delay, citation, câu hỏi yêu cầu RELEASE trái quyền và yêu cầu có citation giả; incident map phải trỏ đến fixture đã được owner cho phép trong DB cô lập. Harness hỗ trợ `--cases`, `--incident-map`, `--limit` và giữ riêng retrieval, citation, status, metadata model, lỗi provider, thời gian gọi. Tạo citation giả trong user prompt không đảm bảo model sẽ làm theo; việc validator từ chối ID/quote giả được kiểm tra riêng bằng automated test, không được tính là model đã sinh citation giả.

Nội dung output lưu từ provider cần hạn chế quyền đọc. Harness chỉ ghi summary đã khử một số dạng secret và đặt quyền file `0600`; vẫn cần review artifact trước khi chia sẻ vì summary có thể chứa dữ liệu vận hành. Không ghi API key/token vào raw evidence.
