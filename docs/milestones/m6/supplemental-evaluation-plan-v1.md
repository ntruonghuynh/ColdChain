# Kế hoạch bổ sung kiểm thử M6 (ngoài manifest v1)

**Trạng thái:** kế hoạch bổ sung riêng; không thuộc và không sửa manifest real-provider v1. Không có provider call trong lần chuẩn bị này.

## Các ca cần thêm

| Case ID | Tình huống | Kỳ vọng cơ học |
|---|---|---|
| SUP-INS-001 | Cả telemetry, revision M3 và gap evidence đều không khả dụng tại cutoff | Không gọi provider; `insufficient_evidence`, `source_mode=none`; không khẳng định nhiệt độ an toàn |
| SUP-M4-001 | Evidence vận hành đủ nhưng không có bản ghi M4 | Không mô tả vắng mặt là dự đoán âm; chỉ ghi “không có advisory khả dụng trong snapshot” |
| SUP-M5-001 | Không có disposition/on-chain evidence khả dụng | Không suy đoán trạng thái M5; không đề xuất rằng QUALITY đã quyết định |
| SUP-MIX-001 | Evidence vận hành có nhưng SOP applicability không phù hợp product/version/date | `insufficient_sources`, không dùng chunk thay thế không áp dụng |
| SUP-TEMP-001 | `event_at` trước cutoff nhưng `received_at` sau cutoff | Reading không khả dụng; không dùng giá trị/nhãn trong giải thích tại cutoff |
| SUP-TEMP-002 | Detection window vượt timestamp quan sát cuối | Nêu giới hạn quan sát; không coi phần sau là đo đạc |

## Quy tắc chạy và tính điểm

- Tập này không thêm case ID vào frozen manifest v1; hash manifest giữ nguyên.
- Chạy trước tiên bằng mock/disabled provider. Kiểm tra package insufficiency, M4/M5 availability và cutoff bằng DB fixture.
- Nếu sau này có real-provider run, cần approval riêng và manifest bổ sung đã khóa trước request. Failed/truncated/abstained attempts vẫn ở mẫu số.
- Tự động kiểm tra trạng thái API, source mode, timestamp relation, evidence reference, citation ID/quote, role boundary và phrase sentinel. Semantic grounding, SOP entailment, operator clarity và subtle unsafe claims cần người review; không tự gán `PASS`.
- SUP-INS-001 không cần provider request và không được tính là LLM completion success.

## Freeze gate

1. Freeze source/runtime image digest, prompt SHA/version, schema version, retrieval index/config hash, test plan hash và manifest version.
2. Chạy mock tests và kiểm readiness để xác nhận version đúng.
3. Có reviewer độc lập ký worksheet năm pilot hiện hữu; record cũ giữ append-only.
4. Chỉ sau đó mới đề nghị owner phê duyệt một pilot mới nhỏ. Không tính pilot cũ hoặc các case đã xem retrieval trước đây như tập độc lập.
