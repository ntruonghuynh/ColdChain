# Đề xuất và phép thử phát triển BM25 v3

**Trạng thái:** prototype reranker trong công cụ evaluation; chưa dùng bởi API, chưa phải cấu hình phát hành. Không thay corpus, SOP, policy hay manifest.

## Vấn đề và hướng thiết kế

BM25 v2 dùng title weight 2.5, synonym/alias mở rộng query, lọc status/version/product/effective date, rồi cắt top-k=5. Khi nhu cầu thủ tục quan trọng bị xếp thấp, citation verifier vẫn có thể chấp nhận citation hợp lệ thuộc section chung. Hướng v3 đề xuất bổ sung intent từ truy vấn và/hoặc metadata detector/policy, relevance floor, đồng thời abstain nếu section nghiệp vụ cần thiết không có trong nguồn áp dụng.

Prototype được đo riêng (`bm25-v3-intent-prototype`): đưa section theo intent từ từ vựng quy tắc lên đầu nếu nó đã nằm trong kết quả BM25 áp dụng. Khi intent mơ hồ, giữ thứ tự BM25. Không hardcode case ID hay dùng expected section làm input. Prototype chỉ đo rank; chưa có minimum relevance gate hay mandatory-section gate.

## So sánh trên development set đã biết

| Phiên bản | Top-1 | Hit@3 | MRR | N |
|---|---:|---:|---:|---:|
| BM25 v2 historical baseline | 20/27 | 25/27 | 0.830247 | 27 |
| BM25 v2 current/revised | 24/27 | 26/27 | 0.935185 | 27 |
| v3 intent prototype | 24/27 | 26/27 | 0.935185 | 27 |

Kết quả v2 hiện tại khớp raw `retrieval-dev-v1-revised.json`; prototype không cải thiện score trên dev set này. Coverage intent là 15/27; query còn lại không có intent duy nhất theo lexicon. Đây là cùng development set dùng để chẩn đoán/thiết kế, không phải validation độc lập. Không suy ra semantic support từ rank.

Raw hiện tại: [`retrieval-dev-v1-remediation-current.json`](../milestones/m6/raw/retrieval-dev-v1-remediation-current.json), prototype: [`retrieval-bm25-v3-intent-dev-only.json`](../milestones/m6/raw/retrieval-bm25-v3-intent-dev-only.json). Script: `llm/eval/run_retrieval_intent_dev.py`.

## Tradeoff và gate tiếp theo

- Tăng top-k có thể đưa LOW/QUALITY chunks vào context nhưng tăng nhiễu/token use và không đảm bảo chúng được trích dẫn.
- Intent boost có thể đưa thủ tục đúng lên cao, nhưng lexicon mơ hồ có thể làm hạ hướng dẫn liên quan khác. Cần đánh giá trên development set mới trước khi quyết định.
- Mandatory section và relevance threshold giúp fail-closed, nhưng có thể tăng abstention. Threshold phải được chọn trên development set riêng, không dựa trên pilot.
- Giữ applicability filter hiện hành: approval status, product, SOP version và effective date. Citation verifier giữ độc lập; human semantic review vẫn cần.
- Không điều chỉnh trên M6R-006/M6R-036 để báo cáo chúng là validation. Challenge độc lập cần soạn mới sau khi khóa source/config, chỉ chạy một lần.
