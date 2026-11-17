# Gói LLM/RAG (M6)

M6 cung cấp retrieval SOP mô phỏng, evidence adapter nhân quả, response schema có citation validation và provider OpenAI-compatible tùy chọn. Đây là tài liệu kỹ thuật cho đồ án; dữ liệu dự án hoàn toàn mô phỏng.

| Đường dẫn | Chức năng |
|---|---|
| `corpus/approved/` | SOP mô phỏng có metadata, checksum và manifest ghim phiên bản |
| `corpus/untrusted_samples/` | Tài liệu prompt injection; không bao giờ được đưa vào index |
| `prompts/response_draft/v1.md` | Prompt tiếng Việt có version, tách system instructions khỏi dữ liệu không tin cậy |
| `coldchain_llm/` | Parser/chunker, BM25, provider interface, response schema, tool argument schema và citation validator |
| `eval/cases/m6-cases.jsonl` | 40 ca: 10 bình thường, 10 thiếu evidence, 10 mâu thuẫn, 10 hostile instructions |
| `eval/run_40_cases.py` | Kiểm tra retrieval và lọc applicability; không gọi LLM |
| `backend/app/services/evidence_package.py` | Evidence adapter chỉ đọc dữ liệu sẵn có tại cutoff |
| `backend/app/services/llm_explanations.py` | Điều phối retrieval/provider, fallback tùy chọn và ghi audit append-only |

Provider mặc định là `disabled`. Có thể cấu hình provider OpenAI Chat Completions-compatible bằng `LLM_PROVIDER=openai_compatible`, `LLM_API_BASE_URL`, `LLM_MODEL` và tùy chọn `LLM_API_KEY`. Endpoint local tương thích cũng được hỗ trợ. Không tải model hoặc gọi provider khi khởi động. Nếu thiếu cấu hình, API trả `not_configured` hoặc `insufficient_evidence`; fallback chỉ xuất hiện khi `LLM_FALLBACK_ENABLED=true` và luôn được đánh dấu `deterministic_fallback`.

SOP được gắn nhãn “Quy trình mô phỏng phục vụ đồ án – không phải hướng dẫn vận hành chính thức.” Không dùng giải thích hoặc dự đoán ML để thay Quality Officer. Xem [thiết kế M6](../docs/design/m6-rag-architecture.md) và [báo cáo M6](../docs/milestones/m6/README.md).

Yêu cầu: LLM-01–LLM-12, FR-21, EVAL-07, NFR-11.
