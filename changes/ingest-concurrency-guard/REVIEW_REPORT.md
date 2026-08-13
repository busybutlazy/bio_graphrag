# Review Report: ingest-concurrency-guard

## Review Context

- **Diff base and scope**:`main` @ `57d721e` → `feat/ingest-concurrency-guard` @ `a42b278`
  （單一 commit）。程式與文件共 8 檔、**+479 / −3**，與 `CHANGE_REPORT.md` §2 的宣稱**逐字相符**
  （`git diff main..HEAD --stat -- . ':(exclude)changes/'` 實測）。另有 4 個 `changes/` 產出物。
  **所有變更檔案皆落在 Plan 批准的路徑清單內，無範圍外編輯。**
- **Artifacts reviewed**：`IMPLEMENTATION_PLAN.md`（rev 1，Approved / jett / 2026-08-13）、
  `TASK_LOG.md`、`VERIFICATION_REPORT.md`、`CHANGE_REPORT.md`、完整 diff、
  `.github/workflows/ci.yml`、`ingestion/pipeline/schema.sql`、
  `routes_ingest.py` / `runner.py` / `load_postgres.py` 的周邊既有程式。
- **Independence disclosure**：本次審查在**全新 session** 進行，未參與本變更的規劃或實作，
  未共用實作 context。但審查者與實作者為同一模型家族，且共用同一份專案文件；
  **設計決策（D1 索引 vs advisory lock、D2 `STALE_AFTER=2h`）已由人類批准，本報告不重開該決策**，
  只檢驗實作是否兌現它。
- **本次審查未修改任何程式碼**。唯一寫入為本檔。所有驗證皆為唯讀查詢、容器內測試、
  或在 `BEGIN … ROLLBACK` 內以 temp table 進行的探測。

## Completion Claim Assessment

**完成宣稱大致成立，且比報告自己宣稱的更強。** 8 條 AC 我逐條追到實作與測試；
兩項報告自陳「未驗證」的殘留風險，我實地打過，**結果對本變更有利**。

獨立複驗（非引用報告數字）：

| 檢驗 | 命令 / 方法 | 結果 |
|---|---|---|
| 索引真的存在且述詞正確 | `psql pg_indexes` | `ingestion_jobs_one_running_extract_per_source ... USING btree (source_path) WHERE ((status='running') AND (job_id ~~ 'ingest:%'))` —— 與 `schema/graph_schema.md` 記載**完全一致** |
| 8 個 guard 測試 | `docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_document_ingest.py -k …` | **8 passed, 10 deselected**（檔案共 18 = 10 既有 + 8 新，與 TASK_LOG 相符） |
| HTTP 409 測試 | `… pytest tests/integration/test_ingest.py -q` | **12 passed**（11 既有 + 1 新） |
| lint 三項（第一輪的失敗點） | 拋棄式 `python:3.12-slim` 容器跑 `ruff check` / `ruff format --check` / `mypy` | `All checks passed!` / `107 files already formatted` / `no issues found in 83 source files`，**三者 exit 0** |

**AC 追溯**：AC1–AC7 皆有對應測試且測試名稱誠實描述其斷言（特別是
`test_a_second_ingest_of_the_same_source_spends_nothing` 真的斷言 `calls == []`，
不是只斷言拋例外——這是本變更的核心宣稱，測試沒有偷工）。
AC8 的基準 232 是 **TASK_LOG 實測所得**（非引用 handoff 文件），Plan 也明確要求如此，已兌現。

### 兩項「已知限制」經實地打擊後不成立（有利揭露）

- **`CHANGE_REPORT` L1 /「沒有真正的競態驗證」——我打了，防護成立。**
  以 6 條各自獨立的 asyncpg 連線同時 `asyncio.gather` 呼叫 `claim_ingest_source`：
  ```
  winners: 1  refused: 5  unexpected: []
  rows in table: 1
  blocking job reported: ['ingest:race-0']
  ```
  真實競態下**恰好一個贏家、五個乾淨的 `IngestAlreadyRunning`、表中只有一列**，
  且五個被拒者都正確回報同一個擋住它們的 job_id。原子性不只是「由 Postgres 保證」的推論。
- **`CHANGE_REPORT` L6 / Plan R5「重複 running 列時 migration 未驗證」——我打了，UPDATE 正確。**
  在 `BEGIN … ROLLBACK` 內以 `CREATE TEMP TABLE … (LIKE ingestion_jobs)` 造出
  同一 source 三列 running（3h / 2h / 1h 前）、另一 source 一列、外加兩列 `job:` seed 列，
  跑 `_MIGRATION_INGEST_CONCURRENCY_GUARD` 的 UPDATE：
  `UPDATE 2` —— 保留最新的 `ingest:new`，關掉 `ingest:old` 與 `ingest:mid`，
  `job:seedx/seedy` **未被動到**，每個 source 剩下恰好一列 running。
  → `CREATE UNIQUE INDEX` 在有重複列的機器上也會成功，**Plan R5 點名的「後端起不來」自傷風險不成立**。
- **`VERIFICATION_REPORT` §6「`make eval` 在 CI 是否為 openai 模式未查證」——已可結案。**
  `.github/workflows/ci.yml` 的 test job 只做 `cp .env.example .env`，
  **全 workflow 未引用任何 `secrets`**，因此 CI 的 `make eval` 走離線路徑、不花錢。
  D-1 的花費是**本機獨有**的問題，不會在 CI 重複發生。

## Findings

### Blocking

無。

### High

無。

### Medium

**M-1 —— 409 訊息在孤兒鎖情境下給出的是錯誤指示，且沒有給出脫困路徑。**

- **Evidence**：`backend/app/api/routes_ingest.py:203-209`
  訊息無條件寫「**請不要重試**:先前的 504 只代表 nginx 等不到回應,不代表後端失敗。」
  同時 `ingestion/pipeline/load_postgres.py:20-27` 的註解把孤兒成因描述為
  「Only a hard kill (container OOM/SIGKILL)」。
- **Violated requirement / risk**：這兩句只在「擋住你的 job 真的還活著」時成立。
  但**最容易製造孤兒列的不是 OOM，而是 `make up`**（`docker compose up -d --build`，
  本專案的標準指令）——匯入進行中重建 backend，行程被殺、`finally` 不會執行，
  留下 `running` 列，該章節被鎖 **2 小時**。此時後端**確實**失敗了，訊息卻斷言它沒有；
  而正確做法（等 2 小時，或執行 `docs/api_contract.md` 那段手動 UPDATE）
  **完全不在訊息裡**，操作者唯一的線索是「去查 `ingestion_jobs` 表」。
- **Impact**：本變更新增的溝通管道，在最可能發生的失敗情境下給出**反向指示**。
  這與變更自身的立論一致——「防護不能依賴操作者判讀正確」——訊息卻要求操作者
  自行判讀擋住它的 job 是活的還是死的。非資料風險，是可用性缺陷。
- **Bounded remediation direction**：在 409 訊息末段補一句條件式指引，
  例如「若你剛重啟過 backend，這一列可能是中斷殘留;它會在 2 小時後自動失效，
  或依 `docs/api_contract.md` 手動關閉」。**不需要改防護邏輯，只改文案。**
  （更完整的做法是回報 `started_at` 距今多久，但那超出本次範圍。）

### Low

**L-1 —— 防護鍵是 `source_path`，但破壞性寫入鍵是 `doc_id`，兩者可以不一致。**

- **Evidence**：`ingestion/extract/runner.py:340` `delete_chunks_for_doc(pg_conn, doc.doc_id)` 與
  `:343` Qdrant 的 `delete_chunks_for_doc(..., doc.doc_id, ...)`；
  `ingestion/extract/parse_document.py:85` `doc_id = meta.get("doc_id") or f"doc:{path.stem}"`。
- **Violated requirement / risk**：`doc_id` 來自 front-matter，缺省才退回檔名 stem。
  因此 `data/sample/chapters/x.md` 與 `data/private/chapters/x.md`（同 stem），
  或任意兩個手寫了相同 `doc_id:` 的檔案，是**兩個不同的 source_path 但同一個 doc_id**。
  防護放行，兩次抽取同時跑，各自 `delete_chunks_for_doc(doc_id)` → `upsert_chunks`，
  後到的 delete 可能清掉先到者剛寫好的 chunks（Postgres 與 Qdrant 皆然）。
- **Impact**：資料一致性缺口，非重複扣款。觸發條件窄（需要 doc_id 撞名），
  且 Plan 已明確把「跨來源互斥」列為 Out of Scope，**這不是偏離批准範圍**。
  但 `docs/api_contract.md` 第 3 點寫「不同章節同時抽取是兩份不同的工作，不是重複」，
  這句話**只在 doc_id 相異時成立**，目前未被任何機制保證。
- **Bounded remediation direction**：不必擴大本次範圍。最小處置是在 `docs/api_contract.md`
  第 3 點加一句限定（「前提是兩個來源的 `doc_id` 不同」），並記入 `docs/notes.md` 作為後續項目。

**L-2 —— 擋住的 job 在 INSERT 失敗與查詢之間結束時，訊息退化且指示仍為「不要重試」。**

- **Evidence**：`ingestion/pipeline/load_postgres.py` `claim_ingest_source` 的
  `blocking = await conn.fetchrow(...)`（註解已誠實承認此窗口），
  搭配 `routes_ingest.py:202` 的 `"未知時間"` fallback。
- **Violated requirement / risk**：此路徑產生的訊息是
  「job_id=None,開始於 未知時間 … **請不要重試**」——但此刻來源**已經空出來**，
  重試會立刻成功。操作者被明確勸阻去做唯一正確的事。
- **Impact**：極罕見（毫秒級窗口），無資料風險，純誤導。
- **Bounded remediation direction**：`blocking is None` 時重試一次 claim（成功即照常進行），
  或至少讓該情境走另一段文案。

**L-3 —— HTTP 測試在真實 demo 章節上留下 `running` 列，只靠 `finally` 清除。**

- **Evidence**：`backend/tests/integration/test_ingest.py`
  `test_run_refuses_a_second_ingest_of_the_same_source` 以
  `_resolve_source(DEMO_SOURCE)` 的**真實絕對路徑**寫入 `ingest:test-in-flight`。
- **Violated requirement / risk**：pytest 被硬性中止（容器被殺、CI job cancel）時
  `finally` 不執行，demo 章節在該 DB 上被鎖 2 小時。CI 每次 `down -v` 不受影響，
  **開發機會中招**，且症狀（`/admin/ingest/run` 回 409）與真實事故無法區分。
- **Bounded remediation direction**：改用一個不對應真實檔案的 source_path，
  或在測試 setup 先做 `DELETE … WHERE job_id LIKE 'ingest:test-%'`。

### Suggestion

- **S-1 —— 前綴耦合（`CHANGE_REPORT` L2）已誠實揭露並在兩處文件點名，但沒有守衛。**
  `EXTRACT_JOB_PREFIX` 與索引述詞的 `'ingest:%'` 是兩份副本，改一邊防護會靜靜失效而測試全綠。
  一行測試即可封住：`assert load_postgres.EXTRACT_JOB_PREFIX == "ingest:"`，
  搭配指向 migration 的註解。成本近乎零，擋住的是「靜默失去防護」這種最貴的失效。
- **S-2 —— `_second_connection()`（`ingestion/tests/test_document_ingest.py`）逐字複製了
  `ingestion/tests/conftest.py::pg_conn` 的連線參數。** 目前兩者一致（已比對），
  但若 conftest 改用不同來源，這裡不會跟著改，「兩條連線指向同一個 DB」這個前提會**靜默變假**，
  而測試仍會通過（連不上才會失敗，連到別處不會）。建議把連線工廠抽到 conftest 供兩者共用。
- **S-3 —— `ensure_schema` 現在每次 `/admin/ingest/run` 與每次啟動都跑一次全表 UPDATE。**
  目前 `ingestion_jobs` 約 100 列，成本可忽略；此表只增不減。若日後成長，
  可考慮把該 UPDATE 收斂為只在索引尚不存在時執行。**現階段不建議動**（YAGNI）。

## Requirement and Test Coverage Gaps

- **AC1–AC7 覆蓋充分且測試斷言誠實**，無 mock-only 宣稱：DB 層行為以真實 Postgres 驗證，
  runner 層以注入的 `extract_fn` 計次驗證，HTTP 層以 `TestClient` 打真實路由驗證。
- **測試特意避開了兩個「會因錯誤理由通過」的陷阱**，值得記錄：
  HTTP 測試 monkeypatch `llm_client.is_configured` 為 True（否則 409 之前先撞 `llm_not_configured`），
  DB 測試堅持開第二條連線（單連線測試對 advisory lock 也會通過，證明不了連線無關性）。
  這兩點是本變更測試設計中最紮實的部分。
- **仍無覆蓋**：孤兒 2 小時門檻的端到端路徑（只有以 `started_at` 回推時間的單元測試）；
  前綴耦合（S-1）；前端 409 的實際渲染。三者皆已在 `CHANGE_REPORT` §6 誠實列出。

## Compatibility, Security, and Scope Assessment

- **契約**：純加法。新增 `409 ingest_already_running`，成功回應形狀與既有錯誤碼未動。
  `docs/api_contract.md` 已同步且內容與實作一致（我逐項比對訊息文案、索引述詞、手動解除 SQL，皆相符）。
- **Schema**：僅新增部分唯一索引，無欄位變更。`schema/graph_schema.md` §2.3 的 DDL 與
  線上 `pg_indexes` 的實際定義**逐字相符**。
- **Migration 安全性**：一次性正規化 UPDATE 的作用域正確（見上方 temp-table 實測），
  且**不會誤傷 seed 路徑**（`job:` 前綴被述詞排除，已實測）。本機執行為 0 列 no-op。
- **離線姿態未被破壞**：新增路徑不觸碰 LLM，全部新測試皆在 `-e OPENAI_API_KEY=` 下通過。
- **`status='approved'` 不變式**：本變更未新增任何檢索查詢，無影響。
- **授權**：409 訊息洩露 `job_id` 與開始時間，但呼叫者必須同時通過 `require_admin`
  與 `require_ingest_owner` 兩道 gate，**無新增資訊揭露面**。
- **Rollback**：`CHANGE_REPORT` §8 誠實指出 revert **不會**移除索引並附上 `DROP INDEX`，
  也正確說明留著無害。一次性 UPDATE 不可逆但本機影響 0 列。**Rollback 敘述可執行、無誇大。**
- **範圍紀律**：8 個變更檔全部在批准清單內；無範圍外重構、無新增依賴、
  無 `start_ingestion_job` 的破壞性改寫（seed 路徑逐字未動，並有測試守住）。

### 偏差處置意見（不構成核可）

- **D-1（`make eval` 花了真實 token，與 Plan 宣稱的「token 預算 0」牴觸）**——
  揭露誠實且未被合理化，矛盾的根源確實在 Plan 本身。補充一項對處置有用的事實：
  **CI 不會重演**（workflow 無 secrets）。這是本機驗證姿態的問題，不是本變更的缺陷。
- **D-2（第一輪 `ruff format --check` 失敗後停止回報，未自行修復）**——
  處理方式**符合** Plan 的 mandatory stop condition 與 `run-approved-change` 的邊界。
  修復後三項 lint 我已獨立複跑通過。
- **D-3（多加一個測試 `test_a_job_just_short_of_stale_still_blocks`）**——
  在批准檔案內，且守住的正是 D2 那個「寧長勿短」的刻意取捨。**理由成立。**

## Unreviewed Areas and Residual Risk

- **未在乾淨 volume 上驗證**。我沿用了現有的非乾淨開發 DB，因此
  `test_pipeline_run_is_idempotent` 這個既有 flake 我沒有重現也沒有排除
  （本次我未重跑全套 232+9，只跑了兩個變更檔共 30 個測試 + 三項 lint）。
  CI 從 `docker compose down -v` 後的乾淨 runner 起跑，才是硬證據。
- **未做人眼前端驗證**。409 在 `frontend/app.js` 的實際渲染仍是讀碼推論。
  M-1 若採納，改的正是這段沒人看過的文案，屆時值得一併目視。
- **未驗證真實的 2 小時孤兒接手路徑**（需要等 2 小時或改系統時間）。
  邏輯已由 `test_claim_takes_over_a_stale_orphan` 與
  `test_a_job_just_short_of_stale_still_blocks` 從兩側夾住，我認為殘留風險低。
- **未執行任何真實抽取**，因此「409 之後第一個 job 仍能正常跑完」這條路徑
  只有邏輯保證（claim 在 `try/finally` 之外，被拒時不會誤呼叫 `finish_ingestion_job`——
  我逐行確認了 `runner.py:257` 在 `:271` 的 `try` 之前）。
- **`make eval` 我未重跑**（會花真實 token）。沿用驗證報告的第二次 `passed=True`。

## Human Disposition Required

- **M-1** 是我唯一建議在合併前處置的項目，且只需改文案，不動邏輯。
- **L-1 / L-2 / L-3 與 S-1 ~ S-3** 可留作後續項目；L-1 的最小處置是補一句文件限定。
- 若決定不處置 M-1，本變更在功能面仍達成其目標——防護本身經真實競態驗證是正確的。

The reviewer does not approve, fix, merge, or release this change.

---

# 追加審查:修復後複驗（2026-08-13）

**範圍**:`8be0e86 fix(ingest): say which kind of stuck job the operator is looking at`
（`a42b278` → `8be0e86`）。**M-1 與 S-1 已修，無迴歸，無範圍外編輯，防護邏輯逐行未動。**

## 處置確認

| 發現 | 處置 | 複驗 |
|---|---|---|
| **M-1**（Medium） | 409 訊息改為條件式；`load_postgres` 註解與 `docs/api_contract.md` 孤兒段同步 | ✅ 前提我獨立驗證：`docker-compose.yml` **未設 `stop_grace_period`** → docker 預設 10 秒，4 分鐘的抽取必被 SIGKILL。實作者的成因分析成立 |
| **S-1**（Suggestion） | 新增 `test_the_index_predicate_and_the_job_prefix_stay_in_sync` | ✅ 斷言真的會咬：改常數而不改 migration 會立刻紅；`claim_ingest_source` 與 `runner` 都以參數方式跟隨常數，唯一的「存下的 SQL 副本」正是被釘住的那一份 |
| **L-1 / L-2 / L-3 / S-2 / S-3** | 記入 `docs/notes.md` N9 | ✅ 五項全在，摘要與處置方向皆與本報告一致，**無一被靜默丟棄** |

**獨立複跑**（非引用 TASK_LOG R1 的數字）:

- `pytest ingestion/tests/test_document_ingest.py tests/integration/test_ingest.py -q` → **31 passed**
  （前一輪同樣兩檔為 30，恰好 +1，與 241 → 242 的宣稱一致）
- `ruff check` / `ruff format --check` / `mypy`（拋棄式容器）→ **三者 exit 0**
- `git show 8be0e86` 逐行確認:`routes_ingest.py` 只改註解與訊息字串，
  `load_postgres.py` 只改註解，測試檔純新增。**`claim_ingest_source`、migration SQL、
  索引述詞、runner 的 claim 位置皆未被觸碰。**

**流程面**:本報告以 211 行原樣進 commit，findings 與末句「The reviewer does not approve」
未被更動；實作者改在 `CHANGE_REPORT` §6.1 與 `TASK_LOG` R1 回應。**審查產出物的所有權被尊重。**
`CHANGE_REPORT` §6 亦誠實把 L1/L6 標為「審查已推翻」而非悄悄刪去。

## 本輪新發現（皆為 Low / Suggestion，不影響功能）

**N-1 —— 產出物數字未隨修復更新，彼此不一致。**
`CHANGE_REPORT.md` §2 仍寫「9 個新測試」與「`git diff --stat`:8 檔、+479 / −3」，
實際為 **10 個新測試、+527 / −3**（實測）。`VERIFICATION_REPORT.md` 仍停在 241 passed，
R1 那一輪的證據只存在於 `TASK_LOG.md`。單獨打開驗證報告的人會看到對不上的數字。
**處置**:兩處各改一行；或在驗證報告加一句指向 TASK_LOG R1。

**N-2 —— M-1 修復的那半段訊息沒有任何測試守住。**
`test_run_refuses_a_second_ingest_of_the_same_source` 的
`assert "不要重試" in error["message"]` 仍然通過——但它現在命中的是條件句
「**若那個 job 還在跑,請不要重試**」，而**新增的孤兒指引（重啟殘留、2 小時、手動關閉）
完全沒有斷言**。日後有人刪掉那半段，測試仍綠，M-1 會靜靜復發。
這正是 S-1 想防的那類失效，只是換了個地方。
**處置**:在同一測試補一句對孤兒半段的斷言（例如 `"重啟" in message` 或 `"手動關閉" in message`）。

**N-3 —— N9 那條 `CancelledError` 觀察是推理，不是實測，且結論只寫了一半。**
筆記斷言「優雅取消時 job 會被記成 `success`……方向安全（錯誤地釋放鎖，不是洩漏鎖）」。
但 `finally` 裡的 `await finish_ingestion_job(...)` 本身也可能被取消打斷，
那一列就會留在 `running` → **鎖被洩漏 2 小時**，方向相反。兩種結果都可能，取決於取消時機。
**處置**:把 N9 該條改成「兩種結果皆可能，未實測」，免得日後有人依「方向安全」的結論決定不處理。

**N-4（沿用，未變）**——訊息裡的 `**` 是字面字元。
`frontend/app.js` 以純文字顯示 `error.message`，操作者會看到星號；現在有兩對。
與 `CHANGE_REPORT` L3（前端無人眼驗證）是同一個缺口，不是本輪新增。

## 追加審查結論

M-1 的修法正確且克制:**只改文案與註解，沒有為了修文案去動防護**——這在
「保護不能依賴操作者判讀」的立論下是正確的取捨。S-1 的守衛選在了唯一真正危險的那一份副本上。
N-1 ~ N-3 皆為一行級處置，是否在合併前處理由人類決定；**N-2 是三者中最值得做的**，
因為它守的是剛剛才修好的東西。

The reviewer does not approve, fix, merge, or release this change.
