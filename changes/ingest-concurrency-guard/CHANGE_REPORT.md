# Change Report: ingest-concurrency-guard

對應 `docs/notes.md` 的 **N8**,依人類決策**只做方向 (c)**:後端同來源併發防護。

- **Plan revision**:1(Approved / jett / 2026-08-13,medium / `supervised-auto`)
- **分支**:`feat/ingest-concurrency-guard`,自 `main` @ `57d721e`
- **驗證**:`VERIFICATION_REPORT.md` —— **PASS**(第一輪停在 lint,批准後重跑通過)
- **審查**:**未進行**。本報告不構成完成宣稱的自我核可。

## 1. 解決了什麼

`POST /admin/ingest/run` 同步阻塞,四個 chunk 約 4 分鐘,超過 nginx 預設代理逾時。
nginx 回 504 但**後端仍在跑而且會跑完**;操作者把 504 讀成失敗而重試,於是兩次抽取同時進行,
同一章節重複燒掉約 15–25k tokens(2026-08-12 真實發生)。

現在同來源已有進行中的抽取 job 時,再次提交在**進入 LLM 迴圈之前**被拒,回
`409 ingest_already_running`,訊息含擋住它的 `job_id`、開始時間,並明講
「本次未執行、未花費任何 token」與「不要重試」。

## 2. 已完成(全部通過測試)

| 項目 | 檔案 | 驗收 |
|---|---|---|
| 部分唯一索引:每個來源最多一列 `running` 抽取 job | `ingestion/pipeline/load_postgres.py`(`_MIGRATION_INGEST_CONCURRENCY_GUARD`) | AC1/AC3/AC4 |
| `claim_ingest_source()`:先釋放逾時孤兒,再原子宣告;衝突時丟 `IngestAlreadyRunning`(帶 job_id / started_at) | 同上 | AC1/AC7 |
| runner 在花錢前宣告,例外原樣上傳 | `ingestion/extract/runner.py:202, 251` | AC1/AC5 |
| HTTP 對映 409 | `backend/app/api/routes_ingest.py::ingest_run` | AC2 |
| 契約與 schema 文件 | `docs/api_contract.md`、`schema/graph_schema.md` §2.3、`docs/notes.md` N8 | — |
| 9 個新測試(離線,注入 `extract_fn`,零 token) | `ingestion/tests/test_document_ingest.py`(8)、`backend/tests/integration/test_ingest.py`(1) | AC1–AC7 |

`git diff --stat`:8 檔、+479 / −3,**全部落在批准的路徑範圍內**。

## 3. 可觀察的行為改變

- **新增**:`POST /admin/ingest/run` 在同來源進行中時回 `409`,body 為
  `{"error":{"code":"ingest_already_running","message":…}}`。
- **不變**:成功回應形狀、既有錯誤碼、`options` / `preview`、前端、nginx、seed 管線、
  抽取/切分/staging/gate/lens/Neo4j/Qdrant 的任何語意。
- **前端未改動**:`frontend/app.js` 的 `apiError` 已泛用顯示 `error.message`。
  **但這是讀碼推論,沒有人眼看過真實渲染**(見 §6)。

## 4. 契約、schema、依賴、migration

- **契約(加法,非破壞性)**:新增一個錯誤碼。既有消費端不需同步升版。已記入 `docs/api_contract.md`。
- **Schema(DDL)**:新增索引 `ingestion_jobs_one_running_extract_per_source`。無欄位變更。
- **Migration 的一次性資料改寫**:建索引前把每個來源除最新一列外的 `running` 抽取列標為 `failed`。
  **不可逆**,但作用域僅限「定義上就是孤兒」的列。**本機執行前後實測皆為 0 列,是 no-op**;
  沒有任何既有資料被改寫。
- **依賴**:無新增。

## 5. 偏差(Plan Deviations)

**D-1 — Plan 宣稱「本變更 token 預算為 0」,實際花了兩輪 `make eval` 的真實 token。**
`make eval` 沒有離線化,讀到 `.env` 的金鑰以 `mode=openai` 執行 22 題 × 2。
Plan 同時把 `make eval` 列為必要驗證、又宣稱零花費,**這兩條互相矛盾,規劃時未察覺**。
第二次執行是為了查第一次的非零退出碼(真因是延遲 P95 超標),
**若先查 `evaluation_runs` 表就能避免**。實際花費**無法量測**(eval 路徑不記錄 token),
粗估 5 萬–10 萬 tokens 量級——這是估算,不是量測。

**D-2 — 第一輪完整驗證失敗(`ruff format --check`),已依 stop condition 停止並回報,
未自行修復。** jett 批准後才執行 `ruff format` 並重跑。
追認解除的是批准瑕疵,不改變「第一輪驗證確實沒過」這個事實。

**D-3 — 多加了一個 Plan 未列的測試** `test_a_job_just_short_of_stale_still_blocks`,
在 T1 的既有檔案與批准路徑內。理由:只驗「逾時會釋放」而不驗「未逾時不釋放」,
等於沒有守住 `STALE_AFTER` 偏長這個刻意取捨。

其餘無偏差:未動批准範圍外的檔案,未新增依賴,未執行任何真實抽取。

## 6. 已知限制(逐項含實際代價)

- **L1 — 沒有真正的競態驗證**。測試以「先造出一列 running,再提交第二次」模擬,
  而非兩個真的同時起跑的 job。原子性由 Postgres 的唯一索引保證,
  但**這條路徑沒有被真實競態打過**。代價:若索引述詞哪天寫錯,測試仍會綠。
- **L2 — 索引述詞的 `'ingest:%'` 與 `EXTRACT_JOB_PREFIX` 是兩份副本**。
  索引述詞是已存下的 SQL 字面值,改常數不會跟著改,**也沒有守衛擋這件事**。
  代價:改前綴會讓防護靜靜失效而測試仍綠。已在 `schema/graph_schema.md` 與程式碼註解點名。
- **L3 — 前端揭露沒有人眼看過**(與 N1 遺留的 T6 同一個缺口)。倉庫沒有前端測試設施,
  且 409 極罕見,那段 UI 不會自然出現。要目視確認得刻意造一列 `running`。
- **L4 — 孤兒 2 小時門檻沒有端到端驗證**,只有以 `started_at` 回推時間的單元測試。
  代價:真實的容器 kill → 2 小時後接手,這條路徑沒被實地走過。
- **L5 — 未在乾淨 volume 上驗證**。既有 flake 與 eval 延遲抖動都源於此。
- **L6 — 「其他機器已有重複 running 列」的情境未驗證**。正規化 UPDATE 在非 0 列時的行為
  只由 SQL 邏輯保證,**沒有測試覆蓋**。
- **L7 — 504 本身還在**。操作者仍會看到逾時,只是重試不再扣款。

## 7. 未完成 / 未驗證

- **N8 的 (a) 與 (b) 未做**:nginx 逾時未調整;非同步 job_id + 輪詢未實作。
  (b) 是真正的解法但屬契約變更且要改前端匯入頁,留待獨立變更。已記入 `docs/notes.md`。
- **`make eval` 在本輪(格式化後)未重跑**,沿用前一次 `passed=True`。理由見驗證報告 §3.1。
- **獨立審查未進行**,人類驗收未取得。

## 8. Rollback

- **程式碼**:`git revert` 本 commit,或捨棄分支。四個程式檔皆為加法,無資料轉換。
- **索引**:revert **不會**移除它,需手動
  `DROP INDEX IF EXISTS ingestion_jobs_one_running_extract_per_source;`
  (留著也無害:它只約束 `running` 抽取列,舊程式碼本來就不會製造重複。)
- **一次性正規化 UPDATE**:不可逆,但本機影響 0 列,無可追溯的損失。
- **資料**:驗證過程清掉了 `curation_items` 中 1 列 `human` 手工提案
  (jett 於 2026-08-13 明確批准犧牲)。demo 群組已由 `make seed` 還原。
