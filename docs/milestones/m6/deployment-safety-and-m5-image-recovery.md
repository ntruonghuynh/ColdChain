# An toàn Docker và phương án khôi phục image M5

**Trạng thái:** candidate M5 đã được kiểm thử trong Compose project cô lập bằng dữ liệu mới; chưa đổi tag, chưa sửa/restart container hoặc volume M5 đang hoạt động. Cần owner approval trước mọi tag restoration/deployment mutation.

## Bằng chứng M5 hiện chạy

- Container `coldchain-backend-1`: ID `490e729589f73bace76d7cf6b7fe10834e7f98ec1652581abe49e507baa2ab4f`; image ID `sha256:f2ad35bbb998dcaeaeac1c6974cd52ec2b71c8fd1304a3e367bb5b44169aeaf2`; Config.Image `coldchain-backend:local`; created `2026-11-16T11:15:41Z`; started `2026-11-16T11:15:44Z`. Compose project/service `coldchain/backend`, Compose v5.5.1, working directory repository. Không có `org.opencontainers.image.revision` label.
- Trong container, runtime báo `APP_VERSION=0.1.0`, `CURRENT_MILESTONE=M5`; Alembic read-only check báo `0005 (head)`.
- SHA-256 của `/app/app/core/config.py`, `/app/app/main.py`, `/app/app/api/health.py` khớp blob các file đó tại Git commit `8c9bad1c57daaabebe374aeb5df920ec48b99ab1` (merge M5 lên `main`, ngày 2026-11-16). Đây là commit nguồn phù hợp nhất hiện có, không phải image provenance cryptographic.
- Image `coldchain-backend:local` hiện là `sha256:0decfeed79a0aafb0dea55aa37e357fbb965af908546732d0d9764565f394e12`, tạo `2026-11-17T09:40:39Z`. Image M6 `coldchain-backend:m6-evalprep` là digest khác. `docker image inspect sha256:f2ad…` trả `No such image`; `RepoDigests`/registry provenance cho M5 không còn sẵn.
- Không tìm thấy registry/source label đáng tin cậy gắn với M5 image. Container config chỉ giữ tag `coldchain-backend:local`, không có registry digest. Vì thế không thể khôi phục binary image gốc từ tag/immutable ID hoặc xác nhận nguồn registry.
- M5 source tại commit nêu trên có `backend/Dockerfile` target `runtime`, base `python:3.12-slim` (không pin digest), cài `backend/requirements.txt`, rồi copy migrations, backend, ML package/registry. Requirements được pin chính xác; Dockerfile không khai báo build args. Historical Compose dùng `coldchain-backend:local` cho migrate/backend/worker/tools, `coldchain-backend:test` cho tests, `coldchain-chain:local` và `coldchain-frontend:local`.
- Historical tree có migrations `0001`–`0005`; env contract vận hành gồm PostgreSQL, JWT, demo role passwords, audit signing key và chain/outbox. Container env key names được kiểm mà không đọc/in giá trị secret.

## Nguồn M5 đã tách biệt và quy trình tái dựng đề xuất

Đã tạo source archive chỉ đọc trong thư mục tạm: `raw/m5-rebuild-source-directory.txt` ghi đường dẫn. Archive được tạo bằng `git archive 8c9bad1…`; không checkout/switch branch và không thay working tree. Compose history trong archive resolve `:local`/`:test`, đúng với M5 source.

Sau approval riêng cho build candidate (không phải approval deploy/tag), lệnh candidate an toàn phải dùng tag mới, không dùng `:local`:

```sh
docker build --platform linux/arm64 --target runtime \
  --tag coldchain-backend:m5-candidate-8c9bad1 \
  --file backend/Dockerfile /private/tmp/<isolated-m5-source-dir>
```

Không coi candidate là byte-identical: base `python:3.12-slim` không pin digest, không có build provenance hoặc repo digest gốc. Trước khi cân nhắc sử dụng candidate, cần kiểm tra app version/milestone, platform, command/healthcheck, package versions, migration head `0005`, env **names**/contract, và chạy M5 regression trên DB/chain cô lập riêng. Không mount active volume và không dùng secret hiện hành; tạo demo secrets riêng cho sandbox.

Rollback/deployment plan sau approval phải giữ container M5 đang chạy làm nguồn phục vụ trong thời gian chuẩn bị; chỉ sau owner approval mới có thay đổi deployment. Nếu candidate không qua smoke/health, hủy đề xuất và tiếp tục giữ container hiện tại. Do image gốc đã mất, không có rollback binary chính xác về image ID cũ sau khi recreate M5; owner cần chấp nhận downtime/rủi ro này hoặc tìm backup/registry có provenance trước đó. Không dùng `docker commit` running container.

## Ngăn image-tag collision

Compose M6 hiện yêu cầu tags tường minh cho `BACKEND_IMAGE`, `BACKEND_TEST_IMAGE`, `CHAIN_IMAGE`, `FRONTEND_IMAGE`; không còn default `:local`/`:test`. `.env.example` dùng namespace `:m6-dev`/`:m6-test`; `.env.m6-evalprep` dùng namespace `:m6-evalprep`. Historical M5 source commit vẫn dùng tags cũ và không bị sửa.

Read-only config validation đã chạy:

- Historical M5 archive: backend `coldchain-backend:local`, test `coldchain-backend:test`, chain `coldchain-chain:local`, frontend `coldchain-frontend:local`.
- M6 project kể cả `test` và `tools` profiles: backend `coldchain-backend:m6-evalprep`, tests `coldchain-backend:m6-evalprep-test`, chain `coldchain-chain:m6-evalprep`, frontend `coldchain-frontend:m6-evalprep`.
- Sanitized projection của config đã resolve cho thấy M5 chain/frontend publish `127.0.0.1:8545`/`:3000`, còn M6 publish `127.0.0.1:18549`/`:3107`; PostgreSQL không publish host port. Project M5 là `coldchain`, M6 là `coldchain-m6-evalprep`, nên named volumes cùng logical name `pgdata`/`chain-deployments` được Compose phân vùng theo project. Projection đã bỏ toàn bộ environment fields để không ghi secret.

M6 config được kiểm để đọc; không có `up`, `build`, `pull` hoặc migration trong bước này. Các container hiện chạy vẫn có image IDs trước đó. Khi một M6 developer chọn build, chỉ dùng `--env-file .env.m6-evalprep -p coldchain-m6-evalprep`; không dùng project mặc định `coldchain`.

## Lệnh an toàn và thao tác cần dừng

Các lệnh chỉ đọc sau không khởi động service:

```sh
docker inspect coldchain-backend-1 --format '{{.Id}} {{.Image}} {{.Created}}'
docker image inspect coldchain-backend:local --format '{{.Id}} {{.Created}} {{json .RepoDigests}}'
docker compose --env-file .env.m6-evalprep -p coldchain-m6-evalprep config --images --profile test --profile tools
```

Không chạy `up`, `up --build`, `build` với tag `:local`, `pull`, `down`, `restart`, `rm`, `volume rm`, `system prune`, hoặc bất kỳ lệnh retag nào cho đến khi image candidate, env contract, migration và rollback được owner duyệt. Đặc biệt tránh Compose project `coldchain` từ working tree M6; `.env` cũ chưa đặt các biến tag bắt buộc, nên config sẽ fail thay vì âm thầm dùng M6 tag.

## Trạng thái approval

Chưa đổi shared `coldchain-backend:local`, chưa recreate M5, chưa mutate M5 database/chain/volumes/secrets. Image tag hiện tại vẫn trỏ tới M6 runtime; M5 container sống vẫn chạy image ID cũ. Cần owner approval trước khôi phục shared tag hoặc triển khai candidate. Khuyến nghị không retag: nếu được duyệt sau này, ưu tiên Compose deployment có `BACKEND_IMAGE` trỏ thẳng tới candidate tag riêng.

## Bổ sung kiểm tra offline ngày 2026-11-17

### Image và nguồn M5

- M5 backend, DB và chain vẫn chạy với container IDs lần lượt `490e729…`, `a79299b…`, `ab2856a…`; trạng thái backend/DB/chain vẫn healthy. Backend tiếp tục dùng immutable image `sha256:f2ad35…` qua config ref `coldchain-backend:local`. `docker image inspect` không tìm được immutable ID `f2ad35…` trong local image store.
- Mở rộng kiểm tra read-only cho ba immutable image IDs đang dùng bởi M5 backend, chain, frontend: cả `sha256:f2ad35…`, `sha256:810125…`, `sha256:4dc629…` đều không còn trong local image store. Do đó image gốc của cả ba service không có sẵn để rollback chính xác; các tag `*-m5-recovery-isolated` hiện có là candidate khác, không thay thế được bằng chứng binary gốc.
- Shared tag `coldchain-backend:local` vẫn là `sha256:0decfeed…` (image M6). Không có tag restoration nào được thực hiện.
- Có sẵn image local `coldchain-backend:m5-recovery-isolated`, ID `sha256:3975fa…`, được tạo dưới Compose project cô lập `coldchain-m5-recovery-isolated`. Nó **không phải** image gốc. Ephemeral container với `--network none` báo `APP_VERSION=0.1.0`, `CURRENT_MILESTONE=M5`, Alembic head `0005`; SHA-256 của `app/core/config.py`, `app/main.py`, `app/api/health.py`, `migrations/versions/0005_m5_ledger_security.py` khớp source M5 ở commit `8c9bad1…`. Image labels không có commit revision; các kiểm tra này chưa chứng minh toàn bộ image hoặc dependency/build provenance, nên đây mới là candidate để kiểm tra thêm.
- Candidate backend không có external registry provenance tin cậy được xác nhận. Không pull/push hoặc truy cập registry. Source phù hợp nhất vẫn là Git commit `8c9bad1c57daaabebe374aeb5df920ec48b99ab1`; source archive cô lập có đường dẫn trong `raw/m5-rebuild-source-directory.txt`. Dockerfile target `runtime`, base `python:3.12-slim` không pin digest, cài requirements đã pin và không có `ARG`; do đó build lại không đảm bảo byte-identical với image cũ.
- M5 chain và frontend cũng đang chạy immutable image IDs khác với M6 chain/frontend; không có thao tác nào thay đổi các tag hay container này. Compose M6 được kiểm cấu hình hiện hành: backend `coldchain-backend:m6-evalprep`, test `coldchain-backend:m6-evalprep-test`, chain `coldchain-chain:m6-evalprep`, frontend `coldchain-frontend:m6-evalprep`. Container chain/frontend M6 đang chạy giữ config ref cũ `:local`; chúng không bị recreate vì làm vậy có thể thay đổi chain state. Trước lần rollout M6 đầy đủ tiếp theo, cần đánh giá riêng chain restart và port/volume/project naming. M5 vẫn dùng project `coldchain` và source Compose lịch sử của nó không bị sửa.

### M6 runtime, data, và kiểm thử

- Chỉ build lại tag riêng `coldchain-backend:m6-evalprep` (image ID mới `sha256:03bfdf…`) và recreate riêng service `backend` trong project `coldchain-m6-evalprep` bằng `--no-deps`. DB, chain và frontend M6 không restart. Không gọi Compose project `coldchain`.
- Backend M6 healthy; readiness thực tế qua API HTTP báo runtime `m6-post-pilot-temporal-v3`, prompt `response_draft/v3` và SHA-256, schema `explanation-content/v2` và SHA-256, adapter `openai-chat-completions/v1`, retriever `bm25-v2-title25-vn-aliases`, corpus 9 chunks. `provider_status=configured` chỉ phản ánh cấu hình; không có provider request nào được gửi.
- `/api/health` trả API/database `ok`, migration đang dùng và kỳ vọng đều `0006`. Bảng append-only vẫn có đúng 5 bản ghi pilot. M6 chain block height vẫn `0x1`; M5 chain block height read-only là `0x4a7`. Record DB/chain chỉ được đọc; không ghi.
- Chạy targeted offline M6 tests trong image test riêng với provider disabled: **35 passed, 0 failed, 6 cảnh báo deprecation**. Bao gồm cutoff/event-received time, UTC, timestamp thiếu, ngày hiệu lực SOP, M6R-016 contradiction, temporal reference/relation sai, schema/citation/provider diagnostics, API mocked-provider, readiness version metadata và Compose tag guard. Lệnh trên host không chạy được vì Python host thiếu FastAPI; lần Docker-based đã qua. Raw: `raw/m6-deployment-offline-regression.txt`.
- Compose image resolution, readiness JSON, migration/record count, chain heights, M5 container inventory và manifest integrity được lưu ở các `raw/m6-*` / `raw/m5-*` evidence tương ứng. Canonical SHA-256 của manifest v1, loại trường self-hash theo protocol, vẫn `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`; file manifest không bị sửa.
- Worksheet năm draft nằm tại `raw/real-llm-pilot-case-review-worksheet.md` và mapping claim/evidence/citation tại `raw/real-llm-pilot-quality-api-review-input.json`. Judgment semantic/operator-facing vẫn **CHƯA REVIEW**. Draft M6R-016 giữ nguyên sai lệch thời gian đã báo; không sửa record hay metadata append-only.

### Kế hoạch rollback và cổng phê duyệt

Rollback an toàn hiện tại là **không chạm vào M5**: các container hiện hữu tiếp tục chạy image IDs của chúng. Image gốc của backend, chain, frontend không thể khôi phục từ local immutable IDs vì chúng không còn; nếu recreate M5 trước khi xác minh candidate thì không có binary rollback chính xác. Các image `m5-recovery-isolated` chỉ là candidates; backend có một số source/hash checks, chain/frontend chưa được kiểm source; chưa candidate nào được tuyên bố tương đương hoặc sẵn sàng triển khai.

Không thực hiện `docker tag`, build/retag vào `coldchain-backend:local`, `docker compose up` cho project M5, hay restart/recreate M5 trước khi owner phê duyệt. Sau approval riêng, bước tiếp theo nên là hoàn tất kiểm tra candidate trên DB/chain độc lập, xác nhận Dockerfile/requirements/env contract/migration và smoke M5, rồi xin approval triển khai riêng; giữ container đang chạy cho tới khi có kế hoạch chuyển đổi được duyệt. Image gốc mất đồng nghĩa không thể cam kết rollback binary về đúng ID cũ.

## Kiểm thử candidate cô lập và trạng thái hiện tại (2026-11-17)

Tạo Compose project độc lập `coldchain-m5-validation-8c9bad1-20261117`, volume/network riêng, host ports `28545`/`23000`, image tags candidate riêng và secrets ngẫu nhiên chỉ dùng cho demo. Không mount volume, chain, hoặc secret của project M5 đang hoạt động. Backend/DB/chain/worker/frontend của project này từng báo healthy; migration và deployment bước đầu kết thúc thành công. Project đã dùng một fixture synthetic mới, không đọc production records.

Kết quả thực thi trong môi trường này:

- M5 backend suite: **229 passed**, 6 warnings; chỉ `backend/tests`, không chạy generator suite hay seed M9. Log: [`m5-candidate-backend-tests.txt`](raw/m5-candidate-backend-tests.txt).
- Hardhat: **6 passing**, gồm role, transition, duplicate và release checks; log: [`m5-candidate-hardhat-tests.txt`](raw/m5-candidate-hardhat-tests.txt).
- HTTP health/frontend: `/`, `/shipments`, `/api/health`, `/api/policies?status=ACTIVE` trả HTTP 200; revision hiện tại/kỳ vọng là `0005`, policy `POL-CHILL-01`. Raw: [`m5-candidate-frontend-and-health-smoke.json`](raw/m5-candidate-frontend-and-health-smoke.json).
- Authenticated workflow qua API: SHIPPER registration, CARRIER pickup, telemetry batch, MONITOR incident open bằng tổ chức receiver, WAREHOUSE delivery, QUALITY RELEASE, WAREHOUSE release. Wrong-role bị 403; invalid/premature transitions 409; replay registration/batch idempotent; 7/7 business refs khớp; reconciliation 7/7 OK; signed audit hợp lệ. Kết quả đầy đủ: [`m5-candidate-authenticated-workflow.json`](raw/m5-candidate-authenticated-workflow.json). Đây là kết quả một fixture cô lập, không phải đánh giá hiệu năng tổng quát.

Candidate `coldchain-backend:m5-recovery-isolated` không có provenance binary gốc, nhưng 13 file build/config nguồn đã khớp commit `8c9bad1c57daaabebe374aeb5df920ec48b99ab1`; container candidate báo app `0.1.0`, milestone M5, migration head `0005`. Test và workflow ở trên cung cấp đủ bằng chứng để owner review candidate cô lập. Chúng **không chứng minh binary-identical** với image M5 mất, cũng không xác nhận chain/frontend candidate tương đương hoàn toàn với image đang chạy.

### Collision guard, runtime freeze và review M6

Compose M6 resolve image tags riêng: backend `coldchain-backend:m6-evalprep`, tests `coldchain-backend:m6-evalprep-test`, chain `coldchain-chain:m6-evalprep`, frontend `coldchain-frontend:m6-evalprep`. M5 history vẫn dùng `:local`/`:test`; M6 Compose regression test kiểm tra explicit variables, tags riêng, project name `coldchain-m6`, không dùng `container_name`/external volume. Read-only `docker compose ... config --images` đã trả các tag M6 riêng. M6 service containers M5/M6 không được restart trong phần kiểm tra này.

Đề xuất freeze đầy đủ, source manifest hash, runtime/image/prompt/schema/retriever/provider/evaluation identifiers và blockers được lưu tại [`m6-release-candidate-freeze-proposal.json`](m6-release-candidate-freeze-proposal.json). Đây mới là **đề xuất, chưa freeze**: worktree dirty; build input không được khóa tại thời điểm build; pilot M6R-016 còn temporal error; human semantic review năm draft đang chờ; hai pilot retrieval miss chưa xử lý; 35 case còn NOT RUN. Manifest v1 canonical SHA-256 vẫn `9bfe4d64fff7f03f5dbb538fd7352d834c4c1729b24220a79ca6fa6926bac244`.

Worksheet cho người review năm draft được lưu tại [`real-llm-pilot-human-review-packet.md`](real-llm-pilot-human-review-packet.md), cùng raw authorized QUALITY extract tại `raw/m6-quality-api-review-extract-verified.json`. M6R-016 được đánh dấu rõ lỗi thời gian; M6R-006 và M6R-036 được đánh dấu retrieval miss. Mỗi kết luận semantic vẫn để trống PASS/FAIL/NEEDS_MORE_EVIDENCE; không sửa draft append-only.

### Giới hạn truy cập Docker và quyết định khuyến nghị

Trong lượt kiểm tra cuối, Docker CLI context là `desktop-linux`; thao tác read-only tới daemon lỗi `permission denied` tại `~/.docker/run/docker.sock`. Không dùng sudo và không thử restart Docker Desktop. Vì vậy không thể xác nhận lại trạng thái hiện tại của containers/chain height hoặc chạy lại Docker test image. Các kết quả container nêu trên là raw evidence đã lưu từ lần chạy cô lập trước; lỗi socket không được diễn giải là container hiện tại healthy hay unhealthy.

- **Candidate M5 recovery readiness: GO cho owner review ở môi trường cô lập**, với giới hạn không binary-identical và chain/frontend chưa có kiểm thử tích hợp đầy đủ.
- **Production tag restoration: NO-GO.** Image gốc thiếu; rollback binary chính xác không khả dụng. Không retag hay deploy; cần approval riêng trước bất kỳ mutation nào và kế hoạch chuyển đổi có chấp nhận rủi ro.
- **M6 provider pilot mới: NO-GO** cho tới khi người review xem năm draft và có phiên bản freeze được owner duyệt.
- **M6 release acceptance: NO-GO** do temporal error lịch sử, semantic review chưa xong, retrieval coverage misses và 35 ca chưa chạy.

Không có provider request, M9 seed, active M5 container/volume/database/chain mutation hoặc shared image retag trong lượt này.

## Cập nhật provenance quyết định human review do owner báo cáo (2026-11-17)

Owner cung cấp PASS cho M6R-001, M6R-006, M6R-016, M6R-021 và M6R-036; các worksheet đã ghi nguyên văn với provenance `OWNER_REPORTED`. Không có reviewer ID, `reviewed_at`, rationale hoặc reviewer-selected evidence refs; thời điểm ghi hồ sơ `recorded_at` được tách biệt. Counts là owner-reported PASS 5, FAIL 0, NEEDS_MORE_EVIDENCE 0, quyết định chưa được cung cấp 0; independent substantiation vẫn **NOT ESTABLISHED**. Xem [human-review summary](human-review/README.md).

Các quyết định đó không đóng findings: M6R-016 vẫn bị chặn bởi `KNOWN_MATERIAL_TEMPORAL_CONTRADICTION` đến khi có explicit defect disposition và evidence; M6R-006 `LOW_EXCURSION` và M6R-036 `QUALITY_REVIEW` vẫn thiếu retrieval top-5 và semantic support chưa được chứng minh. Không sửa các historical append-only explanation, frozen manifest, M5 service hay chain.
