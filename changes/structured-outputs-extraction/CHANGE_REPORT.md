# Change Report: structured-outputs-extraction

對應 `docs/notes.md` 的 **N1**。比較基準:`main` (`c292a68`) → 分支頭(見 git log)。批准依據:`IMPLEMENTATION_PLAN.md`
**revision 3**,狀態 Approved,風險「高」/`one-task-at-a-time`。

> 本報告初版寫於 `a286806`(程式碼三個 commit)。其後追加:CI 補記、以及**審查 H1 後由 owner
> 追加的 Task 6 前端揭露**(計畫由 revision 2 升為 3,`frontend/` 由 Out of Scope 改為納入)。
> 各節已就地更新,標頭不再釘死於單一 commit。

## Outcome

抽取路徑改為兩層防線:模型輸出先受 OpenAI Structured Outputs(`json_schema` + `strict`)約束;
若驗證仍失敗,重試用盡後逐元素挑掉不合格者並揭露,而非丟棄整個 chunk。

計畫的六個 Task 全部完成(T6 為審查後追加),八項驗收條件全部通過。
其中驗收條件 2「丟棄一律揭露」原本只在 API 層成立,經 T6 後在人類介面亦成立(見 §9)。
真實抽取由 `failed_chunks 2/4` 降為 **0/4**,且無任何元素需要被挽救。

**本報告不證明正確性**,只陳述做了什麼、沒做什麼、沒證明什麼。

## Completed

| Task | 交付 | 證據 |
|---|---|---|
| T1 探測 | 四個 schema 變體對 `gpt-4o-mini` 實測,定出 V3 形狀 | `TASK_LOG.md` Task 1 |
| T2 strict schema | `build_strict_schema()` 執行期推導;`llm_client` 改用 json_schema、處理 refusal | commit `51a2056` |
| T3 逐元素挽救 | `salvage.py`;`_extract_chunk` 改回傳 `ExtractionAttempt`;揭露欄位 | commit `521197c` |
| T4 契約文件 | `docs/api_contract.md` 新增 `POST /admin/ingest/run` 一節 | commit `a286806` |
| T5 完整驗證 | 真實抽取 + 完整測試 + lint/mypy;過程中修正一個自身缺陷 | `VERIFICATION_REPORT.md` |
| T6 前端揭露 | 審查 H1 後 owner 追加:統計磚、部分接受說明、逐塊丟棄清單 | `TASK_LOG.md` Task 6、`VERIFICATION_REPORT.md` §9 |

四項已裁決事項皆按批准內容落實:D1a 連帶丟棄、D1b 只揭露不擋、D2 執行期推導(`schema/` 未被修改)、
D4 高風險逐 Task 停止。

## Not Completed

無計畫內項目未完成。

## Not Verified

- ~~**`make eval`(22 題黃金題)未執行**~~ —— **已由 CI 執行並通過**(22/22),見下方 CI 補記。
- **`refusal` 分支未在真實 API 上觸發**。僅以假物件單元測試涵蓋。
- **非 `gpt-4o-mini`、非 `markdown_header` 策略下的行為未評估**。
- **僅單一章節、單次成功抽取**。「strict 模式使挽救不再需要」只有一次觀察支持,不足以推論常態。
- **中間 commit 未逐一執行測試**。`51a2056` 與 `521197c` 各自自洽是靠閱讀相依關係推得
  (commit 1 未動 runner,舊 3-tuple 呼叫端與舊測試一致),**未實際 checkout 驗證**。
- ~~**乾淨環境未複驗**~~ —— **已由 CI 複驗**。本機那個 `test_pipeline_run_is_idempotent` 失敗
  在全新 runner 上未出現,證實只是本機 volume 被真實抽取寫入所致,非迴歸。見下方 CI 補記。

## File Changes

- **Added**:
  - `ingestion/extract/strict_schema.py` —— strict schema 推導與 null 還原
  - `ingestion/extract/salvage.py` —— 逐元素挽救政策
  - `ingestion/tests/test_strict_schema.py`(11 項)
  - `ingestion/tests/test_salvage.py`(8 項)
  - `backend/tests/unit/test_property_key_coverage.py`(1 項)—— **路徑偏離,見下**
  - `changes/structured-outputs-extraction/{IMPLEMENTATION_PLAN,TASK_LOG,VERIFICATION_REPORT,CHANGE_REPORT}.md`
- **Modified**:
  - `ingestion/extract/llm_client.py` —— `response_format()`、`content_of()`、`LLMRefused`
  - `ingestion/extract/runner.py` —— `ExtractionAttempt`、挽救接線、`ChunkReport` 與 `stats` 揭露欄位
  - `ingestion/pipeline/validate_extraction.py` —— `validate_node` / `validate_edge`
  - `ingestion/tests/test_document_ingest.py` —— 配合新回傳型別;新增 1 項冪等實測
  - `docs/api_contract.md` —— 新增一節
  - `frontend/app.js` —— `renderRunResult` 揭露丟棄與降級(T6)
  - `frontend/index.html` —— 資產版本號 `20260812-2`(CDN 快取)
  - `docs/notes.md` —— 由 untracked 改為納入版控(需求來源 N1),並新增 N8(見〈Plan Deviations〉第 4 點)
- **Deleted**:`changes/extraction-prompt-inline-pattern-rules/PR_DRAFT.md`、
  `changes/structured-outputs-extraction/PR_DRAFT.md`(owner 裁定不再維護 PR 草稿;
  兩者皆先提交後刪除,內容存於 git 歷史)
- 程式碼與文件合計 15 檔。`schema/extraction_output_schema.json` **未被修改**(D2 的重點)。

## Observable Behavior

1. **抽取請求**改送 `response_format: json_schema (strict)`。送出的 schema 由內部 schema 推導,
   剝除 `pattern`(有成本實測)**與所有 `description` 註解(無實測,審查 M2)**、
   列舉 `properties` 鍵、選用欄位可為 null。
2. **一個 chunk 從全有全無改為部分接受**。壞元素被丟棄,其餘進入審閱佇列。
3. **丟棄一律揭露**:`stats.dropped[]`(含 `chunk_id/kind/id/reason`)、`dropped_nodes`、
   `dropped_edges`、`degraded_chunks`;`chunks[]` 另有 `dropped` 與 `degraded`。
4. **全部元素不合格時行為不變**:該 chunk 仍計入 `failed_chunks`。
5. **模型拒答改為拋出**,不再被讀成空抽取。
6. **兩道 gate 的判斷邏輯完全未改**。存活元素照常受檢;實測 7 組中 3 組被判 `fail_pattern`。
7. **匯入頁顯示丟棄**:「丟棄(節點/關係)」磚(即使為 0 也顯示)、丟棄時的說明段落、
   逐塊標頭的「丟棄 N / 降級」與卡片內的逐筆 `kind / id / reason`。
   目的是讓被挽救的塊與乾淨的塊在視覺上不可能混淆。

## Contract, Schema, Migration, Dependency, and Configuration Impact

- **Contract(additive)**:`POST /admin/ingest/run` 回應新增四個 `stats` 欄位與 `chunks[]` 的兩個欄位。
  既有欄位未改名、未改語意。已記入 `docs/api_contract.md`。
- **Schema**:無變更。內部 `extraction_output_schema.json` 逐字不動,
  `engineer_gate` 對人工提案的驗證行為因此不受影響(有測試釘住:`test_building_does_not_mutate_the_internal_schema`)。
- **Migration**:無。未動資料庫結構,未刪改既有列。
- **Dependency**:無新增。`openai` 1.109.1(既有 `>=1.40,<2`)已支援。
- **Configuration**:無。未改 `.env`、compose、nginx。

## Plan Deviations and Unplanned Changes

1. **路徑偏離(2026-08-12 owner 已追認,計畫 revision 3 納入該路徑)**:
   新增 `backend/tests/unit/test_property_key_coverage.py`,
   **不在計畫批准的路徑範圍內**(批准範圍為 `ingestion/extract/`、`ingestion/pipeline/validate_extraction.py`、
   `ingestion/tests/`、`schema/`、`docs/api_contract.md`、`changes/structured-outputs-extraction/`)。
   原因:該守衛需讀取 backend 的 gate/lens,而 **ingestion 不得依賴 backend**(相依單向,
   既有的 anchor 守衛同理放在 backend 側)。原本寫在 `ingestion/tests` 並在容器內失敗後才發現。
   依 Execution Policy,新增路徑本應停止並回報;**當時未停止,直接移動了檔案**。
   追認只解除了它的批准瑕疵,**不改變當時未依 stop condition 停止這個事實**——保留此段。
2. **計畫外的缺陷修正**:`strict_schema.drop_strict_nulls()` 及其四項測試不在原計畫任務中,
   是 T5 真實抽取暴露本變更自身缺陷後補上的(見 `VERIFICATION_REPORT.md` §2)。
3. **T5 執行方式偏離**:計畫寫的是經 `POST /admin/ingest/run` 驗證。首次如此執行時 nginx 回 504
   (代理逾時),我誤判為失敗而重試,**造成一次重複抽取**(已中止並在 `ingestion_jobs` 標記)。
   後續改為在容器內直接呼叫 `ingest_document`(同一程式路徑,不經 nginx)。
   **因此 HTTP 端點路徑只被驗證到「會逾時但後端完成」,新欄位的 JSON 序列化未經端點實際檢視。**
4. **花費超出估計**:計畫估 T1 < 1 美分、T5 約 0.2 美分;實際累計約 90k tokens
   (T1 17.9k、失敗執行 34k、中止執行約 15–25k、成功執行 18.8k)。

   **處置(owner 2026-08-12 裁定一併處理)**:已中止該次執行、job 標記 `failed` 並在
   `error_message` 記明原因;根因記入 `docs/notes.md` 的 **N8**。根因不是一次判讀失誤,
   而是介面形態——一個會花錢、耗時數分鐘的操作,用「同步等待、逾時就沒有回應」的方式暴露,
   任何人(或 agent)在 504 之後都會傾向重試。N8 列了三個方向,並指出**後端併發防護**最有效,
   因為它不依賴操作者判讀正確。本變更不做此修補(基礎設施/契約變更,不在範圍)。

## Breaking Changes and Compatibility

- **內部介面破壞性變更**:`runner._extract_chunk` 由回傳 3-tuple 改為 `ExtractionAttempt`。
  呼叫端僅 `runner.ingest_document` 與兩個測試檔(已全數更新,`grep` 確認無其他呼叫端)。
  該函式為模組私有(前綴底線),不屬對外契約。
- **對外相容**:回應僅新增欄位,既有欄位不變。
- **離線姿態不變**:未設 `OPENAI_API_KEY` 時完全不觸及本變更的 API 路徑;全部測試在離線姿態通過。
- **行為相容性的一點提醒**:先前會整塊失敗的 chunk,現在可能部分成功。
  依賴 `failed_chunks` 判斷「這章有沒有問題」的既有流程或人工習慣,需改看 `dropped_*` 與 `degraded_chunks`。

## Remaining Work and Known Limitations

- ~~**尚未推送,無 CI 證據**~~ —— 已推送並開 PR #20,CI 兩個 job 皆綠(見下方補記)。
  一併修正本報告先前的一句誤述:推功能分支**不會**觸發 CI(`ci.yml` 的 `on:` 為
  `push: branches: [main]` 加 `pull_request`),要開 PR 才會跑。
- **`/admin/ingest/*` 的請求契約仍未進 `docs/api_contract.md`**。既有缺口,已在新增章節中標記,
  未順手補寫(不在範圍)。
- **`GET /nodes/{id}` 404 回 `{"detail":...}` 而非專案錯誤契約**。既有問題,與本變更無關,未處理。
- **兩份 `PR_DRAFT.md` 已刪除**(owner 2026-08-12 裁定:PR 草稿不再維護)。
  過程值得記錄,因為結論翻過兩次:原本要刪(理由是 PR 內文已在 GitHub);核對後發現
  **PR #19 的內文只有 1922 字元、本機草稿有 5009**——owner 當時自己撰寫 PR 內文,
  草稿內容不在任何地方,故改為納管;owner 隨後裁定不再維護草稿,兩份皆刪。
  **刪除此時已無損失**:兩份都先被 commit(`8b94c3b`)才刪除,內容留在 git 歷史中可還原;
  且本變更的草稿在刪除前已以 `gh pr edit` 同步進 PR #20 的內文。
  作法上的結論:**PR 內文以 GitHub 為準,repo 內不留副本**,避免兩處分歧。
- ~~**`docs/notes.md` 未納入版控**~~ —— **已納入**(owner 2026-08-12 裁定)。
  它是本變更的需求來源(N1),先前既未修、也未列入本節,是本報告的**揭露缺口**:
  獨立審查 grep 全部產出物後指出「只有 REVIEW_REPORT 提到它」。離開這台機器就無法重建原始請求,
  對一個以稽核為主軸的專案而言是實質風險,不只是整潔問題。
- **`DEGRADED_DROP_RATIO = 0.5` 未經實證校準**,是一個未被真實資料檢驗過的門檻
  (成功執行的丟棄數為 0,從未觸發)。
- **T6 的 UI 沒有自動化測試,也未經人眼確認**。倉庫無前端測試設施;且 strict 模式生效後
  丟棄極罕見,這段畫面在正常操作下不會自然出現。目前證據只有欄位對照與語法檢查。
### 審查發現的處置(owner 裁定:M2 現在修,其餘記入已知限制)

- **M2 已處理**(準確性,非行為):送出的 schema 另外剝除了所有 `description`,而程式碼註解
  宣稱理由是成本、T1 卻從未測過它。已更正 `strict_schema.py` 的模組 docstring(改列**三項**
  偏離,並註明第三項無實測支持)、`TASK_LOG.md` Task 1/2、本報告、`docs/api_contract.md`。
  **行為未改**——`description` 仍被剝除;是否恢復需一次付費抽取判斷,列為後續。
- **M1 跨 chunk 懸空邊**(未修):連帶丟棄的作用域是單一 chunk。同一次執行中,chunk 1 丟棄的
  節點若在 chunk 3 被邊引用,該邊會存活。影響有界——`approve_group` 會在核准時擋下,
  結果是該組無法核准、浪費專家時間,不是圖譜被污染。跨 chunk 路徑無測試。
- **M3 屬性守衛的比對方式脆弱**(未修):以正則掃描原始碼,`.get("x", default)` 與下標存取
  (`props[lid]["feedback_type"]`)抓不到。一次無辜的重構就會讓守衛靜靜失效而測試仍綠。
  建議改 AST 走訪或把鍵集中為 backend 側常數。
- **L1 頂層未知鍵被靜默丟棄**(未修):`salvage` 只讀 `nodes`/`edges` 重組,多餘的頂層鍵
  不會進 `dropped`。strict 模式下實務上到不了,但與本模組的揭露原則不一致。
- **L2 `dropped[].reason` 無長度上限**(未修):直接放 `jsonschema` 的訊息,會整包寫進
  `ingestion_jobs.stats`。大量丟棄的 job 會產生異常肥大的列。
- **L3 strict schema 每次呼叫重讀磁碟**(未修):與 `validate_extraction` 的 import 時快取
  不同步;機率極低但診斷會痛。
- **L4 `degraded_chunks` 非零路徑無測試**(未修):只有 `salvage()` 回傳值的單元測試,
  端到端那條路徑唯一的斷言是 `== 0`。
- **S1 被挽救的 chunk 丟失了觸發挽救的整包錯誤**(未修):挽救成功時 `error=None`,
  `stats.extraction_errors` 因此沒有該 chunk。診斷「模型為什麼一直送壞東西」時,
  那個錯誤原文比逐元素理由更有訊息量。
- **S2 `_drop` 未約束 `id` 型別**(未修,防禦性)。

## Risks, Uncertainty, and Review Hotspots

建議 reviewer 優先看這四處:

1. **`drop_strict_nulls` 的「只剝除選用欄位」邊界**(`strict_schema.py`)。若誤剝必填欄位,
   會把壞元素變成看似不完整的元素,削弱 salvage 的揭露。已有測試,但這是最容易寫錯的地方。
2. **連帶丟棄的判準**(`salvage.py`)。「提案過又被丟掉」才連帶,「從未提案」不連帶。
   兩者搞混會刪掉大量正確的邊(抽取本來就被要求引用既有概念)。
3. **`degraded` 不阻擋是刻意的**(D1b)。等於接受「模型系統性劣化時 job 仍回報 success,
   只在 `degraded_chunks` 顯示」。若 reviewer 認為這對治理主軸太寬鬆,是可爭論的決策點。
4. **路徑偏離**(上節第 1 點)——程序問題,非技術問題,但依規範應由人裁定。

不確定性:strict 模式讓挽救「不再需要」只有**單次**觀察支持;挽救是否在常態下真的極少觸發,未知。

## Rollback

`git revert` 三個 commit 即可,無資料 migration、無 schema 破壞性改動、無設定變更。
若在本變更上線後才 rollback:期間 staged 的提案仍是正常的 `proposed` 列,可照常審閱或退回,
不需資料修補。已寫入的 `dropped_*` 欄位留在 `ingestion_jobs.stats` 中,不影響讀取端。

## Evidence Consulted

- `IMPLEMENTATION_PLAN.md` revision 2(含〈已裁決事項〉與 Approval evidence)
- `TASK_LOG.md` Task 1–5
- `VERIFICATION_REPORT.md`(含自身缺陷、重複花費、一項未決觀察)
- `git diff main..HEAD` 與各 commit message
- `grep` 確認 `_extract_chunk` 呼叫端範圍
- `.github/workflows/ci.yml`(用以判斷乾淨環境證據的取得方式)
- CI run [31576344848](https://github.com/busybutlazy/bio_graphrag/actions/runs/31576344848)(PR #20)
- `REVIEW_REPORT.md`(獨立 session 審查;其 H1 促成 T6,L5 促成本報告標頭更正)
- **未查閱**:T6 之後的獨立複審(尚未進行)

## CI 補記(2026-08-12,PR #20)

本報告初版撰寫時分支尚未推送。PR #20 開啟後 CI 執行完畢,兩個 job 皆通過:

| Job | 結果 | 時間 |
|---|---|---|
| Lint & type-check | pass | 14s |
| Tests & eval (integration) | pass | 1m23s |

integration job 在全新 runner 上跑 `up -d --build → wait → make seed → make test → make eval → down -v`,
因此同時補上「乾淨環境複驗」與「`make eval` 22 題全過」兩項證據。詳見
`VERIFICATION_REPORT.md` §8,其中也列出**仍未改變**的未驗證項目。

**其後的 CI(補記,獨立審查指出本節一度落後兩個 commit)**——分支上四次 run 全部 `success`:

| run | commit | 內容 |
|---|---|---|
| 31576344848 | `0d61550` | 程式碼變更全數涵蓋 |
| 31576675173 | `15baf18` | CI 證據補記 |
| 31579692883 | `a6a9eb3` | **T6 前端揭露** |
| 31580073357 | `f9e1929` | M2 準確性更正 |

**但 CI 對 T6 的證明力有限**:倉庫沒有前端測試設施,綠燈只代表 T6 沒有弄壞 Python 那一側,
**不代表那段 UI 畫得出來**。這一點與〈Remaining Work〉的「T6 未經人眼確認」是同一件事。
