# Task Log: ingest-concurrency-guard

- **Plan revision**: 1
- **Approval evidence**: `IMPLEMENTATION_PLAN.md`〈Human Decisions and Approval〉—— jett / 2026-08-13,
  對 D1–D4 逐項批准(D1 索引、D2 `STALE_AFTER=2h`、D3 supervised-auto、D4 犧牲 1 列 human 提案)。
- **Risk level**: medium
- **Automation mode**: supervised-auto
- **Auto-approved tasks**: T1、T2、T3、T4、T5
- **Approved path scope**:
  `ingestion/pipeline/load_postgres.py`、`ingestion/extract/runner.py`、
  `backend/app/api/routes_ingest.py`、`ingestion/tests/test_document_ingest.py`、
  `backend/tests/integration/test_ingest.py`、
  `docs/api_contract.md`、`schema/graph_schema.md`、`docs/notes.md`、
  `changes/ingest-concurrency-guard/`
- **Baseline Git state**:
  - 起點 `main` @ `57d721e`,工作區僅兩個未追蹤項:`docs/handoff-2026-08-12.md`(前任交接文件,
    不屬本變更)與 `changes/ingest-concurrency-guard/`(本變更產出物)。兩者皆已辨識,無不明修改。
  - 執行分支:`feat/ingest-concurrency-guard`(自 `57d721e` 建立;**未 commit、未 push**)。
- **Baseline tests**(實測,非引用交接文件):
  ```
  docker compose build backend                                                  # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  → 1 failed, 232 passed in 93.41s                                              # exit 1
  ```
  唯一失敗:`ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
  (`assert 12 == 9`)。與 `docs/handoff-2026-08-12.md` 陷阱 5 記載的已知 flake 完全一致
  (volume 非乾淨,DB 內 chunks 多於 sample 來源),**非本變更造成**。
- **Migration 前置實測**(Plan R5 要求):
  ```sql
  SELECT count(*) FROM ingestion_jobs WHERE status='running' AND job_id LIKE 'ingest:%';  → 0
  ```
  → 一次性正規化 UPDATE 在本 DB 上影響 **0 列**,為 no-op。若非 0 即為 stop condition。

---

## T1 — Postgres 層:原子宣告 + 孤兒釋放

- **Boundary and allowed paths**:`ingestion/pipeline/load_postgres.py`、`ingestion/tests/test_document_ingest.py`
- **Files changed**:
  - `ingestion/pipeline/load_postgres.py` —— 新增 `EXTRACT_JOB_PREFIX`、`STALE_AFTER`、
    `IngestAlreadyRunning`、`_MIGRATION_INGEST_CONCURRENCY_GUARD`(正規化 UPDATE + 部分唯一索引)、
    `claim_ingest_source`;`ensure_schema` 追加執行該 migration。`start_ingestion_job` **未動**。
  - `ingestion/tests/test_document_ingest.py` —— 新增 6 個 T1 測試 + 第二連線 helper。
- **Tests added**:`test_claim_refuses_a_second_extraction_of_the_same_source`、
  `test_claim_allows_a_different_source`、`test_claim_reuses_the_source_once_the_job_is_finished`、
  `test_claim_takes_over_a_stale_orphan`、`test_a_job_just_short_of_stale_still_blocks`、
  `test_the_seed_pipeline_is_not_covered_by_the_guard`
- **Container commands and exit codes**:
  ```
  docker compose build backend                                                     # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_document_ingest.py -q
  → 18 passed in 7.36s                                                             # exit 0
  ```
- **Acceptance criteria demonstrated**:AC1(DB 層)、AC3、AC4、AC6(單元層)、AC7。
  另加一個 plan 未列但同一邊界內的測試 `test_a_job_just_short_of_stale_still_blocks`——
  只驗「逾時會釋放」而不驗「未逾時不釋放」,等於沒有守住 `STALE_AFTER` 偏長這個刻意取捨。
- **Tests not run and why**:無。
- **Deviations**:None(新增測試在既有檔案、既有路徑內,未擴大範圍)。
- **Result**: **Pass**

## T2 — runner:在花錢之前宣告

- **Boundary and allowed paths**:`ingestion/extract/runner.py`、`ingestion/tests/test_document_ingest.py`
- **Files changed**:
  - `ingestion/extract/runner.py` —— job_id 改用 `load_postgres.EXTRACT_JOB_PREFIX`(:202);
    `start_ingestion_job` → `claim_ingest_source`(:251),位置在 `try/finally` 之前,
    所以被拒絕時不會留下需要收尾的 job 列。未加 try/except,例外原樣上傳。
  - `ingestion/tests/test_document_ingest.py` —— 新增 2 個 runner 層測試。
- **Tests added**:`test_a_second_ingest_of_the_same_source_spends_nothing`(斷言 `extract_fn`
  呼叫次數為 0)、`test_preview_is_never_blocked`
- **Container commands and exit codes**:同 T1 的那次執行(18 passed,exit 0)。
- **Acceptance criteria demonstrated**:AC1(端到端,含零呼叫模型)、AC5。
- **Tests not run and why**:無。
- **Deviations**:None
- **Result**: **Pass**

## T3 — HTTP:對映成 409

- **Boundary and allowed paths**:`backend/app/api/routes_ingest.py`、`backend/tests/integration/test_ingest.py`
- **Files changed**:
  - `backend/app/api/routes_ingest.py` —— import `load_postgres`;`ingest_run` 補
    `except IngestAlreadyRunning` → `APIError(409, "ingest_already_running", ...)`,
    訊息含 job_id、開始時間、「未花費任何 token」與「不要重試」。`finally` 的連線關閉未動。
  - `backend/tests/integration/test_ingest.py` —— 新增 1 個測試 + `_job_row` helper。
- **Tests added**:`test_run_refuses_a_second_ingest_of_the_same_source`
  (monkeypatch `llm_client.is_configured` 為 True,確保 409 來自守衛而非 `llm_not_configured`——
  否則這個測試會因為錯誤的理由通過)
- **Container commands and exit codes**:
  ```
  docker compose build backend                                                     # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_ingest.py -q
  → 12 passed in 6.56s                                                             # exit 0
  ```
- **Acceptance criteria demonstrated**:AC2。
- **Tests not run and why**:無。
- **Deviations**:None
- **Result**: **Pass**

## T4 — 文件同步

- **Boundary and allowed paths**:`docs/api_contract.md`、`schema/graph_schema.md`、`docs/notes.md`
- **Files changed**:
  - `docs/api_contract.md` —— 新增〈`POST /admin/ingest/run` —— 同來源併發防護(409)〉一節:
    409 錯誤碼、「504 不代表失敗」、四點語意、孤兒鎖的手動解除 SQL、seed 不在範圍內。
  - `schema/graph_schema.md` §2.3 —— 記錄部分唯一索引的 DDL、選它而非 advisory lock 的理由、
    以及「索引述詞是存下的 SQL 字面值,改 `EXTRACT_JOB_PREFIX` 不會跟著改」這個耦合。
  - `docs/notes.md` N8 —— 標明只做了 (c),(a)/(b) 仍未做及其理由。
- **Tests added/modified**:無(純文件)。
- **Container commands and exit codes**:不適用。
- **Acceptance criteria demonstrated**:契約揭露(Plan〈Contract...Impact〉)。
- **Deviations**:None
- **Result**: **Pass**

## T5 — 完整驗證

- **Boundary and allowed paths**:無程式碼改動(evidence-only)。
- **Container commands and exit codes**:見 `VERIFICATION_REPORT.md`。
- **Result**: **Fail —— 停止**

  驗證第 7 步 `ruff format --check` 失敗:`ingestion/tests/test_document_ingest.py`
  有 3 處 `assert await ...fetchval(...) == 1` 需要 ruff 的斷行括號化。**純格式,無行為改變**,
  但 CI 會擋(handoff 陷阱 9 明載 `ruff check` 過不代表 `ruff format --check` 過)。

  依 Plan 的 mandatory stop condition「完整驗證失敗」與 `run-approved-change` 的
  「不得由驗證階段切回實作」,**在此停止,未執行 `ruff format`**,等待人類裁示。

  同時揭露一項對自己不利的偏差,見 `VERIFICATION_REPORT.md` §5:
  **`make eval` 實際跑在 openai 模式,花了真實 token**,與 Plan 宣稱的「本變更 token 預算為 0」牴觸。

---

## R1 — 審查發現處置(review-finding repair,非 Plan 的 Task)

- **觸發**:`REVIEW_REPORT.md`(2026-08-13,獨立 session)。Blocking / High **皆無**。
- **人類處置決定**:jett,2026-08-13 —— 「修 M-1 + S-1,其餘記 notes」。
- **Boundary and allowed paths**:`backend/app/api/routes_ingest.py`、
  `ingestion/pipeline/load_postgres.py`、`ingestion/tests/test_document_ingest.py`、
  `docs/api_contract.md`、`docs/notes.md`(全部在 Plan 原本批准的路徑清單內)。

### 處置內容

- **M-1(Medium,已修)** —— 409 訊息在孤兒鎖情境給出反向指示。
  審查者的前提我獨立驗證過:`make up` = `docker compose up -d --build`,
  `docker-compose.yml` 未設 `stop_grace_period` → docker 預設 10 秒,
  一次 4 分鐘的抽取必定被 SIGKILL。**孤兒的最可能成因是 `make up`,不是 OOM**;
  我原本的註解「Only a hard kill (container OOM/SIGKILL)」字面沒錯但誤導性地窄,
  而訊息無條件斷言「不代表後端失敗」在該情境下是**假的**,且未給脫困路徑。
  改動:409 訊息改為條件式(兩種情境分別指示 + 分辨方法 + 指向手動關閉);
  `load_postgres.STALE_AFTER` 註解改寫成因;`docs/api_contract.md` 的孤兒段同步修正。
  **純文案與註解,未動任何防護邏輯。**
- **S-1(Suggestion,已修)** —— 前綴耦合無守衛。
  新增 `test_the_index_predicate_and_the_job_prefix_stay_in_sync`,
  同時釘住常數值與「migration SQL 必須含由該常數推出的字面值」,
  所以改常數而不改 migration 會立刻紅。
- **記入 `docs/notes.md` N9 作為後續項目**:L-1(防護鍵 `source_path` vs 寫入鍵 `doc_id`)、
  L-2(claim 查詢窗口導致訊息退化)、L-3(HTTP 測試在真實 demo 路徑留 running 列)、
  S-2(測試連線參數複製)、S-3(全表 UPDATE 成長後再收斂),
  外加一項**我自己發現、審查者未提**的既有觀察:`except Exception` 抓不到 `CancelledError`,
  優雅取消時 job 會被記成 `success`(先於本變更,方向安全但稽核紀錄會說謊)。

### 驗證

```
docker compose build backend                                                     # exit 0
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
→ 1 failed, 242 passed in 87.93s        # 241 + S-1 守衛;失敗仍是同一個已知 flake
ruff check / ruff format --check / mypy(拋棄式容器)
→ All checks passed! / 107 files already formatted / no issues found in 83 source files   # exit 0
```

`make eval` **未重跑**:本輪只改文案、註解與一個純斷言測試,不可能影響檢索或作答,
而重跑要再花一次真實 token。

- **Deviations**:None。未動防護邏輯,未擴大路徑範圍。
- **Result**: **Pass**
