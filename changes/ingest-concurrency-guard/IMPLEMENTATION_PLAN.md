# Implementation Plan: ingest-concurrency-guard

對應 `docs/notes.md` 的 **N8**,並依 2026-08-13 的人類決策**只採方向 (c)**:
在後端加「同來源進行中 job」的併發防護,讓誤判逾時後的重試變成無害。
方向 (a)(調高 nginx 逾時)與 (b)(改非同步 job_id + 輪詢)本次不做。

## Objective

`POST /admin/ingest/run` 是同步阻塞的:四個 chunk 約 4 分鐘,超過 nginx 預設代理逾時,
**nginx 回 504 但後端其實跑完了**。操作者(或 agent)把 504 讀成失敗而重試,於是第二次抽取
與第一次同時在跑,重複燒掉約 15–25k tokens——這是 2026-08-12 真實發生過一次的損失。

本變更讓**重複提交在花掉任何 token 之前就被擋下**,並回一個看得懂的 409,告訴操作者
「已經有一個針對此來源的匯入在跑,job_id 是什麼、什麼時候開始的」。防護放在**後端**而非
介面提示,因為它不能依賴操作者判讀正確——這正是上次失敗的環節。

## In Scope

- `ingestion/pipeline/schema.sql` 或 `load_postgres` 的 migration 常數:
  新增「每個 source 最多一列進行中的抽取 job」的**部分唯一索引**,以及一次性的既有孤兒列正規化。
- `ingestion/pipeline/load_postgres.py`:
  - 新增 `EXTRACT_JOB_PREFIX` 常數(取代 runner 內寫死的 `"ingest:"`)。
  - 新增 `claim_ingest_source(...)`:先釋放逾時的孤兒列,再原子地宣告本次 job;
    宣告失敗時丟 `IngestAlreadyRunning`(帶進行中的 `job_id` 與 `started_at`)。
- `ingestion/extract/runner.py::ingest_document`:非 dry-run 路徑改用 `claim_ingest_source`
  取代 `start_ingestion_job`,位置在**任何 LLM 呼叫之前**。
- `backend/app/api/routes_ingest.py::ingest_run`:把 `IngestAlreadyRunning` 對映為
  `APIError(409, "ingest_already_running", ...)`。
- `docs/api_contract.md`:記錄 `POST /admin/ingest/run` 新增的 409 錯誤碼與語意。
- `docs/notes.md`:更新 N8 狀態(記錄只做了 (c),(a)/(b) 仍未做)。
- 對應測試(全離線,以注入的 `extract_fn` 驅動,**零 token 花費**)。

## Out of Scope

- **不動 nginx 設定**(方向 a)。504 仍會發生;本變更只讓「看到 504 後重試」不再重複扣款。
- **不改為非同步 job_id + 輪詢**(方向 b)。`POST /admin/ingest/run` 的成功回應形狀完全不變。
- **不動前端**。`frontend/app.js:45` 的 `apiError` 已會顯示 `error.message`,409 直接渲染成中文訊息,
  不需要新的 UI 分支。
- **不保護 seed 管線**(`ingestion/pipeline/run.py`,job_id 前綴 `job:`)。索引以
  `job_id LIKE 'ingest:%'` 限定,`make seed` 行為完全不變——它是冪等、離線、不花錢的路徑,
  沒有本變更要解決的損失。
- 不做跨來源的全域互斥(不同章節同時抽取是兩份不同的工作,不是重複)。
- 不動抽取、切分、staging、gate、lens、Neo4j、Qdrant 的任何語意。
- 不新增 production dependency。

## Current-State Evidence

- **Repository state**:分支 `main` @ `57d721e`(PR #20 已合併)。`git status --porcelain` 僅一個
  未追蹤檔 `docs/handoff-2026-08-12.md`(上一位的交接文件,不屬本變更,不會被動到)。
  五個服務皆 `running`(`docker compose ps`)。
- **Relevant files and symbols**:
  - `backend/app/api/routes_ingest.py:168-200` —— `ingest_run`:雙 gate → `_validate_strategy`
    → `_resolve_source` → `llm_client.is_configured()` → **每個請求開一條全新的 asyncpg 連線**
    → `ingest_document(dry_run=False, ...)` → `finally: await pg_conn.close()`。
    「每請求一條新連線」是本設計的前提之一(見 D1 的替代方案討論)。
  - `ingestion/extract/runner.py:202` —— `job_id = f"ingest:{uuid.uuid4()}"`,前綴目前寫死。
  - `ingestion/extract/runner.py:250-251` —— `ensure_schema(pg_conn)` 之後緊接
    `start_ingestion_job(pg_conn, job_id, str(source_path))`,**再往下才進入逐 chunk 的
    LLM 呼叫迴圈**(258 起)。這是唯一一個「已經開始、但還沒花錢」的插入點。
  - `ingestion/extract/runner.py:342-380` —— `except Exception: status='failed'; raise` +
    `finally: ... finish_ingestion_job(...)`。**所以正常與例外路徑都會把 job 收尾**;
    只有硬性中止(容器被 kill、OOM)才會留下孤兒的 `running` 列。
  - `ingestion/pipeline/load_postgres.py:81-106` —— `start_ingestion_job`(無條件 INSERT)
    與 `finish_ingestion_job`。`start_ingestion_job` 目前只有兩個呼叫點:
    `runner.py:251`(抽取)與 `run.py:37`(seed,source_path 是資料目錄、job_id 前綴 `job:`)。
  - `ingestion/pipeline/schema.sql:24-33` —— `ingestion_jobs` 的 DDL:
    `job_id TEXT UNIQUE`、`status TEXT`、`source_path TEXT`、`started_at`、`finished_at`。
    **目前沒有任何針對 `source_path` 或 `status` 的索引或約束。**
  - `ingestion/pipeline/load_postgres.py:22-25` —— `ensure_schema` 的 migration 模式:
    `SCHEMA_SQL` + 兩個 `ALTER TABLE ... IF NOT EXISTS` 常數,冪等、每次啟動都跑。新 migration 依此模式加。
  - `backend/app/api/errors.py:10-15` —— `APIError(status_code, code, message)`;
    `backend/app/main.py:31-36` 的 handler 統一輸出 `{"error":{"code","message"}}`。
  - `backend/app/curation/service.py` 已多處以 `409` 表達「狀態衝突」(如 :253、:502),語意一致。
  - `frontend/app.js:45-65` —— `apiError` 取 `body.error.message`,不需改動即可顯示 409 訊息。
- **Existing behavior and baseline tests**:
  - **基準:232 passed**(離線姿態,`main` @ `57d721e`)。**此數字取自
    `docs/handoff-2026-08-12.md` 第 48 行,本次規劃階段並未重跑**——`plan-change` 是唯讀流程,
    而 integration 測試會清 `curation_items`(見〈Risks〉R4)。實作階段的第一件事就是重跑取得真基準。
  - 已知 flake:`test_pipeline_run_is_idempotent`,在非乾淨的 Postgres volume 上會因
    chunk 數多於 sample 來源而失敗。**非迴歸**,CI 從乾淨 runner 起跑不會出現。
  - 目前 DB 實測(唯讀查詢):`ingestion_jobs` 有 `success` 90 列、`failed` 5 列、
    **`running` 0 列**;`curation_items` 有 `demo/proposed` 19 列、`human/proposed` 1 列、
    **無 `llm` 提案**。→ 本機建索引不會因既有重複列而失敗,且沒有真實抽取佇列會被測試洗掉。

## Acceptance Criteria

以下皆為可觀察行為,全部可在離線、零 token 花費下驗證:

- **AC1** 同來源併發被擋在花錢之前:來源 S 有一個進行中的抽取 job 時,第二次
  `ingest_document(S, dry_run=False)` 丟出 `IngestAlreadyRunning`,且注入的 `extract_fn`
  **呼叫次數為 0**,`ingestion_jobs` 不新增任何列。
- **AC2** HTTP 面:同情境下 `POST /admin/ingest/run` 回 `409`,body 為
  `{"error":{"code":"ingest_already_running","message":...}}`,且 message 含進行中的
  `job_id` 與開始時間,足以讓操作者去查 `ingestion_jobs`。
- **AC3** 不同來源不受影響:S 進行中時,對來源 T 的抽取照常開始。
- **AC4** 收尾即釋放:第一個 job 以 `success` **或** `failed` 收尾後,同來源可立即再次抽取。
- **AC5** 預覽不受影響:`POST /admin/ingest/preview` / `dry_run=True` 在任何情況下都不被擋,
  也不寫入任何 `ingestion_jobs` 列。
- **AC6** seed 路徑不變:`make seed` 成功,且連續兩次 `pipeline.run` 不會因新索引而報錯。
- **AC7** 孤兒自癒:`started_at` 早於 `STALE_AFTER` 的 `running` 列不擋新 job;
  它被標為 `failed` 並寫入可辨識的 `error_message`,新 job 正常開始。
- **AC8** 無迴歸:離線全套測試通過,數量 ≥ 基準 + 新增測試數(既有 flake 除外,需具名揭露)。

## Contract, Schema, Dependency, and Migration Impact

- **Contract(新增,非破壞性)**:`POST /admin/ingest/run` 新增一個錯誤碼
  `409 ingest_already_running`。成功回應形狀**不變**;既有錯誤碼不變。
  消費端(前端)已泛用處理 `error.message`,不需同步改版。→ 需更新 `docs/api_contract.md`。
- **Schema(DDL,需批准)**:`ingestion_jobs` 新增部分唯一索引
  `ingestion_jobs_one_running_extract_per_source`
  `ON ingestion_jobs (source_path) WHERE status = 'running' AND job_id LIKE 'ingest:%'`。
  不新增欄位、不改既有欄位型別。→ 需同步 `schema/graph_schema.md` §2.3 的說明(加一行約束描述)。
- **Migration 的一次性資料動作**:建索引前,把每個 source **除最新一列以外**的
  `running` 抽取列標為 `failed`(`error_message` 標明來源為本次 migration)。
  這一步是**不可逆的狀態改寫**,但作用域僅限「定義上就是孤兒」的列(同一 source 有兩列 running
  只可能來自上次的重複提交事故),且本機實測目前為 0 列 → 在此 DB 上是 no-op。
  沒有這一步,既有重複列會讓 `CREATE UNIQUE INDEX` 失敗,進而讓 `ensure_schema` 失敗、
  **backend 起不來**——這是本變更最需要防的自傷。
- **Dependency**:無新增。全部使用既有的 asyncpg / Postgres 功能。
- **相容性**:舊資料列全部保留;沒有前端或 API 消費端需要同步升版。

## Execution Policy

- **Plan revision**:1
- **Risk level**:**medium**
  (碰到會花錢的路徑、含 DDL migration;但改動小、加法為主,且失敗方向是「拒絕開始」而非「錯誤地開始」)
- **Automation mode**:**supervised-auto**(提案;需人類明確批准才生效)
- **Auto-approved task IDs**(`supervised-auto` 時):**T1、T2、T3、T4、T5**
- **Approved file/path scope**(只准動這些):
  - `ingestion/pipeline/load_postgres.py`
  - `ingestion/extract/runner.py`
  - `backend/app/api/routes_ingest.py`
  - `ingestion/tests/test_document_ingest.py`
  - `backend/tests/integration/test_ingest.py`
  - `docs/api_contract.md`、`schema/graph_schema.md`、`docs/notes.md`
  - `changes/ingest-concurrency-guard/`(本變更的產出物)
- **Human checkpoints**:
  1. T5 完整驗證結果回報後停止,等待人類決定是否進入獨立審查。
  2. **任何需要真實 token 花費的動作前必停**——本 plan 的驗證策略設計為完全不需要,
     若實作中發現非花不可,即為 stop condition。
- **Mandatory stop conditions**(遇到即停止回報,不得自行決定):
  - 需要新增 Task 或動到上列路徑以外的檔案。
  - 需要改動已批准的 Contract(成功回應形狀、既有錯誤碼)。
  - 建索引在任何環境失敗,或 `ensure_schema` 因本變更而失敗。
  - 必要測試無法執行,或基準測試數低於 232(扣除具名 flake)。
  - 發現本設計會擋到合法的單一抽取(誤擋),而非只擋重複提交。
  - 需要新增 production dependency。
- **Commit/push permission**: **No unless separately approved after review.**

## Tasks

### T1 — Postgres 層:原子宣告 + 孤兒釋放

- **Files/symbols**:`ingestion/pipeline/load_postgres.py`
  (新增 `EXTRACT_JOB_PREFIX`、`STALE_AFTER`、例外 `IngestAlreadyRunning`、
  函式 `claim_ingest_source`、migration 常數 `_MIGRATION_INGEST_LOCK`)
- **Implementation**:
  1. `EXTRACT_JOB_PREFIX = "ingest:"`,`STALE_AFTER = timedelta(hours=2)`(模組常數,不進 config——
     YAGNI;取值理由見 R2)。
  2. `_MIGRATION_INGEST_LOCK`:先 `UPDATE` 把每個 source 除最新一列外的 `running` 抽取列標為
     `failed`,再 `CREATE UNIQUE INDEX IF NOT EXISTS ... ON ingestion_jobs (source_path)
     WHERE status = 'running' AND job_id LIKE 'ingest:%'`。加進 `ensure_schema`,順序在最後。
  3. `claim_ingest_source(conn, job_id, source_path)`:
     - 先 `UPDATE` 釋放**同一 source** 中 `started_at < now() - STALE_AFTER` 的 running 抽取列
       (標 `failed`,`error_message` 寫明「逾時視為中斷」)。
     - 再 `INSERT ... VALUES ($1,'running',$2)`;捕捉 `asyncpg.UniqueViolationError`
       → 查出擋住的那一列 → `raise IngestAlreadyRunning(job_id=..., started_at=...)`。
     - 例外物件帶結構化欄位,讓上層自己組訊息(不在 DB 層寫使用者文案)。
  4. **`start_ingestion_job` 保留不動**,seed 路徑繼續用它。
- **Tests and container command**:
  新增到 `ingestion/tests/test_document_ingest.py`(可用既有 `pg_conn` fixture,並在測試內另開
  第二條連線以模擬併發;**兩條連線是必要的**,單一連線的測試證明不了任何事)。
  `docker compose build backend && docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_document_ingest.py -q`
- **Stop/handoff**:索引建立在既有 DB 上失敗即停止回報。

### T2 — runner:在花錢之前宣告

- **Files/symbols**:`ingestion/extract/runner.py::ingest_document`(:202 的 job_id 組法、:251)
- **Implementation**:
  1. job_id 改用 `load_postgres.EXTRACT_JOB_PREFIX`,消除「前綴同時寫在索引述詞與 runner 裡」的隱性耦合。
  2. `ensure_schema` 之後把 `start_ingestion_job` 換成 `claim_ingest_source`。
     位置維持在**逐 chunk 迴圈之前**,`IngestAlreadyRunning` 因此在任何 LLM 呼叫前就丟出。
  3. **不加 try/except**:讓例外原樣往上傳,由 route 決定 HTTP 表現;
     容器內直接呼叫 `ingest_document` 的驗證路徑(handoff 陷阱 6 建議的做法)因此同樣受保護。
  4. dry-run 分支在 :224 就 `return`,天然不受影響——不需要額外判斷。
- **Tests and container command**:AC1、AC3、AC4、AC5、AC7 的測試。
  `docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests -q`
- **Stop/handoff**:若發現 dry-run 路徑也會建立 job 列(與現況認知不符)即停止。

### T3 — HTTP:對映成 409

- **Files/symbols**:`backend/app/api/routes_ingest.py::ingest_run`
- **Implementation**:在 `try/finally` 中補一個 `except load_postgres.IngestAlreadyRunning as exc:`
  → `raise APIError(409, "ingest_already_running", <中文訊息,含 job_id 與 started_at,
  並明確叫操作者不要重試、去查 ingestion_jobs>)`。`finally` 的連線關閉維持不變。
- **Tests and container command**:AC2。加到 `backend/tests/integration/test_ingest.py`
  (該檔已有 `TestClient` + monkeypatch owner token 的既有模式可沿用)。
  `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_ingest.py -q`
- **Stop/handoff**:若為了測 409 而必須真的花 token(而非以既有列造出衝突狀態)即停止。

### T4 — 文件同步

- **Files/symbols**:`docs/api_contract.md`(`POST /admin/ingest/run` 一節)、
  `schema/graph_schema.md` §2.3、`docs/notes.md`(N8)
- **Implementation**:
  1. api_contract:新增 409 `ingest_already_running` 的觸發條件、訊息內容、
     以及**「504 不代表失敗」**這個操作者最需要知道的事實。
  2. graph_schema §2.3:記錄新的部分唯一索引與其述詞。
  3. notes N8:標明只做了 (c);(a) nginx 逾時與 (b) 非同步化仍未做,並保留原因。
- **Tests and container command**:無自動化測試(純文件)。
- **Stop/handoff**:若發現契約敘述與實作有出入,以實作為準並回報差異。

### T5 — 完整驗證

- **Files/symbols**:無程式碼改動。
- **Implementation**:依〈Verification Strategy〉逐條執行並如實記錄命令與輸出。
- **Tests and container command**:見下節。
- **Stop/handoff**:**執行完停止**,等待人類決定是否進入 `verify-change` / `review-change`。

## Verification Strategy

必須依序,且**全部在容器內**執行(host 只跑 lint,且用拋棄式容器):

1. **重建映像**(測試檔沒有掛 volume,不重建會跑到舊測試——handoff 陷阱 2):
   `docker compose build backend`
2. **重啟 backend**(ingestion 程式碼與 prompt 有 `lru_cache`——陷阱 1):
   `docker compose up -d backend`
3. **服務就緒**(未就緒會噴一堆假失敗——陷阱 4):
   `bash scripts/wait_for_services.sh localhost 8080 240` + `make health`
4. **離線全套測試**(陷阱 3 的標準姿態):
   `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
   → 與基準 232 比對,新增測試數具名列出;`test_pipeline_run_is_idempotent` 若失敗,
   需先確認是既有 flake(volume 非乾淨)而非本變更造成。
5. **黃金題**(CI 會跑):`make eval`
6. **seed 冪等**(AC6):`make seed` 連跑兩次,兩次都成功。
7. **lint(host,拋棄式容器,釘選版本——陷阱 9)**:
   `docker run --rm -v $PWD:/w -w /w python:3.12-slim sh -c "pip install -q -r backend/requirements-dev.txt && ruff check <paths> && ruff format --check <paths> && mypy backend/app ingestion scripts"`
   `ruff check` 過不代表 `ruff format --check` 過,兩者都要跑。
8. **不需要也不得執行真實抽取**。本變更的所有行為都能以注入的 `extract_fn` 與
   直接操作 `ingestion_jobs` 造出的狀態驗證。**本變更的 token 預算為 0。**

## Risks and Unknowns

- **R1(設計取捨,已決定)——為何用「部分唯一索引」而非 Postgres advisory lock。**
  advisory lock(`pg_try_advisory_lock`)的優點是連線一斷就自動釋放,不需要孤兒處理。
  但它是 **session 級且可重入**:同一條連線第二次取同一把鎖會成功。目前 route 每個請求開新連線
  所以碰巧安全,但這個安全性依賴一個沒有被任何測試守住的實作細節——有人改成連線池就靜默失效。
  唯一索引是**連線無關**的,誰來提交都擋得住,而且把狀態留在 `ingestion_jobs` 裡可被稽核,
  與本專案「可稽核治理」的主軸一致。代價是需要 R2 的孤兒處理。
- **R2(已知限制)——孤兒鎖與 `STALE_AFTER = 2h` 的取捨。**
  容器被 kill 會留下 `running` 孤兒列,在 2 小時內擋住該來源。取值方向刻意偏長:
  太短會讓「上一個還在跑」被誤判成孤兒而**重複扣款**(正是本變更要防的),太長只是讓操作者等
  或手動改一列 DB。實作需在 api_contract 記下手動解法的 SQL。
  `finally` 已覆蓋正常與例外收尾,所以孤兒只可能來自硬性中止。
- **R3(可接受的誤擋)——同一來源的合法二次抽取會被擋。**
  若操作者確實想在第一次跑完前重跑同一章節(例如改了 prompt),會吃到 409。
  這是**刻意的**:本變更的整個前提是「同來源同時跑兩次一定是錯的」。
- **R4(資料)——integration 測試會清 `curation_items`。**
  目前佇列有 19 列 `demo`(可用 `make demo-reset` / `make seed` 還原)與
  **1 列 `human` 手工提案(還原不了)**。實作前需向人類確認這一列可否犧牲,或先手動備份。
  **目前沒有 `llm` 提案**,所以不會洗掉真實抽取成果。
- **R5(migration)——`CREATE UNIQUE INDEX` 失敗會讓 backend 起不來。**
  由 T1 的一次性正規化 UPDATE 消除。本機實測 `running` 為 0 列 → no-op;
  CI 從乾淨 volume 起跑亦然。但**其他機器的 volume 未經檢查**,這是唯一的未知。
- **R6(未解決,不在範圍內)——504 本身還在。**
  操作者仍會看到逾時,只是重試不再扣款。真正的解法是 (b) 非同步化,留在 N8 未完成的部分。
- **R7(耦合)——索引述詞裡的 `'ingest:%'` 與 runner 的 job_id 前綴必須一致。**
  T2 讓兩邊共用 `EXTRACT_JOB_PREFIX` 常數以降低風險,但**索引述詞是 SQL 字面值,常數改了 SQL 不會跟著改**。
  需在 migration 常數旁留註解點名這件事。

## Rollback

- **程式碼**:`git revert` 本變更的 commit(或直接捨棄分支)。四個程式檔的改動皆為加法,無資料轉換。
- **索引**:revert 程式碼**不會**移除已建立的索引。需手動
  `DROP INDEX IF EXISTS ingestion_jobs_one_running_extract_per_source;`
  (留著也無害:它只約束 `running` 抽取列的唯一性,舊程式碼本來就不會製造重複。)
- **一次性正規化 UPDATE**:**不可逆**。作用域僅限重複的 `running` 孤兒列,且本機實測為 0 列。
  若在其他機器上非 0,實作時需在 TASK_LOG 記下被改寫的 job_id 清單以供追溯。
- **文件**:隨 revert 一併回退。

## Human Decisions and Approval

- **Decisions required**:
  1. **D1 — 機制**:採「部分唯一索引 + 逾時釋放」(見 R1/R2),而非 advisory lock。**需批准。**
  2. **D2 — `STALE_AFTER = 2 小時`**:偏長,寧可讓孤兒多擋一陣子,也不冒重複扣款的險。**需批准或改值。**
  3. **D3 — 風險等級 medium + `supervised-auto`(T1–T5)**:需**明確**批准自動化模式;
     若不批准則退回 `one-task-at-a-time`。
  4. **D4 — R4 的資料犧牲**:驗證會清掉 `curation_items` 裡那 1 列 `human` 手工提案。
     可以犧牲,還是要先備份?
- **Decisions resolved**(2026-08-13,由人類批准):
  - **D1** → 採「部分唯一索引 + 逾時釋放」。advisory lock 不採用。
  - **D2** → `STALE_AFTER = 2 小時`,維持提案值。
  - **D3** → 風險 medium、`supervised-auto`,自動核准 T1–T5 連續執行。
  - **D4** → `curation_items` 那 1 列 `human` 手工提案**可以犧牲**,不需事先備份。
- **Status**: Approved
- **Approved plan revision**: 1
- **Approved risk level and automation mode**: medium / `supervised-auto`(auto-approved tasks:T1、T2、T3、T4、T5)
- **Approved by/date**: jett / 2026-08-13
- **Approval evidence**: 使用者於 2026-08-13 對 D1–D4 逐項回覆批准(D1「索引」、D2「可以」、
  D3「自動化跑完」、D4「可以犧牲」)。**Material plan changes invalidate approval.**
