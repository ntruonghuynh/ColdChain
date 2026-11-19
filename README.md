# ColdChain — Theo dõi chuỗi lạnh và xử lý sai lệch nhiệt độ

ColdChain là đồ án học thuật cho môn **IT in Logistics — Project 03**. Ứng dụng mô phỏng hành trình vận chuyển hàng cần bảo quản lạnh, theo dõi dữ liệu cảm biến và hỗ trợ nhân viên đánh giá sai lệch. Hệ thống giữ riêng bằng chứng đo được, khoảng mất dữ liệu, cảnh báo ML/LLM và quyết định nghiệp vụ của con người.

> **Ranh giới sử dụng:** dữ liệu và chính sách trong ứng dụng phục vụ giảng dạy, không phải tiêu chuẩn y tế hay quy định pháp lý. ML và LLM chỉ cung cấp thông tin tham khảo. Khoảng trống dữ liệu là `UNKNOWN`, không có nghĩa hàng hóa an toàn. Chỉ người có role `QUALITY` mới được ghi disposition; `WAREHOUSE` chỉ yêu cầu xuất kho sau khi `QUALITY RELEASE` được backend xác nhận.

## Tính năng và trạng thái

ColdChain hiện tích hợp M1–M6: nền tảng web, dữ liệu mô phỏng, giám sát cảm biến, ML advisory, workflow chất lượng/blockchain và giải thích RAG. React hiển thị các chức năng đã có; một số thao tác M5 và M4 vẫn chỉ có API/CLI.

| Milestone | Chức năng hiện có |
|---|---|
| M1 | React dashboard, FastAPI, PostgreSQL, migration Alembic, đăng nhập và dữ liệu cấu hình |
| M2 | Bộ mô phỏng và bộ dữ liệu seed 11 gồm 200 hành trình tổng hợp |
| M3 | Telemetry, `event_at`/`received_at`, trạng thái CURRENT/STALE/UNKNOWN, baseline theo policy, incident và revision |
| M4 | Random Forest đã đóng băng; API readiness và scoring. Frontend chỉ hiển thị readiness, không tự chấm điểm |
| M5 | Xác thực theo role, QUALITY disposition, WAREHOUSE release gate, transactional outbox, Hardhat cục bộ và signed audit |
| M6 | Retrieval, explanation history và SOP citations. Mở incident chỉ đọc dữ liệu đã lưu, không gọi inference |

## Thành phần chính

- **Frontend:** React, TypeScript, Vite; khi chạy Docker, Nginx phục vụ SPA và proxy `/api` tới backend.
- **Backend:** FastAPI/Python cung cấp API cho dữ liệu, monitoring, authentication và workflow.
- **Dữ liệu:** PostgreSQL lưu cấu hình, hành trình, reading, incident và audit; migration chạy tự động khi khởi động.
- **Worker và blockchain:** worker chuyển event qua transactional outbox tới Hardhat node cục bộ. Hardhat giữ trạng thái trong bộ nhớ; PostgreSQL giữ hồ sơ ứng dụng.
- **Simulator/ML/LLM:** seed 11 là dữ liệu tổng hợp; M3 dùng baseline theo policy; M4 dùng model RF đóng băng; M6 retrieval chạy được khi provider bị tắt.

## Điều kiện cần

- Git và Docker Desktop có Docker Compose v2.
- Kết nối Internet cho lần clone, tải image và cài dependency bên trong image.
- Khuyến nghị dành ít nhất 4 GB RAM cho Docker.
- macOS cần Python 3 để chạy helper môi trường. Windows dùng PowerShell tích hợp sẵn. Người chỉ dùng ứng dụng không cần cài Node.js hoặc cài Python backend trên máy chủ.
- Cổng mặc định trên máy: frontend `3000`, Hardhat RPC `8545`; cả hai bind vào `127.0.0.1`. Backend `8000` và PostgreSQL `5432` chỉ nằm trong mạng Compose.

## Bắt đầu nhanh

### Windows 10/11 — PowerShell

```powershell
git clone https://github.com/ntruonghuynh/ColdChain.git
cd ColdChain
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local_env.ps1
notepad .env
```

Trong `.env`, trước lần chạy đầu tiên, đặt `LOCAL_DEMO_MODE=true`; giữ `APP_ENV=local` và `FRONTEND_BIND_ADDRESS=127.0.0.1`. Lưu rồi đóng Notepad. Sau đó:

```powershell
.\start.bat
```

### macOS — Terminal

```bash
git clone https://github.com/ntruonghuynh/ColdChain.git
cd ColdChain
cp .env.example .env
python3 scripts/setup_local_env.py
open -e .env
```

Trong `.env`, trước lần chạy đầu tiên, đặt `LOCAL_DEMO_MODE=true`; giữ `APP_ENV=local` và `FRONTEND_BIND_ADDRESS=127.0.0.1`. Lưu file rồi chạy:

```bash
./start.command
```

`start.bat` và `start.command` kiểm tra Docker, tạo secret còn thiếu mà không in giá trị, kiểm tra cổng, chạy Compose, đợi health check và mở trình duyệt. Lần đầu có thể mất vài phút. Dataset không tự import.

### Nạp 200 hành trình mô phỏng

Chạy từ thư mục gốc `ColdChain`, sau khi ứng dụng đã healthy. Các lệnh dưới đây dùng được trong PowerShell và macOS Terminal:

```bash
docker compose --profile tools run --rm data-tools python -m app.dataset verify data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset status
docker compose --profile tools run --rm data-tools python -m app.monitoring replay
```

`verify` kiểm tra manifest; `import` đưa 200 journey seed 11 vào database và an toàn khi chạy lại cùng fingerprint; `status` xem số bản ghi đã nhập; `replay` chạy baseline theo receipt time đã ghi, tạo incident/revision cho dashboard. `event_at` (thời điểm cảm biến đo) và `received_at` (thời điểm hệ thống nhận) được giữ riêng.

Để chuẩn bị tình huống mất kết nối đại dương, chạy lệnh có ghi bổ sung shipment mô phỏng riêng:

```bash
docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean --source SIM-S11-J0154
```

Lệnh demo có mã ổn định, không tạo thêm bản sao khi chạy lại. Xem [Hướng dẫn cài đặt](docs/huong-dan-cai-dat.md) để biết lệnh xác minh, kết quả mong đợi và chi tiết dữ liệu.

## Đăng nhập demo tại localhost

Chỉ dùng các mật khẩu ngắn này trong database lớp học mới, riêng tư và bind loopback. Mode phải bật **trước khi seed lần đầu**; nếu database đã có user không tương thích, backend từ chối provisioning thay vì ghi đè tài khoản. Không bật trên máy chủ công khai.

| Username | Password | Role |
|---|---|---|
| `quality` | `123` | `QUALITY` |
| `warehouse` | `123` | `WAREHOUSE` |
| `carrier` | `123` | `CARRIER` |
| `shipper` | `123` | `SHIPPER` |
| `admin` | `123` | `ADMIN` |

Sau khi start, mở **http://localhost:3000** (hoặc cổng đã ghi trong `.env`) rồi chọn **Sign in**. Token chỉ ở bộ nhớ trình duyệt; tải lại trang cần đăng nhập lại. Backend vẫn kiểm tra role trên từng API request.

## Các màn hình dashboard

| Tên trong ứng dụng | Đường dẫn | Dùng để |
|---|---|---|
| Overview | `/` | Tình trạng API/database, migration, số shipment, policy và feature |
| Shipments | `/shipments` | Danh sách shipment, tuyến, trạng thái và nguồn dữ liệu |
| Temperature Monitoring | `/temperature` | Biểu đồ nhiệt độ, policy band, thời gian UTC và tình trạng dữ liệu |
| Excursion Queue | `/excursions` | Incident đang mở; lọc sai lệch nhiệt hoặc DATA_GAP |
| Incident Details | `/incidents/:incidentId` | Bằng chứng, revision, khoảng thiếu dữ liệu, explanation đã lưu |
| Quality Review | `/quality-review` | `QUALITY` review bằng chứng và gửi disposition sau bước xác nhận |
| Audit History | `/audit` | Ledger, audit ký số và xác minh reference; một số kiểm tra chỉ dành cho ADMIN |
| System Settings | `/settings` | Cấu hình/runtime/policy ở chế độ chỉ đọc |
| Sign in | `/login` | Đăng nhập tài khoản backend |

Hướng dẫn thao tác cho từng trường, badge và trạng thái ở [Sổ tay sử dụng](docs/huong-dan-su-dung.md). Kịch bản thuyết trình 6–8 phút ở [Kịch bản demo](docs/kich-ban-demo.md).

## Các giới hạn cần nhớ

- Toàn bộ dữ liệu seed 11 là mô phỏng. Policy `POL-CHILL-01 v1.0` dùng cho giảng dạy: 2–8 °C; trên 8 °C ít nhất 30 phút tạo ngưỡng HIGH; dưới 2 °C ít nhất 15 phút tạo ngưỡng LOW; gap trên 15 phút là UNKNOWN; gap từ 30 phút cần review. Đây không phải hướng dẫn bảo quản thật.
- Không có giao diện shipment registration/custody cho SHIPPER/CARRIER/WAREHOUSE; các endpoint workflow tương ứng chỉ gọi qua API.
- Frontend M4 chỉ đọc readiness. Scoring là POST append-only; không có GET prediction-history.
- Explanation history/citation chỉ hiện nếu database đã có bản ghi. Mở incident không tạo giải thích và không gọi nhà cung cấp LLM.
- Worker tự retry blockchain event theo policy backend; UI chỉ hiển thị trạng thái, không có nút retry.
- Hardhat là node đơn cục bộ, trạng thái chain trong bộ nhớ mất khi container chain được tạo lại. PostgreSQL volume vẫn được giữ bởi `stop` scripts.
- Windows/Linux chưa được xác minh trên chính các hệ điều hành đó; macOS đã có lần triển khai cô lập được ghi lại trong handover. Xem [Khắc phục sự cố](docs/xu-ly-loi.md).

## Tài liệu

- [Hướng dẫn cài đặt bằng tiếng Việt](docs/huong-dan-cai-dat.md)
- [Sổ tay sử dụng dashboard](docs/huong-dan-su-dung.md)
- [Kịch bản demo trên lớp](docs/kich-ban-demo.md)
- [Khắc phục sự cố](docs/xu-ly-loi.md)
- [Deployment handover và biên bản kiểm chứng](docs/deployment-handover.md)
- [Từ điển dữ liệu](data/dictionary/data-dictionary.md) và [nguồn gốc dữ liệu](data/dictionary/provenance.md)
- [Kiến trúc](docs/architecture.md), [API monitoring](docs/api/monitoring-api.md), [thiết kế workflow M5](docs/design/m5-blockchain-workflow.md)
- [Yêu cầu](docs/requirements-analysis.md), [kế hoạch triển khai](docs/implementation-plan.md), [báo cáo M3](docs/milestones/m3/README.md), [báo cáo M5](docs/milestones/m5/README.md), [báo cáo M6](docs/milestones/m6/README.md)
