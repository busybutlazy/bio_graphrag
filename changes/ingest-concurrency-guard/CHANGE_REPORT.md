# Change Report: ingest-concurrency-guard

對應 `docs/notes.md` 的 **N8**,依人類決策**只做方向 (c)**:後端同來源併發防護。

- **Plan revision**:1(Approved / jett / 2026-08-13,medium / `supervised-auto`)
- **分支**:`feat/ingest-concurrency-guard`,自 `main` @ `57d721e`
- **驗證**:`VERIFICATION_REPORT.md` —— **PASS**(第一輪停在 lint,批准後重跑通過)
- **審查**:`REVIEW_REPORT.md`(2026-08-13,獨立 session)—— **Blocking / High 皆無**。
  M-1(Medium)與 S-1(Suggestion)已依 jett 的處置決定修掉(見 §9),
  其餘記入 `docs/notes.md` N9。本報告不構成完成宣稱的自我核可。

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
| 10 個新測試(離線,注入 `extract_fn`,零 token) | `ingestion/tests/test_document_ingest.py`(9,含 S-1 前綴守衛)、`backend/tests/integration/test_ingest.py`(1) | AC1–AC7 |

程式與文件共 **8 個檔案**,如上表所列,**全部落在 Plan 批准的路徑範圍內**。

> **這裡刻意不寫累計行數。** 原本寫的是 `git diff main..HEAD --stat` 的輸出,
> 但 `main..HEAD` 是**會移動的目標**:把它的輸出寫進文件,下一個 commit 就讓
> 「命令」與「輸出」對不上——修 N-1 的那個 commit 自己又製造了一次 N-1
> (527 → 538),第三輪審查抓到了。再改一次數字只會再重演一次。
> 本報告的價值在「改了什麼、為什麼」,不在一個注定過期的數字;
> 要查行數請自己跑 `git diff main..<commit> --stat -- . ':(exclude)changes/'`,
> 端點自己指定。

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

- **~~L1 — 沒有真正的競態驗證~~ → 審查已推翻。** 審查者以 6 條各自獨立的連線
  `asyncio.gather` 打真實競態:1 個贏家、5 個乾淨的 `IngestAlreadyRunning`、表中只有一列,
  五個被拒者皆正確回報同一個擋住它們的 job_id。**原子性不再只是推論。**
- **~~L2 — 前綴耦合無守衛~~ → 已修(S-1)。**
  `test_the_index_predicate_and_the_job_prefix_stay_in_sync` 同時釘住常數值,
  與「migration SQL 必須含由該常數推出的字面值」。改一邊會立刻紅。
- **L3 — 前端揭露沒有人眼看過**(與 N1 遺留的 T6 同一個缺口)。倉庫沒有前端測試設施,
  且 409 極罕見,那段 UI 不會自然出現。要目視確認得刻意造一列 `running`。
- **L4 — 孤兒 2 小時門檻沒有端到端驗證**,只有以 `started_at` 回推時間的單元測試。
  代價:真實的容器 kill → 2 小時後接手,這條路徑沒被實地走過。
- **L5 — 未在乾淨 volume 上驗證**。既有 flake 與 eval 延遲抖動都源於此。
- **~~L6 — 「其他機器已有重複 running 列」未驗證~~ → 審查已推翻。**
  審查者在 `BEGIN … ROLLBACK` 內以 temp table 造出同一 source 三列 running、
  另一 source 一列、外加兩列 `job:` seed 列,跑正規化 UPDATE:`UPDATE 2`,
  保留最新、關掉兩列舊的、**seed 列未被動到**。
  **Plan R5 點名的「後端起不來」自傷風險不成立。**
- **L7 — 504 本身還在**。操作者仍會看到逾時,只是重試不再扣款。
- **L8(審查新增,已記入 notes N9)— 防護鍵是 `source_path`,破壞性寫入鍵是 `doc_id`。**
  兩個不同來源檔可以有相同 `doc_id`,此時防護放行、兩次抽取各自
  `delete_chunks_for_doc(doc_id)`,後到的 delete 可能清掉先到者剛寫好的 chunks。
  是資料一致性缺口,非重複扣款;觸發條件窄,且 Plan 已把跨來源互斥列為 Out of Scope。

## 6.1 審查後的處置(2026-08-13,jett 決定「修 M-1 + S-1,其餘記 notes」)

- **M-1(Medium)已修** —— 409 訊息在孤兒鎖情境給出反向指示。
  **審查者是對的,而且指出了我一個實質錯誤**:我把孤兒成因寫成
  「Only a hard kill (container OOM/SIGKILL)」,但最容易製造孤兒的是
  **`make up`**(`docker compose up -d --build`,本專案標準指令)——
  未設 `stop_grace_period`,docker 預設 10 秒,一次 4 分鐘的抽取必定被 SIGKILL。
  該情境下後端**確實**失敗了,訊息卻無條件斷言它沒有,且未給脫困路徑。
  已改為條件式訊息(兩種情境分別指示 + 分辨方法 + 指向手動關閉),
  並同步修正 `load_postgres` 註解與 `docs/api_contract.md`。**未動防護邏輯。**
- **S-1 已修** —— 見 §6 的 L2。
- **L-1 / L-2 / L-3 / S-2 / S-3 記入 `docs/notes.md` N9**,外加一項我自己發現、
  審查者未提的既有觀察:`runner.py` 的 `except Exception` 抓不到 `CancelledError`,
  優雅取消時 job 會被記成 `success`——先於本變更,方向安全(錯誤地釋放鎖而非洩漏鎖),
  但稽核紀錄會說謊。

## 6.2 追加審查的處置(第二輪,N-1 ~ N-4,jett 決定四項全修)

第二輪審查確認 M-1 / S-1 修法正確、無迴歸、防護邏輯逐行未動,並提出四項 Low/Suggestion。
**四項我獨立驗證後全部成立,已全修**(細節見 `TASK_LOG.md` R2):

- **N-1** 產出物數字未隨修復更新(報告寫 +479 / −3、9 個測試,當時實際為 +527 / −3、10 個)。
  第一次處置是更正數字並註明對應 commit——**這個修法本身又製造了一次 N-1**:
  下一個 commit 讓 527 變成 538,第三輪審查抓到了。
  **最終處置是刪掉那個累計行數**(見 §2 的說明),因為 `main..HEAD` 是會移動的目標,
  改數字只會重演。
- **N-2** M-1 修好的那半段訊息**沒有任何測試守住**,刪掉它測試仍綠、缺陷會靜靜復發。已補三項斷言。**四項中最重要的一項。**
- **N-3** 我對 `CancelledError` 的結論**寫錯了一半**:`finally` 裡的 `await` 若也被取消打斷,鎖會被**洩漏** 2 小時,方向與我寫的「安全」相反。已改寫 N9 該條。
- **N-4** 訊息裡的 `**` 會以字面星號顯示給操作者(`frontend/app.js` 的 `E()` 以文字節點附加)。已移除並加斷言擋回歸。

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
