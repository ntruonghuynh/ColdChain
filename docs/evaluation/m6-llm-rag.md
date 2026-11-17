# Đánh giá M6 RAG – giao thức và kết quả

Tài liệu này ghi kết quả có thể tái lập từ fixture M6. Nội dung và báo cáo milestone viết bằng tiếng Việt; các ID và tên trường giữ nguyên để khớp code.

## Giao thức

Runner: `llm/eval/run_40_cases.py`. Bộ ca: `llm/eval/cases/m6-cases.jsonl`. Mỗi lần chạy đọc SOP được duyệt, gọi BM25 cục bộ và không gọi LLM. Có bốn nhóm, mỗi nhóm 10 tình huống. Kết quả cuối: `docs/milestones/m6/raw/40-case-retrieval-check.json`; log gốc: `docs/milestones/m6/raw/40-case-retrieval-check.txt`.

## Số đo thực thi

| Phép kiểm | Kết quả | Mẫu số |
|---|---:|---:|
| Truy xuất có section mục tiêu trong top-5 | 40/40 (100%) | 40 ca đã hiệu chỉnh |
| Từ chối version không áp dụng | 40/40 | 40 ca |
| Từ chối product category không áp dụng | 40/40 | 40 ca |
| Mã ca trùng | 0 | 40 ca |
| Chunk từ tài liệu hostile được index | 0 | 1 tài liệu SOP + sample hostile ngoài index |

Lần chạy đầu có 34/40 hit; sáu query fixture chưa nêu từ/cụm từ tương ứng trong section mục tiêu. Query mô tả ý định truy xuất được hiệu chỉnh, còn nội dung hostile giữ riêng ở `untrusted_text` và không được đưa vào retrieval. Kết quả đầu được giữ tại `docs/milestones/m6/raw/40-case-retrieval-initial-run.json` để kiểm toán. Vì fixture được hiệu chỉnh sau lần chạy đầu, số cuối là kiểm thử tích hợp của fixture chứ không phải ước lượng benchmark độc lập.

## Chỉ số chưa chạy

Không có inference thật nên các chỉ số sau là **NOT RUN**: độ chính xác facts/sensor, citation do LLM tạo, groundedness ngữ nghĩa, tỉ lệ abstain của câu trả lời sinh, tuân thủ thủ tục qua người chấm, unsafe claim rate, latency và chi phí. Mock/provider parser test không được tính là bằng chứng inference thật. Kiểm citation tự động chỉ xác minh ID nguồn có trong context, phiên bản policy/khoảng sensor và substring quote; không chứng minh nội dung claim đúng ngữ nghĩa.

## Rubric và trạng thái

| Tiêu chí | Cách đánh giá | Kết quả M6 |
|---|---|---|
| Độ chính xác chứng cứ | Đối chiếu từng phát biểu với evidence snapshot và cutoff | NOT RUN với câu trả lời sinh; chưa có inference thật |
| Độ liên quan retrieval | Section mục tiêu trong top-5; review liên quan ngữ nghĩa cần người | 40/40 hit trên fixture đã hiệu chỉnh; semantic review NOT RUN |
| Citation | ID/version/section/quote được so với source set; kiểm claim ngữ nghĩa riêng | Unit checks đã chạy; tỉ lệ trên câu trả lời LLM NOT RUN |
| Groundedness ngữ nghĩa | Reviewer kiểm claim, mức certainty và hỗ trợ của nguồn | NOT RUN |
| Thiếu chứng cứ | Kiểm nhánh insufficient-evidence/fallback và đánh giá câu trả lời khi thiếu dữ liệu | Unit/API regression có; tỷ lệ abstain của provider NOT RUN |
| Đúng thủ tục | Reviewer đối chiếu bước đề xuất với SOP áp dụng và policy | NOT RUN |
| Tuân thủ quyền con người | Kiểm tra draft không quyết định disposition/release; workflow M5 giữ quyền riêng | Unit/API checks có; tỷ lệ trên generated answers NOT RUN |
| Claim không an toàn | Schema chặn cụm từ rủi ro; cần review output thật để đo tỷ lệ | Một số cụm được regression-test; rate của LLM NOT RUN |
| Latency và availability | Đo request end-to-end với provider có cấu hình, mẫu số và timeout | NOT RUN; chỉ test lỗi/provider mock |

## Lệnh tái lập

```sh
docker compose --profile test run --rm backend-tests python /workspace/llm/eval/run_40_cases.py
docker compose --profile test run --rm backend-tests pytest -q -p no:cacheprovider -c pyproject.toml tests/test_m6_rag.py
```

Các lệnh dùng test image và database test riêng. Không dùng seed đánh giá cuối 22, 33, 44, 55, 66; không truy cập ground truth.

## Challenge set độc lập, không tuning

Sau khi giữ nguyên hai kết quả lịch sử 34/40 và 40/40, tạo bộ `llm/eval/challenge/m6-retrieval-challenge-v1.jsonl` (21 ca) và ghi hash đầu vào trước khi chạy. Bộ này chứa 12 câu có mục tiêu liên quan, 3 trường hợp không đủ nguồn, 3 phiên bản sai và 3 loại sản phẩm sai. Nó được chạy đúng một lần; không thay query hoặc ranking sau kết quả.

| Metric tự động | Numerator / denominator | Phương pháp / giới hạn |
|---|---:|---|
| Top-1 đúng | 6/12 | ID section mục tiêu khớp tại vị trí đầu; lexical benchmark nhỏ |
| Hit@3 | 9/12 | Section mục tiêu xuất hiện trong top-3 |
| MRR | 0.6111 | Reciprocal rank trung bình trên 12 query liên quan |
| Target xếp trước distractor | 1/3 | Chỉ cặp mà cả target và distractor đều xuất hiện trong top-5 |
| No-result khi không đủ nguồn | 3/3 | Kết quả `no_applicable_sources` |
| Từ chối version sai | 3/3 | Metadata/version filter xác định |
| Từ chối product sai | 3/3 | Metadata/category filter xác định |

Raw kết quả: `docs/milestones/m6/raw/retrieval-challenge-results.json` và `.txt`; hash đầu vào: `docs/milestones/m6/raw/retrieval-challenge-input-sha256.txt`. Kết quả yếu của top-1 được giữ nguyên, không dùng làm vòng tuning. Challenge chỉ đánh giá retrieval; không sinh lời giải thích.

## Phân loại đánh giá 40 ca và LLM

`run_40_cases.py` cùng `m6-cases.jsonl` hiện là đánh giá retrieval theo fixture. Chúng không gọi provider. Lần đầu đạt 34/40; sau khi chỉnh sáu query fixture đạt 40/40. Cả hai raw được giữ. Vì query đã được sửa, 40/40 không độc lập và không đo chất lượng câu trả lời.

`run_explanation_eval.py` là harness end-to-end mới: tối đa 40 incident đã chuẩn bị, request qua HTTP, kiểm trạng thái provider thật (`source_mode=llm`), citation identifiers, abstention metadata và latency HTTP; lưu nội dung đã khử secret, để semantic review ở `NOT REVIEWED`. Harness không gọi provider nếu thiếu flag `--confirm-provider-calls`; chế độ hiện chạy cho kết quả `DRY_RUN`, `provider_invoked=false`, mẫu số 40. Evidence: `docs/milestones/m6/raw/explanation-eval-dry-run.json` và `.txt`.

| Chỉ số câu trả lời sinh | Kết quả hiện tại | Cách đánh giá / provider |
|---|---|---|
| Evidence factual accuracy | 1 accepted draft được đối chiếu với snapshot; chưa có independent human review | Field values đối chiếu DB; câu summary có một chỗ diễn đạt tự sửa gây khó hiểu |
| Citation correctness của LLM | 13 citations trong 1 draft qua ID/source/quote verifier | Không thay thế review ngữ nghĩa độc lập từng claim |
| Missing-evidence handling của LLM | NOT RUN (0/0) | API fallback/none được kiểm bằng HTTP; không phải output LLM |
| Procedural correctness | NOT RUN (0/0) | Chưa có human review |
| Human-authorization compliance của generated answers | NOT RUN (0/0) | Software boundary HTTP kiểm độc lập; không đo answer model |
| Unsupported safety claim rate | NOT RUN (0/0) | Chưa đánh giá ngữ nghĩa output; keyword/schema checks không thay thế review |
| Provider-call outcomes | 2/3 provider calls trả HTTP 200; một call trả HTTP 401; 1/3 tạo draft được chấp nhận | Ba one-call attempts riêng; không phải 40-case evaluation |
| Provider response latency | 12.057 ms và 19.989 ms | Hai HTTP 200 (`n=2`), các mẫu đơn lẻ, không phải benchmark |

Mock parser/provider unit test là **mock**, kiểm protocol/error handling và không được tính vào số mẫu real LLM. Deterministic fallback kiểm qua HTTP riêng và gắn nhãn `deterministic_fallback`; cũng không được tính là LLM. Đã có ba one-call real-provider attempts: một lỗi xác thực HTTP 401 và hai HTTP 200, trong đó lần thứ ba tạo draft được application chấp nhận. 40-case batch không chạy. Request thứ ba và giới hạn suy luận được ghi ở phần dưới.

## Development retrieval v2 và challenge độc lập mới

Challenge v1 và kết quả cũ được giữ nguyên, không rerun/tune: 6/12 top-1, 9/12 hit@3, MRR 0.6111. Development fixture riêng 27 query cho baseline 20/27 top-1, 25/27 hit@3, MRR 0.830247. Sau đó đã thêm normalization không dấu tiếng Việt, alias hữu hạn theo SOP và trọng số section title 2.5 lần; cùng dev set đạt 24/27 top-1, 26/27 hit@3, MRR 0.935185. Raw trước/sau ở `docs/milestones/m6/raw/retrieval-dev-v1-{baseline,revised}.json`.

Retrieval code và index version `bm25-v2-title25-vn-aliases` được hash trong `docs/evaluation/m6-retrieval-v2-manifest.json`. Sau đóng băng, challenge độc lập v2 được viết/băm và chạy một lần; không điều chỉnh sau chạy. Mẫu 21 ca: 12 relevant, 3 insufficient-source, 3 wrong-version, 3 wrong-product.

| Metric challenge v2 | Numerator / denominator | Phương pháp |
|---|---:|---|
| Top-1 đúng | 7/12 | Target section đứng đầu |
| Hit@3 | 11/12 | Target section trong top 3 |
| MRR | 0.752778 | Trung bình reciprocal rank trên 12 ca relevant |
| Target trước distractor | 7/9 | Chỉ cặp cả hai section được trả trong top-5 |
| Không đủ nguồn trả no-result | 0/3 | Query ngoài nội dung SOP; cả ba vẫn có lexical hit |
| Từ chối version sai | 3/3 | Filter phiên bản metadata |
| Từ chối product sai | 3/3 | Filter product metadata |

Challenge v2 khác nội dung challenge v1, nên không diễn giải 7/12 như cải thiện thống kê so với 6/12. Kết quả 0/3 insufficient-source bộc lộ thiếu minimum relevance threshold. Không tune sau challenge; nếu tiếp tục, threshold phải được chọn trên development set mới và đánh giá bằng challenge độc lập khác. Hash raw: `docs/milestones/m6/raw/retrieval-challenge-v2-input-sha256.txt`; outputs JSON/TXT cùng thư mục.

## Cấu hình provider và trạng thái suy luận thật

Adapter chấp nhận `LLM_PROVIDER=disabled` hoặc `openai_compatible`; endpoint có dạng base OpenAI-compatible để client nối `/chat/completions`. Các biến và lệnh an toàn cho hosted/local endpoint nằm trong `docs/milestones/m6/real-llm-validation-setup.md`. Các secret không được ghi ra log. Ba one-call attempts đã xảy ra; lần thứ ba tạo draft được app chấp nhận. Sáu-case verification và 40-case batch chưa chạy. Đánh giá ngữ nghĩa của một output chỉ là đối chiếu agent với DB snapshot, chưa phải independent human review. Dry-run 40 ca không gửi request.

Service ghi provider/model/API version/token usage/latency ngay sau khi provider trả response, trước citation/schema validation. Provider thành công và validation ứng dụng là hai trạng thái riêng. Nội dung bị từ chối vẫn bị loại bỏ và `source_mode=none`; citation status chỉ `failed` nếu bước citation thực sự được chạy và từ chối nguồn/quote/metadata. Evaluator phân biệt provider attempt, response nhận được, answer được chấp nhận, abstention, citation validation và latency. Factual accuracy, semantic groundedness, procedural correctness yêu cầu người đánh giá và vẫn `NOT REVIEWED`.

## Rà soát các phản hồi provider thật bị từ chối

`docs/evaluation/m6-real-llm-one-call-55343690a58d4.json` ghi nhận provider trả HTTP 200 cho `gpt-6-luna`, dùng 14.225 prompt tokens và 1.200 completion tokens. Ứng dụng không chấp nhận nội dung: `source_mode=none`, trạng thái `insufficient_evidence`, không lưu citation. Evidence của incident và 45 tham chiếu số đo quan sát được đạt kiểm tra nhất quán; năm section SOP phiên bản 1.0 đã được truy xuất. Artifact không ghi `finish_reason` và không giữ văn bản sinh chưa xác minh. Vì vậy không thể phân biệt hồi cứu giữa JSON bị cắt/hỏng, sai schema, thiếu citation, citation không thuộc nguồn đã truy xuất, quote sai, hoặc lỗi xác thực khác. Không kết luận nguyên nhân cụ thể khi không có bằng chứng phân biệt.

Các kiểm tra policy version và sensor interval được orchestration cấp từ cùng evidence package trước khi validation chạy, nên không giải thích được lần thất bại này. Code cũ gộp nhiều lỗi parse/schema/citation thành một kết quả tổng quát. Bản cập nhật ghi mã phân loại và trạng thái từng giai đoạn, không lưu prompt hay text provider chưa xác minh.

### Token budget và prompt

Artifact cũ có tổng `input_tokens=14225`, nhưng tokenizer/prompt nguyên bản không được lưu; không có phân bổ token từng phần đáng tin cậy. Tái dựng offline từ dữ liệu có sẵn cho thấy prompt v1 khoảng 35.437 UTF-8 bytes: system instructions 1.859 bytes, câu hỏi 306, evidence JSON 13.030, source map 18.683 và schema instructions 1.559. Đây là byte, không phải token. Evidence JSON và source map lặp lại 45 bản ghi số đo. Môi trường kiểm tra không có tokenizer phù hợp để tái tính token từng phần.

Prompt `response_draft/v2` giữ nguyên nguồn chi tiết một lần trong source set dùng cho citation, bỏ các mảng chi tiết trùng lặp khỏi evidence JSON và thay bằng số lượng bản ghi; summary, thời điểm, cutoff, interval, policy và metadata hiệu lực SOP vẫn được giữ. Prompt phân biệt SOP áp dụng tại cutoff hiện tại với SOP có hiệu lực tại thời điểm incident. Với `gpt-6-luna`, adapter dùng Chat Completions JSON Schema strict; Pydantic vẫn thực thi giới hạn độ dài cục bộ. Citation verifier tiếp tục bắt buộc vì JSON Schema chỉ định dạng, không chứng minh nguồn hay ngữ nghĩa.

Request có stage diagnostics mới (`M6-REAL-VALIDATION-ONE-871211f6bb684ae9958109d42244890f`) dùng prompt version v2, nhận HTTP 200 từ provider, `finish_reason=length`, và đúng 1.200 completion tokens. Provider call thành công; JSON không hoàn chỉnh nên parser từ chối với `completion_limit_reached`, schema chưa chạy, citation validation `not_run`, `citation_verification=not_applicable`, `source_mode=none`. Điều này xác nhận mức 1.200 không đủ cho request này; không chứng minh nguyên nhân chính xác của request cũ thiếu `finish_reason`, nhưng làm giả thuyết bị cắt phù hợp hơn. Strict JSON Schema được gửi tới provider và model trả về kết quả thay vì lỗi định dạng.

Prompt mới dùng 9.450 input tokens, ít hơn 4.775 so với artifact cũ (14.225); câu hỏi và prompt version khác nhau nên không xem đây là phép đo cô lập hiệu quả của prompt compaction. Evidence package khớp snapshot trước request: 48 evidence references, trong đó 45 reading references; hash package `cb3c6b20b7835e4eea42a977e22e6495baa243937edb23b9c502b789a7f074e7`. SOP `HIGH_EXCURSION` đã được retrieval cùng bốn section khác, version 1.0. Request cap 3.200 tiếp theo dùng cùng lượng input và hoàn tất với 2.405 output tokens.

Record đã lưu trong `docs/evaluation/m6-real-llm-validation-one-call.json`; kiểm tra DB xác nhận diagnostics được lưu, không có raw completion hoặc prompt. Không retry sau `finish_reason=length`.

### Một request duy nhất với cap 3.200, sau phê duyệt riêng

Request ref `M6-REAL-VALIDATION-3200-90963f4153b34039b78413a9ed1fd737` dùng cap 3.200 và được gửi đúng một lần. Provider trả HTTP 200, model `gpt-6-luna`, `finish_reason=stop`, input 9.450, output 2.405 tokens, latency 19.989 ms. Ứng dụng trả `source_mode=llm`, `explanation_status=draft`; parse/schema/evidence/citation validation đều passed. Có 13 citation; tất cả source IDs thuộc evidence hoặc SOP source set đã cấp và verifier chấp nhận ID/quote. Evidence refs phản hồi khớp snapshot trước request (48 refs, 45 readings; SHA-256 giống nhau). Raw đã khử text nằm tại `docs/evaluation/m6-real-llm-validation-3200-one-call.json`; DB record không lưu prompt hoặc raw completion.

Đối chiếu claim với evidence snapshot: số lượng/received time và event-time range, min/max/peak, sensor interval, door state tại ba thời điểm, M3 detection (33 readings, peak 15.9 °C, đạt thời lượng policy), policy v1.0 (2–8 °C, high duration 30 phút), OPEN state, không có M4 prediction/M5 disposition đều khớp dữ liệu vận hành. Output giữ nhiệt độ sau event time cuối là unknown, không diễn đạt thiếu telemetry là an toàn, không ra quyết định release/quarantine và nhắc Quality Officer giữ thẩm quyền. SOP có hiệu lực từ 2026-11-14 được mô tả là hướng dẫn tại cutoff tháng 11, không bị gán ngược cho incident tháng 10. Đây là đối chiếu của agent với DB, chưa phải đánh giá độc lập của người vận hành.

Một điểm chất lượng câu chữ: phần summary có câu tự hỏi “after cutoff?” rồi tự sửa thành “No”; kết luận cuối chính xác (các readings được nhận trước cutoff) nhưng cách diễn đạt dễ gây hiểu nhầm. Câu trả lời là draft đã lưu append-only; không sửa lịch sử. Cần người review trước khi dựa vào nội dung. Không chạy 40-case evaluation và không gửi thêm request.

### Regression offline mới

Test mới phân biệt JSON không hoàn chỉnh với `finish_reason=length`, JSON hợp lệ nhưng sai schema, citation ID không được truy xuất, quote không khớp, citation hợp lệ và trường hợp HTTP/provider thành công nhưng ứng dụng từ chối. Fixture có sensor evidence khả dụng nhưng không có dữ liệu liên lạc xác nhận evidence có thể hợp lệ đồng thời vẫn phải giữ thiếu liên lạc là không xác định. Targeted M6 regression trong Compose cô lập chạy với provider disabled: **23 passed, 6 dependency deprecation warnings**; log `docs/evaluation/m6-real-validation-offline-tests.txt`. Đây là kiểm tra local/mock, không phải bằng chứng chất lượng inference thật.

## Chuẩn bị offline cho output budget 3.200

Sau request cuối bị `finish_reason=length` tại cap 1.200, chỉ thêm `LLM_MAX_OUTPUT_TOKENS=3200` vào file riêng `.env.m6-real-llm` (Git ignored); không sửa `.env`, JWT/audit secrets hay cấu hình M5. Isolated M6 backend được recreate riêng bằng `--no-deps` và xác nhận runtime config là model `gpt-6-luna`, prompt v2, 3.200 tokens, `reasoning_effort=none`, strict JSON Schema, retry 0, fallback false. Backend M5 đang chạy không có override `LLM_MAX_OUTPUT_TOKENS`; container M5 không bị recreate.

Mocked regression xác nhận orchestration chuyển cap 3.200 cho provider và Chat Completions payload dùng `max_completion_tokens=3200`, không dùng `max_tokens`; strict schema giữ đủ 9 trường cấp cao, toàn bộ trường citation đều required, và Pydantic/citation validator vẫn hoạt động. Một response tối thiểu hợp lệ có citation serialize được thành 313 ký tự; đây chỉ là kiểm tra cấu trúc, không bảo đảm một giải thích đầy đủ sẽ luôn hoàn tất trong 3.200 tokens. Các cutoff thời gian, communications uncertainty và phân biệt thời hiệu SOP trong prompt v2 được giữ nguyên.

Targeted M6 + config regressions: **28 passed, 6 dependency deprecation warnings**, với provider bị disable; log `docs/evaluation/m6-real-llm-3200-offline-tests.txt`. Evidence/SOP preflight trước request: cùng incident revision 1, policy 1.0, 45 readings, 48 evidence references và cùng hash package; năm SOP section được lấy lại đúng như snapshot, có `HIGH_EXCURSION`. QUALITY authentication vẫn hợp lệ. Request mới có ref `M6-REAL-VALIDATION-3200-90963f4153b34039b78413a9ed1fd737`, status `PREPARED_NOT_SENT`; plan `docs/evaluation/m6-real-llm-3200-pending-request.json`. Chưa có provider request nào được gửi sau khi cap được tăng.

## Chuẩn bị đánh giá giải thích 40 ca (2026-11-17)

Đã đóng băng case definitions, rubric, incident map và cutoff tại `m6-real-explanation-manifest-v1.json` cùng raw preflight. Phân biệt rõ fixture retrieval đã tuning (34/40 rồi 40/40), retrieval challenge độc lập v1/v2, runner DRY_RUN và một mẫu provider thật. Chỉ số citation verifier không được xem là semantic entailment. 40 ca được map vào 40 incident và shipment seed-11 khác nhau trong DB cô lập; QUALITY history API cho phép đọc 40/40. Bộ kiểm tra SOP xác nhận 38 kết quả applicable và hai query sai product/version trả no-source. Không có M4 prediction hoặc M5 disposition trong fixture DB.

Pilot 5 ca có kế hoạch cụ thể nhưng `PREPARED_NOT_SENT_WAITING_OWNER_APPROVAL`; lần chuẩn bị này không gọi provider. Ước tính input 12k token/ca, output cap 3.2k; 5 ca tối đa 16k output, 35 ca bổ sung 112k. Human factual/semantic/procedural review chưa chạy. Vì mọi incident fixture có evidence package đủ, thiếu bằng chứng được đánh giá cho từng claim cụ thể; chưa có test status API `insufficient_evidence` toàn package. Xem README M6 và `raw/real-llm-pilot-pending-approval.json`.
# Kết quả pilot real-LLM 5 ca sau phê duyệt owner (2026-11-17)

Owner phê duyệt đúng 5 request; không có request nào trong 35 ca còn lại được gửi. Năm request tuần tự tới OpenAI Chat Completions qua backend project Docker cô lập `coldchain-m6-evalprep`; retries bằng 0, fallback tắt. Không gọi lại case nào. Artifact đã khử nội dung: `docs/milestones/m6/raw/real-llm-pilot-result.json`; hậu kiểm hash evidence: `docs/milestones/m6/raw/real-llm-pilot-postcall-consistency.json`.

| Case | Provider HTTP | API | Citation verifier | Tokens vào/ra | Latency API |
|---|---:|---|---|---:|---:|
| M6R-001 | 200 | `source_mode=llm`, `draft` | passed, 3 | 14.045 / 1.338 | 14.148 ms |
| M6R-006 | 200 | `source_mode=llm`, `draft` | passed, 3 | 7.805 / 1.356 | 13.354 ms |
| M6R-016 | 200 | `source_mode=llm`, `draft` | passed, 3 | 12.730 / 1.336 | 12.446 ms |
| M6R-021 | 200 | `source_mode=llm`, `draft` | passed, 2 | 6.992 / 1.096 | 10.110 ms |
| M6R-036 | 200 | `source_mode=llm`, `draft` | passed, 5 | 7.763 / 1.123 | 11.355 ms |
| **Tổng / trung vị** | **5/5** | **5 draft API chấp nhận** | **16 citation** | **49.335 / 6.249** | **12.446 ms API / 12.385 ms provider** |

HTTP 200/provider response và API accepted draft được ghi thành hai tín hiệu riêng. Năm response đều có citation verification `passed`, citation IDs thuộc source set được cấp, evidence reference digest trùng snapshot pre-call 5/5, và disclaimer QUALITY. Static blocked-phrase scan không phát hiện phrase bị cấm 5/5; đây không phải phán xét ngữ nghĩa hoặc review an toàn đầy đủ. Không lưu prompt hoặc raw generated text. Không có human factual, semantic hay procedural review; không tính điểm cho các metric đó.

**Giới hạn runtime diagnostics:** container chạy pilot không phát các trường finish reason và diagnostics phân giai đoạn. Vì vậy `provider_finish_reason`, parse status, schema status và evidence-validator status là `NOT RECORDED/NOT EXPOSED`; không suy diễn giá trị. Application acceptance chỉ được khẳng định từ kết quả API (HTTP 200, `source_mode=llm`, `draft`, citation pass). Điều này cho thấy năm sample qua acceptance path, nhưng chưa đủ observability để kiểm toán từng stage. Không gửi thêm request để lấp khoảng trống.

Preflight retrieval có hai miss so với section kỳ vọng: `LOW_EXCURSION` không nằm trong kết quả M6R-006, và `QUALITY_REVIEW` không nằm trong kết quả M6R-036. Các citation ID/quote vẫn qua verifier theo source set trả về, nhưng sanitized output không giữ section ID từng citation; vì thế chưa chứng minh được relevance ngữ nghĩa cho hai chủ đề trên. Không tuning sau challenge/pilot. Case delayed M6R-016 chỉ có evidence ứng dụng về gap/delayed readings, không có nguồn route/connectivity độc lập; không kết luận chắc chắn về loại tuyến vận chuyển.

Đây là năm mẫu thật, không phải 40-case evaluation và không chứng minh accuracy, groundedness, procedural correctness hay chất lượng tổng thể. Human reviewer nên dùng checklist `docs/milestones/m6/raw/accepted-explanation-human-review-checklist.md` để đối chiếu số đo, `event_at`/`received_at`, khoảng mất liên lạc, M3, M4 advisory, SOP/version, bất định và quyền QUALITY qua luồng đọc được xác thực. Câu chữ của các draft pilot chưa được review; không sửa các bản ghi append-only. 35 ca giữ trạng thái `NOT RUN` và yêu cầu approval riêng.

# Kiểm toán offline sau pilot 5 ca

Audit report tiếng Việt: `docs/milestones/m6/post-pilot-audit.md`. Backend image cô lập trong pilot có adapter/orchestrator/schema cũ: `GenerationResult` không chứa `finish_reason`; code runtime không tạo stage diagnostics; năm DB rows và API details đều không có `validation_diagnostics`. Do đó giá trị lịch sử không thể khôi phục và không được bịa. Runner evaluator cũng bỏ qua diagnostics nếu API trả về; đã sửa thành allow-list và ghi rõ `not_returned_by_api` nếu vắng mặt. Test dùng response giả, không có network.

Rà read-only qua API QUALITY xác nhận 5/5 bản ghi đúng incident, `llm/draft`, citation pass; 0/5 trả diagnostics. DB mapping xác nhận causal reading refs đầy đủ, toàn bộ reading received trước cutoff. Audit sơ bộ thấy M6R-016 có lỗi rõ: detection raised `2026-09-14T09:51:13Z` bị mô tả là sau cutoff `2026-11-17T08:27:42Z`; các refs temporal đầy đủ nằm trong `raw/real-llm-pilot-temporal-evidence-audit.json`. M6R-006 và M6R-036 miss retrieval là top-k ranking (target rank 6 và 9) chứ không phải applicability filter. `verify_citations` không yêu cầu expected section hoặc semantic entailment. Không tune trên pilot.

Offline tests sau khi thêm reporter regression: **26 passed**, 6 deprecation warnings; provider disabled, fallback false, API key rỗng. Log `docs/milestones/m6/raw/m6-pilot-offline-regression.txt`. Kết quả một test riêng báo cáo runner **3 passed** được giữ trong `raw/m6-pilot-reporting-tests.txt`; suite kết hợp 26 là lần chạy cuối. Docker daemon server 29.8.2 hoạt động qua context `desktop-linux`; lệnh trong sandbox bị socket permission-denied, read-only escalated inspect thành công. Isolated services vẫn healthy; M5 chain/db không được restart hoặc sửa.

Manifest 40 case vẫn có hash nội dung cũ và không bị sửa. Pilot 5 case đã được quan sát nên không tính independent; 35 case chưa chạy, nhưng NO-GO cho hiện tại do temporal failure, retrieval miss, diagnostics deploy gap và semantic review pending. Chỉ giữ 35 làm tranche held-out sau khi sửa version mới, review/freeze, không dùng outcome 35 để tune; chúng không phải independent retrieval challenge vì preflight retrieval trước đó đã được xem.

# Hậu kiểm remediation offline sau pilot

Runtime cô lập được build lại từ source, và readiness xác nhận `m6-post-pilot-temporal-v3`, prompt `response_draft/v3`, `bm25-v2-title25-vn-aliases`. Không request provider nào được gửi. Năm record pilot vẫn nguyên append-only, diagnostics lịch sử vẫn không có; mock API test xác nhận diagnostics mới được serialize/persist. Manifest v1 canonical hash tiếp tục là `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`.

Facts thời gian máy tính UTC tách biệt `event_at`, `received_at`, incident/revision, M3, M4/M5 và SOP effective dates; detection last-event so với latest observed reading cũng được nêu riêng. Output mới có `temporal_claims`, validator đối chiếu source reference/timestamp/relation và fail closed nếu relation mâu thuẫn hoặc câu nói rõ timestamp xảy ra sau cutoff khi evidence nói trước/đúng cutoff. Điều này phát hiện fixture M6R-016. Quy tắc kiểm tra hẹp, không chứng minh mọi câu tự nhiên đúng.

Retrieval production không đổi. Development v1 results hiện được tái tạo: v2 top-1 24/27, hit@3 26/27, MRR 0.935185. Prototype `bm25-v3-intent-prototype` cũng 24/27, 26/27, 0.935185; không có cải thiện. Pilot miss LOW rank 6/9 và QUALITY rank 9/9 giữ nguyên như evidence lịch sử; không dùng làm tune/validation mới. Raw ở `docs/milestones/m6/raw/retrieval-bm25-v3-intent-dev-only.json`; cấu hình đề xuất/tradeoff ở `docs/evaluation/m6-retrieval-v3-proposal.md`.

Targeted offline regressions: **31 passed, 6 dependency deprecation warnings**; xem `docs/milestones/m6/raw/m6-post-pilot-offline-tests.txt`. Human review năm draft vẫn pending; supplemental insufficient-evidence/M4/M5 cases ở `docs/milestones/m6/supplemental-evaluation-plan-v1.md`. **NO-GO** cho pilot mới cho tới khi reviewer độc lập ký worksheet và runtime/prompt/schema được freeze. Còn một Docker image-tag limitation: M6 dùng tag riêng, nhưng tag shared `coldchain-backend:local` vẫn trỏ vào M6 image, trong khi M5 container sống vẫn chạy image ID cũ; không recreate M5 Compose trước khi khôi phục tag/image M5 chính xác.
