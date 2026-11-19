# Bàn giao triển khai ColdChain từ bản clone sạch

Tài liệu mô tả cách chạy một bản demo mới với Compose project, image tags, network, PostgreSQL volume và chain deployment volume riêng. Không sao chép `.env`, database, blockchain state hoặc evaluation evidence từ bản cài khác.

## Điều kiện cần

- Docker Desktop + Docker Compose v2 trên Windows 10/11 hoặc macOS; Linux cần Docker Engine + Compose v2.
- Khuyến nghị ít nhất 4 GB RAM khả dụng cho Docker; cần thêm dung lượng cho image và dataset.
- Git và internet để clone/tải image/package.
- Windows dùng PowerShell có sẵn. macOS/Linux cần Python 3 và shell để chạy helper.

Windows scripts chưa được chạy trên máy Windows trong lần bàn giao này; các bước Windows dưới đây đã được rà soát nhưng chưa xác minh thực thi. Linux cũng chưa được kiểm thử.

## Clone và cấu hình

```text
git clone https://github.com/ntruonghuynh/ColdChain.git
cd ColdChain
```

Không dùng lại thư mục đang chứa `.env` của lần cài khác. Start scripts tạo `.env` nếu chưa có và gọi helper để sinh secret cùng Compose project/image tags riêng; helper không in secret. `.env` được Git ignore.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local_env.ps1
docker compose config --quiet
```

Sau đó chạy `start.bat`, hoặc `docker compose up -d --build --wait --wait-timeout 600`. Trước khi chạy thủ công, đảm bảo `FRONTEND_PORT` và `CHAIN_PORT` trống; `start.bat` kiểm tra hai cổng này.

### macOS / Linux shell

```bash
cp .env.example .env
python3 scripts/setup_local_env.py
docker compose config --quiet
```

Trên macOS chạy `./start.command` (hoặc mở bằng Finder). Linux chạy `docker compose up -d --build --wait --wait-timeout 600` sau khi kiểm tra cổng. UI và Hardhat RPC mặc định bind `127.0.0.1`.

Nếu cổng bận, đổi `FRONTEND_PORT` hoặc `CHAIN_PORT` trong `.env`. Không đặt `COMPOSE_PROJECT_NAME` hoặc image tag trùng project khác. Helper ghi tên project vào `.env`; chạy lại helper giữ nguyên tên đã tạo. Compose yêu cầu project name và project-scoped image tags, không dùng `container_name` cố định. Backend và database không publish cổng host.

## Khởi động và migration

```bash
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 600
docker compose ps
```

Backend image khởi động Uvicorn; frontend image dùng Nginx phục vụ React SPA và proxy `/api` tới `backend:8000`. Compose chờ PostgreSQL, migration/reference data một lần, Hardhat local node/contract deployment, backend rồi frontend.

Thay `3000` bằng `FRONTEND_PORT` nếu đổi:

```text
http://127.0.0.1:3000/api/health
http://127.0.0.1:3000/api/health/ledger
http://127.0.0.1:3000/api/llm/readiness
http://127.0.0.1:3000/api/docs
```

Migration revision/head kỳ vọng là `0006_m6_llm_explanations`. M6 retrieval có thể sẵn sàng trong khi `provider_status=not_configured`; `.env.example` tắt provider và không có API key. Không cần key trả phí cho demo đọc.

## Nhập dataset demo

Migration nạp policy, organization và identities nhưng không tự import journeys. Seed 11 là fixture phát triển tracked gồm 200 hành trình mô phỏng. Không dùng seed đánh giá 22, 33, 44, 55, 66.

```bash
docker compose --profile tools run --rm data-tools python -m app.dataset verify data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset status
docker compose --profile tools run --rm data-tools python -m app.monitoring replay
docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean --source SIM-S11-J0154
docker compose --profile tools run --rm data-tools python -m app.monitoring summary
```

Import idempotent theo fingerprint; replay dùng riêng `event_at` và `received_at` để tạo incident history. Ocean demo thêm một simulated shipment cho tình huống outage/UNKNOWN/backfill và evidence revision. Stable ID `DEMO-OCEAN-...` làm thao tác lặp lại idempotent. Các lệnh chỉ ghi vào database volume của project hiện tại.

## Local demo login

Mặc định seeder tạo các user `shipper.demo`, `carrier.demo`, `quality.demo`, `warehouse.demo`, `platform.admin` với mật khẩu sinh trong `.env`: `SHIPPER_DEMO_PASSWORD`, `CARRIER_DEMO_PASSWORD`, `QUALITY_DEMO_PASSWORD`, `WAREHOUSE_DEMO_PASSWORD`, `ADMIN_DEMO_PASSWORD`.

Với classroom demo disposable, bật `LOCAL_DEMO_MODE=true` trong `.env` trước startup/seed đầu tiên; giữ `APP_ENV=local` và `FRONTEND_BIND_ADDRESS=127.0.0.1`. DB trống sẽ được cấp thêm các alias bằng hệ thống PBKDF2 và role backend thông thường:

| Username | Password | Role |
|---|---|---|
| `quality` | `123` | QUALITY |
| `warehouse` | `123` | WAREHOUSE |
| `carrier` | `123` | CARRIER |
| `shipper` | `123` | SHIPPER |
| `admin` | `123` | ADMIN |

Provisioning idempotent, không reset user. Lần đầu bật mode trên DB đã có user bị từ chối; backend cũng yêu cầu `APP_ENV=local` và loopback bind. Khi mode tắt, aliases không đăng nhập được. Password ngắn chỉ dùng trên localhost riêng, không phải môi trường công khai. QUALITY mới ghi disposition; WAREHOUSE mới xin physical release sau QUALITY RELEASE đủ điều kiện.

Kiểm tra trước đó trên database disposable: cả năm tài khoản login được, `/auth/me` trả đúng role, protected request chưa login trả 401, role không đủ quyền trả 403. Seed lại báo không tạo user mới và không thay đổi user đã có. Bộ test local-demo tập trung có 29 test pass. Không chạy lại test hoặc đụng database của project đang bảo vệ trong lần cập nhật tài liệu này.

## Kiểm tra HTTP/auth chỉ đọc

Sau khi import/replay:

```bash
python3 scripts/deployment_smoke.py
```

Script kiểm tra SPA routes, readiness/migration 0006, policy, 200 journeys, HIGH/LOW/DATA_GAP, evidence/revision GET, chain readiness, M4 readiness, M6 offline readiness, ledger/audit GET, 401/403. Nó chỉ POST login cục bộ; không gọi ingestion, disposition, release, prediction scoring, explanation creation hay provider. Empty explanation history và chain history hợp lệ trên fresh demo.

## Những gì có thể trình diễn

- **M1–M3:** overview, shipments, policy band, timeline, queue, incident evidence/revisions/gap và ocean outage/backfill. Thiếu telemetry vẫn UNKNOWN.
- **M4:** frontend đọc model readiness; không tự score. Scoring là POST và prediction history không có GET endpoint.
- **M5:** login, `/auth/me`, Quality Review, disposition confirm, WAREHOUSE release gate riêng, ledger/signed-audit reads. Không gửi mutation khi acceptance chỉ đọc. Fresh import không có ledger events đã xác nhận; M3 replay tạo `INCIDENT_OPENED` vào outbox. Chưa registration M5 thì events có thể pending, chưa có chain tx.
- **M6:** readiness và stored explanation/history/citation chỉ đọc. Fresh DB thường chưa có explanation; mở incident không gọi inference.

Import/replay/ocean setup là CLI. M5 chain-history hoặc M6 citation giàu dữ liệu cần fixture/records được chuẩn bị trong project disposable riêng; không tạo dữ liệu đó trên môi trường bảo vệ. Đăng ký shipment/custody hiện là API workflow, chưa có UI tương ứng.

## Dừng/chạy lại/xóa đúng project

Giữ dữ liệu và process chain:

```bash
docker compose stop
docker compose start
```

Gỡ container/network nhưng giữ named volume:

```bash
docker compose down
```

Chain state Hardhat nằm trong RAM và mất khi container bị remove; PostgreSQL volume vẫn còn.

Chỉ xóa volumes khi đã xác minh đây đúng project demo disposable của mình:

```bash
grep '^COMPOSE_PROJECT_NAME=' .env       # PowerShell: Select-String '^COMPOSE_PROJECT_NAME=' .env
docker compose config --format json
docker compose ps -a
docker compose down --volumes
```

Lệnh cuối xóa PostgreSQL và chain deployment volumes của project đó. Không chạy Docker-wide prune.

## Xử lý nhanh

- Compose thiếu project name: tạo `.env` từ mẫu và chạy helper đúng hệ điều hành.
- Port bind lỗi: chọn `FRONTEND_PORT`/`CHAIN_PORT` trống và kiểm tra `docker compose config --quiet`.
- Migration chưa 0006: xem `docker compose logs migrate db`; không sửa `alembic_version` thủ công.
- Backend/API lỗi: xem `docker compose ps -a` và log `backend migrate db chain chain-deploy frontend`.
- Login lỗi: kiểm tra host/port và trạng thái provisioning; seeder không thay hash password user cũ.
- Provider M6 `not_configured`: đúng với demo offline; GET explanation vẫn hoạt động khi đã có record.
- Thiếu dung lượng: xác định đúng resource disposable trước khi xử lý; tránh global cleanup.

## Biên bản kiểm chứng ngày 2026-11-19

- Tạo archive sạch từ `main`; các startup scripts, `.env.example`, migration `0006` và seed-11 fixture có trong source. Thay đổi handover được chép vào checkout tạm để kiểm thử. Clone GitHub trực tiếp không thực hiện được do môi trường không phân giải `github.com`.
- Startup trên macOS dùng project riêng `coldchain-demo-7c6f5608`, image tags/network/volumes mới, frontend port 3287 và chain port 18551. Migration/reference-data hoàn tất; backend, worker, database, chain, frontend healthy.
- Seed 11 verify/import thành công: 200 journeys, 114,969 readings; `event_at` và `received_at` đều `timestamp with time zone`, 115,643 reading có receipt muộn hơn event. Replay 200 shipments tạo 146 incidents. Ocean demo biểu diễn STALE → UNKNOWN → CURRENT sau delayed backfill.
- Backend/generator: 331 passed, 11 deselected, 0 failed. Frontend: 30 passed; typecheck và production build passed. Có `act(...)` warnings hiện hữu trong frontend tests và deprecation warnings từ dependency backend.
- HTTP/auth smoke: 23 passed, 0 failed, 1 skipped (explanation detail vì fresh DB không có stored explanation). Login và `/auth/me` 200; protected GET chưa login 401; QUALITY bị 403 khi gọi ADMIN-only audit verify. Ledger/audit GET 200. M4 readiness và offline M6 retrieval sẵn sàng; provider `not_configured`.
- M3 replay để lại 147 `INCIDENT_OPENED` pending trong outbox và 0 confirmed chain transactions do chưa có shipment-registration event M5. Không tạo disposition, warehouse release, prediction score, explanation, hay provider call. Contract deploy chỉ lên Hardhat local chain mới.
- Chỉ macOS đã test triển khai. Windows/Linux chưa test trên hệ điều hành tương ứng. 35 evaluation cases M6 còn lại không chạy.
