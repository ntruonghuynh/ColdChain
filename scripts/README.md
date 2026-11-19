# Tài liệu thư mục `scripts/`

| Đường dẫn | Mục đích | Tình trạng |
|---|---|---|
| `setup_local_env.py` | Sinh cấu hình local, secret và tên Compose/image riêng trên macOS/Linux | Đang dùng bởi `start.command` |
| `setup_local_env.ps1` | Tương tự cho Windows PowerShell | Đang dùng bởi `start.bat`; chưa xác minh trên Windows thật |
| `deployment_smoke.py` | Smoke HTTP/auth chỉ đọc cho bản local đã khởi tạo; GET cùng một POST login, không chạy workflow, prediction hay LLM | Đang dùng trong handover |
| `smoke_test.py` | Kiểm tra Compose/app, proxy, SPA và persistence; có thể khởi động/dừng stack theo tùy chọn | Công cụ kiểm thử; đọc help trước khi chạy |
| `eval/` | Công cụ đánh giá nội bộ | Không chạy evaluation batch nếu chưa được giao nhiệm vụ và phê duyệt |

Các CLI import/replay nằm trong backend `app.dataset` và `app.monitoring`, gọi qua service `data-tools` như hướng dẫn cài đặt. Không có `scripts/replay_dataset.py` hoặc thư mục `scripts/demo/` trong phiên bản hiện tại. Script start/stop cho sinh viên nằm ở root: `start.command` / `stop.command` (macOS), `start.bat` / `stop.bat` (Windows).
